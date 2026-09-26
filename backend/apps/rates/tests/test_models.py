from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import DailyRate, Season, SeasonRate
from apps.rates.tests.factories import (
    DailyRateFactory,
    DerivedRatePlanFactory,
    RatePlanFactory,
    RoomTypeRateDefaultsFactory,
    TaxFactory,
)

pytestmark = pytest.mark.django_db


def test_one_daily_rate_per_room_type_plan_and_date(prop):
    row = DailyRateFactory(room_type__property=prop, date=date(2026, 10, 1))
    with pytest.raises(IntegrityError), transaction.atomic():
        DailyRate.objects.create(
            room_type=row.room_type, rate_plan=row.rate_plan, date=date(2026, 10, 1), price=Decimal("1")
        )


def test_daily_rate_defaults_have_no_restrictions(prop):
    row = DailyRate.objects.get(pk=DailyRateFactory(room_type__property=prop).pk)
    assert (row.min_los, row.max_los, row.closed_to_arrival, row.closed_to_departure, row.stop_sell) == (
        None,
        None,
        False,
        False,
        False,
    )
    assert row.extra_adult_price is None and row.extra_child_price is None  # fall back to the defaults


def test_one_defaults_row_per_room_type_and_plan(prop):
    defaults = RoomTypeRateDefaultsFactory(room_type__property=prop)
    with pytest.raises(IntegrityError), transaction.atomic():
        RoomTypeRateDefaultsFactory(room_type=defaults.room_type, rate_plan=defaults.rate_plan)


@pytest.mark.parametrize("factory", [TaxFactory, RatePlanFactory])
def test_codes_are_unique_per_property(prop, factory):
    factory(property=prop, code="X")
    factory(code="X")
    with pytest.raises(IntegrityError), transaction.atomic():
        factory(property=prop, code="X")


def test_derived_plan_points_to_its_parent(prop):
    derived = DerivedRatePlanFactory(property=prop)
    assert derived.parent.kind == "base" and derived.parent.property == prop
    assert list(derived.parent.children.all()) == [derived]
    assert derived.base_plan == derived.parent and derived.parent.base_plan == derived.parent


@pytest.mark.parametrize(("kind", "with_parent"), [("derived", False), ("base", True)])
def test_only_derived_plans_have_a_parent(prop, kind, with_parent):
    parent = RatePlanFactory(property=prop) if with_parent else None
    with pytest.raises(IntegrityError), transaction.atomic():
        RatePlanFactory(property=prop, kind=kind, parent=parent)


def test_season_end_date_is_inclusive_but_not_before_start(prop):
    Season.objects.create(
        property=prop, name="Un día", start_date=date(2026, 12, 24), end_date=date(2026, 12, 24)
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Season.objects.create(
            property=prop, name="Mala", start_date=date(2026, 12, 24), end_date=date(2026, 12, 23)
        )


def test_one_season_rate_per_season_room_type_and_plan(prop):
    season = Season.objects.create(
        property=prop, name="Alta", start_date=date(2026, 12, 15), end_date=date(2027, 1, 15)
    )
    room_type = RoomTypeFactory(property=prop)
    plan = RatePlanFactory(property=prop)
    SeasonRate.objects.create(season=season, room_type=room_type, rate_plan=plan, price=Decimal("400000"))
    with pytest.raises(IntegrityError), transaction.atomic():
        SeasonRate.objects.create(season=season, room_type=room_type, rate_plan=plan, price=Decimal("1"))
