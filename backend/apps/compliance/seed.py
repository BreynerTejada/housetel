"""Demo data of compliance (plan C7 "Seed", spec §10). Runs after bookings and finance (SEED_ORDER).

Per property, through the compliance services (the receivers ignore the seed's replay of history):

- `ComplianceSettings`: `go_live_date` = today − 30 (older departures were invoiced before the hotel used
  Housetel, so they never show up as pending), the SIRE establishment code and automatic TRA / invoices.
- DIAN numbering resolution for tests (habilitación): prefix SETT, range 1–5000, valid for three years.
- Simulated electronic invoices for the departures of the last 30 days, dated at the check-out and numbered in
  that order (PDF/XML are rendered on the first download). The two most recent departures stay without
  invoice:
  they are the "Pendientes" demo and `compliance.issue_pending_invoices` issues them on its next run. One
  invoice is annulled with a credit note and issued again.
- SIRE: one acknowledged file for `[go_live, today − 8]` and one generated file for the last seven days,
  waiting to be uploaded (it lists the foreign guests whose data is incomplete).
- TRA: registrations of the guests in house and of the check-ins of the last three days.

Idempotent: every part is skipped when the property already has data of that kind.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Max
from django.utils import timezone

from apps.bookings.models import Reservation, Stay
from apps.compliance.models import Invoice, InvoiceResolution, SireReport, TraRegistration
from apps.compliance.services import invoices as invoice_service
from apps.compliance.services import sire as sire_service
from apps.compliance.services import tra as tra_service
from apps.compliance.services.config import get_settings
from apps.core.errors import DomainError

HISTORY_DAYS = 30
LEFT_PENDING = 2  # most recent departures left without invoice
TRA_RECENT_DAYS = 3
TEST_TECHNICAL_KEY = "fc8eac422eba16e22ffd8c6f94b3f40a6e38162c"  # DIAN habilitación test set
TEST_RESOLUTION_NUMBER = "18760000001"
SIRE_CODES = {"casa-aurora": "130458", "andino-medellin": "050931", "andino-hostel-bogota": "110517"}
CREDIT_NOTE_REASON = "Anulación por error en los datos del adquiriente; se reexpide la factura"


def seed(ctx) -> None:
    for prop in ctx.properties.values():
        started = time.monotonic()
        today = prop.business_date or ctx.today
        _settings(prop, today)
        _resolution(prop, today)
        issued = _invoices(prop, today)
        reports = _sire(prop, today)
        registered = _tra(prop, today)
        ctx.log(
            f"   {prop.name}: {issued} facturas, {reports} reportes SIRE, {registered} registros TRA "
            f"({time.monotonic() - started:.1f} s)"
        )


# ------------------------------------------------------------------------------------------------ setup


def _settings(prop, today) -> None:
    settings = get_settings(prop)
    changed = []
    if settings.go_live_date is None:
        settings.go_live_date = today - timedelta(days=HISTORY_DAYS)
        changed.append("go_live_date")
    if not settings.sire_establishment_code:
        settings.sire_establishment_code = SIRE_CODES.get(prop.slug, "100001")
        changed.append("sire_establishment_code")
    if changed:
        settings.save(update_fields=[*changed, "updated_at"])


def _resolution(prop, today) -> None:
    kind = InvoiceResolution.DocumentKind.INVOICE
    if InvoiceResolution.objects.filter(property=prop, document_kind=kind, is_active=True).exists():
        return
    valid_from = today - timedelta(days=365)
    InvoiceResolution.objects.create(
        property=prop,
        document_kind=kind,
        prefix="SETT",
        resolution_number=TEST_RESOLUTION_NUMBER,
        from_number=1,
        to_number=5000,
        valid_from=valid_from,
        valid_to=valid_from + timedelta(days=3 * 365),
        technical_key=TEST_TECHNICAL_KEY,
        environment=InvoiceResolution.Environment.TEST,
        is_active=True,
    )


# --------------------------------------------------------------------------------------------- invoices


def _checkout_moment(prop, reservation, checked_out_at) -> datetime:
    """When the invoice was issued: a couple of minutes after the last check-out (or 11:30 that day)."""
    if checked_out_at is not None:
        return checked_out_at + timedelta(minutes=2)
    zone = ZoneInfo(prop.timezone or "America/Bogota")
    return datetime.combine(reservation.checkout_date, datetime.min.time(), zone).replace(hour=11, minute=30)


def _invoices(prop, today) -> int:
    if Invoice.objects.filter(property=prop).exists():
        return 0
    since = today - timedelta(days=HISTORY_DAYS)
    departures = list(
        Reservation.objects.filter(
            property=prop,
            status=Reservation.Status.CHECKED_OUT,
            checkout_date__gte=since,
            checkout_date__lt=today,
        ).annotate(left_at=Max("stays__checked_out_at"))
    )
    pending = invoice_service.uninvoiced_by_reservation(prop, [r.pk for r in departures])
    moments = sorted(
        (
            (_checkout_moment(prop, r, r.left_at), r)
            for r in departures
            if pending.get(r.pk, {}).get("total", 0) > 0
        ),
        key=lambda item: (item[0], item[1].code),
    )
    if len(moments) > LEFT_PENDING:
        moments = moments[: len(moments) - LEFT_PENDING]
    else:
        moments = []
    # the credit note demo: the last departure of the day ten days ago (so numbers stay in date order)
    target_day = today - timedelta(days=10)
    same_day = [r for moment, r in moments if r.checkout_date == target_day]
    corrected = same_day[-1].pk if same_day else None
    issued = 0
    for moment, reservation in moments:
        try:
            invoice = invoice_service.issue_invoice(
                reservation, source="automation", issued_at=moment, render=False
            )
        except DomainError:
            continue
        issued += 1
        if reservation.pk == corrected and invoice.status in invoice_service.DONE_STATUSES:
            invoice_service.issue_credit_note(
                invoice,
                reason=CREDIT_NOTE_REASON,
                confirm=True,
                source="user",
                issued_at=moment + timedelta(minutes=40),
                render=False,
            )
            invoice_service.issue_invoice(
                reservation, source="user", issued_at=moment + timedelta(minutes=45), render=False
            )
            issued += 1
    return issued


# ------------------------------------------------------------------------------------------------- SIRE


def _at(prop, day, hour, minute=0) -> datetime:
    zone = ZoneInfo(prop.timezone or "America/Bogota")
    return datetime.combine(day, datetime.min.time(), zone).replace(hour=hour, minute=minute)


def _sire(prop, today) -> int:
    if SireReport.objects.filter(property=prop).exists():
        return 0
    settings = get_settings(prop)
    start = settings.go_live_date or today - timedelta(days=HISTORY_DAYS)
    acknowledged_end = today - timedelta(days=8)
    count = 0
    if start <= acknowledged_end:
        report = sire_service.generate_sire(prop, start, acknowledged_end, source="automation")
        report = sire_service.mark_submitted(report, source="user")
        generated = _at(prop, acknowledged_end + timedelta(days=1), 8)
        SireReport.objects.filter(pk=report.pk).update(
            generated_at=generated, submitted_at=generated + timedelta(hours=2)
        )
        count += 1
    week_start = max(start, today - timedelta(days=7))
    week_end = today - timedelta(days=1)
    if week_start <= week_end:
        report = sire_service.generate_sire(prop, week_start, week_end, source="automation")
        # the daily 08:00 run, or now if the demo is seeded earlier in the day
        SireReport.objects.filter(pk=report.pk).update(generated_at=min(timezone.now(), _at(prop, today, 8)))
        count += 1
    return count


# -------------------------------------------------------------------------------------------------- TRA


def _tra(prop, today) -> int:
    if TraRegistration.objects.filter(property=prop).exists():
        return 0
    since = today - timedelta(days=TRA_RECENT_DAYS)
    stays = (
        Stay.objects.filter(reservation__property=prop, status=Stay.Status.CHECKED_IN)
        | Stay.objects.filter(
            reservation__property=prop, status=Stay.Status.CHECKED_OUT, checkin_date__gte=since
        )
    ).order_by("checked_in_at", "checkin_date", "created_at")
    registered = 0
    for stay in stays:
        registrations = tra_service.register_stay(stay, source="automation")
        moment = stay.checked_in_at or _at(prop, stay.checkin_date, 15)
        ids = [r.pk for r in registrations if r.status == TraRegistration.Status.REGISTERED]
        if ids:  # registered at check-in, not when the demo was seeded
            TraRegistration.objects.filter(pk__in=ids).update(
                registered_at=moment + timedelta(minutes=3), last_attempt_at=moment + timedelta(minutes=3)
            )
        registered += len(ids)
    return registered
