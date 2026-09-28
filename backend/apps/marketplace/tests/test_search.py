"""Public marketplace catalog: destinations and search (plan C4 › Público)."""

from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.core.tests.factories import OrganizationFactory
from apps.marketplace.tests.conftest import PUBLIC
from apps.marketplace.tests.helpers import build_hotel, day, new_property

pytestmark = pytest.mark.django_db


def _search(public_api, **params):
    params.setdefault("adults", 2)
    response = public_api.get(f"{PUBLIC}/search/", params)
    assert response.status_code == 200, response.json()
    return response.json()


def _fill_dbl_and_ste(hotel, checkin, checkout):
    """Book every sellable unit of the hotel for the range (through the real booking service)."""
    from apps.bookings.services.reservations import create_reservation
    from apps.bookings.types import ReservationRequest, StayRequest
    from apps.guests.types import GuestInput

    for room_type, units in ((hotel.dbl, 2), (hotel.ste, 1)):
        for index in range(units):
            create_reservation(
                ReservationRequest(
                    property=hotel.prop,
                    booker=GuestInput(first_name="Ana", last_name=f"Llena {index}", email=f"ana{index}@x.co"),
                    stays=[
                        StayRequest(
                            room_type_id=room_type.pk,
                            rate_plan_id=hotel.flex.pk,
                            checkin=checkin,
                            checkout=checkout,
                            adults=2,
                        )
                    ],
                )
            )


class TestDestinations:
    def test_lists_cities_of_listed_active_properties_with_their_count(self, public_api, hotel):
        build_hotel(new_property(slug="otro-cartagena"), city="Cartagena")
        build_hotel(new_property(slug="poblado"), city="Medellín")
        build_hotel(new_property(slug="oculto"), city="Bogotá", listed=False)
        suspended = OrganizationFactory(status="suspended")
        build_hotel(new_property(suspended, slug="suspendido"), city="Bogotá")
        inactive = new_property(slug="inactivo", status="inactive")
        build_hotel(inactive, city="Bogotá")

        response = public_api.get(f"{PUBLIC}/destinations/")

        assert response.status_code == 200
        assert [(row["city"], row["department"], row["properties_count"]) for row in response.json()] == [
            ("Cartagena", "Bolívar", 2),
            ("Medellín", "Antioquia", 1),
        ]


class TestSearch:
    def test_without_dates_lists_the_listed_hotels_of_the_city_without_prices(self, public_api, hotel):
        build_hotel(new_property(slug="oculto"), listed=False)
        build_hotel(new_property(slug="poblado"), city="Medellín")

        data = _search(public_api, city="cartagena")  # case-insensitive

        assert [row["slug"] for row in data["results"]] == [hotel.prop.slug]
        assert data["results"][0]["offer"] is None
        assert data["nights"] == 0

    def test_city_matches_without_accents(self, public_api):
        medellin = build_hotel(new_property(slug="poblado"), city="Medellín")

        data = _search(public_api, city="Medellin")

        assert [row["slug"] for row in data["results"]] == [medellin.prop.slug]

    def test_only_listed_hotels_with_availability_are_shown(self, public_api, hotel):
        full = build_hotel(new_property(slug="lleno"))
        _fill_dbl_and_ste(full, day(8), day(10))
        build_hotel(new_property(slug="oculto"), listed=False)  # available, but not in the marketplace

        data = _search(public_api, city="Cartagena", checkin=day(8).isoformat(), checkout=day(10).isoformat())

        assert [row["slug"] for row in data["results"]] == [hotel.prop.slug]
        assert data["count"] == 1
        assert data["nights"] == 2

    def test_the_cheapest_public_marketplace_offer_is_shown_with_total_and_price_per_night(
        self, public_api, hotel
    ):
        data = _search(public_api, city="Cartagena", checkin=day(8).isoformat(), checkout=day(10).isoformat())

        offer = data["results"][0]["offer"]
        # NR = FLEX −12 %: 281.600/night; the CORP plan (250.000) is not public and never reaches the
        # marketplace.
        assert offer["rate_plan"]["code"] == "NR"
        assert offer["room_type"]["code"] == "DBL"
        # 2 nights × 281.600 = 563.200 + IVA 19 % (107.008) = 670.208
        assert offer["total"] == "670208.00"
        assert offer["per_night"] == "335104.00"
        assert offer["currency"] == "COP"

    def test_filters_by_type_stars_and_amenities(self, public_api, hotel):
        build_hotel(new_property(slug="hostal"), property_type="hostel", stars=2)
        dates = {"checkin": day(8).isoformat(), "checkout": day(10).isoformat()}

        assert [
            r["slug"] for r in _search(public_api, city="Cartagena", type="hostel", **dates)["results"]
        ] == ["hostal"]
        assert [r["slug"] for r in _search(public_api, city="Cartagena", stars=4, **dates)["results"]] == [
            hotel.prop.slug
        ]
        hotel.prop.settings = {**hotel.prop.settings, "amenities": ["wifi"]}
        hotel.prop.save(update_fields=["settings"])
        cache.clear()
        # "pool" is a property amenity (only the hostel still has it); "air_conditioning" comes from room
        # types
        assert [
            r["slug"] for r in _search(public_api, city="Cartagena", amenities="pool", **dates)["results"]
        ] == ["hostal"]
        both = _search(public_api, city="Cartagena", amenities="air_conditioning", **dates)["results"]
        assert {r["slug"] for r in both} == {hotel.prop.slug, "hostal"}

    def test_price_range_filters_on_the_price_per_night(self, public_api, hotel):
        cheap = build_hotel(new_property(slug="barato"))
        from apps.rates.models import RoomTypeRateDefaults

        RoomTypeRateDefaults.objects.filter(rate_plan=cheap.flex).update(price=Decimal("100000"))
        dates = {"city": "Cartagena", "checkin": day(8).isoformat(), "checkout": day(10).isoformat()}

        # barato: NR 88.000 + IVA → 104.720/night; hotel: 335.104/night
        assert [r["slug"] for r in _search(public_api, max_price=200000, **dates)["results"]] == ["barato"]
        assert [r["slug"] for r in _search(public_api, min_price=200000, **dates)["results"]] == [
            hotel.prop.slug
        ]

    def test_sorts_by_price(self, public_api, hotel):
        cheap = build_hotel(new_property(slug="barato"), stars=3)
        from apps.rates.models import RoomTypeRateDefaults

        RoomTypeRateDefaults.objects.filter(rate_plan=cheap.flex).update(price=Decimal("100000"))
        dates = {"city": "Cartagena", "checkin": day(8).isoformat(), "checkout": day(10).isoformat()}

        assert [r["slug"] for r in _search(public_api, sort="price", **dates)["results"]] == [
            "barato",
            hotel.prop.slug,
        ]
        assert [r["slug"] for r in _search(public_api, sort="-price", **dates)["results"]] == [
            hotel.prop.slug,
            "barato",
        ]
        # recommended (default): more stars first
        assert [r["slug"] for r in _search(public_api, **dates)["results"]] == [hotel.prop.slug, "barato"]

    def test_facets_count_the_hotels_of_the_city_whatever_the_filters(self, public_api, hotel):
        hostel = build_hotel(new_property(slug="hostal"), property_type="hostel", stars=2)
        hostel.prop.settings = {**hostel.prop.settings, "amenities": ["wifi"]}
        hostel.prop.save(update_fields=["settings"])
        build_hotel(new_property(slug="poblado"), city="Medellín")  # another city: not counted

        data = _search(public_api, city="Cartagena", type="hostel")

        assert [row["slug"] for row in data["results"]] == ["hostal"]
        facets = data["facets"]
        assert facets["types"] == [{"value": "boutique", "count": 1}, {"value": "hostel", "count": 1}]
        assert facets["stars"] == [{"value": 4, "count": 1}, {"value": 2, "count": 1}]
        # wifi and A/C come with both hotels' room types; only the boutique hotel lists a pool.
        # Most common first, ties by code.
        assert [(row["code"], row["count"]) for row in facets["amenities"]] == [
            ("air_conditioning", 2),
            ("wifi", 2),
            ("pool", 1),
        ]
        assert facets["amenities"][1]["name"] == {"es": "Wifi", "en": "Wi-Fi"}
        assert facets["amenities"][1]["icon"] == "wifi"

    def test_a_party_that_fits_no_room_finds_nothing(self, public_api, hotel):
        data = _search(
            public_api, city="Cartagena", checkin=day(8).isoformat(), checkout=day(10).isoformat(), adults=6
        )

        assert data["results"] == []

    def test_results_are_cached_for_the_same_search(self, public_api, hotel):
        dates = {"city": "Cartagena", "checkin": day(8).isoformat(), "checkout": day(10).isoformat()}
        assert _search(public_api, **dates)["count"] == 1

        hotel.prop.marketplace_listed = False
        hotel.prop.save(update_fields=["marketplace_listed"])

        assert _search(public_api, **dates)["count"] == 1  # same combination within 60 s → cached
        cache.clear()
        assert _search(public_api, **dates)["count"] == 0

    def test_result_card_shape(self, public_api, hotel):
        from apps.marketplace.tests.helpers import add_photo

        add_photo(hotel.prop, sort_order=1)
        data = _search(public_api, city="Cartagena", checkin=day(8).isoformat(), checkout=day(10).isoformat())

        row = data["results"][0]
        assert row["name"] == hotel.prop.name
        assert row["property_type"] == "boutique"
        assert row["star_rating"] == 4
        assert row["city"] == "Cartagena"
        assert row["photo"].startswith("/media/")
        assert [a["code"] for a in row["amenities"]] == ["pool", "wifi", "air_conditioning"]
        assert row["amenities"][0] == {
            "code": "pool",
            "name": {"es": "Piscina", "en": "Pool"},
            "icon": "waves-ladder",
            "category": "property",
        }

    @pytest.mark.parametrize(
        "params",
        [
            {"checkin": "2026-10-10", "checkout": "2026-10-09"},
            {"checkin": "2026-10-10"},
            {"checkin": "2026-09-30", "checkout": "2026-10-02"},  # in the past
            {"adults": 0},
        ],
    )
    def test_invalid_searches_answer_400(self, public_api, params):
        response = public_api.get(f"{PUBLIC}/search/", {"adults": 2, **params})

        assert response.status_code == 400
        assert response.json()["code"] in {"validation_error", "invalid_dates"}
