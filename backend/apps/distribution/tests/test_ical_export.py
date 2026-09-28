"""Public iCal export `GET /api/v1/public/distribution/ical/<token>.ics`: a room (or a one-unit category)
exports its stays and blocks with stable UIDs; a category with several units exports the nights it is sold
out. All-day events: DTEND is the exclusive checkout date."""

from datetime import date

import icalendar
import pytest

from apps.bookings.services.reservations import cancel_reservation, create_reservation
from apps.bookings.tests.helpers import guest_input, oct_, stay_request
from apps.bookings.types import ReservationRequest
from apps.distribution.tests.factories import ChannelConnectionFactory, RoomMappingFactory
from apps.inventory.services import block_room, release_block

pytestmark = pytest.mark.django_db


def book(hotel, checkin, checkout, *, room_type=None, room=None, first_name="Laura"):
    return create_reservation(
        ReservationRequest(
            property=hotel.prop,
            booker=guest_input(first_name=first_name),
            stays=[
                stay_request(
                    hotel,
                    checkin,
                    checkout,
                    room_type=room_type or hotel.dbl,
                    room_id=room.pk if room is not None else None,
                )
            ],
            source="phone",
        )
    )


def calendar_mapping(hotel, *, room_type, room=None):
    connection = ChannelConnectionFactory(property=hotel.prop, channel_code="ical", name="Airbnb")
    return RoomMappingFactory(connection=connection, room_type=room_type, room=room, external_room_id="")


def events(public_api, mapping) -> tuple[list[tuple], str, object]:
    response = public_api.get(f"/api/v1/public/distribution/ical/{mapping.ical_export_token}.ics")
    assert response.status_code == 200
    text = response.content.decode()
    parsed = icalendar.Calendar.from_ical(text)
    rows = sorted(
        (str(event["uid"]), event.decoded("dtstart"), event.decoded("dtend"), str(event["summary"]))
        for event in parsed.walk("VEVENT")
    )
    return rows, text, response


def test_a_room_exports_its_stays_and_blocks_with_the_exclusive_checkout(hotel, public_api):
    room = hotel.rooms["101"]
    kept = book(hotel, oct_(10), oct_(12), room=room, first_name="Valeria")
    cancelled = book(hotel, oct_(14), oct_(15), room=room)
    cancel_reservation(cancelled, reason="Cambio de planes", waive_fee=True)
    book(hotel, oct_(10), oct_(12), room=hotel.rooms["102"])  # another room
    block = block_room(room, start=oct_(20), end=oct_(22), kind="maintenance", reason="Pintura")
    released = block_room(room, start=oct_(25), end=oct_(26), kind="maintenance", reason="Revisión")
    release_block(released)
    mapping = calendar_mapping(hotel, room_type=hotel.dbl, room=room)

    rows, text, response = events(public_api, mapping)

    stay = kept.stays.get()
    assert rows == sorted(
        [
            (f"stay-{stay.pk}@housetel.co", oct_(10), oct_(12), "Reservado"),
            (f"block-{block.pk}@housetel.co", oct_(20), oct_(22), "Bloqueado"),
        ]
    )
    assert "DTSTART;VALUE=DATE:20261010" in text and "DTEND;VALUE=DATE:20261012" in text
    assert "Valeria" not in text  # no guest data in a public calendar
    assert response["Content-Type"].startswith("text/calendar")


def test_a_one_unit_category_exports_every_stay_even_unassigned(hotel, public_api):
    unassigned = book(hotel, oct_(10), oct_(13), room_type=hotel.ste)
    mapping = calendar_mapping(hotel, room_type=hotel.ste)

    rows, _text, _response = events(public_api, mapping)

    assert rows == [(f"stay-{unassigned.stays.get().pk}@housetel.co", oct_(10), oct_(13), "Reservado")]


def test_a_category_with_several_units_exports_the_nights_it_is_sold_out(hotel, public_api):
    for room in ("101", "102", "201"):
        book(hotel, oct_(10), oct_(12), room=hotel.rooms[room])
    book(hotel, oct_(12), oct_(13), room=hotel.rooms["101"])
    mapping = calendar_mapping(hotel, room_type=hotel.dbl)

    rows, _text, _response = events(public_api, mapping)

    assert rows == [(f"closed-{mapping.pk}-20261010@housetel.co", oct_(10), oct_(12), "No disponible")]


def test_a_dorm_room_exports_the_nights_all_its_beds_are_taken(hotel, public_api):
    party = create_reservation(
        ReservationRequest(
            property=hotel.prop,
            booker=guest_input(),
            stays=[
                stay_request(
                    hotel, oct_(10), oct_(12), room_type=hotel.dorm_type, adults=4, room_id=hotel.dorm.pk
                )
            ],
            source="phone",
        )
    )
    assert party.stays.count() == 4
    mapping = calendar_mapping(hotel, room_type=hotel.dorm_type, room=hotel.dorm)

    rows, _text, _response = events(public_api, mapping)

    assert rows == [(f"closed-{mapping.pk}-20261010@housetel.co", oct_(10), oct_(12), "No disponible")]


def test_the_export_window_starts_a_week_ago(hotel, public_api):
    room = hotel.rooms["101"]
    hotel.prop.business_date = date(2026, 10, 20)
    hotel.prop.save(update_fields=["business_date"])
    from apps.bookings.models import Stay
    from apps.bookings.tests.factories import ReservationFactory, StayFactory

    old = StayFactory(
        reservation=ReservationFactory(property=hotel.prop, checkin_date=oct_(2), checkout_date=oct_(5)),
        room_type=hotel.dbl,
        rate_plan=hotel.plan,
        room=room,
        checkin_date=oct_(2),
        checkout_date=oct_(5),
        status=Stay.Status.CHECKED_OUT,
    )
    recent = StayFactory(
        reservation=ReservationFactory(property=hotel.prop, checkin_date=oct_(12), checkout_date=oct_(15)),
        room_type=hotel.dbl,
        rate_plan=hotel.plan,
        room=room,
        checkin_date=oct_(12),
        checkout_date=oct_(15),
        status=Stay.Status.CHECKED_OUT,
    )
    mapping = calendar_mapping(hotel, room_type=hotel.dbl, room=room)

    rows, _text, _response = events(public_api, mapping)

    assert [uid for uid, *_rest in rows] == [f"stay-{recent.pk}@housetel.co"]
    assert old.pk != recent.pk


def test_an_unknown_token_is_404(hotel, public_api):
    response = public_api.get("/api/v1/public/distribution/ical/not-a-token.ics")
    assert response.status_code == 404
