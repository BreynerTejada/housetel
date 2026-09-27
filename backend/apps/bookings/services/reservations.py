"""Reservation lifecycle — signatures fixed in Phase A (spec §4.2), implemented by B2b (plan B2b).

Every function runs atomically, audits, and emits its domain signal with `core.signals.send_on_commit`.
Errors: `apps.bookings.types` (AvailabilityError 409, RestrictionError 400, InvalidStateError 409,
RoomNotReadyError 409, BalanceDueError 409, BookingError 400 with a specific `code`).

Lock order (always the same, so concurrent operations queue instead of deadlocking): Reservation row → its
Stay rows → InventoryDay rows in (room_type_id, date) order. Inventory is adjusted before stays are written.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from decimal import Decimal
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import ACTIVE_STAY_STATUSES, Reservation, ReservationGroup, Stay
from apps.bookings.services.assignment import (
    GAP_WINDOW_DAYS,
    best_unit,
    free_units,
    load_units,
    preferred_zone,
    rank,
    room_connections,
)
from apps.bookings.services.charges import post_room_charges
from apps.bookings.services.inventory import ORIGIN, adjust_inventory, stay_units, unit_type_id
from apps.bookings.services.policies import cancellation_fee, no_show_fee, policy_snapshot
from apps.bookings.services.pricing import (
    QUOTE_WARNINGS,
    PricedStay,
    entries_total,
    lodging_tax,
    money_str,
    night_entry,
    price_stay,
    split_amount,
    tax_exempt,
)
from apps.bookings.services.rooms import READY_STATUSES, free_bed, is_blocked, is_occupied
from apps.bookings.services.totals import refresh_reservation
from apps.bookings.types import (
    AssignmentReport,
    AvailabilityError,
    BalanceDueError,
    BookingError,
    InvalidStateError,
    ReservationRequest,
    RestrictionError,
    RoomNotReadyError,
)
from apps.core import alerts, audit, signals
from apps.core.dates import nights as stay_nights
from apps.core.models import AuditEvent
from apps.core.money import D, quantize
from apps.guests.models import Guest
from apps.guests.types import GuestInput
from apps.inventory.models import Bed, CustomFieldDefinition, Room, RoomType
from apps.rates.models import RatePlan

EXCLUSION_VIOLATION = "23P01"
UNIQUE_VIOLATION = "23505"
CODE_ATTEMPTS = 8
CREATABLE_STATUSES = ("confirmed", "tentative")
# Reservation.source → AuditEvent.source when the caller gives no `source_label`
AUDIT_SOURCE_BY_BOOKING_SOURCE = {
    "ota": "channel",
    "marketplace": "guest",
    "booking_engine": "guest",
    "api": "api",
}


def _user(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


# --- create -------------------------------------------------------------------------------------------------


@dataclass
class _StayPlan:
    """One Stay to create (a dorm StayRequest for N guests becomes N one-bed plans)."""

    room_type: RoomType
    rate_plan: RatePlan
    checkin: date
    checkout: date
    adults: int
    children: int
    children_ages: list = field(default_factory=list)
    room: Room | None = None
    bed: Bed | None = None
    locked_room: bool = False
    occupants: list = field(default_factory=list)
    nightly_prices: dict | None = None  # {date: price} imposed by a channel

    @property
    def is_dorm(self) -> bool:
        return self.room_type.kind == RoomType.Kind.DORM


def create_reservation(req: ReservationRequest, *, actor=None, source_label=None) -> Reservation:
    """Create a reservation: upsert booker, lock InventoryDay, validate capacity,
    availability and restrictions, quote (or use channel `nightly_rates`), create Reservation + Stays +
    folio, `reservation_created` and `inventory_changed`. Raises AvailabilityError (409) /
    RestrictionError (400)."""
    from apps.finance import services as finance

    prop = req.property
    _validate_request(req)
    audit_source, actor_label = _audit_source(req.source, source_label)
    currency = prop.currency or "COP"
    with transaction.atomic():
        booker = _resolve_guest(prop, req.booker, actor)
        group = _resolve_group(prop, req.group_id)
        custom_values = _validate_custom_values(prop, req.custom_values)
        plans = [plan for stay_req in req.stays for plan in _plan_stay(prop, stay_req, currency)]

        units: Counter = Counter()
        for plan in plans:
            for night in stay_nights(plan.checkin, plan.checkout):
                units[(plan.room_type.pk, night)] += 1
        shortfalls = adjust_inventory(prop, units, allow_overbooking=req.allow_overbooking)

        priced = [_price_plan(prop, plan, req, booker) for plan in plans]
        promo_applied = next((item.quote.promo_applied for item in priced if item.quote.promo_applied), "")

        now = timezone.now()
        reservation = Reservation(
            property=prop,
            status=req.status,
            source=req.source,
            channel_code=req.channel_code or "",
            external_id=req.external_id or "",
            external_payload=req.external_payload or {},
            booker=booker,
            group=group,
            checkin_date=min(plan.checkin for plan in plans),
            checkout_date=max(plan.checkout for plan in plans),
            adults=sum(plan.adults for plan in plans),
            children=sum(plan.children for plan in plans),
            currency=currency,
            total_amount=sum((item.total for item in priced), Decimal("0")),
            language=req.language or "es",
            eta=req.eta,
            special_requests=req.special_requests or "",
            notes=req.notes or "",
            promo_code=promo_applied or "",
            guarantee=req.guarantee,
            cancellation_policy_snapshot=policy_snapshot(plans[0].rate_plan),
            created_by=_user(actor),
            custom_values=custom_values,
            hold_expires_at=(
                now + timedelta(minutes=req.hold_minutes)
                if req.status == Reservation.Status.TENTATIVE and req.hold_minutes and req.hold_minutes > 0
                else None
            ),
        )
        _save_with_unique_code(reservation)
        for plan, pricing in zip(plans, priced, strict=True):
            stay = Stay.objects.create(
                reservation=reservation,
                room_type=plan.room_type,
                rate_plan=plan.rate_plan,
                checkin_date=plan.checkin,
                checkout_date=plan.checkout,
                adults=plan.adults,
                children=plan.children,
                children_ages=plan.children_ages,
                nightly_rates=pricing.entries,
                total_amount=pricing.total,
                status=req.status,
                locked_room=plan.locked_room,
            )
            if plan.occupants:
                stay.occupants.set([_resolve_guest(prop, occupant, actor) for occupant in plan.occupants])
            if plan.room is not None:
                _assign(stay, plan.room, bed=plan.bed, actor=actor, force=False, source=audit_source)

        finance.get_or_create_folio(reservation)
        if shortfalls:
            _raise_overbooking_alert(reservation, shortfalls)
        audit.record(
            action="bookings.reservation_created",
            target=reservation,
            summary=(
                f"Creó la reserva {reservation.code} "
                f"({reservation.checkin_date} → {reservation.checkout_date})"
            ),
            actor=actor,
            source=audit_source,
            actor_label=actor_label if _user(actor) is None else None,
            property=prop,
            changes={
                "status": [None, reservation.status],
                "total_amount": [None, str(reservation.total_amount)],
                "source": [None, reservation.source],
            },
        )
        signals.send_on_commit(signals.reservation_created, reservation=reservation)
        _emit_inventory_changed(
            prop,
            [plan.room_type.pk for plan in plans],
            reservation.checkin_date,
            reservation.checkout_date,
        )
    return reservation


def _validate_request(req) -> None:
    if not req.stays:
        raise BookingError("La reserva debe tener al menos una estadía", code="no_stays")
    if req.status not in CREATABLE_STATUSES:
        raise BookingError(f"Estado inicial inválido: {req.status}", code="invalid_status")
    if req.source not in Reservation.Source.values:
        raise BookingError(f"Origen inválido: {req.source}", code="invalid_source")
    if req.guarantee not in Reservation.Guarantee.values:
        raise BookingError(f"Garantía inválida: {req.guarantee}", code="invalid_guarantee")


def _audit_source(booking_source, source_label) -> tuple[str, str | None]:
    """(`AuditEvent.source`, actor label). `source_label` is an audit source (user, automation, ai, channel,
    guest, system, api) or, otherwise, the label shown as the actor (e.g. "BookSim")."""
    if source_label in AuditEvent.Source.values:
        return source_label, None
    return AUDIT_SOURCE_BY_BOOKING_SOURCE.get(booking_source, "user"), source_label or None


def _resolve_guest(prop, value, actor) -> Guest:
    """A Guest of the property's organization (merged guests resolve to their primary) or a GuestInput to
    upsert."""
    from apps.guests.services import upsert_guest

    if isinstance(value, Guest):
        guest = value
        while guest.merged_into_id:
            guest = guest.merged_into
        if guest.organization_id != prop.organization_id:
            raise BookingError("El huésped pertenece a otra organización", code="invalid_guest")
        return guest
    if isinstance(value, GuestInput):
        return upsert_guest(prop.organization, value, actor=actor)
    raise BookingError("Datos de huésped inválidos", code="invalid_guest")


def _resolve_group(prop, group_id):
    if not group_id:
        return None
    group = ReservationGroup.objects.filter(pk=group_id, property=prop).first()
    if group is None:
        raise BookingError("El grupo no existe en esta propiedad", code="invalid_group")
    return group


def _validate_custom_values(prop, values) -> dict:
    from apps.inventory.services import validate_custom_values

    definitions = CustomFieldDefinition.objects.filter(
        Q(property__isnull=True) | Q(property=prop), organization=prop.organization, applies_to="reservation"
    )
    if not values and not definitions.exists():
        return {}
    return validate_custom_values(list(definitions), values or {})


def _room_type(prop, room_type_id) -> RoomType:
    room_type = RoomType.objects.filter(pk=room_type_id, property=prop, is_active=True).first()
    if room_type is None:
        raise BookingError(
            "La categoría no existe o no está activa en esta propiedad", code="invalid_room_type"
        )
    return room_type


def _rate_plan(prop, rate_plan_id, room_type) -> RatePlan:
    plan = (
        RatePlan.objects.select_related("parent", "cancellation_policy", "parent__cancellation_policy")
        .filter(pk=rate_plan_id, property=prop, is_active=True)
        .first()
    )
    if plan is None or not plan.room_types.filter(pk=room_type.pk).exists():
        raise BookingError("El plan tarifario no aplica a esta categoría", code="invalid_rate_plan")
    return plan


def _validate_dates(checkin, checkout) -> None:
    if not checkin or not checkout or checkout <= checkin:
        raise BookingError("La salida debe ser posterior a la llegada", code="invalid_dates")


def _check_capacity(room_type, adults, children) -> None:
    if room_type.kind == RoomType.Kind.DORM:
        if adults + children < 1:
            raise BookingError("Indica al menos un huésped", code="capacity_exceeded")
        if children and not room_type.max_children:
            raise BookingError("Este dormitorio no admite niños", code="capacity_exceeded")
        return
    if adults < 1:
        raise BookingError("Cada habitación necesita al menos un adulto", code="capacity_exceeded")
    if adults > room_type.max_adults or children > room_type.max_children:
        raise BookingError(
            f"La categoría admite máximo {room_type.max_adults} adultos y {room_type.max_children} niños",
            code="capacity_exceeded",
        )
    if adults + children > room_type.max_occupancy:
        raise BookingError(
            f"La categoría admite máximo {room_type.max_occupancy} huéspedes", code="capacity_exceeded"
        )


def _parse_nightly_rates(raw, checkin, checkout, currency) -> dict:
    nights = stay_nights(checkin, checkout)
    prices = {}
    try:
        for item in raw:
            day = item["date"] if isinstance(item["date"], date) else date.fromisoformat(str(item["date"]))
            amount = quantize(item["amount"], currency)
            if day in prices or amount < 0:
                raise ValueError
            prices[day] = amount
    except (KeyError, TypeError, ValueError, ArithmeticError):
        raise BookingError("Precios por noche inválidos", code="invalid_nightly_rates") from None
    if set(prices) != set(nights):
        raise BookingError(
            "Los precios por noche deben cubrir exactamente las noches", code="invalid_nightly_rates"
        )
    return prices


def _plan_stay(prop, stay_req, currency) -> list[_StayPlan]:
    room_type = _room_type(prop, stay_req.room_type_id)
    rate_plan = _rate_plan(prop, stay_req.rate_plan_id, room_type)
    _validate_dates(stay_req.checkin, stay_req.checkout)
    adults, children = int(stay_req.adults or 0), int(stay_req.children or 0)
    ages = [int(age) for age in (stay_req.children_ages or [])]
    if ages and len(ages) != children:
        raise BookingError("Indica la edad de cada niño", code="invalid_children_ages")
    _check_capacity(room_type, adults, children)
    prices = (
        _parse_nightly_rates(stay_req.nightly_rates, stay_req.checkin, stay_req.checkout, currency)
        if stay_req.nightly_rates is not None
        else None
    )
    room, bed = _requested_unit(prop, room_type, stay_req.room_id, stay_req.bed_id)
    common = {
        "room_type": room_type,
        "rate_plan": rate_plan,
        "checkin": stay_req.checkin,
        "checkout": stay_req.checkout,
        "room": room,
        "bed": bed,
        "locked_room": bool(stay_req.locked_room),
    }
    occupants = list(stay_req.occupants or [])
    if room_type.kind != RoomType.Kind.DORM:
        return [
            _StayPlan(
                **common,
                adults=adults,
                children=children,
                children_ages=ages,
                occupants=occupants,
                nightly_prices=prices,
            )
        ]
    persons = adults + children
    if bed is not None and persons > 1:
        raise BookingError("Una cama es para un solo huésped", code="capacity_exceeded")
    shares = {day: split_amount(price, persons, currency) for day, price in (prices or {}).items()}
    plans = []
    for index in range(persons):
        is_adult = index < adults
        child_index = index - adults
        plans.append(
            _StayPlan(
                **common,
                adults=1 if is_adult else 0,
                children=0 if is_adult else 1,
                children_ages=[] if is_adult or not ages else [ages[child_index]],
                occupants=occupants[index : index + 1],
                nightly_prices={day: values[index] for day, values in shares.items()} if prices else None,
            )
        )
    return plans


def _requested_unit(prop, room_type, room_id, bed_id):
    """Validate the room/bed asked for at creation (same category; a bed implies its room)."""
    room = bed = None
    if bed_id:
        bed = Bed.objects.select_related("room").filter(pk=bed_id, room__property=prop).first()
        if bed is None or (room_id and str(bed.room_id) != str(room_id)):
            raise BookingError("La cama no existe en esta habitación", code="invalid_bed")
        room = bed.room
    elif room_id:
        room = Room.objects.filter(pk=room_id, property=prop).first()
        if room is None:
            raise BookingError("La habitación no existe en esta propiedad", code="invalid_room")
    if room is not None and room.room_type_id != room_type.pk:
        raise BookingError("La habitación es de otra categoría", code="category_mismatch")
    return room, bed


def _price_plan(prop, plan: _StayPlan, req, booker) -> PricedStay:
    pricing = price_stay(
        property=prop,
        room_type=plan.room_type,
        rate_plan=plan.rate_plan,
        checkin=plan.checkin,
        checkout=plan.checkout,
        adults=1 if plan.is_dorm else plan.adults,
        children=0 if plan.is_dorm else plan.children,
        children_ages=None if plan.is_dorm else plan.children_ages,
        promo_code=req.promo_code,
        foreign_non_resident=booker.is_foreign_non_resident,
        nightly_prices=plan.nightly_prices,
    )
    if req.enforce_restrictions:
        violations = pricing.quote.violations
        blocking = [item for item in violations if item not in QUOTE_WARNINGS]
        if not pricing.quote.restrictions_ok:
            raise RestrictionError(
                "La estadía no cumple las restricciones de la tarifa", violations=blocking or list(violations)
            )
        if "no_rate" in violations and plan.nightly_prices is None:
            raise BookingError("La categoría no tiene precio configurado para esas noches", code="no_rate")
        if "promo_invalid" in violations:
            raise BookingError("El código promocional no es válido para esta reserva", code="promo_invalid")
    return pricing


def _save_with_unique_code(reservation) -> None:
    """Insert the reservation; a generated code that collides is regenerated (a few times)."""
    for _attempt in range(CODE_ATTEMPTS):
        try:
            with transaction.atomic():
                reservation.save()
            return
        except IntegrityError as exc:
            if (
                _sqlstate(exc) != UNIQUE_VIOLATION
                or not Reservation.objects.filter(code=reservation.code).exists()
            ):
                raise
            reservation.code = ""
    raise BookingError("No se pudo generar un código de reserva único", code="code_generation_failed")


def _sqlstate(exc) -> str | None:
    return getattr(exc.__cause__, "sqlstate", None)


def _raise_overbooking_alert(reservation, shortfalls) -> None:
    alerts.raise_alert(
        property=reservation.property,
        kind="overbooking",
        severity="critical",
        title=f"Sobreventa: la reserva {reservation.code} excede la disponibilidad",
        message=(
            f"La reserva {reservation.code} se aceptó sin unidades libres en "
            f"{len(shortfalls)} noche(s). Reubica o reasigna antes de la llegada."
        ),
        link=f"/app/reservations/{reservation.pk}",
        dedupe_key=f"bookings:overbooking:{reservation.pk}",
        data={"reservation_id": str(reservation.pk), "code": reservation.code, "shortfalls": shortfalls},
        source="system",
    )


def _emit_inventory_changed(prop, room_type_ids, start, end) -> None:
    signals.send_on_commit(
        signals.inventory_changed,
        property=prop,
        room_type_ids=list(dict.fromkeys(room_type_ids)),
        start=start,
        end=end,
        origin=ORIGIN,
    )


# --- room assignment --------------------------------------------------------------------------------


def assign_room(stay, room, *, bed=None, actor=None, force=False) -> Stay:
    """Assign a room/bed. Overlap → AvailabilityError. Reversible audit; `room_assigned`.

    The room must be active, of this property and of the stay's category (another category needs `force`:
    an upgrade/downgrade that keeps the booked category and price but moves the inventory unit, so the target
    category must have a unit left). Dorms: `bed` or the first free bed of the room. Blocked → 409
    `room_blocked`; occupied (database exclusion constraint) → 409 `no_availability`. Moving an in-house guest
    leaves the old room dirty (`set_housekeeping_status(source="automation")`)."""
    return _assign(stay, room, bed=bed, actor=actor, force=force, source="user" if _user(actor) else "system")


def unassign_room(stay, *, actor=None) -> Stay:
    """Take the room away from a stay that has not checked in (reversible audit; `room_assigned` with the old
    room). An upgraded stay gives its unit back to the booked category."""
    return _unassign(stay, actor=actor, source="user" if _user(actor) else "system")


def undo_room_change(event) -> None:
    """Undo handler of `bookings.room_assigned` / `bookings.room_unassigned` (core.audit.undo)."""
    data = event.undo_data or {}
    stay = Stay.objects.get(pk=data["stay_id"])
    if data.get("old_room_id"):
        room = Room.objects.get(pk=data["old_room_id"])
        bed = Bed.objects.get(pk=data["old_bed_id"]) if data.get("old_bed_id") else None
        _assign(stay, room, bed=bed, force=True, source=event.source or "user", record=False)
    else:
        _unassign(stay, source=event.source or "user", record=False)


def _lock_stay(stay) -> Stay:
    """Lock the reservation row, then the stay row (the global lock order) and return a fresh stay."""
    Reservation.objects.select_for_update().filter(pk=stay.reservation_id).values_list(
        "pk", flat=True
    ).first()
    return (
        Stay.objects.select_for_update(of=("self",))
        .select_related("reservation__property", "reservation__booker", "room_type", "room__room_type", "bed")
        .get(pk=stay.pk)
    )


class _NoLongerWaiting(Exception):
    """Auto-assignment: the stay got a room, checked in, was locked or cancelled after the run listed it."""


def _assign(
    stay, room, *, bed=None, actor=None, force=False, source="user", record=True, only_waiting=False
) -> Stay:
    """`only_waiting` (auto-assignment): re-check under the lock that the stay still waits for a room
    (pending, unassigned, not locked) and raise `_NoLongerWaiting` otherwise, so a stay changed by someone
    else after the run listed it is never moved."""
    with transaction.atomic():
        stay = _lock_stay(stay)
        if only_waiting and (
            stay.status not in (Stay.Status.TENTATIVE, Stay.Status.CONFIRMED)
            or stay.room_id is not None
            or stay.locked_room
        ):
            raise _NoLongerWaiting
        prop = stay.reservation.property
        room = Room.objects.select_related("room_type").get(pk=room.pk)
        if stay.status not in ACTIVE_STAY_STATUSES:
            raise InvalidStateError("Solo se asignan habitaciones a estadías activas")
        if room.property_id != prop.pk or not room.is_active:
            raise BookingError("La habitación no está disponible en esta propiedad", code="invalid_room")
        if room.room_type.kind != stay.room_type.kind:
            raise BookingError(
                "Las camas de dormitorio y las habitaciones privadas no se mezclan", code="invalid_room"
            )
        if room.room_type_id != stay.room_type_id and not force:
            raise BookingError(
                "La habitación es de otra categoría; confirma el cambio de categoría",
                code="category_mismatch",
            )
        if room.room_type.kind == RoomType.Kind.DORM:
            if bed is None:
                bed = free_bed(stay, room)
            else:
                bed = Bed.objects.filter(pk=bed.pk, room=room, is_active=True).first()
                if bed is None:
                    raise BookingError("La cama no está disponible en esta habitación", code="invalid_bed")
        elif bed is not None:
            raise BookingError("Las habitaciones privadas no tienen camas", code="invalid_bed")
        if stay.room_id == room.pk and stay.bed_id == (bed.pk if bed else None):
            return stay
        if is_blocked(room, bed, stay.checkin_date, stay.checkout_date):
            raise AvailabilityError("La habitación está bloqueada en esas fechas", code="room_blocked")
        if is_occupied(stay, room, bed):
            raise AvailabilityError("La habitación ya está ocupada en esas fechas")

        old_room, old_bed = stay.room, stay.bed
        old_type = unit_type_id(stay)
        if old_type != room.room_type_id:
            adjust_inventory(prop, _move_units(stay, old_type, room.room_type_id))
        stay.room, stay.bed = room, bed
        _save_room(stay)
        if record:
            upgrade = (
                f" · cambio de categoría {stay.room_type.code} → {room.room_type.code}"
                if room.room_type_id != stay.room_type_id
                else ""
            )
            audit.record(
                action="bookings.room_assigned",
                target=stay,
                summary=f"Asignó {_unit_label(room, bed)} a {stay.reservation.code}{upgrade}",
                actor=actor,
                source=source,
                property=prop,
                reversible=True,
                undo_data=_undo_data(stay, old_room, old_bed),
                changes=_room_changes(old_room, old_bed, room, bed),
            )
        signals.send_on_commit(signals.room_assigned, stay=stay, old_room=old_room)
        if old_type != room.room_type_id:
            _emit_inventory_changed(
                prop, [old_type, room.room_type_id], stay.checkin_date, stay.checkout_date
            )
        if stay.status == Stay.Status.CHECKED_IN and old_room is not None and old_room.pk != room.pk:
            _room_left(old_room, actor)
    return stay


def _room_left(room, actor) -> None:
    """An in-house guest moved out of `room`: it needs cleaning, as after a check-out (a dorm room too)."""
    from apps.inventory.services import set_housekeeping_status

    set_housekeeping_status(room, "dirty", actor=actor, source="automation")


def _unassign(stay, *, actor=None, source="user", record=True) -> Stay:
    with transaction.atomic():
        stay = _lock_stay(stay)
        prop = stay.reservation.property
        if stay.status not in (Stay.Status.TENTATIVE, Stay.Status.CONFIRMED):
            raise InvalidStateError("Un huésped en casa no puede quedar sin habitación; muévelo a otra")
        if stay.room_id is None:
            return stay
        old_room, old_bed = stay.room, stay.bed
        old_type = unit_type_id(stay)
        if old_type != stay.room_type_id:
            adjust_inventory(prop, _move_units(stay, old_type, stay.room_type_id))
        stay.room = stay.bed = None
        _save_room(stay)
        if record:
            audit.record(
                action="bookings.room_unassigned",
                target=stay,
                summary=f"Quitó {_unit_label(old_room, old_bed)} de {stay.reservation.code}",
                actor=actor,
                source=source,
                property=prop,
                reversible=True,
                undo_data=_undo_data(stay, old_room, old_bed),
                changes=_room_changes(old_room, old_bed, None, None),
            )
        signals.send_on_commit(signals.room_assigned, stay=stay, old_room=old_room)
        if old_type != stay.room_type_id:
            _emit_inventory_changed(
                prop, [old_type, stay.room_type_id], stay.checkin_date, stay.checkout_date
            )
    return stay


def _save_room(stay) -> None:
    try:
        with transaction.atomic():
            stay.save(update_fields=["room", "bed", "updated_at"])
    except IntegrityError as exc:
        if _sqlstate(exc) == EXCLUSION_VIOLATION:
            raise AvailabilityError("La habitación ya está ocupada en esas fechas") from None
        raise


def _move_units(stay, from_type, to_type) -> Counter:
    moves: Counter = Counter()
    for night in stay_nights(stay.checkin_date, stay.checkout_date):
        moves[(from_type, night)] -= 1
        moves[(to_type, night)] += 1
    return moves


def _unit_label(room, bed) -> str:
    return f"la cama {room.number}-{bed.label}" if bed is not None else f"la habitación {room.number}"


def _undo_data(stay, old_room, old_bed) -> dict:
    return {
        "stay_id": str(stay.pk),
        "old_room_id": str(old_room.pk) if old_room else None,
        "old_bed_id": str(old_bed.pk) if old_bed else None,
    }


def _room_changes(old_room, old_bed, room, bed) -> dict:
    changes = {"room": [old_room.number if old_room else None, room.number if room else None]}
    if old_bed is not None or bed is not None:
        changes["bed"] = [old_bed.label if old_bed else None, bed.label if bed else None]
    return changes


# --- modification, cancellation, no-show, confirmation -----------------------------------------------


def modify_stay(
    stay,
    *,
    checkin=None,
    checkout=None,
    room_type=None,
    rate_plan=None,
    adults=None,
    children=None,
    reprice=True,
    actor=None,
) -> Stay:
    """Change dates/category/plan/occupancy of a stay, moving inventory atomically;
    `reservation_updated`.

    - Inventory: the old nights are released and the new ones taken under row locks (409 when a new night has
      no unit left). Restrictions are not enforced (staff change).
    - Price: `reprice=True` quotes again every night (the reservation's promo code is quoted again);
      `reprice=False` keeps the agreed price of the nights that remain and quotes only the new ones. Nights
      with a posted room charge always keep their amount.
    - Room: kept while it is free and unblocked for the new dates and the booked category does not change
      (or becomes the category of the room, e.g. an upgraded guest who keeps the suite); otherwise the stay is
      left unassigned (`room_assigned` with the old room). An in-house stay keeps its arrival, category
      (unless it becomes the room's) and room (else 409) and cannot leave before the business date.
    - Policy: a new plan on the reservation's first stay refreshes `cancellation_policy_snapshot`.
    - Emits `reservation_updated(reservation, changes, stay)` and `inventory_changed`; audits
      `bookings.stay_modified`.
    """
    from apps.finance.models import Charge

    with transaction.atomic():
        stay = _lock_stay(stay)
        reservation = stay.reservation
        prop = reservation.property
        if stay.status not in ACTIVE_STAY_STATUSES:
            raise InvalidStateError("Solo se pueden modificar estadías activas")
        in_house = stay.status == Stay.Status.CHECKED_IN
        new_checkin, new_checkout = checkin or stay.checkin_date, checkout or stay.checkout_date
        _validate_dates(new_checkin, new_checkout)
        new_type = stay.room_type if room_type is None else _room_type(prop, room_type.pk)
        if new_type.kind != stay.room_type.kind:
            raise BookingError(
                "No se puede cambiar entre dormitorio y habitación privada", code="invalid_room_type"
            )
        if rate_plan is not None or new_type.pk != stay.room_type_id:
            new_plan = _rate_plan(prop, (rate_plan or stay.rate_plan).pk, new_type)
        else:
            new_plan = stay.rate_plan
        new_adults = stay.adults if adults is None else int(adults)
        new_children = stay.children if children is None else int(children)
        dorm = new_type.kind == RoomType.Kind.DORM
        if dorm and new_adults + new_children != 1:
            raise BookingError("Una cama es para un solo huésped", code="capacity_exceeded")
        _check_capacity(new_type, new_adults, new_children)
        room_category = stay.room.room_type_id if stay.room_id else None
        if in_house:
            if new_checkin != stay.checkin_date:
                raise InvalidStateError("El huésped ya llegó: la fecha de llegada no se puede cambiar")
            if new_type.pk not in (stay.room_type_id, room_category):
                raise InvalidStateError(
                    "Para cambiar de categoría a un huésped en casa, muévelo de habitación"
                )
            if new_checkout < prop.business_date:
                raise InvalidStateError("La salida no puede ser anterior a la fecha de negocio")
        before = _stay_values(stay)
        if (new_checkin, new_checkout, new_type.pk, new_plan.pk, new_adults, new_children) == (
            stay.checkin_date,
            stay.checkout_date,
            stay.room_type_id,
            stay.rate_plan_id,
            stay.adults,
            stay.children,
        ):
            return stay

        keep_room = (
            stay.room_id is not None
            and new_type.pk in (stay.room_type_id, room_category)
            and not is_blocked(stay.room, stay.bed, new_checkin, new_checkout)
            and not is_occupied(stay, stay.room, stay.bed, new_checkin, new_checkout)
        )
        if in_house and not keep_room:
            raise AvailabilityError("La habitación está ocupada o bloqueada en las nuevas fechas")
        new_unit_type = stay.room.room_type_id if keep_room else new_type.pk
        deltas = Counter({(new_unit_type, night): 1 for night in stay_nights(new_checkin, new_checkout)})
        deltas.subtract(stay_units(stay))
        adjust_inventory(prop, dict(deltas))

        posted = {
            day.isoformat()
            for day in Charge.objects.filter(stay=stay, kind="room", voided_at__isnull=True).values_list(
                "night_date", flat=True
            )
            if day
        }
        existing = {item["date"]: item for item in stay.nightly_rates or []}
        keep = existing if not reprice else {day: item for day, item in existing.items() if day in posted}
        ages = list(stay.children_ages or [])[:new_children]
        pricing = price_stay(
            property=prop,
            room_type=new_type,
            rate_plan=new_plan,
            checkin=new_checkin,
            checkout=new_checkout,
            adults=1 if dorm else new_adults,
            children=0 if dorm else new_children,
            children_ages=None if dorm else ages,
            promo_code=reservation.promo_code or None,
            foreign_non_resident=reservation.booker.is_foreign_non_resident,
            keep=keep,
        )
        old_room, old_types = stay.room, {unit_type_id(stay), stay.room_type_id}
        old_start, old_end = stay.checkin_date, stay.checkout_date
        stay.checkin_date, stay.checkout_date = new_checkin, new_checkout
        stay.room_type, stay.rate_plan = new_type, new_plan
        stay.adults, stay.children, stay.children_ages = new_adults, new_children, ages
        stay.nightly_rates, stay.total_amount = pricing.entries, pricing.total
        if not keep_room:
            stay.room = stay.bed = None
        try:
            with transaction.atomic():
                stay.save()
        except IntegrityError as exc:
            if _sqlstate(exc) == EXCLUSION_VIOLATION:
                raise AvailabilityError("La habitación ya está ocupada en esas fechas") from None
            raise
        if old_room is not None and not keep_room:
            signals.send_on_commit(signals.room_assigned, stay=stay, old_room=old_room)

        changes = {
            **refresh_reservation(reservation),
            **(
                _refresh_policy(reservation, stay) if before["rate_plan_id"] != str(stay.rate_plan_id) else {}
            ),
            **{f"stay.{name}": pair for name, pair in audit.diff(before, _stay_values(stay)).items()},
        }
        audit.record(
            action="bookings.stay_modified",
            target=stay,
            summary=f"Modificó la estadía de {reservation.code} ({new_checkin} → {new_checkout})",
            actor=actor,
            source="user" if _user(actor) else "system",
            property=prop,
            changes={name: list(pair) for name, pair in changes.items()},
        )
        signals.send_on_commit(
            signals.reservation_updated,
            reservation=reservation,
            changes={name: tuple(pair) for name, pair in changes.items()},
            stay=stay,
        )
        _emit_inventory_changed(
            prop,
            [*sorted(old_types, key=str), new_unit_type, new_type.pk],
            min(old_start, new_checkin),
            max(old_end, new_checkout),
        )
    return stay


class _DryRun(Exception):
    """Rolls back a preview transaction."""


def preview_modify_stay(stay, **changes) -> dict:
    """Dry run of `modify_stay(stay, **changes)` (same arguments, same errors: 409 `no_availability`, 400 …):
    what the stay and the reservation would become — nights, prices, room kept or released — without saving,
    auditing or emitting anything (everything happens in a transaction that is rolled back).

    Returns `{"stay": {id, checkin_date, checkout_date, nights, room_type_id, rate_plan_id, room_id, bed_id,
    adults, children, nightly_rates, total_amount}, "room_kept" (null when the stay has no room yet),
    "current_total", "difference", "reservation_total", "balance"}` (money as strings)."""
    from apps.finance.services import reservation_balance

    current = Stay.objects.select_related("reservation").get(pk=stay.pk)
    result = {}
    try:
        with transaction.atomic():
            updated = modify_stay(current, **changes)
            reservation = Reservation.objects.get(pk=updated.reservation_id)
            result = {
                "stay": {
                    **_stay_values(updated),
                    "id": str(updated.pk),
                    "nights": (updated.checkout_date - updated.checkin_date).days,
                    "nightly_rates": list(updated.nightly_rates or []),
                },
                "room_kept": None if current.room_id is None else updated.room_id == current.room_id,
                "current_total": money_str(current.total_amount),
                "difference": money_str(updated.total_amount - current.total_amount),
                "reservation_total": money_str(reservation.total_amount),
                "balance": money_str(reservation_balance(reservation)),
            }
            raise _DryRun
    except _DryRun:
        pass
    return result


def _refresh_policy(reservation, stay) -> dict:
    """The stay got a new plan: when it is the reservation's first stay (the one the snapshot was taken from
    at creation), the policy snapshot follows the new plan. Returns `{"cancellation_policy": [old id, new
    id]}` when the policy itself changed."""
    first = Stay.objects.filter(reservation=reservation).order_by("created_at").values_list("pk", flat=True)
    old = reservation.cancellation_policy_snapshot or {}
    if first.first() != stay.pk:
        return {}
    plan = RatePlan.objects.select_related("cancellation_policy", "parent__cancellation_policy").get(
        pk=stay.rate_plan_id
    )
    new = policy_snapshot(plan)
    if new == old:
        return {}
    reservation.cancellation_policy_snapshot = new
    reservation.save(update_fields=["cancellation_policy_snapshot", "updated_at"])
    if old.get("id") == new.get("id"):
        return {}
    return {"cancellation_policy": [old.get("id"), new.get("id")]}


def _stay_values(stay) -> dict:
    """JSON-friendly values of the stay fields reported in `changes`."""
    return {
        "checkin_date": stay.checkin_date.isoformat(),
        "checkout_date": stay.checkout_date.isoformat(),
        "room_type_id": str(stay.room_type_id),
        "rate_plan_id": str(stay.rate_plan_id),
        "room_id": str(stay.room_id) if stay.room_id else None,
        "bed_id": str(stay.bed_id) if stay.bed_id else None,
        "adults": stay.adults,
        "children": stay.children,
        "total_amount": money_str(stay.total_amount),
    }


def cancel_reservation(reservation, *, reason, waive_fee=False, actor=None, source="user") -> Reservation:
    """Cancel applying the policy snapshot penalty unless `waive_fee`;
    `reservation_cancelled`.

    Only tentative or confirmed reservations (else InvalidStateError). The fee comes from
    `policies.cancellation_fee` (tentative → free); when > 0 it is posted as a `cancellation_fee` charge
    without tax. The inventory is released, every stay becomes `cancelled` (the room stays recorded for
    history, it no longer blocks it). `source` (user | channel | guest | automation | ai | system | api) goes
    to the audit and the charge. The `bookings.waive_fee` permission is checked by the API."""
    from apps.finance import services as finance

    with transaction.atomic():
        reservation = _lock_reservation(reservation)
        prop = reservation.property
        if reservation.status not in (Reservation.Status.TENTATIVE, Reservation.Status.CONFIRMED):
            raise InvalidStateError("Solo se pueden cancelar reservas tentativas o confirmadas")
        stays = _lock_stays(reservation)
        quoted = cancellation_fee(reservation)
        fee = Decimal("0") if waive_fee else quoted.amount
        _release(prop, stays)
        old_status = reservation.status
        for stay in stays:
            stay.status = Stay.Status.CANCELLED
            stay.save(update_fields=["status", "updated_at"])
        reservation.status = Reservation.Status.CANCELLED
        reservation.cancelled_at = timezone.now()
        reservation.cancellation_reason = reason or ""
        reservation.cancellation_fee = fee
        reservation.hold_expires_at = None
        reservation.save(
            update_fields=[
                "status",
                "cancelled_at",
                "cancellation_reason",
                "cancellation_fee",
                "hold_expires_at",
                "updated_at",
            ]
        )
        audit_source = _source(source)
        if fee > 0:
            finance.post_charge(
                finance.get_or_create_folio(reservation),
                kind="cancellation_fee",
                amount=fee,
                description=f"Penalidad de cancelación · {reservation.code}",
                actor=actor,
                source=audit_source,
            )
        changes = {"status": [old_status, "cancelled"], "cancellation_fee": [None, money_str(fee)]}
        if waive_fee and quoted.amount > 0:
            changes["fee_waived"] = [None, money_str(quoted.amount)]
        audit.record(
            action="bookings.reservation_cancelled",
            target=reservation,
            summary=f"Canceló la reserva {reservation.code}"
            + (" (penalidad exonerada)" if "fee_waived" in changes else ""),
            actor=actor,
            source=audit_source,
            property=prop,
            changes=changes,
        )
        signals.send_on_commit(signals.reservation_cancelled, reservation=reservation)
        _emit_inventory_changed(
            prop, [unit_type_id(stay) for stay in stays], reservation.checkin_date, reservation.checkout_date
        )
    return reservation


def mark_no_show(reservation, *, actor=None, source="automation") -> Reservation:
    """Mark a past-due confirmed reservation as no-show, free inventory, charge the
    policy fee; `reservation_no_show`.

    Requires `confirmed` and `checkin_date < property.business_date` (else InvalidStateError). Every night is
    released; the fee (`policies.no_show_fee`: non-refundable → total, else the policy's penalty type, first
    night without policy) is posted as a `cancellation_fee` charge and stored in `cancellation_fee`."""
    from apps.finance import services as finance

    with transaction.atomic():
        reservation = _lock_reservation(reservation)
        prop = reservation.property
        if reservation.status != Reservation.Status.CONFIRMED:
            raise InvalidStateError("Solo una reserva confirmada puede quedar como no show")
        if reservation.checkin_date >= prop.business_date:
            raise InvalidStateError("La llegada todavía no ha vencido")
        stays = _lock_stays(reservation)
        fee = no_show_fee(reservation).amount
        _release(prop, stays)
        for stay in stays:
            stay.status = Stay.Status.NO_SHOW
            stay.save(update_fields=["status", "updated_at"])
        reservation.status = Reservation.Status.NO_SHOW
        reservation.cancellation_fee = fee
        reservation.hold_expires_at = None
        reservation.save(update_fields=["status", "cancellation_fee", "hold_expires_at", "updated_at"])
        audit_source = _source(source)
        if fee > 0:
            finance.post_charge(
                finance.get_or_create_folio(reservation),
                kind="cancellation_fee",
                amount=fee,
                description=f"Penalidad por no show · {reservation.code}",
                actor=actor,
                source=audit_source,
            )
        audit.record(
            action="bookings.reservation_no_show",
            target=reservation,
            summary=f"Marcó la reserva {reservation.code} como no show",
            actor=actor,
            source=audit_source,
            property=prop,
            changes={"status": ["confirmed", "no_show"], "cancellation_fee": [None, money_str(fee)]},
        )
        signals.send_on_commit(signals.reservation_no_show, reservation=reservation)
        _emit_inventory_changed(
            prop, [unit_type_id(stay) for stay in stays], reservation.checkin_date, reservation.checkout_date
        )
    return reservation


def confirm_reservation(reservation, *, actor=None, source="user") -> Reservation:
    """Tentative → confirmed (its tentative stays too) and the hold is cleared; `reservation_updated` with
    `{"status": ("tentative", "confirmed")}`. Used by the API and by the `payment_received` receiver."""
    with transaction.atomic():
        reservation = _lock_reservation(reservation)
        if reservation.status != Reservation.Status.TENTATIVE:
            raise InvalidStateError("Solo se confirman reservas tentativas")
        for stay in _lock_stays(reservation, statuses=[Stay.Status.TENTATIVE]):
            stay.status = Stay.Status.CONFIRMED
            stay.save(update_fields=["status", "updated_at"])
        reservation.status, reservation.hold_expires_at = Reservation.Status.CONFIRMED, None
        reservation.save(update_fields=["status", "hold_expires_at", "updated_at"])
        audit.record(
            action="bookings.reservation_confirmed",
            target=reservation,
            summary=f"Confirmó la reserva {reservation.code}",
            actor=actor,
            source=_source(source),
            property=reservation.property,
            changes={"status": ["tentative", "confirmed"]},
        )
        signals.send_on_commit(
            signals.reservation_updated,
            reservation=reservation,
            changes={"status": ("tentative", "confirmed")},
        )
    return reservation


UPDATABLE_FIELDS = frozenset(
    {
        "notes",
        "special_requests",
        "eta",
        "language",
        "guarantee",
        "custom_values",
        "tags",
        "group_id",
        "booker_id",
    }
)


def update_reservation(reservation, data: dict, *, actor=None, source="user") -> Reservation:
    """Edit the free fields of a reservation (notes, special requests, ETA, language, guarantee, custom
    values, tags, group, booker). Dates, stays, prices and status change only through their own services.
    Audits `bookings.reservation_updated` and emits `reservation_updated(reservation, changes)`."""
    unknown = sorted(set(data) - UPDATABLE_FIELDS)
    if unknown:
        raise BookingError(f"Campos no editables: {', '.join(unknown)}", code="invalid_field", fields=unknown)
    with transaction.atomic():
        reservation = _lock_reservation(reservation)
        prop = reservation.property
        values = dict(data)
        if "guarantee" in values and values["guarantee"] not in Reservation.Guarantee.values:
            raise BookingError(f"Garantía inválida: {values['guarantee']}", code="invalid_guarantee")
        if "group_id" in values:
            group = _resolve_group(prop, values["group_id"])
            values["group_id"] = group.pk if group else None
        if "booker_id" in values:
            # scoped to the organization: another tenant's guest answers like a missing one (no id probing)
            booker = Guest.objects.filter(pk=values["booker_id"], organization=prop.organization).first()
            if booker is None:
                raise BookingError("El huésped no existe en esta organización", code="invalid_guest")
            values["booker_id"] = _resolve_guest(prop, booker, actor).pk
        if "custom_values" in values:
            values["custom_values"] = _validate_custom_values(prop, values["custom_values"])
        changes = {}
        for name, value in values.items():
            old = getattr(reservation, name)
            if old != value:
                changes[name] = (_plain_value(old), _plain_value(value))
                setattr(reservation, name, value)
        if not changes:
            return reservation
        reservation.save(update_fields=[*values, "updated_at"])
        audit.record(
            action="bookings.reservation_updated",
            target=reservation,
            summary=f"Actualizó la reserva {reservation.code}",
            actor=actor,
            source=_source(source),
            property=prop,
            changes={name: list(pair) for name, pair in changes.items()},
        )
        signals.send_on_commit(signals.reservation_updated, reservation=reservation, changes=changes)
    return reservation


def add_occupant(stay, guest, *, actor=None) -> Guest:
    """Add a guest (a Guest of the organization or a GuestInput to upsert) to the stay's occupants."""
    with transaction.atomic():
        stay = _lock_stay(stay)
        occupant = _resolve_guest(stay.reservation.property, guest, actor)
        if not stay.occupants.filter(pk=occupant.pk).exists():
            stay.occupants.add(occupant)
            audit.record(
                action="bookings.occupant_added",
                target=stay,
                summary=f"Agregó a {occupant.full_name} a {stay.reservation.code}",
                actor=actor,
                source="user" if _user(actor) else "system",
                property=stay.reservation.property,
                changes={"occupant_id": [None, str(occupant.pk)]},
            )
    return occupant


def remove_occupant(stay, guest, *, actor=None) -> None:
    with transaction.atomic():
        stay = _lock_stay(stay)
        if stay.occupants.filter(pk=guest.pk).exists():
            stay.occupants.remove(guest)
            audit.record(
                action="bookings.occupant_removed",
                target=stay,
                summary=f"Quitó a {guest.full_name} de {stay.reservation.code}",
                actor=actor,
                source="user" if _user(actor) else "system",
                property=stay.reservation.property,
                changes={"occupant_id": [str(guest.pk), None]},
            )


def _plain_value(value):
    if isinstance(value, time):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _lock_reservation(reservation) -> Reservation:
    return (
        Reservation.objects.select_for_update(of=("self",))
        .select_related("property", "booker")
        .get(pk=reservation.pk)
    )


def _lock_stays(reservation, statuses=ACTIVE_STAY_STATUSES) -> list:
    return list(
        Stay.objects.select_for_update(of=("self",))
        .select_related("room", "room_type")
        .filter(reservation=reservation, status__in=statuses)
        .order_by("checkin_date", "created_at")
    )


def _release(prop, stays) -> None:
    """Give back the units of these active stays (before their status changes)."""
    deltas: Counter = Counter()
    for stay in stays:
        deltas.subtract(stay_units(stay))
    adjust_inventory(prop, dict(deltas))


def _source(value) -> str:
    return value if value in AuditEvent.Source.values else "user"


_SKIPPED = object()  # `_place`: the stay no longer waits for a room


def auto_assign_rooms(*, property, date_from, date_to, actor=None) -> AssignmentReport:
    """Assign rooms to unassigned stays arriving in the range.

    Candidates: tentative/confirmed stays without room, not `locked_room`, with `date_from <= checkin_date <=
    date_to` (both inclusive). Existing assignments and in-house guests are never moved. Priority: VIP
    booker → groups (a `ReservationGroup`, or a reservation with several stays) → longer stays → earlier
    arrival. Each stay takes the best free unit of its category (see `services.assignment`: ready rooms for
    arrivals due today, rooms connected to the ones its group already has, the group's floor / dorm room,
    no gaps, room order); assignments are audited with `source="automation"`. Each stay is checked again under
    lock right before its assignment: one that got a room, checked in, was locked or cancelled after the run
    listed it is skipped (neither moved nor reported). When today's arrivals are in the range and some remain
    without room, the alert `unassigned_arrivals` is raised (and resolved once they all have one). Runs one at
    a time per property."""
    prop = property
    if not date_from or not date_to or date_to < date_from:
        raise BookingError("El rango de fechas no es válido", code="invalid_dates")
    report = AssignmentReport()
    today = prop.business_date
    with transaction.atomic():
        _advisory_lock(prop)
        stays = list(
            Stay.objects.filter(
                reservation__property=prop,
                status__in=[Stay.Status.TENTATIVE, Stay.Status.CONFIRMED],
                room__isnull=True,
                locked_room=False,
                checkin_date__gte=date_from,
                checkin_date__lte=date_to,
            ).select_related("reservation__booker", "room_type")
        )
        if stays:
            window = timedelta(days=GAP_WINDOW_DAYS)
            units = load_units(
                prop,
                {stay.room_type_id for stay in stays},
                min(stay.checkin_date for stay in stays) - window,
                max(stay.checkout_date for stay in stays) + window,
            )
            groups = _group_keys(stays)
            zones, group_rooms = _group_zones(groups)
            connections = room_connections(prop)
            for stay in sorted(stays, key=lambda item: _assign_priority(item, groups)):
                key = groups.get(stay.pk)
                near = (
                    set().union(*(connections.get(room_id, set()) for room_id in group_rooms.get(key, ())))
                    if key
                    else None
                )
                unit = _place(stay, units.get(stay.room_type_id, []), key, zones, today, actor, near=near)
                if unit is _SKIPPED:
                    continue
                if unit is not None and key:
                    group_rooms.setdefault(key, set()).add(unit.room.pk)
                if unit is None:
                    report.unassigned.append(str(stay.pk))
                    units_label = "camas" if stay.room_type.kind == RoomType.Kind.DORM else "habitaciones"
                    report.messages.append(
                        f"{stay.reservation.code}: no hay {units_label} libres en {stay.room_type.code} "
                        f"del {stay.checkin_date.isoformat()} al {stay.checkout_date.isoformat()}"
                    )
                else:
                    report.assigned.append((str(stay.pk), str(unit.unit_id)))
        if date_from <= today <= date_to:
            _unassigned_arrivals_alert(prop, today)
    return report


def _advisory_lock(prop) -> None:
    """Serialize auto-assignment runs of a property (transaction-scoped PostgreSQL advisory lock)."""
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s)", [int.from_bytes(prop.pk.bytes[:8], "big", signed=True)]
        )


def _group_keys(stays) -> dict:
    per_reservation = Counter(stay.reservation_id for stay in stays)
    keys = {}
    for stay in stays:
        if stay.reservation.group_id:
            keys[stay.pk] = f"group:{stay.reservation.group_id}"
        elif per_reservation[stay.reservation_id] > 1:
            keys[stay.pk] = f"reservation:{stay.reservation_id}"
    return keys


def _group_zones(groups) -> tuple[dict, dict]:
    """Zones and rooms already taken by assigned members of these groups (so new members join them):
    `({group key: zone}, {group key: {room ids}})`."""
    group_ids = {key.split(":", 1)[1] for key in groups.values() if key.startswith("group:")}
    reservation_ids = {key.split(":", 1)[1] for key in groups.values() if key.startswith("reservation:")}
    zones, rooms = {}, {}
    assigned = Stay.objects.filter(
        Q(reservation__group_id__in=group_ids) | Q(reservation_id__in=reservation_ids),
        status__in=ACTIVE_STAY_STATUSES,
        room__isnull=False,
    ).values_list("reservation_id", "reservation__group_id", "room_id", "room__floor", "bed_id")
    for reservation_id, group_id, room_id, floor, bed_id in assigned:
        key = f"group:{group_id}" if group_id else f"reservation:{reservation_id}"
        zones.setdefault(key, f"dorm:{room_id}" if bed_id else (floor or ""))
        rooms.setdefault(key, set()).add(room_id)
    return zones, rooms


def _assign_priority(stay, groups):
    key = groups.get(stay.pk)
    return (
        not stay.reservation.booker.is_vip,
        key is None,
        key or "",
        -(stay.checkout_date - stay.checkin_date).days,
        stay.checkin_date,
        stay.reservation.created_at,
        stay.created_at,
    )


def _place(stay, units, group_key, zones, today, actor, near=None):
    """The unit given to the stay, None when none fits, or `_SKIPPED` when the stay stopped waiting for a room
    (changed by someone else after the run listed it)."""
    candidates = free_units(stay, units)
    if not candidates:
        return None
    zone = zones.get(group_key) if group_key else None
    if group_key and zone is None:
        zone = preferred_zone(candidates)
    for unit in rank(stay, candidates, today=today, zone=zone, near=near):
        try:
            with transaction.atomic():
                _assign(stay, unit.room, bed=unit.bed, actor=actor, source="automation", only_waiting=True)
        except _NoLongerWaiting:
            return _SKIPPED
        except AvailabilityError:
            continue  # taken meanwhile (the database constraint decides): try the next one
        unit.busy.append((stay.checkin_date, stay.checkout_date))
        if group_key:
            zones.setdefault(group_key, unit.zone)
        return unit
    return None


def _unassigned_arrivals_alert(prop, today) -> None:
    waiting = list(
        Stay.objects.filter(
            reservation__property=prop,
            status__in=[Stay.Status.TENTATIVE, Stay.Status.CONFIRMED],
            room__isnull=True,
            checkin_date=today,
        )
        .select_related("reservation")
        .order_by("reservation__code")
    )
    dedupe_key = f"bookings:unassigned_arrivals:{today.isoformat()}"
    if not waiting:
        alerts.resolve_alert(prop, dedupe_key)
        return
    codes = sorted({stay.reservation.code for stay in waiting})
    alerts.raise_alert(
        property=prop,
        kind="unassigned_arrivals",
        severity="warning",
        title=f"{len(waiting)} llegada(s) de hoy sin habitación",
        message="Sin habitación asignada: " + ", ".join(codes),
        link="/app/reservations?unassigned=1",
        dedupe_key=dedupe_key,
        data={"date": today.isoformat(), "reservations": codes},
        source="automation",
    )


def check_in(stay, *, actor=None, force=False) -> Stay:
    """Check a stay in: assigned clean/inspected room, arrival ≤ business date; `stay_checked_in`.

    - Status: confirmed; tentative only with `force` (the hold is cleared and the reservation's other
      tentative stays become confirmed). Others → InvalidStateError.
    - Dates: `checkin_date` after the business date → InvalidStateError (early check-in = modify the dates);
      before it (late arrival) needs `force`, and so does a stay whose checkout already passed (registering
      it after the fact, e.g. loading history; check it out next).
    - Room: without one, the best free unit of the category is assigned (ready rooms first); none free →
      InvalidStateError. The room must be clean or inspected, else RoomNotReadyError (409) unless `force`.
    - The IVA exemption of the nights not charged yet is refreshed with the booker's current data (e.g. the
      passport captured at check-in); the reservation becomes `checked_in`.
    """
    with transaction.atomic():
        stay = _lock_stay(stay)
        reservation = stay.reservation
        prop = reservation.property
        today = prop.business_date
        if stay.status not in (Stay.Status.TENTATIVE, Stay.Status.CONFIRMED):
            raise InvalidStateError("La estadía no está pendiente de llegada")
        if stay.status == Stay.Status.TENTATIVE and not force:
            raise InvalidStateError("La reserva es tentativa: confírmala antes del check-in")
        if stay.checkin_date > today:
            raise InvalidStateError(
                f"La llegada es el {stay.checkin_date.isoformat()}; "
                "para un check-in anticipado modifica las fechas"
            )
        if stay.checkout_date <= today and not force:
            raise InvalidStateError(
                f"La estadía terminó el {stay.checkout_date.isoformat()}; confirma para registrarla tarde"
            )
        if stay.checkin_date < today and not force:
            raise InvalidStateError(
                f"La llegada era el {stay.checkin_date.isoformat()}; confirma el check-in tardío"
            )
        source = "user" if _user(actor) else "system"
        if stay.room_id is None:
            room, bed = best_unit(stay)
            if room is None:
                raise InvalidStateError("No hay una habitación libre para asignar a esta estadía")
            _assign(stay, room, bed=bed, actor=actor, source=source)
            stay = _lock_stay(stay)
        room = stay.room
        if room.housekeeping_status not in READY_STATUSES and not force:
            raise RoomNotReadyError(
                f"La habitación {room.number} no está lista ({room.get_housekeeping_status_display()})",
                room_id=str(room.pk),
                housekeeping_status=room.housekeeping_status,
            )
        total_change = _refresh_taxes(stay)
        old_status = stay.status
        stay.status, stay.checked_in_at = Stay.Status.CHECKED_IN, timezone.now()
        stay.save(update_fields=["status", "checked_in_at", "updated_at"])
        reservation = stay.reservation
        if reservation.status == Reservation.Status.TENTATIVE:  # the guest is here: the rest is confirmed
            Stay.objects.filter(reservation=reservation, status=Stay.Status.TENTATIVE).update(
                status=Stay.Status.CONFIRMED, updated_at=timezone.now()
            )
        if reservation.status in (Reservation.Status.TENTATIVE, Reservation.Status.CONFIRMED):
            reservation.status, reservation.hold_expires_at = Reservation.Status.CHECKED_IN, None
            reservation.save(update_fields=["status", "hold_expires_at", "updated_at"])
        changes = {"status": [old_status, "checked_in"], "room": [None, room.number]}
        if total_change:
            changes["total_amount"] = total_change
        audit.record(
            action="bookings.stay_checked_in",
            target=stay,
            summary=f"Check-in de {reservation.code} en {_unit_label(room, stay.bed)}",
            actor=actor,
            source=source,
            property=prop,
            changes=changes,
        )
        signals.send_on_commit(signals.stay_checked_in, stay=stay)
    return stay


def check_out(stay, *, actor=None, force=False) -> Stay:
    """Check out: posts room charges, requires balance 0 (or force), room → dirty;
    `stay_checked_out`.

    - Only `checked_in` stays. An early departure (business date before `checkout_date`) moves the checkout to
      the business date (at least one night), frees the future nights and emits `reservation_updated`. The
      nights freed from the business date on (e.g. leaving on the arrival day) emit `inventory_changed`.
    - `post_room_charges(until_date=checkout_date)`; if `finance.reservation_balance` > 0 → BalanceDueError
      (409, `amount`) unless `force` (the API requires `bookings.checkout_with_balance`); nothing is kept
      when it fails.
    - The room becomes dirty (`set_housekeeping_status(source="automation")`); the reservation becomes
      `checked_out` when none of its stays is active any more. On commit, `stay_checked_out` is sent before
      the room's `room_status_changed`.
    """
    from apps.finance.services import reservation_balance
    from apps.inventory.services import set_housekeeping_status

    with transaction.atomic():
        stay = _lock_stay(stay)
        prop = stay.reservation.property
        if stay.status != Stay.Status.CHECKED_IN:
            raise InvalidStateError("Solo un huésped en casa puede hacer check-out")
        source = "user" if _user(actor) else "system"
        changes = {}
        departure = max(prop.business_date, stay.checkin_date + timedelta(days=1))
        if departure < stay.checkout_date:
            changes = _shorten(stay, departure)
        post_room_charges(stay, until_date=stay.checkout_date, actor=actor, source=source)
        stay = _lock_stay(stay)
        reservation = stay.reservation
        balance = reservation_balance(reservation)
        if balance > 0 and not force:
            raise BalanceDueError(
                f"La reserva tiene un saldo pendiente de {money_str(balance)}", amount=balance
            )
        _release(prop, [stay])
        if stay.checkout_date > prop.business_date:  # left on the arrival day: tonight is sellable again
            _emit_inventory_changed(
                prop, [unit_type_id(stay)], max(stay.checkin_date, prop.business_date), stay.checkout_date
            )
        stay.status, stay.checked_out_at = Stay.Status.CHECKED_OUT, timezone.now()
        stay.save(update_fields=["status", "checked_out_at", "updated_at"])
        if not Stay.objects.filter(reservation=reservation, status__in=ACTIVE_STAY_STATUSES).exists():
            reservation.status = Reservation.Status.CHECKED_OUT
            reservation.save(update_fields=["status", "updated_at"])
        changes = {"status": ["checked_in", "checked_out"], **changes}
        if balance > 0:
            changes["balance_due"] = [None, money_str(balance)]
        audit.record(
            action="bookings.stay_checked_out",
            target=stay,
            summary=f"Check-out de {reservation.code} ({_unit_label(stay.room, stay.bed)})",
            actor=actor,
            source=source,
            property=prop,
            changes=changes,
        )
        # registered first, so receivers get `stay_checked_out` before the `room_status_changed` below
        signals.send_on_commit(signals.stay_checked_out, stay=stay)
        set_housekeeping_status(stay.room, "dirty", actor=actor, source="automation")
    return stay


def _shorten(stay, departure) -> dict:
    """Early departure: drop the nights from `departure` on, give their units back, refresh the totals and
    emit `reservation_updated`."""
    prop = stay.reservation.property
    old_checkout = stay.checkout_date
    unit = unit_type_id(stay)
    adjust_inventory(prop, {(unit, night): -1 for night in stay_nights(departure, old_checkout)})
    stay.checkout_date = departure
    stay.nightly_rates = [item for item in stay.nightly_rates or [] if item["date"] < departure.isoformat()]
    stay.total_amount = entries_total(stay.nightly_rates)
    stay.save(update_fields=["checkout_date", "nightly_rates", "total_amount", "updated_at"])
    changes = {
        **refresh_reservation(stay.reservation),
        "stay.checkout_date": [old_checkout.isoformat(), departure.isoformat()],
    }
    signals.send_on_commit(
        signals.reservation_updated,
        reservation=stay.reservation,
        changes={name: tuple(pair) for name, pair in changes.items()},
        stay=stay,
    )
    _emit_inventory_changed(prop, [unit], departure, old_checkout)
    return changes


def _refresh_taxes(stay):
    """Re-apply the lodging tax to the nights not charged yet when the booker's IVA exemption changed.
    Returns `[old_total, new_total]` or None."""
    from apps.finance.models import Charge

    prop = stay.reservation.property
    tax = lodging_tax(prop)
    if tax is None:
        return None
    foreign = stay.reservation.booker.is_foreign_non_resident
    exempt_now = tax_exempt(tax, foreign)
    posted = {
        day.isoformat()
        for day in Charge.objects.filter(stay=stay, kind="room", voided_at__isnull=True).values_list(
            "night_date", flat=True
        )
        if day
    }
    entries, changed = [], False
    for item in stay.nightly_rates or []:
        entry_exempt = D(item.get("tax", 0)) == 0 and D(tax.rate) != 0
        if item["date"] in posted or "net" not in item or entry_exempt == exempt_now:
            entries.append(item)
            continue
        price = D(item["amount"]) if tax.included_in_price else D(item["net"])
        entries.append(
            night_entry(date.fromisoformat(item["date"]), price, tax, foreign, prop.currency or "COP")
        )
        changed = True
    if not changed:
        return None
    old_total = stay.total_amount
    stay.nightly_rates, stay.total_amount = entries, entries_total(entries)
    stay.save(update_fields=["nightly_rates", "total_amount", "updated_at"])
    refresh_reservation(stay.reservation)
    return [money_str(old_total), money_str(stay.total_amount)]
