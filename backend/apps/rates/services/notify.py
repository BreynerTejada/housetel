"""`rates_changed` for configuration changes that move prices (plans, category defaults, seasons).

Changes that affect every future night (plans, defaults) announce the horizon `[business_date,
business_date + 365)`; season changes announce the season's own nights. `rate_plan_ids` always lists the
base plan followed by its derived plans (their prices follow the base plan).
"""

from datetime import date, timedelta

from apps.core import signals
from apps.rates.models import RatePlan
from apps.rates.services.writes import emit_rates_changed

HORIZON_DAYS = 365


def horizon(property) -> tuple[date, date]:
    start = property.business_date
    return start, start + timedelta(days=HORIZON_DAYS)


def announce_plan(plan: RatePlan) -> None:
    start, end = horizon(plan.property)
    room_type_ids = list(plan.room_types.values_list("pk", flat=True))
    if plan.kind == RatePlan.Kind.BASE:
        emit_rates_changed(plan.property, room_type_ids, [plan], start, end)
        return
    signals.send_on_commit(
        signals.rates_changed,
        property=plan.property,
        room_type_ids=room_type_ids,
        rate_plan_ids=[plan.pk],
        start=start,
        end=end,
    )


def announce_defaults(defaults) -> None:
    plan = defaults.rate_plan
    start, end = horizon(plan.property)
    emit_rates_changed(plan.property, [defaults.room_type_id], [plan], start, end)


def announce_season(season, *, also_start: date | None = None, also_end: date | None = None) -> None:
    """Nights of the season (plus a previous range when its dates moved), for its categories and plans."""
    rates = list(season.rates.select_related("rate_plan"))
    if not rates:
        return
    start = min(filter(None, [season.start_date, also_start]))
    last = max(filter(None, [season.end_date, also_end]))
    room_type_ids = list(dict.fromkeys(rate.room_type_id for rate in rates))
    plans = list({rate.rate_plan_id: rate.rate_plan for rate in rates}.values())
    emit_rates_changed(season.property, room_type_ids, plans, start, last + timedelta(days=1))


def announce_season_rate(rate) -> None:
    season = rate.season
    emit_rates_changed(
        season.property,
        [rate.room_type_id],
        [rate.rate_plan],
        season.start_date,
        season.end_date + timedelta(days=1),
    )
