"""Staff settings of the booking engine and the marketplace listing (`marketplace.manage`)."""

import pytest
from django.conf import settings

from apps.core.models import AuditEvent
from apps.marketplace.models import BookingEngineSettings, ListingContent
from apps.marketplace.tests.conftest import PUBLIC, STAFF
from apps.marketplace.tests.helpers import add_photo, build_hotel, image_file, new_property

pytestmark = pytest.mark.django_db


class TestAccess:
    @pytest.mark.parametrize("path", ["booking-engine/", "listing/", "embed-snippet/"])
    def test_front_desk_cannot_manage_the_booking_engine(self, api_for, make_member, prop, path):
        response = api_for(make_member("front_desk"), prop).get(f"{STAFF}/{path}")

        assert response.status_code == 403
        assert response.json()["permission"] == "marketplace.manage"

    @pytest.mark.parametrize("path", ["booking-engine/", "listing/", "embed-snippet/"])
    def test_another_organization_never_sees_the_settings(self, stranger_api, hotel, path):
        assert stranger_api.get(f"{STAFF}/{path}").status_code == 404

    def test_anonymous_gets_401(self, public_api, prop):
        response = public_api.get(f"{STAFF}/booking-engine/", HTTP_X_PROPERTY_ID=str(prop.pk))

        assert response.status_code == 401

    def test_settings_are_isolated_per_property(self, api, api_for, owner, hotel):
        other = build_hotel(new_property(hotel.prop.organization, slug="hermano"))
        api.patch(f"{STAFF}/booking-engine/", {"headline": {"es": "Solo Aurora"}}, format="json")

        data = api_for(owner, other.prop).get(f"{STAFF}/booking-engine/").json()

        assert data["headline"] == {}
        assert BookingEngineSettings.objects.get().property == hotel.prop


class TestBookingEngineSettings:
    def test_defaults_without_a_row(self, api, hotel):
        hotel.prop.branding = {"primary_color": "#4E6C88"}
        hotel.prop.save(update_fields=["branding"])

        data = api.get(f"{STAFF}/booking-engine/").json()

        assert data["enabled"] is True
        assert data["primary_color"] == "#4E6C88"  # the hotel brand until the engine sets its own
        assert data["min_advance_hours"] == 0
        assert data["max_advance_days"] == 365
        assert data["allowed_rate_plans"] == []
        assert {plan["code"] for plan in data["rate_plans"]} == {"FLEX", "NR"}  # public plans only
        assert data["public_url"] == f"{settings.FRONTEND_URL}/h/{hotel.prop.slug}"
        assert not BookingEngineSettings.objects.exists()

    def test_patch_updates_the_engine_and_the_hotel_brand(self, api, hotel):
        response = api.patch(
            f"{STAFF}/booking-engine/",
            {
                "primary_color": "#2f6b5e",
                "headline": {"es": "Tu casa en Cartagena", "en": "Your home in Cartagena"},
                "show_promo_field": False,
                "allowed_rate_plans": [str(hotel.flex.pk)],
                "min_advance_hours": 24,
                "max_advance_days": 180,
                "terms": {"es": "Check-in desde las 15:00"},
            },
            format="json",
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["primary_color"] == "#2F6B5E"
        assert data["allowed_rate_plans"] == [str(hotel.flex.pk)]
        engine = BookingEngineSettings.objects.get(property=hotel.prop)
        assert (engine.min_advance_hours, engine.max_advance_days, engine.show_promo_field) == (
            24,
            180,
            False,
        )
        hotel.prop.refresh_from_db()
        assert hotel.prop.branding["primary_color"] == "#2F6B5E"
        event = AuditEvent.objects.get(action="marketplace.booking_engine_updated")
        assert event.property == hotel.prop
        assert "primary_color" in event.changes

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"primary_color": "rojo"}, "primary_color"),
            ({"max_advance_days": 0}, "max_advance_days"),
            ({"min_advance_hours": 1000}, "min_advance_hours"),
            ({"headline": {"es": "x" * 121}}, "headline"),
        ],
    )
    def test_invalid_values_answer_400(self, api, hotel, payload, field):
        response = api.patch(f"{STAFF}/booking-engine/", payload, format="json")

        assert response.status_code == 400
        assert field in response.json()["fields"]

    def test_plans_of_other_properties_or_not_public_are_rejected(self, api, hotel):
        other = build_hotel(new_property(slug="ajeno"))

        for plan in (other.flex, hotel.corp):
            response = api.patch(
                f"{STAFF}/booking-engine/", {"allowed_rate_plans": [str(plan.pk)]}, format="json"
            )
            assert response.status_code == 400
            assert "allowed_rate_plans" in response.json()["fields"]

    def test_uploads_and_removes_the_logo_and_the_hero_image(self, api, hotel):
        for kind in ("logo", "hero"):
            response = api.post(
                f"{STAFF}/booking-engine/{kind}/",
                {"image": image_file(f"{kind}.png", fmt="PNG")},
                format="multipart",
            )
            assert response.status_code == 200, response.json()
        data = response.json()
        assert data["logo"].startswith("/media/booking-engine/")
        assert data["hero_image"].startswith("/media/booking-engine/")

        assert api.delete(f"{STAFF}/booking-engine/hero/").json()["hero_image"] is None
        assert api.delete(f"{STAFF}/booking-engine/logo/").json()["logo"] == ""

    def test_rejects_files_that_are_not_images(self, api, hotel):
        from django.core.files.uploadedfile import SimpleUploadedFile

        fake = SimpleUploadedFile("logo.png", b"not an image", content_type="image/png")

        response = api.post(f"{STAFF}/booking-engine/logo/", {"image": fake}, format="multipart")

        assert response.status_code == 400


class TestListing:
    def test_patch_lists_the_hotel_and_features_photos_in_order(self, api, hotel):
        first = add_photo(hotel.prop, sort_order=1)
        second = add_photo(hotel.prop, room_type=hotel.dbl, sort_order=2)
        hotel.prop.marketplace_listed = False
        hotel.prop.save(update_fields=["marketplace_listed"])

        response = api.patch(
            f"{STAFF}/listing/",
            {
                "marketplace_listed": True,
                "neighborhood": "Getsemaní",
                "tagline": {"es": "Casa colonial con piscina", "en": "Colonial house with a pool"},
                "highlights": [{"es": "Terraza con vista", "en": "Rooftop view"}],
                "featured_photo_ids": [str(second.pk), str(first.pk)],
            },
            format="json",
        )

        assert response.status_code == 200, response.json()
        data = response.json()
        assert data["featured_photo_ids"] == [str(second.pk), str(first.pk)]
        assert {photo["id"] for photo in data["photos"]} == {str(first.pk), str(second.pk)}
        hotel.prop.refresh_from_db()
        assert hotel.prop.marketplace_listed is True
        listing = ListingContent.objects.get(property=hotel.prop)
        assert listing.neighborhood == "Getsemaní"
        public = api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/").json()
        assert [photo["id"] for photo in public["photos"]][:2] == [str(second.pk), str(first.pk)]
        assert AuditEvent.objects.filter(action="marketplace.listing_updated", property=hotel.prop).exists()

    def test_photos_of_other_properties_cannot_be_featured(self, api, hotel):
        other = build_hotel(new_property(slug="ajeno"))
        foreign_photo = add_photo(other.prop, sort_order=1)

        response = api.patch(
            f"{STAFF}/listing/", {"featured_photo_ids": [str(foreign_photo.pk)]}, format="json"
        )

        assert response.status_code == 400
        assert "featured_photo_ids" in response.json()["fields"]

    def test_highlights_are_limited(self, api, hotel):
        response = api.patch(
            f"{STAFF}/listing/", {"highlights": [{"es": f"Punto {n}"} for n in range(7)]}, format="json"
        )

        assert response.status_code == 400
        assert "highlights" in response.json()["fields"]

    def test_unlisting_takes_the_hotel_out_of_the_marketplace(self, api, public_api, hotel):
        api.patch(f"{STAFF}/listing/", {"marketplace_listed": False}, format="json")

        assert public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/").status_code == 404


class TestEmbedAndPublicConfig:
    def test_the_snippet_points_to_the_hotel_engine(self, api, hotel):
        data = api.get(f"{STAFF}/embed-snippet/").json()

        assert data["engine_url"] == f"{settings.FRONTEND_URL}/h/{hotel.prop.slug}"
        assert data["embed_url"] == f"{settings.FRONTEND_URL}/embed/{hotel.prop.slug}"
        assert f'src="{data["embed_url"]}"' in data["iframe"]
        assert data["engine_url"] in data["button"]

    def test_public_config_of_the_booking_engine(self, api, public_api, hotel):
        api.patch(
            f"{STAFF}/booking-engine/",
            {"primary_color": "#2F6B5E", "headline": {"es": "Bienvenidos"}, "show_promo_field": False},
            format="json",
        )

        data = public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/booking-engine/").json()

        assert data["slug"] == hotel.prop.slug
        assert data["enabled"] is True
        assert data["primary_color"] == "#2F6B5E"
        assert data["headline"] == {"es": "Bienvenidos"}
        assert data["show_promo_field"] is False
        assert data["booking"]["earliest_checkin"] == "2026-10-01"

    def test_public_config_of_an_unknown_hotel_is_404(self, public_api):
        assert public_api.get(f"{PUBLIC}/properties/no-existe/booking-engine/").status_code == 404
