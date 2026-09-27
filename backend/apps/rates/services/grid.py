"""Read model of the rate grid (`GET /api/v1/rates/grid/`): categories × nights of one plan.

Prices come from `resolve_daily` (derived plans show derived prices and are read-only); availability per
night is what the bookings contract `availability(checkin=d, checkout=d+1)` answers (see
`daily_availability`). Money is rendered as two-decimal strings rounded to the property currency; a night
without any configured price has `price: null` and `source: "none"`.
"""

from datetime import date, timedelta
from decimal import Decimal

from apps.bookings.models import InventoryDay
from apps.bookings.services.availability import availability
from apps.core.dates import daterange
from apps.core.money import D, quantize
from apps.rates.models import RatePlan
from apps.rates.services.calendar import holiday_list
from apps.rates.services.quote import resolve_daily

CENTS = Decimal("0.01")


def money(value, currency: str) -> str:
    return format(quantize(value, currency).quantize(CENTS), "f")


def default_plan(property) -> RatePlan | None:
    """The first active base plan (sort order, then code)."""
    return RatePlan.objects.filter(property=property, kind=RatePlan.Kind.BASE, is_active=True).first()


def plan_payload(plan: RatePlan) -> dict:
    return {
        "id": str(plan.pk),
        "code": plan.code,
        "name": plan.name,
        "kind": plan.kind,
        "parent": str(plan.parent_id) if plan.parent_id else None,
        "derivation_type": plan.derivation_type,
        "derivation_value": format(D(plan.derivation_value).quantize(CENTS), "f"),
        "editable": plan.kind == RatePlan.Kind.BASE,
    }


def daily_availability(property, room_type_ids: list, dates: list[date]) -> dict[date, dict]:
    """`{date: {room_type_id: units}}`: the units `availability()` gives for each single night.

    One call to the bookings contract over the whole range keeps those nights materialized in `InventoryDay`
    (B2b builds the missing rows there); each night is then read from its row (reading another app's models
    through the ORM is allowed, plan §B). Same numbers as one contract call per night, in a constant number
    of queries (a 90-night range never seen used to take ~4 s). Negative when a category is overbooked.
    """
    result: dict[date, dict] = {day: {} for day in dates}
    if not room_type_ids or not dates:
        return result
    start, end = dates[0], dates[-1] + timedelta(days=1)
    availability(property=property, checkin=start, checkout=end, room_type_ids=room_type_ids)
    rows = InventoryDay.objects.filter(room_type_id__in=room_type_ids, date__gte=start, date__lt=end).only(
        "room_type_id", "date", "total_units", "sold_units", "blocked_units"
    )
    for row in rows:
        result[row.date][row.room_type_id] = row.available
    return result


def build_grid(property, *, rate_plan: RatePlan | None, start: date, end: date, lang: str = "es") -> dict:
    currency = property.currency or "COP"
    dates = list(daterange(start, end))
    payload = {
        "rate_plan": plan_payload(rate_plan) if rate_plan else None,
        "currency": currency,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "dates": [day.isoformat() for day in dates],
        "holidays": holiday_list(start, end, lang),
        "room_types": [],
    }
    if rate_plan is None:
        return payload
    room_types = list(rate_plan.room_types.filter(is_active=True).order_by("sort_order", "code"))
    units = daily_availability(property, [rt.pk for rt in room_types], dates)
    for room_type in room_types:
        rows = []
        for day in resolve_daily(room_type, rate_plan, start, end):
            rows.append(
                {
                    "date": day.date.isoformat(),
                    "price": None if day.source == "none" else money(day.price, currency),
                    "extra_adult_price": money(day.extra_adult_price, currency),
                    "extra_child_price": money(day.extra_child_price, currency),
                    "min_los": day.min_los,
                    "max_los": day.max_los,
                    "cta": day.closed_to_arrival,
                    "ctd": day.closed_to_departure,
                    "stop_sell": day.stop_sell,
                    "source": day.source,
                    "available": units[day.date].get(room_type.pk),
                }
            )
        payload["room_types"].append(
            {
                "id": str(room_type.pk),
                "code": room_type.code,
                "name": room_type.name,
                "color": room_type.color,
                "kind": room_type.kind,
                "rows": rows,
            }
        )
    return payload
