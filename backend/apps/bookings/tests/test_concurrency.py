"""Real concurrency (plan B2b › tests obligatorios): two threads, each with its own database connection and
transaction, compete for the same unit at the same time.

- Booking the last unit of a category: the InventoryDay rows are locked with `select_for_update()`, so the
  second transaction waits for the first, then sees the unit sold and gets AvailabilityError (409). The quote
  is slowed down while the first transaction holds the lock, so both transactions are guaranteed to overlap.
- Assigning the same room to two stays: both pass the application check before either writes (it is slowed
  down), so the database exclusion constraint decides — the second write waits for the first and fails, and
  the service turns that into the same 409.
"""

import threading
import time
from decimal import Decimal

import pytest
from django.db import connection

from apps.bookings.models import InventoryDay, Reservation, Stay
from apps.bookings.services import pricing, reservations
from apps.bookings.services.inventory import rebuild_inventory
from apps.bookings.services.reservations import assign_room, create_reservation
from apps.bookings.tests.helpers import guest_input, oct_, reservation_request, stay_request
from apps.bookings.types import AvailabilityError
from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory
from apps.rates.tests.factories import RatePlanFactory, RoomTypeRateDefaultsFactory

pytestmark = pytest.mark.django_db(transaction=True)


def run_together(jobs) -> list:
    """Start the callables at the same moment, each in its own thread (so its own connection and transaction);
    returns their outcomes: ("ok", result) | ("conflict", error code) | ("error", repr)."""
    barrier = threading.Barrier(len(jobs))
    outcomes = []

    def worker(job):
        try:
            barrier.wait(timeout=10)
            outcomes.append(("ok", job()))
        except AvailabilityError as exc:
            outcomes.append(("conflict", exc.code))
        except Exception as exc:  # noqa: BLE001 - reported by the assertions of the test
            outcomes.append(("error", repr(exc)))
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(job,)) for job in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return outcomes


def slowed(monkeypatch, module, name, seconds=0.4):
    """Make `module.name` take a while (after doing its real work)."""
    real = getattr(module, name)

    def slow(*args, **kwargs):
        result = real(*args, **kwargs)
        time.sleep(seconds)
        return result

    monkeypatch.setattr(module, name, slow)


def category(prop, code, rooms):
    """A private category with `rooms` rooms, priced by a base plan (business date 2026-10-01)."""
    prop.business_date = oct_(1)
    prop.save()
    room_type = RoomTypeFactory(property=prop, code=code, max_adults=2, max_occupancy=2)
    for number in range(1, rooms + 1):
        RoomFactory(room_type=room_type, number=f"{code}{number}")
    plan = RatePlanFactory(property=prop, code="BAR", room_types=[room_type])
    RoomTypeRateDefaultsFactory(room_type=room_type, rate_plan=plan, price=Decimal("900000"))
    return type("Hotel", (), {"prop": prop, "dbl": room_type, "plan": plan})


def booking_request(hotel):
    return reservation_request(hotel, [stay_request(hotel, oct_(1), oct_(3))], booker=guest_input())


@pytest.mark.parametrize("materialized", [True, False], ids=["rows-exist", "rows-missing"])
def test_two_simultaneous_bookings_of_the_last_unit_one_gets_409(prop, monkeypatch, materialized):
    hotel = category(prop, "PH", rooms=1)
    if materialized:
        rebuild_inventory(prop, oct_(1), oct_(3))
    requests = [booking_request(hotel) for _ in range(2)]
    slowed(monkeypatch, pricing, "quote")  # runs after the inventory rows are locked

    outcomes = run_together([lambda req=req: create_reservation(req).code for req in requests])

    assert sorted(kind for kind, _ in outcomes) == ["conflict", "ok"], outcomes
    assert [code for kind, code in outcomes if kind == "conflict"] == ["no_availability"]
    assert Reservation.objects.filter(property=prop).count() == 1
    assert list(
        InventoryDay.objects.filter(room_type=hotel.dbl, date__in=[oct_(1), oct_(2)]).values_list(
            "sold_units", flat=True
        )
    ) == [1, 1]


def test_two_simultaneous_assignments_of_the_same_room_one_gets_409(prop, monkeypatch):
    hotel = category(prop, "DBL", rooms=2)
    wanted = hotel.dbl.rooms.get(number="DBL1")
    stays = [create_reservation(booking_request(hotel)).stays.get() for _ in range(2)]
    slowed(monkeypatch, reservations, "is_occupied")  # both see the room free before either writes

    outcomes = run_together([lambda stay=stay: assign_room(stay, wanted).pk for stay in stays])

    assert sorted(kind for kind, _ in outcomes) == ["conflict", "ok"], outcomes
    assert [code for kind, code in outcomes if kind == "conflict"] == ["no_availability"]
    (winner,) = [stay_id for kind, stay_id in outcomes if kind == "ok"]
    assert list(Stay.objects.filter(room=wanted).values_list("pk", flat=True)) == [winner]
