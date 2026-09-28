"""Automations of messaging (spec §6), auto-discovered by core; beat schedules them from this registry."""

from celery.schedules import crontab

from apps.core.automation import Automation, register
from apps.messaging.lifecycle import run_lifecycle_dispatch

register(
    Automation(
        code="messaging.lifecycle_dispatch",
        app="messaging",
        name_es="Mensajes automáticos del huésped",
        name_en="Automatic guest messages",
        description_es=(
            "Envía los mensajes programados del ciclo del huésped (antes de la llegada con el link de "
            "check-in, "
            "día de llegada, después de la estadía y recordatorio de pago) según las reglas de Mensajería, a "
            "partir de la hora configurada, y reintenta los envíos fallidos."
        ),
        description_en=(
            "Sends the scheduled guest-lifecycle messages (pre-arrival with the check-in link, arrival day, "
            "post-stay and payment reminder) following the Messaging rules, from the configured time, and "
            "retries failed deliveries."
        ),
        schedule=crontab(minute="*/10"),
        handler=run_lifecycle_dispatch,
    )
)
