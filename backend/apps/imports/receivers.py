"""Receivers of imports (auto-discovered by core).

- Habeas Data: when a guest is anonymized, the cells of the import rows that brought their data in are erased
  too — an import file must not keep a copy of what the guest asked to delete.
- A merged guest: the idempotency records that pointed to the duplicate now point to the primary, so a new
  import of the same file updates the surviving guest.
"""

from django.dispatch import receiver

from apps.core.signals import is_seeding
from apps.guests.signals import guest_anonymized, guests_merged


@receiver(guest_anonymized, dispatch_uid="imports.erase_anonymized_guest_rows")
def erase_anonymized_guest_rows(sender, guest=None, merged_ids=(), **kwargs):
    if is_seeding() or guest is None:
        return
    from apps.imports.retention import erase_guest_rows

    erase_guest_rows([guest.pk, *(merged_ids or [])])


@receiver(guests_merged, dispatch_uid="imports.follow_guest_merge")
def follow_guest_merge(sender, primary=None, duplicate=None, **kwargs):
    if is_seeding() or primary is None or duplicate is None:
        return
    from apps.imports.models import ImportedRecord

    ImportedRecord.objects.filter(target_type="guests.guest", target_id=duplicate.pk).update(
        target_id=primary.pk
    )
