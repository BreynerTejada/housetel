"""Domain signals → housekeeping tasks (plan C2: check-out → departure clean; room turned dirty without an
open task → task; history replayed by the demo seed is ignored)."""

import pytest

from apps.core import signals
from apps.core.signals import seeding
from apps.housekeeping.models import HousekeepingTask
from apps.housekeeping.tests.conftest import BUSINESS_DATE, day, make_stay
from apps.housekeeping.tests.factories import HousekeepingTaskFactory

pytestmark = pytest.mark.django_db


def checked_out(stay):
    stay.status = "checked_out"
    stay.save(update_fields=["status"])
    signals.stay_checked_out.send(sender=None, stay=stay)


def turned(room, old, new):
    room.housekeeping_status = new
    room.save(update_fields=["housekeeping_status"])
    signals.room_status_changed.send(sender=None, room=room, old=old, new=new)


class TestCheckOut:
    def test_creates_a_normal_priority_departure_clean(self, hotel):
        room = hotel.rooms["101"]
        stay = make_stay(hotel, room, checkin=day(-2), checkout=BUSINESS_DATE)
        make_stay(hotel, hotel.rooms["102"], checkin=BUSINESS_DATE, checkout=day(2), status="confirmed")

        checked_out(stay)

        task = HousekeepingTask.objects.get()
        assert (task.room, task.kind, task.status, task.priority) == (
            room,
            "departure_clean",
            "pending",
            "normal",
        )
        assert (task.business_date, task.estimated_minutes, task.created_source) == (
            BUSINESS_DATE,
            30,
            "checkout",
        )
        assert task.reservation == stay.reservation
        assert task.property == hotel.prop

    @pytest.mark.parametrize("status", ["confirmed", "tentative"])
    def test_is_high_priority_when_a_guest_arrives_today_in_that_room(self, hotel, status):
        room = hotel.rooms["101"]
        stay = make_stay(hotel, room, checkin=day(-2), checkout=BUSINESS_DATE)
        make_stay(hotel, room, checkin=BUSINESS_DATE, checkout=day(2), status=status)

        checked_out(stay)

        assert HousekeepingTask.objects.get().priority == "high"

    def test_a_room_override_of_the_housekeeping_minutes_is_used(self, hotel):
        room = hotel.rooms["301"]
        room.overrides = {"housekeeping_minutes": 75}
        room.save(update_fields=["overrides"])
        checked_out(make_stay(hotel, room, checkin=day(-1), checkout=BUSINESS_DATE))

        assert HousekeepingTask.objects.get().estimated_minutes == 75

    def test_the_pending_stayover_of_the_room_becomes_its_departure_clean(self, hotel):
        room = hotel.rooms["201"]
        stayover = HousekeepingTaskFactory(room=room, kind="stayover", estimated_minutes=15)
        make_stay(hotel, room, checkin=BUSINESS_DATE, checkout=day(1), status="confirmed")

        checked_out(make_stay(hotel, room, checkin=day(-3), checkout=BUSINESS_DATE))

        task = HousekeepingTask.objects.get()
        assert task.pk == stayover.pk
        assert (task.kind, task.priority, task.estimated_minutes) == ("departure_clean", "high", 30)

    def test_the_departure_clean_planned_in_the_morning_is_kept(self, hotel):
        room = hotel.rooms["102"]
        planned = HousekeepingTaskFactory(room=room, kind="departure_clean", created_source="daily")

        checked_out(make_stay(hotel, room, checkin=day(-1), checkout=BUSINESS_DATE))

        assert list(HousekeepingTask.objects.values_list("pk", flat=True)) == [planned.pk]

    def test_a_second_bed_leaving_the_same_dorm_widens_the_task_to_the_whole_room(self, hotel):
        dorm = hotel.rooms["D1"]
        checked_out(make_stay(hotel, dorm, bed=hotel.beds["A"], checkin=day(-1), checkout=BUSINESS_DATE))
        assert HousekeepingTask.objects.get().bed == hotel.beds["A"]

        checked_out(make_stay(hotel, dorm, bed=hotel.beds["B"], checkin=day(-2), checkout=BUSINESS_DATE))

        task = HousekeepingTask.objects.get()
        assert (task.room, task.bed) == (dorm, None)

    def test_stays_without_a_room_are_ignored(self, hotel):
        stay = make_stay(hotel, hotel.rooms["101"], checkin=day(-1), checkout=BUSINESS_DATE)
        stay.room = None
        checked_out(stay)
        assert not HousekeepingTask.objects.exists()

    def test_history_replayed_by_the_demo_seed_creates_nothing(self, hotel):
        stay = make_stay(hotel, hotel.rooms["101"], checkin=day(-2), checkout=BUSINESS_DATE)
        with seeding():
            checked_out(stay)
            turned(hotel.rooms["102"], "clean", "dirty")
        assert not HousekeepingTask.objects.exists()


class TestRoomStatusChanged:
    def test_a_vacant_room_turning_dirty_gets_a_departure_clean(self, hotel):
        turned(hotel.rooms["202"], "clean", "dirty")

        task = HousekeepingTask.objects.get()
        assert (task.room, task.kind, task.priority, task.created_source) == (
            hotel.rooms["202"],
            "departure_clean",
            "normal",
            "status_change",
        )

    def test_an_occupied_room_turning_dirty_gets_a_stayover(self, hotel):
        room = hotel.rooms["202"]
        stay = make_stay(hotel, room, checkin=day(-1), checkout=day(2))

        turned(room, "clean", "dirty")

        task = HousekeepingTask.objects.get()
        assert (task.kind, task.estimated_minutes, task.reservation) == ("stayover", 15, stay.reservation)

    def test_an_arrival_today_makes_it_high_priority(self, hotel):
        room = hotel.rooms["202"]
        make_stay(hotel, room, checkin=BUSINESS_DATE, checkout=day(3), status="confirmed")
        turned(room, "inspected", "dirty")
        assert HousekeepingTask.objects.get().priority == "high"

    @pytest.mark.parametrize("kind", ["departure_clean", "stayover", "deep_clean"])
    def test_an_open_cleaning_task_is_not_duplicated(self, hotel, kind):
        room = hotel.rooms["202"]
        HousekeepingTaskFactory(room=room, kind=kind, status="in_progress", business_date=day(-1))

        turned(room, "clean", "dirty")

        assert HousekeepingTask.objects.count() == 1

    def test_other_changes_create_nothing(self, hotel):
        turned(hotel.rooms["202"], "dirty", "clean")
        turned(hotel.rooms["201"], "clean", "out_of_service")
        assert not HousekeepingTask.objects.exists()

    @pytest.mark.parametrize("new", ["clean", "inspected"])
    def test_marking_the_room_clean_elsewhere_cancels_its_pending_clean(self, hotel, new):
        room = hotel.rooms["101"]
        pending = HousekeepingTaskFactory(room=room, kind="departure_clean")
        other_room = HousekeepingTaskFactory(room=hotel.rooms["102"], kind="departure_clean")

        turned(room, "dirty", new)

        pending.refresh_from_db()
        assert pending.status == "cancelled"
        assert pending.notes
        other_room.refresh_from_db()
        assert other_room.status == "pending"

    def test_a_clean_already_in_progress_is_left_to_the_housekeeper(self, hotel):
        room = hotel.rooms["101"]
        task = HousekeepingTaskFactory(room=room, kind="departure_clean", status="in_progress")

        turned(room, "dirty", "clean")

        task.refresh_from_db()
        assert task.status == "in_progress"


def test_a_real_check_out_leaves_exactly_one_departure_clean(hotel, django_capture_on_commit_callbacks):
    """B2b sends `stay_checked_out` and then `room_status_changed` → dirty: one task, with the arrival
    rule."""
    from apps.bookings.services.reservations import check_out

    room = hotel.rooms["101"]
    stay = make_stay(hotel, room, checkin=day(-2), checkout=BUSINESS_DATE)
    make_stay(hotel, room, checkin=BUSINESS_DATE, checkout=day(1), status="confirmed")

    with django_capture_on_commit_callbacks(execute=True):
        check_out(stay, force=True)

    task = HousekeepingTask.objects.get()
    assert (task.room, task.kind, task.priority, task.created_source) == (
        room,
        "departure_clean",
        "high",
        "checkout",
    )
