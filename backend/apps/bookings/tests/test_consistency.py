"""InventoryDay maintained incrementally by the booking services must equal a full `rebuild_inventory` after
any sequence of operations (plan B2b › tests obligatorios: "rebuild = incremental tras una secuencia
aleatoria").

Every operation runs with its on-commit callbacks executed, as in production: blocks reach InventoryDay
through the `inventory_changed` receiver, while booking operations rely only on their own incremental
adjustments (the receiver skips `origin="bookings"` events).
"""

import random
from datetime import timedelta

import pytest

from apps.bookings.models import Stay
from apps.bookings.services.inventory import rebuild_inventory
from apps.bookings.services.reservations import (
    assign_room,
    cancel_reservation,
    check_in,
    check_out,
    confirm_reservation,
    mark_no_show,
    modify_stay,
    unassign_room,
)
from apps.bookings.tests.helpers import book, oct_
from apps.core.errors import DomainError
from apps.inventory.models import RoomBlock
from apps.inventory.services import block_room, release_block

pytestmark = pytest.mark.django_db

DAYS = [oct_(day) for day in range(1, 21)]


def random_range(rng, max_nights=4):
    checkin = rng.choice(DAYS[:-1])
    return checkin, checkin + timedelta(days=rng.randint(1, max_nights))


def set_business_date(hotel, day):
    hotel.prop.business_date = day
    hotel.prop.save(update_fields=["business_date", "updated_at"])


@pytest.mark.parametrize("seed", [7, 2026])
def test_incremental_inventory_equals_a_full_rebuild(hotel, django_capture_on_commit_callbacks, seed):
    rng = random.Random(seed)
    rooms = [hotel.rooms[number] for number in ("101", "102", "201", "301")]
    done = []

    def stays(*statuses):
        return list(Stay.objects.filter(reservation__property=hotel.prop, status__in=statuses))

    def create():
        checkin, checkout = random_range(rng)
        room_type = rng.choice([hotel.dbl, hotel.dbl, hotel.ste])
        kwargs = {"allow_overbooking": rng.random() < 0.2, "status": rng.choice(["confirmed", "tentative"])}
        if rng.random() < 0.4:
            candidates = [room for room in rooms if room.room_type_id == room_type.pk]
            kwargs["stay_kwargs"] = {"room_id": rng.choice(candidates).pk}
        book(hotel, checkin, checkout, room_type=room_type, **kwargs)

    def create_dorm():
        checkin, checkout = random_range(rng)
        book(hotel, checkin, checkout, room_type=hotel.dorm_type, adults=rng.randint(1, 3))

    def modify():
        stay = rng.choice(stays("tentative", "confirmed", "checked_in"))
        checkin, checkout = random_range(rng)
        if stay.status == "checked_in":
            checkin = stay.checkin_date
            checkout = max(checkout, stay.checkin_date + timedelta(days=1), hotel.prop.business_date)
        room_type = rng.choice([None, hotel.ste]) if stay.room_type != hotel.dorm_type else None
        modify_stay(stay, checkin=checkin, checkout=checkout, room_type=room_type, reprice=rng.random() < 0.5)

    def assign():
        stay = rng.choice(stays("tentative", "confirmed", "checked_in"))
        if stay.room_type == hotel.dorm_type:
            assign_room(stay, hotel.dorm)
        else:
            assign_room(stay, rng.choice(rooms), force=True)

    def unassign():
        unassign_room(rng.choice(stays("tentative", "confirmed")))

    def cancel():
        cancel_reservation(rng.choice(stays("tentative", "confirmed")).reservation, reason="-")

    def confirm():
        confirm_reservation(rng.choice(stays("tentative")).reservation)

    def arrive():
        stay = rng.choice(stays("tentative", "confirmed"))
        set_business_date(hotel, stay.checkin_date)
        check_in(stay, force=True)

    def leave():
        stay = rng.choice(stays("checked_in"))
        nights = (stay.checkout_date - stay.checkin_date).days
        set_business_date(hotel, stay.checkin_date + timedelta(days=rng.randint(0, nights)))
        check_out(stay, force=True)

    def no_show():
        stay = rng.choice(stays("confirmed"))
        set_business_date(hotel, stay.checkin_date + timedelta(days=1))
        mark_no_show(stay.reservation)

    def block():
        start, end = random_range(rng)
        block_room(rng.choice(rooms), start=start, end=end, kind="maintenance", reason="-")

    def release():
        release_block(rng.choice(list(RoomBlock.objects.filter(released_at__isnull=True))))

    operations = [create] * 6 + [create_dorm] * 2 + [modify, modify, assign, assign, unassign, cancel]
    operations += [confirm, arrive, arrive, leave, no_show, block, release]
    for _step in range(120):
        operation = rng.choice(operations)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                operation()
            done.append(operation.__name__)
        except (DomainError, IndexError):  # a refused operation (409/400) or nothing to act on
            continue

    assert len(set(done)) >= 10, done  # the sequence really exercised the services
    result = rebuild_inventory(hotel.prop, oct_(1) - timedelta(days=7), oct_(30))
    assert (result.updated, result.drift) == (0, [])
