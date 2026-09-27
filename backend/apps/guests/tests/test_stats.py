"""guest_stats: the numbers on the guest profile (stays, nights, total spent, last and next stay)."""

from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.tests.factories import PropertyFactory
from apps.finance.tests.factories import ChargeFactory, FolioFactory
from apps.guests.selectors import guest_stats
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db

TODAY = date(2026, 9, 25)


@pytest.fixture
def history(organization, prop):
    guest = GuestFactory(organization=organization)
    other_hotel = PropertyFactory(organization=organization, name="Andino Medellín")
    past = ReservationFactory(
        property=prop, booker=guest, status="checked_out", code="HT-PAST01",
        checkin_date=date(2024, 1, 10), checkout_date=date(2024, 1, 13),
    )  # fmt: skip
    folio = FolioFactory(reservation=past)
    ChargeFactory(folio=folio, kind="room", unit_price=Decimal("300000"), tax_amount=Decimal("57000"))
    ChargeFactory(folio=folio, kind="extra", unit_price=Decimal("50000"), tax_amount=Decimal("9500"))
    ChargeFactory(folio=folio, kind="extra", unit_price=Decimal("99999"), voided_at=timezone.now())
    # In house right now as a companion: counts as a stay, but someone else pays.
    companion = StayFactory(
        reservation=ReservationFactory(
            property=other_hotel, status="checked_in", code="HT-NOW001",
            checkin_date=date(2026, 9, 24), checkout_date=date(2026, 9, 27),
        ),
        occupants=[guest],
    )  # fmt: skip
    ChargeFactory(folio=FolioFactory(reservation=companion.reservation), unit_price=Decimal("777000"))
    upcoming = ReservationFactory(
        property=prop, booker=guest, status="confirmed", code="HT-NEXT01",
        checkin_date=date(2026, 10, 5), checkout_date=date(2026, 10, 7),
    )  # fmt: skip
    ReservationFactory(property=prop, booker=guest, status="cancelled", checkin_date=date(2025, 3, 1),
                       checkout_date=date(2025, 3, 2))  # fmt: skip
    ReservationFactory(property=prop, booker=guest, status="no_show", checkin_date=date(2025, 4, 1),
                       checkout_date=date(2025, 4, 2))  # fmt: skip
    ReservationFactory(property=prop, status="checked_out")  # another guest's history
    return guest, companion.reservation, upcoming


def test_counts_real_stays_nights_and_what_the_guest_paid(history):
    guest, *_ = history
    stats = guest_stats(guest, today=TODAY)
    assert (stats["reservations_count"], stats["stays_count"], stats["nights"]) == (5, 2, 6)
    assert stats["total_spent"] == Decimal("416500")  # net + IVA, booker only, voided excluded
    assert (stats["cancellations"], stats["no_shows"]) == (1, 1)


def test_last_and_next_stay(history):
    guest, current, upcoming = history
    stats = guest_stats(guest, today=TODAY)
    assert stats["last_stay"] == {
        "reservation_id": str(current.pk),
        "code": "HT-NOW001",
        "property_id": str(current.property_id),
        "property_name": "Andino Medellín",
        "checkin": "2026-09-24",
        "checkout": "2026-09-27",
        "status": "checked_in",
    }
    assert stats["next_stay"]["code"] == upcoming.code


def test_a_new_guest_has_empty_stats(organization):
    stats = guest_stats(GuestFactory(organization=organization), today=TODAY)
    assert stats == {
        "reservations_count": 0,
        "stays_count": 0,
        "nights": 0,
        "total_spent": Decimal("0"),
        "cancellations": 0,
        "no_shows": 0,
        "last_stay": None,
        "next_stay": None,
    }
