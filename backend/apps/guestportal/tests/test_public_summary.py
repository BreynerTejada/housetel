"""The magic link (`/api/v1/public/guestportal/<token>/`): who can open it and what the guest sees."""

import pytest
from django.core import signing

from apps.bookings.tests.helpers import book, oct_
from apps.core.tokens import make_reservation_token

pytestmark = pytest.mark.django_db

PORTAL_ENDPOINTS = [
    ("get", ""),
    ("get", "checkin/"),
    ("post", "checkin/"),
    ("post", "checkin/complete/"),
    ("post", "pay/"),
    ("get", "extras/"),
    ("post", "requests/"),
    ("post", "cancel/"),
    ("post", "modify/"),
    ("post", "modify-preview/"),
]


def _tampered(token: str) -> str:
    """Same payload, one character of the signature changed."""
    last = "A" if token[-1] != "A" else "B"
    return token[:-1] + last


@pytest.mark.parametrize(("method", "path"), PORTAL_ENDPOINTS)
def test_a_tampered_token_is_an_invalid_link_everywhere(public_api, token, method, path):
    response = getattr(public_api, method)(
        f"/api/v1/public/guestportal/{_tampered(token)}/{path}", format="json"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_link"


def test_a_token_signed_for_something_else_is_invalid(public_api, reservation):
    foreign = signing.dumps({"r": str(reservation.pk)}, salt="another.salt", compress=True)

    response = public_api.get(f"/api/v1/public/guestportal/{foreign}/")

    assert response.status_code == 404
    assert response.json()["code"] == "invalid_link"


def test_the_summary_shows_the_booking_to_its_guest(public_api, portal_url, reservation, hotel):
    response = public_api.get(portal_url())

    assert response.status_code == 200
    body = response.json()
    assert body["reservation"]["code"] == reservation.code
    assert body["reservation"]["status"] == "confirmed"
    assert (body["reservation"]["checkin_date"], body["reservation"]["checkout_date"]) == (
        "2026-10-05",
        "2026-10-07",
    )
    assert body["reservation"]["nights"] == 2
    assert body["property"]["name"] == hotel.prop.name
    assert [stay["room_type"]["code"] for stay in body["stays"]] == ["DBL"]
    # 2 nights × 320.000 + IVA 19 % (Colombian resident) = 761.600; nothing paid yet
    assert body["balance"] == {
        "total": "761600.00",
        "paid": "0.00",
        "due": "761600.00",
        "can_pay": True,
        "currency": "COP",
    }
    assert body["checkin"]["status"] == "not_started"
    assert body["checkin"]["is_open"] is True
    assert [guest["role"] for guest in body["guests"]] == ["booker"]
    assert body["guests"][0]["full_name"] == reservation.booker.full_name


def test_the_summary_greets_the_booker_by_name_and_knows_the_hotel_date(public_api, portal_url, reservation):
    body = public_api.get(portal_url()).json()

    assert body["today"] == "2026-10-01"  # the property's business date, not the server clock
    assert body["guests"][0]["first_name"] == reservation.booker.first_name


def test_the_summary_lists_what_the_guest_already_paid(public_api, portal_url, reservation):
    from decimal import Decimal

    from apps.finance.services import get_or_create_folio, record_payment

    record_payment(get_or_create_folio(reservation), amount=Decimal("200000"), method="bank_transfer")

    body = public_api.get(portal_url()).json()

    assert body["payments"] == [{"date": "2026-10-01", "method": "bank_transfer", "amount": "200000.00"}]
    assert body["balance"]["paid"] == "200000.00"


def test_the_portal_is_private_and_never_cached(public_api, portal_url):
    response = public_api.get(portal_url())

    assert "no-store" in response["Cache-Control"]
    assert response["X-Robots-Tag"] == "noindex, nofollow"


def test_the_summary_never_shows_staff_notes_or_identity_numbers(public_api, portal_url, reservation):
    reservation.notes = "Cliente difícil: cobrar todo por adelantado"
    reservation.save(update_fields=["notes"])

    text = public_api.get(portal_url()).content.decode()

    assert "Cliente difícil" not in text
    assert reservation.booker.document_number not in text


def test_each_link_only_opens_its_own_booking(public_api, hotel, reservation):
    other = book(hotel, oct_(10), oct_(12))

    body = public_api.get(f"/api/v1/public/guestportal/{make_reservation_token(other)}/").json()

    assert body["reservation"]["code"] == other.code != reservation.code


def test_the_check_in_opens_a_week_before_arrival(public_api, hotel):
    later = book(hotel, oct_(20), oct_(22))  # business date Oct 1: opens Oct 13

    body = public_api.get(f"/api/v1/public/guestportal/{make_reservation_token(later)}/").json()

    assert body["checkin"]["is_open"] is False
    assert body["checkin"]["opens_on"] == "2026-10-13"
    assert body["checkin"]["reason"] == "not_open_yet"
