"""Automations of `revenue` (spec §6): `revenue.run_rules`, daily at 05:00 and every 6 hours (05, 11, 17 and
23 h). Registered on import (auto-discovered by the core)."""

from celery.schedules import crontab

from apps.core.automation import Automation, RunResult, register
from apps.core.dates import property_now
from apps.revenue.models import RevenueRun
from apps.revenue.services.config import get_settings
from apps.revenue.services.runs import run_revenue


def wants_ai_summary(property, params, trigger) -> bool:
    """Whether this run asks the LLM for its summary. Manual runs always do (when `ai_summary` is on);
    scheduled ones only the first of the property's day while `ai_summary_once_a_day` is on (default): four
    runs a day on every hotel would spend most of a free Gemini quota on summaries nobody reads. The later
    runs keep the deterministic summary."""
    if not params.get("ai_summary", True):
        return False
    if trigger != RevenueRun.Trigger.AUTOMATION or not params.get("ai_summary_once_a_day", True):
        return True
    day_start = property_now(property).replace(hour=0, minute=0, second=0, microsecond=0)
    return not RevenueRun.objects.filter(
        property=property,
        trigger=RevenueRun.Trigger.AUTOMATION,
        started_at__gte=day_start,
        details__ai_status__in=["pending", "done"],
    ).exists()


def run_rules(property, params) -> RunResult:
    """Evaluate the rules of the property (skipped while revenue management is disabled).

    Params: `ai_summary` (default True) and `ai_summary_once_a_day` (default True, see `wants_ai_summary`).
    "Correr ahora" also passes `trigger="manual"` and `triggered_by`."""
    if not get_settings(property).enabled:
        return RunResult(status="skipped", summary="Revenue management está desactivado en esta propiedad")
    trigger = params.get("trigger")
    if trigger not in RevenueRun.Trigger.values:
        trigger = RevenueRun.Trigger.AUTOMATION
    actor = None
    if params.get("triggered_by"):
        from apps.accounts.models import User

        actor = User.objects.filter(pk=params["triggered_by"]).first()
    use_ai = wants_ai_summary(property, params, trigger)
    run = run_revenue(property, trigger=trigger, actor=actor, use_ai=use_ai)
    return RunResult(
        summary=run.summary.get("es", ""),
        details={
            "run_id": str(run.pk),
            "recommendations": run.recommendations_count,
            "auto_applied": run.auto_applied_count,
            "expired": run.expired_count,
        },
    )


register(
    Automation(
        code="revenue.run_rules",
        app="revenue",
        name_es="Reglas de revenue management",
        name_en="Revenue management rules",
        description_es=(
            "Evalúa las reglas de precio (ocupación, anticipación, día de la semana, festivos y eventos) de "
            "los próximos días y deja recomendaciones para aprobar, o las aplica si el hotel activó "
            "auto-aplicar."
        ),
        description_en=(
            "Evaluates the pricing rules (occupancy, lead time, weekday, holidays and events) for the coming "
            "days and leaves recommendations to approve, or applies them when the hotel turned on auto-apply."
        ),
        schedule=crontab(minute=0, hour="5,11,17,23"),
        handler=run_rules,
        default_params={"ai_summary": True, "ai_summary_once_a_day": True},
    )
)
