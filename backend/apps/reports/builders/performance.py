"""Performance reports (permission ``reports.performance``): performance, revenue by segment, pickup,
forecast, cancellations, booking window and guests by nationality."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median

from django.db.models import Sum

from apps.bookings.models import Reservation, Stay
from apps.core.dates import daterange
from apps.finance.models import Charge
from apps.inventory.models import RoomType
from apps.rates.models import RatePlan
from apps.reports import engine
from apps.reports.builders.common import (
    L,
    all_days,
    base_notes,
    day_text,
    guest_name,
    i18n_name,
    period_column,
    period_table_title,
    prev_label,
    prev_title,
    today_marker,
)
from apps.reports.engine import (
    DAY,
    SOLD_STATUSES,
    available_by_day,
    bucket_days,
    channel_of,
    daily_figures,
    local_date,
    nightly_net,
    pct,
    per_unit,
    revenue_by_kind,
    segment_figures,
    totals_of,
)
from apps.reports.labels import (
    CHANNELS,
    LEAD_BUCKETS,
    LOS_BUCKETS,
    SOURCES,
    country_label,
    enum_label,
    enum_labels,
    pick,
    tr,
)
from apps.reports.output import (
    CODE,
    COUNTRY,
    DATE,
    MONEY,
    NUMBER,
    PERCENT,
    TEXT,
    Chart,
    Column,
    Kpi,
    ReportResult,
    Series,
    Table,
)

ZERO = Decimal("0")
ONE = Decimal("0.1")

# --- definitions shown to the user --------------------------------------------------------------------------


def _definitions(lang: str) -> list[str]:
    return [
        L(
            lang,
            "Noches vendidas: estadías confirmadas, en casa o finalizadas que cubren la noche (llegada ≤ "
            "noche < "
            "salida: el día de salida no cuenta). Tentativas, canceladas y no-show no cuentan. En "
            "dormitorios cada "
            "cama es una unidad.",
            "Room nights sold: confirmed, in-house or checked-out stays covering the night (arrival ≤ night "
            "< "
            "departure: the departure day never counts). Tentative, cancelled and no-show stays do not "
            "count. In "
            "dorms every bed is one unit.",
        ),
        L(
            lang,
            "Noches disponibles: unidades activas del inventario menos las bloqueadas (fuera de servicio, "
            "mantenimiento, uso del propietario).",
            "Available room nights: active inventory units minus blocked units (out of order, maintenance, "
            "owner "
            "use).",
        ),
        L(
            lang,
            "Ocupación = vendidas ÷ disponibles. ADR = ingresos de alojamiento ÷ noches vendidas. RevPAR = "
            "ingresos de alojamiento ÷ noches disponibles. Los totales son cocientes de las sumas.",
            "Occupancy = sold ÷ available. ADR = room revenue ÷ room nights sold. RevPAR = room revenue ÷ "
            "available "
            "room nights. Totals are ratios of the sums.",
        ),
        L(
            lang,
            "Ingresos de alojamiento: neto (sin impuestos) de los cargos de noche publicados y no anulados "
            "con esa "
            "fecha de negocio. Desde la fecha de negocio actual en adelante es un pronóstico: la tarifa neta "
            "de las "
            "estadías vendidas (on the books).",
            "Room revenue: net (taxes excluded) of the posted, non-voided room charges of that business "
            "date. From "
            "the current business date on it is a forecast: the net rate of the stays on the books.",
        ),
    ]


def _forecast_note(p) -> str | None:
    if p.end < p.business_date:
        return None
    return L(
        p.lang,
        f"Desde el {day_text(max(p.start, p.business_date), 'es')} las cifras son previstas (reservas on the "
        "books); las noches anteriores son reales.",
        f"From {day_text(max(p.start, p.business_date), 'en')} figures are forecast (bookings on the books); "
        "earlier nights are actual.",
    )


def _row_kind(figures) -> str:
    if figures.forecast_days == 0:
        return "actual"
    return "forecast" if figures.forecast_days == figures.days else "mixed"


# --- performance --------------------------------------------------------------------------------------------


def build_performance(p) -> ReportResult:
    lang, currency = p.lang, p.currency
    days = daily_figures(p.prop, p.start, p.end)
    totals = totals_of(days)
    other = engine.RevenueByKind()
    for figures in revenue_by_kind(p.prop, p.start, p.end).values():
        other.add(figures)
    buckets = bucket_days(days, p.group_by)

    prev_totals = prev_other = None
    prev_buckets: list = []
    if p.compared:
        prev_days = daily_figures(p.prop, p.compare_start, p.compare_end)
        prev_totals = totals_of(prev_days)
        prev_other = engine.RevenueByKind()
        for figures in revenue_by_kind(p.prop, p.compare_start, p.compare_end).values():
            prev_other.add(figures)
        prev_buckets = bucket_days(prev_days, p.group_by)

    def prev(attr):
        return None if prev_totals is None else attr(prev_totals)

    summary = [
        Kpi("occupancy", tr("occupancy", lang), PERCENT, totals.occupancy(), prev(lambda t: t.occupancy())),
        Kpi("adr", tr("adr", lang), MONEY, totals.adr(currency), prev(lambda t: t.adr(currency))),
        Kpi("revpar", tr("revpar", lang), MONEY, totals.revpar(currency), prev(lambda t: t.revpar(currency))),
        Kpi(
            "room_revenue",
            tr("room_revenue", lang),
            MONEY,
            totals.room_revenue,
            prev(lambda t: t.room_revenue),
        ),
        Kpi("sold", tr("sold", lang), NUMBER, totals.sold, prev(lambda t: t.sold)),
        Kpi(
            "other_revenue",
            tr("other_revenue", lang),
            MONEY,
            other.extras + other.other,
            None if prev_other is None else prev_other.extras + prev_other.other,
        ),
    ]

    columns = [
        period_column(p),
        Column("available", tr("available", lang), NUMBER),
        Column("sold", tr("sold", lang), NUMBER),
        Column("occupancy", tr("occupancy", lang), PERCENT),
        Column("adr", tr("adr", lang), MONEY),
        Column("revpar", tr("revpar", lang), MONEY),
        Column("room_revenue", tr("room_revenue", lang), MONEY),
        Column(
            "kind",
            L(lang, "Tipo", "Type"),
            CODE,
            labels={
                "actual": tr("actual", lang),
                "forecast": tr("forecast", lang),
                "mixed": L(lang, "Real y previsto", "Actual and forecast"),
            },
        ),
    ]
    if p.compared:
        columns += [
            Column("occupancy_prev", f"{tr('occupancy', lang)} · {prev_label(p)}", PERCENT),
            Column("adr_prev", f"{tr('adr', lang)} · {prev_label(p)}", MONEY),
            Column("revpar_prev", f"{tr('revpar', lang)} · {prev_label(p)}", MONEY),
            Column("room_revenue_prev", f"{tr('room_revenue_short', lang)} · {prev_label(p)}", MONEY),
        ]
    rows, chart_rows = [], []
    for index, figures in enumerate(buckets):
        row = {
            "date": figures.date,
            "available": figures.available,
            "sold": figures.sold,
            "occupancy": figures.occupancy(),
            "adr": figures.adr(currency),
            "revpar": figures.revpar(currency),
            "room_revenue": figures.room_revenue,
            "kind": _row_kind(figures),
        }
        point = {
            "date": figures.date,
            "occupancy": figures.occupancy(),
            "adr": figures.adr(currency),
            "revpar": figures.revpar(currency),
            "room_revenue": figures.room_revenue,
            "forecast": figures.is_forecast,
        }
        if p.compared:
            before = prev_buckets[index] if index < len(prev_buckets) else None
            values = {
                "occupancy_prev": before.occupancy() if before else None,
                "adr_prev": before.adr(currency) if before else None,
                "revpar_prev": before.revpar(currency) if before else None,
                "room_revenue_prev": before.room_revenue if before else None,
            }
            row.update(values)
            point.update(values)
            point["date_prev"] = before.date if before else None
        rows.append(row)
        chart_rows.append(point)

    totals_row = {
        "date": None,
        "available": totals.available,
        "sold": totals.sold,
        "occupancy": totals.occupancy(),
        "adr": totals.adr(currency),
        "revpar": totals.revpar(currency),
        "room_revenue": totals.room_revenue,
        "kind": None,
    }
    if p.compared:
        totals_row.update(
            {
                "occupancy_prev": prev_totals.occupancy(),
                "adr_prev": prev_totals.adr(currency),
                "revpar_prev": prev_totals.revpar(currency),
                "room_revenue_prev": prev_totals.room_revenue,
            }
        )

    forecast_from = next((f.date.isoformat() for f in buckets if f.is_forecast), None)
    line_type = "line" if (p.group_by or "day") == "day" else "column"

    def chart(key: str, title_key: str, value_type: str, kind: str) -> Chart:
        series = [Series(key, tr(key, lang))]
        if p.compared:
            series.append(Series(f"{key}_prev", prev_title(p), "compare"))
        return Chart(
            key=key,
            title=tr(title_key, lang),
            type=kind,
            x="date",
            x_type="month" if p.group_by == "month" else "date",
            value_type=value_type,
            series=series,
            data=chart_rows,
            marker=today_marker(p) if (p.group_by or "day") == "day" else None,
            forecast_from=forecast_from,
        )

    charts = [
        chart("occupancy", "c_occupancy", PERCENT, line_type),
        chart("adr", "c_adr", MONEY, line_type),
        chart("revpar", "c_revpar", MONEY, line_type),
        chart("room_revenue", "c_room_revenue", MONEY, "column"),
    ]
    notes = base_notes(p, _forecast_note(p), *_definitions(lang))
    notes.append(
        L(
            lang,
            "Otros ingresos: extras, penalidades de cancelación y no-show, cargos y ajustes publicados "
            "(neto).",
            "Other revenue: posted extras, cancellation and no-show penalties, fees and adjustments (net).",
        )
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[Table("periods", period_table_title(p), columns, rows, totals_row)],
        notes=notes,
    )


# --- revenue by segment -------------------------------------------------------------------------------------

SEGMENT_DIMENSIONS = ("source", "channel", "room_type", "rate_plan")


def _segment_label_resolver(p, dimension: str):
    lang = p.lang
    if dimension == "source":
        return lambda key: enum_label(SOURCES, key, lang)
    if dimension == "channel":
        return lambda key: enum_label(CHANNELS, key, lang)
    if dimension == "room_type":
        names = {
            rt.pk: f"{i18n_name(rt.name, lang) or rt.code}" for rt in RoomType.objects.filter(property=p.prop)
        }
        return lambda key: names.get(key, tr("none", lang)) if key else tr("none", lang)
    names = {
        plan.pk: i18n_name(plan.name, lang) or plan.code for plan in RatePlan.objects.filter(property=p.prop)
    }
    return lambda key: names.get(key, tr("none", lang)) if key else tr("none", lang)


def build_revenue_by_segment(p) -> ReportResult:
    lang, currency = p.lang, p.currency
    dimension = p.group_by or "source"
    key = lambda attrs: attrs[dimension]  # noqa: E731
    segments = segment_figures(p.prop, p.start, p.end, key)
    previous = segment_figures(p.prop, p.compare_start, p.compare_end, key) if p.compared else {}
    label_of = _segment_label_resolver(p, dimension)

    total_revenue = sum((s.revenue for s in segments.values()), ZERO)
    total_nights = sum(s.nights for s in segments.values())
    all_reservations = set().union(*(s.reservations for s in segments.values())) if segments else set()
    prev_revenue = sum((s.revenue for s in previous.values()), ZERO)
    prev_nights = sum(s.nights for s in previous.values())

    rows = []
    for segment_key, figures in sorted(
        segments.items(), key=lambda item: (-item[1].revenue, -item[1].nights)
    ):
        row = {
            "segment": label_of(segment_key),
            "segment_key": str(segment_key) if segment_key is not None else "",
            "reservations": len(figures.reservations),
            "nights": figures.nights,
            "nights_share": pct(figures.nights, total_nights),
            "revenue": figures.revenue,
            "revenue_share": pct(figures.revenue, total_revenue),
            "adr": per_unit(figures.revenue, figures.nights, currency),
        }
        if p.compared:
            before = previous.get(segment_key)
            row["revenue_prev"] = before.revenue if before else ZERO
            row["change_pct"] = (
                pct(figures.revenue - before.revenue, before.revenue) if before and before.revenue else None
            )
        rows.append(row)
    if p.compared:  # segments that only sold in the comparison period
        for segment_key, before in previous.items():
            if segment_key in segments:
                continue
            rows.append(
                {
                    "segment": label_of(segment_key),
                    "segment_key": str(segment_key) if segment_key is not None else "",
                    "reservations": 0,
                    "nights": 0,
                    "nights_share": pct(0, total_nights),
                    "revenue": ZERO,
                    "revenue_share": pct(0, total_revenue),
                    "adr": per_unit(0, 0, currency),
                    "revenue_prev": before.revenue,
                    "change_pct": pct(-before.revenue, before.revenue) if before.revenue else None,
                }
            )

    dimension_label = tr(dimension, lang)
    columns = [
        Column("segment", dimension_label, TEXT),
        Column("reservations", tr("reservations", lang), NUMBER),
        Column("nights", tr("sold", lang), NUMBER),
        Column("nights_share", L(lang, "% de noches", "% of nights"), PERCENT),
        Column("revenue", tr("room_revenue", lang), MONEY),
        Column("revenue_share", L(lang, "% de ingresos", "% of revenue"), PERCENT),
        Column("adr", tr("adr", lang), MONEY),
    ]
    if p.compared:
        columns += [
            Column("revenue_prev", f"{tr('room_revenue_short', lang)} · {prev_label(p)}", MONEY),
            Column("change_pct", L(lang, "Variación", "Change"), PERCENT),
        ]
    totals_row = {
        "segment": tr("total_row", lang),
        "reservations": len(all_reservations),
        "nights": total_nights,
        "nights_share": pct(total_nights, total_nights),
        "revenue": total_revenue,
        "revenue_share": pct(total_revenue, total_revenue),
        "adr": per_unit(total_revenue, total_nights, currency),
    }
    if p.compared:
        totals_row["revenue_prev"] = prev_revenue
        totals_row["change_pct"] = pct(total_revenue - prev_revenue, prev_revenue) if prev_revenue else None

    ota_revenue = _ota_revenue(p, p.start, p.end)
    summary = [
        Kpi(
            "room_revenue",
            tr("room_revenue", lang),
            MONEY,
            total_revenue,
            prev_revenue if p.compared else None,
        ),
        Kpi("sold", tr("sold", lang), NUMBER, total_nights, prev_nights if p.compared else None),
        Kpi(
            "adr",
            tr("adr", lang),
            MONEY,
            per_unit(total_revenue, total_nights, currency),
            per_unit(prev_revenue, prev_nights, currency) if p.compared else None,
        ),
        Kpi(
            "direct_share",
            L(lang, "Ingresos directos (sin OTA)", "Direct revenue (no OTA)"),
            PERCENT,
            pct(total_revenue - ota_revenue, total_revenue),
            pct(prev_revenue - _ota_revenue(p, p.compare_start, p.compare_end), prev_revenue)
            if p.compared
            else None,
        ),
    ]
    chart_rows = [
        {"segment": row["segment"], "revenue": row["revenue"]}
        for row in rows
        if row["revenue"] or row["nights"]
    ]
    charts = [
        Chart(
            key="segments",
            title=tr("c_segments", lang),
            type="hbar",
            x="segment",
            x_type="text",
            value_type=MONEY,
            series=[Series("revenue", tr("room_revenue", lang))],
            data=chart_rows,
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            f"Segmentado por {dimension_label.lower()}. Cada noche vendida y cada cargo de alojamiento "
            "cuenta en el "
            "segmento de su estadía, así la suma de los segmentos es exactamente el total del reporte de "
            "rendimiento.",
            f"Split by {dimension_label.lower()}. Every sold night and every room charge counts in the "
            "segment of its "
            "stay, so the segments add up exactly to the performance report.",
        ),
        L(
            lang,
            "Canal: el código de la OTA o del canal cuando existe; si no, Marketplace Housetel, Motor de "
            "reservas "
            "o Directo (recepción, teléfono, email, walk-in).",
            "Channel: the OTA/channel code when there is one; otherwise Housetel marketplace, Booking engine "
            "or "
            "Direct (front desk, phone, email, walk-in).",
        ),
        *_definitions(lang)[3:],
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[Table("segments", tr("t_segments", lang), columns, rows, totals_row)],
        notes=notes,
    )


def _ota_revenue(p, start, end) -> Decimal:
    """Room revenue of OTA reservations in ``[start, end]`` (for the direct share)."""
    if start is None:
        return ZERO
    figures = segment_figures(p.prop, start, end, lambda attrs: attrs["source"] == "ota")
    return figures.get(True).revenue if True in figures else ZERO


# --- pickup -------------------------------------------------------------------------------------------------


def build_pickup(p) -> ReportResult:
    lang = p.lang
    today = p.business_date
    window_start = today - timedelta(days=p.days - 1)
    days = all_days(p)
    available = available_by_day(p.prop, p.start, p.end)
    otb, new, lost = Counter(), Counter(), Counter()
    new_revenue, lost_revenue = defaultdict(Decimal), defaultdict(Decimal)
    new_reservations, lost_reservations = set(), set()
    stays = (
        Stay.objects.filter(
            reservation__property=p.prop,
            status__in=[*SOLD_STATUSES, "cancelled"],
            checkin_date__lte=p.end,
            checkout_date__gt=p.start,
        )
        .annotate(created_day=local_date("reservation__created_at", p.prop))
        .annotate(cancelled_day=local_date("reservation__cancelled_at", p.prop))
        .order_by()
        .values(
            "reservation_id",
            "status",
            "checkin_date",
            "checkout_date",
            "nightly_rates",
            "created_day",
            "cancelled_day",
        )  # fmt: skip
    )
    for stay in stays:
        created = stay["created_day"]
        # No upper bound: a booking made after midnight but before the night audit closes the business day
        # still belongs to the window (its calendar date is already "tomorrow" while the business date is
        # not).
        is_new = stay["status"] in SOLD_STATUSES and created is not None and created >= window_start
        is_lost = (
            stay["status"] == "cancelled"
            and stay["cancelled_day"] is not None
            and stay["cancelled_day"] >= window_start
            and (created is None or created < window_start)
        )
        rates = nightly_net(stay["nightly_rates"]) if (is_new or is_lost) else {}
        for night in daterange(max(stay["checkin_date"], p.start), min(stay["checkout_date"], p.end + DAY)):
            if stay["status"] in SOLD_STATUSES:
                otb[night] += 1
            if is_new:
                new[night] += 1
                new_revenue[night] += rates.get(night, ZERO)
            elif is_lost:
                lost[night] += 1
                lost_revenue[night] += rates.get(night, ZERO)
        if is_new:
            new_reservations.add(stay["reservation_id"])
        elif is_lost:
            lost_reservations.add(stay["reservation_id"])

    rows, chart_rows = [], []
    sum_avail = sum_otb = sum_before = 0
    sum_pickup_revenue = ZERO
    for day in days:
        pickup = new[day] - lost[day]
        before = otb[day] - pickup
        revenue = new_revenue[day] - lost_revenue[day]
        units = available.get(day, 0)
        sum_avail += units
        sum_otb += otb[day]
        sum_before += before
        sum_pickup_revenue += revenue
        rows.append(
            {
                "date": day,
                "available": units,
                "otb": otb[day],
                "otb_before": before,
                "new_nights": new[day],
                "lost_nights": lost[day],
                "pickup": pickup,
                "pickup_revenue": revenue,
                "occupancy": pct(otb[day], units),
                "occupancy_before": pct(before, units),
            }
        )
        chart_rows.append({"date": day, "pickup": pickup})
    columns = [
        Column("date", tr("date", lang), DATE),
        Column("available", tr("available", lang), NUMBER),
        Column("otb_before", tr("otb_before", lang), NUMBER),
        Column("new_nights", tr("new_nights", lang), NUMBER),
        Column("lost_nights", tr("lost_nights", lang), NUMBER),
        Column("pickup", tr("pickup_nights", lang), NUMBER),
        Column("otb", tr("otb", lang), NUMBER),
        Column("occupancy_before", f"{tr('occupancy', lang)} · {L(lang, 'antes', 'before')}", PERCENT),
        Column("occupancy", tr("occupancy", lang), PERCENT),
        Column("pickup_revenue", tr("pickup_revenue", lang), MONEY),
    ]
    totals_row = {
        "date": None,
        "available": sum_avail,
        "otb": sum_otb,
        "otb_before": sum_before,
        "new_nights": sum(new.values()),
        "lost_nights": sum(lost.values()),
        "pickup": sum_otb - sum_before,
        "pickup_revenue": sum_pickup_revenue,
        "occupancy": pct(sum_otb, sum_avail),
        "occupancy_before": pct(sum_before, sum_avail),
    }
    summary = [
        Kpi("pickup", tr("pickup_nights", lang), NUMBER, sum_otb - sum_before),
        Kpi("pickup_revenue", tr("pickup_revenue", lang), MONEY, sum_pickup_revenue),
        Kpi("new_reservations", tr("new_reservations", lang), NUMBER, len(new_reservations)),
        Kpi(
            "cancelled",
            tr("cancelled_reservations", lang),
            NUMBER,
            len(lost_reservations),
            intent="lower-is-better",
        ),
        Kpi(
            "occupancy",
            L(lang, "Ocupación on the books", "Occupancy on the books"),
            PERCENT,
            pct(sum_otb, sum_avail),
        ),
        Kpi(
            "occupancy_before",
            L(
                lang,
                f"Ocupación hace {p.days} {'día' if p.days == 1 else 'días'}",
                f"Occupancy {p.days} {'day' if p.days == 1 else 'days'} ago",
            ),
            PERCENT,
            pct(sum_before, sum_avail),
            intent="neutral",
        ),
    ]
    charts = [
        Chart(
            key="pickup",
            title=tr("c_pickup", lang),
            type="column",
            x="date",
            x_type="date",
            value_type=NUMBER,
            series=[Series("pickup", tr("pickup_nights", lang))],
            data=chart_rows,
            marker=today_marker(p),
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            f"Ventana de pickup: reservas creadas desde el {day_text(window_start, 'es')} hasta la fecha de "
            "negocio "
            f"{day_text(today, 'es')} ({p.days} {'día' if p.days == 1 else 'días'}; fecha de creación en la "
            "zona "
            "horaria del hotel, e incluye lo reservado antes de que la auditoría nocturna cierre el día).",
            f"Pickup window: bookings made from {day_text(window_start, 'en')} through business date "
            f"{day_text(today, 'en')} ({p.days} {'day' if p.days == 1 else 'days'}; booking date in the "
            "hotel's time "
            "zone, including what was booked before the night audit closed the day).",
        ),
        L(
            lang,
            "Pickup de cada noche = noches nuevas (reservas creadas en la ventana que siguen vendidas) − "
            "noches "
            "canceladas en la ventana de reservas que ya existían. On the books antes = on the books hoy − "
            "pickup.",
            "Pickup per night = new room nights (bookings made in the window that are still sold) − room "
            "nights "
            "cancelled in the window from bookings that already existed. On the books before = on the books "
            "now − "
            "pickup.",
        ),
        L(
            lang,
            "Ingresos del pickup: tarifa neta de esas noches (sin impuestos).",
            "Pickup revenue: net rate of those nights (taxes excluded).",
        ),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[Table("pickup", tr("t_pickup", lang), columns, rows, totals_row)],
        notes=notes,
        meta={"window_start": window_start.isoformat(), "window_end": today.isoformat()},
    )


# --- forecast / occupancy outlook ---------------------------------------------------------------------------


def _arrivals_departures(p) -> tuple[Counter, Counter, Counter]:
    """(tentative nights, arrivals, departures) per date of the range (stays, i.e. rooms or beds)."""
    tentative, arrivals, departures = Counter(), Counter(), Counter()
    for checkin, checkout, status in Stay.objects.filter(
        reservation__property=p.prop,
        status__in=[*SOLD_STATUSES, "tentative"],
        checkin_date__lte=p.end + DAY,
        checkout_date__gte=p.start,
    ).values_list("checkin_date", "checkout_date", "status"):
        if status == "tentative":
            for night in daterange(max(checkin, p.start), min(checkout, p.end + DAY)):
                tentative[night] += 1
        if p.start <= checkin <= p.end:
            arrivals[checkin] += 1
        if p.start <= checkout <= p.end and status != "tentative":
            departures[checkout] += 1
    return tentative, arrivals, departures


def build_forecast(p) -> ReportResult:
    lang, currency = p.lang, p.currency
    days = daily_figures(p.prop, p.start, p.end)
    totals = totals_of(days)
    tentative, arrivals, departures = _arrivals_departures(p)
    group = p.group_by or "day"
    buckets = bucket_days(days, group)
    extra = defaultdict(lambda: [0, 0, 0])
    for day in all_days(p):
        key = engine.bucket_start(day, group)
        extra[key][0] += tentative[day]
        extra[key][1] += arrivals[day]
        extra[key][2] += departures[day]
    rows, chart_rows = [], []
    for figures in buckets:
        tent, arr, dep = extra[figures.date]
        rows.append(
            {
                "date": figures.date,
                "available": figures.available,
                "sold": figures.sold,
                "occupancy": figures.occupancy(),
                "tentative": tent,
                "arrivals": arr,
                "departures": dep,
                "room_revenue": figures.room_revenue,
                "adr": figures.adr(currency),
                "revpar": figures.revpar(currency),
            }
        )
        chart_rows.append(
            {"date": figures.date, "occupancy": figures.occupancy(), "forecast": figures.is_forecast}
        )
    columns = [
        period_column(p),
        Column("available", tr("available", lang), NUMBER),
        Column("sold", tr("otb", lang), NUMBER),
        Column("occupancy", tr("occupancy", lang), PERCENT),
        Column("tentative", tr("tentative_nights", lang), NUMBER),
        Column("arrivals", tr("arrivals", lang), NUMBER),
        Column("departures", tr("departures", lang), NUMBER),
        Column("room_revenue", tr("room_revenue", lang), MONEY),
        Column("adr", tr("adr", lang), MONEY),
        Column("revpar", tr("revpar", lang), MONEY),
    ]
    totals_row = {
        "date": None,
        "available": totals.available,
        "sold": totals.sold,
        "occupancy": totals.occupancy(),
        "tentative": sum(tentative.values()),
        "arrivals": sum(arrivals.values()),
        "departures": sum(departures.values()),
        "room_revenue": totals.room_revenue,
        "adr": totals.adr(currency),
        "revpar": totals.revpar(currency),
    }
    summary = [
        Kpi("occupancy", tr("occupancy", lang), PERCENT, totals.occupancy()),
        Kpi("sold", tr("otb", lang), NUMBER, totals.sold),
        Kpi("room_revenue", tr("room_revenue", lang), MONEY, totals.room_revenue),
        Kpi("adr", tr("adr", lang), MONEY, totals.adr(currency)),
        Kpi("revpar", tr("revpar", lang), MONEY, totals.revpar(currency)),
        Kpi("tentative", tr("tentative_nights", lang), NUMBER, sum(tentative.values()), intent="neutral"),
    ]
    charts = [
        Chart(
            key="occupancy",
            title=tr("c_forecast", lang),
            type="column",
            x="date",
            x_type="month" if group == "month" else "date",
            value_type=PERCENT,
            series=[Series("occupancy", tr("occupancy", lang))],
            data=chart_rows,
            marker=today_marker(p) if group == "day" else None,
            forecast_from=next((f.date.isoformat() for f in buckets if f.is_forecast), None),
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "On the books: estadías vendidas (confirmadas y en casa) para cada noche futura. Las tentativas "
            "se "
            "muestran aparte y no suman a la ocupación.",
            "On the books: sold stays (confirmed and in house) for each future night. Tentative holds are "
            "shown "
            "apart and never add to occupancy.",
        ),
        L(
            lang,
            "Llegadas y salidas: estadías (habitaciones o camas) que llegan o salen ese día.",
            "Arrivals and departures: stays (rooms or beds) arriving or departing that day.",
        ),
        *_definitions(lang),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[Table("forecast", tr("t_forecast", lang), columns, rows, totals_row)],
        notes=notes,
    )


def build_occupancy_outlook(p) -> ReportResult:
    """Operational twin of the forecast (no money): occupancy, holds, arrivals and departures per night."""
    lang = p.lang
    days = daily_figures(p.prop, p.start, p.end)
    tentative, arrivals, departures = _arrivals_departures(p)
    rows, chart_rows = [], []
    for figures in days:
        day = figures.date
        rows.append(
            {
                "date": day,
                "available": figures.available,
                "sold": figures.sold,
                "free": max(figures.available - figures.sold, 0),
                "occupancy": figures.occupancy(),
                "tentative": tentative[day],
                "arrivals": arrivals[day],
                "departures": departures[day],
            }
        )
        chart_rows.append({"date": day, "occupancy": figures.occupancy()})
    totals = totals_of(days)
    peak = max(days, key=lambda f: (f.occupancy(), -f.date.toordinal()), default=None)
    columns = [
        Column("date", tr("date", lang), DATE),
        Column("available", tr("available", lang), NUMBER),
        Column("sold", tr("sold", lang), NUMBER),
        Column("free", L(lang, "Libres", "Free"), NUMBER),
        Column("occupancy", tr("occupancy", lang), PERCENT),
        Column("tentative", tr("tentative_nights", lang), NUMBER),
        Column("arrivals", tr("arrivals", lang), NUMBER),
        Column("departures", tr("departures", lang), NUMBER),
    ]
    totals_row = {
        "date": None,
        "available": totals.available,
        "sold": totals.sold,
        "free": max(totals.available - totals.sold, 0),
        "occupancy": totals.occupancy(),
        "tentative": sum(tentative.values()),
        "arrivals": sum(arrivals.values()),
        "departures": sum(departures.values()),
    }
    summary = [
        Kpi("occupancy", L(lang, "Ocupación media", "Average occupancy"), PERCENT, totals.occupancy()),
        Kpi("peak", L(lang, "Noche más llena", "Busiest night"), PERCENT, peak.occupancy() if peak else None),
        Kpi("sold", tr("sold", lang), NUMBER, totals.sold),
        Kpi("arrivals", tr("arrivals", lang), NUMBER, sum(arrivals.values()), intent="neutral"),
    ]
    charts = [
        Chart(
            key="occupancy",
            title=tr("c_outlook", lang),
            type="column",
            x="date",
            x_type="date",
            value_type=PERCENT,
            series=[Series("occupancy", tr("occupancy", lang))],
            data=chart_rows,
            marker=today_marker(p),
        )
    ]
    meta = {"peak_date": peak.date.isoformat() if peak else None}
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[Table("outlook", tr("t_outlook", lang), columns, rows, totals_row)],
        notes=base_notes(p, *_definitions(lang)[:3]),
        meta=meta,
    )


# --- cancellations ------------------------------------------------------------------------------------------


def _cancellation_rate(p, start: date, end: date) -> Decimal:
    created = (
        Reservation.objects.filter(property=p.prop)
        .annotate(day=local_date("created_at", p.prop))
        .filter(day__gte=start, day__lte=end)
    )
    total = created.count()
    return pct(created.filter(status="cancelled").count(), total)


def _cancelled_in(p, start: date, end: date):
    return (
        Reservation.objects.filter(property=p.prop, status="cancelled")
        .annotate(
            cancelled_day=local_date("cancelled_at", p.prop), created_day=local_date("created_at", p.prop)
        )
        .filter(cancelled_day__gte=start, cancelled_day__lte=end)
    )


def _lost(reservation_ids) -> dict:
    """``{reservation_id: (nights, net revenue)}`` of the (cancelled / no-show) stays of those
    reservations."""
    result: dict = defaultdict(lambda: [0, ZERO])
    for reservation_id, checkin, checkout, rates in Stay.objects.filter(
        reservation_id__in=list(reservation_ids)
    ).values_list("reservation_id", "checkin_date", "checkout_date", "nightly_rates"):
        nights = (checkout - checkin).days
        result[reservation_id][0] += nights
        result[reservation_id][1] += sum(nightly_net(rates).values(), ZERO)
    return result


def _fees_posted(reservation_ids) -> dict:
    return {
        reservation_id: total or ZERO
        for reservation_id, total in Charge.objects.filter(
            folio__reservation_id__in=list(reservation_ids),
            kind=Charge.Kind.CANCELLATION_FEE,
            voided_at__isnull=True,
        )
        .order_by()
        .values("folio__reservation_id")
        .annotate(total=Sum("amount"))
        .values_list("folio__reservation_id", "total")
    }


def _cancellation_totals(p, start, end) -> dict:
    reservations = list(_cancelled_in(p, start, end).values_list("id", flat=True))
    lost = _lost(reservations)
    fees = _fees_posted(reservations)
    return {
        "count": len(reservations),
        "nights": sum(v[0] for v in lost.values()),
        "revenue": sum((v[1] for v in lost.values()), ZERO),
        "fees": sum(fees.values(), ZERO),
        "rate": _cancellation_rate(p, start, end),
    }


def build_cancellations(p) -> ReportResult:
    lang = p.lang
    reservations = list(
        _cancelled_in(p, p.start, p.end).select_related("booker").order_by("cancelled_at", "code")
    )
    ids = [r.pk for r in reservations]
    lost = _lost(ids)
    fees = _fees_posted(ids)
    rows = []
    by_day = Counter()
    by_channel: dict = defaultdict(lambda: {"count": 0, "nights": 0, "revenue": ZERO, "fees": ZERO})
    for reservation in reservations:
        nights, revenue = lost[reservation.pk]
        fee = fees.get(reservation.pk, ZERO)
        channel = channel_of(reservation.source, reservation.channel_code)
        rows.append(
            {
                "cancelled_on": reservation.cancelled_day,
                "code": reservation.code,
                "reservation_id": str(reservation.pk),
                "guest": guest_name(reservation.booker),
                "source": reservation.source,
                "channel": channel,
                "created": reservation.created_day,
                "checkin": reservation.checkin_date,
                "nights": nights,
                "lead_days": (reservation.checkin_date - reservation.cancelled_day).days,
                "lost_revenue": revenue,
                "fee": fee,
                "reason": reservation.cancellation_reason,
            }
        )
        by_day[reservation.cancelled_day] += 1
        bucket = by_channel[channel]
        bucket["count"] += 1
        bucket["nights"] += nights
        bucket["revenue"] += revenue
        bucket["fees"] += fee
    totals = {
        "count": len(rows),
        "nights": sum(r["nights"] for r in rows),
        "revenue": sum((r["lost_revenue"] for r in rows), ZERO),
        "fees": sum((r["fee"] for r in rows), ZERO),
    }
    previous = _cancellation_totals(p, p.compare_start, p.compare_end) if p.compared else None
    rate = _cancellation_rate(p, p.start, p.end)
    summary = [
        Kpi(
            "cancellations",
            tr("cancellations", lang),
            NUMBER,
            totals["count"],
            previous and previous["count"],
            "lower-is-better",
        ),
        Kpi(
            "lost_nights",
            tr("lost_nights_total", lang),
            NUMBER,
            totals["nights"],
            previous and previous["nights"],
            "lower-is-better",
        ),
        Kpi(
            "lost_revenue",
            tr("lost_revenue", lang),
            MONEY,
            totals["revenue"],
            previous and previous["revenue"],
            "lower-is-better",
        ),
        Kpi("fees", tr("fees_charged", lang), MONEY, totals["fees"], previous and previous["fees"]),
        Kpi(
            "rate",
            tr("cancellation_rate", lang),
            PERCENT,
            rate,
            previous and previous["rate"],
            "lower-is-better",
        ),
    ]
    columns = [
        Column("cancelled_on", tr("cancelled_on", lang), DATE),
        Column("code", tr("code", lang), TEXT, link="reservation"),
        Column("guest", tr("guest", lang), TEXT),
        Column("channel", tr("channel", lang), CODE, labels=enum_labels(CHANNELS, lang)),
        Column("source", tr("source", lang), CODE, labels=enum_labels(SOURCES, lang)),
        Column("created", tr("created", lang), DATE),
        Column("checkin", tr("checkin", lang), DATE),
        Column("nights", tr("nights", lang), NUMBER),
        Column("lead_days", L(lang, "Días antes de la llegada", "Days before arrival"), NUMBER),
        Column("lost_revenue", tr("lost_revenue", lang), MONEY),
        Column("fee", tr("fee", lang), MONEY),
        Column("reason", tr("reason", lang), TEXT),
    ]
    totals_row = {
        "cancelled_on": None,
        "code": tr("total_row", lang),
        "nights": totals["nights"],
        "lost_revenue": totals["revenue"],
        "fee": totals["fees"],
    }
    channel_rows = [
        {
            "channel": channel,
            "count": data["count"],
            "nights": data["nights"],
            "lost_revenue": data["revenue"],
            "fee": data["fees"],
            "share": pct(data["count"], totals["count"]),
        }
        for channel, data in sorted(by_channel.items(), key=lambda item: -item[1]["count"])
    ]
    channel_columns = [
        Column("channel", tr("channel", lang), CODE, labels=enum_labels(CHANNELS, lang)),
        Column("count", tr("cancellations", lang), NUMBER),
        Column("share", tr("share", lang), PERCENT),
        Column("nights", tr("lost_nights_total", lang), NUMBER),
        Column("lost_revenue", tr("lost_revenue", lang), MONEY),
        Column("fee", tr("fees_charged", lang), MONEY),
    ]
    chart_rows = [{"date": day, "cancellations": by_day[day]} for day in all_days(p)]
    charts = [
        Chart(
            key="cancellations",
            title=tr("c_cancellations", lang),
            type="column",
            x="date",
            x_type="date",
            value_type=NUMBER,
            series=[Series("cancellations", tr("cancellations", lang))],
            data=chart_rows,
            marker=today_marker(p),
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Reservas canceladas cuya fecha de cancelación (zona horaria del hotel) cae en el rango. Incluye "
            "las "
            "retenciones tentativas que vencieron sin pago.",
            "Bookings whose cancellation date (hotel time zone) falls in the range. Includes tentative holds "
            "that "
            "expired unpaid.",
        ),
        L(
            lang,
            "Ingresos perdidos: tarifa neta de todas las noches canceladas. Penalidad: cargos de penalidad "
            "publicados y no anulados.",
            "Lost revenue: net rate of every cancelled night. Penalty: posted, non-voided penalty charges.",
        ),
        L(
            lang,
            "Tasa de cancelación: de las reservas creadas en el rango, el porcentaje que hoy está cancelado.",
            "Cancellation rate: of the bookings made in the range, the share that is cancelled today.",
        ),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[
            Table("cancellations", tr("t_cancellations", lang), columns, rows, totals_row),
            Table("by_channel", tr("t_cancellations_by_channel", lang), channel_columns, channel_rows),
        ],
        notes=notes,
    )


# --- booking window -----------------------------------------------------------------------------------------


def _window_rows(p, start: date, end: date) -> list[dict]:
    return list(
        Reservation.objects.filter(
            property=p.prop, status__in=SOLD_STATUSES, checkin_date__gte=start, checkin_date__lte=end
        )
        .annotate(created_day=local_date("created_at", p.prop))
        .order_by()
        .values("id", "checkin_date", "checkout_date", "source", "channel_code", "created_day")
    )


def _window_stats(rows: list[dict]) -> dict:
    leads = [max((r["checkin_date"] - (r["created_day"] or r["checkin_date"])).days, 0) for r in rows]
    stays = [(r["checkout_date"] - r["checkin_date"]).days for r in rows]
    count = len(rows)
    return {
        "count": count,
        "leads": leads,
        "stays": stays,
        "avg_lead": (Decimal(sum(leads)) / count).quantize(ONE) if count else None,
        "median_lead": Decimal(str(median(leads))).quantize(ONE) if count else None,
        "avg_los": (Decimal(sum(stays)) / count).quantize(ONE) if count else None,
        "same_day": pct(sum(1 for lead in leads if lead == 0), count),
    }


def _bucketize(values: list[int], buckets) -> list[tuple[str, tuple[str, str], int, int]]:
    """(key, labels, count, sum of values) per bucket."""
    result = []
    for key, low, high, labels in buckets:
        inside = [v for v in values if v >= low and (high is None or v <= high)]
        result.append((key, labels, len(inside), sum(inside)))
    return result


def build_booking_window(p) -> ReportResult:
    lang = p.lang
    rows = _window_rows(p, p.start, p.end)
    stats = _window_stats(rows)
    previous = _window_stats(_window_rows(p, p.compare_start, p.compare_end)) if p.compared else None

    def prev(key):
        return previous[key] if previous else None

    summary = [
        Kpi("reservations", tr("reservations", lang), NUMBER, stats["count"], prev("count")),
        Kpi(
            "avg_lead",
            tr("avg_lead", lang),
            NUMBER,
            stats["avg_lead"],
            prev("avg_lead"),
            "neutral",
            unit="days",
        ),
        Kpi(
            "median_lead",
            tr("median_lead", lang),
            NUMBER,
            stats["median_lead"],
            prev("median_lead"),
            "neutral",
            unit="days",
        ),
        Kpi("avg_los", tr("avg_los", lang), NUMBER, stats["avg_los"], prev("avg_los"), unit="nights"),
        Kpi("same_day", tr("same_day", lang), PERCENT, stats["same_day"], prev("same_day"), "neutral"),
    ]
    lead_rows, los_rows = [], []
    lead_buckets = _bucketize(stats["leads"], LEAD_BUCKETS)
    stays_by_lead = defaultdict(int)
    for lead, nights in zip(stats["leads"], stats["stays"], strict=True):
        for key, low, high, _labels in LEAD_BUCKETS:
            if lead >= low and (high is None or lead <= high):
                stays_by_lead[key] += nights
                break
    for key, labels, count, _total in lead_buckets:
        lead_rows.append(
            {
                "bucket": pick(labels, lang),
                "bucket_key": key,
                "reservations": count,
                "share": pct(count, stats["count"]),
                "nights": stays_by_lead[key],
            }
        )
    for key, labels, count, total in _bucketize(stats["stays"], LOS_BUCKETS):
        los_rows.append(
            {
                "bucket": pick(labels, lang),
                "bucket_key": key,
                "reservations": count,
                "share": pct(count, stats["count"]),
                "nights": total,
            }
        )
    by_channel: dict = defaultdict(list)
    for row, lead, nights in zip(rows, stats["leads"], stats["stays"], strict=True):
        by_channel[channel_of(row["source"], row["channel_code"])].append((lead, nights))
    channel_rows = [
        {
            "channel": channel,
            "reservations": len(values),
            "share": pct(len(values), stats["count"]),
            "avg_lead": (Decimal(sum(v[0] for v in values)) / len(values)).quantize(ONE),
            "avg_los": (Decimal(sum(v[1] for v in values)) / len(values)).quantize(ONE),
        }
        for channel, values in sorted(by_channel.items(), key=lambda item: -len(item[1]))
    ]
    bucket_columns = [
        Column("bucket", tr("bucket", lang), TEXT),
        Column("reservations", tr("reservations", lang), NUMBER),
        Column("share", tr("share", lang), PERCENT),
        Column("nights", tr("sold", lang), NUMBER),
    ]
    channel_columns = [
        Column("channel", tr("channel", lang), CODE, labels=enum_labels(CHANNELS, lang)),
        Column("reservations", tr("reservations", lang), NUMBER),
        Column("share", tr("share", lang), PERCENT),
        Column("avg_lead", L(lang, "Anticipación media (días)", "Average lead (days)"), NUMBER),
        Column("avg_los", L(lang, "Estadía media (noches)", "Average stay (nights)"), NUMBER),
    ]
    totals_lead = {
        "bucket": tr("total_row", lang),
        "reservations": stats["count"],
        "share": pct(stats["count"], stats["count"]),
        "nights": sum(stats["stays"]),
    }
    charts = [
        Chart(
            key="lead",
            title=tr("c_lead", lang),
            type="column",
            x="bucket",
            x_type="text",
            value_type=NUMBER,
            series=[Series("reservations", tr("reservations", lang))],
            data=[{"bucket": r["bucket"], "reservations": r["reservations"]} for r in lead_rows],
        ),
        Chart(
            key="los",
            title=tr("c_los", lang),
            type="column",
            x="bucket",
            x_type="text",
            value_type=NUMBER,
            series=[Series("reservations", tr("reservations", lang))],
            data=[{"bucket": r["bucket"], "reservations": r["reservations"]} for r in los_rows],
        ),
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Reservas vendidas (confirmadas, en casa o finalizadas) con llegada en el rango. Anticipación = "
            "días "
            "entre la fecha de creación (zona horaria del hotel) y la llegada. Duración = noches de la "
            "reserva.",
            "Sold bookings (confirmed, in house or checked out) arriving in the range. Lead time = days "
            "between the "
            "booking date (hotel time zone) and arrival. Length of stay = nights of the booking.",
        ),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[
            Table("lead", tr("t_lead", lang), bucket_columns, lead_rows, totals_lead),
            Table("los", tr("t_los", lang), bucket_columns, los_rows, {**totals_lead}),
            Table("by_channel", tr("t_by_source", lang), channel_columns, channel_rows),
        ],
        notes=notes,
    )


# --- guests by nationality ----------------------------------------------------------------------------------

TOP_COUNTRIES = 10


def build_guests_by_nationality(p) -> ReportResult:
    lang, currency = p.lang, p.currency
    countries = segment_figures(p.prop, p.start, p.end, lambda attrs: attrs["nationality"] or "")
    total_nights = sum(f.nights for f in countries.values())
    total_revenue = sum((f.revenue for f in countries.values()), ZERO)
    all_guests = set().union(*(f.guests for f in countries.values())) if countries else set()
    rows = []
    for code, figures in sorted(countries.items(), key=lambda item: (-item[1].nights, -item[1].revenue)):
        if not figures.nights and not figures.revenue:
            continue
        rows.append(
            {
                "country": code,
                "guests": len(figures.guests),
                "reservations": len(figures.reservations),
                "nights": figures.nights,
                "share": pct(figures.nights, total_nights),
                "revenue": figures.revenue,
                "adr": per_unit(figures.revenue, figures.nights, currency),
            }
        )
    foreign_nights = sum(f.nights for code, f in countries.items() if code and code != "CO")
    known = [row for row in rows if row["country"]]
    top = known[0]["country"] if known else ""
    columns = [
        Column("country", tr("country", lang), COUNTRY),
        Column("guests", tr("guests", lang), NUMBER),
        Column("reservations", tr("reservations", lang), NUMBER),
        Column("nights", tr("sold", lang), NUMBER),
        Column("share", L(lang, "% de noches", "% of nights"), PERCENT),
        Column("revenue", tr("room_revenue", lang), MONEY),
        Column("adr", tr("adr", lang), MONEY),
    ]
    totals_row = {
        "country": None,
        "guests": len(all_guests),
        "reservations": len(set().union(*(f.reservations for f in countries.values()))) if countries else 0,
        "nights": total_nights,
        "share": pct(total_nights, total_nights),
        "revenue": total_revenue,
        "adr": per_unit(total_revenue, total_nights, currency),
    }
    summary = [
        Kpi("guests", tr("guests", lang), NUMBER, len(all_guests)),
        Kpi("countries", tr("countries", lang), NUMBER, len(known)),
        Kpi(
            "international",
            tr("international_share", lang),
            PERCENT,
            pct(foreign_nights, total_nights),
            intent="neutral",
        ),
        Kpi(
            "top_country",
            tr("top_country", lang),
            TEXT,
            country_label(top, lang) if top else tr("none", lang),
            intent="neutral",
        ),
    ]
    chart_rows = [
        {"country": row["country"], "label": country_label(row["country"], lang), "nights": row["nights"]}
        for row in rows[:TOP_COUNTRIES]
    ]
    rest = rows[TOP_COUNTRIES:]
    if rest:
        chart_rows.append(
            {"country": "__other__", "label": tr("other", lang), "nights": sum(r["nights"] for r in rest)}
        )
    charts = [
        Chart(
            key="countries",
            title=tr("c_countries", lang),
            type="hbar",
            x="label",
            x_type="text",
            value_type=NUMBER,
            series=[Series("nights", tr("sold", lang))],
            data=chart_rows,
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Nacionalidad del titular de la reserva. Noches e ingresos siguen las mismas reglas del reporte "
            "de "
            "rendimiento (la suma de los países es el total del hotel).",
            "Nationality of the booker. Nights and revenue follow the performance report rules (the "
            "countries add up "
            "to the hotel total).",
        ),
        L(
            lang,
            "Huéspedes únicos: titulares distintos con al menos una noche vendida en el rango.",
            "Unique guests: distinct bookers with at least one sold night in the range.",
        ),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[Table("countries", tr("t_countries", lang), columns, rows, totals_row)],
        notes=notes,
    )
