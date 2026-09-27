"""Permissions (front desk reads rates but cannot edit them; housekeeping cannot read them), multi-tenant
isolation of every resource of the rates API and listings without a query per row."""

from datetime import date
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts.services import add_member, ensure_system_roles
from apps.accounts.tests.factories import UserFactory
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import DailyRate, PromoCode, Season, SeasonRate
from apps.rates.tests.factories import (
    CancellationPolicyFactory,
    DerivedRatePlanFactory,
    ExtraFactory,
    RatePlanFactory,
    RoomTypeRateDefaultsFactory,
    TaxFactory,
)

pytestmark = pytest.mark.django_db

URL = "/api/v1/rates/"
RESOURCES = [
    "taxes",
    "cancellation-policies",
    "rate-plans",
    "room-type-defaults",
    "seasons",
    "season-rates",
    "extras",
    "promo-codes",
]


def make_row(prop, resource, n=0):
    """One row of `resource` in `prop`, with the relations its listing serializes (M2M, children, rates)."""
    room_type = RoomTypeFactory(property=prop)
    plan = RatePlanFactory(property=prop, room_types=[room_type])
    if resource == "taxes":
        return TaxFactory(property=prop)
    if resource == "cancellation-policies":
        policy = CancellationPolicyFactory(property=prop)
        RatePlanFactory(property=prop, cancellation_policy=policy)
        return policy
    if resource == "rate-plans":
        DerivedRatePlanFactory(property=prop, parent=plan, room_types=[room_type])
        return plan
    if resource == "room-type-defaults":
        return RoomTypeRateDefaultsFactory(room_type=room_type, rate_plan=plan)
    season = Season.objects.create(
        property=prop, name=f"Temporada {n}", start_date=date(2026, 12, 15), end_date=date(2027, 1, 15)
    )
    rate = SeasonRate.objects.create(season=season, room_type=room_type, rate_plan=plan, price=Decimal("1"))
    if resource == "seasons":
        return season
    if resource == "season-rates":
        return rate
    if resource == "extras":
        return ExtraFactory(property=prop, tax=TaxFactory(property=prop, applies_to="extras"))
    promo = PromoCode.objects.create(property=prop, code=f"PROMO{n}", value=Decimal("10"))
    promo.rate_plans.set([plan])
    return promo


@pytest.mark.parametrize("resource", RESOURCES)
def test_rows_of_a_sibling_property_are_invisible_and_untouchable(api, rates, resource):
    foreign = make_row(PropertyFactory(organization=rates.prop.organization), resource)
    listing = api.get(f"{URL}{resource}/").json()["results"]
    assert str(foreign.pk) not in {item["id"] for item in listing}
    assert api.get(f"{URL}{resource}/{foreign.pk}/").status_code == 404
    assert api.patch(f"{URL}{resource}/{foreign.pk}/", {}, format="json").status_code == 404
    assert api.delete(f"{URL}{resource}/{foreign.pk}/").status_code == 404
    assert type(foreign).objects.filter(pk=foreign.pk).exists()


def test_season_prices_cannot_use_a_season_of_another_property(api, rates):
    foreign_season = make_row(PropertyFactory(organization=rates.prop.organization), "seasons")
    response = api.post(
        f"{URL}season-rates/",
        {
            "season": str(foreign_season.pk),
            "room_type": str(rates.room_type.pk),
            "rate_plan": str(rates.plan.pk),
            "price": "1",
        },
        format="json",
    )
    assert (response.status_code, list(response.json()["fields"])) == (400, ["season"])


def test_bulk_edit_cannot_touch_categories_of_another_property(api, rates):
    foreign = RoomTypeFactory(property=PropertyFactory(organization=rates.prop.organization))
    response = api.post(
        f"{URL}grid/bulk/",
        {
            "room_type_ids": [str(foreign.pk)],
            "rate_plan_id": str(rates.plan.pk),
            "start": "2026-10-01",
            "end": "2026-10-02",
            "set": {"price": "1"},
        },
        format="json",
    )
    assert (response.status_code, list(response.json()["fields"])) == (400, ["room_type_ids"])
    assert not DailyRate.objects.exists()


@pytest.mark.parametrize("resource", RESOURCES)
def test_listings_do_not_query_once_per_row(api, rates, resource):
    def count_queries():
        with CaptureQueriesContext(connection) as queries:
            response = api.get(f"{URL}{resource}/")
        assert response.status_code == 200
        return len(queries)

    make_row(rates.prop, resource, n=1)
    with_one = count_queries()
    for n in range(2, 6):
        make_row(rates.prop, resource, n=n)
    assert count_queries() == with_one


READS = [
    "taxes/",
    "cancellation-policies/",
    "rate-plans/",
    "room-type-defaults/",
    "seasons/",
    "season-rates/",
    "extras/",
    "promo-codes/",
    "room-types/",
    "holidays/",
    "grid/?start=2026-10-01&end=2026-10-03",
]


@pytest.mark.parametrize("path", READS)
def test_front_desk_can_read_everything(api_for, make_member, rates, path):
    front_desk = api_for(make_member("front_desk"), rates.prop)
    assert front_desk.get(f"{URL}{path}").status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "taxes/", {"code": "X", "name": "X", "rate": "1"}),
        ("post", "rate-plans/", {"code": "X", "name": {"es": "X"}}),
        ("post", "grid/bulk/", {}),
        ("post", "promo-codes/", {"code": "X10", "value": "10"}),
    ],
)
def test_front_desk_cannot_edit(api_for, make_member, rates, method, path, body):
    front_desk = api_for(make_member("front_desk"), rates.prop)
    response = getattr(front_desk, method)(f"{URL}{path}", body, format="json")
    assert response.status_code == 403
    assert (response.json()["code"], response.json()["permission"]) == ("permission_denied", "rates.manage")


def test_front_desk_can_use_the_quote_tool(api_for, make_member, rates):
    front_desk = api_for(make_member("front_desk"), rates.prop)
    response = front_desk.post(
        f"{URL}quote/",
        {
            "room_type_id": str(rates.room_type.pk),
            "rate_plan_id": str(rates.plan.pk),
            "checkin": "2026-10-01",
            "checkout": "2026-10-02",
            "adults": 2,
        },
        format="json",
    )
    assert response.status_code == 200


def test_front_desk_cannot_delete_or_update(api_for, make_member, rates):
    front_desk = api_for(make_member("front_desk"), rates.prop)
    assert front_desk.patch(f"{URL}taxes/{rates.tax.pk}/", {"rate": "5"}, format="json").status_code == 403
    assert front_desk.delete(f"{URL}taxes/{rates.tax.pk}/").status_code == 403


@pytest.mark.parametrize("path", ["taxes/", "grid/?start=2026-10-01&end=2026-10-03", "holidays/"])
def test_housekeeping_cannot_read_rates(api_for, make_member, rates, path):
    housekeeping = api_for(make_member("housekeeping"), rates.prop)
    response = housekeeping.get(f"{URL}{path}")
    assert (response.status_code, response.json()["permission"]) == (403, "rates.view")


def test_rows_of_other_properties_are_invisible(api, rates):
    sibling = PropertyFactory(organization=rates.prop.organization)
    foreign_tax = TaxFactory(property=sibling, code="SIBLING")
    assert [t["code"] for t in api.get(f"{URL}taxes/").json()["results"]] == ["IVA"]
    assert api.get(f"{URL}taxes/{foreign_tax.pk}/").status_code == 404
    assert api.patch(f"{URL}taxes/{foreign_tax.pk}/", {"rate": "1"}, format="json").status_code == 404
    assert api.delete(f"{URL}taxes/{foreign_tax.pk}/").status_code == 404


def test_users_of_another_organization_cannot_open_this_property(api_for, rates):
    other_org = OrganizationFactory()
    ensure_system_roles(other_org)
    stranger = UserFactory()
    add_member(other_org, stranger, "owner")
    client = api_for(stranger, rates.prop)
    assert client.get(f"{URL}taxes/").status_code == 404
    assert client.get(f"{URL}grid/?start=2026-10-01&end=2026-10-03").status_code == 404
