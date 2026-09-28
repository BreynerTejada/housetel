"""The Today panel of the front desk (plan C1): KPIs and the actionable lists of the business date.

Lists (business date `bd`, one row per stay — a dorm stay is one bed):
- `arrivals`: stays arriving on `bd` that are tentative or confirmed (pending) or already checked in/out
  (`done`), plus pending stays whose arrival already passed (issue `late_arrival`, not counted).
- `departures`: checked-in stays leaving on `bd` (pending) or checked out with checkout on `bd` (`done`), plus
  checked-in stays whose checkout already passed (issue `overdue`, not counted).
- `in_house`: every checked-in stay.

`ready` = one click is enough: confirmed, arrives on `bd`, room assigned, clean or inspected and vacant.
An arrival whose room (or dorm bed) still has a guest in house — typically one leaving today who has not
checked out yet — gets the issue `room_occupied` and `occupied_by` (that guest): the bookings check-in only
looks at the housekeeping status, so the desk must see it here.
`online_checkin_done` comes from `guestportal.OnlineCheckin` (status `completed`) when that model exists.

`rooms` is the key rack of the house tonight: every active room of an active category, by floor and room
order, with its housekeeping status, whether a block covers `bd`, the guest in house (`occupant`, private
rooms) and the pending arrival assigned to it (`arrival`), or bed counts for dorms.
"""

import re
from collections import Counter
from datetime import timedelta
from decimal import Decimal

from django.apps import apps as django_apps
from django.db.models import Count, Q

from apps.bookings.models import Reservation, Stay
from apps.bookings.services.queries import with_balance
from apps.bookings.services.rooms import READY_STATUSES
from apps.core.dates import property_now
from apps.frontdesk.models import NightAuditReport
from apps.frontdesk.services.figures import day_figures, money
from apps.inventory.models import Room, RoomBlock

PENDING = ("tentative", "confirmed")
ARRIVED = ("checked_in", "checked_out")
ZERO = Decimal("0")


def today_board(prop) -> dict:
    bd = prop.business_date
    calendar_date = property_now(prop).date()
    stays = list(
        Stay.objects.filter(reservation__property=prop)
        .filter(
            Q(checkin_date=bd, status__in=[*PENDING, *ARRIVED])
            | Q(checkin_date__lt=bd, status__in=PENDING)
            | Q(status="checked_in")
            | Q(status="checked_out", checkout_date=bd)
        )
        .select_related("reservation__booker", "room", "bed", "room_type")
    )
    reservation_ids = {stay.reservation_id for stay in stays}
    balances = dict(
        with_balance(Reservation.objects.filter(pk__in=reservation_ids)).values_list("pk", "balance")
    )
    online = online_checkins_done(reservation_ids)
    occupants = _occupants_by_unit(stays)

    arrivals, departures, in_house = [], [], []
    for stay in stays:
        row = _row(stay, bd, balances.get(stay.reservation_id, ZERO), stay.reservation_id in online)
        if (stay.checkin_date == bd and stay.status in (*PENDING, *ARRIVED)) or (
            stay.checkin_date < bd and stay.status in PENDING
        ):
            arrivals.append(_arrival(row, stay, bd, _occupant_of(stay, occupants, bd)))
        if (stay.status == "checked_in" and stay.checkout_date <= bd) or (
            stay.status == "checked_out" and stay.checkout_date == bd
        ):
            departures.append(_departure(row, stay, bd))
        if stay.status == "checked_in":
            in_house.append(_in_house(row, stay, bd))

    arrivals.sort(key=_arrival_order)
    departures.sort(key=_departure_order)
    in_house.sort(key=_room_order)
    figures = day_figures(prop, bd)
    return {
        "business_date": bd.isoformat(),
        "calendar_date": calendar_date.isoformat(),
        "currency": prop.currency or "COP",
        "kpis": {
            "occupancy_pct": figures["occupancy_pct"],
            "rooms_occupied": figures["rooms_occupied"],
            "rooms_available": figures["rooms_available"],
            "rooms_blocked": figures["rooms_blocked"],
            "rooms_free": figures["rooms_free"],
            "arrivals_total": sum(1 for row in arrivals if row["checkin"] == bd.isoformat()),
            "arrivals_done": sum(1 for row in arrivals if row["done"]),
            "arrivals_late": sum(1 for row in arrivals if "late_arrival" in row["issues"]),
            "departures_total": sum(1 for row in departures if row["checkout"] == bd.isoformat()),
            "departures_done": sum(1 for row in departures if row["done"]),
            "departures_overdue": sum(1 for row in departures if "overdue" in row["issues"]),
            "in_house": len(in_house),
            "guests_in_house": sum(row["adults"] + row["children"] for row in in_house),
            "room_revenue_today": figures["room_revenue"],
            "other_revenue_today": figures["other_revenue"],
            "revenue_today": figures["revenue"],
            "adr_today": figures["adr"],
            "collected_today": figures["collected"],
        },
        "arrivals": arrivals,
        "departures": departures,
        "in_house": in_house,
        "rooms": _rack(prop, bd, stays),
        "previous": _previous(prop, bd),
        "night_audit": {"due": bd < calendar_date, "last_report": last_report(prop)},
    }


def _previous(prop, bd) -> dict | None:
    """Figures of the day before `bd` as its night audit closed them (None when that day has no report)."""
    report = NightAuditReport.objects.filter(
        property=prop, business_date=bd - timedelta(days=1), status__in=["completed", "partial"]
    ).first()
    if report is None:
        return None
    figures = (report.summary or {}).get("figures") or {}
    return {
        "business_date": report.business_date.isoformat(),
        "occupancy_pct": figures.get("occupancy_pct"),
        "rooms_occupied": figures.get("rooms_occupied"),
        "adr": figures.get("adr"),
        "revenue": figures.get("revenue"),
    }


def _rack(prop, bd, stays) -> list[dict]:
    rooms = sorted(
        Room.objects.filter(property=prop, is_active=True, room_type__is_active=True)
        .select_related("room_type")
        .annotate(active_beds=Count("beds", filter=Q(beds__is_active=True))),
        key=lambda room: (_floor_key(room.floor), room.sort_order, _natural(room.number)),
    )
    blocks = RoomBlock.objects.filter(
        room__property=prop, released_at__isnull=True, start_date__lte=bd, end_date__gt=bd
    ).values_list("room_id", "bed_id")
    blocked_rooms = {room_id for room_id, bed_id in blocks if bed_id is None}
    blocked_beds = Counter(room_id for room_id, bed_id in blocks if bed_id is not None)
    in_house: dict = {}
    arriving: dict = {}
    for stay in stays:
        if stay.room_id is None:
            continue
        if stay.status == "checked_in":
            in_house.setdefault(stay.room_id, []).append(stay)
        elif stay.status in PENDING and stay.checkin_date <= bd < stay.checkout_date:
            arriving.setdefault(stay.room_id, []).append(stay)
    return [
        _rack_room(
            room, bd, in_house.get(room.pk, []), arriving.get(room.pk, []), blocked_rooms, blocked_beds
        )
        for room in rooms
    ]


def _rack_room(room, bd, in_house, arriving, blocked_rooms, blocked_beds) -> dict:
    room_type = room.room_type
    entry = {
        "id": str(room.pk),
        "number": room.number,
        "floor": room.floor,
        "room_type": {
            "id": str(room_type.pk),
            "code": room_type.code,
            "color": room_type.color,
            "kind": room_type.kind,
        },
        "housekeeping_status": room.housekeeping_status,
        "blocked": room.pk in blocked_rooms,
        "occupant": None,
        "arrival": None,
        "beds": None,
    }
    if room_type.kind == "dorm":
        entry["beds"] = {
            "total": room.active_beds,
            "occupied": len(in_house),
            "departing": sum(1 for stay in in_house if stay.checkout_date <= bd),
            "arriving": len(arriving),
            "blocked": blocked_beds.get(room.pk, 0),
        }
        return entry
    if in_house:
        # a guest staying tonight wins over one who should already have left
        stay = max(in_house, key=lambda item: item.checkout_date)
        entry["occupant"] = {
            "stay_id": str(stay.pk),
            "reservation_id": str(stay.reservation_id),
            "guest_name": stay.reservation.booker.full_name,
            "checkout": stay.checkout_date.isoformat(),
            "departing": stay.checkout_date <= bd,
        }
    if arriving:
        stay = min(arriving, key=lambda item: (item.checkin_date, item.created_at))
        entry["arrival"] = {
            "stay_id": str(stay.pk),
            "reservation_id": str(stay.reservation_id),
            "guest_name": stay.reservation.booker.full_name,
            "checkin": stay.checkin_date.isoformat(),
            "late": stay.checkin_date < bd,
        }
    return entry


def _floor_key(floor: str) -> tuple:
    """Numeric floors first (1, 2, 10), then named ones, rooms without a floor last."""
    value = (floor or "").strip()
    if value.lstrip("-").isdigit():
        return (0, int(value), "")
    return (1 if value else 2, 0, value.lower())


def _natural(text: str) -> list:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text or "")]


def _online_checkin_model():
    """`guestportal.OnlineCheckin` (C5), or None while that model does not exist."""
    try:
        return django_apps.get_model("guestportal", "OnlineCheckin")
    except LookupError:
        return None


def online_checkins_done(reservation_ids) -> set:
    """Reservations whose online check-in (C5) is completed; empty while the guest portal has no model."""
    model = _online_checkin_model()
    if model is None or not reservation_ids:
        return set()
    return set(
        model.objects.filter(reservation_id__in=reservation_ids, status="completed").values_list(
            "reservation_id", flat=True
        )
    )


def online_checkin_state(reservation) -> dict:
    """`{reservation_id, status, completed_at}` of the reservation's online check-in (status None = never
    started, or the guest portal is not installed)."""
    model = _online_checkin_model()
    checkin = model.objects.filter(reservation=reservation).first() if model is not None else None
    completed_at = getattr(checkin, "completed_at", None)
    return {
        "reservation_id": str(reservation.pk),
        "status": checkin.status if checkin is not None else None,
        "completed_at": completed_at.isoformat() if completed_at else None,
    }


def last_report(prop) -> dict | None:
    report = NightAuditReport.objects.filter(property=prop).order_by("-business_date").first()
    if report is None:
        return None
    return {
        "id": str(report.pk),
        "business_date": report.business_date.isoformat(),
        "status": report.status,
        "finished_at": report.finished_at.isoformat() if report.finished_at else None,
    }


def _row(stay, bd, balance, online_done) -> dict:
    reservation = stay.reservation
    booker = reservation.booker
    room, bed = stay.room, stay.bed
    return {
        "stay_id": str(stay.pk),
        "reservation_id": str(reservation.pk),
        "code": reservation.code,
        "status": stay.status,
        "reservation_status": reservation.status,
        "source": reservation.source,
        "channel_code": reservation.channel_code,
        "guest_id": str(booker.pk),
        "guest_name": booker.full_name,
        "is_vip": booker.is_vip,
        "room_id": str(room.pk) if room else None,
        "room": room.number if room else None,
        "bed_id": str(bed.pk) if bed else None,
        "bed": bed.label if bed else None,
        "room_status": room.housekeeping_status if room else None,
        "room_type": {
            "id": str(stay.room_type_id),
            "code": stay.room_type.code,
            "name": stay.room_type.name,
            "color": stay.room_type.color,
            "kind": stay.room_type.kind,
        },
        "checkin": stay.checkin_date.isoformat(),
        "checkout": stay.checkout_date.isoformat(),
        "nights": (stay.checkout_date - stay.checkin_date).days,
        "adults": stay.adults,
        "children": stay.children,
        "eta": reservation.eta.strftime("%H:%M") if reservation.eta else None,
        "balance": money(balance),
        "balance_due": money(max(balance, ZERO)),
        "online_checkin_done": online_done,
        "checked_in_at": stay.checked_in_at.isoformat() if stay.checked_in_at else None,
        "checked_out_at": stay.checked_out_at.isoformat() if stay.checked_out_at else None,
        "departs_today": stay.checkout_date == bd,
        "occupied_by": None,
    }


def _occupants_by_unit(stays) -> dict:
    """Guests in house by unit: `(room_id, None)` for a private room, `(room_id, bed_id)` for a dorm bed."""
    occupants: dict = {}
    for stay in stays:
        if stay.status == "checked_in" and stay.room_id is not None:
            occupants.setdefault((stay.room_id, stay.bed_id), []).append(stay)
    return occupants


def _occupant_of(stay, occupants, bd) -> dict | None:
    """The guest still in house in the unit a pending arrival is assigned to (the one leaving last)."""
    if stay.status not in PENDING or stay.room_id is None:
        return None
    others = [item for item in occupants.get((stay.room_id, stay.bed_id), []) if item.pk != stay.pk]
    if not others:
        return None
    occupant = max(others, key=lambda item: item.checkout_date)
    return {
        "stay_id": str(occupant.pk),
        "reservation_id": str(occupant.reservation_id),
        "code": occupant.reservation.code,
        "guest_name": occupant.reservation.booker.full_name,
        "checkout": occupant.checkout_date.isoformat(),
        "departing": occupant.checkout_date <= bd,
    }


def _arrival(row, stay, bd, occupied_by=None) -> dict:
    pending = stay.status in PENDING
    issues = []
    if pending:
        if stay.checkin_date < bd:
            issues.append("late_arrival")
        if stay.status == "tentative":
            issues.append("tentative")
        if stay.room_id is None:
            issues.append("unassigned")
        else:
            if occupied_by is not None:
                issues.append("room_occupied")
            if stay.room.housekeeping_status not in READY_STATUSES:
                issues.append("room_not_ready")
    ready = pending and not issues
    return {**row, "done": not pending, "ready": ready, "issues": issues, "occupied_by": occupied_by}


def _departure(row, stay, bd) -> dict:
    done = stay.status == "checked_out"
    issues = []
    if not done and stay.checkout_date < bd:
        issues.append("overdue")
    if Decimal(row["balance"]) > 0:
        issues.append("balance_due")
    return {**row, "done": done, "ready": not done and not issues, "issues": issues}


def _in_house(row, stay, bd) -> dict:
    issues = ["overdue"] if stay.checkout_date < bd else []
    return {**row, "done": False, "ready": False, "issues": issues}


def _arrival_order(row):
    late = "late_arrival" in row["issues"]
    return (row["done"], not late, row["eta"] is None, row["eta"] or "", row["guest_name"])


def _departure_order(row):
    return (row["done"], "overdue" not in row["issues"], *_room_order(row))


def _room_order(row):
    number = row["room"] or ""
    return (number.zfill(8), row["bed"] or "", row["guest_name"])
