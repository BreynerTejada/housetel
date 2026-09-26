import uuid

import pytest
from django.core import signing
from freezegun import freeze_time

from apps.bookings.tests.factories import ReservationFactory
from apps.core.tokens import SALT, make_reservation_token, portal_url, read_reservation_token

pytestmark = pytest.mark.django_db


def test_roundtrip_returns_the_reservation_with_its_property(prop):
    reservation = ReservationFactory(property=prop)
    found = read_reservation_token(make_reservation_token(reservation))
    assert found == reservation and found.property == prop


def test_tampered_token_reads_as_none(prop):
    token = make_reservation_token(ReservationFactory(property=prop))
    assert read_reservation_token(token[:-2] + ("aa" if not token.endswith("aa") else "bb")) is None
    assert read_reservation_token("garbage") is None


def test_token_signed_with_another_salt_is_rejected(prop):
    reservation = ReservationFactory(property=prop)
    forged = signing.dumps({"r": str(reservation.pk)}, salt="another.salt", compress=True)
    assert read_reservation_token(forged) is None


def test_expired_token_reads_as_none(prop):
    reservation = ReservationFactory(property=prop)
    with freeze_time("2026-09-01"):
        token = make_reservation_token(reservation)
    with freeze_time("2026-09-03"):
        assert read_reservation_token(token, max_age=3600) is None
        assert read_reservation_token(token) == reservation  # no max_age → never expires


def test_unknown_reservation_reads_as_none():
    token = signing.dumps({"r": str(uuid.uuid4())}, salt=SALT, compress=True)
    assert read_reservation_token(token) is None


def test_portal_url_points_to_the_frontend(prop, settings):
    settings.FRONTEND_URL = "http://localhost:5173"
    reservation = ReservationFactory(property=prop)
    url = portal_url(reservation)
    assert url.startswith("http://localhost:5173/g/")
    assert read_reservation_token(url.rsplit("/g/", 1)[1]) == reservation
