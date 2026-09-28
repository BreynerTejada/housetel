"""`/api/v1/housekeeping/tickets/`: anyone who cleans or repairs reports damage (with photos from the phone);
maintenance and supervisors work the tickets; blocking tickets hold the room out of service."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.core.tests.factories import PropertyFactory
from apps.housekeeping.models import HousekeepingTask, MaintenanceTicket, TicketPhoto
from apps.housekeeping.services import tickets as svc
from apps.housekeeping.tests.conftest import BUSINESS_DATE, JPEG, PNG, day, make_stay
from apps.housekeeping.tests.factories import MaintenanceTicketFactory
from apps.inventory.models import Room, RoomBlock
from apps.inventory.tests.factories import RoomFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("private_media")]
URL = "/api/v1/housekeeping/tickets/"


@pytest.fixture
def housekeeper(make_member):
    return make_member("housekeeping", full_name="Luz Marina Pérez")


@pytest.fixture
def technician(make_member):
    return make_member("maintenance", full_name="Jorge Técnico")


@pytest.fixture
def supervisor(make_member):
    return make_member("housekeeping_supervisor")


def photo(content=JPEG, name="IMG_2031.jpg"):
    return SimpleUploadedFile(name, content, content_type="image/jpeg")


def ids(response) -> list[str]:
    return [row["id"] for row in response.json()["results"]]


def status_of(room) -> str:
    return Room.objects.get(pk=room.pk).housekeeping_status


class TestReport:
    def test_a_housekeeper_reports_damage_with_photos_from_her_phone(self, hotel, api_for, housekeeper):
        room = hotel.rooms["201"]

        response = api_for(housekeeper, hotel.prop).post(
            URL,
            {
                "room_id": str(room.pk),
                "title": "Ducha sin agua caliente",
                "description": "El calentador no prende",
                "priority": "high",
                "blocks_room": "true",
                "photos": [photo(), photo(PNG, "IMG_2032.png")],
            },
            format="multipart",
        )

        assert response.status_code == 201
        body = response.json()
        assert (body["title"], body["priority"], body["status"], body["blocks_room"]) == (
            "Ducha sin agua caliente",
            "high",
            "open",
            True,
        )
        assert body["room"]["number"] == "201"
        assert body["reported_by"]["id"] == str(housekeeper.pk)
        assert [p["content_type"] for p in body["photos"]] == ["image/jpeg", "image/png"]
        assert all(p["file_url"].startswith("/api/v1/housekeeping/ticket-photos/") for p in body["photos"])
        assert (body["block"]["start_date"], body["block"]["end_date"]) == ("2026-10-01", "2026-10-02")
        assert status_of(room) == "out_of_service"

    def test_a_common_area_is_reported_with_a_location(self, hotel, api_for, housekeeper):
        response = api_for(housekeeper, hotel.prop).post(
            URL, {"location": "Piscina", "title": "Baldosa rota"}
        )
        assert response.status_code == 201
        assert (response.json()["room"], response.json()["location"]) == (None, "Piscina")

    def test_a_photo_that_is_not_an_image_creates_nothing(self, hotel, api_for, housekeeper):
        response = api_for(housekeeper, hotel.prop).post(
            URL,
            {
                "room_id": str(hotel.rooms["101"].pk),
                "title": "Espejo roto",
                "blocks_room": "true",
                "photos": [photo(), photo(b"%PDF-1.7", "factura.pdf")],
            },
            format="multipart",
        )

        assert (response.status_code, response.json()["code"]) == (400, "invalid_file_type")
        assert not MaintenanceTicket.objects.exists() and not TicketPhoto.objects.exists()
        assert not RoomBlock.objects.exists() and status_of(hotel.rooms["101"]) == "clean"

    def test_a_room_of_another_hotel_is_refused(self, hotel, api_for, housekeeper):
        foreign = RoomFactory(room_type__property=PropertyFactory())
        response = api_for(housekeeper, hotel.prop).post(URL, {"room_id": str(foreign.pk), "title": "Fuga"})
        assert (response.status_code, list(response.json()["fields"])) == (400, ["room_id"])

    def test_blocking_over_bookings_needs_force_which_only_maintenance_has(
        self, hotel, api_for, housekeeper, technician
    ):
        room = hotel.rooms["202"]
        stay = make_stay(hotel, room, checkin=day(1), checkout=day(3), status="confirmed")
        body = {
            "room_id": str(room.pk),
            "title": "Fuga",
            "blocks_room": True,
            "blocked_until": day(2).isoformat(),
        }

        conflict = api_for(housekeeper, hotel.prop).post(URL, body)
        assert (conflict.status_code, conflict.json()["code"]) == (409, "room_has_reservations")
        assert conflict.json()["reservations"] == [stay.reservation.code]

        forced = api_for(housekeeper, hotel.prop).post(URL, {**body, "force": True})
        assert (forced.status_code, forced.json()["permission"]) == (403, "housekeeping.maintenance")

        assert api_for(technician, hotel.prop).post(URL, {**body, "force": True}).status_code == 201

    def test_the_front_desk_sees_tickets_but_does_not_report(self, hotel, api_for, make_member):
        front = make_member("front_desk")
        ticket = MaintenanceTicketFactory(room=hotel.rooms["101"])
        api = api_for(front, hotel.prop)

        assert ids(api.get(URL)) == [str(ticket.pk)]
        response = api.post(URL, {"title": "Algo"})
        assert (response.status_code, response.json()["permission"]) == (403, "housekeeping.work")


class TestList:
    def test_open_work_comes_first_and_other_hotels_never_show(self, hotel, api_for, technician):
        resolved = MaintenanceTicketFactory(room=hotel.rooms["101"], status="resolved")
        normal = MaintenanceTicketFactory(room=hotel.rooms["102"])
        urgent = MaintenanceTicketFactory(room=hotel.rooms["201"], priority="urgent")
        started = MaintenanceTicketFactory(room=hotel.rooms["202"], status="in_progress", priority="low")
        MaintenanceTicketFactory(room=RoomFactory(room_type__property=PropertyFactory()))

        response = api_for(technician, hotel.prop).get(URL)

        assert ids(response) == [str(t.pk) for t in (started, urgent, normal, resolved)]

    def test_filters(self, hotel, api_for, technician, housekeeper):
        mine = MaintenanceTicketFactory(room=hotel.rooms["101"], assigned_to=technician)
        blocking = svc.create_ticket(hotel.prop, room=hotel.rooms["201"], title="Aire", blocks_room=True)
        reported = MaintenanceTicketFactory(
            room=None, property=hotel.prop, location="Lobby", reported_by=housekeeper
        )
        closed = MaintenanceTicketFactory(room=hotel.rooms["102"], status="cancelled")
        api = api_for(technician, hotel.prop)

        assert set(ids(api.get(URL, {"status": ["open", "in_progress"]}))) == {
            str(mine.pk),
            str(blocking.pk),
            str(reported.pk),
        }
        assert ids(api.get(URL, {"status": "cancelled"})) == [str(closed.pk)]
        assert ids(api.get(URL, {"blocking": 1})) == [str(blocking.pk)]
        assert ids(api.get(URL, {"assignee": "me"})) == [str(mine.pk)]
        assert set(ids(api.get(URL, {"assignee": "none"}))) == {
            str(blocking.pk),
            str(reported.pk),
            str(closed.pk),
        }
        assert ids(api.get(URL, {"room": str(hotel.rooms["201"].pk)})) == [str(blocking.pk)]
        assert ids(api.get(URL, {"q": "lobby"})) == [str(reported.pk)]
        assert ids(api_for(housekeeper, hotel.prop).get(URL, {"mine": 1})) == [str(reported.pk)]

    def test_the_number_of_queries_does_not_grow_with_the_tickets(self, hotel, api_for, technician):
        api = api_for(technician, hotel.prop)

        def count():
            with CaptureQueriesContext(connection) as queries:
                assert api.get(URL).status_code == 200
            return len(queries)

        first = svc.create_ticket(hotel.prop, room=hotel.rooms["101"], title="Uno", actor=technician)
        svc.add_photo(first, file=photo())
        few = count()
        for number in ("102", "201", "202"):
            ticket = svc.create_ticket(
                hotel.prop, room=hotel.rooms[number], title=number, assigned_to=technician
            )
            svc.add_photo(ticket, file=photo())
        assert count() == few


class TestWork:
    def test_the_technician_takes_the_ticket_and_resolves_it(
        self, hotel, api_for, technician, django_capture_on_commit_callbacks
    ):
        room = hotel.rooms["201"]
        ticket = svc.create_ticket(
            hotel.prop, room=room, title="Aire", blocks_room=True, blocked_until=day(3)
        )
        api = api_for(technician, hotel.prop)

        started = api.post(f"{URL}{ticket.pk}/start/")
        assert (started.status_code, started.json()["status"]) == (200, "in_progress")
        assert started.json()["assigned_to"]["id"] == str(technician.pk)

        with django_capture_on_commit_callbacks(execute=True):
            resolved = api.post(f"{URL}{ticket.pk}/resolve/", {"notes": "Cambié el capacitor"})

        assert resolved.status_code == 200
        body = resolved.json()
        assert (body["status"], body["resolution_notes"], body["resolved_by"]["id"]) == (
            "resolved",
            "Cambié el capacitor",
            str(technician.pk),
        )
        assert body["block"]["released_at"] is not None
        assert status_of(room) == "dirty"
        assert HousekeepingTask.objects.filter(room=room, kind="departure_clean", status="pending").exists()

    def test_edits_blocks_and_assigns(self, hotel, api_for, supervisor, technician, housekeeper):
        ticket = svc.create_ticket(hotel.prop, room=hotel.rooms["102"], title="Humedad")
        api = api_for(supervisor, hotel.prop)

        response = api.patch(
            f"{URL}{ticket.pk}/",
            {"blocks_room": True, "blocked_until": day(4).isoformat(), "assigned_to_id": str(technician.pk)},
        )
        assert response.status_code == 200
        assert (response.json()["blocks_room"], response.json()["blocked_until"]) == (True, "2026-10-05")
        assert response.json()["assigned_to"]["id"] == str(technician.pk)
        assert status_of(hotel.rooms["102"]) == "out_of_service"

        wrong = api.patch(f"{URL}{ticket.pk}/", {"assigned_to_id": str(housekeeper.pk)})
        assert (wrong.status_code, wrong.json()["code"]) == (400, "invalid_assignee")

    def test_cancel_restores_the_room_and_closed_tickets_do_not_change(self, hotel, api_for, technician):
        ticket = svc.create_ticket(hotel.prop, room=hotel.rooms["202"], title="Fuga", blocks_room=True)
        api = api_for(technician, hotel.prop)

        cancelled = api.post(f"{URL}{ticket.pk}/cancel/", {"reason": "Reportado por error"})
        assert (cancelled.status_code, cancelled.json()["status"]) == (200, "cancelled")
        assert status_of(hotel.rooms["202"]) == "clean"

        again = api.post(f"{URL}{ticket.pk}/resolve/")
        assert (again.status_code, again.json()["code"]) == (409, "ticket_closed")

    def test_only_supervisors_delete(self, hotel, api_for, technician, supervisor):
        ticket = MaintenanceTicketFactory(room=hotel.rooms["101"])
        response = api_for(technician, hotel.prop).delete(f"{URL}{ticket.pk}/")
        assert (response.status_code, response.json()["permission"]) == (403, "housekeeping.supervise")
        assert api_for(supervisor, hotel.prop).delete(f"{URL}{ticket.pk}/").status_code == 204
        assert not MaintenanceTicket.objects.exists()

    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            ("patch", "{id}/", {"title": "Otro"}),
            ("post", "{id}/start/", {}),
            ("post", "{id}/resolve/", {}),
            ("post", "{id}/cancel/", {}),
        ],
    )
    def test_housekeepers_report_but_do_not_work_tickets(
        self, hotel, api_for, housekeeper, method, path, body
    ):
        ticket = MaintenanceTicketFactory(room=hotel.rooms["101"], reported_by=housekeeper)
        response = getattr(api_for(housekeeper, hotel.prop), method)(URL + path.format(id=ticket.pk), body)
        assert (response.status_code, response.json()["permission"]) == (403, "housekeeping.maintenance")


class TestPhotos:
    def test_the_reporter_adds_and_removes_photos(self, hotel, api_for, housekeeper):
        ticket = svc.create_ticket(hotel.prop, room=hotel.rooms["101"], title="Espejo", actor=housekeeper)
        api = api_for(housekeeper, hotel.prop)

        added = api.post(f"{URL}{ticket.pk}/photos/", {"image": photo()}, format="multipart")
        assert added.status_code == 201
        assert added.json()["content_type"] == "image/jpeg"

        removed = api.delete(f"{URL}{ticket.pk}/photos/{added.json()['id']}/")
        assert removed.status_code == 204
        assert not TicketPhoto.objects.exists()

    def test_other_housekeepers_cannot_touch_the_photos(self, hotel, api_for, housekeeper, make_member):
        ticket = svc.create_ticket(hotel.prop, room=hotel.rooms["101"], title="Espejo", actor=housekeeper)
        existing = svc.add_photo(ticket, file=photo(), actor=housekeeper)
        colleague = api_for(make_member("housekeeping"), hotel.prop)

        response = colleague.post(f"{URL}{ticket.pk}/photos/", {"image": photo()}, format="multipart")
        assert (response.status_code, response.json()["permission"]) == (403, "housekeeping.maintenance")
        response = colleague.delete(f"{URL}{ticket.pk}/photos/{existing.pk}/")
        assert response.status_code == 403

    def test_the_file_is_served_privately_to_the_hotel_staff(self, hotel, api_for, make_member, housekeeper):
        ticket = svc.create_ticket(hotel.prop, room=hotel.rooms["101"], title="Espejo", actor=housekeeper)
        image = svc.add_photo(ticket, file=photo(), actor=housekeeper)
        url = f"/api/v1/housekeeping/ticket-photos/{image.pk}/file/"

        response = api_for(make_member("front_desk"), hotel.prop).get(url)

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == JPEG
        assert (response["Content-Type"], response["X-Content-Type-Options"]) == ("image/jpeg", "nosniff")
        assert response["Cache-Control"] == "private, no-store"

        other_hotel = PropertyFactory(organization=hotel.prop.organization)
        assert api_for(make_member("owner"), other_hotel).get(url).status_code == 404


def test_the_business_date_is_the_start_of_every_block(hotel, api_for, technician):
    response = api_for(technician, hotel.prop).post(
        URL, {"room_id": str(hotel.rooms["301"].pk), "title": "Pintura", "blocks_room": True}
    )
    block = RoomBlock.objects.get(pk=response.json()["block"]["id"])
    assert (block.start_date, block.kind) == (BUSINESS_DATE, "out_of_order")
