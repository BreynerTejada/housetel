"""Phase A finance services (plan Step 5): folio, charges (net + tax apart), payments, balances."""

from decimal import Decimal

import pytest
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.errors import DomainError
from apps.core.signals import payment_received
from apps.finance.cash import open_cash_shift
from apps.finance.models import Charge, Folio, Payment, Refund
from apps.finance.services import (
    folio_balance,
    get_or_create_folio,
    post_charge,
    record_payment,
    reservation_balance,
)
from apps.rates.tests.factories import TaxFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def reservation(prop):
    reservation = ReservationFactory(property=prop)
    StayFactory(reservation=reservation, total_amount=Decimal("700000"))  # 2 nights × 350000 incl. IVA
    return reservation


@pytest.fixture
def iva(prop):
    return TaxFactory(property=prop, rate=Decimal("19.00"))


@pytest.fixture
def folio(reservation):
    return get_or_create_folio(reservation)


class TestFolio:
    def test_creates_one_guest_folio_per_reservation(self, reservation):
        folio = get_or_create_folio(reservation)
        assert (folio.property, folio.reservation, folio.stay, folio.guest) == (
            reservation.property,
            reservation,
            None,
            reservation.booker,
        )
        assert (folio.folio_type, folio.status, folio.currency) == ("guest", "open", "COP")
        assert get_or_create_folio(reservation).pk == folio.pk

    def test_a_stay_can_have_its_own_folio(self, reservation):
        stay = reservation.stays.get()
        assert get_or_create_folio(reservation, stay=stay).pk != get_or_create_folio(reservation).pk
        assert Folio.objects.filter(reservation=reservation).count() == 2


class TestPostCharge:
    def test_amount_is_net_and_tax_goes_apart(self, folio, iva, owner):
        charge = post_charge(
            folio,
            kind="extra",
            amount=Decimal("35000"),
            description="Desayuno",
            quantity=2,
            tax=iva,
            actor=owner,
        )
        charge.refresh_from_db()
        assert (charge.unit_price, charge.quantity, charge.amount, charge.tax_amount, charge.total) == (
            Decimal("35000"),
            2,
            Decimal("70000"),
            Decimal("13300"),
            Decimal("83300"),
        )
        assert (charge.tax, charge.posted_by, charge.source) == (iva, owner, "user")
        assert charge.business_date == folio.property.business_date

    def test_tax_is_rounded_to_whole_pesos(self, folio, iva):
        charge = post_charge(folio, kind="room", amount=Decimal("294118"), description="Noche", tax=iva)
        assert charge.tax_amount == Decimal("55882")  # 294118 × 0.19 = 55882.42

    def test_exempt_charges_keep_the_tax_reference_with_zero_amount(self, folio, iva):
        charge = post_charge(
            folio, kind="room", amount=Decimal("300000"), description="Noche", tax=iva, tax_exempt=True
        )
        assert (charge.tax, charge.tax_amount, charge.total) == (iva, Decimal("0"), Decimal("300000"))

    def test_optional_links_and_business_date(self, folio, reservation):
        stay = reservation.stays.get()
        night = stay.checkin_date
        charge = post_charge(
            folio,
            kind="room",
            amount=Decimal("100000"),
            description="Noche",
            stay=stay,
            night_date=night,
            business_date=night,
            source="automation",
        )
        assert (charge.stay, charge.night_date, charge.business_date, charge.source, charge.posted_by) == (
            stay,
            night,
            night,
            "automation",
            None,
        )

    def test_closed_folios_do_not_accept_charges(self, folio):
        folio.status = "closed"
        folio.save()
        with pytest.raises(DomainError) as exc:
            post_charge(folio, kind="extra", amount=Decimal("1000"), description="x")
        assert exc.value.code == "folio_closed"


class TestRecordPayment:
    def test_records_an_approved_payment_and_emits_payment_received(
        self, folio, owner, django_capture_on_commit_callbacks
    ):
        received = []

        def receiver(sender, **kwargs):
            received.append(kwargs["payment"])

        open_cash_shift(folio.property, owner, opening_float=Decimal("0"))  # B4: cash needs an open shift
        payment_received.connect(receiver)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                payment = record_payment(
                    folio, amount=Decimal("200000"), method="cash", reference="REC-1", actor=owner
                )
        finally:
            payment_received.disconnect(receiver)
        payment.refresh_from_db()
        assert (
            payment.amount,
            payment.method,
            payment.status,
            payment.provider,
            payment.provider_reference,
        ) == (
            Decimal("200000"),
            "cash",
            "approved",
            "manual",
            "REC-1",
        )
        assert (payment.received_by, payment.business_date) == (owner, folio.property.business_date)
        assert received == [payment]

    def test_pending_payments_do_not_emit(self, folio, django_capture_on_commit_callbacks):
        received = []
        payment_received.connect(
            lambda sender, **kw: received.append(kw), weak=False, dispatch_uid="t-pending"
        )
        try:
            with django_capture_on_commit_callbacks(execute=True):
                payment = record_payment(
                    folio,
                    amount=Decimal("1000"),
                    method="wompi_card",
                    status="pending",
                    provider="wompi",
                    payload={"id": "tx-1"},
                )
        finally:
            payment_received.disconnect(dispatch_uid="t-pending")
        assert payment.provider_payload == {"id": "tx-1"} and received == []

    @pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-5")])
    def test_amount_must_be_positive(self, folio, amount):
        with pytest.raises(DomainError) as exc:
            record_payment(folio, amount=amount, method="cash")
        assert exc.value.code == "invalid_amount"


class TestBalances:
    def test_folio_balance(self, folio, iva):
        post_charge(folio, kind="extra", amount=Decimal("100000"), description="A", tax=iva)  # 119000
        voided = post_charge(folio, kind="extra", amount=Decimal("50000"), description="B")
        Charge.objects.filter(pk=voided.pk).update(voided_at=timezone.now(), void_reason="error")
        paid = record_payment(folio, amount=Decimal("100000"), method="cash")
        record_payment(folio, amount=Decimal("5000"), method="cash", status="declined")
        Refund.objects.create(payment=paid, amount=Decimal("20000"), status="approved")
        Refund.objects.create(payment=paid, amount=Decimal("7000"), status="pending")
        assert folio_balance(folio) == Decimal("39000")  # 119000 − 100000 + 20000

    def test_reservation_balance_counts_the_expected_stay_total_once(self, reservation, folio, iva):
        assert reservation_balance(reservation) == Decimal("700000")
        stay = reservation.stays.get()
        for night in stay.nights:  # posting room nights does not change what is owed
            post_charge(
                folio,
                kind="room",
                amount=Decimal("294118"),
                description="Noche",
                tax=iva,
                stay=stay,
                night_date=night,
            )
        assert reservation_balance(reservation) == Decimal("700000")
        post_charge(folio, kind="extra", amount=Decimal("35000"), description="Desayuno", tax=iva)  # 41650
        record_payment(folio, amount=Decimal("300000"), method="card_terminal")
        assert reservation_balance(reservation) == Decimal("441650")

    def test_reservation_balance_uses_every_folio_of_the_reservation(self, reservation, folio):
        stay_folio = get_or_create_folio(reservation, stay=reservation.stays.get())
        record_payment(folio, amount=Decimal("100000"), method="cash")
        record_payment(stay_folio, amount=Decimal("50000"), method="cash")
        assert reservation_balance(reservation) == Decimal("550000")

    def test_cancelled_stays_are_not_owed_but_their_fee_is(self, reservation, folio):
        reservation.stays.update(status="cancelled")
        post_charge(folio, kind="cancellation_fee", amount=Decimal("350000"), description="Penalidad")
        assert reservation_balance(reservation) == Decimal("350000")

    def test_checked_out_stays_are_still_owed(self, reservation, folio):
        reservation.stays.update(status="checked_out")
        record_payment(folio, amount=Decimal("700000"), method="cash")
        assert reservation_balance(reservation) == Decimal("0")

    def test_payments_of_other_reservations_do_not_count(self, reservation, prop):
        other = ReservationFactory(property=prop)
        record_payment(get_or_create_folio(other), amount=Decimal("100000"), method="cash")
        assert reservation_balance(reservation) == Decimal("700000")
        assert Payment.objects.count() == 1
