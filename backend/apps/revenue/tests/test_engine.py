"""The recommendation engine: anchor price, rules, combination, bounds, maximum change, threshold, rounding.

`compute_recommendations(..., persist=False)` returns unsaved recommendations; the anchor is 300.000 (the
category default) unless a test says otherwise. Business date: Thursday 2026-10-01."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory
from apps.rates.models import DailyRate
from apps.revenue.models import PriceBounds, RateRecommendation
from apps.revenue.services.engine import compute_recommendations
from apps.revenue.tests.conftest import make_rule, oct_, sell

pytestmark = pytest.mark.django_db

D = Decimal
OCCUPANCY = {
    "tiers": [
        {"min": 0, "max": 40, "adjust": -8},
        {"min": 70, "max": 85, "adjust": 8},
        {"min": 85, "max": 100, "adjust": 15},
    ]
}


def compute(hotel, start, end=None, **kwargs):
    recs = compute_recommendations(
        hotel.prop, start=start, end=end or start + timedelta(days=1), persist=False
    )
    return {rec.date: rec for rec in recs}


def rule_reasons(rec):
    return [(r["kind"], r["adjust"], r["applied"]) for r in rec.reasons if r["type"] == "rule"]


def limits(rec):
    return [r["kind"] for r in rec.reasons if r["type"] == "limit"]


class TestOccupancy:
    def test_each_tier_moves_the_price_of_its_nights(self, hotel):
        make_rule(hotel.prop, "occupancy", OCCUPANCY)
        sell(hotel.room_type, oct_(5), 2)  # 20 %
        sell(hotel.room_type, oct_(6), 5)  # 50 %: no tier
        sell(hotel.room_type, oct_(7), 7)  # 70 %
        sell(hotel.room_type, oct_(8), 9)  # 90 %
        sell(hotel.room_type, oct_(9), 10)  # sold out
        recs = compute(hotel, oct_(5), oct_(10))
        assert {day: rec.recommended_price for day, rec in recs.items()} == {
            oct_(5): D("276000"),
            oct_(7): D("324000"),
            oct_(8): D("345000"),
            oct_(9): D("345000"),
        }
        rec = recs[oct_(8)]
        assert (rec.occupancy, rec.available_units) == (D("90.00"), 1)
        assert rec.reasons[0] == {
            "type": "rule",
            "rule_id": str(hotel.prop.pricing_rules.get().pk),
            "name": "occupancy",
            "kind": "occupancy",
            "combine": "stack",
            "adjust": "15.00",
            "applied": True,
            "detail": {"occupancy": "90.00"},
        }

    def test_blocked_units_are_not_sellable(self, hotel):
        make_rule(hotel.prop, "occupancy", OCCUPANCY)
        sell(hotel.room_type, oct_(5), 4, blocked=5)  # 4 of the 5 sellable rooms: 80 %
        rec = compute(hotel, oct_(5))[oct_(5)]
        assert (rec.occupancy, rec.recommended_price) == (D("80.00"), D("324000"))

    def test_nights_without_sellable_units_get_no_recommendation(self, hotel):
        make_rule(hotel.prop, "day_of_week", {"mon": 10})
        sell(hotel.room_type, oct_(5), 0, total=4, blocked=4)
        assert compute(hotel, oct_(5)) == {}


class TestLeadTime:
    def test_last_minute_and_early_bird(self, hotel):
        make_rule(
            hotel.prop,
            "lead_time",
            {"last_minute": [{"max_days": 3, "adjust": -5}], "early_bird": [{"min_days": 60, "adjust": 5}]},
        )
        recs = compute(hotel, oct_(1), oct_(1) + timedelta(days=62))
        assert recs[oct_(1)].recommended_price == D("285000")  # today (0 days)
        assert recs[oct_(4)].recommended_price == D("285000")  # 3 days to go
        assert oct_(5) not in recs
        assert oct_(1) + timedelta(days=59) not in recs
        assert recs[oct_(1) + timedelta(days=60)].recommended_price == D("315000")
        assert recs[oct_(4)].reasons[0]["detail"] == {"lead_days": 3, "window": "last_minute", "days": 3}


class TestDayOfWeek:
    def test_only_the_configured_weekday_changes(self, hotel):
        make_rule(hotel.prop, "day_of_week", {"sat": 8})
        recs = compute(hotel, oct_(1), oct_(8))
        assert list(recs) == [oct_(3)]  # Saturday
        assert recs[oct_(3)].recommended_price == D("324000")


class TestHolidays:
    def test_the_monday_holiday_and_its_long_weekend(self, hotel):
        make_rule(hotel.prop, "holiday", {"adjust": 12})
        recs = compute(hotel, oct_(9), oct_(14))
        assert sorted(recs) == [oct_(10), oct_(11), oct_(12)]
        assert {rec.recommended_price for rec in recs.values()} == {D("336000")}
        assert recs[oct_(12)].reasons[0]["detail"] == {
            "name_es": "Día de la Raza",
            "name_en": "Columbus Day",
            "bridge": False,
        }
        assert recs[oct_(10)].reasons[0]["detail"]["bridge"] is True


class TestEvents:
    def test_an_event_adjusts_its_nights(self, hotel):
        make_rule(
            hotel.prop,
            "event",
            {"start": "2026-10-20", "end": "2026-10-21", "adjust": 10},
            name="Congreso médico",
        )
        recs = compute(hotel, oct_(19), oct_(23))
        assert sorted(recs) == [oct_(20), oct_(21)]
        assert recs[oct_(20)].reasons[0]["name"] == "Congreso médico"


class TestCombination:
    """Saturday 2026-10-10 (long weekend): Saturday +8 %, holiday +12 %, event +20 %; cap raised to 50 %."""

    @pytest.fixture(autouse=True)
    def wide_cap(self, hotel):
        hotel.settings.max_daily_change_percent = 50
        hotel.settings.save()

    def event(self, hotel, combine):
        return make_rule(
            hotel.prop,
            "event",
            {"start": "2026-10-09", "end": "2026-10-11", "adjust": 20},
            combine=combine,
            name="Evento",
        )

    def test_stack_rules_add_up(self, hotel):
        make_rule(hotel.prop, "day_of_week", {"sat": 8})
        make_rule(hotel.prop, "holiday", {"adjust": 12})
        rec = compute(hotel, oct_(10))[oct_(10)]
        assert (rec.adjustment_percent, rec.recommended_price) == (D("20.00"), D("360000"))

    def test_only_the_highest_max_rule_counts(self, hotel):
        make_rule(hotel.prop, "holiday", {"adjust": 12}, combine="max")
        self.event(hotel, "max")
        rec = compute(hotel, oct_(10))[oct_(10)]
        assert rec.recommended_price == D("360000")
        assert sorted(rule_reasons(rec)) == [("event", "20.00", True), ("holiday", "12.00", False)]

    def test_stack_rules_plus_the_winning_max_rule(self, hotel):
        make_rule(hotel.prop, "day_of_week", {"sat": 8})
        make_rule(hotel.prop, "holiday", {"adjust": 12}, combine="max")
        self.event(hotel, "max")
        rec = compute(hotel, oct_(10))[oct_(10)]
        assert (rec.adjustment_percent, rec.recommended_price) == (D("28.00"), D("384000"))

    def test_the_highest_adjustment_wins_over_a_higher_priority(self, hotel):
        make_rule(hotel.prop, "holiday", {"adjust": 12}, combine="max", priority=50)
        rule = self.event(hotel, "max")
        rule.priority = 5
        rule.save()
        rec = compute(hotel, oct_(10))[oct_(10)]
        assert rec.recommended_price == D("360000")  # +20 % (priority 5) beats +12 % (priority 50)

    def test_the_highest_max_rule_wins_even_when_every_one_is_a_discount(self, hotel):
        make_rule(hotel.prop, "holiday", {"adjust": -5}, combine="max")
        make_rule(hotel.prop, "day_of_week", {"sat": -10}, combine="max")
        rec = compute(hotel, oct_(10))[oct_(10)]
        assert rec.recommended_price == D("285000")

    def test_inactive_rules_and_rules_of_other_categories_are_ignored(self, hotel):
        suite = RoomTypeFactory(property=hotel.prop, code="STE", sort_order=2)
        RoomFactory(room_type=suite, number="301")
        make_rule(hotel.prop, "day_of_week", {"sat": 8}, room_types=[suite])
        make_rule(hotel.prop, "holiday", {"adjust": 12}, active=False)
        assert compute(hotel, oct_(10)) == {}  # the suite has no price: nothing to recommend


class TestLimits:
    def test_bounds_are_a_hard_floor_and_ceiling(self, hotel):
        PriceBounds.objects.create(
            room_type=hotel.room_type, rate_plan=hotel.plan, min_price=D("290000"), max_price=D("330000")
        )
        make_rule(hotel.prop, "holiday", {"adjust": 12})
        make_rule(hotel.prop, "occupancy", OCCUPANCY)
        for day in (10, 11, 12):
            sell(hotel.room_type, oct_(day), 6)  # 60 %: no occupancy tier on the long weekend
        recs = compute(hotel, oct_(10), oct_(14))
        assert recs[oct_(12)].recommended_price == D("330000")  # 336.000 → ceiling
        assert limits(recs[oct_(12)]) == ["max_price"]
        assert recs[oct_(13)].recommended_price == D("290000")  # 0 % occupancy: 276.000 → floor
        assert limits(recs[oct_(13)]) == ["min_price"]

    def test_the_change_is_capped_by_the_maximum_daily_change(self, hotel):
        make_rule(hotel.prop, "event", {"start": "2026-10-20", "end": "2026-10-20", "adjust": 50})
        rec = compute(hotel, oct_(20))[oct_(20)]
        assert (rec.adjustment_percent, rec.recommended_price, rec.change_percent) == (
            D("50.00"),
            D("360000"),
            D("20.00"),
        )
        assert rec.reasons[-1] == {
            "type": "limit",
            "kind": "max_daily_change",
            "percent": "20.00",
            "price": "360000.00",
        }

    def test_bounds_win_over_the_maximum_change(self, hotel):
        DailyRate.objects.create(
            room_type=hotel.room_type, rate_plan=hotel.plan, date=oct_(20), price=D("200000"), source="manual"
        )
        PriceBounds.objects.create(room_type=hotel.room_type, rate_plan=hotel.plan, min_price=D("280000"))
        make_rule(hotel.prop, "event", {"start": "2026-10-20", "end": "2026-10-20", "adjust": 100})
        rec = compute(hotel, oct_(20))[oct_(20)]
        # 400.000 wanted → capped at 240.000 (+20 %) → the floor wins: 280.000 (+40 %)
        assert (rec.recommended_price, rec.change_percent) == (D("280000"), D("40.00"))
        assert limits(rec) == ["max_daily_change", "min_price"]

    def test_rounding_never_leaves_the_bounds(self, hotel):
        PriceBounds.objects.create(
            room_type=hotel.room_type, rate_plan=hotel.plan, min_price=D("280500"), max_price=D("330500")
        )
        make_rule(hotel.prop, "holiday", {"adjust": 12})
        DailyRate.objects.create(
            room_type=hotel.room_type, rate_plan=hotel.plan, date=oct_(20), price=D("200000"), source="manual"
        )
        make_rule(hotel.prop, "event", {"start": "2026-10-20", "end": "2026-10-20", "adjust": 100})
        recs = compute(hotel, oct_(12), oct_(21))
        assert recs[oct_(12)].recommended_price == D("330000")  # the ceiling rounded down, not up to 331.000
        assert recs[oct_(20)].recommended_price == D("281000")  # the floor rounded up, not down to 280.000

    def test_the_cap_counts_from_the_price_the_night_had_at_the_start_of_the_day(self, hotel):
        # revenue already raised the night today from 300.000 to 360.000 (+20 %)
        DailyRate.objects.create(
            room_type=hotel.room_type,
            rate_plan=hotel.plan,
            date=oct_(20),
            price=D("360000"),
            source="revenue",
        )
        RateRecommendation.objects.create(
            property=hotel.prop,
            room_type=hotel.room_type,
            rate_plan=hotel.plan,
            date=oct_(20),
            current_price=D("300000"),
            anchor_price=D("300000"),
            anchor_source="default",
            recommended_price=D("360000"),
            change_percent=D("20"),
            status="applied",
            applied_at=timezone.now(),
        )
        make_rule(hotel.prop, "event", {"start": "2026-10-20", "end": "2026-10-20", "adjust": 50})
        assert compute(hotel, oct_(20)) == {}  # 450.000 wanted, but today's 20 % is used up


class TestThresholdAndRounding:
    def test_changes_below_the_minimum_are_not_recommended(self, hotel):
        make_rule(hotel.prop, "day_of_week", {"fri": 1.5, "sat": 2})
        recs = compute(hotel, oct_(2), oct_(4))
        assert list(recs) == [oct_(3)]  # +2 % is recommended (the minimum is inclusive), +1.5 % is not
        assert recs[oct_(3)].change_percent == D("2.00")

    def test_prices_are_rounded_to_the_configured_multiple(self, hotel):
        hotel.room_type.rate_defaults.update(price=D("310500"))
        make_rule(hotel.prop, "day_of_week", {"sat": 7})
        rec = compute(hotel, oct_(3))[oct_(3)]
        assert rec.recommended_price == D("332000")  # 332.235 → nearest 1.000

    def test_without_rounding_only_the_currency_unit_is_kept(self, hotel):
        hotel.settings.price_rounding = 0
        hotel.settings.save()
        hotel.room_type.rate_defaults.update(price=D("310500"))
        make_rule(hotel.prop, "day_of_week", {"sat": 7})
        assert compute(hotel, oct_(3))[oct_(3)].recommended_price == D("332235")


class TestAnchor:
    def test_revenue_rows_are_ignored_and_the_price_returns_to_the_anchor(self, hotel):
        DailyRate.objects.create(
            room_type=hotel.room_type,
            rate_plan=hotel.plan,
            date=oct_(14),
            price=D("345000"),
            source="revenue",
        )
        rec = compute(hotel, oct_(14))[oct_(14)]
        assert (rec.current_price, rec.current_source) == (D("345000"), "revenue")
        assert (rec.anchor_price, rec.anchor_source) == (D("300000"), "default")
        assert rec.recommended_price == D("300000")
        assert rule_reasons(rec) == []

    def test_a_manual_price_is_the_anchor(self, hotel):
        DailyRate.objects.create(
            room_type=hotel.room_type, rate_plan=hotel.plan, date=oct_(15), price=D("400000"), source="manual"
        )
        make_rule(hotel.prop, "day_of_week", {"thu": 10})
        rec = compute(hotel, oct_(15))[oct_(15)]
        assert (rec.anchor_price, rec.anchor_source, rec.recommended_price) == (
            D("400000"),
            "manual",
            D("440000"),
        )

    def test_a_manual_anchor_is_remembered_after_revenue_changed_the_night(self, hotel):
        DailyRate.objects.create(
            room_type=hotel.room_type,
            rate_plan=hotel.plan,
            date=oct_(16),
            price=D("440000"),
            source="revenue",
        )
        RateRecommendation.objects.create(
            property=hotel.prop,
            room_type=hotel.room_type,
            rate_plan=hotel.plan,
            date=oct_(16),
            current_price=D("400000"),
            current_source="manual",
            anchor_price=D("400000"),
            anchor_source="manual",
            recommended_price=D("440000"),
            change_percent=D("10"),
            status="applied",
            applied_at=timezone.now() - timedelta(days=2),
        )
        make_rule(hotel.prop, "day_of_week", {"fri": 10})
        assert compute(hotel, oct_(16)) == {}  # 400.000 + 10 % is already the price

    def test_derived_plans_and_nights_without_price_get_nothing(self, hotel):
        RoomTypeFactory(property=hotel.prop, code="SUP")  # no price anywhere
        make_rule(hotel.prop, "day_of_week", {"sat": 8})
        recs = compute(hotel, oct_(3))
        assert [(rec.room_type.code, rec.rate_plan.code) for rec in recs.values()] == [("DBL", "FLEX")]


def test_nothing_is_saved_without_persist(hotel):
    make_rule(hotel.prop, "day_of_week", {"sat": 8})
    assert compute(hotel, oct_(3))
    assert not RateRecommendation.objects.exists()
