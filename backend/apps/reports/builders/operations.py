"""Operational reports (permission ``reports.operational``): arrivals, departures, in house, no-shows and room
status. Rows are stays (a room, or a dorm bed), like the Today panel."""

from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal

from django.db.models import Q

from apps.bookings.models import Reservation, Stay
from apps.inventory.models import Bed, Room, RoomBlock, RoomType
from apps.reports.builders.common import (
    L,
    balances,
    base_notes,
    guest_name,
    i18n_name,
    room_label,
)
from apps.reports.builders.performance import _lost
from apps.reports.engine import DAY, channel_of
from apps.reports.labels import (
    CHANNELS,
    OCCUPANCY_STATES,
    RESERVATION_STATUSES,
    ROOM_STATUSES,
    enum_labels,
    tr,
)
from apps.reports.output import (
    BOOLEAN,
    CODE,
    DATE,
    MONEY,
    NUMBER,
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
PENDING = ("tentative", "confirmed")


def _stays(p, **filters):
    return (
        Stay.objects.filter(reservation__property=p.prop, **filters)
        .select_related("reservation__booker", "room", "bed", "room_type")
        .order_by("checkin_date", "reservation__code", "created_at")
    )


def _stay_row(p, stay, balance_by_reservation: dict, seen: set) -> dict:
    """One row per stay; the reservation balance goes on its first row only (so totals never double count)."""
    reservation = stay.reservation
    first = reservation.pk not in seen
    seen.add(reservation.pk)
    return {
        "code": reservation.code,
        "reservation_id": str(reservation.pk),
        "guest": guest_name(reservation.booker),
        "vip": bool(reservation.booker.is_vip),
        "status": stay.status,
        "room_type": i18n_name(stay.room_type.name, p.lang) or stay.room_type.code,
        "room": room_label(stay),
        "checkin": stay.checkin_date,
        "checkout": stay.checkout_date,
        "nights": (stay.checkout_date - stay.checkin_date).days,
        "pax": stay.adults + stay.children,
        "channel": channel_of(reservation.source, reservation.channel_code),
        "eta": reservation.eta.strftime("%H:%M") if reservation.eta else "",
        "balance": balance_by_reservation.get(reservation.pk, ZERO) if first else None,
    }


def _columns(lang: str, keys: list[str]) -> list[Column]:
    catalog = {
        "checkin": Column("checkin", tr("checkin", lang), DATE),
        "checkout": Column("checkout", tr("checkout", lang), DATE),
        "code": Column("code", tr("code", lang), TEXT, link="reservation"),
        "guest": Column("guest", tr("guest", lang), TEXT),
        "vip": Column("vip", tr("vip", lang), BOOLEAN),
        "status": Column(
            "status",
            tr("status", lang),
            STATUS,
            status_kind="reservation",
            labels=enum_labels(RESERVATION_STATUSES, lang),
        ),
        "room_type": Column("room_type", tr("room_type", lang), TEXT),
        "room": Column("room", tr("room", lang), TEXT),
        "nights": Column("nights", tr("nights", lang), NUMBER),
        "pax": Column("pax", tr("pax", lang), NUMBER),
        "channel": Column("channel", tr("channel", lang), CODE, labels=enum_labels(CHANNELS, lang)),
        "eta": Column("eta", tr("eta", lang), TEXT),
        "balance": Column("balance", tr("balance", lang), MONEY),
    }
    return [catalog[key] for key in keys]


def _positive(values) -> Decimal:
    return sum((value for value in values if value and value > 0), ZERO)


def build_arrivals(p) -> ReportResult:
    lang = p.lang
    stays = list(
        _stays(
            p,
            checkin_date__gte=p.start,
            checkin_date__lte=p.end,
            status__in=[*PENDING, "checked_in", "checked_out"],
        )
    )
    balance_of = balances(stay.reservation_id for stay in stays)
    seen: set = set()
    rows = [_stay_row(p, stay, balance_of, seen) for stay in stays]
    pending = [s for s in stays if s.status in PENDING]
    pending_reservations = {s.reservation_id for s in pending}
    summary = [
        Kpi("arrivals", tr("arrivals", lang), NUMBER, len(stays), intent="neutral"),
        Kpi("done", tr("arrivals_done", lang), NUMBER, len(stays) - len(pending), intent="neutral"),
        Kpi("pending", tr("arrivals_pending", lang), NUMBER, len(pending), intent="neutral"),
        Kpi(
            "unassigned",
            tr("unassigned", lang),
            NUMBER,
            sum(1 for s in pending if s.room_id is None),
            intent="lower-is-better",
        ),
        Kpi("pax", tr("pax", lang), NUMBER, sum(s.adults + s.children for s in stays), intent="neutral"),
        Kpi(
            "vip",
            tr("vip_count", lang),
            NUMBER,
            sum(1 for s in stays if s.reservation.booker.is_vip),
            intent="neutral",
        ),
        Kpi(
            "balance_due",
            tr("balance_due", lang),
            MONEY,
            _positive(balance_of.get(rid) for rid in pending_reservations),
            intent="lower-is-better",
        ),
    ]
    keys = [
        "checkin",
        "code",
        "guest",
        "vip",
        "status",
        "room_type",
        "room",
        "nights",
        "pax",
        "channel",
        "eta",
        "balance",
    ]
    totals = {
        "code": tr("total_row", lang),
        "nights": sum(r["nights"] for r in rows),
        "pax": sum(r["pax"] for r in rows),
        "balance": sum((r["balance"] for r in rows if r["balance"] is not None), ZERO),
    }
    notes = base_notes(
        p,
        L(
            lang,
            "Estadías (habitaciones o camas) con llegada en el rango: tentativas, confirmadas y las que ya "
            "hicieron "
            "check-in o check-out. Las canceladas y los no-show no aparecen. Saldo = saldo de la reserva (en "
            "su "
            "primera fila) con las noches aún no publicadas incluidas.",
            "Stays (rooms or beds) arriving in the range: tentative, confirmed and those already checked in "
            "or out. "
            "Cancelled and no-show stays are left out. Balance = the booking's balance (on its first row), "
            "including "
            "nights not posted yet.",
        ),
    )
    return ReportResult(
        summary=summary,
        tables=[Table("arrivals", tr("t_arrivals", lang), _columns(lang, keys), rows, totals)],
        notes=notes,
    )


def _expected(p) -> Q:
    """Confirmed stays that have not arrived yet but still will (arrival on or after the business date): they
    are tomorrow's departures and in-house guests. A confirmed stay whose arrival already passed is a pending
    no-show, not a guest."""
    return Q(status="confirmed", checkin_date__gte=p.business_date)


def build_departures(p) -> ReportResult:
    lang = p.lang
    today = p.business_date
    stays = list(
        _stays(p, checkout_date__gte=p.start, checkout_date__lte=p.end).filter(
            Q(status__in=["checked_in", "checked_out"]) | (_expected(p) & Q(checkout_date__gt=today))
        )
    )
    balance_of = balances(stay.reservation_id for stay in stays)
    seen: set = set()
    rows = [_stay_row(p, stay, balance_of, seen) for stay in stays]
    rows.sort(key=lambda row: (row["checkout"], row["status"] != "checked_in", row["room"]))
    pending = [s for s in stays if s.status != "checked_out"]
    with_balance = {rid for rid, value in balance_of.items() if value and value > 0}
    summary = [
        Kpi("departures", tr("departures", lang), NUMBER, len(stays), intent="neutral"),
        Kpi("done", tr("departures_done", lang), NUMBER, len(stays) - len(pending), intent="neutral"),
        Kpi("pending", tr("departures_pending", lang), NUMBER, len(pending), intent="neutral"),
        Kpi(
            "with_balance",
            L(lang, "Reservas con saldo", "Bookings with a balance"),
            NUMBER,
            len(with_balance),
            intent="lower-is-better",
        ),
        Kpi(
            "balance_due",
            tr("balance_due", lang),
            MONEY,
            _positive(balance_of.values()),
            intent="lower-is-better",
        ),
    ]
    keys = [
        "checkout",
        "code",
        "guest",
        "vip",
        "status",
        "room",
        "room_type",
        "checkin",
        "nights",
        "pax",
        "balance",
    ]
    totals = {
        "code": tr("total_row", lang),
        "nights": sum(r["nights"] for r in rows),
        "pax": sum(r["pax"] for r in rows),
        "balance": sum((r["balance"] for r in rows if r["balance"] is not None), ZERO),
    }
    notes = base_notes(
        p,
        L(
            lang,
            "Estadías en casa o finalizadas con salida en el rango (la salida es el día en que dejan la "
            "habitación), "
            "más las confirmadas que aún van a llegar cuando el rango incluye fechas futuras. Las estadías "
            "que nunca "
            "llegaron no aparecen (ver no-shows).",
            "In-house or checked-out stays departing in the range (departure = the day the room is left), "
            "plus the "
            "confirmed stays still to arrive when the range reaches future dates. Stays that never arrived "
            "are left "
            "out (see no-shows).",
        ),
    )
    return ReportResult(
        summary=summary,
        tables=[Table("departures", tr("t_departures", lang), _columns(lang, keys), rows, totals)],
        notes=notes,
    )


def build_in_house(p) -> ReportResult:
    lang = p.lang
    today = p.business_date
    covered = Q(status__in=["checked_in", "checked_out"])
    if p.end > today:  # future nights of the range: guests expected to be in house (arrive later, still sold)
        first_future = max(p.start, today + DAY)
        covered |= _expected(p) & Q(checkout_date__gt=first_future)
    stays = list(_stays(p, checkin_date__lte=p.end, checkout_date__gt=p.start).filter(covered))
    balance_of = balances(stay.reservation_id for stay in stays)
    seen: set = set()
    rows = [_stay_row(p, stay, balance_of, seen) for stay in stays]
    rows.sort(key=lambda row: (row["room"] == "", row["room"]))
    in_house_reservations = {s.reservation_id for s in stays if s.status == "checked_in"}
    summary = [
        Kpi("stays", tr("in_house_stays", lang), NUMBER, len(stays), intent="neutral"),
        Kpi(
            "pax",
            tr("guests_in_house", lang),
            NUMBER,
            sum(s.adults + s.children for s in stays),
            intent="neutral",
        ),
        Kpi(
            "vip",
            tr("vip_count", lang),
            NUMBER,
            sum(1 for s in stays if s.reservation.booker.is_vip),
            intent="neutral",
        ),
        Kpi(
            "departing",
            L(lang, "Salen al final del rango", "Leaving at the end of the range"),
            NUMBER,
            sum(1 for s in stays if s.checkout_date == p.end + DAY),
            intent="neutral",
        ),
        Kpi(
            "balance_due",
            tr("balance_due", lang),
            MONEY,
            _positive(balance_of.get(rid) for rid in in_house_reservations),
            intent="lower-is-better",
        ),
    ]
    keys = [
        "room",
        "code",
        "guest",
        "vip",
        "status",
        "room_type",
        "checkin",
        "checkout",
        "nights",
        "pax",
        "balance",
    ]
    totals = {
        "room": tr("total_row", lang),
        "nights": sum(r["nights"] for r in rows),
        "pax": sum(r["pax"] for r in rows),
        "balance": sum((r["balance"] for r in rows if r["balance"] is not None), ZERO),
    }
    notes = base_notes(
        p,
        L(
            lang,
            "Estadías que ocuparon (o están ocupando) una habitación o cama alguna noche del rango: llegada "
            "≤ noche "
            "< salida y el huésped ya hizo check-in. Para las noches futuras (después de la fecha de "
            "negocio) "
            "también cuentan las confirmadas que van a llegar. Las llegadas pendientes de hoy están en el "
            "reporte "
            "de llegadas.",
            "Stays that occupied (or are occupying) a room or bed on some night of the range: arrival ≤ "
            "night < "
            "departure and the guest has checked in. For future nights (after the business date) the "
            "confirmed stays "
            "still to arrive count too. Today's pending arrivals are in the arrivals report.",
        ),
    )
    return ReportResult(
        summary=summary,
        tables=[Table("in_house", tr("t_in_house", lang), _columns(lang, keys), rows, totals)],
        notes=notes,
    )


def build_no_shows(p) -> ReportResult:
    lang = p.lang
    reservations = list(
        Reservation.objects.filter(
            property=p.prop, status="no_show", checkin_date__gte=p.start, checkin_date__lte=p.end
        )
        .select_related("booker")
        .order_by("checkin_date", "code")
    )
    ids = [r.pk for r in reservations]
    lost = _lost(ids)
    balance_of = balances(ids)
    rows = []
    for reservation in reservations:
        nights, revenue = lost[reservation.pk]
        balance = balance_of.get(reservation.pk, ZERO)
        rows.append(
            {
                "checkin": reservation.checkin_date,
                "code": reservation.code,
                "reservation_id": str(reservation.pk),
                "guest": guest_name(reservation.booker),
                "channel": channel_of(reservation.source, reservation.channel_code),
                "nights": nights,
                "lost_revenue": revenue,
                "fee": reservation.cancellation_fee,
                "balance": balance,
            }
        )
    columns = [
        Column("checkin", tr("checkin", lang), DATE),
        Column("code", tr("code", lang), TEXT, link="reservation"),
        Column("guest", tr("guest", lang), TEXT),
        Column("channel", tr("channel", lang), CODE, labels=enum_labels(CHANNELS, lang)),
        Column("nights", tr("nights", lang), NUMBER),
        Column("lost_revenue", tr("lost_revenue", lang), MONEY),
        Column("fee", tr("fee", lang), MONEY),
        Column("balance", tr("fees_pending", lang), MONEY),
    ]
    totals_row = {
        "code": tr("total_row", lang),
        "nights": sum(r["nights"] for r in rows),
        "lost_revenue": sum((r["lost_revenue"] for r in rows), ZERO),
        "fee": sum((r["fee"] for r in rows), ZERO),
        "balance": sum((r["balance"] for r in rows), ZERO),
    }
    summary = [
        Kpi("no_shows", tr("no_shows", lang), NUMBER, len(rows), intent="lower-is-better"),
        Kpi(
            "lost_nights",
            tr("lost_nights_total", lang),
            NUMBER,
            totals_row["nights"],
            intent="lower-is-better",
        ),
        Kpi(
            "lost_revenue",
            tr("lost_revenue", lang),
            MONEY,
            totals_row["lost_revenue"],
            intent="lower-is-better",
        ),
        Kpi("fees", tr("fees_charged", lang), MONEY, totals_row["fee"], intent="neutral"),
        Kpi(
            "fees_pending",
            tr("fees_pending", lang),
            MONEY,
            _positive(r["balance"] for r in rows),
            intent="lower-is-better",
        ),
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Reservas marcadas como no-show con llegada en el rango. Ingresos perdidos: tarifa neta de las "
            "noches "
            "reservadas. Penalidad: la cobrada según la política; por cobrar = saldo pendiente de la "
            "reserva.",
            "Bookings marked as no-show arriving in the range. Lost revenue: net rate of the booked nights. "
            "Penalty: "
            "the one charged by the policy; outstanding = the booking's unpaid balance.",
        ),
    )
    return ReportResult(
        summary=summary,
        tables=[Table("no_shows", tr("t_no_shows", lang), columns, rows, totals_row)],
        notes=notes,
    )


def _floor_key(room) -> tuple:
    floor = room.floor or ""
    return (
        (0, int(floor), room.sort_order, room.number)
        if floor.isdigit()
        else (1, floor, room.sort_order, room.number)
    )


def build_housekeeping_status(p) -> ReportResult:
    """Snapshot of every active room at the current business date: cleaning state and who is in it."""
    lang = p.lang
    today = p.business_date
    rooms = sorted(
        Room.objects.filter(property=p.prop, is_active=True, room_type__is_active=True).select_related(
            "room_type"
        ),
        key=_floor_key,
    )
    dorm_rooms = {room.pk for room in rooms if room.room_type.kind == RoomType.Kind.DORM}
    beds_per_room = Counter(
        Bed.objects.filter(room_id__in=dorm_rooms, is_active=True).values_list("room_id", flat=True)
    )
    staying_in: dict = defaultdict(list)  # in-house guests who sleep here tonight
    leaving: dict = defaultdict(list)  # in-house guests whose departure is today
    for stay in Stay.objects.filter(
        reservation__property=p.prop, status="checked_in", checkin_date__lte=today, checkout_date__gte=today
    ).select_related("reservation__booker"):
        if stay.room_id is None:
            continue
        (leaving if stay.checkout_date == today else staying_in)[stay.room_id].append(stay)
    arrivals: dict = defaultdict(list)
    for stay in Stay.objects.filter(
        reservation__property=p.prop, status__in=PENDING, checkin_date=today, room__isnull=False
    ).select_related("reservation__booker"):
        arrivals[stay.room_id].append(stay)
    blocked_rooms, blocked_beds = set(), Counter()
    for room_id, bed_id in RoomBlock.objects.filter(
        room__property=p.prop, released_at__isnull=True, start_date__lte=today, end_date__gt=today
    ).values_list("room_id", "bed_id"):
        if bed_id:
            blocked_beds[room_id] += 1
        else:
            blocked_rooms.add(room_id)

    rows = []
    status_counts = Counter()
    occupancy_counts = Counter()
    vacant_dirty = arrivals_not_ready = 0
    for room in rooms:
        staying = staying_in.get(room.pk, [])
        in_room = staying + leaving.get(room.pk, [])
        if room.pk in blocked_rooms:
            state = "blocked"
        elif room.pk in dorm_rooms:
            beds = beds_per_room.get(room.pk, 0)
            state = "vacant" if not staying else ("occupied" if len(staying) >= beds > 0 else "partial")
        else:
            state = "occupied" if staying else "vacant"
        status_counts[room.housekeeping_status] += 1
        occupancy_counts[state] += 1
        dirty = room.housekeeping_status in ("dirty", "out_of_service")
        if state == "vacant" and room.housekeeping_status == "dirty":
            vacant_dirty += 1
        arriving = arrivals.get(room.pk, [])
        if arriving and dirty:
            arrivals_not_ready += 1
        rows.append(
            {
                "room": room.number,
                "floor": room.floor,
                "room_type": i18n_name(room.room_type.name, lang) or room.room_type.code,
                "status": room.housekeeping_status,
                "occupancy_state": state,
                "occupant": ", ".join(guest_name(s.reservation.booker) for s in in_room[:3])
                + (f" +{len(in_room) - 3}" if len(in_room) > 3 else ""),
                "departure_today": room.pk in leaving,
                "arrival_today": ", ".join(guest_name(s.reservation.booker) for s in arriving[:2]),
            }
        )
    columns = [
        Column("room", tr("room", lang), TEXT),
        Column("floor", tr("floor", lang), TEXT),
        Column("room_type", tr("room_type", lang), TEXT),
        Column(
            "status", tr("status", lang), STATUS, status_kind="room", labels=enum_labels(ROOM_STATUSES, lang)
        ),
        Column(
            "occupancy_state", tr("occupancy_state", lang), CODE, labels=enum_labels(OCCUPANCY_STATES, lang)
        ),
        Column("occupant", tr("occupant", lang), TEXT),
        Column("departure_today", tr("departure_today", lang), BOOLEAN),
        Column("arrival_today", tr("arrival_today", lang), TEXT),
    ]
    summary = [
        Kpi(
            "clean",
            enum_labels(ROOM_STATUSES, lang)["clean"],
            NUMBER,
            status_counts["clean"],
            intent="neutral",
        ),
        Kpi(
            "inspected",
            enum_labels(ROOM_STATUSES, lang)["inspected"],
            NUMBER,
            status_counts["inspected"],
            intent="neutral",
        ),
        Kpi(
            "dirty",
            enum_labels(ROOM_STATUSES, lang)["dirty"],
            NUMBER,
            status_counts["dirty"],
            intent="lower-is-better",
        ),
        Kpi(
            "out_of_service",
            enum_labels(ROOM_STATUSES, lang)["out_of_service"],
            NUMBER,
            status_counts["out_of_service"],
            intent="lower-is-better",
        ),
        Kpi(
            "occupied",
            tr("occupied", lang),
            NUMBER,
            occupancy_counts["occupied"] + occupancy_counts["partial"],
            intent="neutral",
        ),
        Kpi("vacant_dirty", tr("vacant_dirty", lang), NUMBER, vacant_dirty, intent="lower-is-better"),
        Kpi(
            "arrivals_not_ready",
            tr("arrivals_not_ready", lang),
            NUMBER,
            arrivals_not_ready,
            intent="lower-is-better",
        ),
    ]
    chart_rows = [
        {"status": code, "label": label, "rooms": status_counts[code]}
        for code, label in enum_labels(ROOM_STATUSES, lang).items()
    ]
    charts = [
        Chart(
            key="rooms",
            title=tr("c_rooms", lang),
            type="status_bar",
            x="status",
            x_type="text",
            value_type=NUMBER,
            series=[Series("rooms", tr("rooms", lang))],
            data=chart_rows,
        )
    ]
    notes = base_notes(
        p,
        L(
            lang,
            "Habitaciones activas de categorías activas. Ocupada: un huésped en casa pasa la noche de hoy; "
            "en "
            "dormitorios, parcial si quedan camas libres. Bloqueada: un bloqueo activo cubre hoy.",
            "Active rooms of active categories. Occupied: an in-house guest stays tonight; in dorms, partly "
            "occupied "
            "while beds are free. Blocked: an active block covers today.",
        ),
    )
    return ReportResult(
        summary=summary,
        charts=charts,
        tables=[Table("rooms", tr("t_rooms", lang), columns, rows)],
        notes=notes,
    )
