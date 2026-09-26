"""Date helpers. Stay ranges are half-open: checkin inclusive, checkout exclusive."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone


def daterange(start: date, end_exclusive: date) -> Iterator[date]:
    current = start
    while current < end_exclusive:
        yield current
        current += timedelta(days=1)


def nights(checkin: date, checkout: date) -> list[date]:
    return list(daterange(checkin, checkout))


def overlaps(a_start: date, a_end: date, b_start: date, b_end: date) -> bool:
    """Half-open overlap: [a_start, a_end) ∩ [b_start, b_end) ≠ ∅."""
    return a_start < b_end and b_start < a_end


def property_now(property) -> datetime:
    """Current aware datetime in the property's timezone."""
    return timezone.now().astimezone(ZoneInfo(property.timezone or "America/Bogota"))
