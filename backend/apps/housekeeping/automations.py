"""Automations of housekeeping (spec §6): daily task generation at 07:00 and auto-assignment at 07:15."""

from celery.schedules import crontab

from apps.core.automation import Automation, RunResult, register
from apps.housekeeping.services.assignment import auto_assign
from apps.housekeeping.services.config import get_settings
from apps.housekeeping.services.generation import generate_daily_tasks


def generate_daily_tasks_handler(property, params) -> RunResult:
    report = generate_daily_tasks(property)
    return RunResult(
        summary=(
            f"{report['created']} tareas creadas: {report['departures']} salidas, "
            f"{report['stayovers']} repasos y {report['dirty_rooms']} habitaciones sucias"
        ),
        details=report,
    )


def auto_assign_handler(property, params) -> RunResult:
    if not get_settings(property).auto_assign:
        return RunResult(status="skipped", summary="La asignación automática está desactivada en este hotel")
    report = auto_assign(property)
    if not report["staff"]:
        status = "partial" if report["unassigned"] else "skipped"
        return RunResult(
            status=status, summary="No hay personal de limpieza con acceso a este hotel", details=report
        )
    summary = f"{report['assigned']} tareas asignadas entre {len(report['staff'])} personas"
    return RunResult(status="partial" if report["unassigned"] else "success", summary=summary, details=report)


register(
    Automation(
        code="housekeeping.generate_daily_tasks",
        app="housekeeping",
        name_es="Tareas de limpieza del día",
        name_en="Daily housekeeping tasks",
        description_es=(
            "Crea las limpiezas de salida esperadas, los repasos de los huéspedes en casa según la "
            "frecuencia configurada y las tareas de las habitaciones sucias."
        ),
        description_en=(
            "Creates the expected departure cleans, the stayovers of in-house guests at the configured "
            "frequency and the tasks of dirty rooms."
        ),
        schedule=crontab(hour=7, minute=0),
        handler=generate_daily_tasks_handler,
    )
)

register(
    Automation(
        code="housekeeping.auto_assign",
        app="housekeeping",
        name_es="Asignación automática de limpieza",
        name_en="Housekeeping auto-assignment",
        description_es=(
            "Reparte las tareas pendientes del día entre el personal de limpieza, equilibrando los minutos y "
            "agrupando por piso."
        ),
        description_en=(
            "Shares the day's pending tasks between housekeepers, balancing minutes and grouping by floor."
        ),
        schedule=crontab(hour=7, minute=15),
        handler=auto_assign_handler,
    )
)
