"""create_payment_intent / sync_payment_intent: links, active verification, idempotency, edge cases."""

import re
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import respx
from django.utils import timezone
from freezegun import freeze_time

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core import integrations
from apps.core.errors import DomainError
from apps.core.models import Alert, AuditEvent
from apps.core.signals import payment_received
from apps.finance.models import Folio, Payment, PaymentIntent
from apps.finance.services import (
    create_payment_intent,
    decide_simulated_intent,
    get_or_create_folio,
    refund_payment,
    reservation_balance,
    sync_payment_intent,
)
from apps.finance.tests.test_providers import wompi_tx
from apps.finance.tests.test_wompi import EVENTS_SECRET

pytestmark = pytest.mark.django_db

API = "https://sandbox.wompi.co/v1"


@pytest.fixture
def reservation(prop):
    reservation = ReservationFactory(property=prop, code="HT-7K2M9Q")
    StayFactory(reservation=reservation, total_amount=Decimal("700000"))
    return reservation


@pytest.fixture
def folio(reservation):
    return get_or_create_folio(reservation)


@pytest.fixture
def real_mode(prop):
    setting = integrations.get_setting(prop, "payments")
    setting.mode = "real"
    setting.config = {"environment": "sandbox", "public_key": "pub_test_abc"}
    setting.save()
    integrations.set_secrets(
        setting,
        {"private_key": "prv_test_xyz", "integrity_secret": "test_integrity", "events_secret": EVENTS_SECRET},
    )
    return setting


@pytest.fixture
def received():
    payments = []

    def receiver(sender, **kwargs):
        payments.append(kwargs["payment"])

    payment_received.connect(receiver, weak=False, dispatch_uid="test-intents")
    yield payments
    payment_received.disconnect(dispatch_uid="test-intents")


def decide(intent, outcome, *, method="wompi_card", transaction_id="SIM-TX-1"):
    intent.refresh_from_db()
    intent.payload = {
        **intent.payload,
        "simulation": {"outcome": outcome, "method": method, "transaction_id": transaction_id},
    }
    intent.save(update_fields=["payload", "updated_at"])


class TestCreate:
    @freeze_time("2026-09-25 20:00:00")
    def test_creates_a_simulated_payment_link(self, folio, settings):
        settings.FRONTEND_URL = "http://front.test"

        intent = create_payment_intent(
            folio, amount=Decimal("250000.4"), return_url="http://front.test/g/token?paid=1"
        )

        assert re.fullmatch(r"HT-7K2M9Q-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}", intent.reference)
        assert (intent.property, intent.folio, intent.amount, intent.currency) == (
            folio.property,
            folio,
            Decimal("250000"),
            "COP",
        )
        assert (intent.provider, intent.mode, intent.status) == ("simulated", "simulated", "created")
        assert intent.checkout_url == f"http://front.test/sim/pay/{intent.reference}"
        assert intent.return_url == "http://front.test/g/token?paid=1"
        assert intent.expires_at == timezone.now() + timedelta(hours=24)
        event = AuditEvent.objects.get(action="finance.payment_intent_created")
        assert event.target_id == str(intent.pk)

    @freeze_time("2026-09-25 20:00:00")
    def test_the_link_lifetime_is_configurable(self, folio, prop):
        prop.settings = {"payment_link_hours": 2}
        prop.save()
        folio.refresh_from_db()
        intent = create_payment_intent(folio, amount=Decimal("1000"), return_url="")
        assert intent.expires_at == timezone.now() + timedelta(hours=2)

    @freeze_time("2026-09-25 20:00:00")
    def test_a_tentative_reservation_link_ends_with_its_hold(self, reservation, folio):
        """After the hold the booking is cancelled: paying later would charge a cancelled reservation."""
        reservation.status = "tentative"
        reservation.hold_expires_at = timezone.now() + timedelta(minutes=20)
        reservation.save()
        intent = create_payment_intent(folio, amount=Decimal("1000"), return_url="")
        assert intent.expires_at == timezone.now() + timedelta(minutes=20)

    @freeze_time("2026-09-25 20:00:00")
    def test_a_hold_longer_than_the_link_lifetime_keeps_the_lifetime(self, reservation, folio):
        reservation.status = "tentative"
        reservation.hold_expires_at = timezone.now() + timedelta(hours=48)
        reservation.save()
        intent = create_payment_intent(folio, amount=Decimal("1000"), return_url="")
        assert intent.expires_at == timezone.now() + timedelta(hours=24)

    def test_rejects_bad_amounts_and_closed_folios(self, folio):
        with pytest.raises(DomainError) as exc:
            create_payment_intent(folio, amount=Decimal("0"), return_url="")
        assert exc.value.code == "invalid_amount"
        folio.status = Folio.Status.CLOSED
        folio.save()
        with pytest.raises(DomainError) as exc:
            create_payment_intent(folio, amount=Decimal("1000"), return_url="")
        assert exc.value.code == "folio_closed"

    def test_disabled_online_payments(self, folio, prop):
        setting = integrations.get_setting(prop, "payments")
        setting.enabled = False
        setting.save()
        with pytest.raises(DomainError) as exc:
            create_payment_intent(folio, amount=Decimal("1000"), return_url="")
        assert (exc.value.code, exc.value.status_code) == ("online_payments_disabled", 409)
        assert not PaymentIntent.objects.exists()

    def test_real_mode_without_keys_creates_nothing(self, folio, real_mode):
        integrations.set_secrets(real_mode, {"integrity_secret": None})
        with pytest.raises(DomainError) as exc:
            create_payment_intent(folio, amount=Decimal("1000"), return_url="")
        assert exc.value.code == "integration_misconfigured"
        assert not PaymentIntent.objects.exists()

    def test_real_mode_builds_a_wompi_checkout(self, folio, real_mode):
        intent = create_payment_intent(folio, amount=Decimal("150000"), return_url="http://front.test/r")
        assert (intent.provider, intent.mode) == ("wompi", "real")
        assert intent.checkout_url.startswith("https://checkout.wompi.co/p/?public-key=pub_test_abc")


class TestSyncSimulated:
    def test_no_decision_yet_changes_nothing(self, folio):
        intent = create_payment_intent(folio, amount=Decimal("100000"), return_url="")
        synced = sync_payment_intent(intent)
        assert synced.status == "created" and synced.last_checked_at is not None
        assert not Payment.objects.exists()

    def test_an_approval_creates_exactly_one_payment(
        self, reservation, folio, received, django_capture_on_commit_callbacks
    ):
        intent = create_payment_intent(folio, amount=Decimal("300000"), return_url="")
        decide(intent, "approved", method="wompi_nequi")

        with django_capture_on_commit_callbacks(execute=True):
            synced = sync_payment_intent(intent)
        with django_capture_on_commit_callbacks(execute=True):
            sync_payment_intent(intent)
            sync_payment_intent(intent)

        payment = Payment.objects.get()
        assert (
            payment.amount,
            payment.method,
            payment.status,
            payment.provider,
            payment.provider_reference,
        ) == (
            Decimal("300000"),
            "wompi_nequi",
            "approved",
            "simulated",
            "SIM-TX-1",
        )
        assert payment.intent == synced and payment.folio == folio
        assert (synced.status, synced.method, synced.provider_transaction_id) == (
            "approved",
            "wompi_nequi",
            "SIM-TX-1",
        )
        assert received == [payment]
        assert reservation_balance(reservation) == Decimal("400000")

    def test_a_declined_link_can_still_be_paid_on_a_retry(self, folio):
        intent = create_payment_intent(folio, amount=Decimal("100000"), return_url="")
        decide(intent, "declined")
        assert sync_payment_intent(intent).status == "declined"
        assert not Payment.objects.exists()

        decide(intent, "approved", transaction_id="SIM-TX-2")
        assert sync_payment_intent(intent).status == "approved"
        assert Payment.objects.get().provider_reference == "SIM-TX-2"

    def test_an_expired_decision_expires_the_link(self, folio):
        intent = create_payment_intent(folio, amount=Decimal("100000"), return_url="")
        decide(intent, "expired")
        assert sync_payment_intent(intent).status == "expired"
        assert not Payment.objects.exists()

    def test_money_received_after_expiry_is_still_recorded(self, folio):
        intent = create_payment_intent(folio, amount=Decimal("100000"), return_url="")
        PaymentIntent.objects.filter(pk=intent.pk).update(status="expired")
        decide(intent, "approved")
        assert sync_payment_intent(intent).status == "approved"
        assert Payment.objects.count() == 1

    def test_a_link_paid_after_the_folio_closed_reopens_it(self, folio):
        intent = create_payment_intent(folio, amount=Decimal("100000"), return_url="")
        Folio.objects.filter(pk=folio.pk).update(status="closed", closed_at=timezone.now())
        decide(intent, "approved")

        sync_payment_intent(intent)

        folio.refresh_from_db()
        assert (folio.status, folio.closed_at) == ("open", None)
        assert Payment.objects.filter(folio=folio, status="approved").count() == 1
        assert Alert.objects.filter(kind="payment_on_closed_folio", resolved_at__isnull=True).exists()

    def test_intents_keep_the_mode_they_were_created_with(self, folio, real_mode):
        real_mode.mode = "simulated"
        real_mode.save()
        intent = create_payment_intent(folio, amount=Decimal("100000"), return_url="")
        real_mode.mode = "real"
        real_mode.save()
        decide(intent, "approved")
        assert sync_payment_intent(intent).status == "approved"  # verified with the simulated provider

    def test_a_hotel_taking_real_payments_refuses_simulated_decisions(self, folio, real_mode):
        """Defense in depth for any caller of the service (the public page already answers 404)."""
        real_mode.mode = "simulated"
        real_mode.save()
        intent = create_payment_intent(folio, amount=Decimal("100000"), return_url="")
        real_mode.mode = "real"
        real_mode.save()

        with pytest.raises(DomainError) as exc:
            decide_simulated_intent(intent, outcome="approved", method="card")

        assert (exc.value.code, exc.value.status_code) == ("simulation_disabled", 409)
        assert not Payment.objects.exists()
        intent.refresh_from_db()
        assert intent.status == "created" and "simulation" not in intent.payload


class TestSyncWompi:
    @pytest.fixture
    def intent(self, folio, real_mode):
        return create_payment_intent(folio, amount=Decimal("150000"), return_url="http://front.test/r")

    @respx.mock
    def test_repeated_verifications_record_one_payment(self, intent):
        search = respx.get(f"{API}/transactions").mock(
            return_value=httpx.Response(200, json={"data": [wompi_tx(reference=intent.reference)]})
        )
        by_id = respx.get(f"{API}/transactions/1234-1610641025-49201").mock(
            return_value=httpx.Response(200, json={"data": wompi_tx(reference=intent.reference)})
        )
        for _ in range(3):
            sync_payment_intent(intent)
        assert (search.call_count, by_id.call_count) == (1, 2)  # the id is used once known
        payment = Payment.objects.get()
        assert (payment.provider, payment.provider_reference, payment.method, payment.amount) == (
            "wompi",
            "1234-1610641025-49201",
            "wompi_card",
            Decimal("150000"),
        )
        intent.refresh_from_db()
        assert intent.status == "approved" and intent.provider_transaction_id == "1234-1610641025-49201"

    @respx.mock
    def test_pending_transactions_mark_the_link_pending(self, intent):
        respx.get(f"{API}/transactions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [
                        wompi_tx(reference=intent.reference, status="PENDING", payment_method_type="PSE")
                    ]
                },
            )
        )
        synced = sync_payment_intent(intent)
        assert (synced.status, synced.method) == ("pending", "wompi_pse")

    @respx.mock
    def test_the_paid_amount_wins_and_a_mismatch_raises_an_alert(self, intent):
        respx.get(f"{API}/transactions").mock(
            return_value=httpx.Response(
                200, json={"data": [wompi_tx(reference=intent.reference, amount_in_cents=10000000)]}
            )
        )
        sync_payment_intent(intent)
        assert Payment.objects.get().amount == Decimal("100000")
        assert Alert.objects.filter(kind="payment_amount_mismatch").exists()

    @respx.mock
    def test_provider_errors_leave_the_link_untouched(self, intent):
        respx.get(f"{API}/transactions").mock(return_value=httpx.Response(500))
        synced = sync_payment_intent(intent)
        assert synced.status == "created" and "500" in synced.status_message
        assert synced.last_checked_at is not None

    @respx.mock
    def test_a_card_payment_voided_at_wompi_stops_counting(self, intent):
        route = respx.get(f"{API}/transactions/1234-1610641025-49201")
        respx.get(f"{API}/transactions").mock(
            return_value=httpx.Response(200, json={"data": [wompi_tx(reference=intent.reference)]})
        )
        sync_payment_intent(intent)
        route.mock(
            return_value=httpx.Response(
                200, json={"data": wompi_tx(reference=intent.reference, status="VOIDED")}
            )
        )

        synced = sync_payment_intent(intent)

        assert synced.status == "approved"
        assert Payment.objects.get().status == "voided"

    @respx.mock
    def test_a_void_that_matches_our_refund_keeps_the_payment(self, intent, owner):
        respx.get(f"{API}/transactions").mock(
            return_value=httpx.Response(200, json={"data": [wompi_tx(reference=intent.reference)]})
        )
        respx.post(f"{API}/transactions/1234-1610641025-49201/void").mock(
            return_value=httpx.Response(201, json={"data": {}})
        )
        sync_payment_intent(intent)
        payment = Payment.objects.get()
        refund_payment(payment, amount=Decimal("150000"), reason="Cancelación", actor=owner, confirm=True)
        respx.get(f"{API}/transactions/1234-1610641025-49201").mock(
            return_value=httpx.Response(
                200, json={"data": wompi_tx(reference=intent.reference, status="VOIDED")}
            )
        )

        sync_payment_intent(intent)

        payment.refresh_from_db()
        assert payment.status == "approved" and payment.refunds.get().status == "approved"
