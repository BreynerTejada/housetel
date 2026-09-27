"""Reservation-level aggregates kept in sync with the stays."""

from datetime import date
from decimal import Decimal

from apps.bookings.models import Stay
from apps.bookings.services.pricing import money_str


def refresh_reservation(reservation) -> dict:
    """Recompute the reservation's dates, guests and total from its stays; returns what changed as
    `{field: [old, new]}` with JSON-friendly values (ISO dates, 2-decimal money strings)."""
    stays = list(Stay.objects.filter(reservation=reservation))
    if not stays:
        return {}
    values = {
        "checkin_date": min(stay.checkin_date for stay in stays),
        "checkout_date": max(stay.checkout_date for stay in stays),
        "adults": sum(stay.adults for stay in stays),
        "children": sum(stay.children for stay in stays),
        "total_amount": sum((stay.total_amount for stay in stays), Decimal("0")),
    }
    changes = {}
    for name, value in values.items():
        old = getattr(reservation, name)
        if old != value:
            changes[name] = [plain(old), plain(value)]
            setattr(reservation, name, value)
    if changes:
        reservation.save(update_fields=[*values, "updated_at"])
    return changes


def plain(value):
    if isinstance(value, Decimal):
        return money_str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
