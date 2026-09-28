"""What the staff sees and does with the guest portal: online check-in data of a reservation, the day's
arrivals with their check-in status, the magic link (+ QR) and sending it with `messaging.send_message`."""

import base64
import io
import logging

import qrcode

from apps.bookings.models import ACTIVE_STAY_STATUSES, Reservation
from apps.bookings.types import InvalidStateError
from apps.core import audit
from apps.core.tokens import portal_url
from apps.guestportal.models import OnlineCheckin
from apps.guestportal.services.access import checkin_of, checkin_window, portal_settings
from apps.guestportal.services.checkin import (
    guest_slots,
    is_adult,
    missing_items,
    slot_complete,
    travel_of,
)
from apps.guestportal.services.requests import requests_of
from apps.guestportal.services.summary import stays_of
from apps.guests.models import GuestDocument
from apps.messaging.services import send_message

logger = logging.getLogger("housetel.guestportal")

CHECKIN_TEMPLATE = "checkin_invitation"
INACTIVE_STAY_STATUSES = ("cancelled", "no_show")


def _identity(guest) -> dict:
    return {
        "first_name": guest.first_name,
        "last_name": guest.last_name,
        "full_name": guest.full_name,
        "document_type": guest.document_type,
        "document_number": guest.document_number,
        "nationality": guest.nationality,
        "country_of_residence": guest.country_of_residence,
        "city_of_residence": guest.city_of_residence,
        "birth_date": guest.birth_date.isoformat() if guest.birth_date else None,
        "email": guest.email,
        "phone": guest.phone,
        "is_foreign_non_resident": guest.is_foreign_non_resident,
    }


def signature_url(reservation) -> str:
    return f"/api/v1/guestportal/reservations/{reservation.pk}/checkin/signature/"


def staff_checkin_detail(reservation) -> dict:
    """Everything the online check-in collected, for the reservation's "Check-in online" tab. Identity
    documents are read through B3's authenticated endpoint (`file_url`), the signature through ours."""
    settings = portal_settings(reservation.property)
    checkin = checkin_of(reservation)
    # after departure (or a cancellation) the registration is still what the hotel keeps: the stays that
    # happened, else every stay of the booking
    stays = stays_of(reservation)
    slots = guest_slots(reservation, [s for s in stays if s.status not in INACTIVE_STAY_STATUSES] or stays)
    guest_ids = [slot.guest.pk for slot in slots if slot.guest]
    documents: dict = {}
    for document in GuestDocument.objects.filter(guest_id__in=guest_ids).exclude(kind="signature"):
        documents.setdefault(document.guest_id, []).append(
            {
                "id": str(document.pk),
                "kind": document.kind,
                "uploaded_via": document.uploaded_via,
                "created_at": document.created_at.isoformat(),
                "file_url": f"/api/v1/guests/documents/{document.pk}/file/",
            }
        )
    url = portal_url(reservation)
    return {
        "reservation_id": str(reservation.pk),
        "code": reservation.code,
        "status": checkin.status if checkin else OnlineCheckin.Status.NOT_STARTED,
        "current_step": checkin.current_step if checkin else OnlineCheckin.Step.GUESTS,
        "completed_at": checkin.completed_at.isoformat() if checkin and checkin.completed_at else None,
        "accepted_terms_at": checkin.accepted_terms_at.isoformat()
        if checkin and checkin.accepted_terms_at
        else None,
        "eta": checkin.eta.strftime("%H:%M") if checkin and checkin.eta else None,
        "ip": checkin.ip if checkin else None,
        "user_agent": checkin.user_agent if checkin else "",
        "signature_url": signature_url(reservation) if checkin and checkin.signature else None,
        "window": checkin_window(reservation, settings).as_dict(),
        "guests": [
            {
                "slot": slot.index,
                "stay_id": str(slot.stay.pk),
                "role": slot.role,
                "guest_id": str(slot.guest.pk) if slot.guest else None,
                "complete": slot_complete(slot, checkin),
                "is_adult": is_adult(slot.guest, reservation.checkin_date) if slot.guest else not slot.child,
                "data": _identity(slot.guest) if slot.guest else {},
                "travel": travel_of(checkin, slot.guest),
                "documents": documents.get(slot.guest.pk, []) if slot.guest else [],
            }
            for slot in slots
        ],
        "missing": missing_items(reservation, checkin, settings, slots),
        "requests": requests_of(reservation),
        "portal_url": url,
        "checkin_url": f"{url}/checkin",
    }


def arrivals_checkins(prop, day) -> list[dict]:
    """Arrivals of `day` (tentative, confirmed or already in) with their online check-in status; completed
    first, then by ETA."""
    reservations = (
        Reservation.objects.filter(property=prop, checkin_date=day, status__in=ACTIVE_STAY_STATUSES)
        .select_related("booker", "online_checkin")
        .order_by("booker__last_name", "code")
    )
    rows = []
    for reservation in reservations:
        checkin = getattr(reservation, "online_checkin", None)
        eta = (checkin.eta if checkin and checkin.eta else None) or reservation.eta
        rows.append(
            {
                "reservation_id": str(reservation.pk),
                "code": reservation.code,
                "status": reservation.status,
                "guest_name": reservation.booker.full_name,
                "is_vip": reservation.booker.is_vip,
                "adults": reservation.adults,
                "children": reservation.children,
                "checkin_status": checkin.status if checkin else OnlineCheckin.Status.NOT_STARTED,
                "completed_at": checkin.completed_at.isoformat()
                if checkin and checkin.completed_at
                else None,
                "eta": eta.strftime("%H:%M") if eta else None,
            }
        )
    rows.sort(key=lambda row: (row["checkin_status"] != "completed", row["eta"] or "99:99"))
    return rows


def qr_data_url(text: str) -> str:
    image = qrcode.make(text, box_size=8, border=2)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def portal_link(reservation) -> dict:
    url = portal_url(reservation)
    return {"url": url, "checkin_url": f"{url}/checkin", "qr_png": qr_data_url(url)}


def send_checkin_link(reservation, *, channels, actor) -> dict:
    """Send the magic link with the `checkin_invitation` template (C6) to the booker. A delivery failure never
    loses the link: the staff can still copy it (`send_error`)."""
    if reservation.status in INACTIVE_STAY_STATUSES:
        raise InvalidStateError("Esta reserva ya no está activa: no hay check-in online que enviar")
    channels = tuple(dict.fromkeys(channel for channel in channels if channel in ("email", "whatsapp"))) or (
        "email",
    )
    url = portal_url(reservation)
    context = {"portal_url": url, "checkin_url": f"{url}/checkin"}
    result = {"url": url, "checkin_url": context["checkin_url"], "messages": []}
    try:
        messages = send_message(
            property=reservation.property,
            template_code=CHECKIN_TEMPLATE,
            guest=reservation.booker,
            reservation=reservation,
            channels=channels,
            context=context,
            language=reservation.language or None,
        )
    except Exception as exc:  # noqa: BLE001 - messaging errors must not break the staff action
        logger.exception("send_checkin_link failed for %s", reservation.pk)
        result["send_error"] = str(exc)[:300]
        messages = []
    result["messages"] = [
        {"channel": m.channel, "to": m.to, "status": m.status, "error": m.error} for m in messages
    ]
    audit.record(
        action="guestportal.link_sent",
        target=reservation,
        summary=f"Envió el link de check-in online de {reservation.code}",
        actor=actor,
        property=reservation.property,
        changes={"channels": list(channels), "sent": len(messages)},
    )
    return result
