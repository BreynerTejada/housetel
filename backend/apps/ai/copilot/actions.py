"""Running the copilot's proposals (plan C9: "al confirmar re-valida el permiso del usuario en ese momento y
ejecuta con los servicios de contrato con audit source="ai"").

- Only the user who asked (the session's owner) can confirm or reject a proposal, and only once.
- The permission the proposal needs is checked again at confirmation time (roles change).
- The action runs through the contract services of its app (bookings, inventory, finance, messaging) in a
  savepoint: a business error (no availability, balance due, room blocked…) rolls it back and leaves the
  proposal `failed` with the reason. A success leaves it `executed` with its result and an
  `ai.copilot_action` audit event (`source="ai"`, actor = the user who confirmed).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.ai.models import CopilotAction
from apps.core import audit
from apps.core.errors import DomainError
from apps.core.permissions import has_perm

logger = logging.getLogger("housetel.ai")


class ActionError(DomainError):
    """The proposal cannot be decided by this user now (404 not theirs, 403 permission, 409 not pending)."""

    code = "action_error"


def _not_found() -> ActionError:
    error = ActionError("Propuesta no encontrada", code="not_found")
    error.status_code = 404
    return error


@dataclass
class ExecContext:
    property: Any
    user: Any
    action: CopilotAction


Executor = Callable[[ExecContext, dict], tuple[dict, Any]]
EXECUTORS: dict[str, Executor] = {}


def executor(code: str):
    def register(fn: Executor) -> Executor:
        EXECUTORS[code] = fn
        return fn

    return register


def _lock_pending(action, user) -> CopilotAction:
    locked = (
        CopilotAction.objects.select_for_update(of=("self",))
        .select_related("session__property")
        .filter(pk=action.pk)
        .first()
    )
    if locked is None or locked.session.user_id != user.pk:
        raise _not_found()
    if locked.status != CopilotAction.Status.PROPOSED:
        error = ActionError("Esta propuesta ya fue decidida", code="action_not_pending", status=locked.status)
        error.status_code = 409
        raise error
    return locked


def execute_action(action, *, user) -> CopilotAction:
    """Confirm and run `action`. Raises ActionError (404/403/409); a failure of the action itself leaves it
    `failed` (returned, not raised)."""
    with transaction.atomic():
        locked = _lock_pending(action, user)
        prop = locked.session.property
        if not has_perm(user, prop, locked.permission):
            error = ActionError(
                "Ya no tienes permiso para ejecutar esta acción",
                code="permission_denied",
                permission=locked.permission,
            )
            error.status_code = 403
            raise error
        run = EXECUTORS.get(locked.action_code)
        now = timezone.now()
        try:
            if run is None:
                raise DomainError(f"Acción desconocida: {locked.action_code}", code="unknown_action")
            with transaction.atomic():
                result, target = run(
                    ExecContext(property=prop, user=user, action=locked), dict(locked.params)
                )
                audit.record(
                    action="ai.copilot_action",
                    target=target,
                    property=prop,
                    actor=user,
                    source="ai",
                    summary=f"Copiloto: {locked.summary}"[:500],
                    changes={
                        "action": locked.action_code,
                        "params": locked.params,
                        "result": result,
                        "proposal_id": str(locked.pk),
                    },
                )
        except DomainError as exc:
            locked.status, locked.error = CopilotAction.Status.FAILED, exc.message
        except Exception as exc:  # a bug must not leave the proposal hanging: record it and log it
            logger.exception("Copilot action %s failed", locked.action_code)
            locked.status = CopilotAction.Status.FAILED
            locked.error = f"Error inesperado al ejecutar la acción ({type(exc).__name__})"
        else:
            locked.status, locked.result, locked.executed_at = CopilotAction.Status.EXECUTED, result, now
        locked.decided_by, locked.decided_at = user, now
        locked.save(
            update_fields=[
                "status",
                "result",
                "error",
                "executed_at",
                "decided_by",
                "decided_at",
                "updated_at",
            ]
        )
    return locked


def reject_action(action, *, user) -> CopilotAction:
    with transaction.atomic():
        locked = _lock_pending(action, user)
        locked.status = CopilotAction.Status.REJECTED
        locked.decided_by, locked.decided_at = user, timezone.now()
        locked.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    return locked


# ---- executors (each returns (result, audit target)) ---------------------------------------------------


def _gone(what: str) -> DomainError:
    return DomainError(f"{what} ya no existe o no está disponible", code="not_available")


def _uuid(value):
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _reservation(ctx, reservation_id):
    from apps.bookings.models import Reservation

    reservation = Reservation.objects.filter(property=ctx.property, pk=_uuid(reservation_id)).first()
    if reservation is None:
        raise _gone("La reserva")
    return reservation


def _stays(ctx, stay_ids):
    from apps.bookings.models import Stay

    ids = [_uuid(value) for value in stay_ids or []]
    stays = list(
        Stay.objects.select_related("reservation", "room")
        .filter(reservation__property=ctx.property, pk__in=[value for value in ids if value])
        .order_by("checkin_date", "id")
    )
    if not stays or len(stays) != len(ids):
        raise _gone("La estadía")
    return stays


def _money(value) -> str:
    return f"{Decimal(value or 0):.2f}"


@executor("create_reservation")
def _create_reservation(ctx: ExecContext, params: dict):
    from apps.bookings.services.reservations import create_reservation
    from apps.bookings.types import ReservationRequest, StayRequest
    from apps.guests.models import Guest
    from apps.guests.types import GuestInput

    if params.get("guest_id"):
        booker = Guest.objects.filter(
            organization=ctx.property.organization, pk=_uuid(params["guest_id"]), merged_into__isnull=True
        ).first()
        if booker is None:
            raise _gone("El huésped")
    else:
        guest = params.get("guest") or {}
        booker = GuestInput(
            first_name=guest.get("first_name", ""),
            last_name=guest.get("last_name", ""),
            email=guest.get("email", ""),
            phone=guest.get("phone", ""),
            language=getattr(ctx.user, "language", "es") or "es",
        )
    request = ReservationRequest(
        property=ctx.property,
        booker=booker,
        stays=[
            StayRequest(
                room_type_id=_uuid(params["room_type_id"]),
                rate_plan_id=_uuid(params["rate_plan_id"]),
                checkin=date.fromisoformat(params["checkin"]),
                checkout=date.fromisoformat(params["checkout"]),
                adults=int(params.get("adults") or 1),
                children=int(params.get("children") or 0),
            )
        ],
        source="front_desk",
        notes=str(params.get("notes") or ""),
    )
    reservation = create_reservation(request, actor=ctx.user, source_label="ai")
    result = {
        "reservation_id": str(reservation.pk),
        "code": reservation.code,
        "status": reservation.status,
        "total": _money(reservation.total_amount),
        "currency": reservation.currency,
    }
    return result, reservation


@executor("move_room")
def _move_room(ctx: ExecContext, params: dict):
    from apps.bookings.services.reservations import assign_room
    from apps.inventory.models import Room

    (stay,) = _stays(ctx, [params.get("stay_id")])
    room = Room.objects.filter(property=ctx.property, pk=_uuid(params.get("room_id")), is_active=True).first()
    if room is None:
        raise _gone("La habitación")
    assign_room(stay, room, actor=ctx.user, force=bool(params.get("force")))
    reservation = stay.reservation
    return {"reservation_id": str(reservation.pk), "code": reservation.code, "room": room.number}, reservation


@executor("check_in")
def _check_in(ctx: ExecContext, params: dict):
    from apps.bookings.services.reservations import check_in

    stays = _stays(ctx, params.get("stay_ids"))
    rooms = []
    for stay in stays:
        done = check_in(stay, actor=ctx.user)
        rooms.append(done.room.number if done.room_id else None)
    reservation = stays[0].reservation
    return {
        "reservation_id": str(reservation.pk),
        "code": reservation.code,
        "checked_in": len(stays),
        "rooms": [room for room in rooms if room],
    }, reservation


@executor("check_out")
def _check_out(ctx: ExecContext, params: dict):
    from apps.bookings.services.reservations import check_out

    stays = _stays(ctx, params.get("stay_ids"))
    for stay in stays:
        check_out(stay, actor=ctx.user)
    reservation = stays[0].reservation
    return {
        "reservation_id": str(reservation.pk),
        "code": reservation.code,
        "checked_out": len(stays),
    }, reservation


SENT_STATUSES = {"queued", "sent", "delivered"}


@executor("send_message")
def _send_message(ctx: ExecContext, params: dict):
    reservation = _reservation(ctx, params.get("reservation_id"))
    channel = params.get("channel") or "email"
    template = params.get("template_code") or ""
    if template == "custom_message":
        try:
            from apps.messaging.inbox import send_to_guest
        except ImportError as exc:  # pragma: no cover - depends on C6
            raise DomainError("El envío de texto libre no está disponible", code="not_available") from exc
        message = send_to_guest(
            ctx.property,
            channel=channel,
            author=ctx.user,
            reservation=reservation,
            body=params.get("message", ""),
        )
        return {
            "reservation_id": str(reservation.pk),
            "code": reservation.code,
            "channel": channel,
            "message_id": str(message.pk),
        }, reservation
    from apps.messaging.services import send_message

    results = send_message(
        property=ctx.property, template_code=template, reservation=reservation, channels=(channel,)
    )
    delivered = [item for item in results if item.status in SENT_STATUSES]
    if not delivered:
        reason = next((item.error for item in results if item.error), "") or "no hay canal disponible"
        raise DomainError(f"El mensaje no se envió: {reason}", code="not_sent")
    return {
        "reservation_id": str(reservation.pk),
        "code": reservation.code,
        "channel": channel,
        "to": delivered[0].to,
        "template_code": template,
    }, reservation


@executor("block_room")
def _block_room(ctx: ExecContext, params: dict):
    from apps.inventory.models import Room
    from apps.inventory.services import block_room

    room = Room.objects.filter(property=ctx.property, pk=_uuid(params.get("room_id"))).first()
    if room is None:
        raise _gone("La habitación")
    block = block_room(
        room,
        start=date.fromisoformat(params["start"]),
        end=date.fromisoformat(params["end"]),
        kind=params.get("kind") or "out_of_service",
        reason=params.get("reason") or "",
        actor=ctx.user,
    )
    return {
        "block_id": str(block.pk),
        "room": room.number,
        "start": params["start"],
        "end": params["end"],
    }, block


@executor("add_extra")
def _add_extra(ctx: ExecContext, params: dict):
    from apps.finance.services import get_or_create_folio, post_extra_charge
    from apps.rates.models import Extra

    reservation = _reservation(ctx, params.get("reservation_id"))
    extra = Extra.objects.filter(
        property=ctx.property, pk=_uuid(params.get("extra_id")), is_active=True
    ).first()
    if extra is None:
        raise _gone("El extra")
    charge = post_extra_charge(
        get_or_create_folio(reservation),
        extra,
        quantity=int(params.get("quantity") or 1),
        actor=ctx.user,
        source="ai",
    )
    return {
        "reservation_id": str(reservation.pk),
        "code": reservation.code,
        "charge_id": str(charge.pk),
        "total": _money(charge.amount + charge.tax_amount),
    }, charge
