"""Maintenance tickets: a ticket that makes the room unusable blocks it (RoomBlock + out of service) until it
is resolved (block released, room back to cleaning) or cancelled (previous status restored)."""

from datetime import timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.housekeeping.models import HousekeepingTask, MaintenanceTicket, TicketPhoto
from apps.housekeeping.services import tickets as svc
from apps.housekeeping.tests.conftest import BUSINESS_DATE, JPEG, PNG, day, make_stay
from apps.inventory.models import Room, RoomBlock

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("private_media")]

WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 64
HEIC = b"\x00\x00\x00\x18ftypheic" + b"0" * 64


@pytest.fixture
def reporter(make_member):
    return make_member("housekeeping")


@pytest.fixture
def technician(make_member):
    return make_member("maintenance", full_name="Jorge Técnico")


def status_of(room) -> str:
    return Room.objects.get(pk=room.pk).housekeeping_status


class TestCreate:
    def test_reports_a_problem_without_touching_the_room(self, hotel, reporter):
        room = hotel.rooms["102"]

        ticket = svc.create_ticket(
            hotel.prop, room=room, title="Grifo gotea", description="Lavamanos", actor=reporter
        )

        assert (ticket.status, ticket.priority, ticket.reported_by, ticket.block) == (
            "open",
            "normal",
            reporter,
            None,
        )
        assert status_of(room) == "clean"
        assert not RoomBlock.objects.exists()
        assert AuditEvent.objects.filter(action="housekeeping.ticket_created", actor=reporter).exists()

    def test_a_blocking_ticket_takes_the_room_out_of_service_until_the_date_given(self, hotel, technician):
        room = hotel.rooms["201"]

        ticket = svc.create_ticket(
            hotel.prop,
            room=room,
            title="Aire no enfría",
            blocks_room=True,
            blocked_until=day(3),
            actor=technician,
        )

        block = RoomBlock.objects.get()
        assert (block.room, block.start_date, block.end_date, block.kind) == (
            room,
            BUSINESS_DATE,
            day(3),
            "out_of_order",
        )
        assert "Aire no enfría" in block.reason
        assert (ticket.block, ticket.blocked_until, ticket.room_status_before) == (block, day(3), "clean")
        assert status_of(room) == "out_of_service"

    def test_the_block_lasts_one_night_when_no_date_is_given(self, hotel, technician):
        ticket = svc.create_ticket(
            hotel.prop, room=hotel.rooms["201"], title="Fuga", blocks_room=True, actor=technician
        )
        assert (ticket.block.start_date, ticket.block.end_date) == (BUSINESS_DATE, day(1))

    def test_a_room_with_bookings_in_those_dates_needs_force(self, hotel, technician):
        room = hotel.rooms["202"]
        stay = make_stay(hotel, room, checkin=day(1), checkout=day(4), status="confirmed")

        with pytest.raises(DomainError) as error:
            svc.create_ticket(hotel.prop, room=room, title="Fuga", blocks_room=True, blocked_until=day(2))
        assert (error.value.status_code, error.value.code) == (409, "room_has_reservations")
        assert error.value.extra["reservations"] == [stay.reservation.code]
        assert not MaintenanceTicket.objects.exists()

        svc.create_ticket(
            hotel.prop,
            room=room,
            title="Fuga",
            blocks_room=True,
            blocked_until=day(2),
            force=True,
            actor=technician,
        )
        assert RoomBlock.objects.filter(room=room, released_at=None).exists()

    @pytest.mark.parametrize(
        ("values", "code"),
        [
            ({"room": None, "location": "Piscina", "blocks_room": True}, "room_required"),
            ({"blocks_room": True, "blocked_until": BUSINESS_DATE}, "invalid_dates"),
            ({"priority": "whenever"}, "invalid_priority"),
            ({"title": "  "}, "title_required"),
        ],
    )
    def test_invalid_reports_are_refused(self, hotel, technician, values, code):
        data = {"room": hotel.rooms["101"], "title": "Algo", **values}
        with pytest.raises(DomainError) as error:
            svc.create_ticket(hotel.prop, actor=technician, **data)
        assert (error.value.status_code, error.value.code) == (400, code)

    def test_common_areas_have_a_location_instead_of_a_room(self, hotel, reporter):
        ticket = svc.create_ticket(
            hotel.prop, room=None, location="Pasillo piso 2", title="Bombillo", actor=reporter
        )
        assert (ticket.room, ticket.location) == (None, "Pasillo piso 2")

    def test_only_maintenance_people_of_the_hotel_can_be_assigned(self, hotel, technician, reporter):
        ticket = svc.create_ticket(hotel.prop, room=hotel.rooms["101"], title="Ducha", assigned_to=technician)
        assert ticket.assigned_to == technician

        with pytest.raises(DomainError) as error:
            svc.update_ticket(ticket, {"assigned_to": reporter}, actor=technician)
        assert error.value.code == "invalid_assignee"


class TestLifeCycle:
    @pytest.fixture
    def blocking(self, hotel, technician):
        return svc.create_ticket(
            hotel.prop,
            room=hotel.rooms["201"],
            title="Aire",
            blocks_room=True,
            blocked_until=day(3),
            actor=technician,
        )

    def test_starting_takes_the_ticket(self, hotel, technician):
        ticket = svc.create_ticket(hotel.prop, room=hotel.rooms["101"], title="Ducha")

        svc.start_ticket(ticket, actor=technician)

        ticket.refresh_from_db()
        assert (ticket.status, ticket.assigned_to) == ("in_progress", technician)
        assert ticket.started_at is not None

    def test_resolving_releases_the_room_and_sends_it_to_cleaning(
        self, hotel, blocking, technician, django_capture_on_commit_callbacks
    ):
        with django_capture_on_commit_callbacks(execute=True):
            svc.resolve_ticket(blocking, actor=technician, notes="Cambié el compresor")

        blocking.refresh_from_db()
        assert (blocking.status, blocking.resolved_by, blocking.resolution_notes) == (
            "resolved",
            technician,
            "Cambié el compresor",
        )
        assert blocking.resolved_at is not None
        assert RoomBlock.objects.get().released_at is not None
        assert status_of(hotel.rooms["201"]) == "dirty"
        task = HousekeepingTask.objects.get()  # created by the "room turned dirty" receiver
        assert (task.room, task.kind) == (hotel.rooms["201"], "departure_clean")

    def test_cancelling_releases_the_room_and_restores_its_status(self, hotel, blocking, technician):
        svc.cancel_ticket(blocking, actor=technician, reason="Reportado por error")

        blocking.refresh_from_db()
        assert blocking.status == "cancelled"
        assert RoomBlock.objects.get().released_at is not None
        assert status_of(hotel.rooms["201"]) == "clean"

    def test_moving_the_end_date_replaces_the_block(self, hotel, blocking, technician):
        svc.update_ticket(blocking, {"blocked_until": day(5)}, actor=technician)

        blocking.refresh_from_db()
        active = RoomBlock.objects.get(released_at=None)
        assert (active.start_date, active.end_date, blocking.block, blocking.blocked_until) == (
            BUSINESS_DATE,
            day(5),
            active,
            day(5),
        )
        assert RoomBlock.objects.exclude(released_at=None).count() == 1
        assert status_of(hotel.rooms["201"]) == "out_of_service"

    def test_the_room_can_be_blocked_later_and_unblocked_before_resolving(self, hotel, technician):
        ticket = svc.create_ticket(hotel.prop, room=hotel.rooms["102"], title="Humedad")

        svc.update_ticket(ticket, {"blocks_room": True, "blocked_until": day(2)}, actor=technician)
        assert status_of(hotel.rooms["102"]) == "out_of_service"

        svc.update_ticket(ticket, {"blocks_room": False}, actor=technician)
        ticket.refresh_from_db()
        assert (ticket.blocks_room, ticket.status) == (False, "open")
        assert RoomBlock.objects.get().released_at is not None
        assert status_of(hotel.rooms["102"]) == "dirty"

    def test_closed_tickets_cannot_change(self, hotel, blocking, technician):
        svc.resolve_ticket(blocking, actor=technician)
        for action in (
            lambda: svc.start_ticket(blocking, actor=technician),
            lambda: svc.resolve_ticket(blocking, actor=technician),
            lambda: svc.cancel_ticket(blocking, actor=technician),
            lambda: svc.update_ticket(blocking, {"title": "Otro"}, actor=technician),
        ):
            with pytest.raises(DomainError) as error:
                action()
            assert (error.value.status_code, error.value.code) == (409, "ticket_closed")

    def test_deleting_a_ticket_releases_its_block(self, hotel, blocking, technician):
        svc.delete_ticket(blocking, actor=technician)
        assert not MaintenanceTicket.objects.exists()
        assert RoomBlock.objects.get().released_at is not None
        assert status_of(hotel.rooms["201"]) == "clean"


class TestPhotos:
    @pytest.fixture
    def ticket(self, hotel):
        return svc.create_ticket(hotel.prop, room=hotel.rooms["101"], title="Espejo roto")

    @pytest.mark.parametrize(
        ("content", "suffix", "content_type"),
        [
            (JPEG, ".jpg", "image/jpeg"),
            (PNG, ".png", "image/png"),
            (WEBP, ".webp", "image/webp"),
            (HEIC, ".heic", "image/heic"),
        ],
    )
    def test_photos_are_private_with_random_names(
        self, ticket, reporter, private_media, settings, content, suffix, content_type
    ):
        photo = svc.add_photo(
            ticket, file=SimpleUploadedFile("habitación 101 Juan.bin", content), actor=reporter
        )

        path = Path(photo.image.path)
        assert path.is_relative_to(private_media) and not path.is_relative_to(settings.MEDIA_ROOT)
        assert path.suffix == suffix and "Juan" not in photo.image.name
        assert path.read_bytes() == content
        assert (photo.content_type, photo.size, photo.uploaded_by) == (content_type, len(content), reporter)
        with pytest.raises(ValueError):
            photo.image.url  # noqa: B018 — no public URL
        assert (private_media / ".gitignore").read_text().strip() == "*"

    @pytest.mark.parametrize("content", [b"<svg onload=alert(1)>", b"%PDF-1.7\n", b"GIF89a....", b""])
    def test_anything_but_a_photo_is_refused(self, ticket, content):
        with pytest.raises(DomainError) as error:
            svc.add_photo(ticket, file=SimpleUploadedFile("x.jpg", content))
        assert error.value.code == "invalid_file_type"

    def test_photos_over_10_mb_are_refused(self, ticket):
        big = SimpleUploadedFile("big.jpg", JPEG + b"0" * (10 * 1024 * 1024))
        with pytest.raises(DomainError) as error:
            svc.add_photo(ticket, file=big)
        assert error.value.code == "file_too_large"

    def test_a_ticket_keeps_at_most_six_photos(self, ticket):
        for _ in range(6):
            svc.add_photo(ticket, file=SimpleUploadedFile("p.jpg", JPEG))
        with pytest.raises(DomainError) as error:
            svc.add_photo(ticket, file=SimpleUploadedFile("p.jpg", JPEG))
        assert error.value.code == "too_many_photos"

    def test_deleting_a_photo_removes_the_file(self, ticket, django_capture_on_commit_callbacks):
        photo = svc.add_photo(ticket, file=SimpleUploadedFile("p.jpg", JPEG))
        path = Path(photo.image.path)

        with django_capture_on_commit_callbacks(execute=True):
            svc.delete_photo(photo)

        assert not TicketPhoto.objects.exists() and not path.exists()


def test_the_room_can_be_blocked_over_a_stay_that_already_left(hotel, technician):
    make_stay(hotel, hotel.rooms["301"], checkin=day(-3), checkout=BUSINESS_DATE, status="checked_out")
    ticket = svc.create_ticket(
        hotel.prop,
        room=hotel.rooms["301"],
        title="Pintura",
        blocks_room=True,
        blocked_until=BUSINESS_DATE + timedelta(days=2),
    )
    assert ticket.block is not None
