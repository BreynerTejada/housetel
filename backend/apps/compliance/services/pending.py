"""Read models of the legal work still to do (tab "Pendientes", the Today widget and the reservation's "Legal"
tab). Nothing here writes."""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Exists, OuterRef, Q

from apps.bookings.models import Reservation, Stay
from apps.compliance.models import Invoice, InvoiceResolution, SireReport, TraRegistration
from apps.compliance.services.builder import build_document, folio_customer
from apps.compliance.services.config import get_settings, local_date
from apps.compliance.services.invoices import (
    DONE_STATUSES,
    RETRYABLE_STATUSES,
    invoice_groups,
    invoiceable_charges,
    uninvoiced_by_reservation,
)
from apps.compliance.services.numbering import NEAR_EXHAUSTION_RATIO, NEAR_EXPIRY_DAYS
from apps.compliance.services.sire import lodged_guests

SIRE_LOOKBACK_DAYS = 30
DEFAULT_LIMIT = 50


def _money(value) -> str:
    return f"{value:.2f}"


def resolution_health(property) -> dict:
    """State of the active invoice numbering resolution: ok | warning | critical | missing."""
    resolution = InvoiceResolution.objects.filter(
        property=property, document_kind=InvoiceResolution.DocumentKind.INVOICE, is_active=True
    ).first()
    if resolution is None:
        return {"status": "missing", "message": "No hay una resolución de facturación activa"}
    today = local_date(property)
    total = resolution.to_number - resolution.from_number + 1
    remaining = resolution.remaining
    used = total - remaining
    days_left = (resolution.valid_to - today).days
    if days_left < 0 or remaining <= 0:
        status = "critical"
        message = "La resolución venció" if days_left < 0 else "Se agotó el rango de numeración"
    elif today < resolution.valid_from:
        status, message = "warning", f"La resolución rige desde el {resolution.valid_from:%d/%m/%Y}"
    elif used / total >= NEAR_EXHAUSTION_RATIO or days_left < NEAR_EXPIRY_DAYS:
        status, message = "warning", f"Quedan {remaining} números y {days_left} días de vigencia"
    else:
        status, message = "ok", f"Quedan {remaining} números y {days_left} días de vigencia"
    return {
        "status": status,
        "message": message,
        "resolution_id": str(resolution.pk),
        "prefix": resolution.prefix,
        "from_number": resolution.from_number,
        "to_number": resolution.to_number,
        "next_number": resolution.next_number,
        "remaining": remaining,
        "used_percent": round(used * 100 / total, 1),
        "valid_to": resolution.valid_to.isoformat(),
        "days_left": days_left,
        "environment": resolution.environment,
    }


# --------------------------------------------------------------------------------------------- invoices


def _invoice_items(property, settings) -> list[dict]:
    items = []
    failed = (
        Invoice.objects.filter(property=property, status__in=RETRYABLE_STATUSES)
        .select_related("reservation__booker")
        .order_by("issue_date", "number")
    )
    for invoice in failed:
        reservation = invoice.reservation
        items.append(
            {
                "status": invoice.status,
                "invoice_id": str(invoice.pk),
                "number": invoice.full_number,
                "kind": invoice.kind,
                "reservation_id": str(reservation.pk) if reservation else None,
                "reservation_code": reservation.code if reservation else "",
                "guest_name": invoice.customer.get("name", ""),
                "checkout_date": reservation.checkout_date.isoformat() if reservation else None,
                "total": _money(invoice.total),
                "error": invoice.error_message,
            }
        )
    departures = Reservation.objects.filter(property=property, status=Reservation.Status.CHECKED_OUT)
    if settings.go_live_date:
        departures = departures.filter(checkout_date__gte=settings.go_live_date)
    pending = uninvoiced_by_reservation(property, departures.values_list("pk", flat=True))
    candidates = [pk for pk, row in pending.items() if row["total"] > 0]
    for reservation in (
        Reservation.objects.filter(pk__in=candidates)
        .select_related("booker")
        .order_by("checkout_date", "code")
    ):
        items.append(
            {
                "status": "not_issued",
                "invoice_id": None,
                "number": "",
                "kind": Invoice.Kind.INVOICE,
                "reservation_id": str(reservation.pk),
                "reservation_code": reservation.code,
                "guest_name": reservation.booker.full_name,
                "checkout_date": reservation.checkout_date.isoformat(),
                "total": _money(pending[reservation.pk]["total"]),
                "error": "",
            }
        )
    return items


# -------------------------------------------------------------------------------------------------- TRA


def _registration_item(registration) -> dict:
    stay = registration.stay
    return {
        "status": registration.status,
        "registration_id": str(registration.pk),
        "reservation_id": str(registration.reservation_id),
        "reservation_code": registration.reservation.code,
        "stay_id": str(stay.pk),
        "guest_id": str(registration.guest_id),
        "guest_name": registration.guest.full_name,
        "room": stay.room.number if stay.room_id else "",
        "checkin_date": stay.checkin_date.isoformat(),
        "missing_fields": registration.missing_fields,
        "error": registration.error,
    }


def _tra_items(property, settings) -> list[dict]:
    registrations = (
        TraRegistration.objects.filter(
            property=property, status__in=(TraRegistration.Status.PENDING, TraRegistration.Status.ERROR)
        )
        .select_related("reservation", "guest", "stay__room")
        .order_by("stay__checkin_date", "-is_main", "created_at")
    )
    items = [_registration_item(r) for r in registrations]
    lodged = Stay.objects.filter(reservation__property=property, status=Stay.Status.CHECKED_IN)
    if settings.go_live_date:
        lodged = lodged.filter(checkin_date__gte=settings.go_live_date)
    missing = lodged.exclude(pk__in=TraRegistration.objects.filter(property=property).values("stay_id"))
    for stay in missing.select_related("reservation__booker", "room").order_by("checkin_date", "created_at"):
        guests = lodged_guests(stay)
        items.append(
            {
                "status": "not_registered",
                "registration_id": None,
                "reservation_id": str(stay.reservation_id),
                "reservation_code": stay.reservation.code,
                "stay_id": str(stay.pk),
                "guest_id": str(guests[0].pk) if guests else None,
                "guest_name": guests[0].full_name if guests else "",
                "room": stay.room.number if stay.room_id else "",
                "checkin_date": stay.checkin_date.isoformat(),
                "missing_fields": [] if guests else ["occupants"],
                "error": "",
            }
        )
    return items


# ------------------------------------------------------------------------------------------------- SIRE


def _foreign_movement_days(property, start, end) -> set:
    """Days in `[start, end]` with a check-in or check-out of a foreign guest (booker or occupant)."""
    foreign_occupant = Stay.occupants.through.objects.filter(stay_id=OuterRef("pk")).exclude(
        guest__nationality__in=["", "CO"]
    )
    foreign = ~Q(reservation__booker__nationality__in=["", "CO"]) | Q(Exists(foreign_occupant))
    stays = (
        Stay.objects.filter(
            reservation__property=property, status__in=(Stay.Status.CHECKED_IN, Stay.Status.CHECKED_OUT)
        )
        .filter(
            Q(checkin_date__range=(start, end)) | Q(checkout_date__range=(start, end), status="checked_out")
        )
        .filter(foreign)
        .values_list("checkin_date", "checkout_date", "status")
        .distinct()
    )
    days = set()
    for checkin, checkout, status in stays:
        if start <= checkin <= end:
            days.add(checkin)
        if status == Stay.Status.CHECKED_OUT and start <= checkout <= end:
            days.add(checkout)
    return days


def _sire(property, settings) -> dict:
    reports = list(
        SireReport.objects.filter(property=property, status=SireReport.Status.GENERATED).order_by(
            "period_start"
        )
    )
    missing = [entry for report in reports for entry in (report.missing or [])]
    end = property.business_date - timedelta(days=1)
    start = end - timedelta(days=SIRE_LOOKBACK_DAYS - 1)
    if settings.go_live_date and settings.go_live_date > start:
        start = settings.go_live_date
    unreported = []
    if start <= end:
        covered = set()
        for report in SireReport.objects.filter(
            property=property, period_end__gte=start, period_start__lte=end
        ):
            day = report.period_start
            while day <= report.period_end:
                covered.add(day)
                day += timedelta(days=1)
        unreported = sorted(d.isoformat() for d in _foreign_movement_days(property, start, end) - covered)
    return {
        "reports": [
            {
                "report_id": str(r.pk),
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "records_count": r.records_count,
                "missing_count": len(r.missing or []),
                "generated_at": r.generated_at.isoformat(),
            }
            for r in reports
        ],
        "missing": missing,
        "unreported_days": unreported,
    }


# -------------------------------------------------------------------------------------------- summaries


def pending_summary(property, *, limit=DEFAULT_LIMIT) -> dict:
    settings = get_settings(property)
    invoices = _invoice_items(property, settings)
    tra = _tra_items(property, settings)
    sire = _sire(property, settings)
    sire_count = len(sire["reports"]) + len(sire["unreported_days"])
    return {
        "resolution": resolution_health(property),
        "invoices": {"count": len(invoices), "items": invoices[:limit]},
        "tra": {"count": len(tra), "items": tra[:limit]},
        "sire": {"count": sire_count, **sire, "missing": sire["missing"][:limit]},
        "counts": {
            "invoices": len(invoices),
            "tra": len(tra),
            "sire": sire_count,
            "total": len(invoices) + len(tra) + sire_count,
        },
    }


def reservation_legal(reservation) -> dict:
    """Invoices, TRA registrations, SIRE records and warnings of one reservation (its "Legal" tab)."""
    from apps.compliance.api.serializers import InvoiceSummarySerializer, TraRegistrationSerializer

    prop = reservation.property
    invoices = (
        Invoice.objects.filter(reservation=reservation)
        .select_related("related_invoice")
        .order_by("created_at")
    )
    uninvoiced = uninvoiced_by_reservation(prop, [reservation.pk]).get(reservation.pk) or {
        "count": 0,
        "total": 0,
    }
    registrations = (
        TraRegistration.objects.filter(reservation=reservation)
        .select_related("guest", "stay__room", "reservation")
        .order_by("stay__checkin_date", "-is_main", "created_at")
    )
    records = reservation_records(reservation)
    booker = reservation.booker
    settings = get_settings(prop)
    folios = folio_options(reservation, settings)
    preview = next((row["preview"] for row in folios if row["preview"]), None)
    guest_side = next((row for row in folios if row["folio_type"] != "company"), None)
    company_billed = any(row["folio_type"] == "company" for row in folios)
    warnings = []
    if not booker.document_number and (
        not company_billed or (guest_side is not None and guest_side["uninvoiced"]["count"] > 0)
    ):
        warnings.append("final_consumer")
    if Invoice.objects.filter(reservation=reservation, status__in=RETRYABLE_STATUSES).exists():
        warnings.append("invoice_failed")
    if registrations.filter(status__in=("pending", "error")).exists():
        warnings.append("tra_pending")
    if any(not r["complete"] for r in records):
        warnings.append("sire_missing")
    return {
        "reservation": {
            "id": str(reservation.pk),
            "code": reservation.code,
            "status": reservation.status,
            "checkout_date": reservation.checkout_date.isoformat(),
            "booker": {
                "id": str(booker.pk),
                "full_name": booker.full_name,
                "document_type": booker.document_type,
                "document_number": booker.document_number,
                "nationality": booker.nationality,
                "is_foreign_non_resident": booker.is_foreign_non_resident,
            },
        },
        "invoices": InvoiceSummarySerializer(invoices, many=True).data,
        "uninvoiced": {"count": uninvoiced["count"], "total": _money(uninvoiced["total"])},
        "can_issue": uninvoiced["total"] > 0,
        "has_accepted_invoice": invoices.filter(status__in=DONE_STATUSES, kind=Invoice.Kind.INVOICE).exists(),
        "tra": TraRegistrationSerializer(registrations, many=True).data,
        "tra_candidates": tra_candidates(reservation),
        "sire": records,
        "warnings": warnings,
        "resolution": resolution_health(prop),
        "preview": preview,
        "folios": folios,
    }


def _preview_payload(document, count: int) -> dict:
    return {
        "customer": document.customer,
        "lines": [
            {key: value for key, value in line.items() if key != "charge_ids"} for line in document.lines
        ],
        "subtotal": _money(document.subtotal),
        "tax_total": _money(document.tax_total),
        "total": _money(document.total),
        "exempt_note": document.exempt_note,
        "charges_count": count,
    }


def folio_options(reservation, settings) -> list[dict]:
    """Who the reservation can be invoiced to (P4, the "Facturar a" selector): one row per folio group — the
    guest side (booker) and each company folio — with its customer, what is still to invoice and the preview.
    Issue a row with `POST invoices/issue/ {folio_id}`."""
    rows = []
    for group in invoice_groups(reservation):
        first = group[0]
        charges = list(
            invoiceable_charges(group)
            .select_related("tax", "stay__room_type", "extra")
            .order_by("business_date", "created_at")
        )
        document = (
            build_document(first, charges, final_consumer_id=settings.final_consumer_id) if charges else None
        )
        customer = (
            document.customer
            if document
            else folio_customer(first, final_consumer_id=settings.final_consumer_id)
        )
        total = document.total if document else 0
        rows.append(
            {
                "folio_id": str(first.pk),
                "folio_ids": [str(folio.pk) for folio in group],
                "folio_type": "company" if first.folio_type == "company" else "guest",
                "status": first.status,
                "company_id": str(first.company_id) if first.company_id else None,
                "customer": customer,
                "uninvoiced": {"count": len(charges), "total": _money(total)},
                "can_issue": bool(document and document.total > 0),
                "preview": _preview_payload(document, len(charges))
                if document and document.total > 0
                else None,
            }
        )
    return rows


def issue_preview(reservation, settings) -> dict | None:
    """What "Emitir factura" would invoice first (the first folio group with charges; see `folio_options`)."""
    return next((row["preview"] for row in folio_options(reservation, settings) if row["preview"]), None)


def tra_candidates(reservation) -> list[dict]:
    """Stays of the reservation that already checked in and have no TRA registration yet."""
    stays = (
        Stay.objects.filter(
            reservation=reservation, status__in=(Stay.Status.CHECKED_IN, Stay.Status.CHECKED_OUT)
        )
        .exclude(pk__in=TraRegistration.objects.filter(reservation=reservation).values("stay_id"))
        .select_related("room", "bed")
        .order_by("checkin_date", "created_at")
    )
    rows = []
    for stay in stays:
        guests = lodged_guests(stay)
        room = stay.room.number if stay.room_id else ""
        if stay.bed_id:
            room = f"{room} · {stay.bed.label}"
        rows.append(
            {
                "stay_id": str(stay.pk),
                "status": stay.status,
                "room": room,
                "checkin_date": stay.checkin_date.isoformat(),
                "guests": [guest.full_name for guest in guests],
            }
        )
    return rows


def reservation_records(reservation) -> list[dict]:
    from apps.compliance.models import SireRecord

    rows = (
        SireRecord.objects.filter(stay__reservation=reservation)
        .select_related("report", "guest")
        .order_by("movement_date", "movement")
    )
    return [
        {
            "id": str(record.pk),
            "report_id": str(record.report_id),
            "report_status": record.report.status,
            "guest_id": str(record.guest_id),
            "guest_name": record.guest.full_name,
            "movement": record.movement,
            "movement_date": record.movement_date.isoformat(),
            "complete": record.complete,
            "missing_fields": record.missing_fields,
        }
        for record in rows
    ]
