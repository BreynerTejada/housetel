"""Quote engine (spec §4.2 contracts; algorithm of plan B2a, which is normative).

`quote()` prices a stay night by night:
1. nights = `[checkin, checkout)`; none → `invalid_dates`.
2. The effective base plan is the plan itself or, for a derived plan, its parent.
3. Base price per night from the base plan: DailyRate → SeasonRate of the active season with the highest
   priority (+ weekday %) → RoomTypeRateDefaults (+ weekday %) → no price (`no_rate` warning). A DailyRate
   row that only holds restrictions (source default/season) keeps following the season/defaults.
4. Derived plans: percent → price × (1 + v/100); amount → price + v (never below 0).
5. Occupancy: adults above the category's `base_occupancy` pay `extra_adult_price`; children up to
   `child_age_limit` (defaults, 12 when missing; a child without age counts as a child) pay
   `extra_child_price`, older children count as adults. One adult with a `single_occupancy_price` → that price
   replaces the base price of a default night; other nights keep its proportion (`night × single/default`,
   so weekday %, seasons and manual prices still apply to a single guest); the derivation of step 4 applies
   afterwards. Dorms: one person per unit (bed), no extras, no single occupancy.
6. Promo code (see `services.promos`): discount per eligible night, `promo_applied=code`; a code that does
   not apply adds the `promo_invalid` warning and never blocks.
7. Restrictions from the base plan rows: `stop_sell` (any night), `cta` (checkin night), `ctd` (row of the
   checkout date), `min_los` (arrival row, else `rate_plan.min_los_default`), `max_los` (arrival row).
   `restrictions_ok` is False only for these; `no_rate` and `promo_invalid` are warnings.
8. Taxes: active taxes with `applies_to` room/all, by code. Exempt foreign non-resident → zero line with
   `exempt=True`; included → informative line `subtotal − subtotal/(1+rate)`; excluded → `subtotal × rate`,
   added to `tax_total`.
9. Every amount is rounded with `core.money.quantize` (COP: whole pesos, half up) per night and in totals.

Ranges are half-open: `[start, end)`; for a stay, `[checkin, checkout)`.
"""

from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal

from apps.core.dates import nights as stay_nights
from apps.core.money import D, apply_percent, quantize
from apps.inventory.models import RoomType
from apps.rates.models import RatePlan, Tax
from apps.rates.services import promos, writes
from apps.rates.services.resolution import load_defaults, resolve_base_days
from apps.rates.types import DayRate, NightPrice, Quote, TaxLine

ZERO = Decimal("0")
ROOM_TAX_SCOPES = ("room", "all")
DEFAULT_CHILD_AGE_LIMIT = 12


@dataclass(frozen=True)
class Occupancy:
    extra_adults: int
    children: int  # children charged as children (age ≤ limit or unknown)
    single: bool


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
    stay = stay_nights(checkin, checkout)
    if not stay:
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

    base_plan = rate_plan.base_plan
    defaults = load_defaults(room_type, base_plan)
    # one extra day: the row of the checkout date carries closed-to-departure
    days = resolve_base_days(room_type, base_plan, checkin, checkout + timedelta(days=1), defaults=defaults)
    night_days, departure = days[:-1], days[-1]
    occupancy = _occupancy(room_type, defaults, adults, children, children_ages)
    promo = promos.find_promo(property, promo_code)
    promo_dates = set(promos.eligible_nights(promo, property=property, rate_plan=rate_plan, nights=stay))

    nights = []
    for day in night_days:
        price = day.price
        if occupancy.single and defaults is not None and defaults.single_occupancy_price is not None:
            price = single_price(price, defaults)
        if rate_plan.kind == RatePlan.Kind.DERIVED and day.source != "none":
            price = derive_price(price, rate_plan)
        base = quantize(price, currency)
        extra_adults = quantize(occupancy.extra_adults * D(day.extra_adult_price), currency)
        extra_children = quantize(occupancy.children * D(day.extra_child_price), currency)
        gross = base + extra_adults + extra_children
        discount = promos.night_discount(promo, gross, currency) if day.date in promo_dates else ZERO
        nights.append(
            NightPrice(
                date=day.date,
                base=base,
                extra_adults=extra_adults,
                extra_children=extra_children,
                discount=discount,
                total=gross - discount,
            )
        )

    violations = _restriction_violations(night_days, departure, rate_plan)
    restrictions_ok = not violations
    if any(day.source == "none" for day in night_days):
        violations.append("no_rate")
    promo_applied = promo.code if promo_dates else None
    if promos.normalize_code(promo_code) and promo_applied is None:
        violations.append("promo_invalid")

    subtotal = quantize(sum((night.total for night in nights), ZERO), currency)
    discount_total = quantize(sum((night.discount for night in nights), ZERO), currency)
    taxes, tax_total = _room_taxes(property, subtotal, guest_is_foreign_non_resident, currency)
    return Quote(
        **common,
        nights=nights,
        subtotal=subtotal,
        discount_total=discount_total,
        taxes=taxes,
        tax_total=tax_total,
        total=subtotal + tax_total,
        restrictions_ok=restrictions_ok,
        violations=violations,
        promo_applied=promo_applied,
    )


def _occupancy(room_type, defaults, adults, children, children_ages) -> Occupancy:
    if room_type.kind == RoomType.Kind.DORM:
        return Occupancy(extra_adults=0, children=0, single=False)
    limit = defaults.child_age_limit if defaults is not None else DEFAULT_CHILD_AGE_LIMIT
    children = max(int(children or 0), 0)
    ages = list(children_ages or [])[:children]
    ages += [None] * (children - len(ages))
    young = sum(1 for age in ages if age is None or int(age) <= limit)
    effective_adults = int(adults or 0) + (children - young)
    return Occupancy(
        extra_adults=max(effective_adults - room_type.base_occupancy, 0),
        children=young,
        single=effective_adults == 1,
    )


def _restriction_violations(night_days: list[DayRate], departure: DayRate, rate_plan) -> list[str]:
    arrival, length = night_days[0], len(night_days)
    violations = []
    if any(day.stop_sell for day in night_days):
        violations.append("stop_sell")
    if arrival.closed_to_arrival:
        violations.append("cta")
    if departure.closed_to_departure:
        violations.append("ctd")
    min_los = arrival.min_los if arrival.min_los is not None else rate_plan.min_los_default
    if min_los and length < min_los:
        violations.append("min_los")
    if arrival.max_los and length > arrival.max_los:
        violations.append("max_los")
    return violations


def resolve_daily(room_type, rate_plan, start, end) -> list[DayRate]:
    """Effective price and restrictions for each night in `[start, end)`.

    Rows come from the plan's base plan (DailyRate → season → defaults, see `services.resolution`); a derived
    plan returns derived (unrounded) prices with the base plan's restrictions. `source` is the DailyRate
    source of a night with a price of its own (manual, bulk, revenue, channel), else "season", "default"
    (RoomTypeRateDefaults) or "none" (no price configured).
    """
    days = resolve_base_days(room_type, rate_plan.base_plan, start, end)
    if rate_plan.kind != RatePlan.Kind.DERIVED:
        return days
    return [
        day if day.source == "none" else replace(day, price=derive_price(day.price, rate_plan))
        for day in days
    ]


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

    `restrictions` keys: min_los, max_los, closed_to_arrival, closed_to_departure, stop_sell (None clears a
    length of stay), plus the relative price changes price_delta_percent / price_delta_amount. `dow` filters
    weekdays (Monday = 0). Missing rows are created with the resolved price. Derived plans raise
    `derived_plan_not_editable`. Records a reversible `rates.bulk_update` audit event (undo restores the
    previous rows) and emits `rates_changed` after commit. See `services.writes`.
    """
    return writes.bulk_update_rates(
        property=property,
        room_types=[room_type],
        rate_plan=rate_plan,
        start=start,
        end=end,
        price=price,
        restrictions=restrictions,
        dow=dow,
        source=source,
        actor=actor,
    ).updated


def single_price(price, defaults) -> Decimal:
    """Price of the night for one guest. The single occupancy price keeps its proportion to the category's
    default price: on a default night it is exactly that price (with the same weekday %), and season, manual
    or revenue nights scale by `single_occupancy_price / defaults.price`, so a single guest pays the same
    share of the night on every date. Not rounded."""
    reference = D(defaults.price)
    if reference <= 0:
        return D(defaults.single_occupancy_price)
    return D(price) * D(defaults.single_occupancy_price) / reference


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
