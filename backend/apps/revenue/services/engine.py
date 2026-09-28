"""Recommendation engine (plan C8): one proposed price per category × base plan × night.

For every active base plan and each of its active categories, night by night from the business date:

1. Current price and source: `rates.resolve_daily` (DailyRate → season → defaults). Nights without any
   configured price (`source="none"`) and nights without sellable units are skipped.
2. Anchor (reference) price: the resolved price ignoring rows written by revenue (`source="revenue"`): a
   manual/bulk/channel price is the anchor; a night that revenue already changed goes back to its season or
   default price, unless the price revenue replaced was set by hand (remembered in the last applied
   recommendation: its `anchor_source` is manual/bulk/channel).
3. Rules: on-the-books occupancy = sold / (total − blocked) of `InventoryDay` (blocked units cannot be sold;
   capped at 100 %), lead time from the business date, weekday, Colombian holidays and long weekends,
   manual events. Each active rule of the category adds its adjustment: `stack` rules add up; of the `max`
   rules only the highest adjustment counts (ties: higher priority). Total = stack sum + winning max (never
   below −90 %).
4. Target = anchor × (1 + total/100), then:
   - maximum daily change: within ±`max_daily_change_percent` of the price the night had at the start of the
     day (the current price, or — when revenue already changed it today — the price before that change);
   - `PriceBounds` of the category and plan: a hard floor and ceiling (they win over the daily change);
   - commercial rounding to a multiple of `price_rounding`, staying inside those limits; currency rounding
     (a `rounding` reason records it, and the limits name the final, rounded price).
5. Threshold: a change smaller than `min_change_percent` of the current price is not recommended (a change
   of exactly the minimum is).

Every recommendation carries structured `reasons` (rules, applied or not, and limits) and a deterministic
explanation in Spanish and English (`services.explain`).
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from apps.bookings.models import InventoryDay
from apps.bookings.services.availability import availability_by_date
from apps.core.dates import property_now
from apps.core.money import D, quantize
from apps.inventory.models import RoomType
from apps.rates.models import RatePlan
from apps.rates.services.quote import resolve_daily
from apps.rates.services.resolution import configured_price, load_defaults, season_rates_for
from apps.revenue import rules as rule_kinds
from apps.revenue.models import PriceBounds, PricingRule, RateRecommendation
from apps.revenue.services.config import get_settings
from apps.revenue.services.explain import explain

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CENTS = Decimal("0.01")
MIN_TOTAL_ADJUST = Decimal("-90")
OWN_PRICE_SOURCES = ("manual", "bulk", "channel")
Status = RateRecommendation.Status
APPLIED_STATUSES = (Status.APPLIED, Status.AUTO_APPLIED)


@dataclass(frozen=True)
class RuleSpec:
    """A rule as the engine sees it (stored rules and drafts being simulated)."""

    id: str | None
    name: str
    kind: str
    params: dict
    combine: str = PricingRule.Combine.STACK
    priority: int = 10
    room_type_ids: frozenset = frozenset()  # empty = every category

    @classmethod
    def from_rule(cls, rule: PricingRule) -> "RuleSpec":
        return cls(
            id=str(rule.pk) if rule.pk else None,
            name=rule.name,
            kind=rule.kind,
            params=rule.params,
            combine=rule.combine,
            priority=rule.priority,
            room_type_ids=frozenset(room_type.pk for room_type in rule.room_types.all()),
        )

    def applies_to(self, room_type_id) -> bool:
        return not self.room_type_ids or room_type_id in self.room_type_ids


@dataclass
class Stored:
    recommendations: list = field(default_factory=list)  # pending after the run (new + refreshed)
    created: int = 0
    refreshed: int = 0
    superseded: int = 0
    kept_rejected: int = 0


def active_rules(property) -> list[RuleSpec]:
    rules = PricingRule.objects.filter(property=property, is_active=True).prefetch_related("room_types")
    return [RuleSpec.from_rule(rule) for rule in rules]


def priced_pairs(property) -> list[tuple[RoomType, RatePlan]]:
    """(category, base plan) pairs: active base plans × their active categories, in display order."""
    plans = (
        RatePlan.objects.filter(property=property, kind=RatePlan.Kind.BASE, is_active=True)
        .prefetch_related(
            Prefetch(
                "room_types",
                queryset=RoomType.objects.filter(is_active=True).order_by("sort_order", "code"),
                to_attr="active_room_types",
            )
        )
        .order_by("sort_order", "code")
    )
    return [(room_type, plan) for plan in plans for room_type in plan.active_room_types]


def compute_recommendations(property, *, start, end, persist=True, run=None, rules=None) -> list:
    """Recommendations for `[start, end)` (never before the business date). With `persist=False` they are
    returned unsaved; otherwise they are stored (see `store_recommendations`) and the pending ones are
    returned."""
    proposals = propose(property, start=start, end=end, rules=rules)
    if not persist:
        return proposals
    start = max(start, property.business_date)
    return store_recommendations(property, proposals, start=start, end=end, run=run).recommendations


# ---- proposal -----------------------------------------------------------------------------------------


class _Anchors:
    """Season/default price of one pair, loaded only when a night needs it."""

    def __init__(self, room_type, plan, start: date, end: date):
        self.room_type, self.plan, self.start, self.end = room_type, plan, start, end
        self._loaded = False

    def configured(self, day: date):
        if not self._loaded:
            self.seasons = season_rates_for(self.room_type, self.plan, self.start, self.end)
            self.defaults = load_defaults(self.room_type, self.plan)
            self._loaded = True
        return configured_price(self.seasons, self.defaults, day)


@dataclass
class _Context:
    property: object
    settings: object
    today: date
    currency: str
    rules: list
    inventory: dict
    holidays: object
    bounds: dict
    latest_applied: dict
    day_start_price: dict

    def anchor(self, key, day, anchors: _Anchors) -> tuple[Decimal, str]:
        if day.source != "revenue":
            return quantize(day.price, self.currency), day.source
        last = self.latest_applied.get(key)
        if last is not None and last.anchor_source in OWN_PRICE_SOURCES:
            return last.anchor_price, last.anchor_source
        configured = anchors.configured(day.date)
        if configured is not None:
            price, source = configured
            return quantize(price, self.currency), source
        if last is not None:
            return last.anchor_price, last.anchor_source
        return quantize(day.price, self.currency), day.source


def propose(property, *, start, end, rules=None) -> list[RateRecommendation]:
    today = property.business_date
    start = max(start, today)
    if end <= start:
        return []
    pairs = priced_pairs(property)
    if not pairs:
        return []
    room_type_ids = sorted({room_type.pk for room_type, _ in pairs}, key=str)
    latest_applied, day_start_price = _applied_history(property, pairs, start, end)
    ctx = _Context(
        property=property,
        settings=get_settings(property),
        today=today,
        currency=property.currency or "COP",
        rules=active_rules(property) if rules is None else list(rules),
        inventory=_inventory(property, room_type_ids, start, end),
        holidays=rule_kinds.holiday_facts(start, end),
        bounds={
            (bounds.room_type_id, bounds.rate_plan_id): bounds
            for bounds in PriceBounds.objects.filter(room_type__property=property)
        },
        latest_applied=latest_applied,
        day_start_price=day_start_price,
    )
    proposals = []
    for room_type, plan in pairs:
        anchors = _Anchors(room_type, plan, start, end)
        for day in resolve_daily(room_type, plan, start, end):
            proposal = _night(ctx, room_type, plan, day, anchors)
            if proposal is not None:
                proposals.append(proposal)
    return proposals


def _inventory(property, room_type_ids, start, end) -> dict:
    """`{(room_type_id, date): (total, sold, blocked)}`; the bookings contract materializes missing rows."""
    availability_by_date(property=property, start=start, end=end, room_type_ids=room_type_ids)
    rows = InventoryDay.objects.filter(
        room_type_id__in=room_type_ids, date__gte=start, date__lt=end
    ).values_list("room_type_id", "date", "total_units", "sold_units", "blocked_units")
    return {(type_id, day): (total, sold, blocked) for type_id, day, total, sold, blocked in rows}


def _applied_history(property, pairs, start, end) -> tuple[dict, dict]:
    """Last applied recommendation per night, and the price each night had before the first revenue change
    applied today (property time)."""
    day_start = property_now(property).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = RateRecommendation.objects.filter(
        property=property,
        status__in=APPLIED_STATUSES,
        room_type_id__in={room_type.pk for room_type, _ in pairs},
        date__gte=start,
        date__lt=end,
    ).order_by("applied_at", "created_at")
    latest, first_today = {}, {}
    for rec in rows.only(
        "room_type_id", "rate_plan_id", "date", "anchor_price", "anchor_source", "current_price", "applied_at"
    ):
        key = (rec.room_type_id, rec.rate_plan_id, rec.date)
        latest[key] = rec
        if rec.applied_at is not None and rec.applied_at >= day_start:
            first_today.setdefault(key, rec.current_price)
    return latest, first_today


def _night(ctx: _Context, room_type, plan, day, anchors: _Anchors) -> RateRecommendation | None:
    if day.source == "none":
        return None
    current = quantize(day.price, ctx.currency)
    total, sold, blocked = ctx.inventory.get((room_type.pk, day.date), (0, 0, 0))
    sellable = total - blocked
    if current <= 0 or sellable <= 0:
        return None
    occupancy = min(Decimal(sold) * HUNDRED / Decimal(sellable), HUNDRED).quantize(CENTS)
    key = (room_type.pk, plan.pk, day.date)
    anchor, anchor_source = ctx.anchor(key, day, anchors)
    facts = rule_kinds.NightFacts(
        date=day.date,
        lead_days=(day.date - ctx.today).days,
        occupancy=occupancy,
        holiday=ctx.holidays.holidays.get(day.date),
        bridge=ctx.holidays.bridges.get(day.date),
    )
    adjust, rule_reasons = combine(ctx.rules, room_type.pk, facts)
    reference = ctx.day_start_price.get(key, current) if day.source == "revenue" else current
    price, limit_reasons = limit_price(
        anchor * (1 + adjust / HUNDRED),
        reference=reference,
        bounds=ctx.bounds.get((room_type.pk, plan.pk)),
        settings=ctx.settings,
        currency=ctx.currency,
    )
    change = ((price - current) * HUNDRED / current).quantize(CENTS, rounding=ROUND_HALF_UP)
    if price == current or abs(change) < D(ctx.settings.min_change_percent):
        return None
    reasons = rule_reasons + limit_reasons
    return RateRecommendation(
        property=ctx.property,
        room_type=room_type,
        rate_plan=plan,
        date=day.date,
        current_price=current,
        current_source=day.source,
        anchor_price=anchor,
        anchor_source=anchor_source,
        adjustment_percent=adjust.quantize(CENTS),
        recommended_price=price,
        change_percent=change,
        occupancy=occupancy,
        available_units=max(sellable - sold, 0),
        reasons=reasons,
        explanation=explain(
            current=current,
            recommended=price,
            change=change,
            anchor=anchor,
            anchor_source=anchor_source,
            reasons=reasons,
            currency=ctx.currency,
        ),
        status=Status.PENDING,
    )


def _money(value) -> str:
    return format(D(value).quantize(CENTS), "f")


def combine(rules, room_type_id, facts) -> tuple[Decimal, list[dict]]:
    """Total adjustment of the night and one reason per rule that matched (see the module docstring)."""
    hits = []
    for spec in rules:
        if not spec.applies_to(room_type_id):
            continue
        hit = rule_kinds.evaluate(spec.kind, spec.params, facts)
        if hit is not None and hit.adjust:
            hits.append((spec, hit))
    stacked = [item for item in hits if item[0].combine == PricingRule.Combine.STACK]
    maxed = sorted(
        (item for item in hits if item[0].combine == PricingRule.Combine.MAX),
        key=lambda item: (-item[1].adjust, -item[0].priority, item[0].name, str(item[0].id)),
    )
    applied = stacked + maxed[:1]
    total = max(sum((hit.adjust for _, hit in applied), ZERO), MIN_TOTAL_ADJUST)

    def reason(spec, hit, is_applied):
        return {
            "type": "rule",
            "rule_id": spec.id,
            "name": spec.name,
            "kind": spec.kind,
            "combine": spec.combine,
            "adjust": _money(hit.adjust),
            "applied": is_applied,
            "detail": hit.detail,
        }

    def order(item):
        return (-item[0].priority, item[0].name, str(item[0].id))

    reasons = [reason(spec, hit, True) for spec, hit in sorted(applied, key=order)]
    reasons += [reason(spec, hit, False) for spec, hit in sorted(maxed[1:], key=order)]
    return total, reasons


def limit_price(raw, *, reference, bounds, settings, currency) -> tuple[Decimal, list[dict]]:
    """Maximum daily change around `reference`, then the category bounds (hard), then rounding."""
    reasons = []
    step = D(settings.max_daily_change_percent) / HUNDRED
    cap_low, cap_high = reference * (1 - step), reference * (1 + step)
    price = min(max(D(raw), cap_low), cap_high)
    if price != D(raw):
        reasons.append(
            {
                "type": "limit",
                "kind": "max_daily_change",
                "percent": _money(settings.max_daily_change_percent),
                "price": _money(quantize(price, currency)),
            }
        )
    floor = D(bounds.min_price) if bounds is not None and bounds.min_price is not None else None
    ceiling = D(bounds.max_price) if bounds is not None and bounds.max_price is not None else None
    if floor is not None and price < floor:
        price = floor
        reasons.append({"type": "limit", "kind": "min_price", "price": _money(floor)})
    if ceiling is not None and price > ceiling:
        price = ceiling
        reasons.append({"type": "limit", "kind": "max_price", "price": _money(ceiling)})
    low = cap_low if floor is None else max(cap_low, floor)
    high = cap_high if ceiling is None else min(cap_high, ceiling)
    if low > high:  # the cap and the bounds do not meet: the bounds win
        low, high = floor, ceiling
    limited = quantize(price, currency)
    final = quantize(round_within(price, D(settings.price_rounding), low, high), currency)
    if final != limited:
        # The explanation names the price the hotel will see: "the price stays at" is the rounded one, and a
        # `rounding` reason says it was rounded (and from which price).
        for reason in reasons:
            if reason["kind"] == "max_daily_change":
                reason["price"] = _money(final)
                reason["rounded"] = True
        reasons.append(
            {
                "type": "limit",
                "kind": "rounding",
                "step": _money(settings.price_rounding),
                "from": _money(limited),
                "price": _money(final),
            }
        )
    return final, reasons


def round_within(value: Decimal, step: Decimal, low, high) -> Decimal:
    """Nearest multiple of `step` inside `[low, high]` (None = open); else the other neighbour; else
    `value`."""
    if step <= 0:
        return value
    units = value / step
    for rounding in (ROUND_HALF_UP, ROUND_FLOOR, ROUND_CEILING):
        candidate = units.to_integral_value(rounding=rounding) * step
        if (low is None or candidate >= low) and (high is None or candidate <= high):
            return candidate
    return value


# ---- storage ------------------------------------------------------------------------------------------


def store_recommendations(property, proposals, *, start, end, run=None) -> Stored:
    """Keep one pending recommendation per night of `[start, end)`:

    - a proposal equal (current and recommended price) to the pending one refreshes it (reasons, occupancy,
      run) instead of creating a new row; a different one supersedes it (the old one expires);
    - a proposal equal to the last rejected one for that night is not proposed again;
    - pending recommendations of the range that are no longer proposed expire.
    """
    result = Stored()
    now = timezone.now()
    with transaction.atomic():
        in_range = RateRecommendation.objects.filter(property=property, date__gte=start, date__lt=end)
        pending = {
            (rec.room_type_id, rec.rate_plan_id, rec.date): rec
            for rec in in_range.filter(status=Status.PENDING)
            .select_related("room_type")  # the run summary reads each category (no query per row)
            .select_for_update(of=("self",))
        }
        rejected = {}
        for rec in in_range.filter(status=Status.REJECTED).order_by("decided_at", "created_at"):
            rejected[(rec.room_type_id, rec.rate_plan_id, rec.date)] = (
                rec.current_price,
                rec.recommended_price,
            )
        to_create, to_update, stale, proposed = [], [], [], set()
        for proposal in proposals:
            key = (proposal.room_type_id, proposal.rate_plan_id, proposal.date)
            prices = (proposal.current_price, proposal.recommended_price)
            old = pending.get(key)
            if rejected.get(key) == prices:
                result.kept_rejected += 1
                continue
            proposed.add(key)
            if old is not None and (old.current_price, old.recommended_price) == prices:
                for name in REFRESHED_FIELDS:
                    setattr(old, name, getattr(proposal, name))
                old.run, old.updated_at = run, now
                to_update.append(old)
                continue
            if old is not None:
                stale.append(old.pk)
                result.superseded += 1
            proposal.run = run
            to_create.append(proposal)
        stale += [rec.pk for key, rec in pending.items() if key not in proposed]
        if stale:  # before creating: at most one pending row per night
            RateRecommendation.objects.filter(pk__in=stale).update(status=Status.EXPIRED, updated_at=now)
        if to_update:
            RateRecommendation.objects.bulk_update(to_update, [*REFRESHED_FIELDS, "run", "updated_at"])
        RateRecommendation.objects.bulk_create(to_create)
    result.created, result.refreshed = len(to_create), len(to_update)
    result.recommendations = sorted(
        [*to_update, *to_create], key=lambda rec: (rec.date, rec.room_type.sort_order, rec.room_type.code)
    )
    return result


REFRESHED_FIELDS = (
    "current_source",
    "anchor_price",
    "anchor_source",
    "adjustment_percent",
    "change_percent",
    "occupancy",
    "available_units",
    "reasons",
    "explanation",
)
