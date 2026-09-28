"""Template variables: what `{{...}}` can say about the guest, the reservation and the hotel."""

from datetime import date
from decimal import Decimal

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.tokens import read_reservation_token
from apps.guests.tests.factories import GuestFactory
from apps.inventory.tests.factories import RoomTypeFactory
from apps.messaging.variables import VARIABLES, build_variables

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _frontend(settings):
    settings.FRONTEND_URL = "http://front.test"


@pytest.fixture
def reservation(prop):
    prop.name = "Hotel Casa Aurora"
    prop.phone = "+57 605 660 1234"
    prop.address = "Calle del Cuartel #36-77"
    prop.save()
    guest = GuestFactory(organization=prop.organization, first_name="Ana", last_name="Pérez")
    reservation = ReservationFactory(
        property=prop,
        booker=guest,
        code="HT-7K2M9Q",
        checkin_date=date(2026, 10, 9),
        checkout_date=date(2026, 10, 11),
        adults=2,
        children=1,
        total_amount=Decimal("761600"),
    )
    room_type = RoomTypeFactory(property=prop, name={"es": "Suite Vista al Mar", "en": "Sea View Suite"})
    StayFactory(reservation=reservation, room_type=room_type, total_amount=Decimal("761600"))
    return reservation


def test_reservation_guest_and_hotel_values_in_spanish(reservation):
    values = build_variables(property=reservation.property, reservation=reservation, language="es")
    assert {
        key: values[key]
        for key in (
            "guest.first_name",
            "guest.last_name",
            "guest.full_name",
            "reservation.code",
            "reservation.checkin",
            "reservation.checkout",
            "nights",
            "reservation.adults",
            "reservation.children",
            "reservation.guests",
            "reservation.room_type",
            "reservation.total",
            "balance",
            "property.name",
            "property.phone",
            "property.address",
            "property.check_in_time",
            "property.check_out_time",
        )
    } == {
        "guest.first_name": "Ana",
        "guest.last_name": "Pérez",
        "guest.full_name": "Ana Pérez",
        "reservation.code": "HT-7K2M9Q",
        "reservation.checkin": "viernes 9 de octubre de 2026",
        "reservation.checkout": "domingo 11 de octubre de 2026",
        "nights": "2",
        "reservation.adults": "2",
        "reservation.children": "1",
        "reservation.guests": "3",
        "reservation.room_type": "Suite Vista al Mar",
        "reservation.total": "$ 761.600",
        "balance": "$ 761.600",
        "property.name": "Hotel Casa Aurora",
        "property.phone": "+57 605 660 1234",
        "property.address": "Calle del Cuartel #36-77",
        "property.check_in_time": "15:00",
        "property.check_out_time": "12:00",
    }


def test_dates_and_names_follow_the_language(reservation):
    values = build_variables(property=reservation.property, reservation=reservation, language="en")
    assert values["reservation.checkin"] == "Friday, October 9, 2026"
    assert values["reservation.room_type"] == "Sea View Suite"


def test_portal_links_are_signed_for_the_reservation(reservation):
    values = build_variables(property=reservation.property, reservation=reservation, language="es")
    assert values["portal_url"].startswith("http://front.test/g/")
    token = values["portal_url"].removeprefix("http://front.test/g/")
    assert read_reservation_token(token) == reservation
    assert values["checkin_url"] == f"{values['portal_url']}/checkin"
    assert values["payment_url"] == values["portal_url"]  # the portal lets the guest pay the balance


def test_the_caller_context_adds_and_overrides_values(reservation):
    values = build_variables(
        property=reservation.property,
        reservation=reservation,
        language="es",
        context={"payment_url": "http://front.test/sim/pay/HT-1", "amount": "$ 200.000", "reference": "HT-1"},
    )
    assert (values["payment_url"], values["amount"], values["reference"]) == (
        "http://front.test/sim/pay/HT-1",
        "$ 200.000",
        "HT-1",
    )


def test_an_iso_expiry_from_the_context_is_shown_in_hotel_time(reservation):
    context = {"expires_at": "2026-09-27T23:44:51+00:00"}
    es = build_variables(
        property=reservation.property, reservation=reservation, language="es", context=context
    )
    en = build_variables(
        property=reservation.property, reservation=reservation, language="en", context=context
    )
    assert es["expires_at"] == "27 de septiembre de 2026, 18:44"
    assert en["expires_at"] == "September 27, 2026, 18:44"


def test_without_a_reservation_only_guest_and_hotel_values_exist(prop):
    guest = GuestFactory(organization=prop.organization, first_name="Luis", last_name="Mora")
    values = build_variables(property=prop, guest=guest, language="es")
    assert values["guest.full_name"] == "Luis Mora" and values["property.name"] == prop.name
    assert "reservation.code" not in values and "portal_url" not in values


def test_every_documented_variable_is_produced(reservation):
    context = {"amount": "$ 1", "reference": "R", "expires_at": "2026-09-27T23:44:51+00:00"}
    values = build_variables(
        property=reservation.property, reservation=reservation, language="es", context=context
    )
    documented = {item["key"] for item in VARIABLES}
    assert documented - set(values) == set()
    assert {
        "guest.first_name",
        "reservation.code",
        "portal_url",
        "checkin_url",
        "payment_url",
        "balance",
        "nights",
    } <= documented
