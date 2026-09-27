"""Fixtures of the rates tests: a Colombian hotel with one double category priced by a base plan."""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.tests.factories import RatePlanFactory, RoomTypeRateDefaultsFactory, TaxFactory


def oct_(day: int) -> date:
    """2026-10-01 is a Thursday; 2026-10-12 (Día de la Raza) a Monday."""
    return date(2026, 10, 1) + timedelta(days=day - 1)


@pytest.fixture
def rates(prop):
    """DBL (base occupancy 2) in the base plan FLEX: 320.000 by default, extra adult 60.000, child 30.000
    (≤ 12 years), IVA 19 % not included and exempt for foreign non-residents."""
    room_type = RoomTypeFactory(
        property=prop, code="DBL", base_occupancy=2, max_adults=3, max_children=2, max_occupancy=4
    )
    plan = RatePlanFactory(property=prop, code="FLEX", room_types=[room_type])
    defaults = RoomTypeRateDefaultsFactory(
        room_type=room_type,
        rate_plan=plan,
        price=Decimal("320000"),
        extra_adult_price=Decimal("60000"),
        extra_child_price=Decimal("30000"),
        child_age_limit=12,
    )
    tax = TaxFactory(
        property=prop,
        code="IVA",
        rate=Decimal("19.00"),
        applies_to="room",
        included_in_price=False,
        exempt_foreign_non_residents=True,
    )
    return SimpleNamespace(prop=prop, room_type=room_type, plan=plan, defaults=defaults, tax=tax)
