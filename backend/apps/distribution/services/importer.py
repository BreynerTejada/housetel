"""Channel bookings → PMS reservations (plan C3 › Entrada).

`import_booking(connection, booking)` is the single entry point for every channel (BookSim/AirSim simulator,
Channex revisions, iCal events). It is idempotent per `(connection, external_id)`: the SHA-256 of the
normalized payload is kept in `ExternalReservationMap.last_payload_hash` and the same payload twice changes
nothing.

- New (or a modification of a booking the PMS never got): `bookings.create_reservation` with `source="ota"`,
  the connection's `channel_code`, `enforce_restrictions=False` (the channel already sold it),
  `allow_overbooking=True` (bookings raises the `overbooking` alert when a unit was missing) and the channel's
  nightly prices.
- Modified: `bookings.modify_stay` per stay (dates, category, plan, occupancy) with `reprice=False`: nights
  the guest keeps keep their price; new nights take the PMS price (the contract has no way to impose channel
  prices on a modification). A change in the number of rooms (or of dorm guests) needs a human.
- Cancelled: `bookings.cancel_reservation(waive_fee=True, source="channel")` (the channel applies its own
  policy).

Failures (unmapped room/rate, a modification without availability…) roll back, are logged, and raise the
critical alert `channel_import_failed` (resolved by the next successful import of that booking). A failed
payload is not remembered, so the next delivery tries again.
"""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.bookings.models import ACTIVE_STAY_STATUSES, Reservation
from apps.bookings.services.availability import availability_by_date
from apps.bookings.services.reservations import cancel_reservation, create_reservation, modify_stay
from apps.bookings.types import AvailabilityError, ReservationRequest, StayRequest
from apps.core import alerts
from apps.core.dates import nights as stay_nights
from apps.core.errors import DomainError
from apps.distribution.errors import MappingError
from apps.distribution.models import ChannelConnection, ExternalReservationMap, SyncLog
from apps.distribution.services.logs import log
from apps.distribution.types import ImportResult, InboundBooking
from apps.guests.types import GuestInput
from apps.inventory.models import Room, RoomType
from apps.rates.models import RatePlan

GUEST_KEYS = ("first_name", "last_name", "email", "phone", "country", "language")
OPEN_STATUSES = (Reservation.Status.TENTATIVE, Reservation.Status.CONFIRMED)
CLOSED_STATUSES = (Reservation.Status.CANCELLED, Reservation.Status.NO_SHOW)
LOG_KINDS = {"created": "booking_new", "modified": "booking_modified", "cancelled": "booking_cancelled"}
LOG_STATUS = {
    "created": SyncLog.Status.SUCCESS,
    "modified": SyncLog.Status.SUCCESS,
    "cancelled": SyncLog.Status.SUCCESS,
    "unchanged": SyncLog.Status.SKIPPED,
    "ignored": SyncLog.Status.SKIPPED,
    "failed": SyncLog.Status.ERROR,
}


@dataclass
class _Unit:
    """One PMS stay a channel room asks for (a dorm room for N guests = N units of one bed)."""

    room_type: RoomType
    rate_plan: RatePlan
    checkin: date
    checkout: date
    adults: int
    children: int


def import_booking(connection, booking: InboundBooking, *, actor=None, quiet_unchanged=False) -> ImportResult:
    """Apply one channel booking (new / modified / cancelled) to the PMS; see the module docstring.

    `quiet_unchanged` skips the log line of a delivery that changed nothing (polled calendars re-send every
    event on every pull)."""
    digest = payload_hash(booking)
    try:
        with transaction.atomic():
            # one import at a time per connection: two deliveries of one booking never both create it
            ChannelConnection.objects.select_for_update().filter(pk=connection.pk).values_list("pk").first()
            result = _apply(connection, booking, digest, actor)
    except DomainError as exc:
        result = ImportResult(action="failed", message=exc.message, code=exc.code)
    if not (quiet_unchanged and result.action == "unchanged"):
        _record(connection, booking, result)
    return result


def payload_hash(booking: InboundBooking) -> str:
    """SHA-256 of what matters in a booking (status, guest, rooms, prices, notes); ids of revisions and the
    raw payload do not count."""
    canonical = {
        "status": booking.status,
        "guest": {key: str(booking.guest.get(key) or "") for key in GUEST_KEYS},
        "rooms": [
            {
                "room": room.external_room_id,
                "rate": room.external_rate_id,
                "room_type": str(room.room_type_id or ""),
                "rate_plan": str(room.rate_plan_id or ""),
                "unit": str(room.room_id or ""),
                "checkin": str(room.checkin),
                "checkout": str(room.checkout),
                "adults": int(room.adults or 0),
                "children": int(room.children or 0),
                "nightly": (
                    None
                    if room.nightly_rates is None
                    else [[str(item["date"]), str(item["amount"])] for item in room.nightly_rates]
                ),
            }
            for room in booking.rooms
        ],
        "notes": booking.notes,
        "special_requests": booking.special_requests,
        "eta": str(booking.eta or ""),
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()


def booking_payload(booking: InboundBooking) -> dict:
    """JSON-safe view of the booking for logs and the reservation map."""
    return {
        "external_id": booking.external_id,
        "status": booking.status,
        "guest": {key: booking.guest.get(key, "") for key in GUEST_KEYS if booking.guest.get(key)},
        "rooms": [
            {
                "external_room_id": room.external_room_id,
                "external_rate_id": room.external_rate_id,
                "checkin": str(room.checkin),
                "checkout": str(room.checkout),
                "adults": room.adults,
                "children": room.children,
                "nightly_rates": (
                    None
                    if room.nightly_rates is None
                    else [{"date": str(n["date"]), "amount": str(n["amount"])} for n in room.nightly_rates]
                ),
            }
            for room in booking.rooms
        ],
        "notes": booking.notes,
        "special_requests": booking.special_requests,
    }


# --- apply --------------------------------------------------------------------------------------------------


def _apply(connection, booking, digest, actor) -> ImportResult:
    mapping = (
        ExternalReservationMap.objects.select_related("reservation")
        .filter(connection=connection, external_id=booking.external_id)
        .first()
    )
    if mapping is not None and mapping.last_payload_hash == digest:
        return ImportResult("unchanged", mapping.reservation, "Sin cambios: la reserva ya estaba al día")
    if booking.status == "cancelled":
        return _cancel(connection, booking, mapping, digest, actor)
    if mapping is None or mapping.reservation.status in CLOSED_STATUSES:
        reservation, overbooked = _create(connection, booking, actor)
        if mapping is None:
            mapping = ExternalReservationMap(connection=connection, external_id=booking.external_id)
        mapping.reservation = reservation
        _remember(mapping, booking, digest)
        message = f"Reserva {reservation.code} creada"
        if overbooked:
            message += " con sobreventa: no quedaban unidades libres"
        return ImportResult("created", reservation, message, overbooked=overbooked)
    _modify(connection, mapping.reservation, booking, actor)
    _remember(mapping, booking, digest)
    return ImportResult("modified", mapping.reservation, f"Reserva {mapping.reservation.code} modificada")


def _remember(mapping, booking, digest) -> None:
    mapping.last_payload_hash = digest
    mapping.last_status = booking.status
    mapping.last_payload = booking_payload(booking)
    if booking.room_mapping_id:
        mapping.room_mapping_id = booking.room_mapping_id
    mapping.save()


def _cancel(connection, booking, mapping, digest, actor) -> ImportResult:
    if mapping is None:
        return ImportResult("ignored", None, "Cancelación de una reserva que nunca llegó al PMS")
    reservation = mapping.reservation
    if reservation.status in CLOSED_STATUSES:
        _remember(mapping, booking, digest)
        return ImportResult("unchanged", reservation, f"La reserva {reservation.code} ya estaba cancelada")
    if reservation.status not in OPEN_STATUSES:
        raise DomainError(
            f"La reserva {reservation.code} ya está en casa o finalizada: acuerda la cancelación con el "
            "canal",
            code="cannot_cancel",
        )
    cancel_reservation(
        reservation, reason=f"Cancelada en {connection.name}", waive_fee=True, actor=actor, source="channel"
    )
    _remember(mapping, booking, digest)
    return ImportResult("cancelled", reservation, f"Reserva {reservation.code} cancelada")


def _create(connection, booking, actor) -> tuple[Reservation, bool]:
    prop = connection.property
    if booking.currency and booking.currency.upper() != (prop.currency or "COP").upper():
        raise DomainError(
            f"La reserva viene en {booking.currency} y el hotel cobra en {prop.currency}: revisa la moneda "
            "de la propiedad en el canal",
            code="currency_mismatch",
        )
    requests = [(room, *_resolve(connection, room)) for room in booking.rooms]
    if not requests:
        raise DomainError("La reserva del canal no trae habitaciones", code="no_rooms")
    overbooked = _short_of_units(prop, requests)

    def request(with_rooms: bool) -> ReservationRequest:
        return ReservationRequest(
            property=prop,
            booker=_guest(booking.guest),
            stays=[
                StayRequest(
                    room_type_id=room_type.pk,
                    rate_plan_id=plan.pk,
                    checkin=room.checkin,
                    checkout=room.checkout,
                    adults=int(room.adults or 0),
                    children=int(room.children or 0),
                    room_id=unit.pk if with_rooms and unit is not None else None,
                    nightly_rates=room.nightly_rates,
                )
                for room, room_type, plan, unit in requests
            ],
            source=Reservation.Source.OTA,
            channel_code=connection.channel_code,
            external_id=booking.external_id,
            external_payload=json.loads(json.dumps(booking.raw or booking_payload(booking), default=str)),
            notes=booking.notes,
            special_requests=booking.special_requests,
            language=_language(booking.guest),
            eta=booking.eta,
            status=Reservation.Status.CONFIRMED,
            allow_overbooking=True,
            enforce_restrictions=False,
            guarantee=Reservation.Guarantee.OTA,
        )

    wants_rooms = any(unit is not None for *_ignored, unit in requests)
    try:
        with transaction.atomic():
            reservation = create_reservation(request(True), actor=actor, source_label=connection.name)
    except AvailabilityError:
        if not wants_rooms:
            raise
        # the calendar's room is taken in the PMS: keep the booking, unassigned, for the front desk to place
        reservation = create_reservation(request(False), actor=actor, source_label=connection.name)
    return reservation, overbooked


def _modify(connection, reservation, booking, actor) -> None:
    stays = list(
        reservation.stays.filter(status__in=ACTIVE_STAY_STATUSES)
        .select_related("room_type", "rate_plan")
        .order_by("created_at", "pk")
    )
    units = _units(connection, booking)
    if len(units) != len(stays):
        raise DomainError(
            "La modificación cambia el número de habitaciones o de huéspedes de dormitorio: aplícala a mano",
            code="manual_modification_required",
        )
    for stay, unit in zip(stays, units, strict=True):
        modify_stay(
            stay,
            checkin=unit.checkin,
            checkout=unit.checkout,
            room_type=unit.room_type if unit.room_type.pk != stay.room_type_id else None,
            rate_plan=unit.rate_plan if unit.rate_plan.pk != stay.rate_plan_id else None,
            adults=unit.adults,
            children=unit.children,
            reprice=False,
            actor=actor,
        )


def _units(connection, booking) -> list[_Unit]:
    units = []
    for room in booking.rooms:
        room_type, plan, _unit = _resolve(connection, room)
        adults, children = int(room.adults or 0), int(room.children or 0)
        if room_type.kind == RoomType.Kind.DORM:
            units += [_Unit(room_type, plan, room.checkin, room.checkout, 1, 0) for _ in range(adults)]
            units += [_Unit(room_type, plan, room.checkin, room.checkout, 0, 1) for _ in range(children)]
        else:
            units.append(_Unit(room_type, plan, room.checkin, room.checkout, adults, children))
    return units


# --- mapping ------------------------------------------------------------------------------------------------


def _resolve(connection, room) -> tuple[RoomType, RatePlan, Room | None]:
    """(category, plan, room or None) of a channel room, from its ids or through the connection mappings."""
    prop = connection.property
    if not room.checkin or not room.checkout or room.checkout <= room.checkin:
        raise DomainError("Fechas inválidas en la reserva del canal", code="invalid_dates")
    if room.room_type_id:
        room_type = RoomType.objects.filter(pk=room.room_type_id, property=prop).first()
    else:
        mapping = (
            connection.room_mappings.select_related("room_type")
            .filter(external_room_id=room.external_room_id, room__isnull=True)
            .first()
        )
        room_type = mapping.room_type if mapping is not None else None
    if room_type is None:
        raise MappingError(
            f"La habitación «{room.external_room_id}» del canal no está mapeada a ninguna categoría",
            code="unmapped_room",
        )
    unit = Room.objects.filter(pk=room.room_id, room_type=room_type).first() if room.room_id else None
    return room_type, _plan(connection, room, room_type), unit


def _plan(connection, room, room_type) -> RatePlan:
    plans = RatePlan.objects.filter(property=connection.property, is_active=True, room_types=room_type)
    if room.rate_plan_id:
        plan = plans.filter(pk=room.rate_plan_id).first()
        if plan is not None:
            return plan
    # mappings whose plan was deleted still identify a known channel rate: its bookings fall back below
    mappings = connection.rate_mappings.select_related("rate_plan")
    candidates = [m for m in mappings if m.room_type_id in (None, room_type.pk)]
    if room.external_rate_id:
        matching = [m for m in candidates if m.external_rate_id == room.external_rate_id]
        if not matching:
            raise MappingError(
                f"La tarifa «{room.external_rate_id}» del canal no está mapeada a ningún plan",
                code="unmapped_rate",
            )
        candidates = sorted(matching, key=lambda m: m.room_type_id is None)  # the category's own first
    for mapping in candidates:
        if mapping.rate_plan_id and plans.filter(pk=mapping.rate_plan_id).exists():
            return mapping.rate_plan
    # a deleted plan, a mapped plan that stopped selling this category, or no rate at all (iCal): the channel
    # already sold it at its own nightly prices, so any plan that sells the category takes the booking
    fallback = plans.order_by("kind", "sort_order", "code").first()
    if fallback is None:
        raise MappingError(
            f"Ningún plan tarifario activo vende la categoría {room_type.code}", code="no_rate_plan"
        )
    return fallback


def _short_of_units(prop, requests) -> bool:
    """Would the booking take more units than the PMS has free on some night?"""
    needed: Counter = Counter()
    for room, room_type, _plan, _unit in requests:
        units = int(room.adults or 0) + int(room.children or 0) if room_type.kind == RoomType.Kind.DORM else 1
        for night in stay_nights(room.checkin, room.checkout):
            needed[(room_type.pk, night)] += units
    start = min(night for _type, night in needed)
    end = max(night for _type, night in needed)
    free = availability_by_date(
        property=prop,
        start=start,
        end=end + timedelta(days=1),
        room_type_ids=list({type_id for type_id, _night in needed}),
    )
    return any(free.get(type_id, {}).get(night, 0) < units for (type_id, night), units in needed.items())


def _guest(data: dict) -> GuestInput:
    country = str(data.get("country") or "").strip().upper()[:2]
    first = str(data.get("first_name") or "").strip()[:100] or "Huésped"
    return GuestInput(
        first_name=first,
        last_name=str(data.get("last_name") or "").strip()[:100],
        email=str(data.get("email") or "").strip()[:254],
        phone=str(data.get("phone") or "").strip()[:32],
        nationality=country,
        country_of_residence=country,
        language=_language(data),
    )


def _language(data: dict) -> str:
    language = str(data.get("language") or "").lower()[:2]
    if language in ("es", "en"):
        return language
    country = str(data.get("country") or "").upper()
    return "en" if country and country != "CO" else "es"


# --- record -------------------------------------------------------------------------------------------------


def _record(connection, booking, result) -> None:
    status = LOG_STATUS[result.action]
    if result.overbooked:
        status = SyncLog.Status.WARNING
    message = result.message
    if result.action == "failed":
        message = f"No se pudo procesar la reserva {booking.external_id}: {result.message}"
    log(
        connection,
        SyncLog.Direction.IN,
        LOG_KINDS.get(result.action, f"booking_{booking.status}"),
        status,
        message,
        payload={**booking_payload(booking), "action": result.action, "code": result.code},
        external_id=booking.external_id,
        reservation=result.reservation,
    )
    dedupe_key = f"distribution:import:{connection.pk}:{booking.external_id}"
    if result.action == "failed":
        alerts.raise_alert(
            property=connection.property,
            kind="channel_import_failed",
            severity="critical",
            title=f"Reserva de {connection.name} sin procesar: {booking.external_id}",
            message=(
                f"{result.message}. La reserva existe en el canal pero no en el PMS: revísala en el registro "
                "de sincronización."
            ),
            link="/app/channels",
            dedupe_key=dedupe_key,
            data={
                "connection_id": str(connection.pk),
                "connection": connection.name,
                "external_id": booking.external_id,
                "code": result.code,
                "error": result.message,
            },
            source="distribution",
        )
    else:
        alerts.resolve_alert(connection.property, dedupe_key)
    ChannelConnection.objects.filter(pk=connection.pk).update(last_sync_at=timezone.now())
