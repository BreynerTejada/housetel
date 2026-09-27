"""Finance receivers (auto-discovered by apps.core at startup)."""

from django.dispatch import receiver

from apps.core import signals


@receiver(signals.stay_checked_out, dispatch_uid="finance.close_settled_folios")
def close_folios_on_checkout(sender, stay, **kwargs):
    """When every stay of the reservation has left and nothing is owed, close its folios (`folio_closed`)."""
    from apps.finance.services import close_settled_folios

    close_settled_folios(stay.reservation)
