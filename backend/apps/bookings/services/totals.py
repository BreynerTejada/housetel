"""Reservation-level aggregates kept in sync with the stays."""

from datetime import date
from decimal import Decimal

from apps.bookings.models import Stay
from apps.bookings.services.pricing import money_str

VOID_STATUSES = ("cancelled", "no_show")


def refresh_reservation(reservation) -> dict:
    """Recompute the reservation's dates, guests and total from its stays; returns what changed as
    `{field: [old, new]}` with JSON-friendly values (ISO dates, 2-decimal money strings).

    Dates and guests follow the stays that are still alive (a room cancelled on its own no longer moves the
    arrival or counts its guests; a fully cancelled reservation keeps them all). The total is always the sum
    of every stay, cancelled ones included (as documented for B2b: balances come from
    `finance.reservation_balance`, which only counts the billable stays)."""
    stays = list(Stay.objects.filter(reservation=reservation))
    if not stays:
        return {}
    live = [stay for stay in stays if stay.status not in VOID_STATUSES] or stays
    values = {
        "checkin_date": min(stay.checkin_date for stay in live),
        "checkout_date": max(stay.checkout_date for stay in live),
        "adults": sum(stay.adults for stay in live),
        "children": sum(stay.children for stay in live),
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
