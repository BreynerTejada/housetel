"""TRA (Tarjeta de Registro Alojamiento, MinCIT): every guest of a stay is registered at check-in.

The first lodged guest (the booker, when lodged there) is the main registration; the others are companions
linked to it (the MinCIT service needs the main guest's code, `padre`, to accept a companion). A registration
with
missing data stays `pending` with `missing_fields` (alert `compliance:tra:missing`) until the data is fixed; a
service error leaves it in `error` (alert `compliance:tra:error`). Both are retried by `retry_registration`
and the
automation `compliance.tra_retry`.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Stay
from apps.compliance.codes import COUNTRY_NAMES_ES, TRA_DOCUMENT_TYPES, TRA_TRAVEL_REASONS
from apps.compliance.models import TraRegistration
from apps.compliance.services.config import get_settings, tra_accommodation_type, tra_establishment_id
from apps.compliance.services.sire import lodged_guests, travel_data
from apps.core import alerts, audit, integrations
from apps.core.errors import ConflictError

logger = logging.getLogger("housetel.compliance")

MAX_AUTO_ATTEMPTS = 10
RETRY_WINDOW_DAYS = 7
MAIN_REQUIRED = ["tipo_identificacion", "numero_identificacion", "nombres", "apellidos", "cuidad_residencia",
                 "numero_habitacion", "rnt_establecimiento"]  # fmt: skip
COMPANION_REQUIRED = ["tipo_identificacion", "numero_identificacion", "nombres", "apellidos",
"cuidad_residencia",
                      "numero_habitacion"]  # fmt: skip
MISSING_ALERT = "compliance:tra:missing"
ERROR_ALERT = "compliance:tra:error"
WAITING_FOR_MAIN = "Esperando el registro del huésped principal"


def _room_label(stay) -> str:
    if not stay.room_id:
        return ""
    return f"{stay.room.number}-{stay.bed.label}" if stay.bed_id else stay.room.number


def _residence(guest) -> str:
    if guest.city_of_residence:
        return guest.city_of_residence
    country = (guest.country_of_residence or guest.nationality or "").upper()
    return COUNTRY_NAMES_ES.get(country, country)


def build_payload(
    settings, stay, guest, *, main: bool, companions: int, travel: dict
) -> tuple[dict, list[str]]:
    """The MinCIT TRA fields of one guest (see providers.MincitTraProvider) and the required ones missing."""
    residence = _residence(guest)
    payload = {
        "tipo_identificacion": TRA_DOCUMENT_TYPES.get((guest.document_type or "").upper(), ""),
        "numero_identificacion": (guest.document_number or "").strip(),
        "nombres": guest.first_name.strip(),
        "apellidos": guest.last_name.strip(),
        "cuidad_residencia": residence,
        "cuidad_procedencia": (travel.get("origin") or "").strip() or residence,
        "numero_habitacion": _room_label(stay),
    }
    if main:
        prop = settings.property
        payload.update(
            {
                "motivo": TRA_TRAVEL_REASONS.get(travel.get("travel_reason", ""), "")
                or settings.tra_travel_reason,
                "numero_acompanantes": companions,
                "check_in": stay.checkin_date.isoformat(),
                "check_out": stay.checkout_date.isoformat(),
                "tipo_acomodacion": tra_accommodation_type(settings),
                "costo": float(stay.total_amount or 0),
                "nombre_establecimiento": prop.legal_name or prop.name,
                "rnt_establecimiento": tra_establishment_id(settings),
            }
        )
    else:
        payload.update(
            {"check_in": stay.checkin_date.isoformat(), "check_out": stay.checkout_date.isoformat()}
        )
    required = MAIN_REQUIRED if main else COMPANION_REQUIRED
    missing = [field for field in required if payload.get(field) in ("", None)]
    if not main and not tra_establishment_id(settings):  # nothing is sent without the establishment's RNT
        missing.append("rnt_establecimiento")
    return payload, missing


def register_stay(stay, *, actor=None, source="user") -> list[TraRegistration]:
    """Create (once) the registrations of every lodged guest of `stay` and send the ones not registered
    yet."""
    stay = Stay.objects.select_related("reservation__property", "room", "bed").get(pk=stay.pk)
    prop = stay.reservation.property
    guests = lodged_guests(stay)
    if not guests:
        return []
    mode = integrations.get_setting(prop, "tra").mode
    with transaction.atomic():
        registrations = []
        for index, guest in enumerate(guests):
            registration, _ = TraRegistration.objects.get_or_create(
                stay=stay,
                guest=guest,
                defaults={
                    "property": prop,
                    "reservation": stay.reservation,
                    "is_main": index == 0,
                    "mode": mode,
                },
            )
            registrations.append(registration)
        main = next((r for r in registrations if r.is_main), registrations[0])
        for registration in registrations:
            if registration.pk != main.pk and registration.parent_id != main.pk:
                registration.parent = main
                registration.save(update_fields=["parent", "updated_at"])
    ordered = sorted(registrations, key=lambda r: not r.is_main)
    for registration in ordered:
        registration.refresh_from_db(fields=["status"])  # a companion may have gone out with its main guest
        if registration.status != TraRegistration.Status.REGISTERED:
            submit(registration, actor=actor, source=source, refresh=False)
    refresh_alerts(prop)
    return [TraRegistration.objects.get(pk=r.pk) for r in ordered]


def submit(registration, *, actor=None, source="user", refresh=True) -> TraRegistration:
    """Build the payload and send one registration (companions only after their main guest)."""
    registration = TraRegistration.objects.select_related(
        "stay__room", "stay__bed", "stay__reservation__property", "guest", "parent"
    ).get(pk=registration.pk)
    stay = registration.stay
    settings = get_settings(stay.reservation.property)
    travel = travel_data(stay.reservation).get(str(registration.guest_id)) or {}
    companions = (
        TraRegistration.objects.filter(stay=stay).exclude(pk=registration.pk).count()
        if registration.is_main
        else 0
    )
    payload, missing = build_payload(
        settings, stay, registration.guest, main=registration.is_main, companions=companions, travel=travel
    )
    registration.payload = payload
    registration.missing_fields = missing
    if missing:
        registration.status = TraRegistration.Status.PENDING
        registration.error = "Faltan datos: " + ", ".join(missing)
        registration.save()
        if refresh:
            refresh_alerts(registration.property)
        return registration
    parent_number = ""
    if not registration.is_main:
        parent = registration.parent
        if parent is None or parent.status != TraRegistration.Status.REGISTERED:
            registration.status = TraRegistration.Status.PENDING
            registration.error = WAITING_FOR_MAIN
            registration.save()
            return registration
        parent_number = parent.tra_number
    provider = integrations.get_provider(registration.property, "tra")
    try:
        result = provider.register(payload, parent_number=parent_number)
    except Exception as exc:  # the registration must stay retryable whatever the provider does
        logger.exception("TRA provider failed for %s", registration.pk)
        result = {
            "status": "error",
            "tra_number": "",
            "message": f"Error del servicio TRA: {exc}",
            "response": {},
        }
    registration.attempts += 1
    registration.last_attempt_at = timezone.now()
    registration.response = result.get("response") or {}
    registration.mode = provider.mode
    if result.get("status") == TraRegistration.Status.REGISTERED:
        registration.status = TraRegistration.Status.REGISTERED
        registration.tra_number = result.get("tra_number", "")
        registration.registered_at = timezone.now()
        registration.error = ""
    else:
        registration.status = TraRegistration.Status.ERROR
        registration.error = result.get("message") or "El servicio TRA no aceptó el registro"
    registration.save()
    audit.record(
        action="compliance.tra_registered"
        if registration.status == "registered"
        else "compliance.tra_failed",
        target=registration,
        summary=f"TRA de {registration.guest.full_name}: "
        + (registration.tra_number if registration.status == "registered" else registration.error),
        actor=actor,
        source=source,
        property=registration.property,
        changes={"status": [None, registration.status]},
    )
    if registration.is_main and registration.status == TraRegistration.Status.REGISTERED:
        for companion in TraRegistration.objects.filter(parent=registration).exclude(status="registered"):
            submit(companion, actor=actor, source=source, refresh=False)
    if refresh:
        refresh_alerts(registration.property)
    return registration


def retry_registration(registration, *, actor=None, source="user") -> TraRegistration:
    if registration.status == TraRegistration.Status.REGISTERED:
        raise ConflictError("Este huésped ya tiene su TRA registrada", code="invalid_state")
    if not registration.is_main and registration.parent and registration.parent.status != "registered":
        submit(registration.parent, actor=actor, source=source)
    return submit(registration, actor=actor, source=source)


def auto_register_on_checkin(stay) -> list[TraRegistration]:
    """Receiver of `stay_checked_in` (when the hotel registers automatically)."""
    settings = get_settings(stay.reservation.property)
    if not settings.tra_auto_register:
        return []
    try:
        return register_stay(stay, source="automation")
    except Exception:  # never break a check-in: the automation retries
        logger.exception("TRA registration of stay %s failed", stay.pk)
        return []


def retry_pending_tra(property, *, max_attempts=MAX_AUTO_ATTEMPTS, window_days=RETRY_WINDOW_DAYS) -> dict:
    """Automation `compliance.tra_retry`: send again the registrations of the last `window_days` days that are
    pending (data fixed since, or waiting for their main guest) or failed."""
    since = property.business_date - timedelta(days=window_days)
    queryset = TraRegistration.objects.filter(
        property=property,
        status__in=(TraRegistration.Status.PENDING, TraRegistration.Status.ERROR),
        attempts__lt=max_attempts,
        stay__checkin_date__gte=since,
    ).order_by("-is_main", "created_at")
    report = {"retried": 0, "registered": 0, "failed": 0}
    for registration in queryset:
        registration.refresh_from_db()
        if registration.status == TraRegistration.Status.REGISTERED:  # sent with its main guest meanwhile
            report["retried"] += 1
            report["registered"] += 1
            continue
        result = submit(registration, source="automation", refresh=False)
        report["retried"] += 1
        report["registered" if result.status == TraRegistration.Status.REGISTERED else "failed"] += 1
    refresh_alerts(property)
    return report


def refresh_alerts(property) -> None:
    missing = (
        TraRegistration.objects.filter(property=property, status=TraRegistration.Status.PENDING)
        .exclude(missing_fields=[])
        .count()
    )
    if missing:
        alerts.raise_alert(
            property=property,
            kind="tra_missing_data",
            severity="warning",
            title=f"TRA: {missing} huésped(es) con datos faltantes",
            message="Completa el documento, los nombres o la ciudad de residencia de los huéspedes para "
            "registrar su "
            "Tarjeta de Registro Alojamiento.",
            link="/app/compliance?tab=tra&status=pending",
            dedupe_key=MISSING_ALERT,
            data={"count": missing},
            source="compliance",
        )
    else:
        alerts.resolve_alert(property, MISSING_ALERT)
    failed = TraRegistration.objects.filter(property=property, status=TraRegistration.Status.ERROR).count()
    if failed:
        alerts.raise_alert(
            property=property,
            kind="tra_error",
            severity="warning",
            title=f"TRA: {failed} registro(s) rechazados por el servicio",
            message="El servicio TRA no aceptó algunos registros. Revisa el detalle y reinténtalos.",
            link="/app/compliance?tab=tra&status=error",
            dedupe_key=ERROR_ALERT,
            data={"count": failed},
            source="compliance",
        )
    else:
        alerts.resolve_alert(property, ERROR_ALERT)
