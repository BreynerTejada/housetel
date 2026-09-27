"""Receivers of `rates`: a reservation created with a promo code counts one use (so `max_uses` works)."""

from decimal import Decimal

import pytest

from apps.bookings.tests.factories import ReservationFactory
from apps.core.signals import reservation_created, send_on_commit
from apps.core.tests.factories import PropertyFactory
from apps.rates.models import PromoCode

pytestmark = pytest.mark.django_db


def promo(prop, code="BIENVENIDA10"):
    return PromoCode.objects.create(property=prop, code=code, discount_type="percent", value=Decimal("10"))


def announce(reservation, capture):
    with capture(execute=True):
        send_on_commit(reservation_created, reservation=reservation)


def test_a_reservation_with_a_promo_code_counts_one_use(prop, django_capture_on_commit_callbacks):
    item = promo(prop)
    announce(
        ReservationFactory(property=prop, promo_code=" bienvenida10 "), django_capture_on_commit_callbacks
    )
    item.refresh_from_db()
    assert item.uses == 1


def test_other_reservations_count_nothing(prop, django_capture_on_commit_callbacks):
    item = promo(prop)
    other_hotel = promo(PropertyFactory(organization=prop.organization))
    announce(ReservationFactory(property=prop, promo_code=""), django_capture_on_commit_callbacks)
    announce(ReservationFactory(property=prop, promo_code="NOEXISTE"), django_capture_on_commit_callbacks)
    item.refresh_from_db()
    other_hotel.refresh_from_db()
    assert (item.uses, other_hotel.uses) == (0, 0)
