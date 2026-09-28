"""Automations registered by housekeeping (spec §6): generate at 07:00, auto-assign at 07:15."""

import pytest

from apps.core import automation
from apps.housekeeping.models import HousekeepingSettings, HousekeepingTask
from apps.housekeeping.tests.conftest import BUSINESS_DATE, day, make_stay
from apps.inventory.models import Room

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("code", "hour", "minute"),
    [("housekeeping.generate_daily_tasks", 7, 0), ("housekeeping.auto_assign", 7, 15)],
)
def test_registered_with_the_planned_schedule(code, hour, minute):
    item = automation.get(code)
    assert (item.app, item.scope, item.default_enabled) == ("housekeeping", "property", True)
    assert (item.schedule.hour, item.schedule.minute) == ({hour}, {minute})
    assert item.name_es and item.name_en and item.description_es


def test_generation_run_creates_the_day_and_records_it(hotel):
    make_stay(hotel, hotel.rooms["101"], checkin=day(-2), checkout=BUSINESS_DATE)
    Room.objects.filter(pk=hotel.rooms["301"].pk).update(housekeeping_status="dirty")

    run = automation.run("housekeeping.generate_daily_tasks", hotel.prop)

    assert run.status == "success"
    assert (run.details["created"], run.details["departures"], run.details["dirty_rooms"]) == (2, 1, 1)
    assert HousekeepingTask.objects.count() == 2


def test_auto_assign_run_shares_the_tasks(hotel, make_member):
    housekeeper = make_member("housekeeping")
    Room.objects.filter(pk=hotel.rooms["301"].pk).update(housekeeping_status="dirty")
    automation.run("housekeeping.generate_daily_tasks", hotel.prop)

    run = automation.run("housekeeping.auto_assign", hotel.prop)

    assert (run.status, run.details["assigned"]) == ("success", 1)
    assert HousekeepingTask.objects.get().assigned_to == housekeeper


def test_auto_assign_is_skipped_when_the_hotel_turned_it_off(hotel, make_member):
    make_member("housekeeping")
    HousekeepingSettings.objects.create(property=hotel.prop, auto_assign=False)
    Room.objects.filter(pk=hotel.rooms["301"].pk).update(housekeeping_status="dirty")
    automation.run("housekeeping.generate_daily_tasks", hotel.prop)

    run = automation.run("housekeeping.auto_assign", hotel.prop)

    assert run.status == "skipped"
    assert HousekeepingTask.objects.get().assigned_to is None


def test_auto_assign_without_staff_is_partial(hotel):
    Room.objects.filter(pk=hotel.rooms["301"].pk).update(housekeeping_status="dirty")
    automation.run("housekeeping.generate_daily_tasks", hotel.prop)

    run = automation.run("housekeeping.auto_assign", hotel.prop)

    assert (run.status, run.details["unassigned"]) == ("partial", 1)
