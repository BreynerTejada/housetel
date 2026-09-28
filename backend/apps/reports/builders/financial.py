"""Financial reports (permission ``reports.financial``): daily revenue by charge type, payments by method,
cash shifts, taxes (VAT: taxable, exempt and untaxed base) and receivables."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Count, DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.bookings.models import Reservation
from apps.bookings.services.queries import with_balance
from apps.finance.models import CashShift, Charge, Payment, Refund
from apps.finance.reporting import annotate_shift_cash
from apps.reports.builders.common import (
    L,
    all_days,
    base_notes,
    guest_name,
    period_column,
    period_table_title,
    today_marker,
)
from apps.reports.engine import RevenueByKind, bucket_start, local_date, pct, revenue_by_kind
from apps.reports.labels import (
    AGING_BUCKETS,
    PAYMENT_METHODS,
    RECEIVABLE_SEGMENTS,
    RESERVATION_STATUSES,
    SHIFT_STATUSES,
    enum_label,
    enum_labels,
    pick,
    tr,
)
from apps.reports.output import (
    CODE,
    DATE,
    DATETIME,
    MONEY,
    NUMBER,
    PERCENT,
    STATUS,
    TEXT,
    Chart,
    Column,
    Kpi,
    ReportResult,
    Series,
    Table,
)

ZERO = Decimal("0")
MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)
ONLINE_METHODS = ("wompi_card", "wompi_pse", "wompi_nequi", "wompi_other")


# --- daily revenue ------------------------------------------------------------------------------------------


def _revenue_totals(prop, start, end) -> RevenueByKind:
    totals = RevenueByKind()
    for figures in revenue_by_kind(prop, start, end).values():
        totals.add(figures)
    return totals


def build_daily_revenue(p) -> ReportResult:
    lang = p.lang
    by_day = revenue_by_kind(p.prop, p.start, p.end)
    group = p.group_by or "day"
    buckets: dict = {}
    for day in all_days(p):
        key = bucket_start(day, group)
        bucket = buckets.setdefault(key, RevenueByKind())
        if day in by_day:
            bucket.add(by_day[day])
    totals = RevenueByKind()
    rows, chart_rows = [], []
    for key in sorted(buckets):
        figures = buckets[key]
        totals.add(figures)
        rows.append(
            {
                "date": key,
                "room": figures.room,
                "extras": figures.extras,
                "penalties": figures.penalties,
                "fees": figures.fees,
                "net": figures.net,
                "taxes": figures.taxes,
                "gross": figures.gross,
            }
        )
        chart_rows.append(
            {"date": key, "room": figures.room, "extras": figures.extras, "other": figures.other}
        )
    previous = _revenue_totals(p.prop, p.compare_start, p.compare_end) if p.compared else None

    def prev(attr):
        return getattr(previous, attr) if previous is not None else None

    summary = [
        Kpi("net", tr("net_revenue", lang), MONEY, totals.net, prev("net")),
        Kpi("room", tr("room_revenue", lang), MONEY, totals.room, prev("room")),
        Kpi("extras", tr("extras_revenue", lang), MONEY, totals.extras, prev("extras")),
        Kpi(
            "other",
            L(lang, "Penalidades, cargos y ajustes", "Penalties, fees and adjustments"),
            MONEY,
            totals.other,
            prev("other"),
            "neutral",
        ),
        Kpi("taxes", tr("taxes", lang), MONEY, totals.taxes, prev("taxes"), "neutral"),
        Kpi("gross", tr("gross_revenue", lang), MONEY, totals.gross, prev("gross")),
    ]
    columns = [
        period_column(p),
        Column("room", tr("room_revenue_short", lang), MONEY),
        Column("extras", tr("extras_revenue", lang), MONEY),
        Column("penalties", tr("penalties", lang), MONEY),
        Column("fees", tr("fees_revenue", lang), MONEY),
        Column("net", tr("net_revenue", lang), MONEY),
        Column("taxes", tr("taxes", lang), MONEY),
        Column("gross", tr("gross_revenue", lang), MONEY),
    ]
    totals_row = {
        "date": None,
        "room": totals.room,
        "extras": totals.extras,
        "penalties": totals.penalties,
        "fees": totals.fees,
        "net": totals.net,
        "taxes": totals.taxes,
        "gross": totals.gross,
    }
    charts = [
        Chart(
            key="revenue",
            title=tr("c_daily_revenue", lang),
            type="stacked_column",
            x="date",
            x_type="month" if group == "month" else "date",
            value_type=MONEY,
            series=[
                Series("room", tr("room_revenue_short", lang), "stack"),
                Series("extras", tr("extras_revenue", lang), "stack"),
                Series("other", L(lang, "Penalidades y otros", "Penalties and other"), "stack"),
            ],
            data=chart_rows,
            marker=today_marker(p) if group == "day" else None,
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Cargos publicados y no anulados, por su fecha de negocio. Montos netos; los impuestos van "
            "aparte. "
            "Solo lo publicado: las noches futuras aún no son ingreso (ver el reporte de rendimiento para el "
            "pronóstico).",
            "Posted, non-voided charges by business date. Net amounts; taxes go apart. Only what was posted: "
            "future "
            "nights are not revenue yet (see the performance report for the forecast).",
        ),
        L(
            lang,
            "Cargos y ajustes: cargos manuales, ajustes (los descuentos restan) y otros. Penalidades: "
            "cancelación "
            "y no-show.",
            "Fees and adjustments: manual fees, adjustments (discounts subtract) and other. Penalties: "
            "cancellation and no-show.",
        ),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[Table("periods", period_table_title(p), columns, rows, totals_row)],
        notes=notes,
    )


# --- payments by method -------------------------------------------------------------------------------------


def _payments(prop, start, end):
    return Payment.objects.filter(
        folio__property=prop, status=Payment.Status.APPROVED, business_date__gte=start, business_date__lte=end
    )


def _refunds(prop, start, end):
    return Refund.objects.filter(
        payment__folio__property=prop,
        status=Refund.Status.APPROVED,
        business_date__gte=start,
        business_date__lte=end,
    )


def _payment_totals(prop, start, end) -> dict:
    payments = _payments(prop, start, end).aggregate(total=Sum("amount"), count=Count("id"))
    online = _payments(prop, start, end).filter(method__in=ONLINE_METHODS).aggregate(total=Sum("amount"))
    refunds = _refunds(prop, start, end).aggregate(total=Sum("amount"))
    total = payments["total"] or ZERO
    return {
        "total": total,
        "count": payments["count"] or 0,
        "refunds": refunds["total"] or ZERO,
        "net": total - (refunds["total"] or ZERO),
        "online": pct(online["total"] or ZERO, total),
    }


def build_payments_by_method(p) -> ReportResult:
    lang = p.lang
    by_method: dict = defaultdict(lambda: {"count": 0, "total": ZERO, "refunds_count": 0, "refunds": ZERO})
    for row in (
        _payments(p.prop, p.start, p.end)
        .order_by()
        .values("method")
        .annotate(count=Count("id"), total=Sum("amount"))
    ):
        by_method[row["method"]]["count"] = row["count"]
        by_method[row["method"]]["total"] = row["total"] or ZERO
    for row in (
        _refunds(p.prop, p.start, p.end)
        .order_by()
        .values("payment__method")
        .annotate(count=Count("id"), total=Sum("amount"))
    ):
        by_method[row["payment__method"]]["refunds_count"] = row["count"]
        by_method[row["payment__method"]]["refunds"] = row["total"] or ZERO
    totals = _payment_totals(p.prop, p.start, p.end)
    rows = [
        {
            "method": method,
            "count": data["count"],
            "total": data["total"],
            "share": pct(data["total"], totals["total"]),
            "refunds": data["refunds"],
            "net": data["total"] - data["refunds"],
        }
        for method, data in sorted(by_method.items(), key=lambda item: -item[1]["total"])
    ]
    method_columns = [
        Column("method", tr("method", lang), CODE, labels=enum_labels(PAYMENT_METHODS, lang)),
        Column("count", tr("payments_count", lang), NUMBER),
        Column("total", tr("payments", lang), MONEY),
        Column("share", tr("share", lang), PERCENT),
        Column("refunds", tr("refunds", lang), MONEY),
        Column("net", tr("net_collected", lang), MONEY),
    ]
    totals_row = {
        "method": None,
        "count": totals["count"],
        "total": totals["total"],
        "share": pct(totals["total"], totals["total"]),
        "refunds": totals["refunds"],
        "net": totals["net"],
    }
    daily: dict = defaultdict(lambda: {"count": 0, "total": ZERO, "refunds": ZERO})
    for row in (
        _payments(p.prop, p.start, p.end)
        .order_by()
        .values("business_date")
        .annotate(count=Count("id"), total=Sum("amount"))
    ):
        daily[row["business_date"]]["count"] = row["count"]
        daily[row["business_date"]]["total"] = row["total"] or ZERO
    for row in (
        _refunds(p.prop, p.start, p.end).order_by().values("business_date").annotate(total=Sum("amount"))
    ):
        daily[row["business_date"]]["refunds"] = row["total"] or ZERO
    daily_rows = [
        {
            "date": day,
            "count": daily[day]["count"],
            "total": daily[day]["total"],
            "refunds": daily[day]["refunds"],
            "net": daily[day]["total"] - daily[day]["refunds"],
        }
        for day in all_days(p)
    ]
    daily_columns = [
        Column("date", tr("date", lang), DATE),
        Column("count", tr("payments_count", lang), NUMBER),
        Column("total", tr("payments", lang), MONEY),
        Column("refunds", tr("refunds", lang), MONEY),
        Column("net", tr("net_collected", lang), MONEY),
    ]
    previous = _payment_totals(p.prop, p.compare_start, p.compare_end) if p.compared else None

    def prev(key):
        return previous[key] if previous else None

    summary = [
        Kpi("total", tr("payments", lang), MONEY, totals["total"], prev("total")),
        Kpi("refunds", tr("refunds", lang), MONEY, totals["refunds"], prev("refunds"), "lower-is-better"),
        Kpi("net", tr("net_collected", lang), MONEY, totals["net"], prev("net")),
        Kpi("count", tr("payments_count", lang), NUMBER, totals["count"], prev("count"), "neutral"),
        Kpi("online", tr("online_share", lang), PERCENT, totals["online"], prev("online"), "neutral"),
    ]
    charts = [
        Chart(
            key="methods",
            title=tr("c_methods", lang),
            type="hbar",
            x="label",
            x_type="text",
            value_type=MONEY,
            series=[Series("total", tr("payments", lang))],
            data=[
                {
                    "method": row["method"],
                    "label": enum_label(PAYMENT_METHODS, row["method"], lang),
                    "total": row["total"],
                }
                for row in rows
                if row["total"]
            ],
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Pagos aprobados por su fecha de negocio (los anulados, rechazados y pendientes no cuentan). "
            "Reembolsos aprobados por su fecha de negocio, en el medio del pago original.",
            "Approved payments by business date (voided, declined and pending ones do not count). Approved "
            "refunds "
            "by business date, under the method of the original payment.",
        ),
        L(
            lang,
            "Pagos en línea: Wompi (tarjeta, PSE, Nequi) sobre el total de pagos.",
            "Online payments: Wompi (card, PSE, Nequi) over total payments.",
        ),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[
            Table("methods", tr("t_methods", lang), method_columns, rows, totals_row),
            Table(
                "daily",
                tr("t_payments_daily", lang),
                daily_columns,
                daily_rows,
                {
                    "date": None,
                    "count": totals["count"],
                    "total": totals["total"],
                    "refunds": totals["refunds"],
                    "net": totals["net"],
                },
            ),
        ],
        notes=notes,
    )


# --- cash shifts --------------------------------------------------------------------------------------------


def build_cash_shifts(p) -> ReportResult:
    lang = p.lang
    shifts = list(
        annotate_shift_cash(
            CashShift.objects.filter(property=p.prop)
            .annotate(opened_day=local_date("opened_at", p.prop))
            .filter(opened_day__gte=p.start, opened_day__lte=p.end)
        )
        .select_related("user")
        .order_by("-opened_at")
    )
    rows = []
    for shift in shifts:
        live_expected = shift.opening_float + shift.cash_in - shift.cash_out
        rows.append(
            {
                "opened_at": shift.opened_at,
                "closed_at": shift.closed_at,
                "user": shift.user.full_name or shift.user.email,
                "status": "closed" if shift.closed_at else "open",
                "opening_float": shift.opening_float,
                "cash_in": shift.cash_in,
                "cash_out": shift.cash_out,
                "expected_cash": shift.expected_cash if shift.expected_cash is not None else live_expected,
                "counted_cash": shift.counted_cash,
                "difference": shift.difference,
            }
        )
    closed = [row for row in rows if row["status"] == "closed"]
    differences = [row["difference"] for row in closed if row["difference"]]
    columns = [
        Column("opened_at", tr("opened_at", lang), DATETIME),
        Column("closed_at", tr("closed_at", lang), DATETIME),
        Column("user", tr("user", lang), TEXT),
        Column("status", tr("status", lang), CODE, labels=enum_labels(SHIFT_STATUSES, lang)),
        Column("opening_float", tr("opening_float", lang), MONEY),
        Column("cash_in", tr("cash_in", lang), MONEY),
        Column("cash_out", tr("cash_out", lang), MONEY),
        Column("expected_cash", tr("expected_cash", lang), MONEY),
        Column("counted_cash", tr("counted_cash", lang), MONEY),
        Column("difference", tr("difference", lang), MONEY),
    ]
    totals_row = {
        "opened_at": None,
        "user": tr("total_row", lang),
        "cash_in": sum((row["cash_in"] for row in rows), ZERO),
        "cash_out": sum((row["cash_out"] for row in rows), ZERO),
        "difference": sum((row["difference"] or ZERO for row in closed), ZERO),
    }
    summary = [
        Kpi("shifts", tr("shifts", lang), NUMBER, len(rows), intent="neutral"),
        Kpi("open", tr("open_shifts", lang), NUMBER, len(rows) - len(closed), intent="neutral"),
        Kpi("cash_in", tr("cash_in", lang), MONEY, totals_row["cash_in"], intent="neutral"),
        Kpi(
            "difference",
            L(lang, "Diferencia acumulada", "Total difference"),
            MONEY,
            totals_row["difference"],
            intent="neutral",
        ),
        Kpi("with_difference", tr("differences", lang), NUMBER, len(differences), intent="lower-is-better"),
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Turnos abiertos en el rango (fecha de apertura en la zona horaria del hotel). Esperado = fondo "
            "inicial "
            "+ efectivo recibido − efectivo devuelto; diferencia = contado − esperado (se guarda al cerrar). "
            "En un "
            "turno abierto el esperado es el del momento.",
            "Shifts opened in the range (opening date in the hotel's time zone). Expected = opening float + "
            "cash "
            "received − cash refunded; difference = counted − expected (stored at closing). For an open "
            "shift the "
            "expected cash is the current one.",
        ),
    )
    return ReportResult(
        summary=summary,
        tables=[Table("shifts", tr("t_shifts", lang), columns, rows, totals_row)],
        notes=notes,
    )


# --- taxes --------------------------------------------------------------------------------------------------

TAXED = Q(tax__isnull=False) & ~Q(tax_amount=0)
EXEMPT = Q(tax__isnull=False, tax_amount=0)
UNTAXED = Q(tax__isnull=True) & ~Q(kind=Charge.Kind.TAX)


def _charges(prop, start, end):
    return Charge.objects.filter(
        folio__property=prop, voided_at__isnull=True, business_date__gte=start, business_date__lte=end
    )


def _tax_totals(prop, start, end) -> dict:
    agg = _charges(prop, start, end).aggregate(
        taxable=Sum("amount", filter=TAXED),
        tax_total=Sum("tax_amount"),
        manual_tax=Sum("amount", filter=Q(kind=Charge.Kind.TAX)),
        exempt=Sum("amount", filter=EXEMPT),
        exempt_count=Count("id", filter=EXEMPT),
        untaxed=Sum("amount", filter=UNTAXED),
    )
    return {
        "taxable": agg["taxable"] or ZERO,
        "tax": (agg["tax_total"] or ZERO) + (agg["manual_tax"] or ZERO),
        "exempt": agg["exempt"] or ZERO,
        "exempt_count": agg["exempt_count"] or 0,
        "untaxed": agg["untaxed"] or ZERO,
    }


def build_taxes(p) -> ReportResult:
    lang = p.lang
    rows = []
    for row in (
        _charges(p.prop, p.start, p.end)
        .filter(tax__isnull=False)
        .order_by()
        .values("tax_id", "tax__code", "tax__name", "tax__rate", "tax__applies_to")
        .annotate(
            taxable=Sum("amount", filter=TAXED),
            tax_total=Sum("tax_amount"),
            exempt=Sum("amount", filter=EXEMPT),
            count=Count("id"),
            exempt_count=Count("id", filter=EXEMPT),
        )
        .order_by("tax__code")
    ):
        rows.append(
            {
                "tax": f"{row['tax__name']} ({row['tax__code']})",
                "rate": row["tax__rate"],
                "taxable": row["taxable"] or ZERO,
                "tax_amount": row["tax_total"] or ZERO,
                "exempt": row["exempt"] or ZERO,
                "untaxed": ZERO,
                "charges": row["count"],
                "exempt_charges": row["exempt_count"],
            }
        )
    totals = _tax_totals(p.prop, p.start, p.end)
    manual = (
        _charges(p.prop, p.start, p.end)
        .filter(kind=Charge.Kind.TAX)
        .aggregate(total=Sum("amount"), count=Count("id"))
    )
    if manual["count"]:
        rows.append(
            {
                "tax": L(lang, "Impuestos cargados manualmente", "Manually posted taxes"),
                "rate": None,
                "taxable": ZERO,
                "tax_amount": manual["total"] or ZERO,
                "exempt": ZERO,
                "untaxed": ZERO,
                "charges": manual["count"],
                "exempt_charges": 0,
            }
        )
    untaxed_count = _charges(p.prop, p.start, p.end).filter(UNTAXED).count()
    if untaxed_count:
        rows.append(
            {
                "tax": tr("no_tax", lang),
                "rate": None,
                "taxable": ZERO,
                "tax_amount": ZERO,
                "exempt": ZERO,
                "untaxed": totals["untaxed"],
                "charges": untaxed_count,
                "exempt_charges": 0,
            }
        )
    columns = [
        Column("tax", tr("tax", lang), TEXT),
        Column("rate", tr("rate", lang), PERCENT),
        Column("taxable", tr("taxable_base", lang), MONEY),
        Column("tax_amount", tr("tax_amount", lang), MONEY),
        Column("exempt", tr("exempt_base", lang), MONEY),
        Column("untaxed", tr("untaxed_base", lang), MONEY),
        Column("charges", tr("charges", lang), NUMBER),
        Column("exempt_charges", tr("exempt_charges", lang), NUMBER),
    ]
    totals_row = {
        "tax": tr("total_row", lang),
        "rate": None,
        "taxable": totals["taxable"],
        "tax_amount": totals["tax"],
        "exempt": totals["exempt"],
        "untaxed": totals["untaxed"],
        "charges": sum(row["charges"] for row in rows),
        "exempt_charges": totals["exempt_count"],
    }
    daily: dict = {}
    for row in (
        _charges(p.prop, p.start, p.end)
        .order_by()
        .values("business_date")
        .annotate(
            taxable=Sum("amount", filter=TAXED),
            tax_total=Sum("tax_amount"),
            manual_tax=Sum("amount", filter=Q(kind=Charge.Kind.TAX)),
            exempt=Sum("amount", filter=EXEMPT),
            untaxed=Sum("amount", filter=UNTAXED),
        )
    ):
        daily[row["business_date"]] = row
    daily_rows, chart_rows = [], []
    for day in all_days(p):
        row = daily.get(day, {})
        values = {
            "date": day,
            "taxable": row.get("taxable") or ZERO,
            "tax_amount": (row.get("tax_total") or ZERO) + (row.get("manual_tax") or ZERO),
            "exempt": row.get("exempt") or ZERO,
            "untaxed": row.get("untaxed") or ZERO,
        }
        daily_rows.append(values)
        chart_rows.append({"date": day, "taxable": values["taxable"], "exempt": values["exempt"]})
    daily_columns = [
        Column("date", tr("date", lang), DATE),
        Column("taxable", tr("taxable_base", lang), MONEY),
        Column("tax_amount", tr("tax_amount", lang), MONEY),
        Column("exempt", tr("exempt_base", lang), MONEY),
        Column("untaxed", tr("untaxed_base", lang), MONEY),
    ]
    previous = _tax_totals(p.prop, p.compare_start, p.compare_end) if p.compared else None

    def prev(key):
        return previous[key] if previous else None

    summary = [
        Kpi("taxable", tr("taxable_base", lang), MONEY, totals["taxable"], prev("taxable"), "neutral"),
        Kpi("tax", L(lang, "IVA generado", "VAT charged"), MONEY, totals["tax"], prev("tax"), "neutral"),
        Kpi("exempt", tr("exempt_base", lang), MONEY, totals["exempt"], prev("exempt"), "neutral"),
        Kpi("untaxed", tr("untaxed_base", lang), MONEY, totals["untaxed"], prev("untaxed"), "neutral"),
        Kpi(
            "exempt_count",
            tr("exempt_charges", lang),
            NUMBER,
            totals["exempt_count"],
            prev("exempt_count"),
            "neutral",
        ),
    ]
    charts = [
        Chart(
            key="bases",
            title=tr("c_taxes", lang),
            type="stacked_column",
            x="date",
            x_type="date",
            value_type=MONEY,
            series=[
                Series("taxable", tr("taxable_base", lang), "stack"),
                Series("exempt", tr("exempt_base", lang), "stack"),
            ],
            data=chart_rows,
            marker=today_marker(p),
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Cargos publicados y no anulados por fecha de negocio. Base gravada: neto de los cargos con "
            "impuesto "
            "cobrado. Base exenta: neto de los cargos con impuesto que quedó en cero por la exención de IVA "
            "a "
            "extranjeros no residentes (ET art. 481 lit. d). No gravado: cargos sin impuesto (p. ej. "
            "penalidades).",
            "Posted, non-voided charges by business date. Taxable base: net of the charges with tax charged. "
            "Exempt "
            "base: net of the charges whose tax was zero because of the VAT exemption for foreign "
            "non-residents (ET "
            "art. 481 lit. d). Not taxed: charges without tax (e.g. penalties).",
        ),
        L(
            lang,
            "El IVA de cada cargo se redondea al peso por cargo, igual que en el folio y la factura.",
            "Each charge's VAT is rounded to the peso per charge, like in the folio and the invoice.",
        ),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[
            Table("taxes", tr("t_taxes", lang), columns, rows, totals_row),
            Table(
                "daily",
                tr("t_taxes_daily", lang),
                daily_columns,
                daily_rows,
                {
                    "date": None,
                    "taxable": totals["taxable"],
                    "tax_amount": totals["tax"],
                    "exempt": totals["exempt"],
                    "untaxed": totals["untaxed"],
                },
            ),
        ],
        notes=notes,
    )


# --- receivables --------------------------------------------------------------------------------------------

SEGMENT_OF_STATUS = {
    "checked_out": "departed",
    "checked_in": "in_house",
    "confirmed": "upcoming",
    "cancelled": "penalties",
    "no_show": "penalties",
}
SEGMENT_ORDER = ["departed", "in_house", "penalties", "upcoming"]


def _paid_annotation():
    zero = Value(ZERO, output_field=MONEY_FIELD)
    payments = (
        Payment.objects.filter(folio__reservation=OuterRef("pk"), status=Payment.Status.APPROVED)
        .order_by()
        .values("folio__reservation")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    refunds = (
        Refund.objects.filter(payment__folio__reservation=OuterRef("pk"), status=Refund.Status.APPROVED)
        .order_by()
        .values("payment__folio__reservation")
        .annotate(total=Sum("amount"))
        .values("total")
    )
    return Coalesce(Subquery(payments, output_field=MONEY_FIELD), zero) - Coalesce(
        Subquery(refunds, output_field=MONEY_FIELD), zero
    )


def build_receivables(p) -> ReportResult:
    lang = p.lang
    today = p.business_date
    reservations = list(
        with_balance(Reservation.objects.filter(property=p.prop, status__in=list(SEGMENT_OF_STATUS)))
        .filter(balance__gt=0)
        .annotate(paid=_paid_annotation())
        .select_related("booker")
    )
    rows = []
    by_segment: dict = defaultdict(lambda: {"count": 0, "balance": ZERO})
    aging: dict = defaultdict(lambda: {"count": 0, "balance": ZERO})
    for reservation in reservations:
        segment = SEGMENT_OF_STATUS[reservation.status]
        days_since = (today - reservation.checkout_date).days if segment == "departed" else None
        rows.append(
            {
                "segment": segment,
                "code": reservation.code,
                "reservation_id": str(reservation.pk),
                "guest": guest_name(reservation.booker),
                "status": reservation.status,
                "checkin": reservation.checkin_date,
                "checkout": reservation.checkout_date,
                "total": reservation.balance + reservation.paid,
                "paid": reservation.paid,
                "balance": reservation.balance,
                "days_since_checkout": days_since,
            }
        )
        by_segment[segment]["count"] += 1
        by_segment[segment]["balance"] += reservation.balance
        if days_since is not None:
            for key, low, high, _labels in AGING_BUCKETS:
                if days_since >= low and (high is None or days_since <= high):
                    aging[key]["count"] += 1
                    aging[key]["balance"] += reservation.balance
                    break
    rows.sort(
        key=lambda row: (
            SEGMENT_ORDER.index(row["segment"]),
            -(row["days_since_checkout"] or 0),
            row["checkin"],
            row["code"],
        )
    )
    total_balance = sum((row["balance"] for row in rows), ZERO)
    columns = [
        Column("segment", tr("segment", lang), CODE, labels=enum_labels(RECEIVABLE_SEGMENTS, lang)),
        Column("code", tr("code", lang), TEXT, link="reservation"),
        Column("guest", tr("guest", lang), TEXT),
        Column(
            "status",
            tr("status", lang),
            STATUS,
            status_kind="reservation",
            labels=enum_labels(RESERVATION_STATUSES, lang),
        ),
        Column("checkin", tr("checkin", lang), DATE),
        Column("checkout", tr("checkout", lang), DATE),
        Column("total", tr("total", lang), MONEY),
        Column("paid", tr("paid", lang), MONEY),
        Column("balance", tr("balance", lang), MONEY),
        Column("days_since_checkout", tr("days_since_checkout", lang), NUMBER),
    ]
    totals_row = {
        "segment": None,
        "code": tr("total_row", lang),
        "total": sum((row["total"] for row in rows), ZERO),
        "paid": sum((row["paid"] for row in rows), ZERO),
        "balance": total_balance,
    }
    segment_rows = [
        {
            "segment": segment,
            "count": by_segment[segment]["count"],
            "balance": by_segment[segment]["balance"],
            "share": pct(by_segment[segment]["balance"], total_balance),
        }
        for segment in SEGMENT_ORDER
    ]
    segment_columns = [
        Column("segment", tr("segment", lang), CODE, labels=enum_labels(RECEIVABLE_SEGMENTS, lang)),
        Column("count", tr("reservations", lang), NUMBER),
        Column("balance", tr("balance", lang), MONEY),
        Column("share", tr("share", lang), PERCENT),
    ]
    aging_rows = [
        {
            "bucket": pick(labels, lang),
            "bucket_key": key,
            "count": aging[key]["count"],
            "balance": aging[key]["balance"],
        }
        for key, _low, _high, labels in AGING_BUCKETS
    ]
    aging_columns = [
        Column("bucket", tr("days_since_checkout", lang), TEXT),
        Column("count", tr("reservations", lang), NUMBER),
        Column("balance", tr("balance", lang), MONEY),
    ]
    summary = [
        Kpi("total", tr("receivable_total", lang), MONEY, total_balance, intent="lower-is-better"),
        Kpi(
            "departed",
            tr("receivable_departed", lang),
            MONEY,
            by_segment["departed"]["balance"],
            intent="lower-is-better",
        ),
        Kpi(
            "in_house",
            tr("receivable_in_house", lang),
            MONEY,
            by_segment["in_house"]["balance"],
            intent="neutral",
        ),
        Kpi(
            "penalties",
            tr("receivable_penalties", lang),
            MONEY,
            by_segment["penalties"]["balance"],
            intent="lower-is-better",
        ),
        Kpi(
            "upcoming",
            tr("receivable_upcoming", lang),
            MONEY,
            by_segment["upcoming"]["balance"],
            intent="neutral",
        ),
    ]
    charts = [
        Chart(
            key="segments",
            title=tr("c_receivables", lang),
            type="hbar",
            x="label",
            x_type="text",
            value_type=MONEY,
            series=[Series("balance", tr("balance", lang))],
            data=[
                {
                    "segment": row["segment"],
                    "label": enum_label(RECEIVABLE_SEGMENTS, row["segment"], lang),
                    "balance": row["balance"],
                }
                for row in segment_rows
            ],
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Reservas con saldo pendiente hoy: estadías facturables (incluye las noches aún no publicadas) + "
            "cargos "
            "no de alojamiento − pagos aprobados + reembolsos aprobados. Las tentativas no aparecen (son "
            "retenciones "
            "esperando pago).",
            "Bookings with an outstanding balance today: billable stays (including nights not posted yet) + "
            "non-room "
            "charges − approved payments + approved refunds. Tentative holds are left out (they wait for "
            "payment).",
        ),
        L(
            lang,
            "Salidas con saldo: huéspedes que ya se fueron y deben (cuentas por cobrar). Llegadas futuras: "
            "saldo que "
            "se cobra antes o durante la estadía.",
            "Departed with balance: guests who left and still owe (accounts receivable). Upcoming arrivals: "
            "balance "
            "collected before or during the stay.",
        ),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[
            Table("receivables", tr("t_receivables", lang), columns, rows, totals_row),
            Table("segments", tr("t_receivables_segments", lang), segment_columns, segment_rows),
            Table("aging", tr("t_receivables_aging", lang), aging_columns, aging_rows),
        ],
        notes=notes,
    )
