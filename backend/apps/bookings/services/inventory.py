"""InventoryDay maintenance (plan B2b › Inventario).

One row per (room_type, night): `total_units`, `sold_units`, `blocked_units`;
`available = total − sold − blocked` (negative when overbooked). Units are rooms for private categories
and beds for dorms.

- `total_units`: active rooms (private) or active beds of active rooms (dorm).
- `sold_units`: active stays (tentative | confirmed | checked_in) covering the night. A stay counts in the
  category of its assigned room (an upgrade occupies the upgraded category), else in its booked category.
- `blocked_units`: distinct units under an active block (`released_at` null) of an active room; blocking a
  dorm room blocks all its active beds, blocking a bed blocks that bed.

`rebuild_inventory` recomputes rows from those tables (idempotent). Booking operations keep `sold_units` up to
date incrementally with `adjust_inventory` inside their own transaction: rows are locked with
`select_for_update()` in `(room_type_id, date)` order (the same order everywhere, so concurrent bookings queue
instead of deadlocking) and missing rows are materialized first. Callers adjust inventory BEFORE writing the
stays, so a materialization never counts the change twice.
"""

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.bookings.models import ACTIVE_STAY_STATUSES, InventoryDay, Stay
from apps.bookings.types import AvailabilityError
from apps.core.dates import daterange
from apps.inventory.models import Bed, Room, RoomBlock, RoomType

logger = logging.getLogger("housetel.bookings")

HORIZON_PAST_DAYS = 7
HORIZON_FUTURE_DAYS = 540
MAX_DRIFT_DETAILS = 50
ORIGIN = "bookings"  # `origin` kwarg of the inventory_changed events emitted by this app
UNIT_FIELDS = ("total_units", "sold_units", "blocked_units")


@dataclass
class RebuildResult:
    created: int = 0  # rows that did not exist
    updated: int = 0  # existing rows whose values were wrong (drift)
    # first 50 repaired rows: {room_type_id, date, <field>: [before, after]}
    drift: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"created": self.created, "updated": self.updated, "drift": self.drift}


def inventory_horizon(property) -> tuple[date, date]:
    """Default range `[business_date − 7, business_date + 540]` as a half-open `[start, end)`."""
    today = property.business_date
    return today - timedelta(days=HORIZON_PAST_DAYS), today + timedelta(days=HORIZON_FUTURE_DAYS + 1)


def rebuild_inventory(property, start=None, end=None, room_type_ids=None) -> RebuildResult:
    """Recompute the InventoryDay rows of `[start, end)` (default: the horizon) for every category of the
    property (or only `room_type_ids`). Idempotent; returns what it created and the drift it repaired."""
    default_start, default_end = inventory_horizon(property)
    start, end = start or default_start, end or default_end
    days = list(daterange(start, end))
    room_types = RoomType.objects.filter(property=property)
    if room_type_ids:
        room_types = room_types.filter(pk__in=list(room_type_ids))
    room_types = list(room_types.only("id", "kind"))
    if not days or not room_types:
        return RebuildResult()
    type_ids = [room_type.pk for room_type in room_types]
    dorm_ids = {room_type.pk for room_type in room_types if room_type.kind == RoomType.Kind.DORM}

    result = RebuildResult()
    with transaction.atomic():
        existing = set(
            InventoryDay.objects.filter(room_type_id__in=type_ids, date__gte=start, date__lt=end).values_list(
                "room_type_id", "date"
            )
        )
        missing = {(type_id, day) for type_id in type_ids for day in days} - existing
        if missing:
            # Inserted in the global lock order: concurrent materializations of overlapping ranges insert the
            # same keys, and inserting them in different orders (a set's order changes from process to
            # process) can deadlock. The text of a UUID sorts like PostgreSQL sorts the uuid.
            InventoryDay.objects.bulk_create(
                [
                    InventoryDay(property=property, room_type_id=type_id, date=day)
                    for type_id, day in sorted(missing, key=lambda key: (str(key[0]), key[1]))
                ],
                ignore_conflicts=True,
                batch_size=1000,
            )
        locked = list(
            InventoryDay.objects.select_for_update()
            .filter(room_type_id__in=type_ids, date__gte=start, date__lt=end)
            .order_by("room_type_id", "date")
        )
        # Counted after the rows are locked: stays written by transactions that held these locks are visible.
        totals, sold, blocked = _count_units(property, type_ids, dorm_ids, start, end)
        now = timezone.now()
        changed = []
        for row in locked:
            key = (row.room_type_id, row.date)
            values = {
                "total_units": totals[row.room_type_id],
                "sold_units": sold[key],
                "blocked_units": len(blocked[key]),
            }
            diffs = {
                name: [getattr(row, name), value]
                for name, value in values.items()
                if getattr(row, name) != value
            }
            if not diffs:
                continue
            for name, (_before, after) in diffs.items():
                setattr(row, name, after)
            row.updated_at = now
            changed.append(row)
            if key not in missing:
                result.updated += 1
                if len(result.drift) < MAX_DRIFT_DETAILS:
                    result.drift.append(
                        {"room_type_id": str(row.room_type_id), "date": row.date.isoformat(), **diffs}
                    )
        if changed:
            InventoryDay.objects.bulk_update(changed, [*UNIT_FIELDS, "updated_at"], batch_size=1000)
        result.created = len(missing)
    return result


def _count_units(property, type_ids, dorm_ids, start, end):
    totals: Counter = Counter(
        Room.objects.filter(room_type_id__in=set(type_ids) - dorm_ids, is_active=True).values_list(
            "room_type_id", flat=True
        )
    )
    active_beds: defaultdict = defaultdict(set)  # dorm room id → its active bed ids
    beds = Bed.objects.filter(room__room_type_id__in=dorm_ids, room__is_active=True, is_active=True)
    for bed_id, room_id, type_id in beds.values_list("id", "room_id", "room__room_type_id"):
        totals[type_id] += 1
        active_beds[room_id].add(bed_id)

    sold: Counter = Counter()
    stays = (
        Stay.objects.filter(
            reservation__property=property,
            status__in=ACTIVE_STAY_STATUSES,
            checkin_date__lt=end,
            checkout_date__gt=start,
        )
        .annotate(unit_type=Coalesce("room__room_type_id", "room_type_id"))
        .filter(unit_type__in=type_ids)
        .values_list("unit_type", "checkin_date", "checkout_date")
    )
    for type_id, checkin, checkout in stays:
        for night in daterange(max(checkin, start), min(checkout, end)):
            sold[(type_id, night)] += 1

    blocked: defaultdict = defaultdict(set)  # (type, night) → blocked unit ids (distinct)
    blocks = RoomBlock.objects.filter(
        room__room_type_id__in=type_ids,
        room__is_active=True,
        released_at__isnull=True,
        start_date__lt=end,
        end_date__gt=start,
    ).values_list("room_id", "room__room_type_id", "bed_id", "start_date", "end_date")
    for room_id, type_id, bed_id, block_start, block_end in blocks:
        if type_id in dorm_ids:
            units = (active_beds[room_id] & {bed_id}) if bed_id else active_beds[room_id]
        else:
            units = {room_id}
        for night in daterange(max(block_start, start), min(block_end, end)):
            blocked[(type_id, night)] |= units
    return totals, sold, blocked


def ensure_inventory(property, room_type_ids, start, end) -> None:
    """Materialize the rows of `[start, end)` that do not exist yet for these categories."""
    expected = (end - start).days
    if expected <= 0 or not room_type_ids:
        return
    counts = dict(
        InventoryDay.objects.filter(room_type_id__in=list(room_type_ids), date__gte=start, date__lt=end)
        .values("room_type_id")
        .annotate(n=Count("id"))
        .values_list("room_type_id", "n")
    )
    missing = [type_id for type_id in room_type_ids if counts.get(type_id, 0) < expected]
    if missing:
        rebuild_inventory(property, start, end, room_type_ids=missing)


def available_by_date(property, room_type_ids, start, end) -> dict:
    """{room_type_id: {date: available}} for `[start, end)`, from InventoryDay (missing rows are built)."""
    ensure_inventory(property, room_type_ids, start, end)
    result: dict = {type_id: {} for type_id in room_type_ids}
    rows = InventoryDay.objects.filter(
        room_type_id__in=list(room_type_ids), date__gte=start, date__lt=end
    ).values_list("room_type_id", "date", *UNIT_FIELDS)
    for type_id, day, total, sold, blocked in rows:
        result[type_id][day] = total - sold - blocked
    return result


def stay_units(stay) -> Counter:
    """{(unit category, night): 1} for every night of an active stay (its assigned room's category, else its
    booked category); empty for inactive stays."""
    if stay.status not in ACTIVE_STAY_STATUSES:
        return Counter()
    type_id = unit_type_id(stay)
    return Counter({(type_id, night): 1 for night in daterange(stay.checkin_date, stay.checkout_date)})


def unit_type_id(stay):
    """Category whose inventory the stay occupies: its assigned room's category, else its booked one."""
    if stay.room_id is not None:
        room = stay.room if stay.room.pk == stay.room_id else Room.objects.get(pk=stay.room_id)
        return room.room_type_id
    return stay.room_type_id


def adjust_inventory(property, deltas, *, allow_overbooking=False) -> list[dict]:
    """Apply `deltas` `{(room_type_id, date): ±units}` to `sold_units` under row locks.

    Positive deltas must fit in the availability of their night; otherwise AvailabilityError (409) — or, with
    `allow_overbooking`, the shortfalls are returned and applied anyway. Call it before writing the stays.
    """
    deltas = {key: delta for key, delta in deltas.items() if delta}
    if not deltas:
        return []
    days_by_type: defaultdict = defaultdict(list)
    for type_id, day in deltas:
        days_by_type[type_id].append(day)
    ranges = {type_id: (min(days), max(days) + timedelta(days=1)) for type_id, days in days_by_type.items()}

    with transaction.atomic():
        # materialize in the global lock order too (a rebuild locks the rows of its category)
        for type_id, (start, end) in sorted(ranges.items(), key=lambda item: str(item[0])):
            ensure_inventory(property, [type_id], start, end)
        condition = Q()
        for type_id, (start, end) in ranges.items():
            condition |= Q(room_type_id=type_id, date__gte=start, date__lt=end)
        rows = {
            (row.room_type_id, row.date): row
            for row in InventoryDay.objects.select_for_update()
            .filter(condition)
            .order_by("room_type_id", "date")
        }
        shortfalls = [
            {
                "room_type_id": str(type_id),
                "date": day.isoformat(),
                "available": rows[(type_id, day)].available,
                "requested": delta,
            }
            for (type_id, day), delta in sorted(
                deltas.items(), key=lambda item: (str(item[0][0]), item[0][1])
            )
            if delta > 0 and rows[(type_id, day)].available < delta
        ]
        if shortfalls and not allow_overbooking:
            raise AvailabilityError(_shortfall_message(shortfalls), shortfalls=shortfalls)
        now = timezone.now()
        changed = []
        for key, delta in deltas.items():
            row = rows[key]
            sold = row.sold_units + delta
            if sold < 0:
                logger.warning(
                    "InventoryDay %s %s would go negative (%s); clamped to 0", key[0], key[1], sold
                )
                sold = 0
            row.sold_units, row.updated_at = sold, now
            changed.append(row)
        InventoryDay.objects.bulk_update(changed, ["sold_units", "updated_at"])
    return shortfalls


def _shortfall_message(shortfalls) -> str:
    first = shortfalls[0]
    code = RoomType.objects.filter(pk=first["room_type_id"]).values_list("code", flat=True).first() or ""
    return f"No hay disponibilidad en la categoría {code} para la noche del {first['date']}"
