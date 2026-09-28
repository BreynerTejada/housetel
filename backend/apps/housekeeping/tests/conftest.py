"""Fixtures of the housekeeping tests: a small hotel on three floors plus a dorm.

- DBL (30 min of housekeeping): rooms 101, 102 (floor 1), 201, 202 (floor 2).
- STE (60 min): room 301 (floor 3).
- DORM (20 min per room): room D1 (floor 1) with beds A–C.
- Business date 2026-10-01.
"""

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory

BUSINESS_DATE = date(2026, 10, 1)


def day(offset: int) -> date:
    return BUSINESS_DATE + timedelta(days=offset)


@pytest.fixture
def hotel(prop):
    from apps.inventory.tests.factories import BedFactory, DormRoomTypeFactory, RoomFactory, RoomTypeFactory

    prop.business_date = BUSINESS_DATE
    prop.save(update_fields=["business_date", "updated_at"])
    dbl = RoomTypeFactory(property=prop, code="DBL", housekeeping_minutes=30, sort_order=1)
    ste = RoomTypeFactory(property=prop, code="STE", housekeeping_minutes=60, sort_order=2)
    dorm = DormRoomTypeFactory(property=prop, code="DORM", housekeeping_minutes=20, sort_order=3)
    rooms = {
        "101": RoomFactory(room_type=dbl, number="101", floor="1", sort_order=1),
        "102": RoomFactory(room_type=dbl, number="102", floor="1", sort_order=2),
        "201": RoomFactory(room_type=dbl, number="201", floor="2", sort_order=3),
        "202": RoomFactory(room_type=dbl, number="202", floor="2", sort_order=4),
        "301": RoomFactory(room_type=ste, number="301", floor="3", sort_order=5),
        "D1": RoomFactory(room_type=dorm, number="D1", floor="1", sort_order=6),
    }
    beds = {label: BedFactory(room=rooms["D1"], label=label) for label in "ABC"}
    return SimpleNamespace(prop=prop, dbl=dbl, ste=ste, dorm=dorm, rooms=rooms, beds=beds)


@pytest.fixture
def private_media(settings, tmp_path):
    """Ticket photos go to a temporary private root (and public media to another one) during the test."""
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


JPEG = b"\xff\xd8\xff\xe0" + b"0" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


def make_stay(hotel, room, *, checkin, checkout, status="checked_in", bed=None, room_type=None, **kwargs):
    """A stay (and its reservation) in `room` without going through the booking services."""
    reservation = ReservationFactory(
        property=hotel.prop, status=status, checkin_date=checkin, checkout_date=checkout, **kwargs
    )
    return StayFactory(
        reservation=reservation,
        room_type=room_type or room.room_type,
        room=room,
        bed=bed,
        status=status,
    )
