"""Demo seed of `revenue` (plan C8 › Seed), idempotent. Per property with categories and an active base plan:

- revenue settings with the defaults (auto-apply off);
- the default rules: occupancy 0–40 % → −8 %, 70–85 % → +8 %, 85–100 % → +15 %; last minute (≤ 3 days)
  −5 %; Saturdays +8 %; holidays and long weekends +12 %; and, for the hotels in Cartagena, the "Festival de
  Música de Cartagena" in January (+20 %). Created only when the property has no rules yet;
- price bounds per category of each base plan: 75 %–160 % of its default price, rounded to thousands;
- one initial run (trigger "seed", no LLM) that leaves pending recommendations, if the property has no seed
  run yet.

Runs after bookings (it reads the on-the-books occupancy of InventoryDay) and rates (plans and defaults).
"""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from apps.rates.models import RatePlan, RoomTypeRateDefaults
from apps.revenue.models import PriceBounds, PricingRule, RevenueRun
from apps.revenue.rules import clean_params
from apps.revenue.services.config import get_settings
from apps.revenue.services.runs import run_revenue

FESTIVAL = "Festival de Música de Cartagena"
BOUNDS = (Decimal("0.75"), Decimal("1.60"))
THOUSAND = Decimal("1000")

DEFAULT_RULES = [
    {
        "name": "Ocupación",
        "kind": "occupancy",
        "priority": 40,
        "params": {
            "tiers": [
                {"min": 0, "max": 40, "adjust": -8},
                {"min": 70, "max": 85, "adjust": 8},
                {"min": 85, "max": 100, "adjust": 15},
            ]
        },
    },
    {"name": "Festivos y puentes", "kind": "holiday", "priority": 20, "params": {"adjust": 12}},
    {
        "name": "Última hora",
        "kind": "lead_time",
        "priority": 15,
        "params": {"last_minute": [{"max_days": 3, "adjust": -5}]},
    },
    {"name": "Sábados", "kind": "day_of_week", "priority": 10, "params": {"sat": 8}},
]


def seed(ctx) -> None:
    for prop in ctx.properties.values():
        plans = list(RatePlan.objects.filter(property=prop, kind=RatePlan.Kind.BASE, is_active=True))
        if not plans or not prop.room_types.filter(is_active=True).exists():
            ctx.log(f"  revenue: {prop.name} sin categorías o planes base, se omite")
            continue
        get_settings(prop)
        rules = _rules(prop, ctx.today)
        bounds = _bounds(prop, plans)
        run = None
        if not RevenueRun.objects.filter(property=prop, trigger=RevenueRun.Trigger.SEED).exists():
            run = run_revenue(prop, trigger=RevenueRun.Trigger.SEED, use_ai=False)
        ctx.log(
            f"  revenue: {prop.name} · {rules} reglas nuevas, {bounds} límites nuevos"
            + (f", {run.recommendations_count} recomendaciones pendientes" if run else "")
        )


def festival_dates(today: date) -> tuple[date, date]:
    """Next edition (still running or upcoming) of the January festival; the end is inclusive."""
    year = today.year if today <= date(today.year, 1, 12) else today.year + 1
    return date(year, 1, 7), date(year, 1, 12)


def _rules(prop, today) -> int:
    if PricingRule.objects.filter(property=prop).exists():
        return 0
    specs = list(DEFAULT_RULES)
    if (prop.city or "").strip().lower() == "cartagena":
        start, end = festival_dates(today)
        specs.append(
            {
                "name": FESTIVAL,
                "kind": "event",
                "priority": 30,
                "params": {
                    "name": FESTIVAL,
                    "start": start.isoformat(),
                    "end": end.isoformat(),
                    "adjust": 20,
                },
            }
        )
    for spec in specs:
        PricingRule.objects.create(
            property=prop,
            name=spec["name"],
            kind=spec["kind"],
            priority=spec["priority"],
            params=clean_params(spec["kind"], spec["params"]),
        )
    return len(specs)


def _bounds(prop, plans) -> int:
    created = 0
    defaults = RoomTypeRateDefaults.objects.filter(
        rate_plan__in=plans, room_type__property=prop, room_type__is_active=True
    )
    for row in defaults.select_related("room_type", "rate_plan"):
        low, high = (_thousands(row.price * factor) for factor in BOUNDS)
        _, was_created = PriceBounds.objects.get_or_create(
            room_type=row.room_type, rate_plan=row.rate_plan, defaults={"min_price": low, "max_price": high}
        )
        created += was_created
    return created


def _thousands(value: Decimal) -> Decimal:
    return (value / THOUSAND).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * THOUSAND
