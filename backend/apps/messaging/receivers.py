"""Domain-signal receivers of messaging (auto-discovered by core). Every receiver with side effects returns
early while the demo seed replays history (`is_seeding`), otherwise the seed would send thousands of
emails."""

from django.dispatch import receiver

from apps.core.signals import is_seeding, reservation_cancelled, reservation_created, reservation_updated
from apps.guests.signals import guest_anonymized
from apps.messaging.lifecycle import dispatch_event, was_dispatched
from apps.messaging.services import erase_guest_conversations


@receiver(reservation_created, dispatch_uid="messaging.confirmation_on_create")
def confirmation_on_create(sender, reservation, **kwargs):
    if is_seeding():
        return
    if reservation.status == "confirmed":
        dispatch_event(reservation, "confirmation")


@receiver(reservation_updated, dispatch_uid="messaging.confirmation_on_update")
def confirmation_on_update(sender, reservation, changes=None, **kwargs):
    if is_seeding():
        return
    status = (changes or {}).get("status")
    if status and tuple(status)[-1] == "confirmed":
        dispatch_event(reservation, "confirmation")


@receiver(reservation_cancelled, dispatch_uid="messaging.cancellation")
def cancellation(sender, reservation, **kwargs):
    if is_seeding():
        return
    # A tentative hold that expired or was dropped was never confirmed to the guest: release it silently.
    if reservation.hold_expires_at is not None and not was_dispatched(reservation, "confirmation"):
        return
    dispatch_event(reservation, "cancellation")


@receiver(guest_anonymized, dispatch_uid="messaging.erase_guest_conversations")
def erase_anonymized_guest(sender, guest, merged_ids=(), **kwargs):
    """Not a side effect but data protection: runs during the seed too."""
    erase_guest_conversations([guest.pk, *(merged_ids or [])])
