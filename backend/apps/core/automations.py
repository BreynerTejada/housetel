"""Automations owned by core."""

from datetime import timedelta

from celery.schedules import crontab
from django.contrib.sessions.models import Session
from django.utils import timezone

from apps.core.automation import Automation, RunResult, register
from apps.core.models import AutomationRun


def cleanup(property, params) -> RunResult:
    days = int(params.get("run_retention_days", 90))
    runs_deleted = AutomationRun.objects.filter(
        started_at__lt=timezone.now() - timedelta(days=days)
    ).delete()[0]
    sessions_deleted = Session.objects.filter(expire_date__lt=timezone.now()).delete()[0]
    return RunResult(
        summary=f"{runs_deleted} corridas antiguas y {sessions_deleted} sesiones expiradas eliminadas",
        details={"runs_deleted": runs_deleted, "sessions_deleted": sessions_deleted},
    )


register(
    Automation(
        code="core.cleanup",
        app="core",
        name_es="Limpieza del sistema",
        name_en="System cleanup",
        description_es="Elimina sesiones expiradas y el historial de automatizaciones con más de 90 días.",
        description_en="Deletes expired sessions and automation history older than 90 days.",
        schedule=crontab(hour=4, minute=30),
        handler=cleanup,
        scope="platform",
        default_params={"run_retention_days": 90},
    )
)
