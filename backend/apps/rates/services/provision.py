"""Rate provisioning (plan §C): the rate setup of a new property (AI onboarding, signup, demo seed).

Idempotent: taxes and plans are matched by code, cancellation policies by their Spanish name and category
defaults by (category, plan); what already exists is never overwritten, so running it again only adds what
is missing.
"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.core import audit
from apps.core.errors import DomainError
from apps.core.money import D
from apps.inventory.models import RoomType
from apps.rates.models import CancellationPolicy, RatePlan, RoomTypeRateDefaults, Tax
from apps.rates.services.writes import emit_rates_changed

HORIZON_DAYS = 365
WEEKEND = ("fri", "sat")  # weekend nights of a Colombian hotel

DEFAULT_TAXES = [
    {
        "code": "IVA",
        "name": "IVA 19% alojamiento",
        "rate": Decimal("19.00"),
        "applies_to": Tax.AppliesTo.ROOM,
        "included_in_price": False,
        "exempt_foreign_non_residents": True,  # E.T. art. 481 lit. d
    },
    {
        "code": "IVA-EXTRAS",
        "name": "IVA 19% extras",
        "rate": Decimal("19.00"),
        "applies_to": Tax.AppliesTo.EXTRAS,
        "included_in_price": False,
        "exempt_foreign_non_residents": False,
    },
]

DEFAULT_POLICIES = {
    "flexible": {
        "name": {"es": "Flexible 48h", "en": "Flexible 48h"},
        "non_refundable": False,
        "free_until_hours_before": 48,
        "penalty_type": CancellationPolicy.PenaltyType.FIRST_NIGHT,
        "penalty_value": Decimal("0"),
        "description": {
            "es": "Cancelación gratis hasta 48 horas antes de la llegada; después se cobra la primera noche.",
            "en": "Free cancellation until 48 hours before arrival; after that the first night is charged.",
        },
    },
    "non_refundable": {
        "name": {"es": "No reembolsable", "en": "Non-refundable"},
        "non_refundable": True,
        "free_until_hours_before": 0,
        "penalty_type": CancellationPolicy.PenaltyType.FULL,
        "penalty_value": Decimal("0"),
        "description": {
            "es": "Precio especial sin cambios ni reembolsos: se cobra el total de la reserva.",
            "en": "Special price with no changes or refunds: the full stay is charged.",
        },
    },
}

DEFAULT_PLANS = [
    {
        "code": "FLEX",
        "name": {"es": "Tarifa flexible", "en": "Flexible rate"},
        "kind": "base",
        "cancellation_policy": "flexible",
        "sort_order": 10,
    },
    {
        "code": "NR",
        "name": {"es": "No reembolsable", "en": "Non-refundable"},
        "kind": "derived",
        "parent": "FLEX",
        "derivation_type": "percent",
        "derivation_value": "-12",
        "cancellation_policy": "non_refundable",
        "sort_order": 20,
    },
    {
        "code": "BB",
        "name": {"es": "Con desayuno", "en": "Breakfast included"},
        "kind": "derived",
        "parent": "FLEX",
        "derivation_type": "amount",
        "derivation_value": "35000",
        "meal_plan": "breakfast",
        "cancellation_policy": "flexible",
        "sort_order": 30,
    },
]

PLAN_FIELDS = ("meal_plan", "is_public", "channels", "deposit_percent", "min_los_default", "sort_order")


def provision_rates(
    property,
    *,
    room_type_prices: dict[str, dict],
    plans: list[dict] | None = None,
    taxes_default: bool = True,
    policies_default: bool = True,
    actor=None,
) -> None:
    """Create the rate setup of a new property (used by AI onboarding and signup).

    room_type_prices: {"DBL": {"price": "320000", "weekend_adjust_percent": 15,
                               "extra_adult_price": "60000", "extra_child_price": "30000"}}
    plans=None → "Tarifa flexible" (FLEX, base) + "No reembolsable" (NR, −12 %) + "Con desayuno" (BB,
    +35 000, breakfast). Custom plans: [{code, name{es,en}, kind "base"|"derived", parent (code),
    derivation_type, derivation_value, cancellation_policy "flexible"|"non_refundable"|None, meal_plan,
    is_public, channels, deposit_percent, min_los_default, sort_order}]; every plan sells every category
    of `room_type_prices` and base plans get their category defaults. Weekend adjust = Friday and Saturday
    nights.
    taxes_default → IVA 19 % on lodging (exempt for foreign non-residents, code IVA) + IVA 19 % on extras
    (code IVA-EXTRAS). policies_default → "Flexible 48h" and "No reembolsable".
    Nothing is written when a category code is unknown (`unknown_room_type`) or a price spec is invalid
    (`invalid_price` with `room_type`): price > 0, extras ≥ 0, single occupancy > 0, weekend % between −100
    and 1000, child age limit 0–17.
    """
    room_type_prices = {code: _clean_prices(code, values) for code, values in room_type_prices.items()}
    room_types = {rt.code: rt for rt in RoomType.objects.filter(property=property, code__in=room_type_prices)}
    unknown = sorted(set(room_type_prices) - set(room_types))
    if unknown:
        raise DomainError(
            f"Categorías inexistentes en la propiedad: {', '.join(unknown)}",
            code="unknown_room_type",
            codes=unknown,
        )
    ordered_types = [room_types[code] for code in room_type_prices]

    with transaction.atomic():
        if taxes_default:
            for spec in DEFAULT_TAXES:
                Tax.objects.get_or_create(property=property, code=spec["code"], defaults=spec)
        policies = {}
        if policies_default:
            for key, spec in DEFAULT_POLICIES.items():
                policies[key] = CancellationPolicy.objects.filter(
                    property=property, name__es=spec["name"]["es"]
                ).first() or CancellationPolicy.objects.create(property=property, **spec)

        created_plans = {}
        for spec in plans if plans is not None else DEFAULT_PLANS:
            plan = _plan(property, spec, created_plans, policies)
            plan.room_types.add(*ordered_types)
            created_plans[plan.code] = plan
            if plan.kind == RatePlan.Kind.BASE:
                for code, values in room_type_prices.items():
                    _defaults(room_types[code], plan, values)

        audit.record(
            action="rates.provisioned",
            target=property,
            property=property,
            actor=actor,
            source="user" if getattr(actor, "is_authenticated", False) else "system",
            summary=f"Tarifas iniciales: {len(created_plans)} planes para {len(ordered_types)} categorías",
            changes={"plans": list(created_plans), "room_types": list(room_type_prices)},
        )
        start = property.business_date
        base_plans = [plan for plan in created_plans.values() if plan.kind == RatePlan.Kind.BASE]
        emit_rates_changed(
            property,
            [rt.pk for rt in ordered_types],
            base_plans,
            start,
            start + timedelta(days=HORIZON_DAYS),
        )


def _plan(property, spec: dict, created: dict, policies: dict) -> RatePlan:
    existing = RatePlan.objects.filter(property=property, code=spec["code"]).first()
    if existing is not None:
        return existing
    derived = spec.get("kind", "base") == RatePlan.Kind.DERIVED
    parent = None
    if derived:
        parent = (
            created.get(spec.get("parent"))
            or RatePlan.objects.filter(
                property=property, code=spec.get("parent"), kind=RatePlan.Kind.BASE
            ).first()
        )
        if parent is None:
            raise DomainError(
                f"El plan {spec['code']} necesita un plan base existente", code="invalid_parent"
            )
    values = {field: spec[field] for field in PLAN_FIELDS if field in spec}
    return RatePlan.objects.create(
        property=property,
        code=spec["code"],
        name=spec.get("name") or {"es": spec["code"], "en": spec["code"]},
        kind=RatePlan.Kind.DERIVED if derived else RatePlan.Kind.BASE,
        parent=parent,
        derivation_type=spec.get("derivation_type", RatePlan.DerivationType.PERCENT),
        derivation_value=D(spec.get("derivation_value", 0)) if derived else Decimal("0"),
        cancellation_policy=policies.get(spec.get("cancellation_policy")),
        **values,
    )


def _number(value) -> Decimal | None:
    """Finite Decimal from a number or numeric string; None when missing (None, "") or not a number."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        number = D(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _clean_prices(code: str, values) -> dict:
    """Validated price spec of one category (Decimal amounts); `invalid_price` otherwise."""
    values = dict(values or {})

    def invalid(message: str) -> DomainError:
        return DomainError(f"Precios de {code}: {message}", code="invalid_price", room_type=code)

    price = _number(values.get("price"))
    if price is None or price <= 0:
        raise invalid("el precio por noche debe ser un número mayor que cero")
    clean = {"price": price}
    for key in ("extra_adult_price", "extra_child_price"):
        raw = values.get(key)
        amount = Decimal("0") if raw in (None, "") else _number(raw)
        if amount is None or amount < 0:
            raise invalid("los precios de persona adicional no pueden ser negativos")
        clean[key] = amount
    raw = values.get("single_occupancy_price")
    single = None if raw in (None, "") else _number(raw)
    if raw not in (None, "") and (single is None or single <= 0):
        raise invalid("el precio de ocupación sencilla debe ser mayor que cero")
    clean["single_occupancy_price"] = single
    raw = values.get("weekend_adjust_percent")
    weekend = None if raw in (None, "") else _number(raw)
    if raw not in (None, "") and (weekend is None or not Decimal("-100") <= weekend <= Decimal("1000")):
        raise invalid("el ajuste de fin de semana debe ser un porcentaje entre -100 y 1000")
    clean["weekend_adjust_percent"] = weekend
    age = values.get("child_age_limit", 12)
    if isinstance(age, bool) or not isinstance(age, int) or not 0 <= age <= 17:
        raise invalid("la edad límite de los niños va de 0 a 17 años")
    clean["child_age_limit"] = age
    return clean


def _defaults(room_type, plan, values: dict) -> None:
    """Category defaults of a base plan from a spec validated by `_clean_prices` (never overwritten)."""
    adjustments = {}
    weekend = values["weekend_adjust_percent"]
    if weekend:  # JSON: whole percentages as int, others as float (like the defaults API)
        percent = int(weekend) if weekend == weekend.to_integral_value() else float(weekend)
        adjustments = {day: percent for day in WEEKEND}
    RoomTypeRateDefaults.objects.get_or_create(
        room_type=room_type,
        rate_plan=plan,
        defaults={
            "price": values["price"],
            "dow_adjustments": adjustments,
            "extra_adult_price": values["extra_adult_price"],
            "extra_child_price": values["extra_child_price"],
            "child_age_limit": values["child_age_limit"],
            "single_occupancy_price": values["single_occupancy_price"],
        },
    )
