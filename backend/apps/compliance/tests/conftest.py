"""Shared fixtures of the compliance tests: a hotel with its taxes and a finished reservation to invoice."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.compliance.tests.factories import ComplianceSettingsFactory, InvoiceResolutionFactory, post
from apps.finance.tests.factories import FolioFactory
from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory
from apps.rates.tests.factories import TaxFactory


@pytest.fixture
def hotel(prop):
    prop.nit = "901234567-7"
    prop.legal_name = "Casa Aurora Hoteles S.A.S."
    prop.address = "Calle del Cuartel #36-77"
    prop.rnt_number = "98765"
    prop.phone = "+57 605 660 1234"
    prop.save()
    ComplianceSettingsFactory(property=prop)
    return prop


@pytest.fixture
def resolution(hotel):
    return InvoiceResolutionFactory(property=hotel)


@pytest.fixture
def lodging_tax(hotel):
    return TaxFactory(property=hotel, code="IVA", name="IVA 19% alojamiento")


@pytest.fixture
def extras_tax(hotel):
    return TaxFactory(
        property=hotel,
        code="IVA-EXT",
        name="IVA 19% extras",
        applies_to="extras",
        exempt_foreign_non_residents=False,
    )


@pytest.fixture
def make_finished_reservation(hotel, lodging_tax):
    """A checked-out reservation (2 nights × 320.000 + IVA) with its guest folio and posted charges."""

    def _make(
        *, booker=None, nights=2, price="320000", status="checked_out", checkin=None, room=None, exempt=False
    ):
        checkin = checkin or hotel.business_date - timedelta(days=nights)
        extra = {"booker": booker} if booker is not None else {}
        reservation = ReservationFactory(
            property=hotel,
            status=status,
            checkin_date=checkin,
            checkout_date=checkin + timedelta(days=nights),
            **extra,
        )
        room_type = (
            room.room_type
            if room
            else RoomTypeFactory(
                property=hotel, code=f"C{reservation.code[-4:]}", name={"es": "Estándar", "en": "Standard"}
            )
        )
        stay = StayFactory(reservation=reservation, room_type=room_type, room=room, status=status)
        folio = FolioFactory(reservation=reservation)
        tax_amount = Decimal("0") if exempt else Decimal(price) * Decimal("0.19")
        for offset in range(nights):
            day = checkin + timedelta(days=offset)
            post(
                folio,
                kind="room",
                amount=price,
                description=f"Noche {day}",
                tax=lodging_tax,
                tax_amount=tax_amount,
                stay=stay,
                night_date=day,
                business_date=day,
            )
        return reservation

    return _make


@pytest.fixture
def room(hotel):
    room_type = RoomTypeFactory(property=hotel, code="DBL", name={"es": "Estándar", "en": "Standard"})
    return RoomFactory(room_type=room_type, number="101")


@pytest.fixture
def fixed_day():
    return date(2026, 10, 14)
