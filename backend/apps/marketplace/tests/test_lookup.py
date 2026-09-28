"""Booking lookup for the confirmation page: `GET bookings/<code>/?email=`."""

import pytest

from apps.bookings.models import Reservation
from apps.marketplace.tests.conftest import PUBLIC
from apps.marketplace.tests.helpers import booking_payload, guest_payload

pytestmark = pytest.mark.django_db


def _book(public_api, payload):
    response = public_api.post(f"{PUBLIC}/bookings/", payload, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def _lookup(public_api, code, email, expected=200):
    response = public_api.get(f"{PUBLIC}/bookings/{code}/", {"email": email})
    assert response.status_code == expected, response.json()
    return response.json()


def test_the_booker_email_opens_the_booking(public_api, hotel):
    payload = booking_payload(
        hotel, payment_option="pay_now", extras=[{"extra_id": str(hotel.breakfast.pk), "quantity": 2}]
    )
    code = _book(public_api, payload)["reservation_code"]

    data = _lookup(public_api, code.lower(), "LAURA@example.com")  # code and email without case

    assert data["code"] == code
    assert data["status"] == "tentative"
    assert data["via"] == "marketplace"
    assert data["property"]["slug"] == hotel.prop.slug
    assert data["property"]["check_in_time"] == "15:00"
    assert (data["checkin"], data["checkout"], data["nights"]) == ("2026-10-09", "2026-10-11", 2)
    assert data["booker"] == {"first_name": "Laura", "last_name": "Gómez", "email": "laura@example.com"}
    assert data["rooms"][0]["units"] == 1
    assert data["rooms"][0]["room_type_name"]["es"] == hotel.dbl.name["es"]
    assert [(extra["quantity"], extra["total"]) for extra in data["extras"]] == [(2, "83300.00")]
    # 761.600 + breakfast 70.000 + IVA 13.300
    assert data["total"] == "844900.00"
    assert data["balance"] == "844900.00"
    assert data["payment"]["status"] == "created"
    assert data["payment"]["amount"] == "844900.00"
    assert data["payment"]["checkout_url"].endswith(data["payment"]["reference"])
    assert data["portal_url"].startswith("http")
    assert data["tax_exempt"] is False
    assert data["cancellation_policy"]["name"]["es"] == "Flexible 48h"


def test_a_wrong_email_answers_404(public_api, hotel):
    code = _book(public_api, booking_payload(hotel))["reservation_code"]

    data = _lookup(public_api, code, "otra@example.com", expected=404)

    assert data["code"] == "not_found"
    assert "portal_url" not in data


def test_the_email_is_required(public_api, hotel):
    code = _book(public_api, booking_payload(hotel))["reservation_code"]

    response = public_api.get(f"{PUBLIC}/bookings/{code}/")

    assert response.status_code == 400


def test_bookings_made_by_the_staff_are_not_exposed(public_api, hotel):
    from apps.bookings.services.reservations import create_reservation
    from apps.bookings.types import ReservationRequest, StayRequest
    from apps.guests.types import GuestInput
    from apps.marketplace.tests.helpers import day

    reservation = create_reservation(
        ReservationRequest(
            property=hotel.prop,
            booker=GuestInput(first_name="Ana", last_name="Recepción", email="ana@example.com"),
            stays=[StayRequest(hotel.dbl.pk, hotel.flex.pk, day(3), day(4), 2)],
            source="phone",
        )
    )

    _lookup(public_api, reservation.code, "ana@example.com", expected=404)


def test_foreign_bookings_show_the_exemption(public_api, hotel):
    payload = booking_payload(hotel, guest=guest_payload(nationality="FR", country_of_residence="FR"))
    code = _book(public_api, payload)["reservation_code"]

    data = _lookup(public_api, code, "laura@example.com")

    assert data["tax_exempt"] is True
    assert data["total"] == "640000.00"
    assert data["payment"] is None
    assert Reservation.objects.get(code=code).status == "confirmed"
