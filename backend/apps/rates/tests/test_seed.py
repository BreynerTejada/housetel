"""Demo seed of `rates` (plan B2a). The categories are created here with the names of the inventory seed
(spec §10 / plan B1); the full seed runs in B-INT."""

import random
from datetime import date
from decimal import Decimal

import pytest

from apps.core.seed import SeedContext
from apps.core.tests.factories import PropertyFactory
from apps.inventory.tests.factories import DormRoomTypeFactory, RoomTypeFactory
from apps.rates.models import (
    CancellationPolicy,
    DailyRate,
    Extra,
    PromoCode,
    RatePlan,
    RoomTypeRateDefaults,
    Season,
    SeasonRate,
    Tax,
)
from apps.rates.seed import seed
from apps.rates.services.quote import quote

pytestmark = pytest.mark.django_db

D = Decimal
TODAY = date(2026, 9, 25)


def category(prop, code, es, en, *, dorm=False, order=0):
    factory = DormRoomTypeFactory if dorm else RoomTypeFactory
    return factory(property=prop, code=code, name={"es": es, "en": en}, sort_order=order)


@pytest.fixture
def ctx(organization):
    aurora = PropertyFactory(organization=organization, business_date=TODAY)
    medellin = PropertyFactory(organization=organization, business_date=TODAY)
    hostel = PropertyFactory(organization=organization, property_type="hostel", business_date=TODAY)
    category(aurora, "DBL", "Estándar", "Standard", order=1)
    category(aurora, "SUP", "Superior", "Superior", order=2)
    category(aurora, "STE", "Suite Vista al Mar", "Sea View Suite", order=3)
    category(medellin, "STD", "Estándar", "Standard", order=1)
    category(medellin, "EJE", "Ejecutiva", "Executive", order=2)
    category(medellin, "FAM", "Familiar", "Family", order=3)
    # codes and names of the inventory seed (apps/inventory/seed.py)
    category(hostel, "D6", "Dormitorio mixto 6 camas", "6-bed mixed dorm", dorm=True, order=1)
    category(hostel, "D8", "Dormitorio mixto 8 camas", "8-bed mixed dorm", dorm=True, order=2)
    category(hostel, "DF6", "Dormitorio femenino 6 camas", "6-bed female dorm", dorm=True, order=3)
    category(hostel, "PDB", "Privada doble", "Private double", order=4)
    category(hostel, "PFM", "Privada familiar", "Family private", order=5)
    return SeedContext(
        today=TODAY,
        rng=random.Random(20260925),
        properties={"aurora": aurora, "andino_mde": medellin, "andino_bog": hostel},
    )


def default_prices(prop):
    rows = RoomTypeRateDefaults.objects.filter(rate_plan__property=prop, rate_plan__code="FLEX")
    return {row.room_type.code: row.price for row in rows.select_related("room_type")}


def test_every_property_gets_its_taxes_policies_plans_and_prices(ctx):
    seed(ctx)
    for prop in ctx.properties.values():
        assert set(Tax.objects.filter(property=prop).values_list("code", flat=True)) == {"IVA", "IVA-EXTRAS"}
        assert CancellationPolicy.objects.filter(property=prop).count() == 2
        assert set(RatePlan.objects.filter(property=prop).values_list("code", flat=True)) == {
            "FLEX",
            "NR",
            "BB",
        }
    assert default_prices(ctx.properties["aurora"]) == {
        "DBL": D("320000.00"),
        "SUP": D("420000.00"),
        "STE": D("650000.00"),
    }
    assert default_prices(ctx.properties["andino_mde"]) == {
        "STD": D("260000.00"),
        "EJE": D("340000.00"),
        "FAM": D("420000.00"),
    }
    assert default_prices(ctx.properties["andino_bog"]) == {
        "D6": D("65000.00"),
        "D8": D("55000.00"),
        "DF6": D("70000.00"),
        "PDB": D("180000.00"),
        "PFM": D("260000.00"),
    }
    dbl = RoomTypeRateDefaults.objects.get(room_type__code="DBL", rate_plan__code="FLEX")
    assert (dbl.dow_adjustments, dbl.extra_adult_price, dbl.extra_child_price) == (
        {"fri": 15, "sat": 15},
        D("60000.00"),
        D("30000.00"),
    )


def test_high_season_and_holy_week_raise_the_prices(ctx):
    seed(ctx)
    aurora = ctx.properties["aurora"]
    high = Season.objects.get(property=aurora, name="Alta fin de año")
    holy = Season.objects.get(property=aurora, name="Semana Santa")
    assert (high.start_date, high.end_date) == (date(2026, 12, 15), date(2027, 1, 15))
    assert (holy.start_date, holy.end_date) == (date(2027, 3, 21), date(2027, 3, 28))  # Easter 2027: 28 Mar
    assert holy.priority > high.priority
    assert SeasonRate.objects.get(season=high, room_type__code="DBL").price == D("416000.00")  # +30 %
    assert SeasonRate.objects.filter(season__property=aurora).count() == 6


def test_extras_promo_and_example_restrictions(ctx):
    seed(ctx)
    aurora = ctx.properties["aurora"]
    extras = {e.code: (e.price, e.charge_type, e.tax.code) for e in Extra.objects.filter(property=aurora)}
    assert extras == {
        "BREAKFAST": (D("35000.00"), "per_person_night", "IVA-EXTRAS"),
        "PARKING": (D("25000.00"), "per_night", "IVA-EXTRAS"),
        "LATE_CHECKOUT": (D("80000.00"), "per_stay", "IVA-EXTRAS"),
        "AIRPORT_TRANSFER": (D("90000.00"), "per_stay", "IVA-EXTRAS"),
    }
    promo = PromoCode.objects.get(property=aurora, code="BIENVENIDA10")
    assert (promo.discount_type, promo.value, promo.valid_from) == ("percent", D("10.00"), TODAY)

    saturdays = DailyRate.objects.filter(rate_plan__property=aurora, min_los=2)
    assert saturdays.exists()
    assert {row.date.weekday() for row in saturdays} == {5}
    assert all(date(2026, 12, 15) <= row.date <= date(2027, 1, 15) for row in saturdays)
    flex = RatePlan.objects.get(property=aurora, code="FLEX")
    dbl = flex.room_types.get(code="DBL")
    saturday = quote(
        property=aurora,
        room_type=dbl,
        rate_plan=flex,
        checkin=date(2026, 12, 19),
        checkout=date(2026, 12, 20),
        adults=2,
    )
    assert saturday.violations == ["min_los"]
    assert saturday.nights[0].base == D("478400")  # season 416.000 × 1.15 (Saturday)


def test_running_it_twice_changes_nothing(ctx):
    seed(ctx)
    counts = [
        model.objects.count()
        for model in (
            Tax,
            CancellationPolicy,
            RatePlan,
            RoomTypeRateDefaults,
            Season,
            SeasonRate,
            Extra,
            PromoCode,
        )
    ]
    daily = list(DailyRate.objects.order_by("id").values_list("id", "price", "min_los"))
    seed(ctx)
    assert counts == [
        model.objects.count()
        for model in (
            Tax,
            CancellationPolicy,
            RatePlan,
            RoomTypeRateDefaults,
            Season,
            SeasonRate,
            Extra,
            PromoCode,
        )
    ]
    assert list(DailyRate.objects.order_by("id").values_list("id", "price", "min_los")) == daily


def test_properties_without_categories_are_skipped(organization):
    empty = PropertyFactory(organization=organization, business_date=TODAY)
    seed(SeedContext(today=TODAY, rng=random.Random(1), properties={"aurora": empty}))
    assert not RatePlan.objects.filter(property=empty).exists()
