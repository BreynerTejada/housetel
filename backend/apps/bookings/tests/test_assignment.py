"""Room assignment (spec §4.2 `assign_room`, plan B2b): validations, the database exclusion constraint
surfaced as AvailabilityError, dorm beds, forced moves to another category (the inventory unit moves with
the guest), reversible audit + generic undo, and `room_assigned`.
"""

import pytest
from django.utils import timezone

from apps.bookings.models import InventoryDay, Stay
from apps.bookings.services import reservations
from apps.bookings.services.assignment import room_options
from apps.bookings.services.reservations import assign_room, unassign_room
from apps.bookings.tests.helpers import book, oct_
from apps.bookings.types import AvailabilityError, BookingError, InvalidStateError
from apps.core import audit
from apps.core.models import AuditEvent
from apps.core.tests.factories import PropertyFactory
from apps.inventory.models import RoomBlock
from apps.inventory.tests.factories import BedFactory, RoomFactory, RoomTypeFactory

pytestmark = pytest.mark.django_db


def new_stay(hotel, checkin=None, checkout=None, **kwargs):
    return book(hotel, checkin or oct_(1), checkout or oct_(3), **kwargs).stays.get()


def fresh(stay):
    return Stay.objects.get(pk=stay.pk)


def sold(room_type, day):
    row = InventoryDay.objects.filter(room_type=room_type, date=day).first()
    return row.sold_units if row else 0


class TestAssign:
    def test_puts_the_stay_in_a_free_room_of_its_category(self, hotel, owner):
        stay = new_stay(hotel)
        result = assign_room(stay, hotel.rooms["101"], actor=owner)
        assert isinstance(result, Stay)
        assert (fresh(stay).room, fresh(stay).bed) == (hotel.rooms["101"], None)

    def test_is_audited_as_reversible(self, hotel, owner):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"], actor=owner)
        event = AuditEvent.objects.get(action="bookings.room_assigned")
        assert (event.target_type, event.target_id, event.actor, event.reversible) == (
            "bookings.stay",
            str(stay.pk),
            owner,
            True,
        )
        assert event.undo_data == {"stay_id": str(stay.pk), "old_room_id": None, "old_bed_id": None}
        assert event.changes == {"room": [None, "101"]}
        assert "101" in event.summary and stay.reservation.code in event.summary

    def test_emits_room_assigned_with_the_previous_room(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        stay = new_stay(hotel)
        with django_capture_on_commit_callbacks(execute=True):
            assign_room(stay, hotel.rooms["101"])
            assign_room(stay, hotel.rooms["102"])
        moves = [(kwargs["stay"].room, kwargs["old_room"]) for kwargs in signal_log.of("room_assigned")]
        assert moves == [(hotel.rooms["101"], None), (hotel.rooms["102"], hotel.rooms["101"])]

    def test_the_same_room_again_changes_nothing(self, hotel):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"])
        assign_room(stay, hotel.rooms["101"])
        assert AuditEvent.objects.filter(action="bookings.room_assigned").count() == 1

    def test_an_occupied_room_is_a_409(self, hotel):
        assign_room(new_stay(hotel, oct_(1), oct_(3)), hotel.rooms["101"])
        other = new_stay(hotel, oct_(2), oct_(4))
        with pytest.raises(AvailabilityError) as error:
            assign_room(other, hotel.rooms["101"])
        assert error.value.status_code == 409
        assert fresh(other).room is None

    def test_the_database_constraint_has_the_last_word(self, hotel, monkeypatch):
        """When the application check misses a booking of the room (written by another transaction meanwhile),
        the exclusion constraint of the database refuses the second one: the same 409, nothing half-saved."""
        assign_room(new_stay(hotel, oct_(1), oct_(3)), hotel.rooms["101"])
        other = new_stay(hotel, oct_(2), oct_(4))
        monkeypatch.setattr(reservations, "is_occupied", lambda *args, **kwargs: False)

        with pytest.raises(AvailabilityError) as error:
            assign_room(other, hotel.rooms["101"])

        assert (error.value.code, error.value.status_code) == ("no_availability", 409)
        assert fresh(other).room is None
        assigned = AuditEvent.objects.filter(action="bookings.room_assigned", target_id=str(other.pk))
        assert not assigned.exists()

    def test_back_to_back_stays_share_the_room(self, hotel):
        assign_room(new_stay(hotel, oct_(1), oct_(3)), hotel.rooms["101"])
        following = new_stay(hotel, oct_(3), oct_(5))
        assign_room(following, hotel.rooms["101"])
        assert fresh(following).room == hotel.rooms["101"]

    def test_a_blocked_room_is_a_409_until_the_block_is_released(self, hotel):
        block = RoomBlock.objects.create(room=hotel.rooms["101"], start_date=oct_(2), end_date=oct_(5))
        stay = new_stay(hotel)
        with pytest.raises(AvailabilityError) as error:
            assign_room(stay, hotel.rooms["101"])
        assert error.value.code == "room_blocked"
        block.released_at = timezone.now()
        block.save()
        assign_room(stay, hotel.rooms["101"])
        assert fresh(stay).room == hotel.rooms["101"]

    def test_inactive_rooms_and_rooms_of_other_properties_are_rejected(self, hotel):
        stay = new_stay(hotel)
        closed = RoomFactory(room_type=hotel.dbl, number="199", is_active=False)
        elsewhere = RoomFactory(room_type=RoomTypeFactory(property=PropertyFactory()), number="101")
        for room in (closed, elsewhere):
            with pytest.raises(BookingError) as error:
                assign_room(stay, room)
            assert error.value.code == "invalid_room"

    @pytest.mark.parametrize("status", ["cancelled", "no_show", "checked_out"])
    def test_only_active_stays_get_rooms(self, hotel, status):
        stay = new_stay(hotel)
        Stay.objects.filter(pk=stay.pk).update(status=status)
        with pytest.raises(InvalidStateError):
            assign_room(stay, hotel.rooms["101"])

    def test_an_in_house_guest_can_move_to_another_room(self, hotel):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"])
        Stay.objects.filter(pk=stay.pk).update(status="checked_in")
        assign_room(stay, hotel.rooms["102"])
        assert fresh(stay).room == hotel.rooms["102"]

    def test_the_room_an_in_house_guest_leaves_needs_cleaning(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"])
        Stay.objects.filter(pk=stay.pk).update(status="checked_in")

        with django_capture_on_commit_callbacks(execute=True):
            assign_room(stay, hotel.rooms["102"])

        hotel.rooms["101"].refresh_from_db()
        assert hotel.rooms["101"].housekeeping_status == "dirty"
        changes = [(kw["room"], kw["old"], kw["new"]) for kw in signal_log.of("room_status_changed")]
        assert changes == [(hotel.rooms["101"], "clean", "dirty")]

    def test_moving_a_guest_who_has_not_arrived_leaves_the_rooms_as_they_are(self, hotel):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"])
        assign_room(stay, hotel.rooms["102"])
        hotel.rooms["101"].refresh_from_db()
        assert hotel.rooms["101"].housekeeping_status == "clean"


class TestAnotherCategory:
    def test_needs_force(self, hotel):
        stay = new_stay(hotel)
        with pytest.raises(BookingError) as error:
            assign_room(stay, hotel.rooms["301"])
        assert error.value.code == "category_mismatch"

    def test_an_upgrade_moves_the_inventory_unit_and_is_recorded(self, hotel, owner):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["301"], force=True, actor=owner)

        assert fresh(stay).room == hotel.rooms["301"] and fresh(stay).room_type == hotel.dbl
        assert (sold(hotel.dbl, oct_(1)), sold(hotel.ste, oct_(1)), sold(hotel.ste, oct_(2))) == (0, 1, 1)
        summary = AuditEvent.objects.get(action="bookings.room_assigned").summary
        assert "DBL → STE" in summary

    def test_the_target_category_must_have_a_unit_left(self, hotel):
        new_stay(hotel, room_type=hotel.ste)  # STE's only unit is sold (not yet assigned)
        stay = new_stay(hotel)
        with pytest.raises(AvailabilityError):
            assign_room(stay, hotel.rooms["301"], force=True)
        assert fresh(stay).room is None
        assert sold(hotel.dbl, oct_(1)) == 1

    def test_private_rooms_and_dorm_beds_never_mix(self, hotel):
        with pytest.raises(BookingError) as error:
            assign_room(new_stay(hotel), hotel.dorm, force=True)
        assert error.value.code == "invalid_room"
        dorm_stay = new_stay(hotel, room_type=hotel.dorm_type, adults=1)
        with pytest.raises(BookingError) as error:
            assign_room(dorm_stay, hotel.rooms["101"], force=True)
        assert error.value.code == "invalid_room"


class TestDorms:
    def test_without_a_bed_the_first_free_one_is_taken(self, hotel):
        first = new_stay(hotel, room_type=hotel.dorm_type, adults=1)
        assign_room(first, hotel.dorm, bed=hotel.beds["A"])
        second = new_stay(hotel, room_type=hotel.dorm_type, adults=1)
        assign_room(second, hotel.dorm)
        assert (fresh(first).bed, fresh(second).bed) == (hotel.beds["A"], hotel.beds["B"])

    def test_a_blocked_bed_is_skipped_and_cannot_be_chosen(self, hotel):
        RoomBlock.objects.create(room=hotel.dorm, bed=hotel.beds["A"], start_date=oct_(1), end_date=oct_(9))
        stay = new_stay(hotel, room_type=hotel.dorm_type, adults=1)
        with pytest.raises(AvailabilityError):
            assign_room(stay, hotel.dorm, bed=hotel.beds["A"])
        assign_room(stay, hotel.dorm)
        assert fresh(stay).bed == hotel.beds["B"]

    def test_an_occupied_bed_is_a_409(self, hotel):
        assign_room(new_stay(hotel, room_type=hotel.dorm_type, adults=1), hotel.dorm, bed=hotel.beds["C"])
        with pytest.raises(AvailabilityError):
            assign_room(new_stay(hotel, room_type=hotel.dorm_type, adults=1), hotel.dorm, bed=hotel.beds["C"])

    def test_the_bed_must_belong_to_the_room(self, hotel):
        other_dorm = RoomFactory(room_type=hotel.dorm_type, number="D2")
        stray = BedFactory(room=other_dorm, label="A")
        with pytest.raises(BookingError) as error:
            assign_room(new_stay(hotel, room_type=hotel.dorm_type, adults=1), hotel.dorm, bed=stray)
        assert error.value.code == "invalid_bed"

    def test_a_full_dorm_room_is_a_409(self, hotel):
        for _ in range(4):
            assign_room(new_stay(hotel, room_type=hotel.dorm_type, adults=1), hotel.dorm)
        other_dorm = RoomFactory(room_type=hotel.dorm_type, number="D2")
        BedFactory(room=other_dorm, label="A")
        with pytest.raises(AvailabilityError):
            assign_room(new_stay(hotel, room_type=hotel.dorm_type, adults=1), hotel.dorm)


class TestUndo:
    def test_undo_restores_the_previous_room_step_by_step(self, hotel, owner):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"], actor=owner)
        assign_room(stay, hotel.rooms["102"], actor=owner)
        first, second = AuditEvent.objects.filter(action="bookings.room_assigned").order_by("created_at")

        audit.undo(second, actor=owner)
        assert fresh(stay).room == hotel.rooms["101"]
        audit.undo(first, actor=owner)
        assert fresh(stay).room is None
        assert (
            AuditEvent.objects.filter(action="bookings.room_assigned").count() == 2
        )  # undo is not re-audited

    def test_undoing_an_upgrade_gives_the_unit_back(self, hotel, owner):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["301"], force=True)
        audit.undo(AuditEvent.objects.get(action="bookings.room_assigned"), actor=owner)
        assert (sold(hotel.dbl, oct_(1)), sold(hotel.ste, oct_(1))) == (1, 0)

    def test_undo_fails_when_the_old_room_was_taken_meanwhile(self, hotel, owner):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"])
        assign_room(stay, hotel.rooms["102"])
        assign_room(new_stay(hotel), hotel.rooms["101"])
        second = AuditEvent.objects.filter(action="bookings.room_assigned", target_id=str(stay.pk)).latest(
            "created_at"
        )
        with pytest.raises(AvailabilityError):
            audit.undo(second, actor=owner)
        assert fresh(stay).room == hotel.rooms["102"]


class TestUnassign:
    def test_takes_the_room_away_and_is_reversible(self, hotel, owner):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"])
        unassign_room(stay, actor=owner)
        assert fresh(stay).room is None
        event = AuditEvent.objects.get(action="bookings.room_unassigned")
        assert event.reversible and event.undo_data["old_room_id"] == str(hotel.rooms["101"].pk)
        audit.undo(event, actor=owner)
        assert fresh(stay).room == hotel.rooms["101"]

    def test_an_upgraded_stay_goes_back_to_its_booked_category(self, hotel):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["301"], force=True)
        unassign_room(stay)
        assert (sold(hotel.dbl, oct_(1)), sold(hotel.ste, oct_(1))) == (1, 0)

    def test_an_in_house_guest_cannot_be_left_without_room(self, hotel):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"])
        Stay.objects.filter(pk=stay.pk).update(status="checked_in")
        with pytest.raises(InvalidStateError):
            unassign_room(stay)

    def test_emits_room_assigned_with_the_old_room(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["101"])
        with django_capture_on_commit_callbacks(execute=True):
            unassign_room(stay)
        (event,) = signal_log.of("room_assigned")
        assert (event["stay"].room, event["old_room"]) == (None, hotel.rooms["101"])


class TestRoomOptions:
    """`room_options(stay)`: where the stay can go — free and unblocked units for all its nights, its own
    category ranked like the auto-assignment, then other categories of the same kind with a unit left."""

    def test_free_rooms_of_the_category_ready_first_then_other_categories(self, hotel):
        from apps.inventory.models import Room

        Room.objects.filter(pk=hotel.rooms["101"].pk).update(housekeeping_status="dirty")
        assign_room(new_stay(hotel, oct_(2), oct_(4)), hotel.rooms["102"])
        stay = new_stay(hotel, oct_(1), oct_(3))

        options = room_options(stay)

        assert [(item["room_number"], item["same_category"], item["ready"]) for item in options] == [
            ("201", True, True),
            ("101", True, False),
            ("301", False, True),
        ]
        assert options[0] == {
            "room_id": str(hotel.rooms["201"].pk),
            "room_number": "201",
            "floor": "2",
            "room_type_id": str(hotel.dbl.pk),
            "room_type_code": "DBL",
            "bed_id": None,
            "bed_label": None,
            "housekeeping_status": "clean",
            "ready": True,
            "same_category": True,
        }

    def test_another_category_is_offered_only_with_a_unit_left(self, hotel):
        new_stay(hotel, oct_(1), oct_(3), room_type=hotel.ste)  # the only suite is sold (not assigned)
        options = room_options(new_stay(hotel, oct_(1), oct_(3)))
        assert "301" not in [item["room_number"] for item in options]

    def test_the_current_room_and_blocked_rooms_are_left_out(self, hotel):
        RoomBlock.objects.create(room=hotel.rooms["201"], start_date=oct_(2), end_date=oct_(3))
        stay = new_stay(hotel, oct_(1), oct_(3))
        assign_room(stay, hotel.rooms["101"])
        numbers = [item["room_number"] for item in room_options(fresh(stay))]
        assert "101" not in numbers and "201" not in numbers and "102" in numbers

    def test_dorm_guests_get_free_beds(self, hotel):
        assign_room(new_stay(hotel, room_type=hotel.dorm_type, adults=1), hotel.dorm, bed=hotel.beds["A"])
        stay = new_stay(hotel, room_type=hotel.dorm_type, adults=1)
        options = room_options(stay)
        assert [(item["room_number"], item["bed_label"]) for item in options] == [
            ("D1", "B"),
            ("D1", "C"),
            ("D1", "D"),
        ]
