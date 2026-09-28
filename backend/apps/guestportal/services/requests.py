"""Extras and service requests from the portal (plan C5).

- Extras sold online: with `auto_approve_extras` the charge is posted right away
  (`finance.post_extra_charge`, source `guest`) and the request is `approved`; otherwise it waits for the
  staff (`requested` + alert) with its estimated price.
- Late check-out, early check-in, transfers and free-text requests always wait for the staff (`requested` +
  alert `guestportal_request`, one per request, resolved when the staff decides).
- The staff approves (optionally charging a catalog extra: e.g. the "Late check-out" extra), rejects or marks
  the request done. Every step is audited.
"""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.bookings.types import InvalidStateError
from apps.core import alerts, audit
from apps.core.errors import DomainError
from apps.core.money import D, quantize
from apps.guestportal.models import ServiceRequest
from apps.guestportal.services.access import portal_settings
from apps.rates.models import Extra

# a tentative booking may still expire: charges and requests wait until it is confirmed
REQUESTABLE_STATUSES = ("confirmed", "checked_in")
NEEDS_NOTES = {ServiceRequest.Kind.OTHER, ServiceRequest.Kind.TRANSFER}
MAX_QUANTITY = 99
ALERT_TITLES = {
    "late_checkout": "Late check-out solicitado",
    "early_checkin": "Early check-in solicitado",
    "transfer": "Traslado solicitado",
    "extra": "Extra por aprobar",
    "other": "Solicitud del huésped",
}


def _tax_of(extra):
    return extra.tax if extra.tax_id and extra.tax.is_active else None


def extra_price(extra, folio, quantity: int) -> Decimal:
    """What the guest pays for `quantity` units: net × quantity + tax, rounded like `finance.post_charge`."""
    from apps.finance.services import extra_unit_net, is_tax_exempt

    currency = folio.currency
    tax = _tax_of(extra)
    net = quantize(D(extra_unit_net(extra, tax)) * int(quantity), currency)
    tax_amount = quantize(net * D(tax.rate) / 100, currency) if tax and not is_tax_exempt(folio, tax) else 0
    return net + D(tax_amount)


def portal_extras(reservation) -> list[dict]:
    """Active extras sold online, priced for this booking (tax and foreign-guest exemption included)."""
    from apps.finance.services import extra_default_quantity, get_or_create_folio, is_tax_exempt

    if reservation.status not in REQUESTABLE_STATUSES:
        return []
    folio = get_or_create_folio(reservation)
    extras = (
        Extra.objects.filter(property=reservation.property, is_active=True, sellable_online=True)
        .select_related("tax")
        .order_by("code")
    )
    result = []
    for extra in extras:
        quantity = extra_default_quantity(extra, folio)
        tax = _tax_of(extra)
        result.append(
            {
                "id": str(extra.pk),
                "code": extra.code,
                "name": extra.name,
                "charge_type": extra.charge_type,
                "unit_price": f"{extra_price(extra, folio, 1):.2f}",
                "default_quantity": quantity,
                "default_total": f"{extra_price(extra, folio, quantity):.2f}",
                "tax_exempt": bool(tax and is_tax_exempt(folio, tax)),
                "currency": folio.currency,
            }
        )
    return result


def request_payload(request) -> dict:
    return {
        "id": str(request.pk),
        "kind": request.kind,
        "status": request.status,
        "extra": {"id": str(request.extra_id), "code": request.extra.code, "name": request.extra.name}
        if request.extra_id
        else None,
        "quantity": request.quantity,
        "requested_time": request.requested_time.strftime("%H:%M") if request.requested_time else None,
        "notes": request.notes,
        "price": f"{request.price:.2f}" if request.price is not None else None,
        "decision_note": request.decision_note,
        "created_at": request.created_at.isoformat(),
        "decided_at": request.decided_at.isoformat() if request.decided_at else None,
    }


def _alert_dedupe(request) -> str:
    return f"guestportal:request:{request.pk}"


def _raise_request_alert(request) -> None:
    reservation = request.reservation
    what = request.extra.code if request.extra_id else request.get_kind_display()
    when = f" hasta/desde las {request.requested_time:%H:%M}" if request.requested_time else ""
    alerts.raise_alert(
        property=reservation.property,
        kind="guestportal_request",
        severity="info",
        title=f"{ALERT_TITLES.get(request.kind, 'Solicitud del huésped')}: {reservation.code}",
        message=(
            f"{reservation.booker.full_name} pidió desde el portal: {what}{when}. {request.notes}"
        ).strip(),
        link=f"/app/reservations/{reservation.pk}",
        dedupe_key=_alert_dedupe(request),
        data={
            "request_id": str(request.pk),
            "reservation_id": str(reservation.pk),
            "kind": request.kind,
            # what the staff UI needs to write this alert in the viewer's language
            "code": reservation.code,
            "guest": reservation.booker.full_name,
            "extra_name": request.extra.name if request.extra_id else None,
            "time": f"{request.requested_time:%H:%M}" if request.requested_time else "",
            "notes": (request.notes or "")[:300],
        },
        source="guest",
    )


def _quantity(value, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        quantity = int(value)
    except (TypeError, ValueError):
        quantity = 0
    if not 1 <= quantity <= MAX_QUANTITY:
        raise DomainError("La cantidad debe estar entre 1 y 99", code="validation_error",
                          fields={"quantity": ["Entre 1 y 99"]})  # fmt: skip
    return quantity


def create_request(
    reservation, *, kind, extra_id=None, quantity=None, requested_time=None, notes=""
) -> ServiceRequest:
    """A request of the guest (see module doc). 409 `invalid_state` once the booking is over or cancelled."""
    from apps.finance.services import extra_default_quantity, get_or_create_folio, post_extra_charge

    if kind not in ServiceRequest.Kind.values:
        raise DomainError(
            "Tipo de solicitud inválido", code="validation_error", fields={"kind": ["Inválido"]}
        )
    if reservation.status not in REQUESTABLE_STATUSES:
        raise InvalidStateError("Esta reserva ya no recibe solicitudes")
    notes = (notes or "").strip()[:1000]
    if kind in NEEDS_NOTES and not notes:
        raise DomainError(
            "Cuéntanos qué necesitas", code="validation_error", fields={"notes": ["Obligatorio"]}
        )
    prop = reservation.property
    with transaction.atomic():
        if kind != ServiceRequest.Kind.EXTRA:
            request = ServiceRequest.objects.create(
                reservation=reservation, kind=kind, requested_time=requested_time, notes=notes
            )
            _raise_request_alert(request)
        else:
            extra = (
                Extra.objects.filter(pk=extra_id, property=prop, is_active=True, sellable_online=True).first()
                if _looks_like_uuid(extra_id)
                else None
            )
            if extra is None:
                raise DomainError("Ese extra no está disponible", code="invalid_extra")
            folio = get_or_create_folio(reservation)
            units = _quantity(quantity, extra_default_quantity(extra, folio))
            if portal_settings(prop).auto_approve_extras:
                charge = post_extra_charge(folio, extra, quantity=units, source="guest")
                request = ServiceRequest.objects.create(
                    reservation=reservation,
                    kind=kind,
                    extra=extra,
                    quantity=units,
                    notes=notes,
                    status=ServiceRequest.Status.APPROVED,
                    price=charge.amount + charge.tax_amount,
                    charge=charge,
                    decided_at=timezone.now(),
                )
            else:
                request = ServiceRequest.objects.create(
                    reservation=reservation,
                    kind=kind,
                    extra=extra,
                    quantity=units,
                    notes=notes,
                    price=extra_price(extra, folio, units),
                )
                _raise_request_alert(request)
        audit.record(
            action="guestportal.request_created",
            target=request,
            summary=f"Solicitud «{request.get_kind_display()}» desde el portal ({reservation.code})",
            source="guest",
            property=prop,
            changes={"kind": kind, "status": request.status, "quantity": request.quantity},
        )
    return request


def _looks_like_uuid(value) -> bool:
    import uuid

    try:
        uuid.UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True


def _decide(request, *, status, actor, note, action, summary):
    request.status = status
    request.decided_by = actor if getattr(actor, "is_authenticated", False) else None
    request.decided_at = timezone.now()
    request.decision_note = (note or "").strip()[:300]
    request.save()
    alerts.resolve_alert(request.reservation.property, _alert_dedupe(request), actor=request.decided_by)
    audit.record(
        action=action,
        target=request,
        summary=summary,
        actor=actor,
        property=request.reservation.property,
        changes={"status": status},
    )
    return request


def _locked(request) -> ServiceRequest:
    return (
        ServiceRequest.objects.select_for_update(of=("self",))
        .select_related("reservation__property", "reservation__booker", "extra")
        .get(pk=request.pk)
    )


def approve_request(request, *, actor, extra=None, quantity=None, note="") -> ServiceRequest:
    """Approve a pending request; charges `extra` (or the requested extra) on the guest folio."""
    from apps.finance.services import get_or_create_folio, post_extra_charge

    with transaction.atomic():
        request = _locked(request)
        if request.status != ServiceRequest.Status.REQUESTED:
            raise InvalidStateError("Esta solicitud ya fue decidida")
        to_charge = extra or request.extra
        if to_charge is not None:
            folio = get_or_create_folio(request.reservation)
            units = _quantity(quantity, request.quantity)
            charge = post_extra_charge(folio, to_charge, quantity=units, actor=actor, source="user")
            request.charge, request.extra, request.quantity = charge, to_charge, units
            request.price = charge.amount + charge.tax_amount
        return _decide(
            request,
            status=ServiceRequest.Status.APPROVED,
            actor=actor,
            note=note,
            action="guestportal.request_approved",
            summary=f"Aprobó «{request.get_kind_display()}» de {request.reservation.code}",
        )


def reject_request(request, *, actor, reason="") -> ServiceRequest:
    with transaction.atomic():
        request = _locked(request)
        if request.status != ServiceRequest.Status.REQUESTED:
            raise InvalidStateError("Esta solicitud ya fue decidida")
        return _decide(
            request,
            status=ServiceRequest.Status.REJECTED,
            actor=actor,
            note=reason,
            action="guestportal.request_rejected",
            summary=f"Rechazó «{request.get_kind_display()}» de {request.reservation.code}",
        )


def complete_request(request, *, actor) -> ServiceRequest:
    with transaction.atomic():
        request = _locked(request)
        if request.status != ServiceRequest.Status.APPROVED:
            raise InvalidStateError("Solo se marcan como realizadas las solicitudes aprobadas")
        request.status = ServiceRequest.Status.DONE
        request.save(update_fields=["status", "updated_at"])
        audit.record(
            action="guestportal.request_done",
            target=request,
            summary=f"Marcó como realizada «{request.get_kind_display()}» de {request.reservation.code}",
            actor=actor,
            property=request.reservation.property,
            changes={"status": "done"},
        )
    return request


def requests_of(reservation) -> list[dict]:
    return [
        request_payload(request)
        for request in ServiceRequest.objects.filter(reservation=reservation).select_related("extra")
    ]
