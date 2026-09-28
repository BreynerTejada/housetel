"""Housekeeping demo seed (plan C2 · Seed): today's tasks in every stage, assigned to the housekeeper of the
hotel, and three maintenance tickets (one blocking a vacant room). Built with fixtures, not with seed_demo."""

import random
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay
from apps.core.seed import SeedContext
from apps.core.signals import seeding
from apps.housekeeping import seed as hk_seed
from apps.housekeeping.models import HousekeepingSettings, HousekeepingTask, MaintenanceTicket, TicketPhoto
from apps.housekeeping.tests.conftest import BUSINESS_DATE, day, make_stay
from apps.inventory.models import Room, RoomBlock
from apps.inventory.tests.factories import RoomFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("private_media")]
BOGOTA = ZoneInfo("America/Bogota")


@pytest.fixture
def housekeeper(make_member):
    return make_member("housekeeping", email="limpieza@hotel.test", full_name="Luz Marina Pérez")


@pytest.fixture
def world(hotel, housekeeper, owner):
    """101 and 102: guests in house (stayovers) · 201: guest leaving today and another arriving (departure
    that waits for the check-out) · 202: left yesterday, dirty · 301: vacant · 302 (last room): someone
    arrives tomorrow."""
    rooms = dict(hotel.rooms)
    rooms["302"] = RoomFactory(room_type=hotel.ste, number="302", floor="3", sort_order=7)
    make_stay(hotel, rooms["101"], checkin=day(-2), checkout=day(2))
    make_stay(hotel, rooms["102"], checkin=day(-1), checkout=day(1))
    make_stay(hotel, rooms["201"], checkin=day(-3), checkout=BUSINESS_DATE)
    make_stay(hotel, rooms["201"], checkin=BUSINESS_DATE, checkout=day(2), status="confirmed")
    make_stay(hotel, rooms["202"], checkin=day(-3), checkout=day(-1), status="checked_out")
    Room.objects.filter(pk=rooms["202"].pk).update(housekeeping_status="dirty")
    make_stay(hotel, rooms["302"], checkin=day(1), checkout=day(3), status="confirmed")
    ctx = SeedContext(
        today=BUSINESS_DATE,
        rng=random.Random(20260925),
        properties={"aurora": hotel.prop},
        users={"aurora_hk": housekeeper, "aurora_owner": owner},
    )
    return {"ctx": ctx, "rooms": rooms, "housekeeper": housekeeper, "owner": owner, "prop": hotel.prop}


@pytest.fixture
def run_seed(django_capture_on_commit_callbacks):
    """As in seed_demo: the transaction commits (on-commit receivers run) while `seeding()` is active, so the
    housekeeping receivers ignore what the seed itself does."""

    def _run(ctx) -> None:
        with seeding(), django_capture_on_commit_callbacks(execute=True):
            hk_seed.seed(ctx)

    return _run


def today_tasks(prop):
    return HousekeepingTask.objects.filter(property=prop, business_date=prop.business_date)


class TestTasks:
    def test_the_day_is_planned_and_given_to_the_housekeeper(self, world, run_seed):
        run_seed(world["ctx"])

        rooms = world["rooms"]
        tasks = {task.room.number: task for task in today_tasks(world["prop"]).select_related("room")}
        assert {number: task.kind for number, task in tasks.items()} == {
            "101": "stayover",
            "102": "stayover",
            "201": "departure_clean",
            "202": "departure_clean",
        }
        assert {task.assigned_to for task in tasks.values()} == {world["housekeeper"]}
        assert tasks["201"].priority == "high"  # someone arrives today in that room
        assert rooms["301"].number not in tasks and rooms["302"].number not in tasks

    def test_the_tasks_are_at_every_stage_of_the_day(self, world, run_seed):
        run_seed(world["ctx"])

        tasks = list(today_tasks(world["prop"]).select_related("room"))
        statuses = [task.status for task in tasks]
        assert statuses.count("in_progress") == 1
        assert "done" in statuses and "pending" in statuses
        leaving = next(task for task in tasks if task.room.number == "201")
        assert leaving.status == "pending"  # the guest has not checked out: nobody can clean it yet
        for task in tasks:
            status = Room.objects.get(pk=task.room_id).housekeeping_status
            if task.status == "done":
                assert status == "clean", task.room.number
                assert task.finished_by == world["housekeeper"]
            elif task.kind == "stayover":
                assert status == "dirty", task.room.number  # waits for its service

    def test_work_times_are_believable_even_right_after_midnight(self, world, run_seed):
        with freeze_time(datetime(2026, 10, 1, 0, 10, tzinfo=BOGOTA)):
            run_seed(world["ctx"])

        midnight = datetime(2026, 10, 1, tzinfo=BOGOTA)
        worked = today_tasks(world["prop"]).exclude(status="pending")
        assert worked.exists()
        for task in worked:
            assert midnight <= task.started_at
            if task.finished_at:
                assert task.started_at <= task.finished_at <= datetime(2026, 10, 1, 0, 10, tzinfo=BOGOTA)

    def test_a_hotel_that_requires_inspection_leaves_inspections_for_the_supervisor(self, world, run_seed):
        world["ctx"].properties = {"andino_mde": world["prop"]}
        world["ctx"].users = {"andino_hk": world["housekeeper"], "andino_owner": world["owner"]}

        run_seed(world["ctx"])

        assert HousekeepingSettings.objects.get(property=world["prop"]).require_inspection is True
        done_rooms = set(today_tasks(world["prop"]).filter(status="done").values_list("room_id", flat=True))
        inspections = today_tasks(world["prop"]).filter(kind="inspection", status="pending")
        assert done_rooms and set(inspections.values_list("room_id", flat=True)) == done_rooms


class TestTickets:
    def test_three_tickets_one_of_them_blocking_a_vacant_room(self, world, run_seed):
        run_seed(world["ctx"])

        tickets = list(MaintenanceTicket.objects.filter(property=world["prop"]))
        assert len(tickets) == 3
        [blocking] = [ticket for ticket in tickets if ticket.blocks_room]
        block = RoomBlock.objects.get(pk=blocking.block_id)
        assert (block.room_id, block.start_date, block.kind, block.released_at) == (
            blocking.room_id,
            BUSINESS_DATE,
            "out_of_order",
            None,
        )
        assert not Stay.objects.filter(
            room_id=blocking.room_id,
            status__in=ACTIVE_STAY_STATUSES,
            checkin_date__lt=block.end_date,
            checkout_date__gt=block.start_date,
        ).exists()
        assert Room.objects.get(pk=blocking.room_id).housekeeping_status == "out_of_service"
        assert not today_tasks(world["prop"]).filter(room_id=blocking.room_id).exists()
        assert {ticket.status for ticket in tickets} == {"open", "in_progress"}
        [common_area] = [ticket for ticket in tickets if ticket.room_id is None]
        assert common_area.location

    def test_the_damage_reported_by_the_housekeeper_has_a_private_photo(self, world, private_media, run_seed):
        run_seed(world["ctx"])

        [photo] = TicketPhoto.objects.filter(ticket__property=world["prop"])
        assert photo.ticket.reported_by == world["housekeeper"]
        assert photo.content_type == "image/jpeg"
        assert Path(photo.image.path).is_relative_to(private_media)
        assert Path(photo.image.path).read_bytes()[:3] == b"\xff\xd8\xff"


def test_running_it_again_duplicates_nothing(world, run_seed):
    run_seed(world["ctx"])
    statuses = dict(HousekeepingTask.objects.values_list("pk", "status"))
    counts = (
        HousekeepingTask.objects.count(),
        MaintenanceTicket.objects.count(),
        TicketPhoto.objects.count(),
        RoomBlock.objects.count(),
    )
    assert all(counts)

    run_seed(world["ctx"])

    assert (
        HousekeepingTask.objects.count(),
        MaintenanceTicket.objects.count(),
        TicketPhoto.objects.count(),
        RoomBlock.objects.count(),
    ) == counts
    assert (
        dict(HousekeepingTask.objects.values_list("pk", "status")) == statuses
    )  # the morning does not advance


def test_a_hotel_without_housekeepers_gets_its_tasks_unassigned(hotel, owner, run_seed):
    """Andino Hostel: its organization's housekeeper only works in Medellín."""
    Room.objects.filter(pk=hotel.rooms["202"].pk).update(housekeeping_status="dirty")
    ctx = SeedContext(
        today=BUSINESS_DATE,
        rng=random.Random(1),
        properties={"andino_bog": hotel.prop},
        users={"andino_owner": owner},
    )

    run_seed(ctx)

    task = HousekeepingTask.objects.get()
    assert (task.room, task.status, task.assigned_to) == (hotel.rooms["202"], "pending", None)
    assert MaintenanceTicket.objects.filter(property=hotel.prop).count() == 3


def test_a_hotel_without_rooms_is_skipped(prop, owner, run_seed):
    ctx = SeedContext(today=prop.business_date, rng=random.Random(1), properties={"aurora": prop}, users={})

    run_seed(ctx)

    assert not HousekeepingTask.objects.exists() and not MaintenanceTicket.objects.exists()


def test_the_seeded_block_keeps_the_inventory_consistent(world, run_seed):
    """The block goes through `inventory.block_room`, so bookings recomputes its availability."""
    from apps.bookings.services.inventory import rebuild_inventory

    window = (BUSINESS_DATE, BUSINESS_DATE + timedelta(days=3))
    rebuild_inventory(world["prop"], *window)  # the rows exist before the seed, as in the demo

    run_seed(world["ctx"])

    assert RoomBlock.objects.filter(released_at=None).exists()
    assert rebuild_inventory(world["prop"], *window).updated == 0
