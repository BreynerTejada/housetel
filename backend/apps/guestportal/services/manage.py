"""Changing or cancelling the booking from the portal (plan C5), always within the policy.

- Cancel: tentative or confirmed reservations whose arrival is today or later, not sold by a channel (the
  OTA owns those) and only if the hotel allows it. The penalty is the policy's (`bookings.cancel_reservation`
  with `source="guest"`); the guest sees it first and must confirm. A resulting credit (deposit larger than
  the penalty) raises an alert so the hotel refunds it.
- Modify dates: confirmed single-room reservations, while the booking could still be cancelled for free
  (non-refundable or past the free window → no). Availability comes from `preview_modify_stay` (it counts the
  guest's own units), rate restrictions from `rates.quote`; `modify_stay(reprice=True)` applies it.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction

from apps.bookings.models import ACTIVE_STAY_STATUSES, Reservation
from apps.bookings.services.policies import cancellation_fee
from apps.bookings.services.reservations import cancel_reservation, modify_stay, preview_modify_stay
from apps.bookings.types import BookingError, RestrictionError
from apps.core import alerts, audit
from apps.core.errors import ConfirmationRequired, ConflictError
from apps.core.money import quantize
from apps.guestportal.services.access import portal_settings
from apps.guestportal.services.summary import money

CANCELLABLE_STATUSES = ("tentative", "confirmed")
RESTRICTIONS = ("stop_sell", "cta", "ctd", "min_los", "max_los")
MAX_NIGHTS = 30


class CancellationNotAllowed(ConflictError):
    code = "cancellation_not_allowed"


class ModificationNotAllowed(ConflictError):
    code = "modification_not_allowed"


def _is_channel_booking(reservation) -> bool:
    return reservation.source == Reservation.Source.OTA


def cancellation_preview(reservation) -> dict:
    """What cancelling now would cost and whether the guest may do it here.

    `reason` when not allowed: disabled | channel | status | past."""
    settings = portal_settings(reservation.property)
    quote = cancellation_fee(reservation)
    reason = None
    if not settings.allow_guest_cancellation:
        reason = "disabled"
    elif _is_channel_booking(reservation):
        reason = "channel"
    elif reservation.status not in CANCELLABLE_STATUSES:
        reason = "status"
    elif reservation.checkin_date < reservation.property.business_date:
        reason = "past"
    policy = quote.policy or {}
    return {
        "can_cancel": reason is None,
        "reason": reason,
        "fee": money(quote.amount),
        "fee_reason": quote.reason,
        "free_until": quote.free_until.isoformat() if quote.free_until else None,
        "non_refundable": bool(policy.get("non_refundable")),
        "policy": {"name": policy.get("name") or {}, "description": policy.get("description") or {}},
        "currency": reservation.currency,
    }


def cancel_from_portal(reservation, *, confirm, reason: str = "") -> Reservation:
    """Cancel with the policy's penalty (`source="guest"`); `confirm` must be exactly True."""
    from apps.finance.services import reservation_balance

    if confirm is not True:
        raise ConfirmationRequired("Confirma que quieres cancelar la reserva")
    preview = cancellation_preview(reservation)
    if preview["reason"] == "disabled":
        raise CancellationNotAllowed("El hotel no permite cancelar desde el portal: contáctalo directamente",
                                     code="cancellation_disabled")  # fmt: skip
    if preview["reason"] == "channel":
        raise CancellationNotAllowed(
            "Esta reserva se hizo por un canal externo: cancélala en el sitio donde reservaste",
            code="managed_by_channel",
        )
    if not preview["can_cancel"]:
        raise CancellationNotAllowed(
            "Esta reserva ya no se puede cancelar desde el portal", reason=preview["reason"]
        )
    with transaction.atomic():
        cancelled = cancel_reservation(
            reservation,
            reason=(reason or "").strip()[:500] or "Cancelada por el huésped desde el portal",
            source="guest",
        )
        balance = quantize(reservation_balance(cancelled), cancelled.currency)
        credit = -balance if balance < 0 else 0
        alerts.raise_alert(
            property=cancelled.property,
            kind="guestportal_cancelled",
            severity="warning" if credit else "info",
            title=f"{cancelled.code} cancelada por el huésped",
            message=(
                f"El huésped canceló desde el portal. Penalidad: {money(cancelled.cancellation_fee)}."
                + (f" Queda un saldo a favor de {money(credit)}: reembólsalo." if credit else "")
            ),
            link=f"/app/reservations/{cancelled.pk}",
            dedupe_key=f"guestportal:cancelled:{cancelled.pk}",
            data={
                "reservation_id": str(cancelled.pk),
                "code": cancelled.code,
                "fee": money(cancelled.cancellation_fee),
                "credit": money(credit),
            },  # fmt: skip
            source="guest",
        )
    return cancelled


def _active_stays(reservation) -> list:
    return list(
        reservation.stays.filter(status__in=ACTIVE_STAY_STATUSES).select_related("room_type", "rate_plan")
    )


def modification_rules(reservation) -> dict:
    """`reason` when not allowed: disabled | channel | status | multiple_rooms | past | non_refundable |
    outside_free_window."""
    settings = portal_settings(reservation.property)
    quote = cancellation_fee(reservation)
    reason = None
    if not settings.allow_guest_modification:
        reason = "disabled"
    elif _is_channel_booking(reservation):
        reason = "channel"
    elif reservation.status != Reservation.Status.CONFIRMED:
        reason = "status"
    elif len(_active_stays(reservation)) != 1:
        reason = "multiple_rooms"
    elif reservation.checkin_date < reservation.property.business_date:
        reason = "past"
    elif quote.amount > 0:
        reason = "non_refundable" if quote.reason == "non_refundable" else "outside_free_window"
    return {
        "can_modify": reason is None,
        "reason": reason,
        "free_until": quote.free_until.isoformat() if quote.free_until else None,
        "max_nights": MAX_NIGHTS,
    }


def _parse(value) -> date | None:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _checked(reservation, checkin, checkout):
    rules = modification_rules(reservation)
    if not rules["can_modify"]:
        raise ModificationNotAllowed("Las fechas de esta reserva no se pueden cambiar desde el portal",
                                     reason=rules["reason"])  # fmt: skip
    checkin, checkout = _parse(checkin), _parse(checkout)
    today = reservation.property.business_date
    if checkin is None or checkout is None or checkout <= checkin or checkin < today:
        raise BookingError("Elige una llegada desde hoy y una salida posterior", code="invalid_dates")
    if (checkout - checkin) > timedelta(days=MAX_NIGHTS):
        raise BookingError(f"Máximo {MAX_NIGHTS} noches desde el portal", code="invalid_dates")
    stay = _active_stays(reservation)[0]
    _check_restrictions(reservation, stay, checkin, checkout)
    return stay, checkin, checkout


def _check_restrictions(reservation, stay, checkin, checkout) -> None:
    from apps.rates.services.quote import quote

    result = quote(
        property=reservation.property,
        room_type=stay.room_type,
        rate_plan=stay.rate_plan,
        checkin=checkin,
        checkout=checkout,
        adults=stay.adults,
        children=stay.children,
        children_ages=list(stay.children_ages or []) or None,
        promo_code=reservation.promo_code or None,
        guest_is_foreign_non_resident=reservation.booker.is_foreign_non_resident,
    )
    violations = [code for code in result.violations if code in RESTRICTIONS]
    if violations:
        raise RestrictionError("Esas fechas no cumplen las condiciones de la tarifa", violations=violations)
    if "no_rate" in result.violations:
        raise BookingError("No hay precio para esas fechas", code="no_rate")


def preview_modification(reservation, *, checkin, checkout) -> dict:
    """New nights and totals for the dates, without saving anything (409 `no_availability` if full)."""
    stay, checkin, checkout = _checked(reservation, checkin, checkout)
    preview = preview_modify_stay(stay, checkin=checkin, checkout=checkout, reprice=True)
    return {
        "checkin": checkin.isoformat(),
        "checkout": checkout.isoformat(),
        "nights": (checkout - checkin).days,
        "current_total": money(reservation.total_amount),
        "total": preview["reservation_total"],
        "difference": money(Decimal(preview["reservation_total"]) - reservation.total_amount),
        "balance": preview["balance"],
        "currency": reservation.currency,
    }


def modify_from_portal(reservation, *, checkin, checkout) -> dict:
    """Move the stay to the new dates (repriced), audit it and tell the front desk."""
    from apps.finance.services import reservation_balance

    stay, checkin, checkout = _checked(reservation, checkin, checkout)
    before = (reservation.checkin_date, reservation.checkout_date, money(reservation.total_amount))
    with transaction.atomic():
        modify_stay(stay, checkin=checkin, checkout=checkout, reprice=True)
        updated = Reservation.objects.select_related("property", "booker").get(pk=reservation.pk)
        balance = quantize(reservation_balance(updated), updated.currency)
        audit.record(
            action="guestportal.reservation_modified",
            target=updated,
            summary=f"El huésped cambió las fechas de {updated.code} desde el portal",
            source="guest",
            property=updated.property,
            changes={
                "checkin_date": [before[0].isoformat(), checkin.isoformat()],
                "checkout_date": [before[1].isoformat(), checkout.isoformat()],
                "total_amount": [before[2], money(updated.total_amount)],
            },
        )
        credit = -balance if balance < 0 else 0
        alerts.raise_alert(
            property=updated.property,
            kind="guestportal_modified",
            severity="warning" if credit else "info",
            title=f"{updated.code}: el huésped cambió sus fechas",
            message=(
                f"Nuevas fechas: {checkin.isoformat()} → {checkout.isoformat()}. "
                "Revisa la asignación de habitación."
                + (f" Saldo a favor: {money(credit)}." if credit else "")
            ),
            link=f"/app/reservations/{updated.pk}",
            dedupe_key=f"guestportal:modified:{updated.pk}",
            data={
                "reservation_id": str(updated.pk),
                "code": updated.code,
                "checkin": checkin.isoformat(),
                "checkout": checkout.isoformat(),
                "credit": money(credit),
            },  # fmt: skip
            source="guest",
        )
    return {"total": money(updated.total_amount), "balance": money(balance), "currency": updated.currency}
