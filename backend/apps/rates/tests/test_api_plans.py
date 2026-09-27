"""Rate plans API: base and derived plans with their validation rules (derived only from a base plan of the
same property, no chains, categories ⊆ the parent's) and `rates_changed` when prices may have changed."""

from datetime import date

import pytest

from apps.core.signals import rates_changed
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import RatePlan
from apps.rates.tests.factories import CancellationPolicyFactory, DerivedRatePlanFactory, RatePlanFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/rates/rate-plans/"


def plan_body(**overrides):
    body = {"code": "FLEX", "name": {"es": "Tarifa flexible", "en": "Flexible rate"}, "kind": "base"}
    body.update(overrides)
    return body


def test_create_a_base_plan(api, prop):
    room_type = RoomTypeFactory(property=prop)
    policy = CancellationPolicyFactory(property=prop)
    response = api.post(
        URL,
        plan_body(
            room_types=[str(room_type.pk)],
            cancellation_policy=str(policy.pk),
            meal_plan="room_only",
            deposit_percent="30",
            channels=["direct", "booking_engine"],
            min_los_default=1,
        ),
        format="json",
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert {key: body[key] for key in ("code", "kind", "parent", "room_types", "cancellation_policy")} == {
        "code": "FLEX",
        "kind": "base",
        "parent": None,
        "room_types": [str(room_type.pk)],
        "cancellation_policy": str(policy.pk),
    }
    assert (body["deposit_percent"], body["channels"], body["children"]) == (
        "30.00",
        ["direct", "booking_engine"],
        [],
    )


def test_create_a_derived_plan(api, rates):
    response = api.post(
        URL,
        plan_body(
            code="NR",
            kind="derived",
            parent=str(rates.plan.pk),
            derivation_type="percent",
            derivation_value="-12",
            room_types=[str(rates.room_type.pk)],
        ),
        format="json",
    )
    assert response.status_code == 201, response.json()
    assert (response.json()["parent"], response.json()["derivation_value"]) == (str(rates.plan.pk), "-12.00")
    assert api.get(f"{URL}{rates.plan.pk}/").json()["children"] == [response.json()["id"]]


def test_a_derived_plan_needs_a_parent(api):
    response = api.post(URL, plan_body(kind="derived"), format="json")
    assert (response.status_code, list(response.json()["fields"])) == (400, ["parent"])


def test_a_base_plan_has_no_parent(api, rates):
    response = api.post(URL, plan_body(code="OTHER", parent=str(rates.plan.pk)), format="json")
    assert (response.status_code, list(response.json()["fields"])) == (400, ["parent"])


def test_derived_plans_only_derive_from_base_plans(api, rates):
    derived = DerivedRatePlanFactory(property=rates.prop, parent=rates.plan)
    response = api.post(URL, plan_body(code="CHAIN", kind="derived", parent=str(derived.pk)), format="json")
    assert (response.status_code, response.json()["code"], list(response.json()["fields"])) == (
        400,
        "parent_not_base",
        ["parent"],
    )


def test_the_parent_must_belong_to_this_property(api):
    response = api.post(URL, plan_body(kind="derived", parent=str(RatePlanFactory().pk)), format="json")
    assert (response.status_code, list(response.json()["fields"])) == (400, ["parent"])


def test_a_plan_cannot_be_its_own_parent(api, rates):
    response = api.patch(
        f"{URL}{rates.plan.pk}/", {"kind": "derived", "parent": str(rates.plan.pk)}, format="json"
    )
    assert (response.status_code, list(response.json()["fields"])) == (400, ["parent"])


def test_derived_categories_must_be_sold_by_the_parent(api, rates):
    outsider = RoomTypeFactory(property=rates.prop, code="STE")
    response = api.post(
        URL,
        plan_body(code="NR", kind="derived", parent=str(rates.plan.pk), room_types=[str(outsider.pk)]),
        format="json",
    )
    assert (response.status_code, list(response.json()["fields"])) == (400, ["room_types"])


def test_a_base_plan_with_derived_plans_cannot_become_derived(api, rates):
    DerivedRatePlanFactory(property=rates.prop, parent=rates.plan)
    other_base = RatePlanFactory(property=rates.prop)
    response = api.patch(
        f"{URL}{rates.plan.pk}/", {"kind": "derived", "parent": str(other_base.pk)}, format="json"
    )
    assert (response.status_code, response.json()["code"]) == (400, "plan_has_children")


def test_a_base_plan_keeps_the_categories_its_derived_plans_sell(api, rates):
    DerivedRatePlanFactory(property=rates.prop, parent=rates.plan, room_types=[rates.room_type])
    response = api.patch(f"{URL}{rates.plan.pk}/", {"room_types": []}, format="json")
    assert (response.status_code, list(response.json()["fields"])) == (400, ["room_types"])


def test_codes_are_unique_per_property(api, rates):
    response = api.post(URL, plan_body(code="FLEX"), format="json")
    assert (response.status_code, list(response.json()["fields"])) == (400, ["code"])


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"deposit_percent": "101"}, "deposit_percent"),
        ({"min_los_default": 0}, "min_los_default"),
        ({"channels": ["direct", ""]}, "channels"),
        ({"channels": "direct"}, "channels"),
        ({"name": {"en": "No Spanish"}}, "name"),
    ],
)
def test_invalid_values(api, change, field):
    response = api.post(URL, plan_body(**change), format="json")
    assert (response.status_code, list(response.json()["fields"])) == (400, [field])


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"derivation_type": ""}, "derivation_type"),
        ({"derivation_value": "-100.01"}, "derivation_value"),
    ],
)
def test_invalid_derivations(api, rates, change, field):
    body = plan_body(
        code="NR",
        kind="derived",
        parent=str(rates.plan.pk),
        derivation_type="percent",
        derivation_value="-12",
    )
    body.update(change)
    response = api.post(URL, body, format="json")
    assert (response.status_code, list(response.json()["fields"])) == (400, [field])


def test_amount_derivations_may_lower_the_price_below_100_percent(api, rates):
    body = plan_body(
        code="PROMO",
        kind="derived",
        parent=str(rates.plan.pk),
        derivation_type="amount",
        derivation_value="-150000",
    )
    assert api.post(URL, body, format="json").status_code == 201


def test_a_percent_derivation_is_checked_against_the_stored_type_on_update(api, rates):
    derived = DerivedRatePlanFactory(property=rates.prop, parent=rates.plan, derivation_type="percent")
    response = api.patch(f"{URL}{derived.pk}/", {"derivation_value": "-120"}, format="json")
    assert (response.status_code, list(response.json()["fields"])) == (400, ["derivation_value"])


def test_a_base_plan_with_derived_plans_cannot_be_deleted(api, rates):
    DerivedRatePlanFactory(property=rates.prop, parent=rates.plan)
    response = api.delete(f"{URL}{rates.plan.pk}/")
    assert (response.status_code, response.json()["code"]) == (409, "in_use")
    assert RatePlan.objects.filter(pk=rates.plan.pk).exists()


def test_filter_by_kind(api, rates):
    DerivedRatePlanFactory(property=rates.prop, parent=rates.plan, code="NR")
    assert [p["code"] for p in api.get(URL, {"kind": "derived"}).json()["results"]] == ["NR"]


def test_changing_a_derivation_announces_new_prices(api, rates, django_capture_on_commit_callbacks):
    rates.prop.business_date = date(2026, 9, 25)
    rates.prop.save()
    derived = DerivedRatePlanFactory(property=rates.prop, parent=rates.plan, room_types=[rates.room_type])
    received = []

    def receiver(sender, **kwargs):
        received.append(kwargs)

    rates_changed.connect(receiver)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            response = api.patch(f"{URL}{derived.pk}/", {"derivation_value": "-15"}, format="json")
    finally:
        rates_changed.disconnect(receiver)
    assert response.status_code == 200, response.json()
    assert [(r["room_type_ids"], r["rate_plan_ids"], r["start"], r["end"]) for r in received] == [
        ([rates.room_type.pk], [derived.pk], date(2026, 9, 25), date(2027, 9, 25))
    ]
