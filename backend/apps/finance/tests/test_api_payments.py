"""Staff API: manual payments, voids, refunds (and completing pending ones), payment links and intents."""

from decimal import Decimal

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.models import Alert
from apps.finance.models import Payment, PaymentIntent
from apps.finance.services import create_payment_intent, get_or_create_folio, record_payment
from apps.finance.tests.factories import PaymentFactory
from apps.messaging import services as messaging
from apps.messaging.types import OutboundMessage

pytestmark = pytest.mark.django_db

URL = "/api/v1/finance/"


@pytest.fixture
def reservation(prop):
    reservation = ReservationFactory(property=prop, code="HT-PAY001")
    StayFactory(reservation=reservation, total_amount=Decimal("700000"))
    return reservation


@pytest.fixture
def folio(reservation):
    return get_or_create_folio(reservation)


class TestRecordPayment:
    def test_records_a_card_terminal_payment(self, api, folio, owner):
        payload = {
            "amount": "200000",
            "method": "card_terminal",
            "reference": "VOUCHER-1",
            "notes": "Visa 4242",
        }
        response = api.post(f"{URL}folios/{folio.pk}/payments/", payload)
        assert response.status_code == 201, response.json()
        body = response.json()
        assert (
            body["amount"],
            body["method"],
            body["status"],
            body["provider"],
            body["provider_reference"],
        ) == (
            "200000.00",
            "card_terminal",
            "approved",
            "manual",
            "VOUCHER-1",
        )
        assert (body["notes"], body["received_by"]["id"]) == ("Visa 4242", str(owner.pk))

    def test_cash_needs_an_open_shift(self, api, folio):
        response = api.post(f"{URL}folios/{folio.pk}/payments/", {"amount": "1000", "method": "cash"})
        assert (response.status_code, response.json()["code"]) == (409, "cash_shift_required")

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"amount": "1000", "method": "wompi_card"}, "method"),
            ({"amount": "0", "method": "bank_transfer"}, "amount"),
            ({"method": "bank_transfer"}, "amount"),
        ],
    )
    def test_invalid_payments(self, api, folio, payload, field):
        response = api.post(f"{URL}folios/{folio.pk}/payments/", payload)
        assert response.status_code == 400 and field in response.json()["fields"]


class TestVoidPayment:
    def test_voids_a_manual_payment_with_confirmation(self, api, folio, owner):
        payment = record_payment(folio, amount=Decimal("50000"), method="bank_transfer", actor=owner)
        assert api.post(f"{URL}payments/{payment.pk}/void/", {"reason": "No llegó"}).status_code == 400
        response = api.post(f"{URL}payments/{payment.pk}/void/", {"reason": "No llegó", "confirm": True})
        assert response.status_code == 200
        assert (response.json()["status"], response.json()["void_reason"]) == ("voided", "No llegó")


class TestRefund:
    @pytest.fixture
    def transfer(self, folio, owner):
        return record_payment(folio, amount=Decimal("100000"), method="bank_transfer", actor=owner)

    def test_refunds_with_confirmation(self, api, transfer):
        payload = {"amount": "30000", "reason": "Descuento", "confirm": True}
        response = api.post(f"{URL}payments/{transfer.pk}/refund/", payload)
        assert response.status_code == 201
        body = response.json()
        assert (body["amount"], body["status"], body["payment_id"], body["reason"]) == (
            "30000.00",
            "approved",
            str(transfer.pk),
            "Descuento",
        )

    def test_requires_confirmation(self, api, transfer):
        response = api.post(f"{URL}payments/{transfer.pk}/refund/", {"amount": "30000", "reason": "x"})
        assert (response.status_code, response.json()["code"]) == (400, "confirmation_required")

    def test_cannot_exceed_what_is_left(self, api, transfer):
        payload = {"amount": "100001", "reason": "x", "confirm": True}
        response = api.post(f"{URL}payments/{transfer.pk}/refund/", payload)
        assert (response.status_code, response.json()["code"], response.json()["refundable"]) == (
            400,
            "refund_exceeds_payment",
            "100000.00",
        )

    def test_pending_refunds_are_completed_later(self, api, folio):
        payment = PaymentFactory(folio=folio, method="ota_collect", amount=Decimal("80000"))
        refund = api.post(
            f"{URL}payments/{payment.pk}/refund/", {"amount": "80000", "reason": "OTA", "confirm": True}
        )
        assert refund.json()["status"] == "pending" and refund.json()["instructions"]

        response = api.post(
            f"{URL}refunds/{refund.json()['id']}/complete/", {"confirm": True, "reference": "EXTRANET-9"}
        )

        assert response.status_code == 200
        assert (response.json()["status"], response.json()["provider_reference"]) == (
            "approved",
            "EXTRANET-9",
        )
        assert Alert.objects.get(dedupe_key=f"refund:{refund.json()['id']}").resolved_at is not None


class TestPaymentLink:
    def test_creates_a_link_that_returns_to_the_guest_portal(self, api, folio, settings):
        settings.FRONTEND_URL = "http://front.test"
        response = api.post(f"{URL}folios/{folio.pk}/payment-link/", {"amount": "150000"})
        assert response.status_code == 201, response.json()
        body = response.json()
        intent = PaymentIntent.objects.get()
        assert body["checkout_url"] == f"http://front.test/sim/pay/{intent.reference}"
        assert body["intent"]["reference"] == intent.reference and intent.reference.startswith("HT-PAY001-")
        assert (body["intent"]["amount"], body["intent"]["status"], body["intent"]["mode"]) == (
            "150000.00",
            "created",
            "simulated",
        )
        assert intent.return_url.startswith("http://front.test/g/") and intent.return_url.endswith("?paid=1")
        assert body["messages"] == []

    def test_can_send_it_by_email_and_whatsapp(self, api, folio, monkeypatch):
        calls = []

        def fake_send_message(**kwargs):
            calls.append(kwargs)
            return [OutboundMessage(channel="email", to="guest@example.com", status="sent")]

        monkeypatch.setattr(messaging, "send_message", fake_send_message)
        payload = {"amount": "150000", "send_via": ["email", "whatsapp"]}
        response = api.post(f"{URL}folios/{folio.pk}/payment-link/", payload)

        assert response.status_code == 201
        (call,) = calls
        assert (call["property"], call["template_code"], call["channels"]) == (
            folio.property,
            "payment_link",
            ("email", "whatsapp"),
        )
        assert (call["guest"], call["reservation"]) == (folio.guest, folio.reservation)
        assert call["context"]["payment_url"] == response.json()["checkout_url"]
        assert response.json()["messages"] == [
            {"channel": "email", "to": "guest@example.com", "status": "sent", "error": ""}
        ]

    def test_unknown_channels_are_rejected(self, api, folio):
        response = api.post(f"{URL}folios/{folio.pk}/payment-link/", {"amount": "1000", "send_via": ["sms"]})
        assert response.status_code == 400 and "send_via" in response.json()["fields"]


class TestIntents:
    def test_lists_the_links_of_a_reservation(self, api, folio, reservation):
        intent = create_payment_intent(folio, amount=Decimal("1000"), return_url="")
        create_payment_intent(
            get_or_create_folio(ReservationFactory(property=folio.property)), amount=1, return_url=""
        )
        body = api.get(f"{URL}intents/", {"reservation": str(reservation.pk)}).json()
        assert [row["reference"] for row in body["results"]] == [intent.reference]

    def test_verify_now(self, api, folio):
        intent = create_payment_intent(folio, amount=Decimal("1000"), return_url="")
        intent.payload = {
            "simulation": {"outcome": "approved", "method": "wompi_card", "transaction_id": "SIM-X"}
        }
        intent.save()
        response = api.post(f"{URL}intents/{intent.pk}/sync/")
        assert response.status_code == 200
        assert (response.json()["status"], response.json()["payment_id"]) == (
            "approved",
            str(Payment.objects.get().pk),
        )
