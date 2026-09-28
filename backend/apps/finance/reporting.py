"""Read models for the finance API: folio totals, the daily payments summary, cash shift movements and CSV
exports (`;`-separated UTF-8 with BOM so Excel opens them correctly)."""

import csv
import io
from decimal import Decimal

from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.utils import timezone

from apps.finance.cash import cash_shift_totals, money_str
from apps.finance.models import Charge, Payment, Refund
from apps.finance.services import folio_expected_balance, reservation_balance

ZERO = Decimal("0")
MONEY = DecimalField(max_digits=14, decimal_places=2)
METHOD_LABELS = dict(Payment.Method.choices)


def _subtotal(queryset, group: str, expression) -> Coalesce:
    rows = queryset.order_by().values(group).annotate(total=Sum(expression)).values("total")[:1]
    return Coalesce(Subquery(rows, output_field=MONEY), Value(ZERO), output_field=MONEY)


def annotate_folio_totals(queryset):
    """Adds `charges_net`, `tax_amount_total`, `payments_sum`, `refunds_sum` per folio (one query)."""
    charges = Charge.objects.filter(folio=OuterRef("pk"), voided_at__isnull=True)
    return queryset.annotate(
        charges_net=_subtotal(charges, "folio", "amount"),
        tax_amount_total=_subtotal(charges, "folio", "tax_amount"),
        payments_sum=_subtotal(
            Payment.objects.filter(folio=OuterRef("pk"), status=Payment.Status.APPROVED), "folio", "amount"
        ),
        refunds_sum=_subtotal(
            Refund.objects.filter(payment__folio=OuterRef("pk"), status=Refund.Status.APPROVED),
            "payment__folio",
            "amount",
        ),
    )


def folio_totals(folio, *, with_reservation: bool = False, with_expected: bool = False) -> dict:
    """Totals of an annotated folio. `charges_total` = net + tax; balance = charges − payments + refunds.

    P4: `expected_balance` = what this folio will owe (its balance plus the lodging not posted yet that goes
    to it; `services.folio_expected_balance`), in the detail and in the folios of one reservation."""
    charges_net = folio.charges_net
    tax_total = folio.tax_amount_total
    charges_total = charges_net + tax_total
    totals = {
        "charges_net": charges_net,
        "tax_total": tax_total,
        "charges_total": charges_total,
        "payments_total": folio.payments_sum,
        "refunds_total": folio.refunds_sum,
        "balance": charges_total - folio.payments_sum + folio.refunds_sum,
    }
    if with_reservation or with_expected:
        totals["expected_balance"] = folio_expected_balance(folio)
    if with_reservation:
        totals["reservation_balance"] = (
            reservation_balance(folio.reservation) if folio.reservation_id else None
        )
    return totals


def payments_summary(property, date) -> dict:
    """Approved payments by method, refunds and charges of one business date."""
    payments = Payment.objects.filter(
        folio__property=property, status=Payment.Status.APPROVED, business_date=date
    )
    by_method = list(
        payments.values("method").annotate(count=Count("id"), total=Sum("amount")).order_by("method")
    )
    refunds = Refund.objects.filter(
        payment__folio__property=property, status=Refund.Status.APPROVED, business_date=date
    ).aggregate(count=Count("id"), total=Sum("amount"))
    charges = Charge.objects.filter(
        folio__property=property, voided_at__isnull=True, business_date=date
    ).aggregate(net=Sum("amount"), tax=Sum("tax_amount"))
    payments_total = sum((row["total"] for row in by_method), ZERO)
    refunds_total = refunds["total"] or ZERO
    net, tax = charges["net"] or ZERO, charges["tax"] or ZERO
    return {
        "date": date.isoformat(),
        "currency": property.currency,
        "payments": {"count": sum(row["count"] for row in by_method), "total": money_str(payments_total)},
        "refunds": {"count": refunds["count"], "total": money_str(refunds_total)},
        "net_total": money_str(payments_total - refunds_total),
        "by_method": [
            {"method": row["method"], "count": row["count"], "total": money_str(row["total"])}
            for row in by_method
        ],
        "charges": {"net": money_str(net), "tax": money_str(tax), "total": money_str(net + tax)},
    }


def _folio_refs(folio) -> dict:
    reservation = folio.reservation if folio.reservation_id else None
    guest = folio.guest if folio.guest_id else (reservation.booker if reservation else None)
    return {
        "folio_id": str(folio.pk),
        "reservation_id": str(reservation.pk) if reservation else None,
        "reservation_code": reservation.code if reservation else None,
        "guest_name": guest.full_name if guest else "",
    }


def shift_movements(shift) -> list[dict]:
    """Payments taken and refunds given during the shift, oldest first (every status, for the record)."""
    payments = Payment.objects.filter(cash_shift=shift).select_related(
        "folio__reservation__booker", "folio__guest"
    )
    refunds = Refund.objects.filter(cash_shift=shift).select_related(
        "payment__folio__reservation__booker", "payment__folio__guest"
    )
    rows = [
        {
            "id": str(p.pk),
            "kind": "payment",
            "created_at": p.created_at,
            "method": p.method,
            "amount": money_str(p.amount),
            "status": p.status,
            "reference": p.provider_reference,
            **_folio_refs(p.folio),
        }
        for p in payments
    ] + [
        {
            "id": str(r.pk),
            "kind": "refund",
            "created_at": r.created_at,
            "method": r.payment.method,
            "amount": money_str(r.amount),
            "status": r.status,
            "reference": r.provider_reference,
            **_folio_refs(r.payment.folio),
        }
        for r in refunds
    ]
    return sorted(rows, key=lambda row: row["created_at"])


def shift_totals_payload(shift) -> dict:
    totals = cash_shift_totals(shift)
    return {
        "opening_float": money_str(totals["opening_float"]),
        "cash_payments": money_str(totals["cash_payments"]),
        "cash_refunds": money_str(totals["cash_refunds"]),
        "expected_cash": money_str(totals["expected_cash"]),
        "payments_count": totals["payments_count"],
        "refunds_count": totals["refunds_count"],
        "by_method": [
            {"method": row["method"], "count": row["count"], "total": money_str(row["total"])}
            for row in totals["methods"]
        ],
    }


# --- CSV ----------------------------------------------------------------------------------------------


def csv_response(filename: str, header: list[str], rows: list[list]) -> HttpResponse:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _local(value) -> str:
    return timezone.localtime(value).strftime("%Y-%m-%d %H:%M") if value else ""


def shift_csv(shift) -> HttpResponse:
    kinds = {"payment": "Pago", "refund": "Reembolso"}
    rows = [
        [
            _local(m["created_at"]),
            kinds[m["kind"]],
            METHOD_LABELS.get(m["method"], m["method"]),
            m["reservation_code"] or "",
            m["guest_name"],
            m["reference"],
            m["status"],
            m["amount"],
        ]
        for m in shift_movements(shift)
    ]
    totals = shift_totals_payload(shift)
    rows += [
        [],
        ["Fondo inicial", totals["opening_float"]],
        ["Efectivo recibido", totals["cash_payments"]],
        ["Reembolsos en efectivo", totals["cash_refunds"]],
        [
            "Efectivo esperado",
            money_str(shift.expected_cash) if shift.expected_cash is not None else totals["expected_cash"],
        ],
        ["Efectivo contado", money_str(shift.counted_cash) if shift.counted_cash is not None else ""],
        ["Diferencia", money_str(shift.difference) if shift.difference is not None else ""],
    ]
    opened = timezone.localtime(shift.opened_at)
    return csv_response(
        f"caja-{opened:%Y%m%d}-{str(shift.pk)[:8]}.csv",
        ["Fecha", "Tipo", "Medio", "Reserva", "Huésped", "Referencia", "Estado", "Monto"],
        rows,
    )


def annotate_shift_cash(queryset):
    """Adds `cash_in` (approved cash payments) and `cash_out` (approved refunds of cash payments) per shift,
    the same figures as `cash_shift_totals`, in one query for the whole list."""
    cash_payments = Payment.objects.filter(
        cash_shift=OuterRef("pk"), status=Payment.Status.APPROVED, method=Payment.Method.CASH
    )
    cash_refunds = Refund.objects.filter(
        cash_shift=OuterRef("pk"), status=Refund.Status.APPROVED, payment__method=Payment.Method.CASH
    )
    return queryset.annotate(
        cash_in=_subtotal(cash_payments, "cash_shift", "amount"),
        cash_out=_subtotal(cash_refunds, "cash_shift", "amount"),
    )


def shifts_csv(shifts, start, end) -> HttpResponse:
    rows = []
    for shift in annotate_shift_cash(shifts):
        live_expected = shift.opening_float + shift.cash_in - shift.cash_out
        expected = shift.expected_cash if shift.expected_cash is not None else live_expected
        rows.append(
            [
                str(shift.pk)[:8],
                shift.user.email,
                _local(shift.opened_at),
                _local(shift.closed_at),
                money_str(shift.opening_float),
                money_str(shift.cash_in),
                money_str(shift.cash_out),
                money_str(expected),
                money_str(shift.counted_cash) if shift.counted_cash is not None else "",
                money_str(shift.difference) if shift.difference is not None else "",
                shift.notes.replace("\n", " "),
            ]
        )
    return csv_response(
        f"turnos-caja-{start or 'inicio'}-{end or 'hoy'}.csv",
        [
            "Turno",
            "Usuario",
            "Apertura",
            "Cierre",
            "Fondo inicial",
            "Efectivo recibido",
            "Reembolsos en efectivo",
            "Esperado",
            "Contado",
            "Diferencia",
            "Notas",
        ],
        rows,
    )


def open_or_closed(queryset, status: str | None):
    if status == "open":
        return queryset.filter(closed_at__isnull=True)
    if status == "closed":
        return queryset.filter(~Q(closed_at=None))
    return queryset
