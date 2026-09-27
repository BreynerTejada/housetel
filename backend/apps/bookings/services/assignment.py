"""Choosing rooms/beds for stays: check-in auto-assignment (`best_unit`) and the candidates/scoring used by
`reservations.auto_assign_rooms`.

A unit is a private room or a dorm bed. Its `busy` intervals are the active stays and active blocks on it (a
dorm room block makes all its beds busy). Scoring, lowest first:
1. not ready (neither clean nor inspected) when the guest arrives today or is late;
2. for a group that already has rooms: not connected to any of them (`Room.connecting_rooms`);
3. outside the group's zone (floor for private rooms, the dorm room for beds);
4. fragmentation: whether the previous or next busy interval touches the stay (a 0-night gap), then the
   smallest gap;
5. the room order (sort order, number, bed label).
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Prefetch

from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay
from apps.bookings.services.rooms import READY_STATUSES
from apps.inventory.models import Bed, Room, RoomBlock, RoomType

GAP_WINDOW_DAYS = 60  # busy intervals this far around the stays are loaded to measure gaps
FAR = 10_000


@dataclass
class Unit:
    room: Room
    bed: Bed | None
    zone: str  # what a group shares: the floor (private) or the dorm room (beds)
    order: int
    busy: list = field(default_factory=list)  # [(start, end)] half-open

    @property
    def unit_id(self):
        return self.bed.pk if self.bed is not None else self.room.pk

    def is_free(self, start, end) -> bool:
        return all(not (busy_start < end and start < busy_end) for busy_start, busy_end in self.busy)

    def gap(self, start, end) -> int:
        """Nights between the stay and the closest busy interval before or after it (FAR when none)."""
        before = [(start - busy_end).days for _, busy_end in self.busy if busy_end <= start]
        after = [(busy_start - end).days for busy_start, _ in self.busy if busy_start >= end]
        return min([*before, *after, FAR])


def load_units(prop, room_type_ids, start, end) -> dict:
    """{room_type_id: [Unit]} of the active rooms / beds of these categories, in room order, with their busy
    intervals overlapping `[start, end)`."""
    units: defaultdict = defaultdict(list)
    by_room, by_bed, beds_of_room = {}, {}, defaultdict(list)
    rooms = (
        Room.objects.filter(property=prop, room_type_id__in=list(room_type_ids), is_active=True)
        .select_related("room_type")
        .prefetch_related(
            Prefetch(
                "beds", queryset=Bed.objects.filter(is_active=True).order_by("label"), to_attr="active_beds"
            )
        )
        .order_by("sort_order", "number")
    )
    dorm_rooms = []
    for room in rooms:
        if room.room_type.kind == RoomType.Kind.DORM:
            dorm_rooms.append(room)
            continue
        unit = Unit(room, None, room.floor or "", order=len(by_room) + len(by_bed))
        units[room.room_type_id].append(unit)
        by_room[room.pk] = unit
    for room in dorm_rooms:
        for bed in room.active_beds:
            unit = Unit(room, bed, f"dorm:{room.pk}", order=len(by_room) + len(by_bed))
            units[room.room_type_id].append(unit)
            by_bed[bed.pk] = unit
            beds_of_room[room.pk].append(unit)
    room_ids = [*by_room, *beds_of_room]
    stays = Stay.objects.filter(
        status__in=ACTIVE_STAY_STATUSES, room_id__in=room_ids, checkin_date__lt=end, checkout_date__gt=start
    ).values_list("room_id", "bed_id", "checkin_date", "checkout_date")
    for room_id, bed_id, checkin, checkout in stays:
        unit = by_bed.get(bed_id) if bed_id else by_room.get(room_id)
        if unit is not None:
            unit.busy.append((checkin, checkout))
    blocks = RoomBlock.objects.filter(
        room_id__in=room_ids, released_at__isnull=True, start_date__lt=end, end_date__gt=start
    ).values_list("room_id", "bed_id", "start_date", "end_date")
    for room_id, bed_id, block_start, block_end in blocks:
        if bed_id:
            targets = [by_bed[bed_id]] if bed_id in by_bed else []
        else:
            targets = [by_room[room_id]] if room_id in by_room else beds_of_room.get(room_id, [])
        for unit in targets:
            unit.busy.append((block_start, block_end))
    return units


def rank(stay, candidates, *, today, zone=None, near=None) -> list:
    """Candidates (free units) from best to worst for this stay. `near`: rooms connected to the rooms the
    stay's group already has (None / empty when there are none)."""
    arriving = stay.checkin_date <= today

    def score(unit):
        gap = unit.gap(stay.checkin_date, stay.checkout_date)
        return (
            arriving and unit.room.housekeeping_status not in READY_STATUSES,
            bool(near) and unit.room.pk not in near,
            zone is not None and unit.zone != zone,
            gap != 0,
            gap,
            unit.order,
        )

    return sorted(candidates, key=score)


def preferred_zone(candidates):
    """For the first member of a group: the zone with the most free units (ties: the first in room order)."""
    counts = Counter(unit.zone for unit in candidates)
    first_seen = {}
    for unit in candidates:
        first_seen.setdefault(unit.zone, unit.order)
    return max(counts, key=lambda zone: (counts[zone], -first_seen[zone])) if counts else None


def room_connections(prop) -> dict:
    """{room_id: {ids of the rooms connected to it}} for the property (the relation is symmetrical)."""
    connections = defaultdict(set)
    through = Room.connecting_rooms.through.objects.filter(from_room__property=prop)
    for from_id, to_id in through.values_list("from_room_id", "to_room_id"):
        connections[from_id].add(to_id)
        connections[to_id].add(from_id)
    return connections


def free_units(stay, units):
    return [unit for unit in units if unit.is_free(stay.checkin_date, stay.checkout_date)]


def room_options(stay) -> list[dict]:
    """Where the stay can go (assign or move), best first: units free and unblocked for all its nights.

    Its own category first, ranked like the auto-assignment (ready rooms first when the guest is due or in
    house, no gaps, room order); then the other active categories of the same kind (private / dorm) that
    still have a unit left on every night — assigning one of those is an upgrade/downgrade (`assign` with
    `force`). The unit the stay already has is not listed. Each option: `{room_id, room_number, floor,
    room_type_id, room_type_code, bed_id, bed_label, housekeeping_status, ready, same_category}`."""
    from apps.bookings.services.availability import availability

    prop = stay.reservation.property
    room_types = {
        room_type.pk: room_type
        for room_type in RoomType.objects.filter(property=prop, is_active=True, kind=stay.room_type.kind)
    }
    others = [pk for pk in room_types if pk != stay.room_type_id]
    left = availability(
        property=prop, checkin=stay.checkin_date, checkout=stay.checkout_date, room_type_ids=others
    )
    offered = [stay.room_type_id] + sorted(
        (pk for pk in others if left.get(pk, 0) >= 1),
        key=lambda pk: (room_types[pk].sort_order, room_types[pk].code),
    )
    window = timedelta(days=GAP_WINDOW_DAYS)
    units = load_units(prop, offered, stay.checkin_date - window, stay.checkout_date + window)
    options = []
    for type_id in offered:
        for unit in rank(stay, free_units(stay, units.get(type_id, [])), today=prop.business_date):
            options.append(
                {
                    "room_id": str(unit.room.pk),
                    "room_number": unit.room.number,
                    "floor": unit.room.floor,
                    "room_type_id": str(type_id),
                    "room_type_code": room_types[type_id].code if type_id in room_types else "",
                    "bed_id": str(unit.bed.pk) if unit.bed else None,
                    "bed_label": unit.bed.label if unit.bed else None,
                    "housekeeping_status": unit.room.housekeeping_status,
                    "ready": unit.room.housekeeping_status in READY_STATUSES,
                    "same_category": type_id == stay.room_type_id,
                }
            )
    return options


def best_unit(stay):
    """(room, bed) of the stay's category free and unblocked for the whole stay, or (None, None)."""
    prop = stay.reservation.property
    start = stay.checkin_date - timedelta(days=GAP_WINDOW_DAYS)
    end = stay.checkout_date + timedelta(days=GAP_WINDOW_DAYS)
    units = load_units(prop, [stay.room_type_id], start, end).get(stay.room_type_id, [])
    ranked = rank(stay, free_units(stay, units), today=prop.business_date)
    return (ranked[0].room, ranked[0].bed) if ranked else (None, None)
