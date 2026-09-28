"""Automations of the front desk (spec §6). Registered on import (auto-discovered by the core)."""

from celery.schedules import crontab

from apps.core.automation import Automation, register
from apps.frontdesk.services.night_audit import CODE, run_night_audit

register(
    Automation(
        code=CODE,
        app="frontdesk",
        name_es="Auditoría nocturna",
        name_en="Night audit",
        description_es=(
            "Cierra el día de negocio: publica el cargo de la noche de cada huésped en casa, marca como "
            "no-show las llegadas que no se presentaron, alerta las salidas vencidas, avanza la fecha de "
            "negocio y genera el reporte de cierre. Solo cierra días que ya terminaron."
        ),
        description_en=(
            "Closes the business day: posts tonight's room charge of every guest in house, marks arrivals "
            "that never came as no-shows, alerts overdue departures, moves the business date forward and "
            "writes the closing report. It only closes days that already ended."
        ),
        schedule=crontab(hour=2, minute=0),
        handler=run_night_audit,
    )
)
