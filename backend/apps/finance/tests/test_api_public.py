"""Public API: simulated gateway (show + decide), status polling for return pages, Wompi webhook."""

import hashlib
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest
import respx
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core import integrations
from apps.core.signals import payment_received
from apps.finance.models import Payment, PaymentIntent
from apps.finance.services import create_payment_intent, get_or_create_folio

pytestmark = pytest.mark.django_db

URL = "/api/v1/public/finance/"
API = "https://sandbox.wompi.co/v1"
EVENTS_SECRET = "test_events_s3cr3t"


@pytest.fixture
def reservation(prop):
    prop.name, prop.city, prop.branding = "Hotel Casa Aurora", "Cartagena", {"primary_color": "#B4583B"}
    prop.save()
    reservation = ReservationFactory(property=prop, code="HT-PUB001", booker__first_name="Camila")
    StayFactory(reservation=reservation, total_amount=Decimal("700000"))
    return reservation


@pytest.fixture
def folio(reservation):
    return get_or_create_folio(reservation)


@pytest.fixture
def intent(folio):
    return create_payment_intent(folio, amount=Decimal("350000"), return_url="http://front.test/g/tok?paid=1")


@pytest.fixture
def real_intent(prop, folio):
    setting = integrations.get_setting(prop, "payments")
    setting.mode = "real"
    setting.config = {"environment": "sandbox", "public_key": "pub_test_abc"}
    setting.save()
    integrations.set_secrets(
        setting,
        {"private_key": "prv_test_xyz", "integrity_secret": "integrity", "events_secret": EVENTS_SECRET},
    )
    return create_payment_intent(folio, amount=Decimal("150000"), return_url="http://front.test/r")


class TestSimulatedGateway:
    def test_shows_the_payment_to_the_guest(self, public_api, intent):
        response = public_api.get(f"{URL}sim/intents/{intent.reference}/")
        assert response.status_code == 200
        body = response.json()
        assert (body["reference"], body["amount"], body["currency"], body["status"], body["mode"]) == (
            intent.reference,
            "350000.00",
            "COP",
            "created",
            "simulated",
        )
        assert body["property"] == {
            "name": "Hotel Casa Aurora",
            "slug": intent.property.slug,
            "city": "Cartagena",
            "primary_color": "#B4583B",
            "logo": "",
        }
        assert (body["reservation_code"], body["payer_first_name"]) == ("HT-PUB001", "Camila")
        assert body["return_url"] == f"http://front.test/g/tok?paid=1&payment_ref={intent.reference}"

    def test_real_and_unknown_links_are_not_exposed(self, public_api, real_intent):
        assert public_api.get(f"{URL}sim/intents/{real_intent.reference}/").status_code == 404
        assert public_api.get(f"{URL}sim/intents/NOPE-123/").status_code == 404
        decide = {"outcome": "approved", "method": "card"}
        assert public_api.post(f"{URL}sim/intents/{real_intent.reference}/decide/", decide).status_code == 404

    def test_approving_records_the_payment(self, public_api, intent, django_capture_on_commit_callbacks):
        received = []
        payment_received.connect(
            lambda sender, **kw: received.append(kw["payment"]), weak=False, dispatch_uid="pub"
        )
        try:
            with django_capture_on_commit_callbacks(execute=True):
                response = public_api.post(
                    f"{URL}sim/intents/{intent.reference}/decide/", {"outcome": "approved", "method": "nequi"}
                )
        finally:
            payment_received.disconnect(dispatch_uid="pub")
        assert response.status_code == 200, response.json()
        assert response.json()["status"] == "approved"
        payment = Payment.objects.get()
        assert (payment.method, payment.provider, payment.amount, payment.intent_id) == (
            "wompi_nequi",
            "simulated",
            Decimal("350000"),
            intent.pk,
        )
        assert payment.provider_reference.startswith("SIM-")
        assert received == [payment]

    def test_declined_links_can_be_retried(self, public_api, intent):
        url = f"{URL}sim/intents/{intent.reference}/decide/"
        assert public_api.post(url, {"outcome": "declined", "method": "card"}).json()["status"] == "declined"
        assert not Payment.objects.exists()
        assert public_api.post(url, {"outcome": "approved", "method": "pse"}).json()["status"] == "approved"
        assert Payment.objects.get().method == "wompi_pse"

    def test_expiring_closes_the_link(self, public_api, intent):
        url = f"{URL}sim/intents/{intent.reference}/decide/"
        assert public_api.post(url, {"outcome": "expired", "method": "card"}).json()["status"] == "expired"
        response = public_api.post(url, {"outcome": "approved", "method": "card"})
        assert (response.status_code, response.json()["code"]) == (409, "intent_closed")
        assert not Payment.objects.exists()

    def test_approving_twice_is_idempotent(self, public_api, intent):
        url = f"{URL}sim/intents/{intent.reference}/decide/"
        public_api.post(url, {"outcome": "approved", "method": "card"})
        again = public_api.post(url, {"outcome": "approved", "method": "card"})
        assert (again.status_code, again.json()["status"]) == (200, "approved")
        assert Payment.objects.count() == 1
        change = public_api.post(url, {"outcome": "declined", "method": "card"})
        assert (change.status_code, change.json()["code"]) == (409, "intent_closed")

    def test_stale_links_cannot_be_paid(self, public_api, intent):
        PaymentIntent.objects.filter(pk=intent.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        assert public_api.get(f"{URL}sim/intents/{intent.reference}/").json()["status"] == "expired"
        response = public_api.post(
            f"{URL}sim/intents/{intent.reference}/decide/", {"outcome": "approved", "method": "card"}
        )
        assert (response.status_code, response.json()["code"]) == (409, "intent_closed")
        intent.refresh_from_db()
        assert intent.status == "expired"

    def test_old_simulated_links_stop_working_once_the_hotel_takes_real_payments(
        self, public_api, intent, prop
    ):
        """A live hotel must never record a "payment" that a guest approves on the simulated page."""
        setting = integrations.get_setting(prop, "payments")
        setting.mode = "real"
        setting.save()

        assert public_api.get(f"{URL}sim/intents/{intent.reference}/").status_code == 404
        response = public_api.post(
            f"{URL}sim/intents/{intent.reference}/decide/", {"outcome": "approved", "method": "card"}
        )

        assert response.status_code == 404
        assert not Payment.objects.exists()
        intent.refresh_from_db()
        assert intent.status == "created"

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"outcome": "maybe", "method": "card"}, "outcome"),
            ({"outcome": "approved", "method": "cash"}, "method"),
        ],
    )
    def test_invalid_decisions(self, public_api, intent, payload, field):
        response = public_api.post(f"{URL}sim/intents/{intent.reference}/decide/", payload)
        assert response.status_code == 400 and field in response.json()["fields"]


class TestStatus:
    def test_polling_verifies_the_payment(self, public_api, intent):
        intent.payload = {
            "simulation": {"outcome": "approved", "method": "wompi_card", "transaction_id": "SIM-P"}
        }
        intent.save()
        response = public_api.get(f"{URL}intents/{intent.reference}/status/")
        assert response.status_code == 200
        assert response.json() == {
            "reference": intent.reference,
            "status": "approved",
            "paid": True,
            "amount": "350000.00",
            "currency": "COP",
            "method": "wompi_card",
            "reservation_code": "HT-PUB001",
            "property_slug": intent.property.slug,
        }
        assert Payment.objects.count() == 1

    @respx.mock
    def test_the_transaction_id_from_the_redirect_is_used(self, public_api, real_intent):
        route = respx.get(f"{API}/transactions/1234-1610641025-49201").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "id": "1234-1610641025-49201",
                        "status": "APPROVED",
                        "amount_in_cents": 15000000,
                        "payment_method_type": "CARD",
                        "reference": real_intent.reference,
                    }
                },
            )
        )
        response = public_api.get(
            f"{URL}intents/{real_intent.reference}/status/", {"id": "1234-1610641025-49201"}
        )
        assert response.json()["paid"] is True and route.called
        real_intent.refresh_from_db()
        assert real_intent.provider_transaction_id == "1234-1610641025-49201"

    @respx.mock
    def test_a_bogus_transaction_id_in_the_redirect_does_not_hide_the_payment(self, public_api, real_intent):
        respx.get(f"{API}/transactions/1-000-bogus").mock(
            return_value=httpx.Response(404, json={"error": {"type": "NOT_FOUND_ERROR"}})
        )
        respx.get(f"{API}/transactions").mock(
            return_value=httpx.Response(
                200, json={"data": [signed_event(real_intent.reference)["data"]["transaction"]]}
            )
        )
        response = public_api.get(f"{URL}intents/{real_intent.reference}/status/", {"id": "1-000-bogus"})
        assert response.json()["paid"] is True
        real_intent.refresh_from_db()
        assert real_intent.provider_transaction_id == "1234-1610641025-49201"

    def test_unknown_references(self, public_api):
        assert public_api.get(f"{URL}intents/NOPE/status/").status_code == 404


def signed_event(reference, *, status="APPROVED", tx_id="1234-1610641025-49201", secret=EVENTS_SECRET):
    timestamp = 1758844800
    raw = f"{tx_id}{status}15000000{timestamp}{secret}"
    return {
        "event": "transaction.updated",
        "data": {
            "transaction": {
                "id": tx_id,
                "amount_in_cents": 15000000,
                "reference": reference,
                "currency": "COP",
                "payment_method_type": "CARD",
                "status": status,
            }
        },
        "environment": "test",
        "signature": {
            "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"],
            "checksum": hashlib.sha256(raw.encode()).hexdigest().upper(),
        },
        "timestamp": timestamp,
        "sent_at": "2026-09-26T00:00:00.000Z",
    }


class TestWompiWebhook:
    @respx.mock
    def test_repeated_signed_events_record_one_payment(self, public_api, real_intent):
        route = respx.get(f"{API}/transactions/1234-1610641025-49201").mock(
            return_value=httpx.Response(
                200, json={"data": signed_event(real_intent.reference)["data"]["transaction"]}
            )
        )
        event = signed_event(real_intent.reference)
        for _ in range(3):
            response = public_api.post(f"{URL}webhooks/wompi/", event, format="json")
            assert response.status_code == 200
        assert route.call_count == 3  # verified actively each time
        payment = Payment.objects.get()
        assert (payment.provider, payment.provider_reference, payment.intent_id) == (
            "wompi",
            "1234-1610641025-49201",
            real_intent.pk,
        )

    def test_forged_events_are_rejected(self, public_api, real_intent):
        event = signed_event(real_intent.reference, secret="not-the-secret")
        response = public_api.post(f"{URL}webhooks/wompi/", event, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "invalid_signature")
        assert not Payment.objects.exists()

    def test_events_that_are_not_ours_are_acknowledged(self, public_api):
        response = public_api.post(f"{URL}webhooks/wompi/", signed_event("SOMEONE-ELSE"), format="json")
        assert response.status_code == 200 and response.json()["ignored"] is True

    @pytest.mark.parametrize(
        ("body", "fmt"),
        [
            ({"event": "transaction.updated", "data": "not-an-object"}, "json"),
            ({"event": "transaction.updated", "data": {"transaction": ["x"]}}, "json"),
            ({"data": "x"}, "multipart"),
        ],
    )
    def test_malformed_bodies_are_acknowledged_without_crashing(self, public_api, body, fmt):
        response = public_api.post(f"{URL}webhooks/wompi/", body, format=fmt)
        assert response.status_code == 200 and response.json()["ignored"] is True
