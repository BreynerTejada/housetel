"""Phase A availability (plan Step 5): correct but slow — active units − overlapping active stays − blocks,
minimum over the nights. Units are rooms (private) or beds (dorm)."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.bookings.services.availability import availability
from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.tests.factories import PropertyFactory
from apps.inventory.models import RoomBlock
from apps.inventory.tests.factories import BedFactory, DormRoomTypeFactory, RoomFactory, RoomTypeFactory

pytestmark = pytest.mark.django_db

OCT = lambda day: date(2026, 10, day)  # noqa: E731


@pytest.fixture
def hotel(prop):
    private = RoomTypeFactory(property=prop, code="DBL")
    rooms = [RoomFactory(room_type=private, number=str(n)) for n in (101, 102, 103)]
    RoomFactory(room_type=private, number="199", is_active=False)
    dorm_type = DormRoomTypeFactory(property=prop, code="DORM")
    dorm = RoomFactory(room_type=dorm_type, number="D1")
    beds = [BedFactory(room=dorm, label=label) for label in "ABCD"]
    BedFactory(room=dorm, label="X", is_active=False)
    return {
        "prop": prop,
        "private": private,
        "rooms": rooms,
        "dorm_type": dorm_type,
        "dorm": dorm,
        "beds": beds,
    }


def book(room_type, checkin, checkout, *, status="confirmed", room=None, bed=None):
    reservation = ReservationFactory(
        property=room_type.property, checkin_date=checkin, checkout_date=checkout, status=status
    )
    return StayFactory(reservation=reservation, room_type=room_type, room=room, bed=bed, status=status)


CHECKIN, CHECKOUT = OCT(1), OCT(4)


def avail(hotel, checkin=CHECKIN, checkout=CHECKOUT, **kwargs):
    return availability(property=hotel["prop"], checkin=checkin, checkout=checkout, **kwargs)


def test_empty_hotel_counts_active_rooms_and_active_dorm_beds(hotel):
    assert avail(hotel) == {hotel["private"].pk: 3, hotel["dorm_type"].pk: 4}


def test_active_stays_reduce_availability_assigned_or_not(hotel):
    book(hotel["private"], OCT(1), OCT(4), room=hotel["rooms"][0])
    book(hotel["private"], OCT(2), OCT(3))
    book(hotel["dorm_type"], OCT(1), OCT(2), room=hotel["dorm"], bed=hotel["beds"][0])
    assert avail(hotel) == {hotel["private"].pk: 1, hotel["dorm_type"].pk: 3}


@pytest.mark.parametrize("status", ["cancelled", "no_show", "checked_out"])
def test_inactive_stays_do_not_count(hotel, status):
    book(hotel["private"], OCT(1), OCT(4), status=status)
    assert avail(hotel)[hotel["private"].pk] == 3


def test_it_is_the_minimum_over_the_nights_and_checkout_day_is_free(hotel):
    book(hotel["private"], OCT(2), OCT(3))
    book(hotel["private"], OCT(2), OCT(3))
    book(hotel["private"], OCT(4), OCT(6))  # arrives on our checkout day
    assert avail(hotel)[hotel["private"].pk] == 1
    assert avail(hotel, OCT(3), OCT(4))[hotel["private"].pk] == 3


def test_blocks_reduce_availability_until_released(hotel):
    room_block = RoomBlock.objects.create(
        room=hotel["rooms"][0], start_date=OCT(3), end_date=OCT(5), kind="maintenance"
    )
    RoomBlock.objects.create(
        room=hotel["rooms"][1],
        start_date=OCT(1),
        end_date=OCT(2),
        kind="maintenance",
        released_at=timezone.now(),
    )
    RoomBlock.objects.create(
        room=hotel["dorm"], bed=hotel["beds"][0], start_date=OCT(1), end_date=OCT(9), kind="out_of_order"
    )
    assert avail(hotel) == {hotel["private"].pk: 2, hotel["dorm_type"].pk: 3}
    room_block.released_at = timezone.now()
    room_block.save()
    assert avail(hotel)[hotel["private"].pk] == 3


def test_blocking_a_whole_dorm_room_blocks_all_its_active_beds(hotel):
    RoomBlock.objects.create(room=hotel["dorm"], start_date=OCT(1), end_date=OCT(2), kind="maintenance")
    assert avail(hotel)[hotel["dorm_type"].pk] == 0


def test_overbooking_shows_as_negative(hotel):
    for _ in range(4):
        book(hotel["private"], OCT(1), OCT(2))
    assert avail(hotel)[hotel["private"].pk] == -1


def test_filters_by_room_type_and_skips_inactive_types(hotel):
    RoomTypeFactory(property=hotel["prop"], code="OLD", is_active=False)
    assert avail(hotel, room_type_ids=[hotel["dorm_type"].pk]) == {hotel["dorm_type"].pk: 4}
    assert len(avail(hotel)) == 2


def test_other_properties_are_ignored(hotel, organization):
    other_type = RoomTypeFactory(property=PropertyFactory(organization=organization))
    RoomFactory(room_type=other_type)
    book(other_type, OCT(1), OCT(3))
    assert other_type.pk not in avail(hotel)


def test_invalid_range_means_nothing_available(hotel):
    assert avail(hotel, OCT(3), OCT(3)) == {hotel["private"].pk: 0, hotel["dorm_type"].pk: 0}


def test_long_ranges_work(hotel):
    start = OCT(1)
    assert avail(hotel, start, start + timedelta(days=90))[hotel["private"].pk] == 3
