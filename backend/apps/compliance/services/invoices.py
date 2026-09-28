"""DIAN electronic invoicing: issue from the folio, retries, credit notes and the pending-work automation.

Flow of `issue_invoice` (the provider call happens outside the numbering transaction so a slow provider never
holds the resolution lock):

1. In one transaction: lock the reservation (or folio), take the non-voided charges not covered by another
   invoice, build customer/lines/totals (`builder.build_document`), take the next number of the active
   resolution (`numbering.assign_number`, row lock) and create the `Invoice` as `draft` with those charges.
2. Send it to the `einvoice` provider (simulated or Factus).
3. In a second transaction: apply the result (`accepted` / `issued` / `rejected` / `error`), store the PDF and
   the XML, audit and raise or resolve the alert `compliance:invoice:<id>`.

A number is never reused: a document that fails keeps its number and is retried (`retry_invoice`, the
automation `compliance.issue_pending_invoices`). Charges covered by an invoice in any status but `cancelled`
cannot be invoiced again; a credit note (`issue_credit_note`) annuls the invoice and frees them.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.bookings.models import ACTIVE_STAY_STATUSES, Reservation, Stay
from apps.compliance.models import Invoice, InvoiceResolution
from apps.compliance.services import numbering
from apps.compliance.services.builder import build_document, invoice_customer
from apps.compliance.services.config import get_settings, local_date, supplier_info
from apps.compliance.services.documents import render_invoice_pdf, render_invoice_xml
from apps.core import alerts, audit, integrations
from apps.core.errors import ConfirmationRequired, ConflictError, DomainError
from apps.finance.models import Charge, Folio

logger = logging.getLogger("housetel.compliance")

COVERING_STATUSES = (
    Invoice.Status.DRAFT,
    Invoice.Status.ISSUED,
    Invoice.Status.ACCEPTED,
    Invoice.Status.REJECTED,
    Invoice.Status.ERROR,
)
RETRYABLE_STATUSES = (Invoice.Status.DRAFT, Invoice.Status.ERROR, Invoice.Status.REJECTED)
DONE_STATUSES = (Invoice.Status.ISSUED, Invoice.Status.ACCEPTED)
MAX_AUTO_ATTEMPTS = 8
LOOKBACK_DAYS = 3
KIND_FILE_NAMES = {Invoice.Kind.INVOICE: "factura", Invoice.Kind.CREDIT_NOTE: "nota-credito"}


class InvoiceConflict(ConflictError):
    code = "invoice_conflict"


# ------------------------------------------------------------------------------------------------ helpers


def covered_charge_ids():
    """Charges already taken by an invoice that is not cancelled (subquery of charge ids)."""
    return Invoice.charges.through.objects.filter(
        invoice__kind=Invoice.Kind.INVOICE, invoice__status__in=COVERING_STATUSES
    ).values("charge_id")


def invoiceable_charges(folios):
    return Charge.objects.filter(folio__in=folios, voided_at__isnull=True).exclude(
        pk__in=covered_charge_ids()
    )


def uninvoiced_by_reservation(property, reservation_ids=None) -> dict:
    """{reservation_id: {"count", "total"}} of the non-voided charges no invoice covers (total = net +
    IVA)."""
    queryset = invoiceable_charges(Folio.objects.filter(property=property, reservation__isnull=False))
    if reservation_ids is not None:
        queryset = queryset.filter(folio__reservation_id__in=list(reservation_ids))
    money = DecimalField(max_digits=14, decimal_places=2)
    rows = queryset.values("folio__reservation_id").annotate(
        total=Coalesce(Sum(F("amount") + F("tax_amount"), output_field=money), Value(0, output_field=money)),
        count=Sum(Value(1)),
    )
    return {row["folio__reservation_id"]: {"count": row["count"], "total": row["total"]} for row in rows}


def _resolve(target) -> tuple[Reservation | None, list[Folio]]:
    if isinstance(target, Reservation):
        folios = list(Folio.objects.filter(reservation=target).order_by("created_at"))
        if not folios:
            raise InvoiceConflict(
                "La reserva no tiene folio con cargos para facturar", code="nothing_to_invoice"
            )
        return target, folios
    if isinstance(target, Folio):
        return target.reservation, [target]
    raise TypeError("issue_invoice espera una reserva o un folio")


def _customer_guest(invoice):
    if invoice.reservation_id:
        return invoice.reservation.booker
    return invoice.folio.guest


def _user(actor):
    return actor if actor is not None and getattr(actor, "is_authenticated", False) else None


def _file_name(invoice, extension: str) -> str:
    return f"{KIND_FILE_NAMES[invoice.kind]}-{invoice.full_number or invoice.pk}.{extension}"


# -------------------------------------------------------------------------------------------------- issue


def issue_invoice(target, *, actor=None, source="user", issued_at=None, render=True) -> Invoice:
    """Invoice the non-voided, not yet invoiced charges of a reservation (all its folios) or of one folio.

    `issued_at` backdates the document (seed / backfills: its date is the one the numbering validates);
    `render=False` leaves the PDF/XML to be generated on first download (`ensure_pdf` / `ensure_xml`)."""
    reservation, folios = _resolve(target)
    prop = folios[0].property
    settings = get_settings(prop)
    moment = issued_at or timezone.now()
    day = local_date(prop, moment)
    try:
        with transaction.atomic():
            if reservation is not None:
                Reservation.objects.select_for_update().filter(pk=reservation.pk).first()
            list(Folio.objects.select_for_update().filter(pk__in=[f.pk for f in folios]).order_by("pk"))
            charges = list(
                invoiceable_charges(folios)
                .select_related("tax", "stay__room_type", "extra")
                .order_by("business_date", "created_at")
            )
            if not charges:
                raise InvoiceConflict("No hay cargos pendientes de facturar", code="nothing_to_invoice")
            document = build_document(folios[0], charges, final_consumer_id=settings.final_consumer_id)
            if document.total <= 0:
                raise DomainError("El total a facturar debe ser mayor que cero", code="invalid_total")
            resolution, number = numbering.assign_number(
                prop, InvoiceResolution.DocumentKind.INVOICE, on_date=day
            )
            invoice = Invoice.objects.create(
                property=prop,
                reservation=reservation,
                folio=folios[0],
                resolution=resolution,
                kind=Invoice.Kind.INVOICE,
                status=Invoice.Status.DRAFT,
                number=number,
                prefix=resolution.prefix,
                full_number=f"{resolution.prefix}{number}",
                issue_date=day,
                issued_at=moment,
                currency=prop.currency,
                customer=document.customer,
                lines=document.lines,
                subtotal=document.subtotal,
                tax_total=document.tax_total,
                total=document.total,
                exempt_note=document.exempt_note,
                mode=integrations.get_setting(prop, "einvoice").mode,
                environment=resolution.environment,
                created_by=_user(actor),
            )
            invoice.charges.set(charges)
    except numbering.NumberingError as exc:
        numbering.raise_failure_alert(prop, exc)  # the alert raised inside the transaction was rolled back
        raise
    return _send(invoice, actor=actor, source=source, render=render)


def _send(invoice, *, actor, source, render=True) -> Invoice:
    provider = integrations.get_provider(invoice.property, "einvoice")
    try:
        result = provider.issue(invoice, supplier=supplier_info(invoice.property))
    except Exception as exc:  # a provider bug must not lose the document: it stays retryable
        logger.exception("E-invoice provider failed for %s", invoice.pk)
        result = {"status": Invoice.Status.ERROR, "message": f"Error del proveedor: {exc}", "response": {}}
    return _apply(
        invoice,
        result,
        provider_code=getattr(provider, "code", ""),
        actor=actor,
        source=source,
        render=render,
    )


def _apply(
    invoice, result: dict, *, provider_code: str, actor, source, render=True, refreshed=False
) -> Invoice:
    status = result.get("status") or Invoice.Status.ERROR
    with transaction.atomic():
        invoice = (
            Invoice.objects.select_for_update(of=("self",))
            .select_related("property", "resolution")
            .get(pk=invoice.pk)
        )
        before = invoice.status
        invoice.status = status
        invoice.provider = provider_code or invoice.provider
        invoice.provider_response = result.get("response") or {}
        invoice.last_attempt_at = timezone.now()
        if not refreshed:
            invoice.attempts += 1
        if status in DONE_STATUSES:
            invoice.cufe = result.get("cufe") or invoice.cufe
            invoice.qr_data = result.get("qr_data") or invoice.qr_data
            invoice.provider_ref = result.get("provider_ref") or invoice.provider_ref
            if result.get("number"):
                invoice.full_number = result["number"]
            invoice.error_message = ""
        else:
            invoice.error_message = result.get("message") or "El proveedor no aceptó el documento"
        invoice.save()
        if status in DONE_STATUSES:
            if invoice.kind == Invoice.Kind.CREDIT_NOTE and invoice.related_invoice_id:
                Invoice.objects.filter(pk=invoice.related_invoice_id).update(
                    status=Invoice.Status.CANCELLED, updated_at=timezone.now()
                )
            if render:
                _store_files(invoice, xml=result.get("xml"))
        _audit(invoice, before, actor=actor, source=source)
        _alert(invoice)
    return invoice


def _store_files(invoice, *, xml: bytes | None = None) -> None:
    invoice.pdf_file.save(_file_name(invoice, "pdf"), ContentFile(render_invoice_pdf(invoice)), save=False)
    if xml is None and invoice.mode == "simulated":
        xml = render_invoice_xml(invoice)
    fields = ["pdf_file", "updated_at"]
    if xml:
        invoice.xml_file.save(_file_name(invoice, "xml"), ContentFile(xml), save=False)
        fields.append("xml_file")
    invoice.save(update_fields=fields)


def _audit(invoice, before, *, actor, source) -> None:
    label = "Nota crédito" if invoice.kind == Invoice.Kind.CREDIT_NOTE else "Factura"
    if invoice.status in DONE_STATUSES:
        action = (
            "compliance.credit_note_issued"
            if invoice.kind == Invoice.Kind.CREDIT_NOTE
            else "compliance.invoice_issued"
        )
        summary = f"{label} {invoice.full_number} emitida ({invoice.get_status_display().lower()})"
    else:
        action = "compliance.invoice_failed"
        summary = f"{label} {invoice.full_number}: {invoice.error_message}"[:500]
    audit.record(
        action=action,
        target=invoice,
        summary=summary,
        actor=actor,
        source=source,
        property=invoice.property,
        changes={"status": [before, invoice.status], "total": [None, f"{invoice.total:.2f}"]},
    )


def alert_key(invoice) -> str:
    return f"compliance:invoice:{invoice.pk}"


def _alert(invoice) -> None:
    if invoice.status in DONE_STATUSES:
        alerts.resolve_alert(invoice.property, alert_key(invoice))
        return
    label = "La nota crédito" if invoice.kind == Invoice.Kind.CREDIT_NOTE else "La factura"
    rejected = invoice.status == Invoice.Status.REJECTED
    alerts.raise_alert(
        property=invoice.property,
        kind="invoice_rejected" if rejected else "invoice_error",
        severity="critical" if rejected else "warning",
        title=f"{label} {invoice.full_number} {'fue rechazada' if rejected else 'no se pudo emitir'}",
        message=invoice.error_message,
        link=f"/app/compliance?tab=invoices&invoice={invoice.pk}",
        dedupe_key=alert_key(invoice),
        data={"invoice_id": str(invoice.pk), "status": invoice.status},
        source="compliance",
    )


# ------------------------------------------------------------------------------------------------- retry


def retry_invoice(invoice, *, actor=None, source="user") -> Invoice:
    """Send again a draft / failed / rejected document (a rejected invoice takes the current customer data,
    the
    usual fix), or ask the provider about one still waiting for the DIAN (`issued`)."""
    invoice = Invoice.objects.select_related("property", "reservation__booker", "folio__guest").get(
        pk=invoice.pk
    )
    if invoice.status == Invoice.Status.ISSUED:
        return refresh_invoice(invoice, actor=actor, source=source)
    if invoice.status not in RETRYABLE_STATUSES:
        raise InvoiceConflict(
            f"El documento está {invoice.get_status_display().lower()}: no hay nada que reintentar",
            code="invalid_state",
        )
    if invoice.kind == Invoice.Kind.INVOICE:
        settings = get_settings(invoice.property)
        customer = invoice_customer(_customer_guest(invoice), final_consumer_id=settings.final_consumer_id)
        if customer != invoice.customer:
            invoice.customer = customer
            invoice.save(update_fields=["customer", "updated_at"])
    return _send(invoice, actor=actor, source=source)


def refresh_invoice(invoice, *, actor=None, source="user") -> Invoice:
    provider = integrations.get_provider(invoice.property, "einvoice")
    try:
        result = provider.refresh(invoice)
    except Exception as exc:
        logger.exception("E-invoice refresh failed for %s", invoice.pk)
        result = {"status": Invoice.Status.ERROR, "message": f"Error del proveedor: {exc}"}
    if result.get("status") == Invoice.Status.ERROR:
        # a failed status query says nothing about the document: keep it `issued` and record the message
        Invoice.objects.filter(pk=invoice.pk).update(
            error_message=result.get("message", ""), last_attempt_at=timezone.now(), updated_at=timezone.now()
        )
        invoice.refresh_from_db()
        return invoice
    return _apply(
        invoice,
        result,
        provider_code=getattr(provider, "code", ""),
        actor=actor,
        source=source,
        refreshed=True,
    )


# ------------------------------------------------------------------------------------------- credit note


def issue_credit_note(
    invoice, *, reason, actor=None, confirm=False, source="user", issued_at=None, render=True
) -> Invoice:
    """Annul an issued/accepted invoice with a credit note (correction concept 2, full amount). Risky action:
    requires `confirm=True` (the API also requires `compliance.void_invoice`). `issued_at` / `render` as in
    `issue_invoice` (backfills and the demo seed)."""
    if confirm is not True:
        raise ConfirmationRequired("Confirma la anulación de la factura con una nota crédito")
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("Indica el motivo de la nota crédito", code="reason_required")
    prop = invoice.property
    moment = issued_at or timezone.now()
    day = local_date(prop, moment)
    try:
        with transaction.atomic():
            original = Invoice.objects.select_for_update().get(pk=invoice.pk)
            if original.kind != Invoice.Kind.INVOICE:
                raise DomainError("Solo se anulan facturas", code="invalid_kind")
            if original.status not in DONE_STATUSES:
                raise InvoiceConflict(
                    f"La factura está {original.get_status_display().lower()}: solo se anulan facturas "
                    "emitidas",
                    code="invalid_state",
                )
            if original.credit_notes.filter(status__in=COVERING_STATUSES).exists():
                raise InvoiceConflict(
                    "Esta factura ya tiene una nota crédito en curso", code="credit_note_exists"
                )
            resolution, number = numbering.assign_number(
                prop, InvoiceResolution.DocumentKind.CREDIT_NOTE, on_date=day
            )
            note = Invoice.objects.create(
                property=prop,
                reservation=original.reservation,
                folio=original.folio,
                resolution=resolution,
                kind=Invoice.Kind.CREDIT_NOTE,
                status=Invoice.Status.DRAFT,
                number=number,
                prefix=resolution.prefix,
                full_number=f"{resolution.prefix}{number}",
                issue_date=day,
                issued_at=moment,
                currency=original.currency,
                customer=original.customer,
                lines=original.lines,
                subtotal=original.subtotal,
                tax_total=original.tax_total,
                total=original.total,
                exempt_note=original.exempt_note,
                reason=reason,
                related_invoice=original,
                mode=integrations.get_setting(prop, "einvoice").mode,
                environment=resolution.environment,
                created_by=_user(actor),
            )
    except numbering.NumberingError as exc:
        numbering.raise_failure_alert(prop, exc)
        raise
    return _send(note, actor=actor, source=source, render=render)


# -------------------------------------------------------------------------------------------------- files


def ensure_pdf(invoice) -> bytes:
    """The stored PDF, generated (and stored) when missing."""
    if invoice.pdf_file:
        try:
            with invoice.pdf_file.open("rb") as handle:
                return handle.read()
        except FileNotFoundError:
            pass
    data = render_invoice_pdf(invoice)
    invoice.pdf_file.save(_file_name(invoice, "pdf"), ContentFile(data), save=False)
    Invoice.objects.filter(pk=invoice.pk).update(pdf_file=invoice.pdf_file.name, updated_at=timezone.now())
    return data


def ensure_xml(invoice) -> bytes:
    """The stored XML; otherwise the provider's signed XML (real mode) or our UBL representation."""
    if invoice.xml_file:
        try:
            with invoice.xml_file.open("rb") as handle:
                return handle.read()
        except FileNotFoundError:
            pass
    data = None
    if invoice.mode == "real" and invoice.status in DONE_STATUSES:
        try:
            data = integrations.get_provider(invoice.property, "einvoice").fetch_xml(invoice)
        except Exception:  # noqa: BLE001 - fall back to the local representation
            logger.exception("Could not download the provider XML of %s", invoice.pk)
    data = data or render_invoice_xml(invoice)
    invoice.xml_file.save(_file_name(invoice, "xml"), ContentFile(data), save=False)
    Invoice.objects.filter(pk=invoice.pk).update(xml_file=invoice.xml_file.name, updated_at=timezone.now())
    return data


# ------------------------------------------------------------------------------------ automatic issuing


def departed(reservation) -> bool:
    """Every stay has left (checked out, or cancelled / no-show) and at least one checked out."""
    statuses = set(Stay.objects.filter(reservation=reservation).values_list("status", flat=True))
    return Stay.Status.CHECKED_OUT in statuses and not statuses & set(ACTIVE_STAY_STATUSES)


def auto_issue_on_checkout(stay) -> Invoice | None:
    """Receiver of `stay_checked_out`: when the last stay leaves and the hotel invoices automatically."""
    reservation = Reservation.objects.select_related("property").get(pk=stay.reservation_id)
    if not departed(reservation):
        return None
    settings = get_settings(reservation.property)
    if not settings.auto_issue_invoices:
        return None
    if settings.go_live_date and reservation.checkout_date < settings.go_live_date:
        return None
    pending = uninvoiced_by_reservation(reservation.property, [reservation.pk]).get(reservation.pk)
    if not pending or pending["total"] <= 0:
        return None
    try:
        return issue_invoice(reservation, source="automation")
    except DomainError as exc:  # numbering problems raise their own alert
        logger.warning("Automatic invoice of %s failed: %s", reservation.code, exc)
        return None


def issue_pending_invoices(property, *, lookback_days=LOOKBACK_DAYS, max_attempts=MAX_AUTO_ATTEMPTS) -> dict:
    """Automation `compliance.issue_pending_invoices`: retry drafts and technical errors, ask the provider
    about
    documents waiting for the DIAN and (with automatic invoicing on) invoice the reservations that left in the
    last `lookback_days` days without an invoice. Rejected documents wait for a person (they need a fix)."""
    report = {"retried": 0, "accepted": 0, "failed": 0, "refreshed": 0, "auto_issued": 0, "errors": []}
    retry = Invoice.objects.filter(
        property=property, status__in=(Invoice.Status.DRAFT, Invoice.Status.ERROR), attempts__lt=max_attempts
    )
    for invoice in retry.order_by("issue_date", "number"):
        report["retried"] += 1
        result = retry_invoice(invoice, source="automation")
        report["accepted" if result.status in DONE_STATUSES else "failed"] += 1
    for invoice in Invoice.objects.filter(property=property, status=Invoice.Status.ISSUED):
        refresh_invoice(invoice, source="automation")
        report["refreshed"] += 1
    settings = get_settings(property)
    if not settings.auto_issue_invoices:
        return report
    since = property.business_date - timedelta(days=lookback_days)
    if settings.go_live_date and settings.go_live_date > since:
        since = settings.go_live_date
    candidates = Reservation.objects.filter(
        property=property, status=Reservation.Status.CHECKED_OUT, checkout_date__gte=since
    ).order_by("checkout_date", "created_at")
    pending = uninvoiced_by_reservation(property, candidates.values_list("pk", flat=True))
    for reservation in candidates:
        if reservation.pk not in pending or pending[reservation.pk]["total"] <= 0:
            continue
        try:
            invoice = issue_invoice(reservation, source="automation")
        except DomainError as exc:
            report["failed"] += 1
            report["errors"].append(
                {"reservation": reservation.code, "code": exc.code, "detail": exc.message}
            )
            if isinstance(exc, numbering.NumberingError):  # no usable resolution: the rest would fail too
                break
            continue
        report["auto_issued"] += 1
        if invoice.status not in DONE_STATUSES:
            report["failed"] += 1
    return report
