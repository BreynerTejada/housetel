"""record_payment rules (cash shift, closed folio, audit) and void_payment for manual payments."""

from decimal import Decimal

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.errors import ConfirmationRequired, DomainError
from apps.core.models import AuditEvent
from apps.finance import services
from apps.finance.cash import open_cash_shift
from apps.finance.models import Payment
from apps.finance.services import (
    get_or_create_folio,
    record_payment,
    refund_payment,
    reservation_balance,
    void_payment,
)
from apps.finance.tests.factories import PaymentFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def reservation(prop):
    reservation = ReservationFactory(property=prop)
    StayFactory(reservation=reservation, total_amount=Decimal("700000"))
    return reservation


@pytest.fixture
def folio(reservation):
    return get_or_create_folio(reservation)


class TestCashShiftRule:
    def test_cash_requires_an_open_shift_of_the_actor(self, folio, owner):
        with pytest.raises(DomainError) as exc:
            record_payment(folio, amount=Decimal("100000"), method="cash", actor=owner)
        assert (exc.value.code, exc.value.status_code) == ("cash_shift_required", 409)

    def test_payments_taken_during_a_shift_are_linked_to_it(self, folio, owner, prop):
        shift = open_cash_shift(prop, owner, opening_float=Decimal("200000"))
        cash = record_payment(folio, amount=Decimal("100000"), method="cash", actor=owner)
        card = record_payment(folio, amount=Decimal("50000"), method="card_terminal", actor=owner)
        assert cash.cash_shift == shift and card.cash_shift == shift

    def test_another_users_shift_does_not_count(self, folio, owner, prop, make_member):
        open_cash_shift(prop, make_member("front_desk"), opening_float=Decimal("0"))
        with pytest.raises(DomainError) as exc:
            record_payment(folio, amount=Decimal("100000"), method="cash", actor=owner)
        assert exc.value.code == "cash_shift_required"

    def test_the_rule_can_be_turned_off_per_property(self, folio, owner, prop):
        prop.settings = {"require_cash_shift": False}
        prop.save()
        folio.refresh_from_db()
        payment = record_payment(folio, amount=Decimal("100000"), method="cash", actor=owner)
        assert payment.status == "approved" and payment.cash_shift is None

    def test_non_cash_payments_and_system_payments_need_no_shift(self, folio, owner):
        assert (
            record_payment(folio, amount=Decimal("1000"), method="bank_transfer", actor=owner).cash_shift
            is None
        )
        assert record_payment(folio, amount=Decimal("1000"), method="cash").status == "approved"  # no actor


class TestRecordPayment:
    def test_is_audited(self, folio, owner):
        payment = record_payment(folio, amount=Decimal("80000"), method="card_terminal", actor=owner)
        event = AuditEvent.objects.get(action="finance.payment_recorded")
        assert (event.target_id, event.actor, event.property) == (str(payment.pk), owner, folio.property)

    def test_is_all_or_nothing(self, folio, owner, monkeypatch):
        """API views are not atomic: a payment must never be stored without its audit event."""

        def audit_down(**kwargs):
            raise RuntimeError("audit unavailable")

        monkeypatch.setattr(services.audit, "record", audit_down)
        with pytest.raises(RuntimeError):
            record_payment(folio, amount=Decimal("1000"), method="bank_transfer", actor=owner)
        assert not Payment.objects.exists()

    def test_a_closed_folio_takes_no_payments(self, folio):
        folio.status = "closed"
        folio.save()
        with pytest.raises(DomainError) as exc:
            record_payment(folio, amount=Decimal("1000"), method="bank_transfer")
        assert exc.value.code == "folio_closed"

    def test_unknown_methods_are_rejected(self, folio):
        with pytest.raises(DomainError) as exc:
            record_payment(folio, amount=Decimal("1000"), method="bitcoin")
        assert exc.value.code == "invalid_method"


class TestVoidPayment:
    def test_requires_confirmation_and_reason(self, folio, owner):
        payment = record_payment(folio, amount=Decimal("100000"), method="bank_transfer", actor=owner)
        with pytest.raises(ConfirmationRequired):
            void_payment(payment, reason="Transferencia no llegó", actor=owner, confirm=False)
        with pytest.raises(DomainError) as exc:
            void_payment(payment, reason="", actor=owner, confirm=True)
        assert exc.value.code == "reason_required"

    def test_a_manual_payment_recorded_by_mistake_stops_counting(self, reservation, folio, owner):
        payment = record_payment(folio, amount=Decimal("100000"), method="bank_transfer", actor=owner)
        assert reservation_balance(reservation) == Decimal("600000")

        void_payment(payment, reason="La transferencia no llegó", actor=owner, confirm=True)

        payment.refresh_from_db()
        assert (payment.status, payment.voided_by, payment.void_reason) == (
            "voided",
            owner,
            "La transferencia no llegó",
        )
        assert payment.voided_at is not None
        assert reservation_balance(reservation) == Decimal("700000")
        assert AuditEvent.objects.filter(action="finance.payment_voided", target_id=str(payment.pk)).exists()

    def test_online_payments_are_refunded_not_voided(self, folio, owner):
        payment = PaymentFactory(folio=folio, method="wompi_card", provider="wompi", provider_reference="t-1")
        with pytest.raises(DomainError) as exc:
            void_payment(payment, reason="x", actor=owner, confirm=True)
        assert (exc.value.code, exc.value.status_code) == ("payment_not_voidable", 409)

    def test_refunded_payments_cannot_be_voided(self, folio, owner):
        payment = record_payment(folio, amount=Decimal("100000"), method="bank_transfer", actor=owner)
        refund_payment(payment, amount=Decimal("10000"), reason="Descuento", actor=owner, confirm=True)
        with pytest.raises(DomainError) as exc:
            void_payment(payment, reason="x", actor=owner, confirm=True)
        assert exc.value.code == "payment_not_voidable"
