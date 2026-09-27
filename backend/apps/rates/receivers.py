"""Signal receivers of `rates` (auto-discovered by core): promo code usage."""

from django.dispatch import receiver

from apps.core.signals import reservation_created
from apps.rates.services.promos import register_use


@receiver(reservation_created, dispatch_uid="rates.count_promo_use")
def count_promo_use(sender, reservation, **kwargs):
    """A reservation created with a promo code consumes one use of it (enforces `PromoCode.max_uses`)."""
    if reservation.promo_code:
        register_use(reservation.property, reservation.promo_code)
