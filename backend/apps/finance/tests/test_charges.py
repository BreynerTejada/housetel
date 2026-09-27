"""post_charge (audit, sign rules) and void_charge (confirmation, reason, audit, balance)."""

from decimal import Decimal

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.errors import ConfirmationRequired, DomainError
from apps.core.models import AuditEvent
from apps.finance import services
from apps.finance.models import Charge
from apps.finance.services import folio_balance, get_or_create_folio, post_charge, void_charge
from apps.rates.tests.factories import TaxFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def folio(prop):
    reservation = ReservationFactory(property=prop)
    StayFactory(reservation=reservation, total_amount=Decimal("700000"))
    return get_or_create_folio(reservation)


@pytest.fixture
def iva(prop):
    return TaxFactory(property=prop, rate=Decimal("19.00"))


class TestPostCharge:
    def test_is_audited(self, folio, owner):
        charge = post_charge(
            folio, kind="extra", amount=Decimal("35000"), description="Desayuno", quantity=2, actor=owner
        )
        event = AuditEvent.objects.get(action="finance.charge_posted")
        assert (event.target_type, event.target_id, event.actor, event.property) == (
            "finance.charge",
            str(charge.pk),
            owner,
            folio.property,
        )
        assert "Desayuno" in event.summary

    def test_negative_amounts_are_only_for_adjustments(self, folio, iva):
        with pytest.raises(DomainError) as exc:
            post_charge(folio, kind="extra", amount=Decimal("-1000"), description="x")
        assert exc.value.code == "invalid_amount"

        credit = post_charge(
            folio, kind="adjustment", amount=Decimal("-50000"), description="Cortesía", tax=iva
        )
        assert (credit.amount, credit.tax_amount, credit.total) == (
            Decimal("-50000"),
            Decimal("-9500"),
            Decimal("-59500"),
        )

    def test_a_closed_folio_is_a_conflict(self, folio):
        folio.status = "closed"
        folio.save()
        with pytest.raises(DomainError) as exc:
            post_charge(folio, kind="extra", amount=Decimal("1000"), description="x")
        assert (exc.value.code, exc.value.status_code) == ("folio_closed", 409)

    def test_is_all_or_nothing(self, folio, monkeypatch):
        """API views are not atomic: a charge must never be stored without its audit event."""

        def audit_down(**kwargs):
            raise RuntimeError("audit unavailable")

        monkeypatch.setattr(services.audit, "record", audit_down)
        with pytest.raises(RuntimeError):
            post_charge(folio, kind="extra", amount=Decimal("1000"), description="x")
        assert not Charge.objects.exists()


class TestVoidCharge:
    def test_requires_explicit_confirmation(self, folio, owner):
        charge = post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar")
        with pytest.raises(ConfirmationRequired):
            void_charge(charge, reason="Error de digitación", actor=owner, confirm=False)
        charge.refresh_from_db()
        assert charge.voided_at is None

    def test_requires_a_reason(self, folio, owner):
        charge = post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar")
        with pytest.raises(DomainError) as exc:
            void_charge(charge, reason="   ", actor=owner, confirm=True)
        assert exc.value.code == "reason_required"

    def test_voids_audits_and_leaves_the_balance(self, folio, owner, iva):
        kept = post_charge(folio, kind="extra", amount=Decimal("100000"), description="Tour", tax=iva)
        charge = post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar", tax=iva)
        assert folio_balance(folio) == Decimal("178500")  # 119000 + 59500

        result = void_charge(charge, reason="Cargado a la habitación equivocada", actor=owner, confirm=True)

        charge.refresh_from_db()
        assert result.pk == charge.pk and charge.is_voided
        assert (charge.voided_by, charge.void_reason) == (owner, "Cargado a la habitación equivocada")
        assert folio_balance(folio) == kept.total == Decimal("119000")
        event = AuditEvent.objects.get(action="finance.charge_voided")
        assert (event.target_id, event.actor) == (str(charge.pk), owner)
        assert event.changes["reason"] == "Cargado a la habitación equivocada"

    def test_cannot_void_twice(self, folio, owner):
        charge = post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar")
        void_charge(charge, reason="Duplicado", actor=owner, confirm=True)
        with pytest.raises(DomainError) as exc:
            void_charge(charge, reason="Otra vez", actor=owner, confirm=True)
        assert (exc.value.code, exc.value.status_code) == ("already_voided", 409)

    def test_charges_of_a_closed_folio_cannot_be_voided(self, folio, owner):
        charge = post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar")
        folio.status = "closed"
        folio.save()
        with pytest.raises(DomainError) as exc:
            void_charge(charge, reason="Error", actor=owner, confirm=True)
        assert exc.value.code == "folio_closed"
