"""`housekeeping.generate_daily_tasks`: stayovers by frequency, expected departures and dirty rooms."""

import pytest

from apps.housekeeping.models import HousekeepingSettings, HousekeepingTask
from apps.housekeeping.services.generation import generate_daily_tasks
from apps.housekeeping.tests.conftest import BUSINESS_DATE, day, make_stay
from apps.housekeeping.tests.factories import HousekeepingTaskFactory
from apps.inventory.models import Room

pytestmark = pytest.mark.django_db


def frequency(hotel, days):
    HousekeepingSettings.objects.update_or_create(
        property=hotel.prop, defaults={"stayover_frequency_days": days}
    )


def tasks_by_room() -> dict[str, str]:
    return {t.room.number: t.kind for t in HousekeepingTask.objects.select_related("room")}


@pytest.fixture
def occupancy(hotel):
    """101: 1st night done (arrived yesterday) · 102: arrived 2 days ago · 201: leaves today, someone arrives
    today · 202: arrives today (clean, vacant) · 301: dirty and vacant · D1: two beds in house."""
    make_stay(hotel, hotel.rooms["101"], checkin=day(-1), checkout=day(2))
    make_stay(hotel, hotel.rooms["102"], checkin=day(-2), checkout=day(1))
    make_stay(hotel, hotel.rooms["201"], checkin=day(-3), checkout=BUSINESS_DATE)
    make_stay(hotel, hotel.rooms["201"], checkin=BUSINESS_DATE, checkout=day(2), status="confirmed")
    make_stay(hotel, hotel.rooms["202"], checkin=BUSINESS_DATE, checkout=day(3), status="confirmed")
    Room.objects.filter(pk=hotel.rooms["301"].pk).update(housekeeping_status="dirty")
    make_stay(hotel, hotel.rooms["D1"], bed=hotel.beds["A"], checkin=day(-1), checkout=day(3))
    make_stay(hotel, hotel.rooms["D1"], bed=hotel.beds["B"], checkin=day(-2), checkout=day(1))
    return hotel


def test_daily_stayovers_expected_departures_and_dirty_rooms(occupancy):
    report = generate_daily_tasks(occupancy.prop)

    assert tasks_by_room() == {
        "101": "stayover",
        "102": "stayover",
        "201": "departure_clean",
        "301": "departure_clean",
        "D1": "stayover",
    }
    assert report == {
        "created": 5,
        "stayovers": 3,
        "departures": 1,
        "dirty_rooms": 1,
        "rooms_marked_dirty": 3,
    }
    departure = HousekeepingTask.objects.get(room=occupancy.rooms["201"])
    assert (departure.priority, departure.business_date, departure.created_source) == (
        "high",
        BUSINESS_DATE,
        "daily",
    )
    assert HousekeepingTask.objects.get(room=occupancy.rooms["102"]).estimated_minutes == 15


def test_rooms_with_a_stayover_turn_dirty_until_serviced(occupancy, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        generate_daily_tasks(occupancy.prop)

    statuses = dict(Room.objects.filter(property=occupancy.prop).values_list("number", "housekeeping_status"))
    assert (statuses["101"], statuses["102"], statuses["D1"]) == ("dirty", "dirty", "dirty")
    assert (statuses["201"], statuses["202"]) == ("clean", "clean")  # the departure waits for the check-out
    assert HousekeepingTask.objects.count() == 5  # the "room turned dirty" receiver added nothing


def test_every_other_day_skips_the_first_night(occupancy):
    frequency(occupancy, 2)

    generate_daily_tasks(occupancy.prop)

    rooms = tasks_by_room()
    assert "101" not in rooms  # one night since arrival
    assert rooms["102"] == "stayover" and rooms["D1"] == "stayover"  # bed B arrived two nights ago


def test_frequency_zero_means_no_stayover_service(occupancy):
    frequency(occupancy, 0)

    generate_daily_tasks(occupancy.prop)

    assert tasks_by_room() == {"201": "departure_clean", "301": "departure_clean"}


def test_running_again_does_not_duplicate_nor_redo_what_was_handled(occupancy):
    generate_daily_tasks(occupancy.prop)
    HousekeepingTask.objects.filter(room=occupancy.rooms["101"]).update(status="done")
    HousekeepingTask.objects.filter(room=occupancy.rooms["102"]).update(status="cancelled")

    report = generate_daily_tasks(occupancy.prop)

    assert report["created"] == 0
    assert HousekeepingTask.objects.count() == 5


def test_a_clean_still_open_from_yesterday_is_not_duplicated(occupancy):
    carried = HousekeepingTaskFactory(room=occupancy.rooms["301"], business_date=day(-1))

    generate_daily_tasks(occupancy.prop)

    assert list(HousekeepingTask.objects.filter(room=occupancy.rooms["301"])) == [carried]


def test_inactive_and_out_of_service_rooms_are_left_alone(hotel):
    Room.objects.filter(pk=hotel.rooms["101"].pk).update(housekeeping_status="dirty", is_active=False)
    Room.objects.filter(pk=hotel.rooms["102"].pk).update(housekeeping_status="out_of_service")
    make_stay(hotel, hotel.rooms["102"], checkin=day(-1), checkout=day(2))

    report = generate_daily_tasks(hotel.prop)

    assert report["created"] == 0
    assert Room.objects.get(pk=hotel.rooms["102"].pk).housekeeping_status == "out_of_service"
