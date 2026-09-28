"""ARI values of one category for one connection (plan C3 › Salida).

- Availability per night = `bookings.availability_by_date` (InventoryDay), never below 0; an inactive category
  sells 0.
- Per rate mapping that applies to the category: the plan price per night from `rates.resolve_daily` (derived
  plans resolved), rounded like a quote, then × (1 + markup/100) and rounded to the currency. Restrictions
  come from the base plan rows; a night without its own minimum stay takes the mapped plan's `min_los_default`
  when it is above 1.
- A rate the channel must not sell is sent closed (stop-sell, no price): deleted plan, inactive, not public,
  not enabled for this channel (`RatePlan.channels`), not selling the category, or a night without price.
"""

from datetime import date

from apps.bookings.services.availability import availability_by_date
from apps.core.dates import daterange
from apps.core.money import apply_percent, quantize
from apps.distribution.types import AriBatch, AriRate, AriRateDay
from apps.rates.services.quote import resolve_daily


def channel_price(price, markup_percent, currency: str = "COP"):
    """Plan price of a night as the channel sells it: rounded like a quote, plus the markup, rounded."""
    return quantize(apply_percent(quantize(price, currency), markup_percent), currency)


def sellable_on(plan, room_type, channel_code: str) -> bool:
    """The plan may be sold for this category on this channel (same rules as `search_offers` for any channel
    other than direct: active, public, and the channel listed in `plan.channels` or the list empty)."""
    if plan is None or not plan.is_active or not plan.is_public or not room_type.is_active:
        return False
    if plan.channels and channel_code not in plan.channels:
        return False
    return room_type.pk in {item.pk for item in plan.room_types.all()}


def build_batch(connection, room_type, start: date, end: date, kinds) -> AriBatch:
    """Current ARI of `room_type` over `[start, end)` for `connection` (see the module docstring)."""
    prop = connection.property
    currency = prop.currency or "COP"
    mapping = next(
        (
            item
            for item in connection.room_mappings.all()
            if item.room_type_id == room_type.pk and not item.room_id
        ),
        None,
    )
    by_date = availability_by_date(property=prop, start=start, end=end, room_type_ids=[room_type.pk])
    units = by_date.get(room_type.pk, {})
    availability = {day: max(int(units.get(day, 0)), 0) for day in daterange(start, end)}
    rates = [
        _rate(connection, rate_mapping, room_type, start, end, currency)
        for rate_mapping in connection.rate_mappings.all()
        if rate_mapping.room_type_id in (None, room_type.pk)
    ]
    return AriBatch(
        connection_id=connection.pk,
        room_type_id=room_type.pk,
        room_type_code=room_type.code,
        external_room_id=mapping.external_room_id if mapping is not None else "",
        start=start,
        end=end,
        kinds=tuple(sorted(set(kinds))),
        availability=availability,
        rates=rates,
    )


def _rate(connection, rate_mapping, room_type, start, end, currency) -> AriRate:
    plan = rate_mapping.rate_plan
    markup = rate_mapping.markup_percent
    if not sellable_on(plan, room_type, connection.channel_code):
        days = [_closed(day) for day in daterange(start, end)]
    else:
        default_min_los = plan.min_los_default if plan.min_los_default and plan.min_los_default > 1 else None
        days = []
        for day in resolve_daily(room_type, plan, start, end):
            price = None if day.source == "none" else channel_price(day.price, markup, currency)
            days.append(
                AriRateDay(
                    date=day.date,
                    price=price,
                    min_los=day.min_los if day.min_los is not None else default_min_los,
                    max_los=day.max_los,
                    closed_to_arrival=day.closed_to_arrival,
                    closed_to_departure=day.closed_to_departure,
                    stop_sell=day.stop_sell or price is None,
                )
            )
    return AriRate(
        external_rate_id=rate_mapping.external_rate_id,
        rate_plan_id=plan.pk if plan is not None else None,
        markup_percent=markup,
        days=days,
    )


def _closed(day: date) -> AriRateDay:
    return AriRateDay(
        date=day,
        price=None,
        min_los=None,
        max_los=None,
        closed_to_arrival=False,
        closed_to_departure=False,
        stop_sell=True,
    )
