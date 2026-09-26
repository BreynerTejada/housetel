"""Availability — contracts fixed in Phase A (spec §4.2); B2b moves `availability` to InventoryDay
and implements `search_offers` (plan B2b)."""

from collections import Counter, defaultdict
from uuid import UUID

from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay
from apps.bookings.types import Offer
from apps.core.dates import nights as stay_nights
from apps.inventory.models import Bed, Room, RoomBlock, RoomType


def availability(*, property, checkin, checkout, room_type_ids=None) -> dict[UUID, int]:
    """Units still sellable per active room type for every night of `[checkin, checkout)` (the minimum).

    Units = active rooms (private) or active beds in active rooms (dorm). Per night: units − active
    stays covering the night (assigned or not) − active blocks (a whole dorm room blocks all its active
    beds). The result is negative when a category is overbooked. Empty/invalid ranges return 0 for every type.
    Phase A computes it from the source tables (correct but slow).
    """
    room_types = RoomType.objects.filter(property=property, is_active=True)
    if room_type_ids is not None:
        room_types = room_types.filter(pk__in=list(room_type_ids))
    room_types = list(room_types)
    nights = stay_nights(checkin, checkout)
    if not nights:
        return {room_type.pk: 0 for room_type in room_types}

    type_ids = [room_type.pk for room_type in room_types]
    dorm_ids = {room_type.pk for room_type in room_types if room_type.kind == RoomType.Kind.DORM}

    totals: Counter = Counter(
        Room.objects.filter(room_type_id__in=set(type_ids) - dorm_ids, is_active=True).values_list(
            "room_type_id", flat=True
        )
    )
    dorm_beds = list(
        Bed.objects.filter(room__room_type_id__in=dorm_ids, room__is_active=True, is_active=True).values_list(
            "room_id", "room__room_type_id"
        )
    )
    totals.update(room_type_id for _room_id, room_type_id in dorm_beds)
    active_beds_per_room = Counter(room_id for room_id, _room_type_id in dorm_beds)

    taken: defaultdict = defaultdict(int)  # (room_type_id, night) → units
    stays = Stay.objects.filter(
        room_type_id__in=type_ids,
        status__in=ACTIVE_STAY_STATUSES,
        checkin_date__lt=checkout,
        checkout_date__gt=checkin,
    ).values_list("room_type_id", "checkin_date", "checkout_date")
    for room_type_id, start, end in stays:
        for night in nights:
            if start <= night < end:
                taken[(room_type_id, night)] += 1

    blocks = RoomBlock.objects.filter(
        room__room_type_id__in=type_ids,
        room__is_active=True,
        released_at__isnull=True,
        start_date__lt=checkout,
        end_date__gt=checkin,
    ).select_related("room", "bed")
    for block in blocks:
        room_type_id = block.room.room_type_id
        if room_type_id in dorm_ids:
            units = (1 if block.bed.is_active else 0) if block.bed_id else active_beds_per_room[block.room_id]
        else:
            units = 1
        for night in nights:
            if block.start_date <= night < block.end_date:
                taken[(room_type_id, night)] += units

    return {
        room_type.pk: min(totals[room_type.pk] - taken[(room_type.pk, night)] for night in nights)
        for room_type in room_types
    }


def search_offers(
    *,
    property,
    checkin,
    checkout,
    adults,
    children=0,
    children_ages=None,
    channel="direct",
    promo_code=None,
    guest_is_foreign_non_resident=False,
) -> list[Offer]:
    """Sellable offers (cheapest first): active categories with capacity ×
    applicable active plans (channel in plan.channels or channels empty; "direct" includes non-public plans,
    other channels only public ones) → quote → kept when `restrictions_ok` and availability ≥ units needed."""
    raise NotImplementedError("bookings.search_offers: B2b implementa esta función")
