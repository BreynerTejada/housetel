"""Daily task generation (automation `housekeeping.generate_daily_tasks`, 07:00).

For the business date of the property, per active room (out-of-service rooms are skipped):
1. Expected departures (in-house stays whose check-out is today or overdue) → departure clean, high priority
   when a guest arrives today in the room. The room stays as it is until the check-out makes it dirty.
2. Stayovers: in-house stays continuing tonight, every `stayover_frequency_days` nights since arrival (0 = no
   stayover service) → stayover; the room turns dirty until it is serviced.
3. Dirty rooms without an open clean → departure clean (vacant) or stayover (occupied).

Idempotent: a room that already had a departure/stayover task today (in any status: done, cancelled…) is not
planned again, and an open clean from an earlier day is reused instead of duplicated.
"""

from django.db import transaction

from apps.bookings.models import Stay
from apps.housekeeping.models import HousekeepingTask
from apps.housekeeping.services.common import TURNOVER_KINDS, Kind
from apps.housekeeping.services.config import get_settings
from apps.housekeeping.services.tasks import ensure_turnover_task, open_cleaning_task
from apps.inventory.models import Room
from apps.inventory.services import set_housekeeping_status

Status = Room.HousekeepingStatus
DAILY = HousekeepingTask.Source.DAILY


def generate_daily_tasks(property, *, actor=None) -> dict:
    today = property.business_date
    frequency = get_settings(property).stayover_frequency_days
    rooms = {
        room.pk: room
        for room in Room.objects.filter(property=property, is_active=True)
        .exclude(housekeeping_status=Status.OUT_OF_SERVICE)
        .select_related("room_type", "property")
    }
    departures, stayovers = {}, {}
    in_house = Stay.objects.filter(
        reservation__property=property, status="checked_in", room_id__in=list(rooms)
    ).select_related("reservation", "bed")
    for stay in in_house.order_by("checkin_date", "created_at"):
        if stay.checkout_date <= today:
            departures.setdefault(stay.room_id, []).append(stay)
        elif frequency and (today - stay.checkin_date).days >= 1:
            if (today - stay.checkin_date).days % frequency == 0:
                stayovers.setdefault(stay.room_id, stay)
    planned_today = set(
        HousekeepingTask.objects.filter(
            property=property, business_date=today, kind__in=TURNOVER_KINDS
        ).values_list("room_id", flat=True)
    )
    report = {"created": 0, "stayovers": 0, "departures": 0, "dirty_rooms": 0, "rooms_marked_dirty": 0}

    def plan(room, kind, *, reservation=None, bed=None) -> bool:
        if room.pk in planned_today and open_cleaning_task(room) is None:
            return False  # already handled today
        _task, created = ensure_turnover_task(
            room, kind=kind, source=DAILY, reservation=reservation, bed=bed, actor=actor
        )
        report["created"] += created
        return created

    with transaction.atomic():
        for room_id, stays in departures.items():
            room = rooms[room_id]
            for stay in stays:
                report["departures"] += plan(
                    room, Kind.DEPARTURE_CLEAN, reservation=stay.reservation, bed=stay.bed
                )
        for room_id, stay in stayovers.items():
            room = rooms[room_id]
            if plan(room, Kind.STAYOVER, reservation=stay.reservation):
                report["stayovers"] += 1
                if room.housekeeping_status in (Status.CLEAN, Status.INSPECTED):
                    source = "user" if getattr(actor, "is_authenticated", False) else "automation"
                    set_housekeeping_status(room, Status.DIRTY, actor=actor, source=source)
                    report["rooms_marked_dirty"] += 1
        for room in rooms.values():
            if room.housekeeping_status != Status.DIRTY or room.pk in departures or room.pk in stayovers:
                continue
            occupied = (
                Stay.objects.filter(room=room, status="checked_in").select_related("reservation").first()
            )
            kind = Kind.STAYOVER if occupied else Kind.DEPARTURE_CLEAN
            report["dirty_rooms"] += plan(room, kind, reservation=occupied.reservation if occupied else None)
    return report
