"""Finishing touches of the bookings seed on today's arrivals (plan B2b › Seed: "llegadas de hoy, algunas con
habitación limpia y lista, otras sin asignar"), checked on small hand-made scenarios instead of the random
demo: at least two arrivals, one without room and one in a ready room, whatever the dice said."""

import random
from datetime import timedelta

import pytest

from apps.bookings.models import Stay
from apps.bookings.seed import PropertySeeder
from apps.bookings.services.reservations import check_in
from apps.bookings.tests.helpers import book, oct_
from apps.core.seed import SeedContext
from apps.inventory.models import Room

pytestmark = pytest.mark.django_db

READY = ("clean", "inspected")


def finish(hotel, seed=3):
    ctx = SeedContext(today=oct_(1), rng=random.Random(seed), properties={"aurora": hotel.prop})
    seeder = PropertySeeder(ctx, "aurora", hotel.prop, random.Random(seed))
    seeder._todays_arrivals()
    seeder._room_statuses()


def arrivals(hotel):
    return list(
        Stay.objects.filter(reservation__property=hotel.prop, checkin_date=oct_(1)).select_related("room")
    )


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_when_every_arrival_has_a_room_one_is_left_for_the_auto_assignment(hotel, seed):
    for number in ("101", "102", "201"):
        book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms[number].pk})
    Room.objects.filter(property=hotel.prop).update(housekeeping_status="dirty")

    finish(hotel, seed)

    stays = arrivals(hotel)
    assert any(stay.room is None for stay in stays)
    assert any(stay.room is not None and stay.room.housekeeping_status in READY for stay in stays)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_when_no_arrival_has_a_room_one_gets_a_ready_room(hotel, seed):
    book(hotel, oct_(1), oct_(2))
    book(hotel, oct_(1), oct_(4))
    Room.objects.filter(property=hotel.prop).update(housekeeping_status="dirty")

    finish(hotel, seed)

    stays = arrivals(hotel)
    assert any(stay.room is None for stay in stays)
    assert any(stay.room is not None and stay.room.housekeeping_status in READY for stay in stays)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_with_a_single_arrival_another_one_is_booked_for_today(hotel, seed):
    book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})

    finish(hotel, seed)

    stays = arrivals(hotel)
    assert len(stays) >= 2
    assert any(stay.room is None for stay in stays)
    assert any(stay.room is not None and stay.room.housekeeping_status in READY for stay in stays)


def test_an_arrival_waiting_for_a_departing_guest_is_moved_to_a_vacant_room(hotel):
    """Room 101 is still occupied by a guest who leaves today, so it cannot be the ready one."""
    departing = book(hotel, oct_(0), oct_(1), stay_kwargs={"room_id": hotel.rooms["101"].pk}).stays.get()
    hotel.prop.business_date = oct_(0)
    hotel.prop.save()
    check_in(departing)
    hotel.prop.business_date = oct_(1)
    hotel.prop.save()
    waiting = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk}).stays.get()
    book(hotel, oct_(1), oct_(2), room_type=hotel.dorm_type, adults=1)

    finish(hotel)

    waiting = Stay.objects.select_related("room").get(pk=waiting.pk)
    assert waiting.room not in (None, hotel.rooms["101"])
    assert waiting.room.housekeeping_status in READY
    assert any(stay.room is None for stay in arrivals(hotel))


def test_when_full_tonight_in_house_guests_leave_today_to_make_room_for_arrivals(hotel):
    hotel.prop.business_date = oct_(0)
    hotel.prop.save()
    for number in ("101", "102", "201", "301"):
        room = hotel.rooms[number]
        stay = book(
            hotel, oct_(0), oct_(5), room_type=room.room_type, stay_kwargs={"room_id": room.pk}
        ).stays.get()
        check_in(stay)
    book(hotel, oct_(0), oct_(5), room_type=hotel.dorm_type, adults=4)
    hotel.prop.business_date = oct_(1)
    hotel.prop.save()

    finish(hotel)

    assert len(arrivals(hotel)) == 2
    departing = Stay.objects.filter(
        reservation__property=hotel.prop, status="checked_in", checkout_date=oct_(1)
    )
    assert departing.count() == 2
    assert any(stay.room is None for stay in arrivals(hotel))


def test_without_free_units_tonight_nothing_is_booked(hotel):
    for room_type, count in ((hotel.dbl, 3), (hotel.ste, 1), (hotel.dorm_type, 4)):
        for _ in range(count):
            book(hotel, oct_(1) - timedelta(days=1), oct_(3), room_type=room_type, adults=1)

    finish(hotel)

    assert arrivals(hotel) == []
