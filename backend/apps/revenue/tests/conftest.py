"""Fixtures of the revenue tests: a hotel whose business date is Thursday 2026-10-01, one category DBL with
10 rooms priced 300.000 by default in the base plan FLEX (plus the derived NR, −12 %).

2026-10-12 is a Monday holiday (Día de la Raza): Saturday 10 and Sunday 11 are its long weekend.
The LLM is always faked here: the real client (C9) must never be called from these tests."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.ai.types import LLMResult
from apps.bookings.models import InventoryDay
from apps.bookings.services.inventory import rebuild_inventory
from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory
from apps.rates.tests.factories import DerivedRatePlanFactory, RatePlanFactory, RoomTypeRateDefaultsFactory
from apps.revenue.models import PricingRule, RevenueSettings

BUSINESS_DATE = date(2026, 10, 1)


def oct_(day: int) -> date:
    return date(2026, 10, 1) + timedelta(days=day - 1)


class FakeLLM:
    """Records the prompts; answers like a real provider would (or like the simulated one)."""

    def __init__(self, *, data=None, text="", simulated=False, provider="fake", error=None):
        self.calls = []
        self.data, self.text, self.simulated, self.provider, self.error = (
            data,
            text,
            simulated,
            provider,
            error,
        )

    def generate(self, messages, *, system=None, tools=None, response_schema=None, temperature=0.2):
        self.calls.append({"messages": messages, "system": system, "response_schema": response_schema})
        if self.error is not None:
            raise self.error
        return LLMResult(
            text=self.text, data=self.data, provider=self.provider, model="m", simulated=self.simulated
        )


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    """Default: the simulated provider (its text is not a summary, so the template is kept)."""
    llm = FakeLLM(text="(modo simulado) …", simulated=True, provider="simulated")
    monkeypatch.setattr("apps.revenue.services.summary.get_llm", lambda property=None: llm)
    return llm


@pytest.fixture
def hotel(prop):
    prop.business_date = BUSINESS_DATE
    prop.save(update_fields=["business_date"])
    room_type = RoomTypeFactory(property=prop, code="DBL", sort_order=1)
    for number in range(101, 111):
        RoomFactory(room_type=room_type, number=str(number))
    plan = RatePlanFactory(property=prop, code="FLEX", room_types=[room_type])
    derived = DerivedRatePlanFactory(property=prop, code="NR", parent=plan, room_types=[room_type])
    RoomTypeRateDefaultsFactory(room_type=room_type, rate_plan=plan, price=Decimal("300000"))
    rebuild_inventory(prop, BUSINESS_DATE, BUSINESS_DATE + timedelta(days=130))
    settings = RevenueSettings.objects.create(property=prop)
    return SimpleNamespace(prop=prop, room_type=room_type, plan=plan, derived=derived, settings=settings)


def sell(room_type, day: date, sold: int, *, total: int = 10, blocked: int = 0) -> None:
    """On-the-books position of one night (the rows exist: the fixture materialized them)."""
    updated = InventoryDay.objects.filter(room_type=room_type, date=day).update(
        sold_units=sold, total_units=total, blocked_units=blocked
    )
    assert updated == 1


def make_rule(prop, kind, params, *, name=None, combine="stack", priority=10, room_types=None, active=True):
    from apps.revenue.rules import clean_params

    rule = PricingRule.objects.create(
        property=prop,
        name=name or kind,
        kind=kind,
        params=clean_params(kind, params),
        combine=combine,
        priority=priority,
        is_active=active,
    )
    if room_types:
        rule.room_types.set(room_types)
    return rule
