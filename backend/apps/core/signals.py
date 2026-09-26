"""Domain signals (spec §4.1). Producers call `send_on_commit`; consumers connect in
`apps/<app>/receivers.py`."""

import logging

from django.db import transaction
from django.dispatch import Signal

logger = logging.getLogger("housetel.signals")

reservation_created = Signal()  # reservation
reservation_updated = Signal()  # reservation, changes: dict[str, tuple[old, new]]
reservation_cancelled = Signal()  # reservation
reservation_no_show = Signal()  # reservation
stay_checked_in = Signal()  # stay
stay_checked_out = Signal()  # stay
room_assigned = Signal()  # stay, old_room
room_status_changed = Signal()  # room, old, new
inventory_changed = (
    Signal()
)  # property, room_type_ids: list, start: date | None, end: date | None (exclusive)
rates_changed = Signal()  # property, room_type_ids, rate_plan_ids, start, end (exclusive)
payment_received = Signal()  # payment
folio_closed = Signal()  # folio
guest_checked_in_online = Signal()  # reservation


def send_on_commit(signal: Signal, **kwargs) -> None:
    """Send `signal` after the current transaction commits. Receiver errors are logged, never raised."""

    def _send():
        for receiver, result in signal.send_robust(sender=None, **kwargs):
            if isinstance(result, Exception):
                logger.error("Receiver %r failed: %r", receiver, result, exc_info=result)

    transaction.on_commit(_send)
