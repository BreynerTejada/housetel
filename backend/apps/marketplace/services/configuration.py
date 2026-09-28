"""Staff side of C4: booking engine settings, marketplace listing and the embeddable snippet.

Authorized exception of the plan: C4 writes `Property.marketplace_listed` (listing) and
`Property.branding["primary_color"]` (the engine color is also the hotel brand used by the guest portal and
the payment page). The logo and hero image of the engine are C4's own files (`booking-engine/<property>/`).
Every change is audited (`marketplace.*`).
"""

from django.conf import settings as django_settings
from django.db import transaction
from django.utils.html import escape

from apps.core import audit
from apps.inventory.models import Photo
from apps.marketplace.models import BookingEngineSettings, ListingContent, ListingPhoto
from apps.marketplace.services.catalog import photo_payload
from apps.marketplace.services.engine import BOOKING_ENGINE, brand, engine_settings, listing_content
from apps.marketplace.services.search import invalidate_search_cache
from apps.rates.models import RatePlan

ENGINE_FIELDS = (
    "enabled",
    "primary_color",
    "headline",
    "show_promo_field",
    "min_advance_hours",
    "max_advance_days",
    "terms",
)
LISTING_FIELDS = ("tagline", "highlights", "neighborhood")


def engine_url(prop) -> str:
    return f"{django_settings.FRONTEND_URL}/h/{prop.slug}"


def embed_url(prop) -> str:
    return f"{django_settings.FRONTEND_URL}/embed/{prop.slug}"


def marketplace_url(prop) -> str:
    return f"{django_settings.FRONTEND_URL}/hotel/{prop.slug}"


def selectable_plans(prop) -> list[RatePlan]:
    """Plans the engine may be limited to: the property's active public plans."""
    return list(
        RatePlan.objects.filter(property=prop, is_active=True, is_public=True).order_by("sort_order", "code")
    )


def engine_payload(prop) -> dict:
    settings = engine_settings(prop)
    allowed = (
        [
            str(pk)
            for pk in settings.allowed_rate_plans.order_by("sort_order", "code").values_list("pk", flat=True)
        ]
        if settings.pk
        else []
    )
    current = brand(prop, settings)
    return {
        "enabled": settings.enabled,
        "primary_color": current["primary_color"],
        "logo": current["logo"],
        "logo_is_custom": bool(settings.logo),
        "hero_image": settings.hero_image.url if settings.hero_image else None,
        "headline": settings.headline or {},
        "show_promo_field": settings.show_promo_field,
        "allowed_rate_plans": allowed,
        "min_advance_hours": settings.min_advance_hours,
        "max_advance_days": settings.max_advance_days,
        "terms": settings.terms or {},
        "rate_plans": [
            {
                "id": str(plan.pk),
                "code": plan.code,
                "name": plan.name or {},
                "kind": plan.kind,
                "channels": plan.channels or [],
                "sells_on_engine": not plan.channels or BOOKING_ENGINE in plan.channels,
            }
            for plan in selectable_plans(prop)
        ],
        "public_url": engine_url(prop),
        "embed_url": embed_url(prop),
        "property": {"name": prop.name, "slug": prop.slug, "city": prop.city},
    }


def _engine_snapshot(settings) -> dict:
    snapshot = {field: getattr(settings, field) for field in ENGINE_FIELDS}
    snapshot["allowed_rate_plans"] = (
        sorted(str(pk) for pk in settings.allowed_rate_plans.values_list("pk", flat=True))
        if settings.pk
        else []
    )
    return snapshot


def update_engine(prop, data: dict, *, actor=None) -> BookingEngineSettings:
    """Apply validated settings; `primary_color` is also written to the hotel brand."""
    with transaction.atomic():
        settings, _ = BookingEngineSettings.objects.select_for_update().get_or_create(property=prop)
        before = _engine_snapshot(settings)
        for field in ENGINE_FIELDS:
            if field in data:
                setattr(settings, field, data[field])
        settings.save()
        if "allowed_rate_plans" in data:
            settings.allowed_rate_plans.set(data["allowed_rate_plans"])
        if data.get("primary_color"):
            prop.branding = {**(prop.branding or {}), "primary_color": data["primary_color"]}
            prop.save(update_fields=["branding", "updated_at"])
        changes = audit.diff(before, _engine_snapshot(settings))
        if changes:
            transaction.on_commit(invalidate_search_cache)
            audit.record(
                action="marketplace.booking_engine_updated",
                target=settings,
                summary="Actualizó el motor de reservas",
                actor=actor,
                property=prop,
                changes=changes,
            )
    prop.booking_engine = settings
    return settings


def set_engine_image(prop, kind: str, image, *, actor=None) -> BookingEngineSettings:
    """`kind`: "logo" or "hero_image". A new file replaces (and deletes) the previous one; `image=None`
    removes it."""
    with transaction.atomic():
        settings, _ = BookingEngineSettings.objects.select_for_update().get_or_create(property=prop)
        field = getattr(settings, kind)
        old_name = field.name if field else ""
        if image is None:
            setattr(settings, kind, "")
        else:
            field.save(_image_name(kind, image), image, save=False)
        settings.save()
        audit.record(
            action=f"marketplace.{'logo' if kind == 'logo' else 'hero'}_"
            f"{'removed' if image is None else 'updated'}",
            target=settings,
            summary="Cambió la imagen del motor de reservas",
            actor=actor,
            property=prop,
        )
        if old_name:
            storage = field.storage
            transaction.on_commit(lambda: storage.exists(old_name) and storage.delete(old_name))
    prop.booking_engine = settings
    return settings


def _image_name(kind: str, image) -> str:
    import uuid
    from pathlib import Path

    extension = (Path(image.name).suffix or ".jpg").lower()
    return f"{'logo' if kind == 'logo' else 'hero'}-{uuid.uuid4().hex[:12]}{extension}"


# ---- Listing -----------------------------------------------------------------------------------------------


def listing_payload(prop) -> dict:
    listing = listing_content(prop)
    featured = (
        [
            str(pk)
            for pk in listing.listing_photos.order_by("sort_order", "created_at").values_list(
                "photo_id", flat=True
            )
        ]
        if listing.pk
        else []
    )
    photos = (
        Photo.objects.filter(property=prop, room__isnull=True)
        .select_related("room_type")
        .order_by("room_type__sort_order", "room_type__code", "sort_order", "created_at")
    )
    return {
        "marketplace_listed": prop.marketplace_listed,
        "tagline": listing.tagline or {},
        "highlights": listing.highlights or [],
        "neighborhood": listing.neighborhood,
        "featured_photo_ids": featured,
        "photos": [
            {
                **photo_payload(photo),
                "room_type": (
                    {
                        "id": str(photo.room_type.pk),
                        "code": photo.room_type.code,
                        "name": photo.room_type.name,
                    }
                    if photo.room_type_id
                    else None
                ),
            }
            for photo in photos
        ],
        "description": prop.description or {},
        "name": prop.name,
        "city": prop.city,
        "star_rating": prop.star_rating,
        "property_type": prop.property_type,
        "public_url": marketplace_url(prop),
    }


def _listing_snapshot(prop, listing) -> dict:
    snapshot = {field: getattr(listing, field) for field in LISTING_FIELDS}
    snapshot["marketplace_listed"] = prop.marketplace_listed
    snapshot["featured_photo_ids"] = (
        [str(pk) for pk in listing.listing_photos.order_by("sort_order").values_list("photo_id", flat=True)]
        if listing.pk
        else []
    )
    return snapshot


def update_listing(prop, data: dict, *, actor=None) -> ListingContent:
    with transaction.atomic():
        listing, _ = ListingContent.objects.select_for_update().get_or_create(property=prop)
        before = _listing_snapshot(prop, listing)
        for field in LISTING_FIELDS:
            if field in data:
                setattr(listing, field, data[field])
        listing.save()
        if "featured_photo_ids" in data:
            listing.listing_photos.all().delete()
            ListingPhoto.objects.bulk_create(
                ListingPhoto(listing=listing, photo_id=photo_id, sort_order=index)
                for index, photo_id in enumerate(data["featured_photo_ids"])
            )
        if "marketplace_listed" in data and data["marketplace_listed"] != prop.marketplace_listed:
            prop.marketplace_listed = data["marketplace_listed"]
            prop.save(update_fields=["marketplace_listed", "updated_at"])
        changes = audit.diff(before, _listing_snapshot(prop, listing))
        if changes:
            transaction.on_commit(invalidate_search_cache)
            audit.record(
                action="marketplace.listing_updated",
                target=listing,
                summary="Actualizó la ficha del marketplace",
                actor=actor,
                property=prop,
                changes=changes,
            )
    prop.listing = listing
    return listing


# ---- Embed ----------------------------------------------------------------------------------------------


def embed_snippet(prop) -> dict:
    engine, widget = engine_url(prop), embed_url(prop)
    title = escape(f"Reservas · {prop.name}")
    color = brand(prop)["primary_color"]
    return {
        "engine_url": engine,
        "embed_url": widget,
        "iframe": (
            f'<iframe src="{widget}" title="{title}" loading="lazy" '
            'style="width:100%;max-width:980px;height:190px;border:0;border-radius:14px"></iframe>'
        ),
        "button": (
            f'<a href="{engine}" target="_blank" rel="noopener" '
            'style="display:inline-block;padding:12px 22px;'
            f"border-radius:10px;background:{color};color:#fff;font:600 16px/1.2 system-ui,sans-serif;"
            f'text-decoration:none">Reservar ahora</a>'
        ),
    }
