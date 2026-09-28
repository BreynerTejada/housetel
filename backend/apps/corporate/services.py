"""Corporate billing and receivables (pilot plan P4).

Contract: `target_folio(reservation, kind) -> Folio` — finance's `post_charge` calls it for each charge
posted on a reservation's guest folio (night audit, penalties, portal extras, copilot…).

- Billing of a reservation (`set_billing`): who pays (guest | company) and which charge categories go to the
  company folio (`routing`, see `apps.corporate.routing`). Changing it can move the charges already posted
  (`reroute_existing_charges`), always through finance's audited `transfer_charge`.
- Receivables (cartera): company folios whose reservation finished (checked out, cancelled, no-show) or that
  have no reservation (opening balances) and still owe money. Aging by days since the document date (the
  company invoice's issue date, else the check-out / cancellation date, else the opening balance date) in
  buckets 0–30, 31–60, 61–90 and 90+; overdue past the due date (invoice due date or document date + terms).
- Payments on account (`record_account_payment`): each allocation is a finance `Payment` on a company folio;
  the rest stays as the company's credit until `apply_credit`. `void_account_payment` voids its payments.
- Credit (cupo): the company's exposure in the whole organization (open company folios + lodging still to
  post of its reservations in progress − unapplied credit) against `credit_limit`; going over raises an alert
  (it warns, it does not block: the guest's check-out is never blocked by a company with credit).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Min, Q, Sum
from django.utils import timezone

from apps.core import alerts, audit
from apps.core.errors import ConfirmationRequired, ConflictError, DomainError, NotFoundError
from apps.core.money import quantize
from apps.corporate.models import AccountPayment, AccountPaymentAllocation, Company, ReservationBilling
from apps.corporate.routing import ROUTE_VALUES, billing_of, routes_kind
from apps.finance import services as finance
from apps.finance.models import Charge, Folio, Payment
from apps.finance.reporting import annotate_folio_totals

logger = logging.getLogger("housetel.corporate")

ZERO = Decimal("0")
AR_METHODS = ["bank_transfer", "cash", "card_terminal", "other"]
FINISHED_STATUSES = ("checked_out", "cancelled", "no_show")
IN_PROGRESS_STATUSES = ("tentative", "confirmed", "checked_in")
AGING_BUCKETS = (("current", 0, 30), ("d31_60", 31, 60), ("d61_90", 61, 90), ("d90_plus", 91, None))
OPENING_BALANCE_SOURCE = "opening_balance"


class BillingError(DomainError):
    code = "invalid_billing"


class AllocationError(DomainError):
    code = "invalid_allocation"


# ------------------------------------------------------------------------------------------------ routing


def target_folio(reservation, kind) -> Folio:
    """The folio a charge of `kind` of this reservation goes to: the company folio when the reservation is
    billed to a company and `kind` is routed to it, otherwise the reservation's guest folio."""
    billing = billing_of(reservation)
    if routes_kind(billing, kind):
        return finance.get_or_create_company_folio(reservation, billing.company)
    return finance.get_or_create_folio(reservation)


def normalize_routing(routing) -> list[str]:
    values = [value for value in dict.fromkeys(routing or []) if value in ROUTE_VALUES]
    if not values or ReservationBilling.Route.ALL in values:
        return [ReservationBilling.Route.ALL.value]
    return [value for value in ROUTE_VALUES if value in values]


def _snapshot(billing) -> dict:
    return {
        "bill_to": billing.bill_to,
        "company": billing.company.legal_name if billing.company_id else None,
        "routing": list(billing.routing or []),
        "purchase_order": billing.purchase_order,
        "notes": billing.notes,
    }


def set_billing(
    reservation,
    *,
    bill_to,
    company=None,
    routing=None,
    purchase_order="",
    notes="",
    actor=None,
    move_existing=True,
) -> tuple[ReservationBilling, int]:
    """Save who pays the reservation. With `move_existing`, posted charges that the new rules send elsewhere
    move to their folio (not voided, not invoiced, open folios). Returns `(billing, moved charges)`."""
    if bill_to not in ReservationBilling.BillTo.values:
        raise BillingError("Elige a quién se factura: huésped o empresa", code="invalid_bill_to")
    if bill_to == ReservationBilling.BillTo.COMPANY:
        if company is None:
            raise BillingError("Elige la empresa", code="company_required")
        if company.organization_id != reservation.property.organization_id:
            raise NotFoundError("Empresa no encontrada")
        if not company.is_active:
            raise BillingError("La empresa está inactiva", code="company_inactive")
        routing = normalize_routing(routing)
    else:
        company, routing = None, []
    from apps.bookings.models import Reservation

    with transaction.atomic():
        Reservation.objects.select_for_update().filter(pk=reservation.pk).first()
        billing = ReservationBilling.objects.select_for_update().filter(reservation=reservation).first()
        before = _snapshot(billing) if billing else {"bill_to": "guest"}
        if billing is None:
            billing = ReservationBilling(reservation=reservation)
        billing.bill_to = bill_to
        billing.company = company
        billing.routing = routing
        billing.purchase_order = (purchase_order or "").strip()[:60]
        billing.notes = (notes or "").strip()
        billing.updated_by = actor if getattr(actor, "is_authenticated", False) else None
        billing.save()
        if company is not None:
            finance.get_or_create_company_folio(reservation, company)
        moved = reroute_existing_charges(reservation, actor=actor) if move_existing else 0
        after = _snapshot(billing)
        audit.record(
            action="corporate.billing_updated",
            target=billing,
            summary=(
                f"Facturación de {reservation.code}: "
                + (f"empresa {company.legal_name}" if company else "huésped")
                + (f" · {moved} cargos movidos" if moved else "")
            ),
            actor=actor,
            property=reservation.property,
            changes={**audit.diff(before, after), **({"moved_charges": moved} if moved else {})},
        )
    if company is not None:
        check_credit(company, property=reservation.property)
    return billing, moved


def reroute_existing_charges(reservation, *, actor=None) -> int:
    """Move the posted charges that sit on the wrong folio for the reservation's current billing rules (only
    between the main guest folio and the company folios; voided, invoiced or closed-folio charges stay)."""
    invoiced = set(
        Charge.invoices.through.objects.filter(
            charge__folio__reservation=reservation, invoice__kind="invoice"
        )
        .exclude(invoice__status="cancelled")
        .values_list("charge_id", flat=True)
    )
    charges = (
        Charge.objects.filter(
            folio__reservation=reservation, folio__status=Folio.Status.OPEN, voided_at__isnull=True
        )
        .filter(
            Q(folio__folio_type=Folio.FolioType.GUEST, folio__stay__isnull=True)
            | Q(folio__folio_type="company")
        )
        .exclude(pk__in=invoiced)
        .order_by("business_date", "created_at")
    )
    moved = 0
    for charge in charges:
        wanted = target_folio(reservation, charge.kind)
        if wanted.pk == charge.folio_id or wanted.status != Folio.Status.OPEN:
            continue
        finance.transfer_charge(
            charge, to_folio=wanted, actor=actor, reason="Reglas de facturación de la reserva"
        )
        moved += 1
    return moved


# ------------------------------------------------------------------------------------------------- credit


def _unapplied_by_payment(queryset) -> dict:
    """{account_payment_id: unapplied amount} of active account payments."""
    payments = list(
        queryset.filter(status=AccountPayment.Status.ACTIVE).annotate(applied=Sum("allocations__amount"))
    )
    return {payment.pk: payment.amount - (payment.applied or ZERO) for payment in payments}


def credit_status(company) -> dict:
    """Exposure of the company in the whole organization against its credit limit."""
    folios = annotate_folio_totals(
        Folio.objects.filter(company=company, folio_type=Folio.FolioType.COMPANY, status=Folio.Status.OPEN)
    )
    posted = sum((_annotated_balance(folio) for folio in folios), ZERO)
    unposted = ZERO
    routed = ReservationBilling.objects.filter(
        company=company,
        bill_to=ReservationBilling.BillTo.COMPANY,
        reservation__status__in=IN_PROGRESS_STATUSES,
    ).select_related("reservation")
    for billing in routed:
        if routes_kind(billing, "room"):
            unposted += finance.unposted_lodging(billing.reservation)
    unapplied = sum(_unapplied_by_payment(AccountPayment.objects.filter(company=company)).values(), ZERO)
    used = posted + unposted - unapplied
    limit = company.credit_limit
    return {
        "enabled": company.credit_enabled,
        "limit": limit,
        "used": used,
        "available": (limit - used) if limit is not None else None,
        "over_limit": bool(company.credit_enabled and limit is not None and used > limit),
        "terms_days": company.payment_terms_days,
    }


def check_credit(company, *, property) -> dict:
    """Raise (or resolve) the alert `corporate:credit:<company>` when the company goes over its limit."""
    status = credit_status(company)
    key = f"corporate:credit:{company.pk}"
    if status["over_limit"]:
        alerts.raise_alert(
            property=property,
            kind="company_over_credit",
            severity="warning",
            title=f"{company.legal_name} superó su cupo de crédito",
            message=(
                f"Usa {_money(status['used'])} de un cupo de {_money(status['limit'])}. Revisa su cartera o "
                "pide un pago antes de aceptar más consumos a crédito."
            ),
            link=f"/app/companies/{company.pk}",
            dedupe_key=key,
            data={
                "company_id": str(company.pk),
                "company": company.legal_name,
                "used": f"{status['used']:.2f}",
                "limit": f"{status['limit']:.2f}",
            },
            source="corporate",
        )
    else:
        alerts.resolve_alert(property, key)
    return status


# ------------------------------------------------------------------------------------------- receivables


@dataclass
class Item:
    """One company folio as a line of the statement."""

    folio: Folio
    balance: Decimal
    expected: Decimal
    finished: bool
    document_date: date | None = None
    due_date: date | None = None
    invoice: object | None = None
    extra: dict = field(default_factory=dict)


def _annotated_balance(folio) -> Decimal:
    return folio.charges_net + folio.tax_amount_total - folio.payments_sum + folio.refunds_sum


def _invoices_by_folio(folio_ids) -> dict:
    """{folio_id: latest valid invoice} (not annulled) covering the folio."""
    from apps.compliance.models import Invoice

    found = {}
    for invoice in (
        Invoice.objects.filter(folio_id__in=list(folio_ids), kind=Invoice.Kind.INVOICE)
        .exclude(status=Invoice.Status.CANCELLED)
        .order_by("issue_date", "created_at")
    ):
        found[invoice.folio_id] = invoice
    return found


def _items(property, *, company=None, as_of=None) -> list[Item]:
    """Company folios of the property (optionally one company) with their balances and dates."""
    today = as_of or property.business_date
    queryset = Folio.objects.filter(property=property, folio_type=Folio.FolioType.COMPANY)
    if company is not None:
        queryset = queryset.filter(company=company)
    folios = list(
        annotate_folio_totals(queryset.select_related("company", "reservation__booker")).order_by(
            "created_at"
        )
    )
    ids = [folio.pk for folio in folios]
    invoices = _invoices_by_folio(ids)
    first_dates = dict(
        Charge.objects.filter(folio_id__in=ids, voided_at__isnull=True)
        .values("folio_id")
        .annotate(first=Min("business_date"))
        .values_list("folio_id", "first")
    )
    lodging_of = {
        billing.reservation_id: billing.company_id
        for billing in ReservationBilling.objects.filter(
            reservation_id__in=[folio.reservation_id for folio in folios if folio.reservation_id]
        )
        if routes_kind(billing, "room")
    }
    items = []
    for folio in folios:
        balance = _annotated_balance(folio)
        reservation = folio.reservation if folio.reservation_id else None
        finished = reservation is None or reservation.status in FINISHED_STATUSES
        expected = balance
        if reservation is not None and not finished and lodging_of.get(reservation.pk) == folio.company_id:
            expected += finance.unposted_lodging(reservation)
        item = Item(folio=folio, balance=balance, expected=expected, finished=finished)
        invoice = invoices.get(folio.pk)
        item.invoice = invoice
        if invoice is not None:
            item.document_date = invoice.issue_date
        elif reservation is not None and finished:
            item.document_date = (
                reservation.checkout_date
                if reservation.status == "checked_out"
                else (
                    timezone.localdate(reservation.cancelled_at)
                    if reservation.cancelled_at
                    else reservation.checkin_date
                )
            )
        elif reservation is None:
            item.document_date = first_dates.get(folio.pk) or timezone.localdate(folio.created_at)
        if item.document_date is not None:
            terms = folio.company.payment_terms_days if folio.company.credit_enabled else 0
            item.due_date = (invoice.due_date if invoice is not None and invoice.due_date else None) or (
                item.document_date + timedelta(days=terms)
            )
        item.extra["today"] = today
        items.append(item)
    return items


def bucket_of(days: int) -> str:
    for key, low, high in AGING_BUCKETS:
        if days >= low and (high is None or days <= high):
            return key
    return "current"


def _empty_aging() -> dict:
    return {key: ZERO for key, _, _ in AGING_BUCKETS}


def _item_payload(item: Item) -> dict:
    folio, reservation = item.folio, item.folio.reservation if item.folio.reservation_id else None
    today = item.extra["today"]
    age = (today - item.document_date).days if item.document_date else 0
    overdue = (today - item.due_date).days if item.due_date and today > item.due_date else 0
    return {
        "folio_id": str(folio.pk),
        "folio_status": folio.status,
        "kind": "reservation" if reservation else "opening_balance",
        "label": folio.label,
        "reservation": (
            {
                "id": str(reservation.pk),
                "code": reservation.code,
                "status": reservation.status,
                "checkin_date": reservation.checkin_date.isoformat(),
                "checkout_date": reservation.checkout_date.isoformat(),
                "guest_name": reservation.booker.full_name,
            }
            if reservation
            else None
        ),
        "invoice": (
            {
                "id": str(item.invoice.pk),
                "number": item.invoice.full_number,
                "status": item.invoice.status,
                "issue_date": item.invoice.issue_date.isoformat(),
                "total": f"{item.invoice.total:.2f}",
            }
            if item.invoice is not None
            else None
        ),
        "document_date": item.document_date.isoformat() if item.document_date else None,
        "due_date": item.due_date.isoformat() if item.due_date else None,
        "age_days": max(age, 0),
        "overdue_days": max(overdue, 0),
        "bucket": bucket_of(max(age, 0)),
        "charges_total": f"{folio.charges_net + folio.tax_amount_total:.2f}",
        "paid": f"{folio.payments_sum - folio.refunds_sum:.2f}",
        "balance": f"{item.balance:.2f}",
        "expected_balance": f"{item.expected:.2f}",
    }


def _summarize(items: list[Item]) -> dict:
    open_items = [item for item in items if item.finished and item.balance != 0]
    progress = [item for item in items if not item.finished and item.expected != 0]
    aging = _empty_aging()
    overdue = ZERO
    for item in open_items:
        payload = _item_payload(item)
        aging[payload["bucket"]] += item.balance
        if payload["overdue_days"] > 0:
            overdue += item.balance
    return {
        "open": open_items,
        "progress": progress,
        "balance": sum((item.balance for item in open_items), ZERO),
        "in_progress": sum((item.expected for item in progress), ZERO),
        "overdue": overdue,
        "aging": aging,
    }


def _money_map(values: dict) -> dict:
    return {key: f"{value:.2f}" for key, value in values.items()}


def _credit_payload(status: dict) -> dict:
    return {
        "enabled": status["enabled"],
        "limit": f"{status['limit']:.2f}" if status["limit"] is not None else None,
        "used": f"{status['used']:.2f}",
        "available": f"{status['available']:.2f}" if status["available"] is not None else None,
        "over_limit": status["over_limit"],
        "terms_days": status["terms_days"],
    }


def account_payments_payload(company, property, *, limit=50) -> list[dict]:
    payments = (
        AccountPayment.objects.filter(company=company, property=property)
        .select_related("created_by", "voided_by")
        .prefetch_related("allocations__folio__reservation")
        .order_by("-received_on", "-created_at")[:limit]
    )
    rows = []
    for payment in payments:
        allocations = list(payment.allocations.all())
        applied = sum((allocation.amount for allocation in allocations), ZERO)
        rows.append(
            {
                "id": str(payment.pk),
                "amount": f"{payment.amount:.2f}",
                "applied": f"{applied:.2f}",
                "unapplied": f"{(payment.amount - applied) if payment.status == 'active' else ZERO:.2f}",
                "method": payment.method,
                "reference": payment.reference,
                "received_on": payment.received_on.isoformat(),
                "notes": payment.notes,
                "status": payment.status,
                "created_by": payment.created_by.full_name if payment.created_by_id else None,
                "created_at": payment.created_at.isoformat(),
                "voided_at": payment.voided_at.isoformat() if payment.voided_at else None,
                "void_reason": payment.void_reason,
                "allocations": [
                    {
                        "id": str(allocation.pk),
                        "folio_id": str(allocation.folio_id),
                        "amount": f"{allocation.amount:.2f}",
                        "label": allocation.folio.label,
                        "reservation_code": allocation.folio.reservation.code
                        if allocation.folio.reservation_id
                        else None,
                    }
                    for allocation in allocations
                ],
            }
        )
    return rows


def unapplied_credit(company, property) -> Decimal:
    return sum(
        _unapplied_by_payment(AccountPayment.objects.filter(company=company, property=property)).values(),
        ZERO,
    )


def statement(company, property, *, as_of=None) -> dict:
    """Account statement of a company at one property: open items with aging, reservations in progress,
    payments on account, unapplied credit and the organization-wide credit status."""
    items = _items(property, company=company, as_of=as_of)
    summary = _summarize(items)
    unapplied = unapplied_credit(company, property)
    open_items = sorted(
        summary["open"], key=lambda item: (item.document_date or date.max, item.folio.created_at)
    )
    return {
        "as_of": (as_of or property.business_date).isoformat(),
        "currency": property.currency,
        "totals": {
            "balance": f"{summary['balance']:.2f}",
            "overdue": f"{summary['overdue']:.2f}",
            "in_progress": f"{summary['in_progress']:.2f}",
            "unapplied": f"{unapplied:.2f}",
            "net_balance": f"{summary['balance'] - unapplied:.2f}",
            "open_items": len(open_items),
        },
        "aging": _money_map(summary["aging"]),
        "credit": _credit_payload(credit_status(company)),
        "items": [_item_payload(item) for item in open_items],
        "in_progress": [_item_payload(item) for item in summary["progress"]],
        "payments": account_payments_payload(company, property),
    }


def receivables(property, *, as_of=None) -> dict:
    """Receivables of the property by company (the `/app/receivables` summary)."""
    items = _items(property, as_of=as_of)
    by_company: dict = {}
    for item in items:
        by_company.setdefault(item.folio.company_id, []).append(item)
    unapplied_rows = (
        AccountPayment.objects.filter(property=property, status=AccountPayment.Status.ACTIVE)
        .values("company_id")
        .annotate(amount=Sum("amount"))
    )
    applied_rows = (
        AccountPaymentAllocation.objects.filter(
            account_payment__property=property, account_payment__status=AccountPayment.Status.ACTIVE
        )
        .values("account_payment__company_id")
        .annotate(amount=Sum("amount"))
    )
    applied = {row["account_payment__company_id"]: row["amount"] or ZERO for row in applied_rows}
    unapplied = {
        row["company_id"]: (row["amount"] or ZERO) - applied.get(row["company_id"], ZERO)
        for row in unapplied_rows
    }
    company_ids = set(by_company) | {pk for pk, value in unapplied.items() if value}
    companies = {company.pk: company for company in Company.objects.filter(pk__in=company_ids)}
    totals = {"balance": ZERO, "overdue": ZERO, "in_progress": ZERO, "unapplied": ZERO}
    aging = _empty_aging()
    rows = []
    for company_id in company_ids:
        company = companies[company_id]
        summary = _summarize(by_company.get(company_id, []))
        credit = unapplied.get(company_id, ZERO)
        if not summary["open"] and not summary["progress"] and not credit:
            continue
        oldest = max((_item_payload(item)["age_days"] for item in summary["open"]), default=0)
        rows.append(
            {
                "company": company_ref(company),
                "balance": f"{summary['balance']:.2f}",
                "overdue": f"{summary['overdue']:.2f}",
                "in_progress": f"{summary['in_progress']:.2f}",
                "unapplied": f"{credit:.2f}",
                "net_balance": f"{summary['balance'] - credit:.2f}",
                "aging": _money_map(summary["aging"]),
                "open_items": len(summary["open"]),
                "oldest_days": oldest,
            }
        )
        for key in aging:
            aging[key] += summary["aging"][key]
        totals["balance"] += summary["balance"]
        totals["overdue"] += summary["overdue"]
        totals["in_progress"] += summary["in_progress"]
        totals["unapplied"] += credit
    rows.sort(
        key=lambda row: (-Decimal(row["overdue"]), -Decimal(row["balance"]), row["company"]["legal_name"])
    )
    return {
        "as_of": (as_of or property.business_date).isoformat(),
        "currency": property.currency,
        "totals": {
            **_money_map(totals),
            "net_balance": f"{totals['balance'] - totals['unapplied']:.2f}",
            "companies": len(rows),
        },
        "aging": _money_map(aging),
        "companies": rows,
    }


def company_balances(property, companies) -> dict:
    """{company_id: {"balance", "overdue", "in_progress"}} at the property (companies list)."""
    wanted = {company.pk for company in companies}
    by_company: dict = {}
    for item in _items(property):
        if item.folio.company_id in wanted:
            by_company.setdefault(item.folio.company_id, []).append(item)
    result = {}
    for company_id, items in by_company.items():
        summary = _summarize(items)
        result[company_id] = {
            "balance": summary["balance"],
            "overdue": summary["overdue"],
            "in_progress": summary["in_progress"],
        }
    return result


def company_ref(company) -> dict:
    from apps.corporate.nit import format_nit

    return {
        "id": str(company.pk),
        "legal_name": company.legal_name,
        "trade_name": company.trade_name,
        "kind": company.kind,
        "nit": company.nit,
        "dv": company.dv,
        "nit_display": format_nit(company.nit, company.dv),
        "credit_enabled": company.credit_enabled,
        "payment_terms_days": company.payment_terms_days,
        "is_active": company.is_active,
    }


def company_reservations(company, property) -> list[dict]:
    """Reservations of the property billed to the company (or with a folio of it), newest arrival first."""
    from apps.bookings.models import Reservation

    reservation_ids = set(
        ReservationBilling.objects.filter(company=company, reservation__property=property).values_list(
            "reservation_id", flat=True
        )
    ) | set(
        Folio.objects.filter(company=company, property=property, reservation__isnull=False).values_list(
            "reservation_id", flat=True
        )
    )
    reservations = (
        Reservation.objects.filter(pk__in=reservation_ids)
        .select_related("booker", "billing")
        .order_by("-checkin_date", "-created_at")[:200]
    )
    items = {
        item.folio.reservation_id: item
        for item in _items(property, company=company)
        if item.folio.reservation_id
    }
    rows = []
    for reservation in reservations:
        billing = getattr(reservation, "billing", None)
        item = items.get(reservation.pk)
        rows.append(
            {
                "id": str(reservation.pk),
                "code": reservation.code,
                "status": reservation.status,
                "checkin_date": reservation.checkin_date.isoformat(),
                "checkout_date": reservation.checkout_date.isoformat(),
                "guest_name": reservation.booker.full_name,
                "billed_to_company": bool(
                    billing and billing.bill_to == "company" and billing.company_id == company.pk
                ),
                "routing": list(billing.routing or []) if billing else [],
                "purchase_order": billing.purchase_order if billing else "",
                "company_balance": f"{item.expected if item else ZERO:.2f}",
                "invoice_number": item.invoice.full_number if item and item.invoice is not None else "",
            }
        )
    return rows


# ----------------------------------------------------------------------------------- payments on account


def _open_folio_for(company, property, folio_id) -> Folio:
    folio = (
        Folio.objects.filter(
            pk=folio_id, company=company, property=property, folio_type=Folio.FolioType.COMPANY
        )
        .select_related("reservation", "company")
        .first()
    )
    if folio is None:
        raise AllocationError("Ese folio no es de esta empresa en este hotel", code="folio_not_found")
    return folio


def _outstanding(folio) -> Decimal:
    """What can still be applied to a company folio: its expected balance (posted + lodging to post)."""
    return finance.folio_expected_balance(folio)


def _auto_plan(company, property, amount) -> list[tuple[Folio, Decimal]]:
    """Oldest open items first (FIFO by document date) until `amount` runs out."""
    items = [item for item in _items(property, company=company) if item.finished and item.balance > 0]
    items.sort(key=lambda item: (item.document_date or date.max, item.folio.created_at))
    plan, left = [], amount
    for item in items:
        if left <= 0:
            break
        take = min(left, item.balance)
        plan.append((item.folio, take))
        left -= take
    return plan


def _explicit_plan(company, property, allocations, currency) -> list[tuple[Folio, Decimal]]:
    plan, seen = [], set()
    for allocation in allocations or []:
        amount = quantize(allocation.get("amount") or 0, currency)
        if amount <= 0:
            continue
        folio = _open_folio_for(company, property, allocation.get("folio_id"))
        if folio.pk in seen:
            raise AllocationError("Cada folio va una sola vez", code="duplicate_folio")
        seen.add(folio.pk)
        if folio.status == Folio.Status.CLOSED:
            raise AllocationError(
                f"El folio de {folio.label or folio.reservation} ya está saldado", code="folio_closed"
            )
        outstanding = _outstanding(folio)
        if amount > outstanding:
            raise AllocationError(
                f"Al folio {folio.reservation.code if folio.reservation_id else folio.label} solo le faltan "
                f"{_money(outstanding)}",
                code="allocation_exceeds_balance",
                outstanding=f"{outstanding:.2f}",
            )
        plan.append((folio, amount))
    return plan


def _allocate(account_payment, folio, amount, actor) -> AccountPaymentAllocation:
    reference = account_payment.reference or f"Pago a cuenta {account_payment.company.legal_name}"
    payment = finance.record_payment(
        folio, amount=amount, method=account_payment.method, reference=reference[:120], actor=actor
    )
    Payment.objects.filter(pk=payment.pk).update(
        notes=f"Pago a cuenta de {account_payment.company.legal_name}"[:1000]
    )
    return AccountPaymentAllocation.objects.create(
        account_payment=account_payment, folio=folio, payment=payment, amount=amount
    )


def record_account_payment(
    company,
    property,
    *,
    amount,
    method,
    reference="",
    notes="",
    received_on=None,
    allocations=None,
    auto_allocate=False,
    actor=None,
) -> AccountPayment:
    """Record money a company paid on account: applied to the given folios (`allocations = [{folio_id,
    amount}]`) or to the oldest open items (`auto_allocate`); what is left stays as the company's credit.
    Cash needs the user's open cash shift (finance rule)."""
    currency = property.currency
    amount = quantize(amount, currency)
    if amount <= 0:
        raise DomainError("El monto debe ser mayor que cero", code="invalid_amount")
    if method not in AR_METHODS:
        raise DomainError(f"Medio de pago inválido: {method}", code="invalid_method")
    if company.organization_id != property.organization_id:
        raise NotFoundError("Empresa no encontrada")
    received_on = received_on or property.business_date
    if received_on > property.business_date:
        raise DomainError("La fecha del pago no puede ser futura", code="invalid_date")
    with transaction.atomic():
        plan = (
            _auto_plan(company, property, amount)
            if auto_allocate and not allocations
            else _explicit_plan(company, property, allocations, currency)
        )
        applied = sum((value for _, value in plan), ZERO)
        if applied > amount:
            raise AllocationError(
                f"Aplicaste {_money(applied)} y el pago es de {_money(amount)}",
                code="allocation_exceeds_payment",
            )
        account_payment = AccountPayment.objects.create(
            company=company,
            property=property,
            amount=amount,
            method=method,
            reference=(reference or "").strip()[:120],
            received_on=received_on,
            notes=(notes or "").strip(),
            created_by=actor if getattr(actor, "is_authenticated", False) else None,
        )
        for folio, value in plan:
            _allocate(account_payment, folio, value, actor)
        audit.record(
            action="corporate.account_payment_recorded",
            target=account_payment,
            summary=(
                f"Pago a cuenta de {company.legal_name} por {_money(amount)}: {_money(applied)} aplicados"
                + (f", {_money(amount - applied)} a favor" if amount > applied else "")
            ),
            actor=actor,
            property=property,
            changes={
                "amount": f"{amount:.2f}",
                "applied": f"{applied:.2f}",
                "method": method,
                "reference": account_payment.reference,
                "folios": [str(folio.pk) for folio, _ in plan],
            },
        )
    for folio, _ in plan:
        finance.close_folio_if_settled(folio)
    check_credit(company, property=property)
    return account_payment


def apply_credit(
    company, property, *, allocations=None, auto=False, actor=None
) -> list[AccountPaymentAllocation]:
    """Apply the company's unapplied credit (oldest payments first) to folios (explicit or FIFO)."""
    currency = property.currency
    created = []
    with transaction.atomic():
        sources = [
            payment
            for payment in AccountPayment.objects.select_for_update()
            .filter(company=company, property=property, status=AccountPayment.Status.ACTIVE)
            .order_by("received_on", "created_at")
        ]
        left = {
            payment.pk: payment.amount - (payment.allocations.aggregate(total=Sum("amount"))["total"] or ZERO)
            for payment in sources
        }
        available = sum(left.values(), ZERO)
        if available <= 0:
            raise AllocationError("La empresa no tiene saldo a favor para aplicar", code="no_credit")
        plan = (
            _auto_plan(company, property, available)
            if auto and not allocations
            else _explicit_plan(company, property, allocations, currency)
        )
        wanted = sum((value for _, value in plan), ZERO)
        if not plan:
            raise AllocationError("No hay nada que aplicar", code="nothing_to_apply")
        if wanted > available:
            raise AllocationError(
                f"El saldo a favor es de {_money(available)}", code="allocation_exceeds_credit"
            )
        for folio, value in plan:
            remaining = value
            for source in sources:
                if remaining <= 0:
                    break
                take = min(left[source.pk], remaining)
                if take <= 0:
                    continue
                created.append(_allocate(source, folio, take, actor))
                left[source.pk] -= take
                remaining -= take
        audit.record(
            action="corporate.credit_applied",
            target=company,
            summary=f"Aplicó {_money(wanted)} del saldo a favor de {company.legal_name}",
            actor=actor,
            property=property,
            changes={"amount": f"{wanted:.2f}", "folios": [str(folio.pk) for folio, _ in plan]},
        )
    for folio, _ in plan:
        finance.close_folio_if_settled(folio)
    return created


def void_account_payment(account_payment, *, reason, actor=None, confirm=False) -> AccountPayment:
    """Annul a payment on account recorded by mistake: its payments are voided (closed folios reopen)."""
    if confirm is not True:
        raise ConfirmationRequired("Confirma la anulación del pago a cuenta")
    reason = (reason or "").strip()
    if not reason:
        raise DomainError("Indica el motivo", code="reason_required")
    with transaction.atomic():
        account_payment = (
            AccountPayment.objects.select_for_update()
            .select_related("company", "property")
            .get(pk=account_payment.pk)
        )
        if account_payment.status != AccountPayment.Status.ACTIVE:
            raise ConflictError("Este pago a cuenta ya está anulado", code="already_voided")
        for allocation in account_payment.allocations.select_related("folio", "payment"):
            if allocation.folio.status == Folio.Status.CLOSED:
                finance.reopen_folio(allocation.folio, actor=actor, reason="anulación de un pago a cuenta")
            if allocation.payment.status == Payment.Status.APPROVED:
                finance.void_payment(
                    allocation.payment, reason=f"Pago a cuenta anulado: {reason}", actor=actor, confirm=True
                )
        account_payment.status = AccountPayment.Status.VOIDED
        account_payment.voided_at = timezone.now()
        account_payment.voided_by = actor if getattr(actor, "is_authenticated", False) else None
        account_payment.void_reason = reason
        account_payment.save(update_fields=["status", "voided_at", "voided_by", "void_reason", "updated_at"])
        audit.record(
            action="corporate.account_payment_voided",
            target=account_payment,
            summary=(
                f"Anuló un pago a cuenta de {account_payment.company.legal_name} por "
                f"{_money(account_payment.amount)}"
            ),
            actor=actor,
            property=account_payment.property,
            changes={"reason": reason, "amount": f"{account_payment.amount:.2f}"},
        )
    check_credit(account_payment.company, property=account_payment.property)
    return account_payment


# ------------------------------------------------------------------------------------- opening balances


def add_opening_balance(
    company, property, *, amount, document_date, reference, description="", actor=None
) -> Folio:
    """Register a receivable that comes from before Housetel (e.g. a legacy invoice): a company folio without
    reservation with one charge dated on the document date (not invoiced again in Housetel)."""
    amount = quantize(amount, property.currency)
    reference = (reference or "").strip()
    if amount <= 0:
        raise DomainError("El monto debe ser mayor que cero", code="invalid_amount")
    if not reference:
        raise DomainError(
            "Indica el número del documento (p. ej. la factura anterior)", code="reference_required"
        )
    if document_date > property.business_date:
        raise DomainError("La fecha del documento no puede ser futura", code="invalid_date")
    if company.organization_id != property.organization_id:
        raise NotFoundError("Empresa no encontrada")
    with transaction.atomic():
        folio = Folio.objects.create(
            property=property,
            company=company,
            folio_type=Folio.FolioType.COMPANY,
            currency=property.currency,
            label=reference[:120],
        )
        with finance.explicit_folio():
            finance.post_charge(
                folio,
                kind="other",
                amount=amount,
                description=(description or f"Saldo inicial de cartera · {reference}")[:255],
                actor=actor,
                source=OPENING_BALANCE_SOURCE,
                business_date=document_date,
            )
        audit.record(
            action="corporate.opening_balance_added",
            target=folio,
            summary=f"Saldo inicial de {company.legal_name}: {reference} por {_money(amount)}",
            actor=actor,
            property=property,
            changes={
                "amount": f"{amount:.2f}",
                "document_date": document_date.isoformat(),
                "reference": reference,
            },
        )
    check_credit(company, property=property)
    return folio


# ------------------------------------------------------------------------------------------------ helpers


def _money(amount) -> str:
    return finance._money(amount or ZERO)
