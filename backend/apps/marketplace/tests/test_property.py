"""Public hotel page and offers (marketplace and booking engine)."""

from decimal import Decimal

import pytest

from apps.core.models import IntegrationSetting
from apps.marketplace.models import BookingEngineSettings, ListingContent, ListingPhoto
from apps.marketplace.tests.conftest import PUBLIC
from apps.marketplace.tests.helpers import add_photo, build_hotel, day, new_property

pytestmark = pytest.mark.django_db


def _offers(public_api, hotel, expected=200, **params):
    query = {"checkin": day(8).isoformat(), "checkout": day(10).isoformat(), "adults": 2, **params}
    response = public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/offers/", query)
    assert response.status_code == expected, response.json()
    return response.json()


def _plans(data):
    return sorted({(offer["room_type"]["code"], offer["rate_plan"]["code"]) for offer in data["offers"]})


class TestPropertyPage:
    def test_shows_the_public_hotel_page(self, public_api, hotel):
        from apps.inventory.models import CustomFieldDefinition

        gallery = add_photo(hotel.prop, sort_order=1)
        room_photo = add_photo(hotel.prop, room_type=hotel.ste, sort_order=1)
        listing = ListingContent.objects.create(
            property=hotel.prop,
            neighborhood="Centro Histórico",
            tagline={"es": "Casa colonial", "en": "Colonial house"},
            highlights=[{"es": "Piscina en la terraza", "en": "Rooftop pool"}],
        )
        ListingPhoto.objects.create(listing=listing, photo=room_photo, sort_order=0)
        CustomFieldDefinition.objects.create(
            organization=hotel.prop.organization,
            applies_to="room_type",
            key="orientation",
            label={"es": "Orientación", "en": "Orientation"},
            field_type="select",
            options=[{"value": "sea", "label": {"es": "Mar", "en": "Sea"}}],
            show_in_marketplace=True,
        )
        hotel.ste.custom_values = {"orientation": "sea"}
        hotel.ste.save(update_fields=["custom_values"])

        response = public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == hotel.prop.name
        assert data["neighborhood"] == "Centro Histórico"
        assert data["highlights"] == [{"es": "Piscina en la terraza", "en": "Rooftop pool"}]
        # featured photos first (listing order), then the hotel gallery
        assert [photo["id"] for photo in data["photos"]] == [str(room_photo.pk), str(gallery.pk)]
        assert data["check_in_time"] == "15:00"
        assert data["policies"]["min_checkin_age"] == 18
        assert [rt["code"] for rt in data["room_types"]] == ["DBL", "STE"]
        suite = data["room_types"][1]
        assert suite["max_occupancy"] == 4
        assert suite["units_count"] == 1
        assert [photo["id"] for photo in suite["photos"]] == [str(room_photo.pk)]
        assert suite["features"] == [
            {
                "key": "orientation",
                "label": {"es": "Orientación", "en": "Orientation"},
                "field_type": "select",
                "value": "sea",
                "display": [{"es": "Mar", "en": "Sea"}],
            }
        ]
        # only extras sold online
        assert [extra["code"] for extra in data["extras"]] == ["BRK"]
        # cancellation policies of the plans this channel sells (CORP is not public)
        assert sorted(policy["name"]["es"] for policy in data["cancellation_policies"]) == [
            "Flexible 48h",
            "No reembolsable",
        ]
        assert data["booking"]["earliest_checkin"] == "2026-10-01"
        assert data["booking"]["online_payments"] is True

    def test_typical_attributes_come_from_the_rooms(self, public_api, hotel):
        from apps.inventory.tests.factories import RoomFactory

        hotel.ste.size_m2 = Decimal("42")
        hotel.ste.view = "sea"
        hotel.ste.save(update_fields=["size_m2", "view"])
        RoomFactory(room_type=hotel.ste, number="306", overrides={"size_m2": "48.00", "view": "panoramic"})

        data = public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/").json()

        suite = next(rt for rt in data["room_types"] if rt["code"] == "STE")
        assert suite["size_m2_range"] == ["42.00", "48.00"]
        assert set(suite["views"]) == {"sea", "panoramic"}
        assert suite["units_count"] == 2

    def test_unlisted_hotels_are_not_in_the_marketplace_but_keep_their_booking_engine(self, public_api):
        hotel = build_hotel(new_property(slug="directo"), listed=False)

        assert public_api.get(f"{PUBLIC}/properties/directo/").status_code == 404
        engine = public_api.get(f"{PUBLIC}/properties/directo/", {"via": "booking_engine"})
        assert engine.status_code == 200
        assert engine.json()["slug"] == hotel.prop.slug

    def test_the_hotel_page_carries_the_booking_engine_texts(self, public_api, hotel):
        BookingEngineSettings.objects.create(
            property=hotel.prop,
            headline={"es": "Duerme dentro de la muralla", "en": "Sleep inside the walls"},
            terms={"es": "No se admiten mascotas.", "en": "No pets."},
        )

        data = public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/", {"via": "booking_engine"}).json()

        assert data["headline"] == {"es": "Duerme dentro de la muralla", "en": "Sleep inside the walls"}
        assert data["terms"] == {"es": "No se admiten mascotas.", "en": "No pets."}
        # the marketplace checkout shows the same hotel terms
        assert public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/").json()["terms"]["en"] == "No pets."

    def test_a_disabled_booking_engine_answers_404(self, public_api, hotel):
        BookingEngineSettings.objects.create(property=hotel.prop, enabled=False)

        response = public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/", {"via": "booking_engine"})

        assert response.status_code == 404
        assert response.json()["code"] == "booking_engine_disabled"
        assert public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/").status_code == 200

    def test_suspended_organizations_do_not_sell(self, public_api, hotel):
        hotel.prop.organization.status = "suspended"
        hotel.prop.organization.save(update_fields=["status"])

        assert public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/").status_code == 404
        response = public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/", {"via": "booking_engine"})
        assert response.status_code == 404


class TestOffers:
    def test_offers_never_include_plans_that_are_not_public(self, public_api, hotel):
        data = _offers(public_api, hotel)

        assert _plans(data) == [("DBL", "FLEX"), ("DBL", "NR"), ("STE", "FLEX"), ("STE", "NR")]
        assert all(offer["rate_plan"]["code"] != "CORP" for offer in data["offers"])

    def test_plans_restricted_to_other_channels_are_left_out(self, public_api, hotel):
        hotel.nr.channels = ["booking_engine"]
        hotel.nr.save(update_fields=["channels"])

        assert _plans(_offers(public_api, hotel)) == [("DBL", "FLEX"), ("STE", "FLEX")]
        assert ("DBL", "NR") in _plans(_offers(public_api, hotel, via="booking_engine"))

    def test_the_booking_engine_only_sells_its_allowed_plans(self, public_api, hotel):
        settings = BookingEngineSettings.objects.create(property=hotel.prop)
        settings.allowed_rate_plans.set([hotel.flex])

        assert _plans(_offers(public_api, hotel, via="booking_engine")) == [("DBL", "FLEX"), ("STE", "FLEX")]
        assert len(_plans(_offers(public_api, hotel))) == 4  # the marketplace is not affected

    def test_offers_carry_the_exact_total_cheapest_first(self, public_api, hotel):
        data = _offers(public_api, hotel)

        first = data["offers"][0]
        assert (first["room_type"]["code"], first["rate_plan"]["code"]) == ("DBL", "NR")
        # 281.600 × 2 nights + 19 % IVA per night (53.504 × 2)
        assert first["net_total"] == "563200.00"
        assert first["tax_total"] == "107008.00"
        assert first["total"] == "670208.00"
        assert first["per_night"] == "335104.00"
        assert first["max_quantity"] == 2  # two DBL rooms free
        assert first["rate_plan"]["cancellation_policy"]["non_refundable"] is True
        assert data["nights"] == 2
        assert data["tax_exempt"] is False

    def test_foreign_non_residents_see_totals_without_iva(self, public_api, hotel):
        data = _offers(public_api, hotel, foreign="true")

        first = data["offers"][0]
        assert data["tax_exempt"] is True
        assert first["tax_exempt"] is True
        assert first["tax_total"] == "0.00"
        assert first["total"] == "563200.00"

    def test_a_promo_code_is_applied_and_reported(self, public_api, hotel):
        from apps.rates.models import PromoCode

        PromoCode.objects.create(property=hotel.prop, code="BIENVENIDA10", discount_type="percent", value=10)

        data = _offers(public_api, hotel, promo_code="bienvenida10")

        assert data["promo"] == {"code": "BIENVENIDA10", "applied": True}
        flex = next(
            o for o in data["offers"] if o["room_type"]["code"] == "DBL" and o["rate_plan"]["code"] == "FLEX"
        )
        # 320.000 − 10 % = 288.000 × 2 = 576.000 + IVA 109.440
        assert flex["total"] == "685440.00"
        assert _offers(public_api, hotel, promo_code="NOEXISTE")["promo"] == {
            "code": "NOEXISTE",
            "applied": False,
        }

    def test_deposit_plans_are_hidden_while_online_payments_are_off(self, public_api, hotel):
        hotel.flex.deposit_percent = Decimal("30")
        hotel.flex.save(update_fields=["deposit_percent"])
        IntegrationSetting.objects.create(property=hotel.prop, kind="payments", enabled=False)

        data = _offers(public_api, hotel)

        assert _plans(data) == [("DBL", "NR"), ("STE", "NR")]
        assert data["online_payments"] is False

    def test_dorm_beds_are_priced_per_guest(self, public_api, hotel):
        from apps.inventory.tests.factories import BedFactory, DormRoomTypeFactory, RoomFactory
        from apps.rates.tests.factories import RoomTypeRateDefaultsFactory

        dorm = DormRoomTypeFactory(property=hotel.prop, code="D6", sort_order=3)
        room = RoomFactory(room_type=dorm, number="D1")
        for label in "ABC":
            BedFactory(room=room, label=label)
        hotel.flex.room_types.add(dorm)
        RoomTypeRateDefaultsFactory(room_type=dorm, rate_plan=hotel.flex, price=Decimal("65000"))

        data = _offers(public_api, hotel, adults=3)

        beds = next(o for o in data["offers"] if o["room_type"]["code"] == "D6")
        assert beds["units_needed"] == 3
        assert beds["max_quantity"] == 1
        # 3 beds × 2 nights × (65.000 + 12.350 IVA)
        assert beds["total"] == "464100.00"

    @pytest.mark.parametrize(
        ("settings_kwargs", "checkin", "code"),
        [
            ({"min_advance_hours": 48}, 1, "too_soon"),
            ({"max_advance_days": 30}, 40, "too_far"),
        ],
    )
    def test_the_booking_window_is_enforced(self, public_api, hotel, settings_kwargs, checkin, code):
        BookingEngineSettings.objects.create(property=hotel.prop, **settings_kwargs)

        data = _offers(
            public_api,
            hotel,
            expected=400,
            checkin=day(checkin).isoformat(),
            checkout=day(checkin + 2).isoformat(),
        )

        assert data["code"] == code

    def test_offers_need_dates(self, public_api, hotel):
        response = public_api.get(f"{PUBLIC}/properties/{hotel.prop.slug}/offers/", {"adults": 2})

        assert response.status_code == 400
        assert response.json()["code"] == "validation_error"
