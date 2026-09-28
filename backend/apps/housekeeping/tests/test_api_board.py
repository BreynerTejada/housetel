"""Supervision endpoints: `board/`, `summary/`, `staff/`, `settings/` and the validated room-status proxy
`rooms/{id}/status/` (inventory's own endpoint needs `inventory.manage`, which housekeeping roles lack)."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.models import AuditEvent
from apps.core.tests.factories import PropertyFactory
from apps.housekeeping.models import HousekeepingSettings, HousekeepingTask
from apps.housekeeping.services import tickets as ticket_svc
from apps.housekeeping.tests.conftest import BUSINESS_DATE, day, make_stay
from apps.housekeeping.tests.factories import HousekeepingTaskFactory, MaintenanceTicketFactory
from apps.inventory.models import Room
from apps.inventory.tests.factories import RoomFactory

pytestmark = pytest.mark.django_db
BASE = "/api/v1/housekeeping/"


@pytest.fixture
def housekeeper(make_member):
    return make_member("housekeeping", full_name="Luz Marina Pérez", email="luz@example.com")


@pytest.fixture
def colleague(make_member):
    return make_member("housekeeping", full_name="Rosa Díaz")


@pytest.fixture
def supervisor(make_member):
    return make_member("housekeeping_supervisor")


def set_status(room, status):
    Room.objects.filter(pk=room.pk).update(housekeeping_status=status)


@pytest.fixture
def day_in_progress(hotel, housekeeper):
    """101: guest leaving today + VIP arriving at 15:00, departure clean for Luz · 102: dirty, clean in
    progress · 201: blocked by a ticket · 202: inspected, inspection pending · 301: stayover done ·
    D1: two beds in house (a cancelled task)."""
    rooms = hotel.rooms
    leaving = make_stay(hotel, rooms["101"], checkin=day(-2), checkout=BUSINESS_DATE, adults=2)
    arriving = make_stay(hotel, rooms["101"], checkin=BUSINESS_DATE, checkout=day(2), status="confirmed")
    arriving.reservation.eta = "15:00"
    arriving.reservation.save(update_fields=["eta"])
    arriving.reservation.booker.is_vip = True
    arriving.reservation.booker.save(update_fields=["is_vip"])
    make_stay(hotel, rooms["D1"], bed=hotel.beds["A"], checkin=day(-1), checkout=day(2), adults=1, children=0)
    make_stay(hotel, rooms["D1"], bed=hotel.beds["B"], checkin=day(-1), checkout=day(1), adults=1, children=0)
    set_status(rooms["102"], "dirty")
    set_status(rooms["202"], "inspected")
    ticket = ticket_svc.create_ticket(
        hotel.prop, room=rooms["201"], title="Aire", blocks_room=True, blocked_until=day(2)
    )
    tasks = {
        "101": HousekeepingTaskFactory(
            room=rooms["101"], assigned_to=housekeeper, reservation=leaving.reservation, priority="high"
        ),
        "102": HousekeepingTaskFactory(room=rooms["102"], status="in_progress"),
        "202": HousekeepingTaskFactory(room=rooms["202"], kind="inspection", estimated_minutes=10),
        "301": HousekeepingTaskFactory(
            room=rooms["301"], kind="stayover", status="done", estimated_minutes=60
        ),
        "D1": HousekeepingTaskFactory(room=rooms["D1"], kind="stayover", status="cancelled"),
    }
    return {"tasks": tasks, "ticket": ticket, "arriving": arriving, "leaving": leaving}


class TestBoard:
    def test_rooms_by_floor_with_occupancy_arrivals_tasks_and_blocks(
        self, hotel, api_for, supervisor, day_in_progress
    ):
        response = api_for(supervisor, hotel.prop).get(f"{BASE}board/")

        assert response.status_code == 200
        body = response.json()
        assert body["business_date"] == "2026-10-01"
        assert [(f["floor"], [r["number"] for r in f["rooms"]]) for f in body["floors"]] == [
            ("1", ["101", "102", "D1"]),
            ("2", ["201", "202"]),
            ("3", ["301"]),
        ]
        rooms = {room["number"]: room for floor in body["floors"] for room in floor["rooms"]}
        r101 = rooms["101"]
        assert (r101["housekeeping_status"], r101["occupied"], r101["open_tickets"]) == ("clean", True, 0)
        assert r101["room_type"]["code"] == "DBL"
        assert r101["in_house"] == {
            "code": day_in_progress["leaving"].reservation.code,
            "checkout_date": "2026-10-01",
            "departs_today": True,
            "guests": day_in_progress["leaving"].adults + day_in_progress["leaving"].children,
            "is_vip": False,
        }
        assert r101["arrival_today"] == {
            "code": day_in_progress["arriving"].reservation.code,
            "eta": "15:00",
            "is_vip": True,
        }
        [task] = r101["tasks"]
        assert (task["id"], task["waiting_for_checkout"], task["assigned_to"]["full_name"]) == (
            str(day_in_progress["tasks"]["101"].pk),
            True,
            "Luz Marina Pérez",
        )
        r201 = rooms["201"]
        assert (r201["housekeeping_status"], r201["open_tickets"], r201["tasks"]) == ("out_of_service", 1, [])
        assert (r201["active_block"]["kind"], r201["active_block"]["end_date"]) == (
            "out_of_order",
            "2026-10-03",
        )
        assert rooms["D1"]["in_house"]["guests"] == 2
        assert rooms["202"]["arrival_today"] is None and rooms["202"]["in_house"] is None
        assert body["settings"] == {
            "stayover_frequency_days": 1,
            "require_inspection": False,
            "auto_assign": True,
            "minutes_per_shift": 420,
        }
        assert [row["full_name"] for row in body["staff"]] == ["Luz Marina Pérez"]

    def test_a_housekeeper_only_sees_her_own_tasks_on_the_board(
        self, hotel, api_for, housekeeper, colleague, day_in_progress
    ):
        body = api_for(housekeeper, hotel.prop).get(f"{BASE}board/").json()

        tasks = [task["id"] for floor in body["floors"] for room in floor["rooms"] for task in room["tasks"]]
        assert tasks == [str(day_in_progress["tasks"]["101"].pk)]
        assert [row["id"] for row in body["staff"]] == [str(housekeeper.pk)]

    def test_the_number_of_queries_does_not_grow_with_the_rooms(
        self, hotel, api_for, supervisor, housekeeper
    ):
        api = api_for(supervisor, hotel.prop)

        def count():
            with CaptureQueriesContext(connection) as queries:
                assert api.get(f"{BASE}board/").status_code == 200
            return len(queries)

        HousekeepingTaskFactory(room=hotel.rooms["101"], assigned_to=housekeeper)
        count()  # the first call creates the hotel's settings row
        few = count()
        for number in ("401", "402", "403"):
            room = RoomFactory(room_type=hotel.dbl, number=number, floor="4")
            HousekeepingTaskFactory(room=room, assigned_to=housekeeper)
            make_stay(hotel, room, checkin=day(-1), checkout=day(1))
        MaintenanceTicketFactory(room=hotel.rooms["202"])
        assert count() == few


def test_summary_counts_rooms_tasks_minutes_and_tickets(hotel, api_for, make_member, day_in_progress):
    response = api_for(make_member("front_desk"), hotel.prop).get(f"{BASE}summary/")

    assert response.status_code == 200
    assert response.json() == {
        "business_date": "2026-10-01",
        "rooms": {"total": 6, "clean": 3, "dirty": 1, "inspected": 1, "out_of_service": 1, "occupied": 2},
        "tasks": {
            "total": 3,
            "pending": 1,
            "in_progress": 1,
            "done": 1,
            "inspections_pending": 1,
            "unassigned": 0,
        },
        "minutes": {"total": 120, "done": 60},
        "tickets": {"open": 1, "blocking": 1},
    }


def test_staff_lists_housekeepers_with_their_load_and_the_technicians(
    hotel, api_for, supervisor, housekeeper, colleague, make_member
):
    technician = make_member("maintenance", full_name="Jorge Técnico")
    HousekeepingTaskFactory(room=hotel.rooms["101"], assigned_to=housekeeper, estimated_minutes=30)
    HousekeepingTaskFactory(
        room=hotel.rooms["102"], assigned_to=housekeeper, estimated_minutes=45, status="done"
    )
    MaintenanceTicketFactory(room=hotel.rooms["201"], assigned_to=technician)

    body = api_for(supervisor, hotel.prop).get(f"{BASE}staff/").json()

    assert body["housekeepers"] == [
        {
            "id": str(housekeeper.pk),
            "full_name": "Luz Marina Pérez",
            "email": "luz@example.com",
            "minutes": 75,
            "minutes_done": 45,
            "tasks": 2,
            "tasks_done": 1,
        },
        {
            "id": str(colleague.pk),
            "full_name": "Rosa Díaz",
            "email": colleague.email,
            "minutes": 0,
            "minutes_done": 0,
            "tasks": 0,
            "tasks_done": 0,
        },
    ]
    assert body["maintenance"] == [
        {"id": str(technician.pk), "full_name": "Jorge Técnico", "email": technician.email, "open_tickets": 1}
    ]


class TestSettings:
    URL = f"{BASE}settings/"

    def test_everyone_with_access_reads_the_defaults(self, hotel, api_for, make_member):
        response = api_for(make_member("front_desk"), hotel.prop).get(self.URL)
        assert response.json() == {
            "stayover_frequency_days": 1,
            "require_inspection": False,
            "auto_assign": True,
            "minutes_per_shift": 420,
        }

    def test_the_supervisor_changes_them_and_it_is_audited(self, hotel, api_for, supervisor):
        response = api_for(supervisor, hotel.prop).patch(
            self.URL, {"stayover_frequency_days": 2, "require_inspection": True}
        )

        assert response.status_code == 200
        assert (response.json()["stayover_frequency_days"], response.json()["require_inspection"]) == (
            2,
            True,
        )
        saved = HousekeepingSettings.objects.get(property=hotel.prop)
        assert (saved.stayover_frequency_days, saved.require_inspection, saved.auto_assign) == (2, True, True)
        event = AuditEvent.objects.get(action="housekeeping.settings_updated")
        assert event.actor == supervisor and event.changes["stayover_frequency_days"] == [1, 2]

    @pytest.mark.parametrize(
        "body",
        [{"minutes_per_shift": 30}, {"stayover_frequency_days": 45}, {"require_inspection": "tal vez"}],
    )
    def test_out_of_range_values_are_refused(self, hotel, api_for, supervisor, body):
        response = api_for(supervisor, hotel.prop).patch(self.URL, body)
        assert (response.status_code, list(response.json()["fields"])) == (400, list(body))

    def test_housekeepers_cannot_change_them(self, hotel, api_for, housekeeper):
        response = api_for(housekeeper, hotel.prop).patch(self.URL, {"auto_assign": False})
        assert (response.status_code, response.json()["permission"]) == (403, "housekeeping.supervise")


class TestRoomStatus:
    def url(self, room):
        return f"{BASE}rooms/{room.pk}/status/"

    def test_a_housekeeper_marks_a_room_dirty_and_it_gets_its_clean(
        self, hotel, api_for, housekeeper, django_capture_on_commit_callbacks
    ):
        room = hotel.rooms["202"]

        with django_capture_on_commit_callbacks(execute=True):
            response = api_for(housekeeper, hotel.prop).post(self.url(room), {"housekeeping_status": "dirty"})

        assert response.status_code == 200
        assert response.json() == {"id": str(room.pk), "number": "202", "housekeeping_status": "dirty"}
        assert HousekeepingTask.objects.get(room=room).kind == "departure_clean"
        event = AuditEvent.objects.get(action="inventory.room_status_changed")
        assert (event.actor, event.source) == (housekeeper, "user")

    @pytest.mark.parametrize("status", ["inspected", "out_of_service"])
    def test_inspecting_or_closing_a_room_is_for_supervisors(
        self, hotel, api_for, housekeeper, supervisor, status
    ):
        room = hotel.rooms["202"]
        refused = api_for(housekeeper, hotel.prop).post(self.url(room), {"housekeeping_status": status})
        assert (refused.status_code, refused.json()["permission"]) == (403, "housekeeping.supervise")

        allowed = api_for(supervisor, hotel.prop).post(self.url(room), {"housekeeping_status": status})
        assert (allowed.status_code, allowed.json()["housekeeping_status"]) == (200, status)

    def test_a_room_held_by_a_maintenance_ticket_stays_out_of_service(self, hotel, api_for, supervisor):
        room = hotel.rooms["201"]
        ticket_svc.create_ticket(hotel.prop, room=room, title="Aire", blocks_room=True)

        response = api_for(supervisor, hotel.prop).post(self.url(room), {"housekeeping_status": "clean"})

        assert (response.status_code, response.json()["code"]) == (409, "room_blocked")
        assert Room.objects.get(pk=room.pk).housekeeping_status == "out_of_service"

    def test_validation_permissions_and_isolation(self, hotel, api_for, housekeeper, make_member):
        api = api_for(housekeeper, hotel.prop)
        invalid = api.post(self.url(hotel.rooms["101"]), {"housekeeping_status": "sparkling"})
        assert (invalid.status_code, list(invalid.json()["fields"])) == (400, ["housekeeping_status"])

        foreign = RoomFactory(room_type__property=PropertyFactory(organization=hotel.prop.organization))
        assert api.post(self.url(foreign), {"housekeeping_status": "dirty"}).status_code == 404

        front = api_for(make_member("front_desk"), hotel.prop)
        response = front.post(self.url(hotel.rooms["101"]), {"housekeeping_status": "dirty"})
        assert (response.status_code, response.json()["permission"]) == (403, "housekeeping.work")
