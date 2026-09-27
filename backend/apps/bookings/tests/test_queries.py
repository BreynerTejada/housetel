"""`with_balance` annotates reservations with what they owe in SQL (for lists, filters and the calendar). It
must agree with the contract `finance.reservation_balance` in every case."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.models import Reservation
from apps.bookings.services.charges import post_room_charges
from apps.bookings.services.queries import with_balance
from apps.bookings.services.reservations import cancel_reservation
from apps.bookings.tests.helpers import book, oct_
from apps.finance.models import Charge, Refund
from apps.finance.services import get_or_create_folio, post_charge, record_payment, reservation_balance

pytestmark = pytest.mark.django_db


def test_matches_reservation_balance(hotel):
    untouched = book(hotel, oct_(1), oct_(3))
    charged = book(hotel, oct_(1), oct_(3))
    post_room_charges(charged.stays.get(), until_date=oct_(3))
    folio = get_or_create_folio(charged)
    post_charge(folio, kind="extra", amount=Decimal("35000"), description="Desayuno", tax=hotel.iva)
    voided = post_charge(folio, kind="fee", amount=Decimal("9999"), description="Error")
    Charge.objects.filter(pk=voided.pk).update(voided_at=timezone.now())
    payment = record_payment(folio, amount=Decimal("500000"), method="bank_transfer")
    Refund.objects.create(payment=payment, amount=Decimal("100000"), status="approved")
    Refund.objects.create(payment=payment, amount=Decimal("5000"), status="pending")
    record_payment(folio, amount=Decimal("1000"), method="bank_transfer", status="declined")
    cancelled = book(hotel, oct_(5), oct_(6))
    cancel_reservation(cancelled, reason="-")

    annotated = {item.pk: item.balance for item in with_balance(Reservation.objects.all())}

    for reservation in (untouched, charged, cancelled):
        assert annotated[reservation.pk] == reservation_balance(reservation), reservation.code
    assert annotated[charged.pk] == Decimal("761600") + Decimal("41650") - Decimal("400000")
    assert annotated[cancelled.pk] == Decimal("0")
