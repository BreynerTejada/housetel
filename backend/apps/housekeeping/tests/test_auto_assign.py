"""`housekeeping.auto_assign`: balance the day's minutes between the housekeepers and keep each one on as few
floors as possible."""

import pytest

from apps.accounts.models import Membership
from apps.core.tests.factories import PropertyFactory
from apps.housekeeping.models import HousekeepingSettings, HousekeepingTask
from apps.housekeeping.services.assignment import auto_assign, eligible_staff
from apps.housekeeping.tests.conftest import day
from apps.housekeeping.tests.factories import HousekeepingTaskFactory
from apps.inventory.tests.factories import RoomFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def floors(hotel):
    """Four rooms per floor on floors 1 and 2."""
    rooms = dict(hotel.rooms)
    for number in ("103", "104", "203", "204"):
        rooms[number] = RoomFactory(room_type=hotel.dbl, number=number, floor=number[0])
    return rooms


@pytest.fixture
def ana(make_member):
    return make_member("housekeeping", full_name="Ana Ruiz")


@pytest.fixture
def beto(make_member):
    return make_member("housekeeping", full_name="Beto Mora")


def pending(rooms, numbers, minutes=30, **kwargs):
    return [HousekeepingTaskFactory(room=rooms[n], estimated_minutes=minutes, **kwargs) for n in numbers]


def load(user) -> int:
    return sum(HousekeepingTask.objects.filter(assigned_to=user).values_list("estimated_minutes", flat=True))


def floors_of(user) -> set[str]:
    return set(HousekeepingTask.objects.filter(assigned_to=user).values_list("room__floor", flat=True))


def test_each_housekeeper_gets_the_same_minutes_on_one_floor(hotel, floors, ana, beto):
    pending(floors, ["101", "102", "103", "104", "201", "202", "203", "204"])

    report = auto_assign(hotel.prop)

    assert (load(ana), load(beto)) == (120, 120)
    assert (floors_of(ana), floors_of(beto)) == ({"1"}, {"2"})
    assert (report["assigned"], report["unassigned"]) == (8, 0)
    assert [(row["full_name"], row["minutes"], row["tasks"]) for row in report["staff"]] == [
        ("Ana Ruiz", 120, 4),
        ("Beto Mora", 120, 4),
    ]


def test_a_crowded_floor_is_split_but_the_minutes_stay_balanced(hotel, floors, ana, beto):
    pending(floors, ["101", "102", "103", "104"])
    pending(floors, ["101", "102"], kind="deep_clean", minutes=30)
    pending(floors, ["201", "202"])

    auto_assign(hotel.prop)

    assert (load(ana), load(beto)) == (120, 120)
    assert floors_of(ana) == {"1"}  # the first housekeeper never leaves her floor
    assert floors_of(beto) == {"1", "2"}


def test_work_already_assigned_counts_in_the_balance(hotel, floors, ana, beto):
    pending(floors, ["201", "202", "203"], assigned_to=ana, status="in_progress")  # 90 min
    pending(floors, ["101", "102", "103", "104"])  # 120 min to share

    auto_assign(hotel.prop)

    assert (load(ana), load(beto)) == (90, 120)


def test_only_housekeepers_of_this_property_get_tasks(hotel, floors, ana, make_member, organization, owner):
    make_member("housekeeping_supervisor")
    make_member("front_desk")
    make_member("housekeeping", properties=[PropertyFactory(organization=organization)])
    inactive = make_member("housekeeping", full_name="Carla Inactiva")
    Membership.objects.filter(user=inactive).update(is_active=False)

    assert eligible_staff(hotel.prop) == [ana]

    pending(floors, ["101", "201"])
    auto_assign(hotel.prop)
    assert set(HousekeepingTask.objects.values_list("assigned_to", flat=True)) == {ana.pk}


def test_inspections_started_and_closed_tasks_are_not_touched(hotel, floors, ana, beto):
    inspection = HousekeepingTaskFactory(room=floors["101"], kind="inspection")
    started = HousekeepingTaskFactory(room=floors["102"], status="in_progress")
    done = HousekeepingTaskFactory(room=floors["103"], status="done")
    [overdue] = pending(floors, ["201"], business_date=day(-1))  # still open from yesterday

    report = auto_assign(hotel.prop)

    assert report["assigned"] == 1
    for task in (inspection, started, done):
        task.refresh_from_db()
        assert task.assigned_to is None
    overdue.refresh_from_db()
    assert overdue.assigned_to is not None


def test_the_staff_can_be_chosen_for_the_day(hotel, floors, ana, beto):
    pending(floors, ["101", "102", "201"])

    auto_assign(hotel.prop, staff=[beto])

    assert (load(ana), load(beto)) == (0, 90)


def test_without_housekeepers_nothing_is_assigned(hotel, floors):
    pending(floors, ["101", "102"])

    report = auto_assign(hotel.prop)

    assert (report["assigned"], report["unassigned"]) == (0, 2)
    assert not HousekeepingTask.objects.exclude(assigned_to=None).exists()


def test_reports_who_goes_over_the_shift(hotel, floors, ana):
    HousekeepingSettings.objects.create(property=hotel.prop, minutes_per_shift=60)
    pending(floors, ["101", "102", "103"])

    report = auto_assign(hotel.prop)

    assert report["overloaded"] == [str(ana.pk)]
