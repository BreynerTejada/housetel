"""`/api/v1/housekeeping/tasks/`: housekeepers see and work only their own tasks, supervisors everything."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.tests.factories import PropertyFactory
from apps.housekeeping.models import HousekeepingTask
from apps.housekeeping.tests.conftest import BUSINESS_DATE, day, make_stay
from apps.housekeeping.tests.factories import HousekeepingTaskFactory
from apps.inventory.models import Room
from apps.inventory.tests.factories import RoomFactory

pytestmark = pytest.mark.django_db
URL = "/api/v1/housekeeping/tasks/"


@pytest.fixture
def housekeeper(make_member):
    return make_member("housekeeping", full_name="Luz Marina Pérez")


@pytest.fixture
def colleague(make_member):
    return make_member("housekeeping", full_name="Rosa Díaz")


@pytest.fixture
def supervisor(make_member):
    return make_member("housekeeping_supervisor")


def ids(response) -> set[str]:
    return {row["id"] for row in response.json()["results"]}


class TestList:
    def test_a_supervisor_sees_the_day_including_what_is_still_open_from_yesterday(
        self, hotel, api_for, supervisor
    ):
        today = HousekeepingTaskFactory(room=hotel.rooms["101"])
        carried = HousekeepingTaskFactory(room=hotel.rooms["102"], business_date=day(-1))
        HousekeepingTaskFactory(room=hotel.rooms["201"], business_date=day(-1), status="done")
        other_hotel = HousekeepingTaskFactory(room=RoomFactory(room_type__property=PropertyFactory()))

        response = api_for(supervisor, hotel.prop).get(URL)

        assert response.status_code == 200
        assert ids(response) == {str(today.pk), str(carried.pk)}
        assert str(other_hotel.pk) not in ids(response)

    def test_a_housekeeper_only_sees_her_own_tasks(self, hotel, api_for, housekeeper, colleague):
        mine = HousekeepingTaskFactory(room=hotel.rooms["101"], assigned_to=housekeeper)
        HousekeepingTaskFactory(room=hotel.rooms["102"], assigned_to=colleague)
        HousekeepingTaskFactory(room=hotel.rooms["201"])

        response = api_for(housekeeper, hotel.prop).get(URL)

        assert ids(response) == {str(mine.pk)}

    def test_mine_filters_the_tasks_of_whoever_asks(self, hotel, api_for, supervisor, housekeeper):
        own = HousekeepingTaskFactory(room=hotel.rooms["101"], assigned_to=supervisor, kind="inspection")
        HousekeepingTaskFactory(room=hotel.rooms["102"], assigned_to=housekeeper)

        assert ids(api_for(supervisor, hotel.prop).get(URL, {"mine": 1})) == {str(own.pk)}

    def test_filters_by_status_floor_kind_assignee_and_date(self, hotel, api_for, supervisor, housekeeper):
        a = HousekeepingTaskFactory(room=hotel.rooms["101"], status="in_progress", assigned_to=housekeeper)
        b = HousekeepingTaskFactory(room=hotel.rooms["201"], kind="stayover")
        c = HousekeepingTaskFactory(room=hotel.rooms["202"], status="done")
        old = HousekeepingTaskFactory(room=hotel.rooms["301"], business_date=day(-3), status="done")
        api = api_for(supervisor, hotel.prop)

        assert ids(api.get(URL, {"status": ["in_progress", "done"]})) == {str(a.pk), str(c.pk)}
        assert ids(api.get(URL, {"floor": "2"})) == {str(b.pk), str(c.pk)}
        assert ids(api.get(URL, {"kind": "stayover"})) == {str(b.pk)}
        assert ids(api.get(URL, {"assignee": "none"})) == {str(b.pk), str(c.pk)}
        assert ids(api.get(URL, {"assignee": str(housekeeper.pk)})) == {str(a.pk)}
        assert ids(api.get(URL, {"date": day(-3).isoformat()})) == {str(old.pk)}
        assert api.get(URL, {"date": "ayer"}).json()["code"] == "validation_error"

    def test_open_work_comes_first_by_priority(self, hotel, api_for, supervisor):
        done = HousekeepingTaskFactory(room=hotel.rooms["101"], status="done")
        normal = HousekeepingTaskFactory(room=hotel.rooms["102"])
        urgent = HousekeepingTaskFactory(room=hotel.rooms["301"], priority="urgent")
        started = HousekeepingTaskFactory(room=hotel.rooms["201"], status="in_progress")

        rows = api_for(supervisor, hotel.prop).get(URL).json()["results"]

        assert [row["id"] for row in rows] == [str(t.pk) for t in (started, urgent, normal, done)]

    def test_the_row_tells_the_housekeeper_what_she_needs(self, hotel, api_for, supervisor, housekeeper):
        room = hotel.rooms["101"]
        leaving = make_stay(hotel, room, checkin=day(-2), checkout=BUSINESS_DATE)
        arriving = make_stay(hotel, room, checkin=BUSINESS_DATE, checkout=day(2), status="confirmed")
        arriving.reservation.eta = "14:30"
        arriving.reservation.save(update_fields=["eta"])
        task = HousekeepingTaskFactory(
            room=room, priority="high", assigned_to=housekeeper, reservation=leaving.reservation, notes="VIP"
        )

        row = api_for(supervisor, hotel.prop).get(URL).json()["results"][0]

        assert row["id"] == str(task.pk)
        assert row["room"] == {
            "id": str(room.pk),
            "number": "101",
            "name": "",
            "floor": "1",
            "housekeeping_status": "clean",
            "room_type": {
                "id": str(hotel.dbl.pk),
                "code": "DBL",
                "name": hotel.dbl.name,
                "color": hotel.dbl.color,
                "kind": "private",
            },
        }
        assert (row["kind"], row["status"], row["priority"], row["business_date"]) == (
            "departure_clean",
            "pending",
            "high",
            "2026-10-01",
        )
        assert row["assigned_to"] == {
            "id": str(housekeeper.pk),
            "full_name": "Luz Marina Pérez",
            "email": housekeeper.email,
        }
        assert row["reservation"] == {"id": str(leaving.reservation.pk), "code": leaving.reservation.code}
        assert (row["waiting_for_checkout"], row["overdue"], row["notes"]) == (True, False, "VIP")
        assert row["arrival_today"] == {"code": arriving.reservation.code, "eta": "14:30", "is_vip": False}
        assert (row["estimated_minutes"], row["bed"], row["started_at"], row["created_source"]) == (
            30,
            None,
            None,
            "manual",
        )

    def test_the_number_of_queries_does_not_grow_with_the_tasks(
        self, hotel, api_for, supervisor, housekeeper
    ):
        api = api_for(supervisor, hotel.prop)

        def count():
            with CaptureQueriesContext(connection) as queries:
                assert api.get(URL).status_code == 200
            return len(queries)

        HousekeepingTaskFactory(room=hotel.rooms["101"], assigned_to=housekeeper)
        few = count()
        for number in ("102", "201", "202", "301", "D1"):
            HousekeepingTaskFactory(room=hotel.rooms[number], assigned_to=housekeeper, kind="stayover")
        assert count() == few


class TestWork:
    def test_the_housekeeper_starts_and_finishes_her_task(self, hotel, api_for, housekeeper):
        room = hotel.rooms["102"]
        Room.objects.filter(pk=room.pk).update(housekeeping_status="dirty")
        task = HousekeepingTaskFactory(room=room, assigned_to=housekeeper)
        api = api_for(housekeeper, hotel.prop)

        started = api.post(f"{URL}{task.pk}/start/")
        assert (started.status_code, started.json()["status"]) == (200, "in_progress")

        finished = api.post(f"{URL}{task.pk}/finish/", {"notes": "Todo listo"})
        assert finished.status_code == 200
        assert (finished.json()["status"], finished.json()["notes"]) == ("done", "Todo listo")
        assert finished.json()["room"]["housekeeping_status"] == "clean"

    def test_tasks_of_someone_else_do_not_exist_for_her(self, hotel, api_for, housekeeper, colleague):
        task = HousekeepingTaskFactory(room=hotel.rooms["101"], assigned_to=colleague)
        api = api_for(housekeeper, hotel.prop)
        assert api.post(f"{URL}{task.pk}/start/").status_code == 404
        assert api.get(f"{URL}{task.pk}/").status_code == 404

    def test_the_front_desk_sees_but_does_not_clean(self, hotel, api_for, make_member):
        front = make_member("front_desk")
        task = HousekeepingTaskFactory(room=hotel.rooms["101"])
        api = api_for(front, hotel.prop)

        assert ids(api.get(URL)) == {str(task.pk)}
        response = api.post(f"{URL}{task.pk}/start/")
        assert (response.status_code, response.json()["permission"]) == (403, "housekeeping.work")

    def test_a_departure_waits_for_the_check_out(self, hotel, api_for, housekeeper):
        room = hotel.rooms["101"]
        make_stay(hotel, room, checkin=day(-1), checkout=BUSINESS_DATE)
        task = HousekeepingTaskFactory(room=room, assigned_to=housekeeper)

        response = api_for(housekeeper, hotel.prop).post(f"{URL}{task.pk}/start/")

        assert (response.status_code, response.json()["code"]) == (409, "guest_in_room")


class TestSupervision:
    def test_inspects_assigns_and_cancels(self, hotel, api_for, supervisor, housekeeper):
        api = api_for(supervisor, hotel.prop)
        inspection = HousekeepingTaskFactory(room=hotel.rooms["301"], kind="inspection")
        response = api.post(f"{URL}{inspection.pk}/inspect/", {"passed": True})
        assert (response.status_code, response.json()["status"]) == (200, "inspected")

        task = HousekeepingTaskFactory(room=hotel.rooms["101"])
        response = api.post(f"{URL}{task.pk}/assign/", {"user_id": str(housekeeper.pk)})
        assert (response.status_code, response.json()["assigned_to"]["id"]) == (200, str(housekeeper.pk))
        response = api.post(f"{URL}{task.pk}/assign/", {"user_id": None})
        assert response.json()["assigned_to"] is None

        response = api.post(f"{URL}{task.pk}/cancel/", {"reason": "Duplicada"})
        assert (response.status_code, response.json()["status"]) == (200, "cancelled")

    def test_assigning_to_someone_who_does_not_clean_is_refused(
        self, hotel, api_for, supervisor, make_member
    ):
        task = HousekeepingTaskFactory(room=hotel.rooms["101"])
        front = make_member("front_desk")
        api = api_for(supervisor, hotel.prop)

        assert (
            api.post(f"{URL}{task.pk}/assign/", {"user_id": str(front.pk)}).json()["code"]
            == "invalid_assignee"
        )
        unknown = api.post(f"{URL}{task.pk}/assign/", {"user_id": "7f0f0f0f-0000-4000-8000-000000000000"})
        assert (unknown.status_code, unknown.json()["code"]) == (400, "invalid_assignee")

    def test_creates_a_manual_task(self, hotel, api_for, supervisor, housekeeper):
        response = api_for(supervisor, hotel.prop).post(
            URL,
            {
                "room_id": str(hotel.rooms["301"].pk),
                "kind": "deep_clean",
                "priority": "low",
                "notes": "Lavar cortinas",
                "assigned_to_id": str(housekeeper.pk),
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert (body["kind"], body["priority"], body["estimated_minutes"], body["assigned_to"]["id"]) == (
            "deep_clean",
            "low",
            120,
            str(housekeeper.pk),
        )

    def test_a_manual_task_needs_a_room_of_this_hotel_and_a_known_kind(self, hotel, api_for, supervisor):
        api = api_for(supervisor, hotel.prop)
        foreign = RoomFactory(room_type__property=PropertyFactory())
        response = api.post(URL, {"room_id": str(foreign.pk), "kind": "deep_clean"})
        assert (response.status_code, response.json()["fields"].keys()) == (400, {"room_id"})
        response = api.post(URL, {"room_id": str(hotel.rooms["101"].pk), "kind": "sweep"})
        assert (response.status_code, list(response.json()["fields"])) == (400, ["kind"])

    def test_edits_priority_notes_and_minutes(self, hotel, api_for, supervisor):
        task = HousekeepingTaskFactory(room=hotel.rooms["101"])
        response = api_for(supervisor, hotel.prop).patch(
            f"{URL}{task.pk}/", {"priority": "urgent", "notes": "Llega un VIP", "estimated_minutes": 45}
        )
        assert response.status_code == 200
        task.refresh_from_db()
        assert (task.priority, task.notes, task.estimated_minutes) == ("urgent", "Llega un VIP", 45)

    def test_auto_assign_and_generate_from_the_board(
        self, hotel, api_for, supervisor, housekeeper, colleague
    ):
        Room.objects.filter(pk__in=[hotel.rooms["101"].pk, hotel.rooms["201"].pk]).update(
            housekeeping_status="dirty"
        )
        api = api_for(supervisor, hotel.prop)

        generated = api.post(f"{URL}generate/")
        assert (generated.status_code, generated.json()["created"]) == (200, 2)

        report = api.post(f"{URL}auto-assign/", {"user_ids": [str(colleague.pk)]})
        assert report.status_code == 200
        assert (report.json()["assigned"], [row["user_id"] for row in report.json()["staff"]]) == (
            2,
            [str(colleague.pk)],
        )
        assert set(HousekeepingTask.objects.values_list("assigned_to", flat=True)) == {colleague.pk}

    def test_auto_assign_only_accepts_housekeepers_of_the_hotel(
        self, hotel, api_for, supervisor, make_member
    ):
        front = make_member("front_desk")
        response = api_for(supervisor, hotel.prop).post(f"{URL}auto-assign/", {"user_ids": [str(front.pk)]})
        assert (response.status_code, response.json()["code"]) == (400, "invalid_assignee")

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("post", "{id}/inspect/", {}),
            ("post", "{id}/assign/", {"user_id": None}),
            ("post", "{id}/cancel/", {}),
            ("patch", "{id}/", {"priority": "low"}),
            ("post", "auto-assign/", {}),
            ("post", "generate/", {}),
            ("post", "", {"kind": "custom"}),
        ],
    )
    def test_housekeepers_cannot_supervise(self, hotel, api_for, housekeeper, method, path, body):
        task = HousekeepingTaskFactory(room=hotel.rooms["101"], assigned_to=housekeeper)
        response = getattr(api_for(housekeeper, hotel.prop), method)(URL + path.format(id=task.pk), body)
        assert (response.status_code, response.json()["permission"]) == (403, "housekeeping.supervise")
