"""Configuration API of `rates`: taxes, cancellation policies, extras, promo codes, seasons (+ season rates)
and category defaults. Scoped to `X-Property-Id`; `rates.view` reads, `rates.manage` writes."""

from datetime import date
from decimal import Decimal

import pytest

from apps.core.signals import rates_changed
from apps.core.tests.factories import PropertyFactory
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import (
    CancellationPolicy,
    Extra,
    PromoCode,
    RoomTypeRateDefaults,
    Season,
    SeasonRate,
    Tax,
)
from apps.rates.tests.conftest import oct_
from apps.rates.tests.factories import (
    CancellationPolicyFactory,
    DerivedRatePlanFactory,
    ExtraFactory,
    RatePlanFactory,
    TaxFactory,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/rates/"


@pytest.fixture
def capture_rates_changed():
    received = []

    def receiver(sender, **kwargs):
        kwargs.pop("signal")
        received.append(kwargs)

    rates_changed.connect(receiver)
    yield received
    rates_changed.disconnect(receiver)


class TestTaxes:
    def test_create_list_update_and_delete(self, api, prop):
        response = api.post(
            f"{URL}taxes/",
            {
                "code": "ICA",
                "name": "Impuesto municipal",
                "rate": "1.50",
                "applies_to": "all",
                "included_in_price": True,
                "exempt_foreign_non_residents": False,
            },
            format="json",
        )
        assert response.status_code == 201, response.json()
        tax_id = response.json()["id"]
        assert response.json() == {
            "id": tax_id,
            "code": "ICA",
            "name": "Impuesto municipal",
            "rate": "1.50",
            "applies_to": "all",
            "included_in_price": True,
            "exempt_foreign_non_residents": False,
            "is_active": True,
        }
        TaxFactory(code="OTHER")  # another property
        listing = api.get(f"{URL}taxes/").json()
        assert [t["code"] for t in listing["results"]] == ["ICA"]
        assert (
            api.patch(f"{URL}taxes/{tax_id}/", {"is_active": False}, format="json").json()["is_active"]
            is False
        )
        assert api.delete(f"{URL}taxes/{tax_id}/").status_code == 204

    def test_codes_are_unique_per_property(self, api, prop):
        TaxFactory(property=prop, code="IVA")
        response = api.post(f"{URL}taxes/", {"code": "IVA", "name": "IVA", "rate": "19"}, format="json")
        assert (response.status_code, list(response.json()["fields"])) == (400, ["code"])

    @pytest.mark.parametrize("rate", ["-1", "100.01"])
    def test_rate_is_a_percentage(self, api, rate):
        response = api.post(f"{URL}taxes/", {"code": "X", "name": "X", "rate": rate}, format="json")
        assert (response.status_code, list(response.json()["fields"])) == (400, ["rate"])

    def test_a_tax_used_by_an_extra_cannot_be_deleted(self, api, prop):
        tax = TaxFactory(property=prop, applies_to="extras")
        ExtraFactory(property=prop, tax=tax)
        response = api.delete(f"{URL}taxes/{tax.pk}/")
        assert (response.status_code, response.json()["code"]) == (409, "in_use")
        assert Tax.objects.filter(pk=tax.pk).exists()


class TestCancellationPolicies:
    def test_create_with_translations(self, api):
        response = api.post(
            f"{URL}cancellation-policies/",
            {
                "name": {"es": "Flexible 24h", "en": "Flexible 24h"},
                "free_until_hours_before": 24,
                "penalty_type": "percent",
                "penalty_value": "50",
                "description": {"es": "Gratis hasta 24 h antes.", "en": "Free until 24 h before."},
            },
            format="json",
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["name"], body["penalty_type"], body["penalty_value"], body["plans_count"]) == (
            {"es": "Flexible 24h", "en": "Flexible 24h"},
            "percent",
            "50.00",
            0,
        )

    def test_the_spanish_name_is_required(self, api):
        response = api.post(f"{URL}cancellation-policies/", {"name": {"en": "Only English"}}, format="json")
        assert (response.status_code, list(response.json()["fields"])) == (400, ["name"])

    def test_a_percent_penalty_cannot_exceed_100(self, api):
        response = api.post(
            f"{URL}cancellation-policies/",
            {"name": {"es": "Mala"}, "penalty_type": "percent", "penalty_value": "120"},
            format="json",
        )
        assert (response.status_code, list(response.json()["fields"])) == (400, ["penalty_value"])

    def test_a_policy_used_by_a_plan_cannot_be_deleted(self, api, prop):
        policy = CancellationPolicyFactory(property=prop)
        RatePlanFactory(property=prop, cancellation_policy=policy)
        response = api.delete(f"{URL}cancellation-policies/{policy.pk}/")
        assert (response.status_code, response.json()["code"]) == (409, "in_use")
        assert CancellationPolicy.objects.filter(pk=policy.pk).exists()


class TestExtras:
    def test_create_with_an_extras_tax(self, api, prop):
        tax = TaxFactory(property=prop, code="IVA-EXTRAS", applies_to="extras")
        response = api.post(
            f"{URL}extras/",
            {
                "code": "PARKING",
                "name": {"es": "Parqueadero", "en": "Parking"},
                "price": "25000",
                "charge_type": "per_night",
                "tax": str(tax.pk),
            },
            format="json",
        )
        assert response.status_code == 201, response.json()
        assert (response.json()["price"], response.json()["tax"], response.json()["sellable_online"]) == (
            "25000.00",
            str(tax.pk),
            True,
        )

    @pytest.mark.parametrize("which", ["lodging_tax", "other_property"])
    def test_the_tax_must_be_an_extras_tax_of_this_property(self, api, prop, which):
        tax = (
            TaxFactory(property=prop, applies_to="room")
            if which == "lodging_tax"
            else TaxFactory(applies_to="extras")
        )
        response = api.post(
            f"{URL}extras/",
            {"code": "X", "name": {"es": "X"}, "price": "1", "charge_type": "per_stay", "tax": str(tax.pk)},
            format="json",
        )
        assert (response.status_code, list(response.json()["fields"])) == (400, ["tax"])

    def test_negative_prices_are_rejected(self, api):
        response = api.post(f"{URL}extras/", {"code": "X", "name": {"es": "X"}, "price": "-1"}, format="json")
        assert (response.status_code, list(response.json()["fields"])) == (400, ["price"])

    def test_an_extra_charged_in_a_folio_cannot_be_deleted(self, api, prop):
        from apps.finance.tests.factories import ChargeFactory

        extra = ExtraFactory(property=prop)
        ChargeFactory(folio__reservation__property=prop, extra=extra)
        response = api.delete(f"{URL}extras/{extra.pk}/")
        assert (response.status_code, response.json()["code"]) == (409, "in_use")
        assert Extra.objects.filter(pk=extra.pk).exists()


class TestPromoCodes:
    def test_codes_are_stored_uppercase_and_uses_are_read_only(self, api, prop):
        plan = RatePlanFactory(property=prop)
        response = api.post(
            f"{URL}promo-codes/",
            {
                "code": " bienvenida10 ",
                "discount_type": "percent",
                "value": "10",
                "valid_from": "2026-09-01",
                "valid_to": "2026-12-31",
                "rate_plans": [str(plan.pk)],
                "max_uses": 100,
                "uses": 99,
            },
            format="json",
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["code"], body["uses"], body["rate_plans"], body["max_uses"]) == (
            "BIENVENIDA10",
            0,
            [str(plan.pk)],
            100,
        )

    def test_codes_are_unique_without_case(self, api, prop):
        PromoCode.objects.create(property=prop, code="VERANO", discount_type="percent", value=Decimal("5"))
        response = api.post(
            f"{URL}promo-codes/", {"code": "verano", "discount_type": "percent", "value": "5"}, format="json"
        )
        assert (response.status_code, list(response.json()["fields"])) == (400, ["code"])

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"discount_type": "percent", "value": "120"}, "value"),
            ({"discount_type": "amount", "value": "0"}, "value"),
            ({"valid_from": "2026-10-10", "valid_to": "2026-10-01"}, "valid_to"),
            ({"stay_from": "2026-10-10", "stay_to": "2026-10-01"}, "stay_to"),
            ({"code": "no válido!"}, "code"),
        ],
    )
    def test_invalid_values(self, api, payload, field):
        body = {"code": "PROMO", "discount_type": "percent", "value": "10", **payload}
        response = api.post(f"{URL}promo-codes/", body, format="json")
        assert (response.status_code, list(response.json()["fields"])) == (400, [field])

    def test_plans_of_another_property_are_rejected(self, api):
        response = api.post(
            f"{URL}promo-codes/",
            {
                "code": "X10",
                "discount_type": "percent",
                "value": "10",
                "rate_plans": [str(RatePlanFactory().pk)],
            },
            format="json",
        )
        assert (response.status_code, list(response.json()["fields"])) == (400, ["rate_plans"])


class TestSeasons:
    def test_seasons_list_their_rates(self, api, rates):
        response = api.post(
            f"{URL}seasons/",
            {"name": "Alta fin de año", "start_date": "2026-12-15", "end_date": "2027-01-15", "priority": 10},
            format="json",
        )
        assert response.status_code == 201, response.json()
        season_id = response.json()["id"]
        api.post(
            f"{URL}season-rates/",
            {
                "season": season_id,
                "room_type": str(rates.room_type.pk),
                "rate_plan": str(rates.plan.pk),
                "price": "416000",
                "dow_adjustments": {"fri": 15, "sat": 15},
            },
            format="json",
        )
        detail = api.get(f"{URL}seasons/{season_id}/").json()
        assert detail["end_date"] == "2027-01-15"
        assert [(r["room_type"], r["price"], r["dow_adjustments"]) for r in detail["rates"]] == [
            (str(rates.room_type.pk), "416000.00", {"fri": 15, "sat": 15})
        ]

    def test_the_end_date_cannot_be_before_the_start(self, api):
        response = api.post(
            f"{URL}seasons/",
            {"name": "Mala", "start_date": "2026-12-15", "end_date": "2026-12-14"},
            format="json",
        )
        assert (response.status_code, list(response.json()["fields"])) == (400, ["end_date"])

    def test_posting_a_season_rate_again_updates_it_and_announces_the_season_range(
        self, api, rates, capture_rates_changed, django_capture_on_commit_callbacks
    ):
        season = Season.objects.create(
            property=rates.prop, name="Puente", start_date=oct_(10), end_date=oct_(12)
        )
        body = {
            "season": str(season.pk),
            "room_type": str(rates.room_type.pk),
            "rate_plan": str(rates.plan.pk),
        }
        assert api.post(f"{URL}season-rates/", {**body, "price": "400000"}, format="json").status_code == 201
        with django_capture_on_commit_callbacks(execute=True):
            response = api.post(f"{URL}season-rates/", {**body, "price": "410000"}, format="json")
        assert (response.status_code, response.json()["price"]) == (200, "410000.00")
        assert SeasonRate.objects.get().price == Decimal("410000.00")
        assert capture_rates_changed == [
            {
                "property": rates.prop,
                "room_type_ids": [rates.room_type.pk],
                "rate_plan_ids": [rates.plan.pk],
                "start": oct_(10),
                "end": oct_(13),
            }
        ]

    def test_season_rates_belong_to_base_plans(self, api, rates):
        season = Season.objects.create(
            property=rates.prop, name="Puente", start_date=oct_(10), end_date=oct_(12)
        )
        derived = DerivedRatePlanFactory(property=rates.prop, parent=rates.plan)
        response = api.post(
            f"{URL}season-rates/",
            {
                "season": str(season.pk),
                "room_type": str(rates.room_type.pk),
                "rate_plan": str(derived.pk),
                "price": "1",
            },
            format="json",
        )
        assert (response.status_code, list(response.json()["fields"])) == (400, ["rate_plan"])


class TestRoomTypeDefaults:
    def test_posting_the_same_category_and_plan_updates_the_defaults(
        self, api, rates, capture_rates_changed, django_capture_on_commit_callbacks
    ):
        prop = rates.prop
        prop.business_date = date(2026, 9, 25)
        prop.save()
        body = {
            "room_type": str(rates.room_type.pk),
            "rate_plan": str(rates.plan.pk),
            "price": "300000",
            "dow_adjustments": {"fri": 10, "sat": 10},
            "extra_adult_price": "50000",
            "extra_child_price": "25000",
            "child_age_limit": 10,
            "single_occupancy_price": "250000",
        }
        with django_capture_on_commit_callbacks(execute=True):
            response = api.post(f"{URL}room-type-defaults/", body, format="json")
        assert response.status_code == 200, response.json()
        defaults = RoomTypeRateDefaults.objects.get()
        assert (defaults.price, defaults.dow_adjustments, defaults.child_age_limit) == (
            Decimal("300000.00"),
            {"fri": 10, "sat": 10},
            10,
        )
        assert capture_rates_changed[0]["room_type_ids"] == [rates.room_type.pk]
        assert (capture_rates_changed[0]["start"], capture_rates_changed[0]["end"]) == (
            date(2026, 9, 25),
            date(2026, 9, 25).replace(year=2027),
        )

    def test_new_defaults_are_created(self, api, rates):
        suite = RoomTypeFactory(property=rates.prop, code="STE")
        response = api.post(
            f"{URL}room-type-defaults/",
            {"room_type": str(suite.pk), "rate_plan": str(rates.plan.pk), "price": "650000"},
            format="json",
        )
        assert response.status_code == 201, response.json()
        listing = api.get(f"{URL}room-type-defaults/", {"rate_plan": str(rates.plan.pk)}).json()
        assert sorted(item["price"] for item in listing["results"]) == ["320000.00", "650000.00"]

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"dow_adjustments": {"friday": 10}}, "dow_adjustments"),
            ({"dow_adjustments": {"fri": "mucho"}}, "dow_adjustments"),
            ({"dow_adjustments": {"fri": -150}}, "dow_adjustments"),
            ({"price": "-1"}, "price"),
            ({"child_age_limit": 18}, "child_age_limit"),
        ],
    )
    def test_invalid_values(self, api, rates, change, field):
        body = {"room_type": str(rates.room_type.pk), "rate_plan": str(rates.plan.pk), "price": "1", **change}
        response = api.post(f"{URL}room-type-defaults/", body, format="json")
        assert (response.status_code, list(response.json()["fields"])) == (400, [field])

    def test_defaults_belong_to_base_plans_of_this_property(self, api, rates):
        derived = DerivedRatePlanFactory(property=rates.prop, parent=rates.plan)
        for plan, room_type in (
            (derived, rates.room_type),
            (rates.plan, RoomTypeFactory(property=PropertyFactory())),
        ):
            response = api.post(
                f"{URL}room-type-defaults/",
                {"room_type": str(room_type.pk), "rate_plan": str(plan.pk), "price": "1"},
                format="json",
            )
            assert response.status_code == 400, response.json()
