"""refund_payment for manual payments (limits, confirmation, cash shift) and completing pending refunds."""

from decimal import Decimal

import httpx
import pytest
import respx
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.errors import ConfirmationRequired, DomainError
from apps.core.models import Alert, AuditEvent
from apps.finance.cash import cash_shift_totals, open_cash_shift
from apps.finance.models import Folio, Refund
from apps.finance.services import (
    complete_refund,
    get_or_create_folio,
    record_payment,
    refund_payment,
    refundable_amount,
    reservation_balance,
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


@pytest.fixture
def transfer(folio, owner):
    return record_payment(folio, amount=Decimal("100000"), method="bank_transfer", actor=owner)


class TestGuards:
    def test_requires_explicit_confirmation(self, transfer, owner):
        with pytest.raises(ConfirmationRequired):
            refund_payment(transfer, amount=Decimal("1000"), reason="x", actor=owner, confirm=False)
        assert not Refund.objects.exists()

    def test_requires_a_reason_and_a_positive_amount(self, transfer, owner):
        with pytest.raises(DomainError) as exc:
            refund_payment(transfer, amount=Decimal("1000"), reason=" ", actor=owner, confirm=True)
        assert exc.value.code == "reason_required"
        with pytest.raises(DomainError) as exc:
            refund_payment(transfer, amount=Decimal("0"), reason="x", actor=owner, confirm=True)
        assert exc.value.code == "invalid_amount"

    @pytest.mark.parametrize("status", ["declined", "voided", "pending", "error"])
    def test_only_approved_payments_can_be_refunded(self, folio, owner, status):
        payment = PaymentFactory(folio=folio, method="bank_transfer", status=status)
        with pytest.raises(DomainError) as exc:
            refund_payment(payment, amount=Decimal("1000"), reason="x", actor=owner, confirm=True)
        assert (exc.value.code, exc.value.status_code) == ("payment_not_refundable", 409)

    def test_cannot_refund_more_than_what_is_left(self, transfer, owner):
        refund_payment(transfer, amount=Decimal("60000"), reason="Parcial", actor=owner, confirm=True)
        with pytest.raises(DomainError) as exc:
            refund_payment(transfer, amount=Decimal("50000"), reason="Otra", actor=owner, confirm=True)
        assert (exc.value.code, exc.value.status_code) == ("refund_exceeds_payment", 400)
        assert exc.value.extra["refundable"] == Decimal("40000")
        refund_payment(transfer, amount=Decimal("40000"), reason="Resto", actor=owner, confirm=True)
        with pytest.raises(DomainError):
            refund_payment(transfer, amount=Decimal("1"), reason="Más", actor=owner, confirm=True)

    def test_a_closed_folio_takes_no_refunds(self, folio, transfer, owner):
        """A closed folio is read-only: a refund would leave it closed while the guest owes money."""
        Folio.objects.filter(pk=folio.pk).update(status="closed", closed_at=timezone.now())
        with pytest.raises(DomainError) as exc:
            refund_payment(transfer, amount=Decimal("1000"), reason="x", actor=owner, confirm=True)
        assert (exc.value.code, exc.value.status_code) == ("folio_closed", 409)
        assert not Refund.objects.exists()

    def test_pending_refunds_count_against_the_limit(self, folio, owner):
        payment = PaymentFactory(
            folio=folio, method="ota_collect", provider="manual", amount=Decimal("100000")
        )
        refund_payment(payment, amount=Decimal("70000"), reason="OTA", actor=owner, confirm=True)
        with pytest.raises(DomainError) as exc:
            refund_payment(payment, amount=Decimal("40000"), reason="OTA", actor=owner, confirm=True)
        assert exc.value.code == "refund_exceeds_payment"


class TestManualRefunds:
    def test_are_approved_at_once_and_raise_the_balance(self, reservation, transfer, owner):
        assert reservation_balance(reservation) == Decimal("600000")

        refund = refund_payment(
            transfer, amount=Decimal("30000"), reason="Descuento", actor=owner, confirm=True
        )

        assert (refund.status, refund.amount, refund.reason) == ("approved", Decimal("30000"), "Descuento")
        assert (refund.requested_by, refund.approved_by) == (owner, owner)
        assert refund.business_date == reservation.property.business_date
        assert refund.completed_at is not None
        assert reservation_balance(reservation) == Decimal("630000")
        event = AuditEvent.objects.get(action="finance.payment_refunded")
        assert (event.target_id, event.actor) == (str(refund.pk), owner)

    def test_cash_refunds_come_out_of_the_actors_shift(self, folio, owner, prop):
        shift = open_cash_shift(prop, owner, opening_float=Decimal("0"))
        cash = record_payment(folio, amount=Decimal("100000"), method="cash", actor=owner)
        refund = refund_payment(cash, amount=Decimal("10000"), reason="Vuelto", actor=owner, confirm=True)
        assert refund.cash_shift == shift

    def test_card_terminal_refunds_are_shift_movements_but_leave_the_drawer_alone(self, folio, owner, prop):
        """Reconciling the card terminal's closing report needs the refunds done on it during the shift."""
        shift = open_cash_shift(prop, owner, opening_float=Decimal("100000"))
        card = record_payment(
            folio, amount=Decimal("200000"), method="card_terminal", reference="V-1", actor=owner
        )
        refund = refund_payment(card, amount=Decimal("20000"), reason="Descuento", actor=owner, confirm=True)
        assert refund.cash_shift == shift
        totals = cash_shift_totals(shift)
        assert (totals["expected_cash"], totals["cash_refunds"], totals["refunds_count"]) == (
            Decimal("100000"),
            Decimal("0"),
            1,
        )

    def test_online_refunds_are_not_shift_movements(self, folio, owner, prop):
        open_cash_shift(prop, owner, opening_float=Decimal("0"))
        online = PaymentFactory(
            folio=folio, provider="simulated", method="wompi_card", provider_reference="S-9"
        )
        refund = refund_payment(
            online, amount=Decimal("10000"), reason="Descuento", actor=owner, confirm=True
        )
        assert refund.cash_shift is None

    def test_cash_refunds_need_an_open_shift(self, folio, owner, prop):
        prop.settings = {"require_cash_shift": False}
        prop.save()
        folio.refresh_from_db()
        cash = record_payment(folio, amount=Decimal("100000"), method="cash", actor=owner)
        prop.settings = {}
        prop.save()
        cash.refresh_from_db()
        with pytest.raises(DomainError) as exc:
            refund_payment(cash, amount=Decimal("10000"), reason="Vuelto", actor=owner, confirm=True)
        assert exc.value.code == "cash_shift_required"

    def test_ota_collected_payments_wait_for_a_manual_refund(self, folio, owner):
        payment = PaymentFactory(
            folio=folio, method="ota_collect", provider="manual", amount=Decimal("100000")
        )

        refund = refund_payment(
            payment, amount=Decimal("100000"), reason="Cancelada", actor=owner, confirm=True
        )

        assert refund.status == "pending" and refund.approved_by is None and refund.completed_at is None
        assert "OTA" in refund.instructions
        alert = Alert.objects.get(dedupe_key=f"refund:{refund.pk}")
        assert alert.resolved_at is None and alert.kind == "refund_pending"


class TestCompleteRefund:
    @pytest.fixture
    def pending(self, folio, owner):
        payment = PaymentFactory(
            folio=folio, method="ota_collect", provider="manual", amount=Decimal("90000")
        )
        return refund_payment(payment, amount=Decimal("90000"), reason="Cancelada", actor=owner, confirm=True)

    def test_marks_it_done_and_resolves_the_alert(self, reservation, pending, owner):
        before = reservation_balance(reservation)

        refund = complete_refund(pending, actor=owner, confirm=True, reference="TRF-778")

        assert (refund.status, refund.approved_by, refund.provider_reference) == (
            "approved",
            owner,
            "TRF-778",
        )
        assert refund.completed_at is not None
        assert reservation_balance(reservation) == before + Decimal("90000")
        assert Alert.objects.get(dedupe_key=f"refund:{refund.pk}").resolved_at is not None

    def test_can_record_a_failure(self, pending, owner):
        refund = complete_refund(pending, actor=owner, confirm=True, outcome="failed")
        assert refund.status == "failed"

    def test_requires_confirmation_and_a_pending_refund(self, pending, owner):
        with pytest.raises(ConfirmationRequired):
            complete_refund(pending, actor=owner, confirm=False)
        complete_refund(pending, actor=owner, confirm=True)
        with pytest.raises(DomainError) as exc:
            complete_refund(pending, actor=owner, confirm=True)
        assert (exc.value.code, exc.value.status_code) == ("refund_not_pending", 409)


class TestProviderRefunds:
    API = "https://sandbox.wompi.co/v1"

    @pytest.fixture
    def real_mode(self, prop):
        from apps.core import integrations

        setting = integrations.get_setting(prop, "payments")
        setting.mode = "real"
        setting.config = {"environment": "sandbox", "public_key": "pub_test_abc"}
        setting.save()
        integrations.set_secrets(setting, {"private_key": "prv_test_xyz", "integrity_secret": "s"})
        return setting

    def test_simulated_payments_are_refunded_by_the_simulated_gateway(self, folio, owner):
        payment = PaymentFactory(
            folio=folio, provider="simulated", method="wompi_card", provider_reference="S-1"
        )
        refund = refund_payment(
            payment, amount=Decimal("20000"), reason="Descuento", actor=owner, confirm=True
        )
        assert refund.status == "approved" and refund.provider_reference.startswith("SIMREF-")
        assert refund.approved_by == owner

    @respx.mock
    def test_wompi_card_payments_are_voided(self, folio, owner, real_mode):
        payment = PaymentFactory(
            folio=folio, provider="wompi", method="wompi_card", provider_reference="1234-1-1"
        )
        respx.post(f"{self.API}/transactions/1234-1-1/void").mock(
            return_value=httpx.Response(201, json={"data": {"status": "APPROVED"}})
        )
        refund = refund_payment(
            payment, amount=Decimal("20000"), reason="Descuento", actor=owner, confirm=True
        )
        assert (refund.status, refund.provider_reference) == ("approved", "1234-1-1")

    @respx.mock
    def test_wompi_pse_payments_are_refunded_through_the_refunds_api(
        self, reservation, folio, owner, real_mode
    ):
        payment = record_payment(
            folio,
            amount=Decimal("100000"),
            method="wompi_pse",
            reference="1234-2-2",
            provider="wompi",
        )
        respx.post(f"{self.API}/refunds").mock(
            return_value=httpx.Response(
                201, json={"data": {"id": 7, "status": "APPROVED", "v2_refund_id": "v2_r7"}}
            )
        )
        before = reservation_balance(reservation)
        refund = refund_payment(
            payment, amount=Decimal("20000"), reason="Descuento", actor=owner, confirm=True
        )
        assert (refund.status, refund.provider_reference, refund.approved_by) == ("approved", "v2_r7", owner)
        assert reservation_balance(reservation) == before + Decimal("20000")
        assert not Alert.objects.filter(dedupe_key=f"refund:{refund.pk}").exists()

    @respx.mock
    def test_wompi_pse_payments_without_the_refunds_api_wait_for_a_manual_transfer(
        self, folio, owner, real_mode
    ):
        payment = PaymentFactory(
            folio=folio, provider="wompi", method="wompi_pse", provider_reference="1234-2-2"
        )
        respx.post(f"{self.API}/refunds").mock(return_value=httpx.Response(401, json={}))
        refund = refund_payment(
            payment, amount=Decimal("20000"), reason="Descuento", actor=owner, confirm=True
        )
        assert refund.status == "pending" and "transferencia" in refund.instructions
        assert Alert.objects.get(dedupe_key=f"refund:{refund.pk}").kind == "refund_pending"

    @respx.mock
    def test_a_rejected_void_is_recorded_as_failed_and_frees_the_amount(self, folio, owner, real_mode):
        payment = PaymentFactory(
            folio=folio,
            provider="wompi",
            method="wompi_card",
            provider_reference="1234-1-1",
            amount=Decimal("50000"),
        )
        respx.post(f"{self.API}/transactions/1234-1-1/void").mock(return_value=httpx.Response(422, json={}))
        respx.post(f"{self.API}/refunds").mock(
            return_value=httpx.Response(
                201, json={"data": {"id": 8, "status": "DECLINED", "status_message": "x"}}
            )
        )
        refund = refund_payment(
            payment, amount=Decimal("50000"), reason="Descuento", actor=owner, confirm=True
        )
        assert refund.status == "failed" and refund.completed_at is not None
        assert Alert.objects.get(dedupe_key=f"refund:{refund.pk}").kind == "refund_failed"
        assert refundable_amount(payment) == Decimal("50000")
