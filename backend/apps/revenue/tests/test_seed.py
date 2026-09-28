"""Demo seed of `revenue` (plan C8 › Seed): default rules, price bounds per category and one initial run that
leaves pending recommendations (nothing is applied and the LLM is never called)."""

import random
from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.bookings.services.inventory import rebuild_inventory
from apps.core.seed import SeedContext
from apps.core.tests.factories import PropertyFactory
from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory
from apps.rates.models import DailyRate
from apps.rates.tests.factories import RatePlanFactory, RoomTypeRateDefaultsFactory
from apps.revenue.models import PriceBounds, PricingRule, RateRecommendation, RevenueRun, RevenueSettings
from apps.revenue.seed import seed
from apps.revenue.services.runs import run_revenue

pytestmark = pytest.mark.django_db

D = Decimal
TODAY = date(2026, 9, 25)


def hotel(organization, city, prices):
    prop = PropertyFactory(organization=organization, city=city, business_date=TODAY)
    plan = RatePlanFactory(property=prop, code="FLEX")
    for order, (code, price) in enumerate(prices.items(), start=1):
        room_type = RoomTypeFactory(property=prop, code=code, sort_order=order)
        RoomFactory(room_type=room_type, number=f"{order}01")
        RoomFactory(room_type=room_type, number=f"{order}02")
        plan.room_types.add(room_type)
        RoomTypeRateDefaultsFactory(room_type=room_type, rate_plan=plan, price=D(price))
    rebuild_inventory(prop, TODAY, TODAY + timedelta(days=130))
    return prop


@pytest.fixture
def ctx(organization):
    aurora = hotel(organization, "Cartagena", {"DBL": "320000", "STE": "650000"})
    medellin = hotel(organization, "Medellín", {"STD": "260000"})
    empty = PropertyFactory(organization=organization, business_date=TODAY)  # no categories, no plans
    return SeedContext(
        today=TODAY,
        rng=random.Random(20260925),
        properties={"aurora": aurora, "andino_mde": medellin, "andino_bog": empty},
    )


@pytest.fixture
def no_llm(monkeypatch):
    calls = []
    monkeypatch.setattr("apps.revenue.services.summary.get_llm", lambda property=None: calls.append(property))
    return calls


def rules_of(prop):
    return {
        rule.name: (rule.kind, rule.params, rule.combine)
        for rule in PricingRule.objects.filter(property=prop)
    }


def test_every_property_gets_the_default_rules(ctx, no_llm):
    seed(ctx)
    medellin = rules_of(ctx.properties["andino_mde"])
    assert medellin == {
        "Ocupación": (
            "occupancy",
            {
                "tiers": [
                    {"min": 0, "max": 40, "adjust": -8},
                    {"min": 70, "max": 85, "adjust": 8},
                    {"min": 85, "max": 100, "adjust": 15},
                ]
            },
            "stack",
        ),
        "Última hora": (
            "lead_time",
            {"last_minute": [{"max_days": 3, "adjust": -5}], "early_bird": []},
            "stack",
        ),
        "Sábados": ("day_of_week", {"sat": 8}, "stack"),
        "Festivos y puentes": ("holiday", {"adjust": 12, "include_bridges": True}, "stack"),
    }
    assert (
        PricingRule.objects.filter(property=ctx.properties["andino_mde"], room_types__isnull=False).count()
        == 0
    )


def test_the_cartagena_hotel_also_gets_the_music_festival_in_january(ctx, no_llm):
    seed(ctx)
    rules = rules_of(ctx.properties["aurora"])
    assert rules["Festival de Música de Cartagena"] == (
        "event",
        {"name": "Festival de Música de Cartagena", "start": "2027-01-07", "end": "2027-01-12", "adjust": 20},
        "stack",
    )
    assert "Festival de Música de Cartagena" not in rules_of(ctx.properties["andino_mde"])


def test_bounds_per_category_follow_its_default_price(ctx, no_llm):
    seed(ctx)
    bounds = {
        bound.room_type.code: (bound.rate_plan.code, bound.min_price, bound.max_price)
        for bound in PriceBounds.objects.filter(room_type__property=ctx.properties["aurora"])
    }
    # 75 % and 160 % of the default price, rounded to thousands of pesos
    assert bounds == {
        "DBL": ("FLEX", D("240000.00"), D("512000.00")),
        "STE": ("FLEX", D("488000.00"), D("1040000.00")),
    }


def test_an_initial_run_leaves_pending_recommendations_without_applying_them(ctx, no_llm):
    seed(ctx)
    for key in ("aurora", "andino_mde"):
        prop = ctx.properties[key]
        run = RevenueRun.objects.get(property=prop)
        assert (run.trigger, run.status, run.ai_provider) == ("seed", "success", "")
        pending = RateRecommendation.objects.filter(property=prop, status="pending")
        assert pending.count() == run.recommendations_count > 0
        assert RevenueSettings.objects.get(property=prop).auto_apply is False
    assert not DailyRate.objects.filter(source="revenue").exists()
    assert no_llm == []  # the demo never waits for (or spends) the LLM


def test_new_demo_rules_get_their_run_even_after_an_earlier_empty_run(ctx, no_llm):
    """The scheduled automation may run before the demo rules exist (0 recommendations): the seed still
    leaves pending recommendations for the rules it creates."""
    aurora = ctx.properties["aurora"]
    earlier = run_revenue(aurora, use_ai=False)
    assert earlier.recommendations_count == 0  # no rules yet
    seed(ctx)
    assert RevenueRun.objects.filter(property=aurora, trigger="seed").count() == 1
    assert RateRecommendation.objects.filter(property=aurora, status="pending").exists()


def test_properties_without_categories_or_plans_are_skipped(ctx, no_llm):
    seed(ctx)
    empty = ctx.properties["andino_bog"]
    assert not PricingRule.objects.filter(property=empty).exists()
    assert not RevenueRun.objects.filter(property=empty).exists()


def test_seeding_twice_creates_nothing_new(ctx, no_llm):
    seed(ctx)
    counts = (
        PricingRule.objects.count(),
        PriceBounds.objects.count(),
        RevenueRun.objects.count(),
        RateRecommendation.objects.count(),
    )
    seed(ctx)
    assert (
        PricingRule.objects.count(),
        PriceBounds.objects.count(),
        RevenueRun.objects.count(),
        RateRecommendation.objects.count(),
    ) == counts
