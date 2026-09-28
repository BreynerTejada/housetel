"""Shared rules of the housekeeping services: task kinds, estimated minutes and room occupancy.

Occupancy is read from bookings (ORM reads are allowed across apps; writes go through contracts):
- occupied = a `checked_in` stay in the room (a departing guest still counts until the check-out);
- arrival today = a `tentative`/`confirmed` stay assigned to the room whose check-in is the business date.
"""

from apps.bookings.models import Stay
from apps.housekeeping.models import PRIORITY_RANK, HousekeepingTask

Kind = HousekeepingTask.Kind
Status = HousekeepingTask.Status

OPEN_STATUSES = (Status.PENDING, Status.IN_PROGRESS)
CLOSED_STATUSES = (Status.DONE, Status.INSPECTED, Status.CANCELLED)
TURNOVER_KINDS = (Kind.DEPARTURE_CLEAN, Kind.STAYOVER)  # at most one open per room (DB constraint)
CLEANING_KINDS = (Kind.DEPARTURE_CLEAN, Kind.STAYOVER, Kind.DEEP_CLEAN)  # finishing one cleans the room
ARRIVING_STATUSES = ("tentative", "confirmed")


def rank(priority: str) -> int:
    return PRIORITY_RANK.get(priority, 1)


def room_minutes(room) -> int:
    """Housekeeping minutes of a room: its override (Room.overrides) or its category's."""
    overrides = room.overrides if isinstance(room.overrides, dict) else {}
    value = overrides.get("housekeeping_minutes")
    try:
        minutes = int(value) if value not in (None, "") else room.room_type.housekeeping_minutes
    except (TypeError, ValueError):
        minutes = room.room_type.housekeeping_minutes
    return max(1, int(minutes or 1))


def estimated_minutes(room, kind: str) -> int:
    """Departure clean / other = the room's minutes; stayover = half (≥ 10); deep clean = double;
    inspection and turndown = 10."""
    base = room_minutes(room)
    if kind == Kind.STAYOVER:
        return max(10, (base + 1) // 2)
    if kind == Kind.DEEP_CLEAN:
        return base * 2
    if kind in (Kind.INSPECTION, Kind.TURNDOWN):
        return 10
    return base


def in_house_stay(room):
    """The `checked_in` stay occupying the room (any bed of a dorm), or None."""
    return (
        Stay.objects.filter(room=room, status="checked_in")
        .select_related("reservation")
        .order_by("checkin_date", "created_at")
        .first()
    )


def arrives_today(room, business_date) -> bool:
    return Stay.objects.filter(room=room, checkin_date=business_date, status__in=ARRIVING_STATUSES).exists()


def user_or_none(actor):
    return actor if getattr(actor, "is_authenticated", False) else None
