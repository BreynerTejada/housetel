"""OTA simulator (plan C3 › Simulador de OTAs, `/app/simulators/ota`).

BookSim, AirSim and the simulated Channex are OTAs that live in this database:

- What the OTA sees is the ARI the PMS pushed (`SimOtaInventory`, one cell per channel room × rate × night).
  `ota_inventory()` shows it as a grid.
- The OTA sells only what it received: every night needs a cell with a price, a free unit (a bed per guest in
  dorms) and no stop-sell, and the stay must respect the arrival night's minimum/maximum stay, closed to
  arrival and closed to departure. `force=True` skips those checks to simulate an overbooking.
- A booking (`SimOtaBooking`) keeps its payload and a revision number. BookSim and AirSim deliver it to the
  PMS at once through `importer.import_booking` (the path of every real channel); the simulated Channex keeps
  it `pending` until the PMS pulls it (`services.pull.pull_bookings`, like the Channex revisions feed).
- Modifications re-check only the nights the booking did not already hold in the same room; the prices of
  kept nights do not change. Cancellations are delivered like any other revision.
"""

import random
import secrets
import uuid
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Max

from apps.core.dates import daterange
from apps.core.dates import nights as stay_nights
from apps.core.errors import DomainError, NotFoundError
from apps.core.money import quantize
from apps.distribution.models import ChannelConnection, ExternalReservationMap, SimOtaBooking, SimOtaInventory
from apps.distribution.types import ImportResult, InboundBooking, InboundRoom
from apps.inventory.models import RoomType

OTA_LABELS = {"booksim": "BookSim", "airsim": "AirSim", "channex": "Channex (simulado)"}
PUSH_DELIVERY = (ChannelConnection.Channel.BOOKSIM, ChannelConnection.Channel.AIRSIM)
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
MAX_NIGHTS = 60

COLOMBIAN_GUESTS = [
    ("Valentina", "Ríos"),
    ("Santiago", "Herrera"),
    ("Camila", "Ospina"),
    ("Mateo", "Cárdenas"),
    ("Isabella", "Moreno"),
    ("Sebastián", "Gutiérrez"),
    ("Mariana", "Salazar"),
    ("Juan Pablo", "Restrepo"),
    ("Daniela", "Quintero"),
    ("Andrés", "Vargas"),
]
FOREIGN_GUESTS = [
    ("Emma", "Schneider", "DE", "en"),
    ("Liam", "Johnson", "US", "en"),
    ("Chloé", "Martin", "FR", "en"),
    ("Lucas", "Silva", "BR", "en"),
    ("Sofía", "Fernández", "AR", "es"),
    ("Noah", "Brown", "CA", "en"),
    ("Olivia", "Taylor", "GB", "en"),
    ("Carmen", "López", "ES", "es"),
]


class SimulatorError(DomainError):
    code = "simulator_error"
    status_code = 409


# --- helpers ------------------------------------------------------------------------------------------------


def is_simulated(connection) -> bool:
    from apps.distribution.providers import connection_mode

    if connection.channel_code in PUSH_DELIVERY:
        return True
    return (
        connection.channel_code == ChannelConnection.Channel.CHANNEX
        and connection_mode(connection) == "simulated"
    )


def ensure_simulated(connection) -> None:
    if not is_simulated(connection):
        error = SimulatorError(
            "Esta conexión habla con un canal real: el simulador solo sirve para BookSim, AirSim y Channex "
            "en modo simulado",
            code="not_simulated",
        )
        error.status_code = 400
        raise error


def _bad_request(message: str, code: str) -> SimulatorError:
    error = SimulatorError(message, code=code)
    error.status_code = 400
    return error


def _room_mapping(connection, external_room_id: str):
    mapping = (
        connection.room_mappings.select_related("room_type")
        .filter(external_room_id=external_room_id, room__isnull=True)
        .first()
    )
    if mapping is None or not external_room_id:
        raise _bad_request(f"La OTA no tiene la habitación «{external_room_id}»", "unknown_room")
    return mapping


def _check_rate(connection, external_rate_id: str, room_type) -> None:
    known = connection.rate_mappings.filter(external_rate_id=external_rate_id).exclude(external_rate_id="")
    if not any(item.room_type_id in (None, room_type.pk) for item in known):
        raise _bad_request(
            f"La OTA no vende la tarifa «{external_rate_id}» en esa habitación", "unknown_rate"
        )


def _check_stay(checkin, checkout, adults, children) -> None:
    if not checkin or not checkout or checkout <= checkin:
        raise _bad_request("La salida debe ser posterior a la llegada", "invalid_dates")
    if (checkout - checkin).days > MAX_NIGHTS:
        raise _bad_request(f"La OTA vende máximo {MAX_NIGHTS} noches por reserva", "invalid_dates")
    if int(adults) < 1 or int(children) < 0:
        raise _bad_request("La reserva necesita al menos un adulto", "invalid_occupancy")


def _units(room_type, adults: int, children: int) -> int:
    """Units the stay takes in the OTA: one room, or one bed per guest in a dorm."""
    return int(adults) + int(children) if room_type.kind == RoomType.Kind.DORM else 1


def _sellability(connection, room, rate, checkin, checkout, units, *, held=frozenset(), dates_changed=True):
    """(price per night or None, reasons the OTA cannot sell it). Nights in `held` (already sold to this
    booking in this room) are not checked again."""
    nights = stay_nights(checkin, checkout)
    cells = {
        cell.date: cell
        for cell in SimOtaInventory.objects.filter(
            connection=connection,
            external_room_id=room,
            external_rate_id=rate,
            date__gte=checkin,
            date__lte=checkout,
        )
    }
    reasons = []
    missing = [night for night in nights if night not in cells]
    if missing:
        reasons.append(
            f"La OTA no ha recibido disponibilidad ni tarifas para {len(missing)} noche(s) desde "
            f"{missing[0].isoformat()}: haz una sincronización completa desde Canales"
        )
    for night in nights:
        cell = cells.get(night)
        if cell is None or night in held:
            continue
        if cell.stop_sell:
            reasons.append(f"Cerrada a la venta el {night.isoformat()}")
        elif cell.price is None:
            reasons.append(f"Sin tarifa el {night.isoformat()}")
        if cell.available < units:
            reasons.append(f"Sin unidades el {night.isoformat()} (quedan {max(cell.available, 0)})")
    arrival, departure = cells.get(checkin), cells.get(checkout)
    if dates_changed and arrival is not None:
        if arrival.closed_to_arrival:
            reasons.append(f"No admite llegadas el {checkin.isoformat()}")
        if arrival.min_los and len(nights) < arrival.min_los:
            reasons.append(f"Estadía mínima de {arrival.min_los} noches llegando el {checkin.isoformat()}")
        if arrival.max_los and len(nights) > arrival.max_los:
            reasons.append(f"Estadía máxima de {arrival.max_los} noches llegando el {checkin.isoformat()}")
    if dates_changed and departure is not None and departure.closed_to_departure:
        reasons.append(f"No admite salidas el {checkout.isoformat()}")
    prices = {
        night: cells[night].price for night in nights if night in cells and cells[night].price is not None
    }
    return prices, reasons


def _nightly(prices: dict, nights: list[date], units: int, currency: str, kept: dict | None = None):
    """Payload nightly rates (the room total per night: price × beds in a dorm); None when a night has no
    price (the PMS prices it)."""
    kept = kept or {}
    rows = []
    for night in nights:
        if night in kept:
            rows.append({"date": night.isoformat(), "amount": kept[night]})
        elif night in prices:
            rows.append(
                {"date": night.isoformat(), "amount": f"{quantize(prices[night] * units, currency):.2f}"}
            )
        else:
            return None
    return rows


def _total(nightly) -> str | None:
    if nightly is None:
        return None
    return f"{sum((Decimal(row['amount']) for row in nightly), Decimal('0')):.2f}"


def _guest(data: dict | None) -> dict:
    """The booker as the OTA sends it; a plausible one is invented when none is given."""
    data = {key: str(value).strip() for key, value in (data or {}).items() if value not in (None, "")}
    if data.get("first_name") or data.get("last_name"):
        return {
            key: data.get(key, "")[:120]
            for key in ("first_name", "last_name", "email", "phone", "country", "language")
        }
    rng = random.Random()
    if rng.random() < 0.6:
        first, last = rng.choice(COLOMBIAN_GUESTS)
        country, language = "CO", "es"
    else:
        first, last, country, language = rng.choice(FOREIGN_GUESTS)
    handle = f"{first}.{last}".lower().replace(" ", "")
    return {
        "first_name": first,
        "last_name": last,
        "email": f"{handle}{rng.randint(10, 99)}@example.com",
        "phone": "",
        "country": country,
        "language": language,
    }


def _new_external_id(connection) -> str:
    if connection.channel_code == ChannelConnection.Channel.BOOKSIM:
        return f"BS-{secrets.randbelow(9_000_000) + 1_000_000}"
    if connection.channel_code == ChannelConnection.Channel.AIRSIM:
        return "AS-HM" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return str(uuid.uuid4())


def _get(connection, external_id: str) -> SimOtaBooking:
    booking = SimOtaBooking.objects.filter(connection=connection, external_id=external_id).first()
    if booking is None:
        raise NotFoundError(f"La OTA no tiene la reserva {external_id}")
    return booking


# --- bookings -----------------------------------------------------------------------------------------------


def create_booking(
    connection,
    *,
    external_room_id: str,
    external_rate_id: str,
    checkin: date,
    checkout: date,
    adults: int,
    children: int = 0,
    guest: dict | None = None,
    notes: str = "",
    force: bool = False,
    actor=None,
) -> SimOtaBooking:
    """A guest books in the OTA (see the module docstring). Raises `SimulatorError(code="ota_not_sellable",
    reasons=[...])` when the OTA cannot sell it and `force` is False."""
    ensure_simulated(connection)
    _check_stay(checkin, checkout, adults, children)
    mapping = _room_mapping(connection, external_room_id)
    _check_rate(connection, external_rate_id, mapping.room_type)
    units = _units(mapping.room_type, adults, children)
    prices, reasons = _sellability(connection, external_room_id, external_rate_id, checkin, checkout, units)
    if reasons and not force:
        raise SimulatorError(
            f"La OTA no puede vender esa estadía: {reasons[0]}", code="ota_not_sellable", reasons=reasons
        )
    currency = connection.property.currency or "COP"
    nightly = _nightly(prices, stay_nights(checkin, checkout), units, currency)
    payload = {
        "ota": OTA_LABELS.get(connection.channel_code, connection.name),
        "guest": _guest(guest),
        "rooms": [
            {
                "external_room_id": external_room_id,
                "external_rate_id": external_rate_id,
                "checkin": checkin.isoformat(),
                "checkout": checkout.isoformat(),
                "adults": int(adults),
                "children": int(children),
                "nightly_rates": nightly,
            }
        ],
        "currency": currency,
        "total": _total(nightly),
        "notes": (notes or "").strip()[:1000],
        "forced": bool(force and reasons),
    }
    for _attempt in range(5):
        try:
            with transaction.atomic():
                booking = SimOtaBooking.objects.create(
                    connection=connection, external_id=_new_external_id(connection), payload=payload
                )
            break
        except IntegrityError:  # external id already used by this OTA: draw another one
            continue
    else:  # pragma: no cover - 5 collisions in a 9-million space
        raise SimulatorError("No se pudo generar el código de la reserva", code="simulator_error")
    _after_change(connection, booking, actor)
    return booking


def modify_booking(
    connection,
    external_id: str,
    *,
    checkin: date | None = None,
    checkout: date | None = None,
    external_room_id: str | None = None,
    external_rate_id: str | None = None,
    adults: int | None = None,
    children: int | None = None,
    force: bool = False,
    actor=None,
) -> SimOtaBooking:
    """The guest changes the booking in the OTA: a new revision, delivered like the first one."""
    ensure_simulated(connection)
    booking = _get(connection, external_id)
    if booking.status == SimOtaBooking.Status.CANCELLED:
        raise SimulatorError("La reserva ya está cancelada en la OTA", code="booking_cancelled")
    old = booking.payload["rooms"][0]
    old_checkin, old_checkout = date.fromisoformat(old["checkin"]), date.fromisoformat(old["checkout"])
    new = {
        "external_room_id": external_room_id or old["external_room_id"],
        "external_rate_id": external_rate_id or old["external_rate_id"],
        "checkin": checkin or old_checkin,
        "checkout": checkout or old_checkout,
        "adults": int(adults if adults is not None else old["adults"]),
        "children": int(children if children is not None else old["children"]),
    }
    _check_stay(new["checkin"], new["checkout"], new["adults"], new["children"])
    mapping = _room_mapping(connection, new["external_room_id"])
    _check_rate(connection, new["external_rate_id"], mapping.room_type)
    units = _units(mapping.room_type, new["adults"], new["children"])
    same_unit = (new["external_room_id"], new["external_rate_id"], units) == (
        old["external_room_id"],
        old["external_rate_id"],
        _units(mapping.room_type, old["adults"], old["children"]),
    )
    held = frozenset(stay_nights(old_checkin, old_checkout)) if same_unit else frozenset()
    prices, reasons = _sellability(
        connection,
        new["external_room_id"],
        new["external_rate_id"],
        new["checkin"],
        new["checkout"],
        units,
        held=held,
        dates_changed=(new["checkin"], new["checkout"]) != (old_checkin, old_checkout),
    )
    if reasons and not force:
        raise SimulatorError(
            f"La OTA no puede aplicar el cambio: {reasons[0]}", code="ota_not_sellable", reasons=reasons
        )
    kept = {}
    if same_unit:
        kept = {
            date.fromisoformat(row["date"]): row["amount"]
            for row in old.get("nightly_rates") or []
            if date.fromisoformat(row["date"]) in held
        }
    currency = booking.payload.get("currency") or connection.property.currency or "COP"
    nightly = _nightly(prices, stay_nights(new["checkin"], new["checkout"]), units, currency, kept)
    room = {
        **new,
        "checkin": new["checkin"].isoformat(),
        "checkout": new["checkout"].isoformat(),
        "nightly_rates": nightly,
    }
    booking.payload = {
        **booking.payload,
        "rooms": [room],
        "total": _total(nightly),
        "forced": bool(booking.payload.get("forced")) or bool(force and reasons),
    }
    booking.status = SimOtaBooking.Status.MODIFIED
    booking.revision += 1
    booking.pms_status, booking.pms_message = SimOtaBooking.PmsStatus.PENDING, ""
    booking.save(update_fields=["payload", "status", "revision", "pms_status", "pms_message", "updated_at"])
    _after_change(connection, booking, actor)
    return booking


def cancel_booking(connection, external_id: str, *, actor=None) -> SimOtaBooking:
    """The guest cancels in the OTA: a `cancelled` revision, delivered like the others."""
    ensure_simulated(connection)
    booking = _get(connection, external_id)
    if booking.status == SimOtaBooking.Status.CANCELLED:
        raise SimulatorError("La reserva ya está cancelada en la OTA", code="booking_cancelled")
    booking.status = SimOtaBooking.Status.CANCELLED
    booking.revision += 1
    booking.pms_status, booking.pms_message = SimOtaBooking.PmsStatus.PENDING, ""
    booking.save(update_fields=["status", "revision", "pms_status", "pms_message", "updated_at"])
    _after_change(connection, booking, actor)
    return booking


def _after_change(connection, booking, actor) -> None:
    if connection.channel_code in PUSH_DELIVERY:
        deliver(connection, booking, actor=actor)


def deliver(connection, booking, *, actor=None) -> ImportResult:
    """Send the booking's current revision to the PMS (BookSim/AirSim do it at once; also "deliver again"
    after a failure)."""
    from apps.distribution.services.importer import import_booking

    result = import_booking(connection, to_inbound(booking), actor=actor)
    booking.pms_status = (
        SimOtaBooking.PmsStatus.FAILED if result.action == "failed" else SimOtaBooking.PmsStatus.IMPORTED
    )
    booking.pms_message = (result.message or "")[:1000]
    booking.save(update_fields=["pms_status", "pms_message", "updated_at"])
    return result


def to_inbound(booking) -> InboundBooking:
    """The booking as the channel sends it to the PMS."""
    payload = booking.payload or {}
    rooms = [
        InboundRoom(
            external_room_id=room["external_room_id"],
            external_rate_id=room["external_rate_id"],
            checkin=date.fromisoformat(room["checkin"]),
            checkout=date.fromisoformat(room["checkout"]),
            adults=int(room.get("adults") or 1),
            children=int(room.get("children") or 0),
            nightly_rates=(
                None
                if room.get("nightly_rates") is None
                else [
                    {"date": date.fromisoformat(row["date"]), "amount": Decimal(str(row["amount"]))}
                    for row in room["nightly_rates"]
                ]
            ),
        )
        for room in payload.get("rooms") or []
    ]
    ota = payload.get("ota") or OTA_LABELS.get(booking.connection.channel_code, "OTA")
    notes = f"{ota} · reserva {booking.external_id}"
    if payload.get("notes"):
        notes += f"\n{payload['notes']}"
    return InboundBooking(
        external_id=booking.external_id,
        status=booking.status,
        guest=dict(payload.get("guest") or {}),
        rooms=rooms,
        currency=payload.get("currency") or "",
        notes=notes,
        raw={**payload, "external_id": booking.external_id, "revision": booking.revision},
        revision_id=f"{booking.pk}:{booking.revision}",
    )


# --- simulated Channex feed ---------------------------------------------------------------------------------


def pending_bookings(connection) -> list[InboundBooking]:
    """Revisions the PMS has not pulled yet (a failed one is offered again, like the Channex feed)."""
    pending = SimOtaBooking.objects.filter(
        connection=connection,
        pms_status__in=[SimOtaBooking.PmsStatus.PENDING, SimOtaBooking.PmsStatus.FAILED],
    ).order_by("updated_at", "pk")
    return [to_inbound(booking) for booking in pending.select_related("connection")]


def _revision(booking: InboundBooking):
    pk, _sep, revision = (booking.revision_id or "").partition(":")
    return pk, int(revision) if revision.isdigit() else None


def acknowledge_booking(connection, booking: InboundBooking) -> None:
    """The PMS applied this revision: mark it imported (a newer revision stays pending)."""
    pk, revision = _revision(booking)
    reservation = (
        ExternalReservationMap.objects.filter(connection=connection, external_id=booking.external_id)
        .select_related("reservation")
        .first()
    )
    message = (
        f"Descargada por el PMS: reserva {reservation.reservation.code}"
        if reservation
        else "Descargada por el PMS"
    )
    SimOtaBooking.objects.filter(connection=connection, pk=pk, revision=revision).update(
        pms_status=SimOtaBooking.PmsStatus.IMPORTED, pms_message=message
    )


def reject_booking(connection, booking: InboundBooking, message: str) -> None:
    """The PMS could not apply this revision: it stays in the feed (failed) with the reason."""
    pk, revision = _revision(booking)
    SimOtaBooking.objects.filter(connection=connection, pk=pk, revision=revision).update(
        pms_status=SimOtaBooking.PmsStatus.FAILED, pms_message=(message or "")[:1000]
    )


# --- what the OTA sees --------------------------------------------------------------------------------------


def _cell(cell) -> dict | None:
    if cell is None:
        return None
    return {
        "date": cell.date.isoformat(),
        "available": cell.available,
        "price": f"{cell.price:.2f}" if cell.price is not None else None,
        "min_los": cell.min_los,
        "max_los": cell.max_los,
        "closed_to_arrival": cell.closed_to_arrival,
        "closed_to_departure": cell.closed_to_departure,
        "stop_sell": cell.stop_sell,
    }


def ota_inventory(connection, start: date, end: date) -> dict:
    """The ARI the OTA holds for `[start, end)`, per mapped channel room and rate (None = no data)."""
    ensure_simulated(connection)
    dates = list(daterange(start, end))
    room_mappings = list(
        connection.room_mappings.filter(room__isnull=True)
        .select_related("room_type")
        .order_by("room_type__sort_order", "room_type__code")
    )
    rate_mappings = list(connection.rate_mappings.select_related("rate_plan").order_by("created_at"))
    cells = SimOtaInventory.objects.filter(
        connection=connection,
        date__gte=start,
        date__lt=end,
        external_room_id__in=[mapping.external_room_id for mapping in room_mappings],
    )
    index = {(cell.external_room_id, cell.external_rate_id, cell.date): cell for cell in cells}
    rooms = []
    for mapping in room_mappings:
        applicable = [item for item in rate_mappings if item.room_type_id in (None, mapping.room_type_id)]
        entries = [(item.external_rate_id, item) for item in applicable] or [("", None)]
        rooms.append(
            {
                "external_room_id": mapping.external_room_id,
                "room_type": _room_type(mapping.room_type),
                "rates": [
                    {
                        "external_rate_id": external_rate_id,
                        "rate_plan": _plan(item.rate_plan) if item is not None else None,
                        "markup_percent": f"{item.markup_percent:.2f}" if item is not None else "0.00",
                        "cells": [
                            _cell(index.get((mapping.external_room_id, external_rate_id, day)))
                            for day in dates
                        ],
                    }
                    for external_rate_id, item in entries
                ],
            }
        )
    last = SimOtaInventory.objects.filter(connection=connection).aggregate(last=Max("updated_at"))["last"]
    return {
        "connection": {
            "id": str(connection.pk),
            "name": connection.name,
            "channel_code": connection.channel_code,
            "ota": OTA_LABELS.get(connection.channel_code, connection.name),
            "delivery": "push" if connection.channel_code in PUSH_DELIVERY else "pull",
        },
        "start": start.isoformat(),
        "end": end.isoformat(),
        "currency": connection.property.currency or "COP",
        "dates": [day.isoformat() for day in dates],
        "rooms": rooms,
        "last_update": last.isoformat() if last else None,
    }


def _room_type(room_type) -> dict:
    return {
        "id": str(room_type.pk),
        "code": room_type.code,
        "name": room_type.name,
        "kind": room_type.kind,
        "color": room_type.color,
    }


def _plan(plan) -> dict | None:
    if plan is None:
        return None
    return {"id": str(plan.pk), "code": plan.code, "name": plan.name}
