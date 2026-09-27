"""`resolve_daily` contract: effective price + restrictions per night, as the grid shows them."""

from decimal import Decimal

import pytest

from apps.rates.models import Season, SeasonRate
from apps.rates.services.quote import resolve_daily, set_daily_rates
from apps.rates.tests.conftest import oct_
from apps.rates.tests.factories import DailyRateFactory, DerivedRatePlanFactory

pytestmark = pytest.mark.django_db

D = Decimal


def test_each_source_is_reported(rates):
    rates.defaults.dow_adjustments = {"sat": 15}
    rates.defaults.save()
    season = Season.objects.create(property=rates.prop, name="Puente", start_date=oct_(2), end_date=oct_(2))
    SeasonRate.objects.create(
        season=season, room_type=rates.room_type, rate_plan=rates.plan, price=D("400000")
    )
    DailyRateFactory(room_type=rates.room_type, rate_plan=rates.plan, date=oct_(4), price=D("300000"))
    days = resolve_daily(rates.room_type, rates.plan, oct_(1), oct_(5))
    assert [(d.date, d.price, d.source) for d in days] == [
        (oct_(1), D("320000"), "default"),
        (oct_(2), D("400000"), "season"),
        (oct_(3), D("368000.00"), "default"),  # Saturday +15 %
        (oct_(4), D("300000"), "manual"),
    ]


def test_season_days_take_extra_prices_from_the_defaults(rates):
    season = Season.objects.create(property=rates.prop, name="Alta", start_date=oct_(1), end_date=oct_(1))
    SeasonRate.objects.create(
        season=season, room_type=rates.room_type, rate_plan=rates.plan, price=D("400000")
    )
    day = resolve_daily(rates.room_type, rates.plan, oct_(1), oct_(2))[0]
    assert (day.extra_adult_price, day.extra_child_price, day.min_los, day.stop_sell) == (
        D("60000"),
        D("30000"),
        None,
        False,
    )


def test_derived_plans_get_derived_prices_with_the_base_restrictions(rates):
    derived = DerivedRatePlanFactory(property=rates.prop, parent=rates.plan, derivation_value=D("-12"))
    DailyRateFactory(
        room_type=rates.room_type, rate_plan=rates.plan, date=oct_(2), price=D("400000"), stop_sell=True
    )
    days = resolve_daily(rates.room_type, derived, oct_(1), oct_(3))
    assert [(d.price, d.stop_sell, d.source) for d in days] == [
        (D("281600"), False, "default"),
        (D("352000"), True, "manual"),
    ]


def test_days_without_price_stay_at_zero_even_for_derived_plans(rates):
    rates.defaults.delete()
    derived = DerivedRatePlanFactory(
        property=rates.prop, parent=rates.plan, derivation_type="amount", derivation_value=D("35000")
    )
    assert [(d.price, d.source) for d in resolve_daily(rates.room_type, derived, oct_(1), oct_(2))] == [
        (D("0"), "none")
    ]


class TestNightsThatOnlyHoldRestrictions:
    """A night written only for its restrictions keeps the source `default`/`season`: nobody set its price, so
    it follows later changes of the category defaults and of the seasons (only a price change freezes it)."""

    def restrict(self, rates, **restrictions):
        set_daily_rates(
            property=rates.prop,
            room_type=rates.room_type,
            rate_plan=rates.plan,
            start=oct_(1),
            end=oct_(3),
            restrictions=restrictions,
        )

    def days(self, rates):
        return resolve_daily(rates.room_type, rates.plan, oct_(1), oct_(3))

    def test_they_follow_a_later_change_of_the_defaults(self, rates):
        self.restrict(rates, min_los=2)
        rates.defaults.price = D("350000")
        rates.defaults.save()
        assert [(d.price, d.source, d.min_los) for d in self.days(rates)] == [(D("350000"), "default", 2)] * 2

    def test_they_follow_a_later_change_of_the_season_and_its_removal(self, rates):
        season = Season.objects.create(
            property=rates.prop, name="Puente", start_date=oct_(1), end_date=oct_(2)
        )
        SeasonRate.objects.create(
            season=season, room_type=rates.room_type, rate_plan=rates.plan, price=D("400000")
        )
        self.restrict(rates, stop_sell=True)
        SeasonRate.objects.filter(season=season).update(price=D("450000"))
        assert [(d.price, d.source, d.stop_sell) for d in self.days(rates)] == [
            (D("450000"), "season", True)
        ] * 2
        season.delete()
        assert [(d.price, d.source, d.stop_sell) for d in self.days(rates)] == [
            (D("320000"), "default", True)
        ] * 2

    def test_a_season_created_afterwards_prices_them(self, rates):
        self.restrict(rates, closed_to_arrival=True)
        season = Season.objects.create(
            property=rates.prop, name="Puente", start_date=oct_(1), end_date=oct_(1)
        )
        SeasonRate.objects.create(
            season=season, room_type=rates.room_type, rate_plan=rates.plan, price=D("400000")
        )
        assert [(d.price, d.source) for d in self.days(rates)] == [
            (D("400000"), "season"),
            (D("320000"), "default"),
        ]

    def test_they_keep_their_last_price_when_nothing_is_configured_anymore(self, rates):
        self.restrict(rates, min_los=2)
        rates.defaults.delete()
        assert [(d.price, d.source) for d in self.days(rates)] == [(D("320000"), "default")] * 2

    def test_nights_with_a_price_of_their_own_do_not_follow(self, rates):
        DailyRateFactory(room_type=rates.room_type, rate_plan=rates.plan, date=oct_(1), price=D("300000"))
        rates.defaults.price = D("350000")
        rates.defaults.save()
        assert [(d.price, d.source) for d in self.days(rates)] == [
            (D("300000"), "manual"),
            (D("350000"), "default"),
        ]
