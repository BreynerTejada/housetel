"""Signed reservation tokens for the guest portal magic link (plan §C; expiry added in plan P1).

A token carries the reservation id (`r`) and, since the pilot, an expiry date (`exp`): the reservation's
check-out plus `PORTAL_TOKEN_DAYS_AFTER_CHECKOUT` (30) days. Tokens signed before the expiry existed (no
`exp`) stay valid. Changing the stay dates changes the token, but links already sent keep working until their
own `exp`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from django.core import signing
from django.utils import timezone

from apps.core.runtime import public_base_url

if TYPE_CHECKING:  # bookings is imported lazily: core must not depend on it at import time
    from apps.bookings.models import Reservation

SALT = "housetel.reservation"
PORTAL_TOKEN_DAYS_AFTER_CHECKOUT = 30


def token_expiry(reservation) -> date | None:
    """Last day the portal link of `reservation` works (check-out + 30 days), or None without dates."""
    checkout = getattr(reservation, "checkout_date", None)
    return checkout + timedelta(days=PORTAL_TOKEN_DAYS_AFTER_CHECKOUT) if checkout else None


def make_reservation_token(reservation) -> str:
    payload = {"r": str(reservation.pk)}
    expiry = token_expiry(reservation)
    if expiry:
        payload["exp"] = expiry.isoformat()
    return signing.dumps(payload, salt=SALT, compress=True)


def _expired(payload: dict) -> bool:
    raw = payload.get("exp")
    if raw is None:
        return False  # issued before tokens expired: still valid
    try:
        expiry = date.fromisoformat(str(raw))
    except ValueError:
        return True
    return timezone.localdate() > expiry


def read_reservation_token(token: str, *, max_age: int | None = None) -> Reservation | None:
    """The Reservation (with its property) for a valid token; None if tampered, expired (its `exp` date or
    `max_age` seconds) or unknown."""
    from apps.bookings.models import Reservation

    try:
        data = signing.loads(token, salt=SALT, max_age=max_age)
    except signing.BadSignature:
        return None
    if not isinstance(data, dict) or _expired(data):
        return None
    return Reservation.objects.select_related("property").filter(pk=data.get("r")).first()


def portal_url(reservation) -> str:
    """`{public_base_url}/g/{token}`: FRONTEND_URL, or PUBLIC_BASE_URL (e.g. a tunnel) when set, so the links
    that reach guests by e-mail or WhatsApp open from their phones."""
    return f"{public_base_url()}/g/{make_reservation_token(reservation)}"
