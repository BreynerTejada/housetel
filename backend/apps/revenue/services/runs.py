"""A revenue run (automation `revenue.run_rules`, "Correr ahora" and the demo seed).

`run_revenue` evaluates `[business date, business date + horizon)`: expires the pending recommendations of
past nights, stores the new ones (`engine.store_recommendations`), applies them when the property has
`auto_apply` (status `auto_applied`, rates written without actor → audit source "automation"), and writes the
deterministic summary. Runs of one property are serialized (its settings row is locked).

The AI summary is asked for only after the run commits (`transaction.on_commit`), in a background thread: a
slow or failing LLM (a real call takes several seconds) never keeps the run's transaction and row locks open,
nor makes "Correr ahora" wait. Until it answers, `ai_summary` holds the deterministic summary, `ai_provider`
stays empty and `details["ai_status"]` is "pending"; then it becomes "done" (LLM text stored) or
"unavailable" (simulated client, quota, network…: the deterministic summary stays). Runs without AI (the demo
seed) are "skipped". Under the test suite (`settings.TESTING`) the summary is written inline.
"""

import logging
import threading
from datetime import timedelta
from functools import partial

from django.conf import settings as django_settings
from django.db import connections, transaction
from django.utils import timezone

from apps.revenue.models import RateRecommendation, RevenueRun, RevenueSettings
from apps.revenue.services import summary
from apps.revenue.services.config import get_settings
from apps.revenue.services.decisions import DECISION_FIELDS, write_rates
from apps.revenue.services.engine import propose, store_recommendations

Status = RateRecommendation.Status
logger = logging.getLogger("housetel.revenue")

AI_PENDING, AI_DONE, AI_UNAVAILABLE, AI_SKIPPED = "pending", "done", "unavailable", "skipped"


def expire_past(property) -> int:
    """Pending recommendations of nights before the business date → expired; returns how many."""
    return RateRecommendation.objects.filter(
        property=property, status=Status.PENDING, date__lt=property.business_date
    ).update(status=Status.EXPIRED, updated_at=timezone.now())


def run_revenue(property, *, trigger=RevenueRun.Trigger.AUTOMATION, actor=None, use_ai=True) -> RevenueRun:
    user = actor if getattr(actor, "is_authenticated", False) else None
    with transaction.atomic():
        settings = RevenueSettings.objects.select_for_update().get(pk=get_settings(property).pk)
        start = property.business_date
        end = start + timedelta(days=settings.horizon_days)
        run = RevenueRun.objects.create(
            property=property, trigger=trigger, triggered_by=user, start_date=start, end_date=end
        )
        expired = expire_past(property)
        stored = store_recommendations(
            property, propose(property, start=start, end=end), start=start, end=end, run=run
        )
        auto_applied = 0
        if settings.auto_apply and stored.recommendations:
            write_rates(property, stored.recommendations, actor=None, status=Status.AUTO_APPLIED)
            RateRecommendation.objects.bulk_update(stored.recommendations, DECISION_FIELDS)
            auto_applied = sum(1 for rec in stored.recommendations if rec.status == Status.AUTO_APPLIED)
        stats = summary.run_stats(
            property, stored, start=start, end=end, auto_applied=auto_applied, expired=expired
        )
        run.summary = summary.template_summary(stats)
        run.ai_summary, run.ai_provider = run.summary, ""
        run.recommendations_count = stats["count"]
        run.auto_applied_count = auto_applied
        run.expired_count = expired
        run.details = {**stats, "ai_status": AI_PENDING if use_ai else AI_SKIPPED}
        run.status = RevenueRun.Status.SUCCESS
        run.finished_at = timezone.now()
        run.save()
        if use_ai:
            transaction.on_commit(partial(schedule_ai_summary, run.pk, stats), robust=True)
    return run


def schedule_ai_summary(run_id, stats: dict) -> None:
    """Write the AI summary of a committed run in a background thread (inline under the test suite)."""
    if getattr(django_settings, "TESTING", False):
        write_ai_summary(run_id, stats)
        return
    threading.Thread(
        target=_background_ai_summary, args=(run_id, stats), name=f"revenue-ai-{run_id}", daemon=True
    ).start()


def _background_ai_summary(run_id, stats: dict) -> None:
    try:
        write_ai_summary(run_id, stats)
    except Exception:  # noqa: BLE001 - a background summary must never crash the process
        logger.exception("Revenue AI summary failed (run=%s)", run_id)
    finally:
        connections.close_all()  # this thread's connections only


def write_ai_summary(run_id, stats: dict) -> None:
    """Ask the LLM for the summary of a committed run; keep the deterministic one when it has nothing."""
    run = RevenueRun.objects.select_related("property").filter(pk=run_id).first()
    if run is None:
        return
    text, provider = summary.ai_summary(run.property, stats)
    details = {**(run.details or {}), "ai_status": AI_DONE if provider else AI_UNAVAILABLE}
    fields = {"details": details, "updated_at": timezone.now()}
    if provider:
        fields.update(ai_summary=text, ai_provider=provider)
    RevenueRun.objects.filter(pk=run_id).update(**fields)
