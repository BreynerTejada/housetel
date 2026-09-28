"""Receivers of the guest portal (auto-discovered by core).

The online check-in keeps per-guest trip data under `OnlineCheckin.data["travel"][<guest_id>]` and the
booker's signature. They follow the CRM (B3 signals):
- `guest_anonymized` (Habeas Data): the guest's trip data goes away; if the guest booked, the signature and
  the evidence of the acceptance (IP, user agent) too.
- `guests_merged`: trip data keyed by the duplicate moves to the surviving profile.
"""

from django.db import transaction
from django.db.models import Q
from django.dispatch import receiver

from apps.core.signals import is_seeding
from apps.guestportal.models import OnlineCheckin
from apps.guests.signals import guest_anonymized, guests_merged


def _checkins_of(guest_ids):
    return (
        OnlineCheckin.objects.filter(
            Q(reservation__booker_id__in=guest_ids) | Q(reservation__stays__occupants__in=guest_ids)
        )
        .select_related("reservation")
        .distinct()
    )


@receiver(guest_anonymized, dispatch_uid="guestportal.forget_anonymized_guest")
def forget_anonymized_guest(sender, guest, merged_ids=(), **kwargs):
    if is_seeding():
        return
    ids = {str(guest.pk), *(str(pk) for pk in merged_ids or [])}
    for checkin in _checkins_of(list(ids)):
        data = dict(checkin.data or {})
        data["travel"] = {key: value for key, value in data.get("travel", {}).items() if key not in ids}
        data["documents"] = [item for item in data.get("documents", []) if item.get("guest_id") not in ids]
        checkin.data = data
        if str(checkin.reservation.booker_id) in ids:
            if checkin.signature:
                name, storage = checkin.signature.name, checkin.signature.storage
                transaction.on_commit(lambda name=name, storage=storage: storage.delete(name))
                checkin.signature = ""
            checkin.ip, checkin.user_agent = None, ""
        checkin.save()


@receiver(guests_merged, dispatch_uid="guestportal.follow_guest_merge")
def follow_guest_merge(sender, primary, duplicate, **kwargs):
    if is_seeding():
        return
    old, new = str(duplicate.pk), str(primary.pk)
    for checkin in OnlineCheckin.objects.filter(data__travel__has_key=old):
        data = dict(checkin.data or {})
        travel = dict(data.get("travel", {}))
        trip = travel.pop(old)
        travel.setdefault(new, trip)
        data["travel"] = travel
        data["documents"] = [
            {**item, "guest_id": new} if item.get("guest_id") == old else item
            for item in data.get("documents", [])
        ]
        checkin.data = data
        checkin.save(update_fields=["data", "updated_at"])
