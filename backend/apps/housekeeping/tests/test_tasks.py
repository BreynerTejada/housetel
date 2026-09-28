"""Task life cycle: start → finish → room clean (or inspection → inspected), assignment, cancellation and
manual tasks."""

import pytest

from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.housekeeping.models import HousekeepingSettings, HousekeepingTask
from apps.housekeeping.services import tasks as svc
from apps.housekeeping.tests.conftest import BUSINESS_DATE, day, make_stay
from apps.housekeeping.tests.factories import HousekeepingTaskFactory
from apps.inventory.models import Room

pytestmark = pytest.mark.django_db


def status_of(room) -> str:
    return Room.objects.get(pk=room.pk).housekeeping_status


def dirty(room):
    Room.objects.filter(pk=room.pk).update(housekeeping_status="dirty")
    room.refresh_from_db()
    return room


@pytest.fixture
def housekeeper(make_member):
    return make_member("housekeeping", full_name="Luz Marina Pérez")


@pytest.fixture
def supervisor(make_member):
    return make_member("housekeeping_supervisor")


class TestStart:
    def test_starts_the_task_and_takes_it_when_unassigned(self, hotel, housekeeper):
        task = HousekeepingTaskFactory(room=dirty(hotel.rooms["101"]))

        svc.start_task(task, actor=housekeeper)

        task.refresh_from_db()
        assert (task.status, task.assigned_to) == ("in_progress", housekeeper)
        assert task.started_at is not None

    def test_a_task_already_started_cannot_start_again(self, hotel, housekeeper):
        task = HousekeepingTaskFactory(room=hotel.rooms["101"], status="in_progress")
        with pytest.raises(DomainError) as error:
            svc.start_task(task, actor=housekeeper)
        assert (error.value.status_code, error.value.code) == (409, "invalid_state")

    def test_a_departure_clean_waits_until_the_guest_checks_out(self, hotel, housekeeper):
        room = hotel.rooms["101"]
        make_stay(hotel, room, checkin=day(-2), checkout=BUSINESS_DATE)  # still in house
        task = HousekeepingTaskFactory(room=room, kind="departure_clean")

        with pytest.raises(DomainError) as error:
            svc.start_task(task, actor=housekeeper)

        assert (error.value.status_code, error.value.code) == (409, "guest_in_room")
        task.refresh_from_db()
        assert task.status == "pending"

    def test_a_stayover_is_done_with_the_guest_in_house(self, hotel, housekeeper):
        room = hotel.rooms["101"]
        make_stay(hotel, room, checkin=day(-2), checkout=day(2))
        task = HousekeepingTaskFactory(room=room, kind="stayover")

        svc.start_task(task, actor=housekeeper)

        task.refresh_from_db()
        assert task.status == "in_progress"


class TestFinish:
    def test_finishing_a_clean_leaves_the_room_clean(
        self, hotel, housekeeper, django_capture_on_commit_callbacks
    ):
        room = dirty(hotel.rooms["101"])
        task = HousekeepingTaskFactory(room=room, status="in_progress", assigned_to=housekeeper)

        with django_capture_on_commit_callbacks(execute=True):
            svc.finish_task(task, actor=housekeeper, notes="Cambié toallas")

        task.refresh_from_db()
        assert (task.status, task.finished_by, task.notes) == ("done", housekeeper, "Cambié toallas")
        assert task.finished_at is not None
        assert status_of(room) == "clean"
        assert not HousekeepingTask.objects.filter(kind="inspection").exists()
        assert AuditEvent.objects.filter(action="housekeeping.task_finished", actor=housekeeper).exists()

    def test_a_pending_task_can_be_finished_directly(self, hotel, housekeeper):
        task = HousekeepingTaskFactory(room=dirty(hotel.rooms["102"]), kind="stayover")
        svc.finish_task(task, actor=housekeeper)
        task.refresh_from_db()
        assert task.status == "done" and task.started_at is not None

    def test_with_inspection_required_the_room_waits_for_the_supervisor(
        self, hotel, housekeeper, django_capture_on_commit_callbacks
    ):
        HousekeepingSettings.objects.create(property=hotel.prop, require_inspection=True)
        room = dirty(hotel.rooms["301"])
        task = HousekeepingTaskFactory(room=room, status="in_progress", priority="high")

        with django_capture_on_commit_callbacks(execute=True):
            svc.finish_task(task, actor=housekeeper)

        assert status_of(room) == "clean"
        inspection = HousekeepingTask.objects.get(kind="inspection")
        assert (inspection.room, inspection.status, inspection.priority) == (room, "pending", "high")
        assert (inspection.estimated_minutes, inspection.created_source) == (10, "inspection")
        assert inspection.business_date == BUSINESS_DATE

    @pytest.mark.parametrize("kind", ["turndown", "custom"])
    def test_turndown_and_other_tasks_do_not_change_the_room_status(self, hotel, housekeeper, kind):
        room = dirty(hotel.rooms["201"])
        svc.finish_task(HousekeepingTaskFactory(room=room, kind=kind), actor=housekeeper)
        assert status_of(room) == "dirty"

    def test_a_room_out_of_service_stays_out_of_service(self, hotel, housekeeper):
        room = hotel.rooms["202"]
        Room.objects.filter(pk=room.pk).update(housekeeping_status="out_of_service")
        svc.finish_task(HousekeepingTaskFactory(room=room, kind="deep_clean"), actor=housekeeper)
        assert status_of(room) == "out_of_service"

    def test_an_inspection_is_not_finished_but_inspected(self, hotel, supervisor):
        task = HousekeepingTaskFactory(room=hotel.rooms["101"], kind="inspection")
        with pytest.raises(DomainError) as error:
            svc.finish_task(task, actor=supervisor)
        assert error.value.code == "invalid_state"

    def test_a_closed_task_cannot_be_finished(self, hotel, housekeeper):
        task = HousekeepingTaskFactory(room=hotel.rooms["101"], status="cancelled")
        with pytest.raises(DomainError) as error:
            svc.finish_task(task, actor=housekeeper)
        assert error.value.code == "invalid_state"


class TestInspect:
    def test_passing_the_inspection_leaves_the_room_inspected(self, hotel, supervisor):
        room = hotel.rooms["301"]
        inspection = HousekeepingTaskFactory(room=room, kind="inspection")

        svc.inspect_task(inspection, actor=supervisor)

        inspection.refresh_from_db()
        assert (inspection.status, inspection.finished_by) == ("inspected", supervisor)
        assert status_of(room) == "inspected"

    def test_a_failed_inspection_sends_the_room_back_to_its_housekeeper(
        self, hotel, housekeeper, supervisor, django_capture_on_commit_callbacks
    ):
        room = hotel.rooms["301"]
        HousekeepingTaskFactory(room=room, status="done", assigned_to=housekeeper, finished_by=housekeeper)
        inspection = HousekeepingTaskFactory(room=room, kind="inspection")

        with django_capture_on_commit_callbacks(execute=True):
            svc.inspect_task(inspection, actor=supervisor, passed=False, notes="Falta cambiar sábanas")

        inspection.refresh_from_db()
        assert inspection.status == "done" and "Falta cambiar sábanas" in inspection.notes
        assert status_of(room) == "dirty"
        redo = HousekeepingTask.objects.get(status="pending")
        assert (redo.kind, redo.priority, redo.assigned_to, redo.created_source) == (
            "departure_clean",
            "high",
            housekeeper,
            "inspection",
        )
        assert "Falta cambiar sábanas" in redo.notes

    def test_a_finished_clean_can_be_inspected_directly(self, hotel, supervisor):
        room = hotel.rooms["201"]
        clean = HousekeepingTaskFactory(room=room, status="done")
        pending_inspection = HousekeepingTaskFactory(room=room, kind="inspection")

        svc.inspect_task(clean, actor=supervisor)

        clean.refresh_from_db()
        pending_inspection.refresh_from_db()
        assert (clean.status, pending_inspection.status) == ("inspected", "inspected")
        assert status_of(room) == "inspected"

    def test_a_clean_not_finished_yet_cannot_be_inspected(self, hotel, supervisor):
        task = HousekeepingTaskFactory(room=hotel.rooms["201"], status="in_progress")
        with pytest.raises(DomainError) as error:
            svc.inspect_task(task, actor=supervisor)
        assert (error.value.status_code, error.value.code) == (409, "invalid_state")


class TestAssignAndCancel:
    def test_assigns_to_a_housekeeper_of_the_property_and_unassigns(self, hotel, housekeeper, supervisor):
        task = HousekeepingTaskFactory(room=hotel.rooms["101"])

        svc.assign_task(task, user=housekeeper, actor=supervisor)
        task.refresh_from_db()
        assert task.assigned_to == housekeeper

        svc.assign_task(task, user=None, actor=supervisor)
        task.refresh_from_db()
        assert task.assigned_to is None

    def test_only_people_who_clean_in_this_property_can_be_assigned(
        self, hotel, supervisor, make_member, organization
    ):
        from apps.core.tests.factories import PropertyFactory

        task = HousekeepingTaskFactory(room=hotel.rooms["101"])
        front_desk = make_member("front_desk")
        elsewhere = make_member("housekeeping", properties=[PropertyFactory(organization=organization)])

        for user in (front_desk, elsewhere):
            with pytest.raises(DomainError) as error:
                svc.assign_task(task, user=user, actor=supervisor)
            assert (error.value.status_code, error.value.code) == (400, "invalid_assignee")

    def test_cancels_an_open_task_but_not_a_finished_one(self, hotel, supervisor):
        task = HousekeepingTaskFactory(room=hotel.rooms["101"])
        svc.cancel_task(task, actor=supervisor, reason="Duplicada")
        task.refresh_from_db()
        assert task.status == "cancelled" and "Duplicada" in task.notes

        done = HousekeepingTaskFactory(room=hotel.rooms["102"], status="done")
        with pytest.raises(DomainError) as error:
            svc.cancel_task(done, actor=supervisor)
        assert error.value.code == "invalid_state"


class TestManualTask:
    def test_creates_a_deep_clean_with_double_minutes(self, hotel, supervisor, housekeeper):
        task = svc.create_task(
            hotel.prop,
            room=hotel.rooms["301"],
            kind="deep_clean",
            priority="low",
            notes="Lavar cortinas",
            assigned_to=housekeeper,
            actor=supervisor,
        )
        assert (task.kind, task.estimated_minutes, task.priority, task.assigned_to) == (
            "deep_clean",
            120,
            "low",
            housekeeper,
        )
        assert (task.business_date, task.created_source, task.notes) == (
            BUSINESS_DATE,
            "manual",
            "Lavar cortinas",
        )

    def test_a_second_open_turnover_for_the_room_is_refused(self, hotel, supervisor):
        HousekeepingTaskFactory(room=hotel.rooms["101"], kind="stayover")
        with pytest.raises(DomainError) as error:
            svc.create_task(hotel.prop, room=hotel.rooms["101"], kind="departure_clean", actor=supervisor)
        assert (error.value.status_code, error.value.code) == (409, "task_exists")
