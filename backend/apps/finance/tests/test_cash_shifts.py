"""Cash shifts: open, totals (expected vs counted), close with optional denomination count."""

from decimal import Decimal

import pytest

from apps.bookings.tests.factories import ReservationFactory
from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.finance.cash import cash_shift_totals, close_cash_shift, current_cash_shift, open_cash_shift
from apps.finance.services import get_or_create_folio, record_payment, refund_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def folio(prop):
    return get_or_create_folio(ReservationFactory(property=prop))


@pytest.fixture
def shift(prop, owner):
    return open_cash_shift(prop, owner, opening_float=Decimal("200000"), notes="Turno mañana")


class TestOpen:
    def test_opens_a_shift_for_the_user(self, prop, owner, shift):
        assert (shift.property, shift.user, shift.opening_float, shift.notes) == (
            prop,
            owner,
            Decimal("200000"),
            "Turno mañana",
        )
        assert shift.closed_at is None and current_cash_shift(prop, owner) == shift
        assert AuditEvent.objects.filter(action="finance.cash_shift_opened", target_id=str(shift.pk)).exists()

    def test_only_one_open_shift_per_user(self, prop, owner, shift):
        with pytest.raises(DomainError) as exc:
            open_cash_shift(prop, owner, opening_float=Decimal("0"))
        assert (exc.value.code, exc.value.status_code) == ("cash_shift_open", 409)

    def test_the_opening_float_cannot_be_negative(self, prop, owner):
        with pytest.raises(DomainError) as exc:
            open_cash_shift(prop, owner, opening_float=Decimal("-1"))
        assert exc.value.code == "invalid_amount"


class TestTotals:
    def test_expected_cash_is_float_plus_cash_in_minus_cash_refunds(self, folio, owner, shift):
        cash = record_payment(folio, amount=Decimal("150000"), method="cash", actor=owner)
        record_payment(folio, amount=Decimal("80000"), method="card_terminal", actor=owner)
        record_payment(folio, amount=Decimal("5000"), method="cash", actor=owner, status="declined")
        refund_payment(cash, amount=Decimal("20000"), reason="Descuento", actor=owner, confirm=True)

        totals = cash_shift_totals(shift)

        assert totals["opening_float"] == Decimal("200000")
        assert totals["cash_payments"] == Decimal("150000")
        assert totals["cash_refunds"] == Decimal("20000")
        assert totals["expected_cash"] == Decimal("330000")
        assert totals["by_method"] == {"cash": Decimal("150000"), "card_terminal": Decimal("80000")}
        assert totals["payments_count"] == 2


class TestClose:
    def test_close_computes_the_difference(self, folio, owner, shift):
        record_payment(folio, amount=Decimal("150000"), method="cash", actor=owner)

        closed = close_cash_shift(shift, counted_cash=Decimal("345000"), actor=owner, notes="Faltan 5.000")

        assert (closed.expected_cash, closed.counted_cash, closed.difference) == (
            Decimal("350000"),
            Decimal("345000"),
            Decimal("-5000"),
        )
        assert closed.closed_at is not None and closed.closed_by == owner
        assert closed.notes == "Turno mañana\nFaltan 5.000"
        event = AuditEvent.objects.get(action="finance.cash_shift_closed")
        assert event.changes["difference"] == "-5000.00"

    def test_counting_by_denomination(self, owner, shift):
        closed = close_cash_shift(shift, actor=owner, denominations={"100000": 1, "50000": 2, "500": 3})
        assert closed.counted_cash == Decimal("201500")
        assert closed.denominations == {"100000": 1, "50000": 2, "500": 3}
        assert closed.difference == Decimal("1500")

    def test_denominations_must_match_the_counted_total(self, owner, shift):
        with pytest.raises(DomainError) as exc:
            close_cash_shift(shift, counted_cash=Decimal("1000"), actor=owner, denominations={"2000": 1})
        assert exc.value.code == "denominations_mismatch"

    def test_a_count_is_required(self, owner, shift):
        with pytest.raises(DomainError) as exc:
            close_cash_shift(shift, actor=owner)
        assert exc.value.code == "counted_cash_required"

    def test_cannot_close_twice_and_later_cash_needs_a_new_shift(self, folio, prop, owner, shift):
        close_cash_shift(shift, counted_cash=Decimal("200000"), actor=owner)
        with pytest.raises(DomainError) as exc:
            close_cash_shift(shift, counted_cash=Decimal("200000"), actor=owner)
        assert exc.value.code == "cash_shift_closed"
        assert current_cash_shift(prop, owner) is None
        with pytest.raises(DomainError):
            record_payment(folio, amount=Decimal("1000"), method="cash", actor=owner)
