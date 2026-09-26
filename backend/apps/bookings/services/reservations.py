"""Reservation lifecycle — signatures fixed in Phase A (spec §4.2), implemented by B2b (plan B2b).

Every function runs atomically, audits, and emits its domain signal with `core.signals.send_on_commit`.
Errors: `apps.bookings.types` (AvailabilityError 409, RestrictionError 400, InvalidStateError 409,
RoomNotReadyError 409, BalanceDueError 409).
"""

from apps.bookings.models import Reservation, Stay
from apps.bookings.types import AssignmentReport, ReservationRequest


def create_reservation(req: ReservationRequest, *, actor=None, source_label=None) -> Reservation:
    """Create a reservation: upsert booker, lock InventoryDay, validate capacity,
    availability and restrictions, quote (or use channel `nightly_rates`), create Reservation + Stays +
    folio, `reservation_created` and `inventory_changed`. Raises AvailabilityError (409) /
    RestrictionError (400)."""
    raise NotImplementedError("bookings.create_reservation: B2b implementa esta función")


def modify_stay(
    stay,
    *,
    checkin=None,
    checkout=None,
    room_type=None,
    rate_plan=None,
    adults=None,
    children=None,
    reprice=True,
    actor=None,
) -> Stay:
    """Change dates/category/plan/occupancy of a stay, moving inventory atomically;
    `reservation_updated`."""
    raise NotImplementedError("bookings.modify_stay: B2b implementa esta función")


def cancel_reservation(reservation, *, reason, waive_fee=False, actor=None, source="user") -> Reservation:
    """Cancel applying the policy snapshot penalty unless `waive_fee`;
    `reservation_cancelled`."""
    raise NotImplementedError("bookings.cancel_reservation: B2b implementa esta función")


def assign_room(stay, room, *, bed=None, actor=None, force=False) -> Stay:
    """Assign a room/bed. Overlap → AvailabilityError. Reversible audit; `room_assigned`."""
    raise NotImplementedError("bookings.assign_room: B2b implementa esta función")


def auto_assign_rooms(*, property, date_from, date_to, actor=None) -> AssignmentReport:
    """Assign rooms to unassigned stays arriving in the range."""
    raise NotImplementedError("bookings.auto_assign_rooms: B2b implementa esta función")


def check_in(stay, *, actor=None, force=False) -> Stay:
    """Check a stay in: assigned clean/inspected room, arrival ≤ business date; `stay_checked_in`."""
    raise NotImplementedError("bookings.check_in: B2b implementa esta función")


def check_out(stay, *, actor=None, force=False) -> Stay:
    """Check out: posts room charges, requires balance 0 (or force), room → dirty;
    `stay_checked_out`."""
    raise NotImplementedError("bookings.check_out: B2b implementa esta función")


def mark_no_show(reservation, *, actor=None, source="automation") -> Reservation:
    """Mark a past-due confirmed reservation as no-show, free inventory, charge the
    policy fee; `reservation_no_show`."""
    raise NotImplementedError("bookings.mark_no_show: B2b implementa esta función")
