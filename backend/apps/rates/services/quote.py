"""Quote engine — contracts fixed in Phase A (spec §4.2); B2a completes the algorithm (plan B2a).

Phase A level (plan Step 5):
- price per night: `DailyRate` of the BASE plan → `RoomTypeRateDefaults.price` → 0 (with a `no_rate` warning);
- derived plans: parent price ± percent/amount (never below 0);
- taxes: active `Tax` with `applies_to` room/all. Excluded taxes add up; included ones are informative lines;
  foreign non-residents get an `exempt=True` zero line when the tax allows it;
- `stop_sell` on any night → restriction violation.
Not yet: seasons, weekday adjustments, occupancy extras, single occupancy, promos, CTA/CTD/LOS (B2a).

Ranges are half-open: `[start, end)`; for a stay, `[checkin, checkout)`.
"""

from dataclasses import replace
from decimal import Decimal

from django.db import transaction

from apps.core import signals
from apps.core.dates import daterange
from apps.core.dates import nights as stay_nights
from apps.core.errors import DomainError
from apps.core.money import D, apply_percent, quantize
from apps.rates.models import DailyRate, RatePlan, RoomTypeRateDefaults, Tax
from apps.rates.types import DayRate, NightPrice, Quote, TaxLine

ZERO = Decimal("0")
RESTRICTION_FIELDS = frozenset(
    {"min_los", "max_los", "closed_to_arrival", "closed_to_departure", "stop_sell"}
)
PRICE_DELTAS = frozenset({"price_delta_percent", "price_delta_amount"})
ROOM_TAX_SCOPES = ("room", "all")


def quote(
    *,
    property,
    room_type,
    rate_plan,
    checkin,
    checkout,
    adults,
    children=0,
    children_ages=None,
    promo_code=None,
    guest_is_foreign_non_resident=False,
) -> Quote:
    currency = property.currency or "COP"
    common = {
        "room_type_id": room_type.pk,
        "rate_plan_id": rate_plan.pk,
        "checkin": checkin,
        "checkout": checkout,
        "adults": adults,
        "children": children,
        "currency": currency,
    }
    if not stay_nights(checkin, checkout):
        return Quote(
            **common,
            nights=[],
            subtotal=ZERO,
            discount_total=ZERO,
            taxes=[],
            tax_total=ZERO,
            total=ZERO,
            restrictions_ok=False,
            violations=["invalid_dates"],
        )

    days = resolve_daily(room_type, rate_plan, checkin, checkout)
    nights = []
    for day in days:
        price = quantize(day.price, currency)
        nights.append(
            NightPrice(
                date=day.date, base=price, extra_adults=ZERO, extra_children=ZERO, discount=ZERO, total=price
            )
        )
    restriction_violations = ["stop_sell"] if any(day.stop_sell for day in days) else []
    warnings = ["no_rate"] if any(day.source == "none" for day in days) else []

    subtotal = quantize(sum((night.total for night in nights), ZERO), currency)
    taxes, tax_total = _room_taxes(property, subtotal, guest_is_foreign_non_resident, currency)
    return Quote(
        **common,
        nights=nights,
        subtotal=subtotal,
        discount_total=ZERO,
        taxes=taxes,
        tax_total=tax_total,
        total=subtotal + tax_total,
        restrictions_ok=not restriction_violations,
        violations=restriction_violations + warnings,
        promo_applied=None,
    )


def resolve_daily(room_type, rate_plan, start, end) -> list[DayRate]:
    """Effective price and restrictions for each night in `[start, end)`.

    Rows come from the plan's base plan; a derived plan returns derived (unrounded) prices with the
    base plan's restrictions. `source` is the DailyRate source, "default" (RoomTypeRateDefaults) or
    "none" (no price configured).
    """
    base_plan = rate_plan.base_plan
    rows = {
        row.date: row
        for row in DailyRate.objects.filter(
            room_type=room_type, rate_plan=base_plan, date__gte=start, date__lt=end
        )
    }
    defaults = RoomTypeRateDefaults.objects.filter(room_type=room_type, rate_plan=base_plan).first()
    default_adult = defaults.extra_adult_price if defaults else ZERO
    default_child = defaults.extra_child_price if defaults else ZERO

    days = []
    for day in daterange(start, end):
        row = rows.get(day)
        if row is not None:
            day_rate = DayRate(
                date=day,
                price=row.price,
                extra_adult_price=row.extra_adult_price
                if row.extra_adult_price is not None
                else default_adult,
                extra_child_price=row.extra_child_price
                if row.extra_child_price is not None
                else default_child,
                min_los=row.min_los,
                max_los=row.max_los,
                closed_to_arrival=row.closed_to_arrival,
                closed_to_departure=row.closed_to_departure,
                stop_sell=row.stop_sell,
                source=row.source,
            )
        elif defaults is not None:
            day_rate = DayRate(
                date=day,
                price=defaults.price,
                extra_adult_price=default_adult,
                extra_child_price=default_child,
                min_los=None,
                max_los=None,
                closed_to_arrival=False,
                closed_to_departure=False,
                stop_sell=False,
                source="default",
            )
        else:
            day_rate = DayRate(
                date=day,
                price=ZERO,
                extra_adult_price=ZERO,
                extra_child_price=ZERO,
                min_los=None,
                max_los=None,
                closed_to_arrival=False,
                closed_to_departure=False,
                stop_sell=False,
                source="none",
            )
        if rate_plan.kind == RatePlan.Kind.DERIVED and day_rate.source != "none":
            day_rate = replace(day_rate, price=derive_price(day_rate.price, rate_plan))
        days.append(day_rate)
    return days


def set_daily_rates(
    *,
    property,
    room_type,
    rate_plan,
    start,
    end,
    price=None,
    restrictions=None,
    dow=None,
    source="manual",
    actor=None,
) -> int:
    """Write the DailyRate grid of a BASE plan for `[start, end)`; returns how many nights were written.

    `restrictions` keys: min_los, max_los, closed_to_arrival, closed_to_departure, stop_sell, plus
    the relative price changes price_delta_percent / price_delta_amount. `dow` filters weekdays
    (Monday = 0). Missing rows are created with the resolved price. Emits `rates_changed` after commit.
    """
    if rate_plan.kind != RatePlan.Kind.BASE:
        raise DomainError(
            "Los planes derivados se calculan desde su plan base", code="derived_plan_not_editable"
        )
    restrictions = dict(restrictions or {})
    unknown = set(restrictions) - RESTRICTION_FIELDS - PRICE_DELTAS
    if unknown:
        raise DomainError(
            f"Restricciones desconocidas: {', '.join(sorted(unknown))}", code="invalid_restriction"
        )
    weekdays = set(dow) if dow is not None else None
    user = actor if getattr(actor, "is_authenticated", False) else None
    currency = property.currency or "COP"

    count = 0
    with transaction.atomic():
        existing = {
            row.date: row
            for row in DailyRate.objects.select_for_update().filter(
                room_type=room_type, rate_plan=rate_plan, date__gte=start, date__lt=end
            )
        }
        resolved = {day.date: day for day in resolve_daily(room_type, rate_plan, start, end)}
        for day in daterange(start, end):
            if weekdays is not None and day.weekday() not in weekdays:
                continue
            row = existing.get(day) or DailyRate(
                room_type=room_type, rate_plan=rate_plan, date=day, price=resolved[day].price
            )
            if price is not None:
                row.price = D(price)
            if "price_delta_percent" in restrictions:
                row.price = apply_percent(row.price, restrictions["price_delta_percent"])
            if "price_delta_amount" in restrictions:
                row.price = max(D(row.price) + D(restrictions["price_delta_amount"]), ZERO)
            row.price = quantize(row.price, currency)
            for key in RESTRICTION_FIELDS & restrictions.keys():
                setattr(row, key, restrictions[key])
            row.source = source
            row.updated_by = user
            row.save()
            count += 1
        if count:
            signals.send_on_commit(
                signals.rates_changed,
                property=property,
                room_type_ids=[room_type.pk],
                rate_plan_ids=[rate_plan.pk],
                start=start,
                end=end,
            )
    return count


def derive_price(price, rate_plan) -> Decimal:
    """Derived plan price from its parent's price (percent or amount, never below 0). Not rounded."""
    value = D(rate_plan.derivation_value)
    if rate_plan.derivation_type == RatePlan.DerivationType.AMOUNT:
        return max(D(price) + value, ZERO)
    return max(apply_percent(price, value), ZERO)


def _room_taxes(property, subtotal, foreign_non_resident, currency) -> tuple[list[TaxLine], Decimal]:
    lines, total = [], ZERO
    taxes = Tax.objects.filter(property=property, is_active=True, applies_to__in=ROOM_TAX_SCOPES).order_by(
        "code"
    )
    for tax in taxes:
        rate = D(tax.rate)
        if tax.exempt_foreign_non_residents and foreign_non_resident:
            lines.append(
                TaxLine(
                    code=tax.code,
                    name=tax.name,
                    rate=rate,
                    amount=ZERO,
                    included=tax.included_in_price,
                    exempt=True,
                )
            )
        elif tax.included_in_price:
            amount = quantize(subtotal - subtotal / (1 + rate / 100), currency)
            lines.append(TaxLine(code=tax.code, name=tax.name, rate=rate, amount=amount, included=True))
        else:
            amount = quantize(subtotal * rate / 100, currency)
            lines.append(TaxLine(code=tax.code, name=tax.name, rate=rate, amount=amount, included=False))
            total += amount
    return lines, total
