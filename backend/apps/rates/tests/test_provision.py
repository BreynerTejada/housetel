"""`provision_rates` (plan §C): the rate setup of a new property, idempotent by code/name."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.core.signals import rates_changed
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import CancellationPolicy, RatePlan, RoomTypeRateDefaults, Tax
from apps.rates.services.provision import provision_rates
from apps.rates.services.quote import quote

pytestmark = pytest.mark.django_db

D = Decimal
PRICES = {
    "DBL": {
        "price": "320000",
        "weekend_adjust_percent": 15,
        "extra_adult_price": "60000",
        "extra_child_price": "30000",
    },
    "SUP": {"price": "420000"},
}


@pytest.fixture
def hotel(prop):
    prop.business_date = date(2026, 9, 25)
    prop.save()
    return {
        "prop": prop,
        "DBL": RoomTypeFactory(property=prop, code="DBL"),
        "SUP": RoomTypeFactory(property=prop, code="SUP"),
    }


def test_default_setup_creates_taxes_policies_plans_and_prices(hotel, owner):
    prop = hotel["prop"]
    provision_rates(prop, room_type_prices=PRICES, actor=owner)

    taxes = {t.code: t for t in Tax.objects.filter(property=prop)}
    assert {
        code: (t.rate, t.applies_to, t.included_in_price, t.exempt_foreign_non_residents)
        for code, t in taxes.items()
    } == {
        "IVA": (D("19.00"), "room", False, True),
        "IVA-EXTRAS": (D("19.00"), "extras", False, False),
    }
    policies = {p.name["es"]: p for p in CancellationPolicy.objects.filter(property=prop)}
    assert set(policies) == {"Flexible 48h", "No reembolsable"}
    assert (policies["Flexible 48h"].free_until_hours_before, policies["Flexible 48h"].penalty_type) == (
        48,
        "first_night",
    )
    assert (policies["No reembolsable"].non_refundable, policies["No reembolsable"].penalty_type) == (
        True,
        "full",
    )

    plans = {p.code: p for p in RatePlan.objects.filter(property=prop)}
    assert set(plans) == {"FLEX", "NR", "BB"}
    flex, nr, bb = plans["FLEX"], plans["NR"], plans["BB"]
    assert (flex.kind, flex.name["es"], flex.cancellation_policy) == (
        "base",
        "Tarifa flexible",
        policies["Flexible 48h"],
    )
    assert (nr.parent, nr.derivation_type, nr.derivation_value, nr.cancellation_policy) == (
        flex,
        "percent",
        D("-12.00"),
        policies["No reembolsable"],
    )
    assert (bb.parent, bb.derivation_type, bb.derivation_value, bb.meal_plan) == (
        flex,
        "amount",
        D("35000.00"),
        "breakfast",
    )
    for plan in plans.values():
        assert set(plan.room_types.all()) == {hotel["DBL"], hotel["SUP"]}

    dbl = RoomTypeRateDefaults.objects.get(room_type=hotel["DBL"], rate_plan=flex)
    assert (dbl.price, dbl.dow_adjustments, dbl.extra_adult_price, dbl.extra_child_price) == (
        D("320000.00"),
        {"fri": 15, "sat": 15},
        D("60000.00"),
        D("30000.00"),
    )
    sup = RoomTypeRateDefaults.objects.get(room_type=hotel["SUP"], rate_plan=flex)
    assert (sup.price, sup.dow_adjustments, sup.extra_adult_price) == (D("420000.00"), {}, D("0.00"))
    assert AuditEvent.objects.filter(action="rates.provisioned", property=prop, actor=owner).count() == 1

    friday = quote(
        property=prop,
        room_type=hotel["DBL"],
        rate_plan=nr,
        checkin=date(2026, 10, 2),
        checkout=date(2026, 10, 3),
        adults=2,
    )
    assert friday.subtotal == D("323840")  # 320.000 × 1.15 × 0.88


def test_running_it_again_does_not_duplicate_or_overwrite(hotel):
    prop = hotel["prop"]
    provision_rates(prop, room_type_prices=PRICES)
    RoomTypeRateDefaults.objects.filter(room_type=hotel["DBL"]).update(price=D("333000"))
    provision_rates(prop, room_type_prices=PRICES)
    assert (Tax.objects.count(), CancellationPolicy.objects.count(), RatePlan.objects.count()) == (2, 2, 3)
    assert RoomTypeRateDefaults.objects.get(room_type=hotel["DBL"]).price == D("333000.00")


def test_custom_plans_and_no_default_taxes_or_policies(hotel):
    prop = hotel["prop"]
    provision_rates(
        prop,
        room_type_prices={"DBL": {"price": "250000"}},
        plans=[
            {"code": "BAR", "name": {"es": "Mejor tarifa", "en": "Best rate"}, "kind": "base"},
            {
                "code": "WEB",
                "name": {"es": "Web", "en": "Web"},
                "kind": "derived",
                "parent": "BAR",
                "derivation_type": "percent",
                "derivation_value": "-5",
                "is_public": False,
                "channels": ["direct"],
            },
        ],
        taxes_default=False,
        policies_default=False,
    )
    assert not Tax.objects.exists() and not CancellationPolicy.objects.exists()
    bar, web = RatePlan.objects.get(code="BAR"), RatePlan.objects.get(code="WEB")
    assert (bar.kind, bar.cancellation_policy, list(bar.room_types.all())) == ("base", None, [hotel["DBL"]])
    assert (web.parent, web.derivation_value, web.is_public, web.channels) == (
        bar,
        D("-5.00"),
        False,
        ["direct"],
    )
    assert RoomTypeRateDefaults.objects.get(rate_plan=bar).price == D("250000.00")


def test_unknown_room_type_codes_are_rejected_before_writing(hotel):
    with pytest.raises(DomainError) as exc:
        provision_rates(hotel["prop"], room_type_prices={"DBL": {"price": "1"}, "XXX": {"price": "1"}})
    assert exc.value.code == "unknown_room_type"
    assert not RatePlan.objects.exists() and not Tax.objects.exists()


@pytest.mark.parametrize(
    "spec",
    [
        {},  # a category without price would sell at 0
        {"price": "0"},
        {"price": "-1"},
        {"price": "mucho"},
        {"price": "320000", "extra_adult_price": "-5"},
        {"price": "320000", "extra_child_price": "gratis"},
        {"price": "320000", "single_occupancy_price": "0"},
        {"price": "320000", "weekend_adjust_percent": -150},
        {"price": "320000", "weekend_adjust_percent": "alto"},
        {"price": "320000", "child_age_limit": 18},
    ],
)
def test_prices_are_validated_before_writing_anything(hotel, spec):
    with pytest.raises(DomainError) as exc:
        provision_rates(hotel["prop"], room_type_prices={"SUP": {"price": "420000"}, "DBL": spec})
    assert (exc.value.code, exc.value.extra["room_type"]) == ("invalid_price", "DBL")
    assert not RatePlan.objects.exists() and not Tax.objects.exists()


def test_emits_rates_changed_for_the_first_year(hotel, django_capture_on_commit_callbacks):
    received = []

    def receiver(sender, **kwargs):
        received.append(kwargs)

    rates_changed.connect(receiver)
    try:
        with django_capture_on_commit_callbacks(execute=True):
            provision_rates(hotel["prop"], room_type_prices=PRICES)
    finally:
        rates_changed.disconnect(receiver)
    assert len(received) == 1
    plan_ids = set(RatePlan.objects.values_list("pk", flat=True))
    assert set(received[0]["rate_plan_ids"]) == plan_ids
    assert set(received[0]["room_type_ids"]) == {hotel["DBL"].pk, hotel["SUP"].pk}
    assert (received[0]["start"], received[0]["end"]) == (
        date(2026, 9, 25),
        date(2026, 9, 25) + timedelta(days=365),
    )
