"""Database guarantees of the housekeeping models."""

import pytest
from django.db import IntegrityError, transaction

from apps.housekeeping.tests.factories import HousekeepingTaskFactory
from apps.inventory.tests.factories import RoomFactory

pytestmark = pytest.mark.django_db


def test_a_room_has_at_most_one_open_turnover_task(prop):
    """Check-out and "room became dirty" receivers may race for the same room: the database keeps one open
    departure/stayover clean per room."""
    room = RoomFactory(room_type__property=prop)
    HousekeepingTaskFactory(room=room, kind="departure_clean")

    with pytest.raises(IntegrityError), transaction.atomic():
        HousekeepingTaskFactory(room=room, kind="stayover", status="in_progress")


def test_finished_tasks_and_other_kinds_do_not_block_a_new_turnover(prop):
    room = RoomFactory(room_type__property=prop)
    HousekeepingTaskFactory(room=room, kind="departure_clean", status="done")
    HousekeepingTaskFactory(room=room, kind="stayover", status="cancelled")
    HousekeepingTaskFactory(room=room, kind="deep_clean")
    HousekeepingTaskFactory(room=room, kind="inspection")

    HousekeepingTaskFactory(room=room, kind="departure_clean")  # no IntegrityError
