"""Public catalog: destinations, property cards and the public hotel page (photos are public media)."""

from collections import Counter

from django.db.models import Count, Q

from apps.core.models import Property
from apps.inventory.models import Amenity, CustomFieldDefinition, Photo, Room, RoomType
from apps.marketplace.services.engine import (
    BOOKING_ENGINE,
    MARKETPLACE,
    allowed_plan_ids,
    booking_window,
    brand,
    engine_settings,
    listed_properties,
    listing_content,
    online_payments_enabled,
)
from apps.rates.models import Extra, RatePlan

CARD_AMENITIES = 6
CARD_PHOTOS = 4
DEFAULT_POLICIES = {
    "pets_allowed": False,
    "smoking_allowed": False,
    "children_allowed": True,
    "events_allowed": False,
    "min_checkin_age": 18,
}


# ---- Destinations --------------------------------------------------------------------------------------


def destinations() -> list[dict]:
    """Cities with listed properties, most properties first, each with a cover photo."""
    rows = (
        listed_properties()
        .values("city", "department")
        .annotate(properties_count=Count("pk"))
        .order_by("-properties_count", "city")
    )
    result = []
    for row in rows:
        if not row["city"]:
            continue
        cover = None
        for prop in listed_properties().filter(city=row["city"]).order_by("-star_rating", "name"):
            photos = property_photos(prop)
            if photos:
                cover = photos[0].image.url
                break
        result.append(
            {
                "city": row["city"],
                "department": row["department"],
                "properties_count": row["properties_count"],
                "cover_photo": cover,
            }
        )
    return result


# ---- Amenities -----------------------------------------------------------------------------------------


def amenity_codes(prop) -> list[str]:
    """Hotel amenities (`Property.settings["amenities"]`, in their order) then the amenities of its active
    categories, most common first."""
    own = [code for code in (prop.settings or {}).get("amenities", []) if isinstance(code, str)]
    counts = Counter(
        RoomType.objects.filter(property=prop, is_active=True).values_list("amenities__code", flat=True)
    )
    counts.pop(None, None)
    from_rooms = sorted((code for code in counts if code not in own), key=lambda code: (-counts[code], code))
    return [*dict.fromkeys(own), *from_rooms]


def amenity_index(organization, codes) -> dict[str, dict]:
    """`{code: {code, name, icon, category}}`; an organization's own amenity wins over the global one."""
    index = {}
    rows = Amenity.objects.filter(
        Q(organization__isnull=True) | Q(organization=organization), code__in=set(codes)
    ).order_by("organization_id")  # nulls (global) last in PostgreSQL ascending order → own rows first
    for amenity in rows:
        index.setdefault(amenity.code, amenity_payload(amenity))
    return index


def amenity_payload(amenity) -> dict:
    return {"code": amenity.code, "name": amenity.name, "icon": amenity.icon, "category": amenity.category}


def resolve_amenities(organization, codes) -> list[dict]:
    index = amenity_index(organization, codes)
    return [index[code] for code in codes if code in index]


# ---- Photos --------------------------------------------------------------------------------------------


def photo_payload(photo) -> dict:
    return {"id": str(photo.pk), "url": photo.image.url, "caption": photo.caption or {}}


def property_photos(prop, listing=None) -> list[Photo]:
    """Featured photos (listing order), then the hotel gallery, then the categories' photos; no repeats."""
    listing = listing if listing is not None else listing_content(prop)
    featured = (
        [
            item.photo
            for item in listing.listing_photos.select_related("photo").order_by("sort_order", "created_at")
        ]
        if listing.pk
        else []
    )
    gallery = list(Photo.objects.filter(property=prop, room_type__isnull=True, room__isnull=True))
    categories = list(
        Photo.objects.filter(property=prop, room_type__is_active=True, room__isnull=True).order_by(
            "room_type__sort_order", "room_type__code", "sort_order", "created_at"
        )
    )
    seen, ordered = set(), []
    for photo in [*featured, *gallery, *categories]:
        if photo.pk not in seen:
            seen.add(photo.pk)
            ordered.append(photo)
    return ordered


# ---- Cards (search results, home) ----------------------------------------------------------------------


def property_card(prop) -> dict:
    listing = listing_content(prop)
    photos = property_photos(prop, listing)
    codes = amenity_codes(prop)
    return {
        "slug": prop.slug,
        "name": prop.name,
        "property_type": prop.property_type,
        "star_rating": prop.star_rating,
        "city": prop.city,
        "department": prop.department,
        "neighborhood": listing.neighborhood,
        "tagline": listing.tagline or {},
        "highlights": listing.highlights or [],
        "photo": photos[0].image.url if photos else None,
        "photos": [photo.image.url for photo in photos[:CARD_PHOTOS]],
        "amenities": resolve_amenities(prop.organization, codes)[:CARD_AMENITIES],
        "amenity_codes": codes,
        "currency": prop.currency or "COP",
    }


# ---- Public hotel page ---------------------------------------------------------------------------------


def channel_plans(prop, via: str, settings=None) -> list[RatePlan]:
    """Active plans this channel sells: public ones (and, on the booking engine, only the allowed ones)."""
    plans = (
        RatePlan.objects.filter(property=prop, is_active=True, is_public=True)
        .select_related("cancellation_policy", "parent__cancellation_policy")
        .prefetch_related("room_types")
        .order_by("sort_order", "code")
    )
    allowed = allowed_plan_ids(settings or engine_settings(prop)) if via == BOOKING_ENGINE else set()
    result = []
    for plan in plans:
        channels = plan.channels or []
        if channels and via not in channels:
            continue
        if allowed and plan.pk not in allowed:
            continue
        result.append(plan)
    return result


def effective_policy(plan):
    policy = plan.cancellation_policy
    if policy is None and plan.parent_id:
        policy = plan.parent.cancellation_policy
    return policy


def policy_payload(policy) -> dict | None:
    if policy is None:
        return None
    return {
        "id": str(policy.pk),
        "name": policy.name or {},
        "description": policy.description or {},
        "non_refundable": policy.non_refundable,
        "free_until_hours_before": policy.free_until_hours_before,
        "penalty_type": policy.penalty_type,
        "penalty_value": format(policy.penalty_value, "f"),
    }


def _features(definitions, values) -> list[dict]:
    """Custom fields shown in the marketplace (`show_in_marketplace`) with their option labels."""
    features = []
    for definition in definitions:
        value = (values or {}).get(definition.key)
        if value in (None, "", []):
            continue
        labels = {}
        for option in definition.options or []:
            if isinstance(option, dict):
                labels[option.get("value")] = option.get("label") or {}
        chosen = value if isinstance(value, list) else [value]
        display = [labels[item] for item in chosen if item in labels] if labels else None
        features.append(
            {
                "key": definition.key,
                "label": definition.label or {},
                "field_type": definition.field_type,
                "value": value,
                "display": display,
            }
        )
    return features


def _typical(rooms, category) -> dict:
    """What most rooms of a category look like (rooms may override size, view, amenities…)."""
    from apps.inventory.services import effective_attributes

    attributes = [effective_attributes(room) for room in rooms]
    if not attributes:
        return {
            "size_m2_range": None,
            "views": [category.view] if category.view else [],
            "amenities": sorted(amenity.code for amenity in category.amenities.all()),
        }
    sizes = sorted({a["size_m2"] for a in attributes if a["size_m2"] is not None})
    views = Counter(a["view"] for a in attributes if a["view"])
    amenity_counts = Counter(code for a in attributes for code in a["amenities"])
    return {
        "size_m2_range": [format(sizes[0], "f"), format(sizes[-1], "f")] if len(sizes) > 1 else None,
        "views": [view for view, _ in views.most_common()],
        "amenities": sorted(code for code, count in amenity_counts.items() if count * 2 > len(attributes)),
    }


def room_type_payloads(prop, plans) -> list[dict]:
    sold = {room_type.pk for plan in plans for room_type in plan.room_types.all()}
    categories = list(
        RoomType.objects.filter(property=prop, is_active=True, pk__in=sold)
        .prefetch_related("amenities", "photos")
        .order_by("sort_order", "code")
    )
    rooms_by_type: dict = {}
    for room in (
        Room.objects.filter(property=prop, is_active=True, room_type__in=categories)
        .select_related("room_type")
        .prefetch_related("room_type__amenities", "extra_amenities", "removed_amenities", "beds")
    ):
        rooms_by_type.setdefault(room.room_type_id, []).append(room)
    definitions = list(
        CustomFieldDefinition.objects.filter(
            Q(property__isnull=True) | Q(property=prop),
            organization=prop.organization,
            applies_to=CustomFieldDefinition.AppliesTo.ROOM_TYPE,
            show_in_marketplace=True,
        ).order_by("sort_order", "key")
    )
    all_codes = {amenity.code for category in categories for amenity in category.amenities.all()}
    index = amenity_index(prop.organization, all_codes)
    payloads = []
    for category in categories:
        rooms = rooms_by_type.get(category.pk, [])
        typical = _typical(rooms, category)
        if category.kind == RoomType.Kind.DORM:
            units = sum(1 for room in rooms for bed in room.beds.all() if bed.is_active)
        else:
            units = len(rooms)
        payloads.append(
            {
                "id": str(category.pk),
                "code": category.code,
                "name": category.name or {},
                "description": category.description or {},
                "kind": category.kind,
                "base_occupancy": category.base_occupancy,
                "max_adults": category.max_adults,
                "max_children": category.max_children,
                "max_occupancy": category.max_occupancy,
                "beds": category.beds or [],
                "size_m2": format(category.size_m2, "f") if category.size_m2 is not None else None,
                "size_m2_range": typical["size_m2_range"],
                "views": typical["views"],
                "smoking_allowed": category.smoking_allowed,
                "accessible": category.accessible,
                "amenities": [index[code] for code in typical["amenities"] if code in index],
                "photos": [photo_payload(photo) for photo in category.photos.all() if photo.room_id is None],
                "features": _features(definitions, category.custom_values),
                "units_count": units,
            }
        )
    return payloads


def extras_payload(prop) -> list[dict]:
    extras = Extra.objects.filter(property=prop, is_active=True, sellable_online=True).select_related("tax")
    return [
        {
            "id": str(extra.pk),
            "code": extra.code,
            "name": extra.name or {},
            "price": format(extra.price, "f"),
            "charge_type": extra.charge_type,
            "tax_rate": format(extra.tax.rate, "f") if extra.tax_id and extra.tax.is_active else None,
            "tax_included": bool(extra.tax_id and extra.tax.is_active and extra.tax.included_in_price),
        }
        for extra in extras
    ]


def property_detail(prop: Property, via: str = MARKETPLACE) -> dict:
    """Everything the public hotel page shows (marketplace or booking engine)."""
    settings = engine_settings(prop)
    listing = listing_content(prop)
    plans = channel_plans(prop, via, settings)
    photos = property_photos(prop, listing)
    policies = {**DEFAULT_POLICIES, **((prop.settings or {}).get("policies") or {})}
    seen_policies, cancellation = set(), []
    for plan in plans:
        policy = effective_policy(plan)
        if policy is not None and policy.pk not in seen_policies:
            seen_policies.add(policy.pk)
            cancellation.append(policy_payload(policy))
    card = property_card(prop)
    card.pop("amenity_codes", None)  # internal: the search filters by it
    return {
        **card,
        "description": prop.description or {},
        "address": prop.address,
        "country": prop.country,
        "latitude": format(prop.latitude, "f") if prop.latitude is not None else None,
        "longitude": format(prop.longitude, "f") if prop.longitude is not None else None,
        "phone": prop.phone,
        "email": prop.email,
        "website": prop.website,
        "rnt_number": prop.rnt_number,
        "check_in_time": prop.check_in_time.strftime("%H:%M") if prop.check_in_time else None,
        "check_out_time": prop.check_out_time.strftime("%H:%M") if prop.check_out_time else None,
        "house_rules": prop.house_rules or {},
        "policies": policies,
        "languages": (prop.settings or {}).get("languages") or [prop.default_language or "es"],
        "amenities": resolve_amenities(prop.organization, amenity_codes(prop)),
        "photos": [photo_payload(photo) for photo in photos],
        "hero_image": settings.hero_image.url
        if settings.hero_image
        else (photos[0].image.url if photos else None),
        "room_types": room_type_payloads(prop, plans),
        "cancellation_policies": cancellation,
        "extras": extras_payload(prop),
        "headline": settings.headline or {},
        "terms": settings.terms or {},
        "booking": {
            **booking_window(prop, settings).as_dict(),
            "min_advance_hours": settings.min_advance_hours,
            "max_advance_days": settings.max_advance_days,
            "show_promo_field": settings.show_promo_field,
            "online_payments": online_payments_enabled(prop),
        },
        "brand": brand(prop, settings),
        "marketplace_listed": prop.marketplace_listed,
        "booking_engine_enabled": settings.enabled,
        "via": via,
    }


def engine_config(prop: Property) -> dict:
    """Public config of the hotel's booking engine (`/h/<slug>`, `/embed/<slug>`): brand, texts, window."""
    settings = engine_settings(prop)
    photos = property_photos(prop)
    return {
        "slug": prop.slug,
        "name": prop.name,
        "city": prop.city,
        "department": prop.department,
        "property_type": prop.property_type,
        "star_rating": prop.star_rating,
        "address": prop.address,
        "phone": prop.phone,
        "email": prop.email,
        "currency": prop.currency or "COP",
        "enabled": settings.enabled,
        **brand(prop, settings),
        "hero_image": settings.hero_image.url
        if settings.hero_image
        else (photos[0].image.url if photos else None),
        "headline": settings.headline or {},
        "show_promo_field": settings.show_promo_field,
        "terms": settings.terms or {},
        "booking": {
            **booking_window(prop, settings).as_dict(),
            "online_payments": online_payments_enabled(prop),
        },
        "languages": (prop.settings or {}).get("languages") or [prop.default_language or "es"],
    }
