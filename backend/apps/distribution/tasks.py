"""Celery tasks of distribution (auto-discovered by config/celery.py)."""

from celery import shared_task


@shared_task(name="distribution.push_ari_queue", ignore_result=True)
def push_ari_queue(property_id: str) -> None:
    """Debounced push (scheduled with `countdown` by `services.queue.schedule_push`): sends every pending ARI
    update of the property. The `distribution.push_ari` automation sweeps what is left every minute."""
    from apps.core.models import Property
    from apps.distribution.services.queue import process_queue

    prop = Property.objects.filter(pk=property_id).first()
    if prop is not None:
        process_queue(prop)
