"""Signals of `guests` for the apps of later phases. Sent with apps.core.signals.send_on_commit (only after
the transaction commits; a failing receiver is logged and never breaks the others). Subscribe from your
app's `receivers.py`.

- guest_anonymized(guest, merged_ids): the guest's personal data was erased on request (Habeas Data, Ley
  1581). Apps that keep their own copy of that data (message threads, drafts, exports…) erase or detach it.
  `merged_ids` are the records merged into the guest earlier, erased too. Records the law obliges to keep
  (invoices, SIRE/TRA reports) follow their own retention rules.
- guests_merged(primary, duplicate): `duplicate` was merged into `primary`. Every foreign key and many-to-many
  to Guest was already moved to `primary` (generically, see merge_guests); apps that reference guests any
  other way (ids inside JSON, external mappings) update them here.
"""

from django.dispatch import Signal

guest_anonymized = Signal()  # guest: Guest, merged_ids: list[UUID]
guests_merged = Signal()  # primary: Guest, duplicate: Guest (now with merged_into=primary)
