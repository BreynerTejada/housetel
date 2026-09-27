"""Physical occupancy queries shared by assignment, modification and check-in (no writes here)."""

from django.db.models import Q

from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay
from apps.bookings.types import AvailabilityError
from apps.inventory.models import RoomBlock

READY_STATUSES = ("clean", "inspected")


def overlapping_stays(stay, checkin=None, checkout=None):
    """Other active stays overlapping `[checkin, checkout)` (default: the stay's own dates)."""
    return Stay.objects.filter(
        status__in=ACTIVE_STAY_STATUSES,
        checkin_date__lt=checkout or stay.checkout_date,
        checkout_date__gt=checkin or stay.checkin_date,
    ).exclude(pk=stay.pk)


def is_occupied(stay, room, bed, checkin=None, checkout=None) -> bool:
    """Someone else sleeps in that room (private) or bed (dorm) on some of those nights."""
    others = overlapping_stays(stay, checkin, checkout)
    if bed is not None:
        return others.filter(bed=bed).exists()
    return others.filter(room=room, bed__isnull=True).exists()


def is_blocked(room, bed, start, end) -> bool:
    """An active block covers the room (or, for a bed, its dorm room or the bed) in `[start, end)`."""
    blocks = RoomBlock.objects.filter(
        room=room, released_at__isnull=True, start_date__lt=end, end_date__gt=start
    )
    if bed is None:
        return blocks.exists()
    return blocks.filter(Q(bed__isnull=True) | Q(bed=bed)).exists()


def free_bed(stay, room):
    """First active bed of the dorm room (by label) free and unblocked for the whole stay."""
    taken = set(overlapping_stays(stay).filter(room=room).values_list("bed_id", flat=True))
    for bed in room.beds.filter(is_active=True).order_by("label"):
        if bed.pk not in taken and not is_blocked(room, bed, stay.checkin_date, stay.checkout_date):
            return bed
    raise AvailabilityError("No quedan camas libres en esta habitación para esas fechas")
