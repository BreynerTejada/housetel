import re
from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.bookings.models import InventoryDay, Reservation
from apps.bookings.tests.factories import ReservationFactory
from apps.inventory.tests.factories import RoomTypeFactory

pytestmark = pytest.mark.django_db


class TestReservation:
    def test_code_is_generated_when_missing(self, prop):
        reservation = ReservationFactory(property=prop, code="")
        assert re.fullmatch(r"HT-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}", reservation.code)

    def test_code_is_unique_across_properties(self, prop, organization):
        ReservationFactory(property=prop, code="HT-AAAAAA")
        with pytest.raises(IntegrityError), transaction.atomic():
            ReservationFactory(code="HT-AAAAAA")

    def test_defaults(self, prop):
        reservation = ReservationFactory(property=prop)
        fresh = Reservation.objects.get(pk=reservation.pk)
        assert (fresh.guarantee, fresh.currency, fresh.tags, fresh.custom_values) == ("none", "COP", [], {})
        assert fresh.hold_expires_at is None and fresh.eta is None


class TestInventoryDay:
    def test_available_is_total_minus_sold_minus_blocked(self, prop):
        day = InventoryDay(
            property=prop,
            room_type=RoomTypeFactory(property=prop),
            date=date(2026, 10, 1),
            total_units=10,
            sold_units=6,
            blocked_units=1,
        )
        assert day.available == 3

    def test_available_goes_negative_when_overbooked(self, prop):
        day = InventoryDay(total_units=2, sold_units=3, blocked_units=0)
        assert day.available == -1

    def test_one_row_per_room_type_and_date(self, prop):
        room_type = RoomTypeFactory(property=prop)
        InventoryDay.objects.create(property=prop, room_type=room_type, date=date(2026, 10, 1), total_units=5)
        with pytest.raises(IntegrityError), transaction.atomic():
            InventoryDay.objects.create(
                property=prop, room_type=room_type, date=date(2026, 10, 1), total_units=5
            )
