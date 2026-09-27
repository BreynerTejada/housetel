"""The listings of the bookings API do not query per row (spec §8 / verification: no N+1): the number of SQL
queries of a page must not grow with the number of reservations, stays, rooms or groups on it."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.bookings.services.reservations import create_reservation
from apps.bookings.tests.factories import ReservationGroupFactory
from apps.bookings.tests.helpers import book, oct_, reservation_request, stay_request
from apps.guests.tests.factories import GuestFactory
from apps.inventory.tests.factories import BedFactory, RoomFactory

pytestmark = pytest.mark.django_db

BASE = "/api/v1/bookings/"


def queries_of(client, path, params=None) -> int:
    with CaptureQueriesContext(connection) as captured:
        response = client.get(f"{BASE}{path}", params or {})
    assert response.status_code == 200, response.json()
    return len(captured)


def add_reservations(hotel, first_day):
    """A mix that touches every related object of a list item: a group, an assigned room, a dorm party of
    several beds and a multi-stay reservation."""
    contact = GuestFactory(organization=hotel.prop.organization)
    group = ReservationGroupFactory(property=hotel.prop, contact_guest=contact)
    book(hotel, oct_(first_day), oct_(first_day + 1), group_id=group.pk)
    book(hotel, oct_(first_day), oct_(first_day + 2), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    book(hotel, oct_(first_day), oct_(first_day + 1), room_type=hotel.dorm_type, adults=2)
    create_reservation(
        reservation_request(
            hotel,
            [
                stay_request(hotel, oct_(first_day), oct_(first_day + 1)),
                stay_request(hotel, oct_(first_day), oct_(first_day + 1), room_type=hotel.ste, adults=1),
            ],
        )
    )


def test_the_reservation_list_does_not_query_per_reservation(hotel, api):
    add_reservations(hotel, 1)
    few = queries_of(api, "reservations/")
    add_reservations(hotel, 4)
    add_reservations(hotel, 7)
    assert queries_of(api, "reservations/") == few


def test_the_calendar_does_not_query_per_stay_room_or_bed(hotel, api):
    params = {"start": "2026-10-01", "end": "2026-10-15"}
    add_reservations(hotel, 1)
    queries_of(api, "calendar/", params)  # the first call materializes the InventoryDay rows of the range
    few = queries_of(api, "calendar/", params)
    RoomFactory(room_type=hotel.dbl, number="202", floor="2")
    extra_dorm = RoomFactory(room_type=hotel.dorm_type, number="D2")
    for label in "ABC":
        BedFactory(room=extra_dorm, label=label)
    add_reservations(hotel, 4)
    add_reservations(hotel, 7)
    assert queries_of(api, "calendar/", params) == few


def test_the_group_list_does_not_query_per_group(hotel, api):
    add_reservations(hotel, 1)
    few = queries_of(api, "groups/")
    add_reservations(hotel, 4)
    add_reservations(hotel, 7)
    assert queries_of(api, "groups/") == few


def test_room_options_do_not_query_per_dorm_room(hotel, api):
    stay = book(hotel, oct_(1), oct_(2), room_type=hotel.dorm_type, adults=1).stays.get()
    few = queries_of(api, f"stays/{stay.pk}/room-options/")
    for number in ("D2", "D3", "D4"):
        dorm = RoomFactory(room_type=hotel.dorm_type, number=number)
        for label in "AB":
            BedFactory(room=dorm, label=label)
    assert queries_of(api, f"stays/{stay.pk}/room-options/") == few
