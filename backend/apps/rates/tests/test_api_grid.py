"""Grid, bulk edit, staff quote tool, holidays and the category lookup of the rates API.

Ranges are half-open: `?start=2026-10-11&end=2026-10-13` shows the nights of the 11th and the 12th.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.bookings.tests.factories import StayFactory
from apps.core.models import AuditEvent
from apps.core.tests.factories import PropertyFactory
from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory
from apps.rates.models import DailyRate
from apps.rates.tests.conftest import oct_
from apps.rates.tests.factories import DailyRateFactory, DerivedRatePlanFactory, RatePlanFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/rates/"


@pytest.fixture
def hotel(rates):
    """Two DBL rooms; one confirmed stay the night of 11 Oct; a manual price with restrictions on the 12th."""
    RoomFactory(room_type=rates.room_type, number="101")
    RoomFactory(room_type=rates.room_type, number="102")
    StayFactory(
        reservation__property=rates.prop,
        reservation__checkin_date=oct_(11),
        reservation__checkout_date=oct_(12),
        room_type=rates.room_type,
        rate_plan=rates.plan,
    )
    DailyRateFactory(
        room_type=rates.room_type,
        rate_plan=rates.plan,
        date=oct_(12),
        price=Decimal("350000"),
        min_los=2,
        closed_to_arrival=True,
    )
    RoomTypeFactory(property=rates.prop, code="OUT")  # not sold by the plan
    return rates


def grid(api, **params):
    return api.get(f"{URL}grid/", {"start": "2026-10-11", "end": "2026-10-13", **params})


def row(date_, price, source, available, **restrictions):
    return {
        "date": date_,
        "price": price,
        "extra_adult_price": "60000.00",
        "extra_child_price": "30000.00",
        "min_los": None,
        "max_los": None,
        "cta": False,
        "ctd": False,
        "stop_sell": False,
        "source": source,
        "available": available,
        **restrictions,
    }


class TestGrid:
    def test_shape_prices_restrictions_availability_and_holidays(self, api, hotel):
        response = grid(api, rate_plan=str(hotel.plan.pk))
        assert response.status_code == 200, response.json()
        assert response.json() == {
            "rate_plan": {
                "id": str(hotel.plan.pk),
                "code": "FLEX",
                "name": hotel.plan.name,
                "kind": "base",
                "parent": None,
                "derivation_type": "percent",
                "derivation_value": "0.00",
                "editable": True,
            },
            "currency": "COP",
            "start": "2026-10-11",
            "end": "2026-10-13",
            "dates": ["2026-10-11", "2026-10-12"],
            "holidays": [{"date": "2026-10-12", "name": "Día de la Raza"}],
            "room_types": [
                {
                    "id": str(hotel.room_type.pk),
                    "code": "DBL",
                    "name": hotel.room_type.name,
                    "color": hotel.room_type.color,
                    "kind": "private",
                    "rows": [
                        row("2026-10-11", "320000.00", "default", 1),
                        row("2026-10-12", "350000.00", "manual", 2, min_los=2, cta=True),
                    ],
                }
            ],
        }

    def test_the_first_active_base_plan_is_the_default(self, api, hotel):
        RatePlanFactory(property=hotel.prop, code="AAA", sort_order=99)
        RatePlanFactory(property=hotel.prop, code="OLD", sort_order=0, is_active=False)
        assert grid(api).json()["rate_plan"]["code"] == "FLEX"

    def test_derived_plans_show_derived_prices_read_only(self, api, hotel):
        derived = DerivedRatePlanFactory(
            property=hotel.prop,
            parent=hotel.plan,
            derivation_value=Decimal("-12"),
            room_types=[hotel.room_type],
        )
        body = grid(api, rate_plan=str(derived.pk)).json()
        assert (body["rate_plan"]["editable"], body["rate_plan"]["parent"]) == (False, str(hotel.plan.pk))
        rows = body["room_types"][0]["rows"]
        assert [(r["price"], r["cta"]) for r in rows] == [("281600.00", False), ("308000.00", True)]

    def test_a_new_default_price_reaches_nights_that_only_hold_restrictions(self, api, hotel):
        """E2E #4: weekend min stay in bulk, then the category price changes: the grid shows the new price."""
        response = api.post(
            f"{URL}grid/bulk/",
            {
                "room_type_ids": [str(hotel.room_type.pk)],
                "rate_plan_id": str(hotel.plan.pk),
                "start": "2026-10-11",
                "end": "2026-10-12",
                "set": {"min_los": 2},
            },
            format="json",
        )
        assert response.status_code == 200, response.json()
        response = api.post(
            f"{URL}room-type-defaults/",
            {"room_type": str(hotel.room_type.pk), "rate_plan": str(hotel.plan.pk), "price": "340000"},
            format="json",
        )
        assert response.status_code == 200, response.json()
        rows = grid(api, rate_plan=str(hotel.plan.pk)).json()["room_types"][0]["rows"]
        assert [(r["price"], r["source"], r["min_los"]) for r in rows] == [
            ("340000.00", "default", 2),
            ("350000.00", "manual", 2),
        ]

    def test_days_without_price_have_a_null_price(self, api, hotel):
        hotel.defaults.delete()
        rows = grid(api, rate_plan=str(hotel.plan.pk)).json()["room_types"][0]["rows"]
        assert [(r["price"], r["source"]) for r in rows] == [(None, "none"), ("350000.00", "manual")]

    def test_without_plans_the_grid_is_empty(self, api, prop):
        body = grid(api).json()
        assert (body["rate_plan"], body["room_types"], body["dates"]) == (
            None,
            [],
            ["2026-10-11", "2026-10-12"],
        )

    @pytest.mark.parametrize(
        ("params", "field"),
        [
            ({"start": ""}, "start"),
            ({"end": "2026-10-11"}, "end"),
            ({"end": "2027-10-11"}, "end"),
            ({"rate_plan": "not-a-uuid"}, "rate_plan"),
        ],
    )
    def test_invalid_parameters(self, api, hotel, params, field):
        response = grid(api, **params)
        assert (response.status_code, list(response.json()["fields"])) == (400, [field])

    def test_plans_of_another_property_are_not_found(self, api, hotel):
        response = grid(api, rate_plan=str(RatePlanFactory().pk))
        assert (response.status_code, list(response.json()["fields"])) == (400, ["rate_plan"])

    def test_the_queries_do_not_grow_with_the_nights(self, api, hotel):
        """90 nights must not cost 90 availability look-ups (a range never seen took ~4 s in dev)."""

        def queries_for(start, nights):
            end = start + timedelta(days=nights)
            with CaptureQueriesContext(connection) as queries:
                response = grid(api, start=start.isoformat(), end=end.isoformat())
            assert response.status_code == 200
            return len(queries)

        # two ranges whose inventory was never materialized
        assert queries_for(date(2027, 3, 1), 90) == queries_for(date(2027, 7, 1), 7)

    def test_availability_counts_blocks_and_overbooking_night_by_night(self, api, hotel):
        second = StayFactory(
            reservation__property=hotel.prop,
            reservation__checkin_date=oct_(11),
            reservation__checkout_date=oct_(13),
            room_type=hotel.room_type,
            rate_plan=hotel.plan,
        )
        StayFactory(
            reservation__property=hotel.prop,
            reservation__checkin_date=oct_(11),
            reservation__checkout_date=oct_(12),
            room_type=hotel.room_type,
            rate_plan=hotel.plan,
        )
        assert second.room is None
        rows = grid(api, rate_plan=str(hotel.plan.pk)).json()["room_types"][0]["rows"]
        # 2 rooms: the 11th has 3 stays (overbooked by 1), the 12th has 1
        assert [r["available"] for r in rows] == [-1, 1]


class TestBulk:
    def bulk(self, api, rates, **overrides):
        body = {
            "room_type_ids": [str(rates.room_type.pk)],
            "rate_plan_id": str(rates.plan.pk),
            "start": "2026-10-01",
            "end": "2026-10-08",
            "weekdays": [4, 5],
            "set": {"price": "380000", "min_los": 2, "cta": True},
        }
        body.update(overrides)
        return api.post(f"{URL}grid/bulk/", body, format="json")

    def test_updates_the_selected_weekdays_and_returns_the_audit_event(self, api, rates):
        response = self.bulk(api, rates)
        assert response.status_code == 200, response.json()
        event = AuditEvent.objects.get(action="rates.bulk_update")
        assert response.json() == {"updated": 2, "audit_event_id": str(event.pk)}
        assert event.reversible is True
        rows = DailyRate.objects.order_by("date")
        assert [(r.date, r.price, r.min_los, r.closed_to_arrival, r.source) for r in rows] == [
            (oct_(2), Decimal("380000.00"), 2, True, "bulk"),  # Friday
            (oct_(3), Decimal("380000.00"), 2, True, "bulk"),  # Saturday
        ]

    def test_restriction_names_map_to_the_grid_fields(self, api, rates):
        response = self.bulk(
            api,
            rates,
            end="2026-10-02",
            weekdays=[],
            source="manual",
            set={"ctd": True, "stop_sell": True, "max_los": 5, "price_delta_percent": "10"},
        )
        assert response.status_code == 200, response.json()
        first = DailyRate.objects.get(date=oct_(1))
        assert (first.closed_to_departure, first.stop_sell, first.max_los, first.price, first.source) == (
            True,
            True,
            5,
            Decimal("352000.00"),
            "manual",
        )

    @pytest.mark.parametrize(
        ("overrides", "field"),
        [
            ({"set": {}}, "set"),
            ({"set": {"price": "1", "price_delta_percent": "5"}}, "set"),
            ({"set": {"min_los": 0}}, "set"),
            ({"set": {"cta": "tal vez"}}, "set"),
            ({"weekdays": [7]}, "weekdays"),
            ({"end": "2026-10-01"}, "end"),
            ({"room_type_ids": []}, "room_type_ids"),
            ({"source": "revenue"}, "source"),
        ],
    )
    def test_invalid_payloads(self, api, rates, overrides, field):
        response = self.bulk(api, rates, **overrides)
        assert (response.status_code, list(response.json()["fields"])) == (400, [field])
        assert not DailyRate.objects.exists()

    def test_categories_outside_the_plan_are_rejected(self, api, rates):
        outsider = RoomTypeFactory(property=rates.prop)
        response = self.bulk(api, rates, room_type_ids=[str(outsider.pk)])
        assert (response.status_code, list(response.json()["fields"])) == (400, ["room_type_ids"])

    def test_derived_plans_are_read_only(self, api, rates):
        derived = DerivedRatePlanFactory(property=rates.prop, parent=rates.plan, room_types=[rates.room_type])
        response = self.bulk(api, rates, rate_plan_id=str(derived.pk))
        assert (response.status_code, response.json()["code"]) == (400, "derived_plan_not_editable")

    def test_nothing_matching_returns_zero_without_an_audit_event(self, api, rates):
        response = self.bulk(api, rates, end="2026-10-02", weekdays=[6])
        assert response.json() == {"updated": 0, "audit_event_id": None}

    def test_restrictions_on_nights_without_price_say_which_category_and_night(self, api, rates):
        rates.defaults.delete()
        response = self.bulk(api, rates, end="2026-10-02", weekdays=[], set={"stop_sell": True})
        body = response.json()
        assert (response.status_code, body["code"], body["room_type"], body["date"]) == (
            400,
            "no_rate",
            "DBL",
            "2026-10-01",
        )
        assert not DailyRate.objects.exists()


class TestQuote:
    def test_prices_a_stay_like_the_quote_contract(self, api, rates):
        response = api.post(
            f"{URL}quote/",
            {
                "room_type_id": str(rates.room_type.pk),
                "rate_plan_id": str(rates.plan.pk),
                "checkin": "2026-10-01",
                "checkout": "2026-10-03",
                "adults": 3,
                "children": 1,
                "children_ages": [4],
                "guest_is_foreign_non_resident": True,
            },
            format="json",
        )
        assert response.status_code == 200, response.json()
        body = response.json()
        assert [n["total"] for n in body["nights"]] == ["410000.00", "410000.00"]  # 320 + 60 + 30
        assert (body["subtotal"], body["tax_total"], body["total"], body["restrictions_ok"]) == (
            "820000.00",
            "0.00",
            "820000.00",
            True,
        )
        assert body["taxes"][0]["exempt"] is True

    def test_dates_in_the_wrong_order_are_explained_by_the_quote(self, api, rates):
        body = {
            "room_type_id": str(rates.room_type.pk),
            "rate_plan_id": str(rates.plan.pk),
            "checkin": "2026-10-03",
            "checkout": "2026-10-01",
        }
        response = api.post(f"{URL}quote/", body, format="json")
        assert (response.status_code, response.json()["violations"]) == (200, ["invalid_dates"])

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"adults": 0}, "adults"),
            ({"children_ages": [30]}, "children_ages"),
            ({"room_type_id": "other"}, "room_type_id"),
            ({"checkout": "2027-10-03"}, "checkout"),  # more than a year of nights
        ],
    )
    def test_invalid_requests(self, api, rates, change, field):
        body = {
            "room_type_id": str(rates.room_type.pk),
            "rate_plan_id": str(rates.plan.pk),
            "checkin": "2026-10-01",
            "checkout": "2026-10-03",
            "adults": 2,
        }
        if change.get("room_type_id") == "other":
            change = {"room_type_id": str(RoomTypeFactory(property=PropertyFactory()).pk)}
        response = api.post(f"{URL}quote/", {**body, **change}, format="json")
        assert (response.status_code, list(response.json()["fields"])) == (400, [field])


class TestHolidays:
    def test_colombian_holidays_of_a_year(self, api):
        body = api.get(f"{URL}holidays/", {"year": 2026}).json()
        assert {"date": "2026-10-12", "name": "Día de la Raza"} in body
        assert body[0] == {"date": "2026-01-01", "name": "Año Nuevo"}
        assert len(body) == len({item["date"] for item in body})

    def test_a_half_open_range_and_the_user_language(self, api, owner):
        owner.language = "en"
        owner.save()
        body = api.get(f"{URL}holidays/", {"start": "2026-10-01", "end": "2026-11-02"}).json()
        assert body == [{"date": "2026-10-12", "name": "Columbus Day"}]

    def test_the_screen_can_ask_for_its_language(self, api):
        """The frontend switches language before the profile is saved: it asks for the one it shows."""
        body = api.get(f"{URL}holidays/", {"start": "2026-10-01", "end": "2026-11-02", "lang": "en"}).json()
        assert body == [{"date": "2026-10-12", "name": "Columbus Day"}]
        grid_holidays = api.get(
            f"{URL}grid/", {"start": "2026-10-12", "end": "2026-10-13", "lang": "en"}
        ).json()
        assert grid_holidays["holidays"] == [{"date": "2026-10-12", "name": "Columbus Day"}]

    @pytest.mark.parametrize(
        ("path", "params"), [("holidays/", {}), ("grid/", {"start": "2026-10-12", "end": "2026-10-13"})]
    )
    def test_unknown_languages_are_rejected(self, api, path, params):
        response = api.get(f"{URL}{path}", {**params, "lang": "fr"})
        assert (response.status_code, list(response.json()["fields"])) == (400, ["lang"])

    def test_the_default_is_the_year_of_the_business_date(self, api, prop):
        prop.business_date = date(2027, 3, 1)
        prop.save()
        assert api.get(f"{URL}holidays/").json()[0]["date"].startswith("2027-")


def test_room_types_lookup_lists_the_categories_of_this_property(api, rates):
    RoomTypeFactory(code="ELSEWHERE")
    body = api.get(f"{URL}room-types/").json()
    assert [(item["id"], item["code"], item["kind"], item["base_occupancy"]) for item in body] == [
        (str(rates.room_type.pk), "DBL", "private", 2)
    ]
    expected = (
        "id code name kind color base_occupancy max_adults max_children max_occupancy is_active sort_order"
    )
    assert set(body[0]) == set(expected.split())
