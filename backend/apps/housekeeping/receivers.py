"""Domain signal receivers of housekeeping (auto-discovered by core).

- `stay_checked_out` → departure clean of the room (high priority if a guest arrives today in it), assigned
  at once to a housekeeper when the hotel assigns automatically (`services.assignment.assign_new_task`).
- `room_status_changed` → dirty without an open clean: a clean (stayover if occupied, else departure);
  clean / inspected set outside a task: its pending turnover cleans are cancelled. A room held out of service
  by a blocking maintenance ticket that a check-out turned dirty goes back to out of service (the check-out
  still gets its departure clean, which can be done during the repair; resolving or cancelling the ticket
  sends the room to cleaning).

The demo seed replays months of history through the booking services: while it runs these receivers do
nothing (`is_seeding()`); `apps/housekeeping/seed.py` creates today's tasks explicitly.
"""

from django.dispatch import receiver

from apps.core import signals
from apps.core.signals import is_seeding
from apps.housekeeping.models import HousekeepingTask
from apps.housekeeping.services.assignment import assign_new_task
from apps.housekeeping.services.common import Kind, in_house_stay
from apps.housekeeping.services.tasks import close_pending_turnovers, ensure_turnover_task
from apps.housekeeping.services.tickets import hold_blocked_room
from apps.inventory.models import Room


def _room(room_id):
    return Room.objects.select_related("room_type", "property").filter(pk=room_id).first()


@receiver(signals.stay_checked_out, dispatch_uid="housekeeping.departure_clean")
def create_departure_clean(sender, stay, **kwargs):
    if is_seeding() or stay.room_id is None:
        return
    room = _room(stay.room_id)
    if room is None:
        return
    task, created = ensure_turnover_task(
        room,
        kind=Kind.DEPARTURE_CLEAN,
        source=HousekeepingTask.Source.CHECKOUT,
        reservation=stay.reservation,
        bed=stay.bed,
    )
    if created:
        assign_new_task(task)


@receiver(signals.room_status_changed, dispatch_uid="housekeeping.room_status")
def follow_room_status(sender, room, old=None, new=None, **kwargs):
    if is_seeding():
        return
    if new == Room.HousekeepingStatus.DIRTY:
        room = _room(room.pk)
        if room is None:
            return
        if old == Room.HousekeepingStatus.OUT_OF_SERVICE and hold_blocked_room(room):
            return
        occupant = in_house_stay(room)
        task, created = ensure_turnover_task(
            room,
            kind=Kind.STAYOVER if occupant else Kind.DEPARTURE_CLEAN,
            source=HousekeepingTask.Source.STATUS_CHANGE,
            reservation=occupant.reservation if occupant else None,
        )
        if created:
            assign_new_task(task)
    elif new in (Room.HousekeepingStatus.CLEAN, Room.HousekeepingStatus.INSPECTED):
        close_pending_turnovers(room, new_status=new)
