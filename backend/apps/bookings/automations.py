"""Automations of bookings (spec §6 + plan B2b). Registered on import (auto-discovered by the core)."""

from datetime import timedelta

from celery.schedules import crontab
from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Reservation
from apps.bookings.services.inventory import rebuild_inventory
from apps.bookings.services.reservations import auto_assign_rooms, cancel_reservation
from apps.bookings.types import BookingError
from apps.core import alerts
from apps.core.automation import Automation, RunResult, register

DRIFT_ALERT = "bookings:inventory_drift"


def auto_assign(property, params) -> RunResult:
    """Today's and tomorrow's arrivals (business date)."""
    today = property.business_date
    days = int(params.get("days_ahead", 1))
    report = auto_assign_rooms(property=property, date_from=today, date_to=today + timedelta(days=days))
    return RunResult(
        status="partial" if report.unassigned else "success",
        summary=f"{len(report.assigned)} estadías asignadas, {len(report.unassigned)} sin habitación",
        details={
            "assigned": len(report.assigned),
            "unassigned": len(report.unassigned),
            "messages": report.messages,
        },
    )


def release_expired_tentative(property, params) -> RunResult:
    """Cancel, without fee, the tentative reservations whose hold expired.

    Each one is read again under lock just before cancelling it: a payment may have confirmed it after the
    list was taken (the `payment_received` receiver), and a confirmed reservation must never be released."""
    now = timezone.now()
    expired = Reservation.objects.filter(
        property=property, status=Reservation.Status.TENTATIVE, hold_expires_at__lt=now
    )
    released, failed = [], []
    for reservation_id, code in expired.order_by("hold_expires_at").values_list("pk", "code"):
        try:
            with transaction.atomic():
                reservation = expired.select_for_update(of=("self",)).filter(pk=reservation_id).first()
                if reservation is None:  # confirmed (or cancelled) meanwhile
                    continue
                cancel_reservation(
                    reservation,
                    reason="La retención de la reserva tentativa expiró",
                    waive_fee=True,
                    source="automation",
                )
            released.append(code)
        except BookingError as exc:
            failed.append({"code": code, "error": exc.message})
    details = {"released": released}
    if failed:
        details["failed"] = failed
    return RunResult(
        status="partial" if failed else "success",
        summary=f"{len(released)} reservas tentativas liberadas",
        details=details,
    )


def inventory_reconcile(property, params) -> RunResult:
    """Rebuild InventoryDay over the horizon; rows that had to be fixed raise `inventory_drift`."""
    result = rebuild_inventory(property)
    if result.updated:
        alerts.raise_alert(
            property=property,
            kind="inventory_drift",
            severity="warning",
            title=f"Inventario corregido: {result.updated} noche(s) no cuadraban",
            message=(
                "La conciliación diaria recalculó la disponibilidad y encontró diferencias con lo vendido o "
                "bloqueado. Revisa cambios hechos por fuera de los servicios de reservas."
            ),
            link="/app/calendar",
            dedupe_key=DRIFT_ALERT,
            data=result.as_dict(),
            source="automation",
        )
    else:
        alerts.resolve_alert(property, DRIFT_ALERT)
    return RunResult(
        summary=f"{result.created} noches creadas, {result.updated} corregidas",
        details=result.as_dict(),
    )


register(
    Automation(
        code="bookings.auto_assign_rooms",
        app="bookings",
        name_es="Asignación automática de habitaciones",
        name_en="Automatic room assignment",
        description_es=(
            "Asigna habitación a las llegadas de hoy y mañana sin habitación: VIP y grupos primero, prefiere "
            "habitaciones limpias, el mismo piso para los grupos y evita huecos."
        ),
        description_en=(
            "Assigns rooms to today's and tomorrow's arrivals without one: VIPs and groups first, clean "
            "rooms, one floor per group and no gaps."
        ),
        schedule=crontab(hour=6, minute=0),
        handler=auto_assign,
        default_params={"days_ahead": 1},
    )
)
register(
    Automation(
        code="bookings.release_expired_tentative",
        app="bookings",
        name_es="Liberar reservas tentativas vencidas",
        name_en="Release expired tentative reservations",
        description_es=(
            "Cancela sin penalidad las reservas tentativas cuya retención expiró y libera el inventario."
        ),
        description_en=(
            "Cancels, without fee, tentative reservations whose hold expired and frees the inventory."
        ),
        schedule=crontab(minute="*/15"),
        handler=release_expired_tentative,
    )
)
register(
    Automation(
        code="bookings.inventory_reconcile",
        app="bookings",
        name_es="Conciliación de inventario",
        name_en="Inventory reconciliation",
        description_es=(
            "Recalcula la disponibilidad desde habitaciones, bloqueos y estadías, y alerta si encontró "
            "diferencias."
        ),
        description_en=(
            "Recomputes availability from rooms, blocks and stays and alerts when it had to fix it."
        ),
        schedule=crontab(hour=4, minute=0),
        handler=inventory_reconcile,
    )
)
