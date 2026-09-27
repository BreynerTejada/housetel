"""Price resolution of a BASE plan, night by night (plan B2a, quote step 3).

For each date: the `DailyRate` row (materialized grid) → the `SeasonRate` of the active season with the
highest priority (a season is active from `start_date` to `end_date`, both inclusive) adjusted by its
weekday percentages → the `RoomTypeRateDefaults` price adjusted by its weekday percentages → no price
(`source="none"`).

A row whose source is `default` or `season` (`FOLLOWING_SOURCES`) was materialized only to hold restrictions:
nobody set its price, so its price keeps following the season/defaults of today (a season created, edited
or deleted later, a new default price). Only when neither exists any more does it keep its stored price.
Rows with a price of their own (`manual`, `bulk`, `revenue`, `channel`) are the exact price of that date.

Weekday adjustments are percentages keyed `mon…sun` (`{"fri": 10, "sat": 15}`). Rows with a price of their
own never get weekday adjustments. Prices are returned unrounded; callers round with
`apps.core.money.quantize`. Extra adult/child prices come from the row when set, else from the defaults.
"""

from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation

from apps.core.dates import daterange
from apps.core.money import D, apply_percent
from apps.rates.models import DailyRate, RoomTypeRateDefaults, SeasonRate
from apps.rates.types import DayRate

ZERO = Decimal("0")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
NO_DEFAULTS = object()
FOLLOWING_SOURCES = ("default", "season")  # rows without a price of their own (see the module docstring)


def load_defaults(room_type, base_plan) -> RoomTypeRateDefaults | None:
    return RoomTypeRateDefaults.objects.filter(room_type=room_type, rate_plan=base_plan).first()


def weekday_percent(adjustments, day: date) -> Decimal:
    """The percentage of `day`'s weekday in a `{"mon": 0, …}` mapping (0 when missing or malformed)."""
    if not isinstance(adjustments, dict):
        return ZERO
    try:
        return D(adjustments.get(WEEKDAYS[day.weekday()]) or 0)
    except (InvalidOperation, TypeError, ValueError):
        return ZERO


def with_weekday(price, adjustments, day: date) -> Decimal:
    percent = weekday_percent(adjustments, day)
    return apply_percent(price, percent) if percent else D(price)


def season_rates_for(room_type, base_plan, start: date, end: date) -> list[SeasonRate]:
    """Season rates of `(room_type, base_plan)` whose season overlaps `[start, end)`, best first:
    higher priority, then the most recent start, then a stable id order."""
    rates = SeasonRate.objects.filter(
        room_type=room_type,
        rate_plan=base_plan,
        season__start_date__lt=end,
        season__end_date__gte=start,
    ).select_related("season")
    return sorted(rates, key=lambda r: (-r.season.priority, -r.season.start_date.toordinal(), str(r.pk)))


def active_season_rate(season_rates: Iterable[SeasonRate], day: date) -> SeasonRate | None:
    return next((r for r in season_rates if r.season.start_date <= day <= r.season.end_date), None)


def configured_price(season_rates: Iterable[SeasonRate], defaults, day: date) -> tuple[Decimal, str] | None:
    """`(price, source)` of `day` from the configuration alone: the active season rate, else the category
    defaults (both with their weekday %); None when neither exists."""
    season_rate = active_season_rate(season_rates, day)
    if season_rate is not None:
        return with_weekday(season_rate.price, season_rate.dow_adjustments, day), "season"
    if defaults is not None:
        return with_weekday(defaults.price, defaults.dow_adjustments, day), "default"
    return None


def resolve_base_days(room_type, base_plan, start: date, end: date, *, defaults=NO_DEFAULTS) -> list[DayRate]:
    """One `DayRate` per date of `[start, end)` for a BASE plan (see the module docstring)."""
    if defaults is NO_DEFAULTS:
        defaults = load_defaults(room_type, base_plan)
    rows = {
        row.date: row
        for row in DailyRate.objects.filter(
            room_type=room_type, rate_plan=base_plan, date__gte=start, date__lt=end
        )
    }
    seasons = season_rates_for(room_type, base_plan, start, end)
    default_adult = defaults.extra_adult_price if defaults else ZERO
    default_child = defaults.extra_child_price if defaults else ZERO

    days = []
    for day in daterange(start, end):
        row = rows.get(day)
        configured = configured_price(seasons, defaults, day)
        if row is not None:
            price, source = row.price, row.source
            if row.source in FOLLOWING_SOURCES and configured is not None:
                price, source = configured
            days.append(
                DayRate(
                    date=day,
                    price=price,
                    extra_adult_price=default_adult
                    if row.extra_adult_price is None
                    else row.extra_adult_price,
                    extra_child_price=default_child
                    if row.extra_child_price is None
                    else row.extra_child_price,
                    min_los=row.min_los,
                    max_los=row.max_los,
                    closed_to_arrival=row.closed_to_arrival,
                    closed_to_departure=row.closed_to_departure,
                    stop_sell=row.stop_sell,
                    source=source,
                )
            )
            continue
        price, source = configured if configured is not None else (ZERO, "none")
        days.append(
            DayRate(
                date=day,
                price=price,
                extra_adult_price=default_adult,
                extra_child_price=default_child,
                min_los=None,
                max_los=None,
                closed_to_arrival=False,
                closed_to_departure=False,
                stop_sell=False,
                source=source,
            )
        )
    return days
