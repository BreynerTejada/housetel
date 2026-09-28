"""Signal receivers of distribution (auto-discovered by apps.core.apps.CoreConfig.ready).

Inventory and rate changes queue ARI for the channels (`services.queue.enqueue_ari`). The demo seed replays
thousands of historical signals: while it runs nothing is queued (`is_seeding()`); `distribution/seed.py` does
one explicit full sync per connection instead.

Deleting a rate plan emits no `rates_changed` (B2a): `pre_delete` of RatePlan (only listened to, never
written) queues the connections that map it, so the channel receives the rate closed (its mapping keeps
`rate_plan` null; see `services.ari`).
"""

from django.db import transaction
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.core import signals
from apps.core.signals import is_seeding
from apps.distribution.services.queue import enqueue_ari
from apps.rates.models import RatePlan


@receiver(signals.inventory_changed, dispatch_uid="distribution.ari_on_inventory_changed")
def ari_on_inventory_changed(sender, property=None, room_type_ids=None, start=None, end=None, **kwargs):
    """Availability moved (reservations, blocks, rooms…): queue it. Unlike bookings, events with
    `origin="bookings"` count too: those are exactly the reservations the channels must hear about."""
    if is_seeding() or property is None:
        return
    enqueue_ari(property, room_type_ids=room_type_ids or None, start=start, end=end, kinds=("availability",))


@receiver(signals.rates_changed, dispatch_uid="distribution.ari_on_rates_changed")
def ari_on_rates_changed(
    sender, property=None, room_type_ids=None, rate_plan_ids=None, start=None, end=None, **kwargs
):
    """Prices or restrictions changed (grid, plans, defaults, seasons, revenue): queue them."""
    if is_seeding() or property is None:
        return
    enqueue_ari(
        property,
        room_type_ids=room_type_ids or None,
        rate_plan_ids=rate_plan_ids or None,
        start=start,
        end=end,
        kinds=("rates", "restrictions"),
    )


@receiver(pre_delete, sender=RatePlan, dispatch_uid="distribution.ari_on_rate_plan_deleted")
def ari_on_rate_plan_deleted(sender, instance, **kwargs):
    """A mapped plan is being deleted: once committed, push its (now closed) rates to those connections."""
    if is_seeding():
        return
    from apps.distribution.models import ChannelConnection

    connections = list(ChannelConnection.objects.filter(rate_mappings__rate_plan=instance).distinct())
    if not connections:
        return
    property = instance.property

    def _enqueue():
        for connection in connections:
            enqueue_ari(property, connection=connection, kinds=("rates", "restrictions"))

    transaction.on_commit(_enqueue)
