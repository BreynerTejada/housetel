"""Automations of distribution (spec §6 + plan C3). Registered on import (auto-discovered by the core).

- `distribution.push_ari` (every minute): sends the ARI queue. Signals already schedule a debounced Celery
  push 5 seconds after each change; this sweep sends what is left (retries whose backoff expired, pushes lost
  with a worker restart).
- `distribution.pull_ical` (every 15 minutes): imports the remote iCal calendars.
- `distribution.pull_bookings` (every 5 minutes): downloads the bookings of pull channels (Channex revisions
  feed; the simulated Channex feed too).

With nothing to do a run ends `skipped`.
"""

from celery.schedules import crontab

from apps.core.automation import Automation, RunResult, register
from apps.distribution.models import AriUpdate, ChannelConnection
from apps.distribution.services.ical import pull_ical
from apps.distribution.services.pull import PULL_CHANNELS, pull_bookings
from apps.distribution.services.queue import process_queue


def push_ari(property, params) -> RunResult:
    if not AriUpdate.objects.filter(property=property, status=AriUpdate.Status.PENDING).exists():
        return RunResult(status="skipped", summary="Nada pendiente en la cola de ARI")
    summary = process_queue(property)
    trouble = summary["retrying"] or summary["failed"]
    return RunResult(
        status="partial" if trouble else ("success" if summary["sent"] else "skipped"),
        summary=(
            f"{summary['sent']} actualizaciones enviadas, {summary['retrying']} por reintentar, "
            f"{summary['failed']} fallidas"
        ),
        details=summary,
    )


def pull_calendars(property, params) -> RunResult:
    if not ChannelConnection.objects.filter(
        property=property, channel_code=ChannelConnection.Channel.ICAL, room_mappings__ical_import_url__gt=""
    ).exists():
        return RunResult(status="skipped", summary="Sin calendarios iCal para importar")
    summary = pull_ical(property)
    return RunResult(
        status="partial" if summary.get("failed") else "success",
        summary=(
            f"{summary.get('calendars', 0)} calendarios: {summary.get('created', 0)} nuevas, "
            f"{summary.get('modified', 0)} modificadas, {summary.get('cancelled', 0)} canceladas, "
            f"{summary.get('failed', 0)} con error"
        ),
        details=summary,
    )


def pull_channel_bookings(property, params) -> RunResult:
    if not ChannelConnection.objects.filter(property=property, channel_code__in=PULL_CHANNELS).exists():
        return RunResult(status="skipped", summary="Sin canales que descargar")
    summary = pull_bookings(property)
    return RunResult(
        status="partial" if summary.get("failed") or summary.get("errors") else "success",
        summary=(
            f"{summary.get('created', 0)} nuevas, {summary.get('modified', 0)} modificadas, "
            f"{summary.get('cancelled', 0)} canceladas, {summary.get('failed', 0)} con error"
        ),
        details=summary,
    )


register(
    Automation(
        code="distribution.push_ari",
        app="distribution",
        name_es="Enviar disponibilidad y tarifas a los canales",
        name_en="Push availability and rates to channels",
        description_es=(
            "Envía a BookSim, AirSim y Channex la disponibilidad, las tarifas y las restricciones que "
            "cambiaron (cola con debounce y reintentos)."
        ),
        description_en=(
            "Sends the availability, rates and restrictions that changed to BookSim, AirSim and Channex "
            "(debounced queue with retries)."
        ),
        schedule=crontab(minute="*"),
        handler=push_ari,
    )
)
register(
    Automation(
        code="distribution.pull_ical",
        app="distribution",
        name_es="Importar calendarios iCal",
        name_en="Import iCal calendars",
        description_es=(
            "Descarga los calendarios iCal de Airbnb, VRBO o Booking.com y convierte sus eventos en "
            "reservas; los eventos que desaparecen cancelan su reserva."
        ),
        description_en=(
            "Downloads the iCal calendars of Airbnb, VRBO or Booking.com and turns their events into "
            "reservations; events that disappear cancel their reservation."
        ),
        schedule=crontab(minute="*/15"),
        handler=pull_calendars,
    )
)
register(
    Automation(
        code="distribution.pull_bookings",
        app="distribution",
        name_es="Descargar reservas de Channex",
        name_en="Download Channex bookings",
        description_es=(
            "Lee las reservas nuevas, modificadas y canceladas de Channex (feed de revisiones), las aplica "
            "en el PMS y las confirma al canal."
        ),
        description_en=(
            "Reads new, modified and cancelled bookings from Channex (revisions feed), applies them in the "
            "PMS and acknowledges them to the channel."
        ),
        schedule=crontab(minute="*/5"),
        handler=pull_channel_bookings,
    )
)
