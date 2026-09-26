"""Signed reservation tokens for the guest portal magic link (plan §C)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core import signing

if TYPE_CHECKING:  # bookings is imported lazily: core must not depend on it at import time
    from apps.bookings.models import Reservation

SALT = "housetel.reservation"


def make_reservation_token(reservation) -> str:
    return signing.dumps({"r": str(reservation.pk)}, salt=SALT, compress=True)


def read_reservation_token(token: str, *, max_age: int | None = None) -> Reservation | None:
    """The Reservation (with its property) for a valid token; None if tampered, expired or unknown."""
    from apps.bookings.models import Reservation

    try:
        data = signing.loads(token, salt=SALT, max_age=max_age)
    except signing.BadSignature:
        return None
    return Reservation.objects.select_related("property").filter(pk=data.get("r")).first()


def portal_url(reservation) -> str:
    return f"{settings.FRONTEND_URL}/g/{make_reservation_token(reservation)}"
