"""Housetel KPI engine (plan C10): the ONE place where occupancy, ADR, RevPAR and revenue are defined.

Every report, the Today widget and the exports read their figures from here, so two screens can never
disagree about the same night. All dates are **business dates** of the property.

Definitions (also shown to the user in the "Cómo se calcula" notes of each report):

- **Range** ``[start, end]`` is inclusive on both ends: "1 to 30 September" is 30 nights. The night of a date
  ``d`` is the stay night that starts on ``d``; stays cover ``checkin <= d < checkout`` (the checkout day is
  never a night of the stay).
- **Room nights sold(d)** = stays with status ``confirmed | checked_in | checked_out`` that cover ``d``.
  Tentative holds, cancelled and no-show stays never count (a penalty they paid counts as *other revenue*).
  Dorms sell beds: every dorm stay is one bed, so dorm units are beds.
- **Available room nights(d)** = Σ ``InventoryDay.total_units − blocked_units`` over the property's categories
  (active rooms, or active beds of active dorm rooms, minus units under an active block). Days outside the
  materialized inventory horizon are computed from the same tables with the same rule.
- **Occupancy(d)** = sold ÷ available × 100 (0 when nothing is available).
- **Room revenue(d)** = Σ ``Charge.amount`` (net, taxes apart) of non-voided ``room`` charges posted with
  ``business_date = d`` (actual). From the current business date on, nights are not posted yet (the night
  audit posts them), so the forecast = Σ ``nightly_rates[].net`` of the sold stays for that night (``confirmed
  | checked_in``), skipping any stay night that already has a posted room charge (counted as actual).
- **ADR** = room revenue ÷ room nights sold; **RevPAR** = room revenue ÷ available room nights.
- Totals of a range are ratios of the sums (never averages of daily ratios).
- **Other revenue** (posted only): extras (``extra``), penalties (``cancellation_fee``) and fees and
  adjustments (``fee``, ``adjustment``, ``other``), all net; taxes = Σ ``tax_amount`` (+ ``tax`` charges).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from django.db.models.functions import TruncDate

from apps.bookings.models import InventoryDay, Stay
from apps.core.dates import daterange
from apps.core.money import D, quantize
from apps.finance.models import Charge
from apps.inventory.models import Bed, Room, RoomBlock, RoomType

ZERO = Decimal("0")
ONE_DECIMAL = Decimal("0.1")
SOLD_STATUSES = ("confirmed", "checked_in", "checked_out")
FORECAST_STATUSES = ("confirmed", "checked_in")  # sold stays that still have unposted future nights
OTHER_KINDS = ("fee", "adjustment", "other")
DAY = timedelta(days=1)


# --- small helpers ---------------------------------------------------------------------------------------


def inclusive_days(start: date, end: date) -> list[date]:
    """Every date of ``[start, end]`` (both ends included)."""
    return list(daterange(start, end + DAY))


def pct(part, whole) -> Decimal:
    """``part ÷ whole × 100`` rounded to one decimal (0 when ``whole`` is 0)."""
    whole = D(whole)
    if not whole:
        return ZERO.quantize(ONE_DECIMAL)
    return (D(part) * 100 / whole).quantize(ONE_DECIMAL, rounding=ROUND_HALF_UP)


def per_unit(amount, units, currency: str) -> Decimal:
    """Money per unit rounded to the currency (0 when there are no units): ADR, RevPAR, averages."""
    if not units:
        return quantize(ZERO, currency)
    return quantize(D(amount) / D(units), currency)


def comparison_range(start: date, end: date, mode: str | None) -> tuple[date, date] | None:
    """The period a range is compared with: the same number of days right before it (``previous_period``) or
    the same dates one year earlier (``previous_year``; 29 Feb → 28 Feb)."""
    if mode == "previous_period":
        length = (end - start).days + 1
        prev_end = start - DAY
        return prev_end - timedelta(days=length - 1), prev_end
    if mode == "previous_year":
        return start - relativedelta(years=1), end - relativedelta(years=1)
    return None


def local_date(field_name: str, prop) -> TruncDate:
    """Calendar date of a datetime column in the property's time zone (booking and cancellation dates)."""
    return TruncDate(field_name, tzinfo=ZoneInfo(prop.timezone or "America/Bogota"))


def nightly_net(nightly_rates) -> dict[date, Decimal]:
    """``{night: net}`` from ``Stay.nightly_rates`` (``[{"date", "amount", "net", "tax"}]``)."""
    result: dict[date, Decimal] = {}
    for item in nightly_rates or []:
        try:
            night = date.fromisoformat(str(item.get("date")))
        except (TypeError, ValueError):
            continue
        result[night] = D(item.get("net", item.get("amount")))
    return result


def channel_of(source: str | None, channel_code: str | None) -> str:
    """Distribution channel of a reservation: the OTA/channel code when there is one, else the direct channel
    it came through (marketplace, booking engine) or ``direct`` (front desk, phone, email, walk-in, API)."""
    if channel_code:
        return channel_code
    if source in ("marketplace", "booking_engine"):
        return source
    return "direct"


# --- available room nights ---------------------------------------------------------------------------------


def available_by_day(prop, start: date, end: date) -> dict[date, int]:
    """``{date: available room nights}`` for ``[start, end]`` from InventoryDay (``total − blocked``)."""
    days = inclusive_days(start, end)
    per_pair: dict[tuple, int] = {}
    for type_id, day, total, blocked in InventoryDay.objects.filter(
        property=prop, date__gte=start, date__lte=end
    ).values_list("room_type_id", "date", "total_units", "blocked_units"):
        per_pair[(type_id, day)] = max(total - blocked, 0)
    type_ids = list(RoomType.objects.filter(property=prop).values_list("id", flat=True))
    missing = [(type_id, day) for type_id in type_ids for day in days if (type_id, day) not in per_pair]
    if missing:
        per_pair.update(_available_from_tables(prop, missing, start, end))
    result = dict.fromkeys(days, 0)
    for (_type_id, day), units in per_pair.items():
        if day in result:
            result[day] += units
    return result


def _available_from_tables(prop, pairs: list[tuple], start: date, end: date) -> dict[tuple, int]:
    """Same rule as ``bookings.services.inventory.rebuild_inventory`` (read-only) for days without an
    InventoryDay row: active rooms (private) or active beds of active rooms (dorm), minus distinct units under
    an active block of an active room (blocking a dorm room blocks all its beds)."""
    type_ids = {type_id for type_id, _ in pairs}
    kinds = dict(RoomType.objects.filter(pk__in=type_ids).values_list("id", "kind"))
    dorm_ids = {type_id for type_id, kind in kinds.items() if kind == RoomType.Kind.DORM}
    totals: Counter = Counter(
        Room.objects.filter(room_type_id__in=type_ids - dorm_ids, is_active=True).values_list(
            "room_type_id", flat=True
        )
    )
    beds_of_room: defaultdict = defaultdict(set)
    for bed_id, room_id, type_id in Bed.objects.filter(
        room__room_type_id__in=dorm_ids, room__is_active=True, is_active=True
    ).values_list("id", "room_id", "room__room_type_id"):
        totals[type_id] += 1
        beds_of_room[room_id].add(bed_id)
    blocked: defaultdict = defaultdict(set)
    for room_id, type_id, bed_id, block_start, block_end in RoomBlock.objects.filter(
        room__room_type_id__in=type_ids,
        room__is_active=True,
        released_at__isnull=True,
        start_date__lte=end,
        end_date__gt=start,
    ).values_list("room_id", "room__room_type_id", "bed_id", "start_date", "end_date"):
        if type_id in dorm_ids:
            units = (beds_of_room[room_id] & {bed_id}) if bed_id else set(beds_of_room[room_id])
        else:
            units = {room_id}
        for night in daterange(max(block_start, start), min(block_end, end + DAY)):
            blocked[(type_id, night)] |= units
    return {(type_id, day): max(totals[type_id] - len(blocked[(type_id, day)]), 0) for type_id, day in pairs}


# --- the daily figures --------------------------------------------------------------------------------------


@dataclass
class DayFigures:
    """Figures of one business date (or of a week/month bucket when aggregated)."""

    date: date
    available: int = 0
    sold: int = 0
    room_revenue: Decimal = ZERO  # actual (posted) + forecast
    forecast_revenue: Decimal = ZERO  # part of room_revenue that is forecast (unposted future nights)
    forecast_days: int = 0  # days of the bucket on or after the business date
    days: int = 1

    @property
    def is_forecast(self) -> bool:
        return self.forecast_days > 0

    def occupancy(self) -> Decimal:
        return pct(self.sold, self.available)

    def adr(self, currency: str) -> Decimal:
        return per_unit(self.room_revenue, self.sold, currency)

    def revpar(self, currency: str) -> Decimal:
        return per_unit(self.room_revenue, self.available, currency)


def sold_stays(prop, start: date, end: date, statuses: Iterable[str] = SOLD_STATUSES, *, values=()):
    """Stays of the property with one of ``statuses`` that cover at least one night of ``[start, end]``."""
    return (
        Stay.objects.filter(
            reservation__property=prop,
            status__in=list(statuses),
            checkin_date__lte=end,
            checkout_date__gt=start,
        )
        .order_by()
        .values("id", "reservation_id", "checkin_date", "checkout_date", "status", "nightly_rates", *values)
    )


def posted_room_nights(prop, start: date, end: date) -> set[tuple]:
    """``{(stay_id, night)}`` with a non-voided room charge, for nights of ``[start, end]``."""
    if start > end:
        return set()
    return set(
        Charge.objects.filter(
            folio__property=prop,
            kind=Charge.Kind.ROOM,
            voided_at__isnull=True,
            stay__isnull=False,
            night_date__gte=start,
            night_date__lte=end,
        ).values_list("stay_id", "night_date")
    )


def actual_room_revenue(prop, start: date, end: date) -> dict[date, Decimal]:
    """``{business_date: Σ net}`` of the non-voided room charges posted in ``[start, end]``."""
    return {
        day: net or ZERO
        for day, net in Charge.objects.filter(
            folio__property=prop,
            kind=Charge.Kind.ROOM,
            voided_at__isnull=True,
            business_date__gte=start,
            business_date__lte=end,
        )
        .order_by()
        .values("business_date")
        .annotate(net=Sum("amount"))
        .values_list("business_date", "net")
    }


def daily_figures(prop, start: date, end: date) -> list[DayFigures]:
    """Available, sold and room revenue (actual + forecast) of every date of ``[start, end]``."""
    today = prop.business_date
    days = {
        day: DayFigures(date=day, forecast_days=1 if day >= today else 0)
        for day in inclusive_days(start, end)
    }
    for day, units in available_by_day(prop, start, end).items():
        days[day].available = units
    posted = posted_room_nights(prop, max(start, today), end) if end >= today else set()
    for stay in sold_stays(prop, start, end):
        rates = None
        for night in daterange(max(stay["checkin_date"], start), min(stay["checkout_date"], end + DAY)):
            figures = days[night]
            figures.sold += 1
            if night >= today and stay["status"] in FORECAST_STATUSES and (stay["id"], night) not in posted:
                if rates is None:
                    rates = nightly_net(stay["nightly_rates"])
                amount = rates.get(night, ZERO)
                figures.forecast_revenue += amount
                figures.room_revenue += amount
    for day, net in actual_room_revenue(prop, start, end).items():
        days[day].room_revenue += net
    return [days[day] for day in sorted(days)]


@dataclass
class Totals:
    available: int = 0
    sold: int = 0
    room_revenue: Decimal = ZERO
    forecast_revenue: Decimal = ZERO
    days: int = 0
    forecast_days: int = 0

    def occupancy(self) -> Decimal:
        return pct(self.sold, self.available)

    def adr(self, currency: str) -> Decimal:
        return per_unit(self.room_revenue, self.sold, currency)

    def revpar(self, currency: str) -> Decimal:
        return per_unit(self.room_revenue, self.available, currency)


def totals_of(days: Iterable[DayFigures]) -> Totals:
    totals = Totals()
    for day in days:
        totals.available += day.available
        totals.sold += day.sold
        totals.room_revenue += day.room_revenue
        totals.forecast_revenue += day.forecast_revenue
        totals.days += day.days
        totals.forecast_days += day.forecast_days
    return totals


def bucket_start(day: date, group_by: str) -> date:
    if group_by == "week":
        return day - timedelta(days=day.weekday())  # ISO week, Monday
    if group_by == "month":
        return day.replace(day=1)
    return day


def bucket_days(days: list[DayFigures], group_by: str) -> list[DayFigures]:
    """Aggregate daily figures into weeks (Monday) or months (first day); ratios are recomputed from sums."""
    if group_by in (None, "", "day"):
        return days
    buckets: dict[date, DayFigures] = {}
    for day in days:
        key = bucket_start(day.date, group_by)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = buckets[key] = DayFigures(date=key, days=0)
        bucket.available += day.available
        bucket.sold += day.sold
        bucket.room_revenue += day.room_revenue
        bucket.forecast_revenue += day.forecast_revenue
        bucket.forecast_days += day.forecast_days
        bucket.days += day.days
    return [buckets[key] for key in sorted(buckets)]


# --- revenue by charge kind (posted) ------------------------------------------------------------------------


@dataclass
class RevenueByKind:
    room: Decimal = ZERO
    extras: Decimal = ZERO
    penalties: Decimal = ZERO
    fees: Decimal = ZERO  # fee + adjustment + other
    taxes: Decimal = ZERO

    @property
    def other(self) -> Decimal:
        return self.penalties + self.fees

    @property
    def net(self) -> Decimal:
        return self.room + self.extras + self.penalties + self.fees

    @property
    def gross(self) -> Decimal:
        return self.net + self.taxes

    def add(self, other: RevenueByKind) -> None:
        self.room += other.room
        self.extras += other.extras
        self.penalties += other.penalties
        self.fees += other.fees
        self.taxes += other.taxes


def revenue_by_kind(prop, start: date, end: date) -> dict[date, RevenueByKind]:
    """``{business_date: RevenueByKind}`` of the non-voided charges posted in ``[start, end]``."""
    result: dict[date, RevenueByKind] = defaultdict(RevenueByKind)
    rows = (
        Charge.objects.filter(
            folio__property=prop, voided_at__isnull=True, business_date__gte=start, business_date__lte=end
        )
        .order_by()
        .values("business_date", "kind")
        .annotate(net=Sum("amount"), tax=Sum("tax_amount"))
    )
    for row in rows:
        figures = result[row["business_date"]]
        net, tax = row["net"] or ZERO, row["tax"] or ZERO
        kind = row["kind"]
        figures.taxes += tax
        if kind == Charge.Kind.ROOM:
            figures.room += net
        elif kind == Charge.Kind.EXTRA:
            figures.extras += net
        elif kind == Charge.Kind.CANCELLATION_FEE:
            figures.penalties += net
        elif kind == Charge.Kind.TAX:
            figures.taxes += net
        else:
            figures.fees += net
    return result


# --- attribution of room nights and room revenue to segments ------------------------------------------------

SEGMENT_STAY_VALUES = (
    "room_type_id",
    "rate_plan_id",
    "reservation__source",
    "reservation__channel_code",
    "reservation__booker_id",
    "reservation__booker__nationality",
)
SEGMENT_CHARGE_VALUES = (
    "amount",
    "business_date",
    "stay_id",
    "stay__room_type_id",
    "stay__rate_plan_id",
    "folio__reservation_id",
    "folio__reservation__source",
    "folio__reservation__channel_code",
    "folio__reservation__booker_id",
    "folio__reservation__booker__nationality",
)


@dataclass
class SegmentFigures:
    nights: int = 0
    revenue: Decimal = ZERO
    forecast_revenue: Decimal = ZERO
    reservations: set = field(default_factory=set)
    guests: set = field(default_factory=set)


def _stay_attrs(stay: dict) -> dict:
    return {
        "source": stay["reservation__source"],
        "channel": channel_of(stay["reservation__source"], stay["reservation__channel_code"]),
        "room_type": stay["room_type_id"],
        "rate_plan": stay["rate_plan_id"],
        "nationality": (stay["reservation__booker__nationality"] or "").upper(),
        "reservation": stay["reservation_id"],
        "guest": stay["reservation__booker_id"],
    }


def _charge_attrs(charge: dict) -> dict:
    source = charge["folio__reservation__source"]
    return {
        "source": source,
        "channel": channel_of(source, charge["folio__reservation__channel_code"]) if source else None,
        "room_type": charge["stay__room_type_id"],
        "rate_plan": charge["stay__rate_plan_id"],
        "nationality": (charge["folio__reservation__booker__nationality"] or "").upper(),
        "reservation": charge["folio__reservation_id"],
        "guest": charge["folio__reservation__booker_id"],
    }


def segment_figures(
    prop, start: date, end: date, key: Callable[[dict], object]
) -> dict[object, SegmentFigures]:
    """Room nights sold and room revenue of ``[start, end]`` split by ``key(attrs)``.

    Uses exactly the engine definitions, so the segments always add up to the performance totals: every sold
    stay night counts in its stay's segment; actual revenue is each posted room charge (business date in the
    range) in the segment of its stay/reservation; forecast revenue is each unposted future night in its
    stay's segment. ``attrs``: ``source, channel, room_type, rate_plan, nationality, reservation, guest``.
    """
    today = prop.business_date
    result: dict[object, SegmentFigures] = defaultdict(SegmentFigures)
    posted = posted_room_nights(prop, max(start, today), end) if end >= today else set()
    for stay in sold_stays(prop, start, end, values=SEGMENT_STAY_VALUES):
        attrs = _stay_attrs(stay)
        figures = result[key(attrs)]
        rates = None
        counted = False
        for night in daterange(max(stay["checkin_date"], start), min(stay["checkout_date"], end + DAY)):
            figures.nights += 1
            counted = True
            if night >= today and stay["status"] in FORECAST_STATUSES and (stay["id"], night) not in posted:
                if rates is None:
                    rates = nightly_net(stay["nightly_rates"])
                amount = rates.get(night, ZERO)
                figures.revenue += amount
                figures.forecast_revenue += amount
        if counted:
            figures.reservations.add(attrs["reservation"])
            if attrs["guest"]:
                figures.guests.add(attrs["guest"])
    charges = (
        Charge.objects.filter(
            folio__property=prop,
            kind=Charge.Kind.ROOM,
            voided_at__isnull=True,
            business_date__gte=start,
            business_date__lte=end,
        )
        .order_by()
        .values(*SEGMENT_CHARGE_VALUES)
    )
    for charge in charges:
        result[key(_charge_attrs(charge))].revenue += charge["amount"] or ZERO
    return dict(result)
