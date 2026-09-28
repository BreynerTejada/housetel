"""Plans: the catalog (spec §5 C11) and which plan fits an organization."""

from decimal import Decimal

from django.db.models import Count, Q

from apps.core.money import quantize
from apps.saas.models import Plan

YEARLY_DISCOUNT_PERCENT = Decimal("15")


def yearly_price(monthly) -> Decimal:
    """12 months with the yearly discount (−15 %), rounded to whole pesos."""
    return quantize(Decimal(monthly) * 12 * (100 - YEARLY_DISCOUNT_PERCENT) / 100)


DEFAULT_PLANS = [
    {
        "code": "starter",
        "name": {"es": "Starter", "en": "Starter"},
        "description": {
            "es": "Para hostales y hoteles pequeños de hasta 15 habitaciones o camas.",
            "en": "For hostels and small hotels with up to 15 rooms or beds.",
        },
        "max_units": 15,
        "max_properties": 1,
        "price_monthly": Decimal("149000"),
        "sort": 10,
    },
    {
        "code": "pro",
        "name": {"es": "Pro", "en": "Pro"},
        "description": {
            "es": "Para hoteles medianos de hasta 60 unidades, con todo incluido.",
            "en": "For mid-sized hotels with up to 60 units, everything included.",
        },
        "max_units": 60,
        "max_properties": 2,
        "price_monthly": Decimal("349000"),
        "sort": 20,
    },
    {
        "code": "cadena",
        "name": {"es": "Cadena", "en": "Chain"},
        "description": {
            "es": "Unidades y propiedades ilimitadas para cadenas y grupos hoteleros.",
            "en": "Unlimited units and properties for hotel chains and groups.",
        },
        "max_units": None,
        "max_properties": None,
        "price_monthly": Decimal("899000"),
        "sort": 30,
    },
]


def ensure_default_plans() -> dict[str, Plan]:
    """Create the default plans when missing (never overwrites prices the admin changed)."""
    plans: dict[str, Plan] = {}
    for spec in DEFAULT_PLANS:
        values = dict(spec)
        values["price_yearly"] = yearly_price(values["price_monthly"])
        code = values.pop("code")
        plan, _ = Plan.objects.get_or_create(code=code, defaults=values)
        plans[code] = plan
    return plans


def active_plans():
    return Plan.objects.filter(is_active=True).order_by("sort", "price_monthly")


def plan_fits(plan: Plan, *, units: int, properties: int = 1) -> bool:
    return (plan.max_units is None or units <= plan.max_units) and (
        plan.max_properties is None or properties <= plan.max_properties
    )


def plan_for_units(units: int, properties: int = 1) -> Plan:
    """Smallest active plan that fits the size (the unlimited plan when nothing smaller fits)."""
    plans = list(active_plans())
    if not plans:
        plans = list(ensure_default_plans().values())
    for plan in plans:
        if plan_fits(plan, units=units, properties=properties):
            return plan
    unlimited = [p for p in plans if p.max_units is None]
    return unlimited[-1] if unlimited else plans[-1]


def plans_with_counts():
    return Plan.objects.annotate(
        subscriptions_count=Count("subscriptions", distinct=True),
        active_subscriptions_count=Count(
            "subscriptions",
            filter=Q(subscriptions__status__in=["trialing", "active", "past_due"]),
            distinct=True,
        ),
    ).order_by("sort", "price_monthly")
