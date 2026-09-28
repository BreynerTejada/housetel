"""Receivers of `revenue` (auto-discovered by the core).

`rates_changed` → the pending recommendations of those categories, plans and nights whose current price is no
longer the price of the night (e.g. someone set it by hand in the grid) expire: approving them would write a
price computed from stale figures over that decision. The next run proposes again from the new price.
Changes that leave the price as it was (a renamed plan) keep them. Ignored while the demo seed runs.
"""

from django.dispatch import receiver
from django.utils import timezone

from apps.core.money import quantize
from apps.core.signals import is_seeding, rates_changed
from apps.rates.services.quote import resolve_daily
from apps.revenue.models import RateRecommendation


@receiver(rates_changed, dispatch_uid="revenue.expire_stale_recommendations")
def expire_stale_recommendations(
    sender, property, room_type_ids, rate_plan_ids, start=None, end=None, **kwargs
):
    if is_seeding():
        return
    pending = RateRecommendation.objects.filter(
        property=property,
        status=RateRecommendation.Status.PENDING,
        room_type_id__in=list(room_type_ids or []),
        rate_plan_id__in=list(rate_plan_ids or []),
    ).select_related("room_type", "rate_plan")
    if start is not None:
        pending = pending.filter(date__gte=start)
    if end is not None:
        pending = pending.filter(date__lt=end)
    groups: dict = {}
    for rec in pending:
        groups.setdefault((rec.room_type_id, rec.rate_plan_id), []).append(rec)
    currency = property.currency or "COP"
    stale = []
    for recs in groups.values():
        first, last = min(rec.date for rec in recs), max(rec.date for rec in recs)
        days = resolve_daily(
            recs[0].room_type, recs[0].rate_plan, first, last.fromordinal(last.toordinal() + 1)
        )
        prices = {day.date: quantize(day.price, currency) for day in days}
        stale += [rec.pk for rec in recs if prices.get(rec.date) != rec.current_price]
    if stale:
        RateRecommendation.objects.filter(pk__in=stale).update(
            status=RateRecommendation.Status.EXPIRED, updated_at=timezone.now()
        )
