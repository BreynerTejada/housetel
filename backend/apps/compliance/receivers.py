"""Compliance receivers (auto-discovered by apps.core at startup).

- `stay_checked_out` → when the last stay of the reservation leaves, issue its electronic invoice (if the
  hotel
  invoices automatically).
- `stay_checked_in` → register the TRA (Tarjeta de Registro Alojamiento) of every guest of the stay.

Both ignore the demo seed's replay of history (`is_seeding()`): `apps/compliance/seed.py` creates the invoices
and TRA registrations of the recent past explicitly.
"""

import logging

from django.dispatch import receiver

from apps.core import signals
from apps.core.signals import is_seeding

logger = logging.getLogger("housetel.compliance")


@receiver(signals.stay_checked_out, dispatch_uid="compliance.issue_invoice_on_checkout")
def issue_invoice_on_checkout(sender, stay, **kwargs):
    if is_seeding():
        return
    from apps.compliance.services.invoices import auto_issue_on_checkout

    auto_issue_on_checkout(stay)


@receiver(signals.stay_checked_in, dispatch_uid="compliance.register_tra_on_checkin")
def register_tra_on_checkin(sender, stay, **kwargs):
    if is_seeding():
        return
    from apps.compliance.services.tra import auto_register_on_checkin

    auto_register_on_checkin(stay)
