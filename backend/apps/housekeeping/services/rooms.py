"""Room cleaning status set from housekeeping (`POST rooms/{id}/status/`).

Inventory's own endpoint needs `inventory.manage`, which housekeeping roles lack; this proxy writes through
the contract `inventory.set_housekeeping_status` (audited with the actor, `room_status_changed` on commit, so
the "room turned dirty" receiver creates its clean). Who may set which status is decided by the API (clean /
dirty for housekeepers, any status for supervisors); here: a room held out of service by an open maintenance
ticket stays out of service until the ticket is resolved or unblocked.
"""

from apps.core.errors import ConflictError
from apps.housekeeping.models import MaintenanceTicket
from apps.inventory.models import Room
from apps.inventory.services import set_housekeeping_status

OPEN_TICKET_STATUSES = (MaintenanceTicket.Status.OPEN, MaintenanceTicket.Status.IN_PROGRESS)


def blocking_ticket(room) -> MaintenanceTicket | None:
    return (
        MaintenanceTicket.objects.filter(room=room, blocks_room=True, status__in=OPEN_TICKET_STATUSES)
        .order_by("created_at")
        .first()
    )


def set_room_status(room, status: str, *, actor) -> Room:
    ticket = blocking_ticket(room)
    if ticket is not None and status != Room.HousekeepingStatus.OUT_OF_SERVICE:
        raise ConflictError(
            f"La habitación {room.number} está bloqueada por el ticket de mantenimiento «{ticket.title}»: "
            "resuélvelo o quita el bloqueo primero",
            code="room_blocked",
            ticket_id=ticket.pk,
        )
    return set_housekeeping_status(room, status, actor=actor, source="user")
