"""What the confirmation page shows: an online booking looked up by its code and the booker's email.

Only marketplace and booking-engine reservations are exposed (staff bookings reach the guest through the
portal link). A code that does not exist and a wrong email answer the same 404.
"""

from collections import OrderedDict
from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone

from apps.bookings.models import Reservation
from apps.bookings.services.pricing import lodging_tax, tax_exempt
from apps.core.dates import nights as stay_nights
from apps.core.errors import NotFoundError
from apps.core.money import D
from apps.core.tokens import portal_url
from apps.finance import services as finance
from apps.finance.models import Charge, Payment, PaymentIntent, Refund
from apps.marketplace.services.checkout import confirmation_path
from apps.marketplace.services.engine import brand
from apps.marketplace.services.offers import money

ONLINE_SOURCES = (Reservation.Source.MARKETPLACE, Reservation.Source.BOOKING_ENGINE)
OPEN_LINK_STATUSES = (PaymentIntent.Status.CREATED, PaymentIntent.Status.PENDING)


def find_online_booking(code: str, email: str) -> Reservation:
    reservation = (
        Reservation.objects.select_related("property", "booker")
        .filter(code__iexact=(code or "").strip(), source__in=ONLINE_SOURCES)
        .first()
    )
    if reservation is None or (reservation.booker.email or "").lower() != (email or "").strip().lower():
        raise NotFoundError("No encontramos una reserva con ese código y ese correo")
    return reservation


def _rooms(reservation) -> list[dict]:
    """Stays grouped by category and plan (a dorm booking for N guests is N one-bed stays)."""
    groups: OrderedDict = OrderedDict()
    stays = reservation.stays.select_related("room_type", "rate_plan").exclude(
        status__in=["cancelled", "no_show"]
    )
    for stay in stays.order_by("created_at"):
        key = (stay.room_type_id, stay.rate_plan_id)
        group = groups.setdefault(
            key,
            {
                "room_type_name": stay.room_type.name or {},
                "room_type_kind": stay.room_type.kind,
                "rate_plan_name": stay.rate_plan.name or {},
                "meal_plan": stay.rate_plan.meal_plan,
                "units": 0,
                "adults": 0,
                "children": 0,
                "total": Decimal("0"),
            },
        )
        group["units"] += 1
        group["adults"] += stay.adults
        group["children"] += stay.children
        group["total"] += D(stay.total_amount)
    return [{**group, "total": money(group["total"])} for group in groups.values()]


def _payment(reservation) -> dict | None:
    intent = PaymentIntent.objects.filter(folio__reservation=reservation).order_by("-created_at").first()
    if intent is None:
        return None
    stale = finance.intent_is_stale(intent)
    status = PaymentIntent.Status.EXPIRED if stale else intent.status
    open_link = intent.status in OPEN_LINK_STATUSES and not stale
    return {
        "reference": intent.reference,
        "status": status,
        "amount": money(intent.amount),
        "checkout_url": intent.checkout_url if open_link else None,
        "expires_at": intent.expires_at.isoformat() if intent.expires_at else None,
    }


def booking_status(code: str, email: str) -> dict:
    reservation = find_online_booking(code, email)
    prop, booker = reservation.property, reservation.booker
    balance = finance.reservation_balance(reservation)
    paid = Payment.objects.filter(folio__reservation=reservation, status=Payment.Status.APPROVED).aggregate(
        total=Sum("amount")
    )["total"] or Decimal("0")
    refunded = Refund.objects.filter(
        payment__folio__reservation=reservation, status=Refund.Status.APPROVED
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    extras = Charge.objects.filter(
        folio__reservation=reservation, kind=Charge.Kind.EXTRA, voided_at__isnull=True
    ).order_by("created_at")
    via = reservation.source
    return {
        "code": reservation.code,
        "status": reservation.status,
        "via": via,
        "property": {
            "slug": prop.slug,
            "name": prop.name,
            "city": prop.city,
            "address": prop.address,
            "phone": prop.phone,
            "email": prop.email,
            "timezone": prop.timezone,
            "check_in_time": prop.check_in_time.strftime("%H:%M") if prop.check_in_time else None,
            "check_out_time": prop.check_out_time.strftime("%H:%M") if prop.check_out_time else None,
            **brand(prop),
        },
        "checkin": reservation.checkin_date.isoformat(),
        "checkout": reservation.checkout_date.isoformat(),
        "nights": len(stay_nights(reservation.checkin_date, reservation.checkout_date)),
        "adults": reservation.adults,
        "children": reservation.children,
        "currency": reservation.currency,
        "booker": {"first_name": booker.first_name, "last_name": booker.last_name, "email": booker.email},
        "rooms": _rooms(reservation),
        "extras": [
            {"description": charge.description, "quantity": charge.quantity, "total": money(charge.total)}
            for charge in extras
        ],
        "total": money(balance + paid - refunded),
        "paid": money(paid),
        "balance": money(balance),
        "tax_exempt": tax_exempt(lodging_tax(prop), booker.is_foreign_non_resident),
        "cancellation_policy": reservation.cancellation_policy_snapshot or None,
        "hold_expires_at": reservation.hold_expires_at.isoformat() if reservation.hold_expires_at else None,
        "special_requests": reservation.special_requests,
        "eta": reservation.eta.strftime("%H:%M") if reservation.eta else None,
        "payment": _payment(reservation),
        "portal_url": portal_url(reservation),
        "confirmation_path": confirmation_path(prop, via, reservation.code),
        "created_at": timezone.localtime(reservation.created_at).isoformat(),
    }
