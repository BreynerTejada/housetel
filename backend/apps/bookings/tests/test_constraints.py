"""The database itself forbids double-assigning a room or a dorm bed (ExclusionConstraint + btree_gist)."""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.bookings.models import Stay
from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.inventory.tests.factories import BedFactory, DormRoomTypeFactory, RoomFactory, RoomTypeFactory

pytestmark = pytest.mark.django_db

OCT = lambda day: date(2026, 10, day)  # noqa: E731


@pytest.fixture
def room(prop):
    return RoomFactory(room_type=RoomTypeFactory(property=prop))


def stay_in(room, checkin, checkout, *, status="confirmed", bed=None):
    reservation = ReservationFactory(
        property=room.property, checkin_date=checkin, checkout_date=checkout, status=status
    )
    return StayFactory(reservation=reservation, room_type=room.room_type, room=room, bed=bed, status=status)


def test_two_active_stays_in_the_same_room_and_overlapping_dates_are_rejected(room):
    stay_in(room, OCT(1), OCT(4))
    with pytest.raises(IntegrityError), transaction.atomic():
        stay_in(room, OCT(3), OCT(5))


@pytest.mark.parametrize("status", ["tentative", "confirmed", "checked_in"])
def test_every_active_status_blocks_the_room(room, status):
    stay_in(room, OCT(1), OCT(4), status=status)
    with pytest.raises(IntegrityError), transaction.atomic():
        stay_in(room, OCT(2), OCT(3))


@pytest.mark.parametrize("status", ["cancelled", "no_show", "checked_out"])
def test_inactive_stays_do_not_block_the_room(room, status):
    stay_in(room, OCT(1), OCT(4), status=status)
    stay_in(room, OCT(1), OCT(4))
    assert Stay.objects.filter(room=room).count() == 2


def test_checkout_day_can_be_the_next_checkin_day(room):
    stay_in(room, OCT(1), OCT(4))
    stay_in(room, OCT(4), OCT(6))
    assert Stay.objects.filter(room=room).count() == 2


def test_reactivating_an_overlapping_cancelled_stay_is_rejected(room):
    stay_in(room, OCT(1), OCT(4))
    cancelled = stay_in(room, OCT(2), OCT(5), status="cancelled")
    cancelled.status = "confirmed"
    with pytest.raises(IntegrityError), transaction.atomic():
        cancelled.save()


def test_unassigned_stays_never_conflict(prop):
    room_type = RoomTypeFactory(property=prop)
    for _ in range(3):
        StayFactory(
            reservation=ReservationFactory(property=prop, checkin_date=OCT(1), checkout_date=OCT(3)),
            room_type=room_type,
        )
    assert Stay.objects.filter(room__isnull=True).count() == 3


class TestDorms:
    @pytest.fixture
    def dorm(self, prop):
        return RoomFactory(room_type=DormRoomTypeFactory(property=prop), number="D1")

    def test_different_beds_of_the_same_dorm_can_be_sold_for_the_same_nights(self, dorm):
        bed_a, bed_b = BedFactory(room=dorm, label="A"), BedFactory(room=dorm, label="B")
        stay_in(dorm, OCT(1), OCT(4), bed=bed_a)
        stay_in(dorm, OCT(1), OCT(4), bed=bed_b)
        assert Stay.objects.filter(room=dorm).count() == 2

    def test_the_same_bed_cannot_be_sold_twice(self, dorm):
        bed = BedFactory(room=dorm, label="A")
        stay_in(dorm, OCT(1), OCT(4), bed=bed)
        with pytest.raises(IntegrityError), transaction.atomic():
            stay_in(dorm, OCT(3), OCT(6), bed=bed)


def test_checkout_must_be_after_checkin(room):
    with pytest.raises(IntegrityError), transaction.atomic():
        stay_in(room, OCT(4), OCT(4))
