"""Signal receivers and undo handlers of bookings (auto-discovered by apps.core.apps.CoreConfig.ready)."""

from django.dispatch import receiver

from apps.bookings.services.inventory import ORIGIN, rebuild_inventory
from apps.bookings.services.pricing import money_str
from apps.bookings.services.reservations import confirm_reservation, undo_room_change
from apps.core import alerts, audit, signals


@receiver(signals.inventory_changed, dispatch_uid="bookings.rebuild_on_inventory_changed")
def rebuild_on_inventory_changed(sender, property=None, room_type_ids=None, start=None, end=None, **kwargs):
    """Rooms, beds or blocks changed somewhere else (inventory, housekeeping, …): recompute the affected rows.

    `start`/`end` None means the whole horizon; empty `room_type_ids` means every category. Events emitted by
    bookings itself (`origin="bookings"`) are skipped: those operations already adjusted the rows in their
    own transaction.
    """
    if property is None or kwargs.get("origin") == ORIGIN:
        return
    rebuild_inventory(property, start, end, room_type_ids=room_type_ids or None)


@receiver(signals.payment_received, dispatch_uid="bookings.confirm_on_payment")
def confirm_on_payment(sender, payment=None, **kwargs):
    """An approved payment confirms a tentative reservation.

    On a cancelled reservation, paying what it still owes (its cancellation fee) is the normal flow; only a
    payment that leaves the guest with money in favor (reservation balance < 0: e.g. a hold that expired
    before the online payment was approved) needs a human — refund or rebook — so it raises
    `payment_after_cancellation` with that `credit`."""
    from apps.finance.services import reservation_balance

    if payment is None or payment.status != "approved" or payment.folio.reservation_id is None:
        return
    reservation = payment.folio.reservation
    if reservation.status == "tentative":
        confirm_reservation(reservation, source="system")
        return
    if reservation.status != "cancelled":
        return
    credit = -reservation_balance(reservation)
    if credit <= 0:
        return
    currency = payment.folio.currency
    alerts.raise_alert(
        property=reservation.property,
        kind="payment_after_cancellation",
        severity="warning",
        title=f"Pago recibido para la reserva cancelada {reservation.code}",
        message=(
            f"Llegó un pago de {money_str(payment.amount)} {currency} después de cancelar la reserva y queda "
            f"un saldo a favor del huésped de {money_str(credit)} {currency}. Reembólsalo o crea una nueva "
            "reserva."
        ),
        link=f"/app/reservations/{reservation.pk}",
        dedupe_key=f"bookings:payment_after_cancellation:{payment.pk}",
        data={
            "reservation_id": str(reservation.pk),
            "payment_id": str(payment.pk),
            "credit": money_str(credit),
        },
        source="system",
    )


audit.register_undo("bookings.room_assigned", undo_room_change)
audit.register_undo("bookings.room_unassigned", undo_room_change)
