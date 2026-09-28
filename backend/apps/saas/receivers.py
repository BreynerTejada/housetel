"""SaaS receivers (auto-discovered): marketplace commissions and the soft plan limit.

Every receiver returns early while the demo seed runs (`is_seeding()`): the seed replays months of history;
`apps/saas/seed.py` creates the commissions of the seeded marketplace reservations explicitly.
"""

import logging

from django.dispatch import receiver

from apps.core.signals import (
    inventory_changed,
    is_seeding,
    reservation_cancelled,
    reservation_created,
    reservation_no_show,
    reservation_updated,
)

logger = logging.getLogger("housetel.saas")


def _sync(reservation) -> None:
    if is_seeding() or reservation is None or getattr(reservation, "source", None) != "marketplace":
        return
    from apps.saas.services.commissions import sync_commission

    sync_commission(reservation)


@receiver(reservation_created)
def commission_on_created(sender, reservation=None, **kwargs):
    _sync(reservation)


@receiver(reservation_updated)
def commission_on_updated(sender, reservation=None, **kwargs):
    _sync(reservation)


@receiver(reservation_cancelled)
def commission_on_cancelled(sender, reservation=None, **kwargs):
    _sync(reservation)


@receiver(reservation_no_show)
def commission_on_no_show(sender, reservation=None, **kwargs):
    _sync(reservation)


@receiver(inventory_changed)
def plan_limit_on_inventory(sender, property=None, origin=None, **kwargs):
    """Rooms or beds added / removed (not bookings, which don't change the unit count) → soft limit check."""
    if is_seeding() or origin == "bookings" or property is None:
        return
    from apps.saas.services.billing import check_plan_limit

    check_plan_limit(property.organization)
