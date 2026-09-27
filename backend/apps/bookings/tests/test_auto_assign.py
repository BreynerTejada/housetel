"""`auto_assign_rooms` (spec §4.2, plan B2b): unassigned, unlocked, not checked-in stays arriving between
`date_from` and `date_to` (both inclusive) get a free, unblocked unit of their category.

Priority: VIP bookers → groups → longer stays. Preferences: (a) ready rooms (clean/inspected) for arrivals
due today, (b) rooms connected to the ones the group already has, then the same floor for a group (dorms: the
same room), (c) the least fragmentation (a room whose previous or next stay touches this one), then the room
order. Assignments never move existing ones.
Conftest hotel: DBL 101 (floor 1), 102 (floor 1), 201 (floor 2); business date 2026-10-01.
"""

from contextlib import contextmanager

import pytest
from django.db.models.signals import post_save

from apps.bookings.models import Stay
from apps.bookings.services.reservations import assign_room, auto_assign_rooms, create_reservation
from apps.bookings.tests.factories import ReservationGroupFactory
from apps.bookings.tests.helpers import book, guest_input, oct_, reservation_request, stay_request
from apps.bookings.types import AssignmentReport, BookingError
from apps.core.models import Alert, AuditEvent
from apps.guests.models import Guest
from apps.inventory.models import Room, RoomBlock
from apps.inventory.tests.factories import RoomFactory

pytestmark = pytest.mark.django_db


def new_stay(hotel, checkin, checkout, room=None, **kwargs):
    stay = book(hotel, checkin, checkout, **kwargs).stays.get()
    if room is not None:
        assign_room(stay, room)
    return stay


def room_of(stay):
    return Stay.objects.get(pk=stay.pk).room


def run(hotel, date_from=None, date_to=None):
    return auto_assign_rooms(property=hotel.prop, date_from=date_from or oct_(1), date_to=date_to or oct_(1))


def test_assigns_the_arrivals_of_the_range_and_reports_them(hotel):
    today = new_stay(hotel, oct_(1), oct_(3))
    tomorrow = new_stay(hotel, oct_(2), oct_(4))
    later = new_stay(hotel, oct_(5), oct_(6))

    report = run(hotel, oct_(1), oct_(2))

    assert isinstance(report, AssignmentReport)
    assert room_of(today) is not None and room_of(tomorrow) is not None and room_of(later) is None
    assert sorted(report.assigned) == sorted(
        [(str(today.pk), str(room_of(today).pk)), (str(tomorrow.pk), str(room_of(tomorrow).pk))]
    )
    assert (report.unassigned, report.messages) == ([], [])
    assert set(
        AuditEvent.objects.filter(action="bookings.room_assigned").values_list("source", flat=True)
    ) == {"automation"}


def test_ready_rooms_first_for_todays_arrivals_only(hotel):
    Room.objects.filter(pk=hotel.rooms["101"].pk).update(housekeeping_status="dirty")
    today = new_stay(hotel, oct_(1), oct_(3))
    run(hotel)
    assert room_of(today) == hotel.rooms["102"]

    tomorrow = new_stay(hotel, oct_(2), oct_(3))
    run(hotel, oct_(2), oct_(2))
    assert room_of(tomorrow) == hotel.rooms["101"]  # dirty today, cleaned before tomorrow


def test_prefers_the_room_that_leaves_no_gap(hotel):
    new_stay(hotel, oct_(1), oct_(3), room=hotel.rooms["102"])  # 102 frees up the day we arrive
    arrival = new_stay(hotel, oct_(3), oct_(5))
    run(hotel, oct_(3), oct_(3))
    assert room_of(arrival) == hotel.rooms["102"]


def test_a_group_stays_on_one_floor(hotel):
    RoomFactory(room_type=hotel.dbl, number="202", floor="2", sort_order=9)
    new_stay(hotel, oct_(3), oct_(5), room=hotel.rooms["101"])  # floor 1 keeps one free room (102)
    group = ReservationGroupFactory(property=hotel.prop, name="Congreso")
    first = new_stay(hotel, oct_(3), oct_(5), group_id=group.pk)
    second = new_stay(hotel, oct_(3), oct_(5), group_id=group.pk)

    run(hotel, oct_(3), oct_(3))

    assert {room_of(first).floor, room_of(second).floor} == {"2"}


def test_a_multi_room_reservation_counts_as_a_group(hotel):
    RoomFactory(room_type=hotel.dbl, number="202", floor="2", sort_order=9)
    new_stay(hotel, oct_(3), oct_(5), room=hotel.rooms["101"])
    reservation = create_reservation(
        reservation_request(
            hotel, [stay_request(hotel, oct_(3), oct_(5)), stay_request(hotel, oct_(3), oct_(5))]
        )
    )
    run(hotel, oct_(3), oct_(3))
    assert {stay.room.floor for stay in reservation.stays.all()} == {"2"}


def test_a_group_takes_the_rooms_connected_to_the_ones_it_already_has(hotel):
    """Spec §5 B2b "conecta grupos": 103 connects with 101, so the family gets 101 + 103 instead of 101 +
    102 (same floor, earlier in the room order)."""
    connected = RoomFactory(room_type=hotel.dbl, number="103", floor="1", sort_order=2)
    hotel.rooms["101"].connecting_rooms.add(connected)
    reservation = create_reservation(
        reservation_request(
            hotel, [stay_request(hotel, oct_(3), oct_(5)), stay_request(hotel, oct_(3), oct_(5))]
        )
    )

    run(hotel, oct_(3), oct_(3))

    assert {stay.room.number for stay in reservation.stays.all()} == {"101", "103"}


def test_a_new_member_joins_the_room_connected_to_an_assigned_one(hotel):
    connected = RoomFactory(room_type=hotel.dbl, number="103", floor="1", sort_order=2)
    connected.connecting_rooms.add(hotel.rooms["201"])
    group = ReservationGroupFactory(property=hotel.prop, name="Familia Díaz")
    new_stay(hotel, oct_(3), oct_(5), room=hotel.rooms["201"], group_id=group.pk)
    late = new_stay(hotel, oct_(3), oct_(5), group_id=group.pk)

    run(hotel, oct_(3), oct_(3))

    assert room_of(late) == connected


def test_vip_bookers_go_first(hotel):
    for number in ("101", "102"):
        new_stay(hotel, oct_(1), oct_(3), room=hotel.rooms[number])
    regular = new_stay(hotel, oct_(1), oct_(2))
    vip = new_stay(hotel, oct_(1), oct_(2), booker=guest_input(first_name="Sofía"), allow_overbooking=True)
    Guest.objects.filter(pk=vip.reservation.booker_id).update(is_vip=True)

    report = run(hotel)

    assert (room_of(vip), room_of(regular)) == (hotel.rooms["201"], None)
    assert report.unassigned == [str(regular.pk)]
    assert regular.reservation.code in report.messages[0]


def test_longer_stays_go_first(hotel):
    for number in ("101", "102"):
        new_stay(hotel, oct_(1), oct_(5), room=hotel.rooms[number])
    short = new_stay(hotel, oct_(1), oct_(2))
    long_ = new_stay(hotel, oct_(1), oct_(4), allow_overbooking=True)
    run(hotel)
    assert (room_of(long_), room_of(short)) == (hotel.rooms["201"], None)


def test_locked_checked_in_and_assigned_stays_are_left_alone(hotel):
    locked = new_stay(hotel, oct_(1), oct_(2), stay_kwargs={"locked_room": True})
    assigned = new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["201"])
    in_house = new_stay(hotel, oct_(1), oct_(2))
    Stay.objects.filter(pk=in_house.pk).update(status="checked_in")

    run(hotel)

    assert (room_of(locked), room_of(assigned), room_of(in_house)) == (None, hotel.rooms["201"], None)


@contextmanager
def meanwhile(first, action):
    """Run `action()` as another user would, right after the run gave `first` its room (the run listed the
    waiting stays before)."""

    def hook(sender, instance, **kwargs):
        if instance.pk == first.pk and instance.room_id is not None:
            post_save.disconnect(sender=Stay, dispatch_uid="test-meanwhile")
            action()

    post_save.connect(hook, sender=Stay, dispatch_uid="test-meanwhile")
    try:
        yield
    finally:
        post_save.disconnect(sender=Stay, dispatch_uid="test-meanwhile")


@pytest.mark.parametrize("status", ["confirmed", "checked_in"], ids=["assigned", "checked-in"])
def test_a_stay_that_got_a_room_meanwhile_is_not_moved(hotel, status):
    first = new_stay(hotel, oct_(1), oct_(2))
    taken = new_stay(hotel, oct_(1), oct_(2))

    def front_desk_acts():
        Stay.objects.filter(pk=taken.pk).update(room=hotel.rooms["201"], status=status)

    with meanwhile(first, front_desk_acts):
        report = run(hotel)

    assert room_of(first) is not None
    assert Stay.objects.get(pk=taken.pk).room == hotel.rooms["201"]
    assert str(taken.pk) not in {stay_id for stay_id, _unit in report.assigned}
    assert not AuditEvent.objects.filter(action="bookings.room_assigned", target_id=str(taken.pk)).exists()


def test_a_stay_cancelled_meanwhile_is_skipped_and_the_run_goes_on(hotel):
    first = new_stay(hotel, oct_(1), oct_(2))
    gone = new_stay(hotel, oct_(1), oct_(2))
    last = new_stay(hotel, oct_(1), oct_(2))

    with meanwhile(first, lambda: Stay.objects.filter(pk=gone.pk).update(status="cancelled")):
        report = run(hotel)

    assert (room_of(first) is not None, room_of(gone), room_of(last) is not None) == (True, None, True)
    assert sorted(stay_id for stay_id, _unit in report.assigned) == sorted([str(first.pk), str(last.pk)])
    assert report.unassigned == []


def test_blocked_rooms_are_skipped(hotel):
    for number in ("101", "102"):
        RoomBlock.objects.create(room=hotel.rooms[number], start_date=oct_(1), end_date=oct_(9))
    arrival = new_stay(hotel, oct_(1), oct_(2))
    run(hotel)
    assert room_of(arrival) == hotel.rooms["201"]


def test_dorm_guests_get_beds_and_a_group_shares_the_dorm_room(hotel):
    other_dorm = RoomFactory(room_type=hotel.dorm_type, number="D0", sort_order=0)
    from apps.inventory.tests.factories import BedFactory

    BedFactory(room=other_dorm, label="A")
    reservation = book(hotel, oct_(1), oct_(2), room_type=hotel.dorm_type, adults=3)

    run(hotel)

    stays = list(reservation.stays.all())
    assert all(stay.bed is not None for stay in stays)
    assert {stay.room for stay in stays} == {hotel.dorm}  # D0 has one bed: the group does not split
    assert len({stay.bed for stay in stays}) == 3


def test_unassigned_arrivals_of_today_raise_an_alert_that_clears_later(hotel):
    for number in ("101", "102", "201"):
        new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms[number])
    waiting = new_stay(hotel, oct_(1), oct_(2), allow_overbooking=True)

    run(hotel)

    alert = Alert.objects.get(kind="unassigned_arrivals", resolved_at__isnull=True)
    assert waiting.reservation.code in alert.message
    RoomFactory(room_type=hotel.dbl, number="203", floor="2")
    run(hotel)
    assert room_of(waiting).number == "203"
    assert not Alert.objects.filter(kind="unassigned_arrivals", resolved_at__isnull=True).exists()


def test_the_range_must_be_valid(hotel):
    with pytest.raises(BookingError) as error:
        run(hotel, oct_(3), oct_(2))
    assert error.value.code == "invalid_dates"
