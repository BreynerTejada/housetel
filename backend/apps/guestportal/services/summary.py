"""What the guest sees on the portal home (`GET /api/v1/public/guestportal/<token>/`).

Only data that belongs to the booking and is useful to the guest: never staff notes, audit trails, other
reservations or identity numbers (the check-in step shows the booker's own data, see `checkin.py`)."""

import logging
from decimal import Decimal

from django.apps import apps as django_apps
from django.db.models import Prefetch, Sum

from apps.bookings.models import Stay
from apps.core import integrations
from apps.core.money import quantize
from apps.core.runtime import simulations_enabled
from apps.guestportal.services.access import checkin_of, checkin_window, portal_settings
from apps.inventory.models import Photo

ZERO = Decimal("0")
MESSAGES_SHOWN = 20
HIDDEN_CHANNELS = ("internal_note",)
logger = logging.getLogger("housetel.guestportal")


def money(value) -> str:
    return f"{Decimal(value or 0):.2f}"


def payments_enabled(prop) -> bool:
    """Whether the portal offers "Pagar": the payments integration is on and, where simulations are off
    (production), really live (real mode and configured, `core.integrations.is_live`). Same rule as the
    marketplace checkout (plan P6): a hotel without its Wompi keys never shows a button that cannot work."""
    if not simulations_enabled():
        return integrations.is_live(prop, "payments")
    return integrations.get_setting(prop, "payments").enabled


def balance_of(reservation) -> dict:
    """`due` = what the guest side still owes (`finance.guest_part`: includes nights not yet posted, and never
    the part billed to a company — P4/P-INT: the portal pays the guest's folio, so a company's part, with or
    without credit, is settled by the company); `paid` = approved payments − approved refunds of the guest
    side's folios; `total` = due + paid. Without companies it is exactly `finance.reservation_balance`."""
    from apps.finance.models import Folio, Payment, Refund
    from apps.finance.services import guest_part

    currency = reservation.currency
    due = quantize(guest_part(reservation), currency)
    company = Folio.FolioType.COMPANY
    payments = (
        Payment.objects.filter(folio__reservation=reservation, status=Payment.Status.APPROVED)
        .exclude(folio__folio_type=company)
        .aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    refunds = (
        Refund.objects.filter(payment__folio__reservation=reservation, status=Refund.Status.APPROVED)
        .exclude(payment__folio__folio_type=company)
        .aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    paid = quantize(payments - refunds, currency)
    return {
        "total": money(due + paid),
        "paid": money(paid),
        "due": money(due),
        "currency": currency,
        "can_pay": due > 0 and payments_enabled(reservation.property),
    }


def _time(value) -> str | None:
    return value.strftime("%H:%M") if value else None


def property_payload(prop) -> dict:
    branding = prop.branding or {}
    photo = Photo.objects.filter(property=prop, room_type=None, room=None).order_by(
        "sort_order", "created_at"
    )
    first = photo.first()
    return {
        "name": prop.name,
        "slug": prop.slug,
        "city": prop.city,
        "address": prop.address,
        "phone": prop.phone,
        "email": prop.email,
        "website": prop.website,
        "check_in_time": _time(prop.check_in_time),
        "check_out_time": _time(prop.check_out_time),
        "timezone": prop.timezone,
        "currency": prop.currency,
        "default_language": prop.default_language,
        "primary_color": branding.get("primary_color", ""),
        "logo": branding.get("logo", ""),
        "photo": first.image.url if first else None,
        "house_rules": prop.house_rules or {},
    }


def stays_of(reservation) -> list[Stay]:
    return list(
        Stay.objects.filter(reservation=reservation)
        .select_related("room_type", "rate_plan", "room")
        .prefetch_related(
            Prefetch("room_type__photos", queryset=Photo.objects.order_by("sort_order", "created_at")),
            "occupants",
        )
        .order_by("checkin_date", "created_at")
    )


def stay_payload(stay) -> dict:
    photos = list(stay.room_type.photos.all())
    in_house = stay.status == Stay.Status.CHECKED_IN
    return {
        "id": str(stay.pk),
        "status": stay.status,
        "checkin_date": stay.checkin_date.isoformat(),
        "checkout_date": stay.checkout_date.isoformat(),
        "nights": (stay.checkout_date - stay.checkin_date).days,
        "adults": stay.adults,
        "children": stay.children,
        "room_type": {
            "id": str(stay.room_type_id),
            "code": stay.room_type.code,
            "name": stay.room_type.name,
            "kind": stay.room_type.kind,
            "photo": photos[0].image.url if photos else None,
        },
        "rate_plan": {
            "id": str(stay.rate_plan_id),
            "code": stay.rate_plan.code,
            "name": stay.rate_plan.name,
            "meal_plan": stay.rate_plan.meal_plan,
        },
        # the room number is shared only once the guest is in the house
        "room": {"number": stay.room.number} if in_house and stay.room_id else None,
        "total_amount": money(stay.total_amount),
    }


def guests_payload(reservation, stays) -> list[dict]:
    booker = reservation.booker
    guests = [
        {
            "id": str(booker.pk),
            "first_name": booker.first_name,
            "full_name": booker.full_name,
            "role": "booker",
            "stay_id": None,
        }
    ]
    seen = {booker.pk}
    for stay in stays:
        for occupant in stay.occupants.all():
            if occupant.pk in seen:
                continue
            seen.add(occupant.pk)
            guests.append(
                {
                    "id": str(occupant.pk),
                    "first_name": occupant.first_name,
                    "full_name": occupant.full_name,
                    "role": "occupant",
                    "stay_id": str(stay.pk),
                }
            )
    return guests


def payments_of(reservation) -> list[dict]:
    """Approved payments of the booking, oldest first: the guest's receipt (refunds are netted in
    `balance.paid`)."""
    from apps.finance.models import Payment

    payments = Payment.objects.filter(
        folio__reservation=reservation, status=Payment.Status.APPROVED
    ).order_by("business_date", "created_at")
    return [
        {"date": payment.business_date.isoformat(), "method": payment.method, "amount": money(payment.amount)}
        for payment in payments
    ]


def messages_of(reservation) -> list[dict]:
    """The conversation about this booking (C6 `messaging.Message`: confirmation, pre-arrival, replies of the
    front desk and what the guest wrote), oldest first. Internal notes and failed deliveries are never shown,
    nor who on the staff wrote. Read-only through the ORM; empty while messaging has no such model."""
    try:
        message_model = django_apps.get_model("messaging", "Message")
    except LookupError:
        return []
    try:
        rows = list(
            message_model.objects.filter(reservation=reservation)
            .exclude(channel__in=HIDDEN_CHANNELS)
            .exclude(status="failed")
            .order_by("-created_at")
            .values("id", "direction", "channel", "subject", "body", "created_at")[:MESSAGES_SHOWN]
        )
    except Exception:  # noqa: BLE001 - the portal never breaks because of another app's schema
        logger.exception("guest portal could not read the messages of %s", reservation.pk)
        return []
    return [
        {
            "id": str(row["id"]),
            "direction": "in" if row["direction"] == "in" else "out",
            "channel": row["channel"],
            "subject": row["subject"] or "",
            "body": row["body"] or "",
            "created_at": row["created_at"].isoformat(),
        }
        for row in reversed(rows)
    ]


def reservation_payload(reservation) -> dict:
    return {
        "code": reservation.code,
        "status": reservation.status,
        "source": reservation.source,
        "channel_code": reservation.channel_code,
        "checkin_date": reservation.checkin_date.isoformat(),
        "checkout_date": reservation.checkout_date.isoformat(),
        "nights": (reservation.checkout_date - reservation.checkin_date).days,
        "adults": reservation.adults,
        "children": reservation.children,
        "currency": reservation.currency,
        "total_amount": money(reservation.total_amount),
        "eta": _time(reservation.eta),
        "language": reservation.language,
        "cancelled_at": reservation.cancelled_at.isoformat() if reservation.cancelled_at else None,
        "cancellation_fee": money(reservation.cancellation_fee),
    }


def checkin_summary(reservation, settings) -> dict:
    checkin = checkin_of(reservation)
    window = checkin_window(reservation, settings)
    return {
        "status": checkin.status if checkin else "not_started",
        "current_step": checkin.current_step if checkin else "guests",
        "completed_at": checkin.completed_at.isoformat() if checkin and checkin.completed_at else None,
        **window.as_dict(),
    }


def portal_summary(reservation) -> dict:
    prop = reservation.property
    settings = portal_settings(prop)
    stays = stays_of(reservation)
    from apps.guestportal.services.manage import cancellation_preview, modification_rules
    from apps.guestportal.services.requests import portal_extras, requests_of

    return {
        "today": prop.business_date.isoformat(),
        "property": property_payload(prop),
        "reservation": reservation_payload(reservation),
        "stays": [stay_payload(stay) for stay in stays],
        "guests": guests_payload(reservation, stays),
        "balance": balance_of(reservation),
        "payments": payments_of(reservation),
        "checkin": checkin_summary(reservation, settings),
        "extras": portal_extras(reservation),
        "requests": requests_of(reservation),
        "messages": messages_of(reservation),
        "cancellation": cancellation_preview(reservation),
        "modification": modification_rules(reservation),
        "settings": {"auto_approve_extras": settings.auto_approve_extras},
    }
