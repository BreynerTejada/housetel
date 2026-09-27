"""Payment providers registered for kind="payments": simulated (default) and real (Wompi, respx)."""

import copy
import json
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx
from django.test import RequestFactory

from apps.core import integrations
from apps.core.errors import DomainError
from apps.finance.errors import ProviderError
from apps.finance.providers import SimulatedPaymentProvider, WompiProvider, redirect_url_for
from apps.finance.tests.factories import FolioFactory, PaymentFactory, PaymentIntentFactory
from apps.finance.tests.test_wompi import DOC_EVENT, EVENTS_SECRET

pytestmark = pytest.mark.django_db

API = "https://sandbox.wompi.co/v1"
BOGOTA = ZoneInfo("America/Bogota")


@pytest.fixture
def folio(prop):
    return FolioFactory(reservation__property=prop, reservation__code="HT-7K2M9Q")


@pytest.fixture
def wompi_setting(prop):
    setting = integrations.get_setting(prop, "payments")
    setting.mode = "real"
    setting.config = {"environment": "sandbox", "public_key": "pub_test_abc"}
    setting.save()
    integrations.set_secrets(
        setting,
        {
            "private_key": "prv_test_xyz",
            "integrity_secret": "test_integrity_s3cr3t",
            "events_secret": EVENTS_SECRET,
        },
    )
    return setting


@pytest.fixture
def wompi(wompi_setting):
    provider = integrations.get_provider(wompi_setting.property, "payments")
    assert isinstance(provider, WompiProvider)
    return provider


def wompi_tx(**overrides):
    tx = {
        "id": "1234-1610641025-49201",
        "created_at": "2026-09-25T15:00:00.000Z",
        "amount_in_cents": 15000000,
        "reference": "HT-7K2M9Q-4F7H2K",
        "currency": "COP",
        "payment_method_type": "CARD",
        "status": "APPROVED",
        "status_message": None,
    }
    return {**tx, **overrides}


def test_both_modes_are_registered_for_payments():
    registered = integrations.providers_for("payments")
    assert registered == {"simulated": SimulatedPaymentProvider, "real": WompiProvider}
    fields = {field["name"]: field for field in WompiProvider.CONFIG_FIELDS}
    assert set(fields) == {"environment", "public_key", "private_key", "integrity_secret", "events_secret"}
    assert [name for name, field in fields.items() if field["secret"]] == [
        "private_key",
        "integrity_secret",
        "events_secret",
    ]


def test_redirects_go_back_to_the_return_url_with_the_reference(folio):
    intent = PaymentIntentFactory(
        folio=folio, reference="HT-7K2M9Q-4F7H2K", return_url="http://front.test/g/abc?paid=1"
    )
    assert redirect_url_for(intent) == "http://front.test/g/abc?paid=1&payment_ref=HT-7K2M9Q-4F7H2K"
    intent.return_url = ""
    assert redirect_url_for(intent) == ""


class TestSimulated:
    @pytest.fixture
    def provider(self, prop):
        return integrations.get_provider(prop, "payments")

    def test_is_the_default_and_checks_out_on_the_simulated_page(self, provider, folio, settings):
        settings.FRONTEND_URL = "http://front.test"
        intent = PaymentIntentFactory(folio=folio, reference="HT-7K2M9Q-4F7H2K")
        assert isinstance(provider, SimulatedPaymentProvider)
        assert (
            provider.create_checkout(intent)["checkout_url"] == "http://front.test/sim/pay/HT-7K2M9Q-4F7H2K"
        )

    def test_reports_the_decision_taken_on_the_simulated_page(self, provider, folio):
        intent = PaymentIntentFactory(folio=folio)
        assert provider.fetch_status(intent)["status"] == "created"
        intent.payload = {
            "simulation": {"outcome": "approved", "method": "wompi_nequi", "transaction_id": "SIM-1"}
        }
        result = provider.fetch_status(intent)
        assert (result["status"], result["method"], result["provider_reference"], result["amount"]) == (
            "approved",
            "wompi_nequi",
            "SIM-1",
            intent.amount,
        )

    def test_refunds_are_approved_at_once(self, provider, folio):
        payment = PaymentFactory(
            folio=folio, provider="simulated", method="wompi_card", provider_reference="SIM-1"
        )
        result = provider.refund(payment, Decimal("50000"))
        assert result["status"] == "approved" and result["provider_reference"].startswith("SIMREF-")


class TestWompiCheckout:
    def test_signed_checkout_with_expiry_redirect_and_customer(self, wompi, folio):
        intent = PaymentIntentFactory(
            folio=folio,
            provider="wompi",
            mode="real",
            reference="HT-7K2M9Q-4F7H2K",
            amount=Decimal("150000"),
            expires_at=datetime(2026, 9, 26, 15, 0, tzinfo=BOGOTA),
            return_url="http://front.test/booking/HT-7K2M9Q/confirmed",
        )
        url = wompi.create_checkout(intent)["checkout_url"]
        query = {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}
        assert url.startswith("https://checkout.wompi.co/p/?")
        assert query["public-key"] == "pub_test_abc"
        assert query["amount-in-cents"] == "15000000"
        assert query["expiration-time"] == "2026-09-26T20:00:00.000Z"
        assert query["redirect-url"] == (
            "http://front.test/booking/HT-7K2M9Q/confirmed?payment_ref=HT-7K2M9Q-4F7H2K"
        )
        assert query["customer-data:email"] == folio.guest.email
        # sha256("HT-7K2M9Q-4F7H2K" "15000000" "COP" "2026-09-26T20:00:00.000Z" "test_integrity_s3cr3t")
        assert (
            query["signature:integrity"] == "9505e537da6ec6ce41bb90adede957503c49a986edd14971de10f305d4278abb"
        )

    def test_missing_keys_are_a_configuration_error(self, wompi_setting, folio):
        integrations.set_secrets(wompi_setting, {"integrity_secret": None})
        provider = integrations.get_provider(wompi_setting.property, "payments")
        with pytest.raises(DomainError) as exc:
            provider.create_checkout(PaymentIntentFactory(folio=folio, provider="wompi", mode="real"))
        assert exc.value.code == "integration_misconfigured"


class TestWompiStatus:
    @respx.mock
    def test_searches_by_reference_and_maps_the_approved_card_payment(self, wompi, folio):
        intent = PaymentIntentFactory(
            folio=folio, provider="wompi", mode="real", reference="HT-7K2M9Q-4F7H2K"
        )
        route = respx.get(f"{API}/transactions").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": [wompi_tx(id="1-declined", status="DECLINED"), wompi_tx(amount_in_cents=15000000)]
                },
            )
        )
        result = wompi.fetch_status(intent)
        assert route.calls.last.request.url.params["reference"] == "HT-7K2M9Q-4F7H2K"
        assert (result["status"], result["method"], result["provider_reference"], result["amount"]) == (
            "approved",
            "wompi_card",
            "1234-1610641025-49201",
            Decimal("150000"),
        )

    @respx.mock
    def test_uses_the_transaction_id_when_known(self, wompi, folio):
        intent = PaymentIntentFactory(
            folio=folio,
            provider="wompi",
            mode="real",
            reference="HT-7K2M9Q-4F7H2K",
            provider_transaction_id="1234-1610641025-49201",
        )
        respx.get(f"{API}/transactions/1234-1610641025-49201").mock(
            return_value=httpx.Response(
                200, json={"data": wompi_tx(status="PENDING", payment_method_type="PSE")}
            )
        )
        result = wompi.fetch_status(intent)
        assert (result["status"], result["method"]) == ("pending", "wompi_pse")

    @respx.mock
    def test_a_transaction_of_another_reference_is_ignored(self, wompi, folio):
        """The id may come from the redirect query string: it must belong to this link's reference."""
        intent = PaymentIntentFactory(
            folio=folio,
            provider="wompi",
            mode="real",
            reference="HT-7K2M9Q-4F7H2K",
            provider_transaction_id="999-someone-else",
        )
        respx.get(f"{API}/transactions/999-someone-else").mock(
            return_value=httpx.Response(
                200, json={"data": wompi_tx(id="999-someone-else", reference="OTHER-REF")}
            )
        )
        respx.get(f"{API}/transactions").mock(return_value=httpx.Response(200, json={"data": []}))
        assert wompi.fetch_status(intent)["status"] == "created"

    @respx.mock
    def test_an_unknown_transaction_id_falls_back_to_the_reference_search(self, wompi, folio):
        """Anyone can put an `id` in the return URL: a wrong one must not hide the real payment."""
        intent = PaymentIntentFactory(
            folio=folio,
            provider="wompi",
            mode="real",
            reference="HT-7K2M9Q-4F7H2K",
            provider_transaction_id="1-000-bogus",
        )
        respx.get(f"{API}/transactions/1-000-bogus").mock(
            return_value=httpx.Response(404, json={"error": {"type": "NOT_FOUND_ERROR"}})
        )
        respx.get(f"{API}/transactions").mock(return_value=httpx.Response(200, json={"data": [wompi_tx()]}))
        result = wompi.fetch_status(intent)
        assert (result["status"], result["provider_reference"]) == ("approved", "1234-1610641025-49201")

    @respx.mock
    def test_an_empty_answer_for_the_known_id_falls_back_to_the_reference_search(self, wompi, folio):
        intent = PaymentIntentFactory(
            folio=folio,
            provider="wompi",
            mode="real",
            reference="HT-7K2M9Q-4F7H2K",
            provider_transaction_id="1234-1610641025-49201",
        )
        respx.get(f"{API}/transactions/1234-1610641025-49201").mock(
            return_value=httpx.Response(200, json={"data": {}})
        )
        respx.get(f"{API}/transactions").mock(return_value=httpx.Response(200, json={"data": [wompi_tx()]}))
        assert wompi.fetch_status(intent)["status"] == "approved"

    @respx.mock
    def test_no_transaction_yet(self, wompi, folio):
        intent = PaymentIntentFactory(folio=folio, provider="wompi", mode="real")
        respx.get(f"{API}/transactions").mock(return_value=httpx.Response(200, json={"data": []}))
        assert wompi.fetch_status(intent)["status"] == "created"

    @respx.mock
    def test_api_failures_raise(self, wompi, folio):
        intent = PaymentIntentFactory(folio=folio, provider="wompi", mode="real")
        respx.get(f"{API}/transactions").mock(return_value=httpx.Response(500))
        with pytest.raises(ProviderError):
            wompi.fetch_status(intent)


class TestWompiWebhook:
    def _request(self, event, **headers):
        return RequestFactory().post(
            "/api/v1/public/finance/webhooks/wompi/",
            data=json.dumps(event),
            content_type="application/json",
            **headers,
        )

    def test_a_signed_event_is_parsed(self, wompi):
        parsed = wompi.parse_webhook(self._request(DOC_EVENT))
        assert parsed == {
            "event": "transaction.updated",
            "reference": "MZQ3X2DE2SMX",
            "status": "approved",
            "transaction_id": "1234-1610641025-49201",
            "method": "wompi_nequi",
            "transaction": DOC_EVENT["data"]["transaction"],
        }

    def test_a_forged_event_is_rejected(self, wompi):
        forged = copy.deepcopy(DOC_EVENT)
        forged["data"]["transaction"]["amount_in_cents"] = 100
        assert wompi.parse_webhook(self._request(forged)) is None
        assert wompi.parse_webhook(self._request(DOC_EVENT, HTTP_X_EVENT_CHECKSUM="00ff")) is None

    def test_malformed_bodies_are_rejected(self, wompi):
        request = RequestFactory().post(
            "/api/v1/public/finance/webhooks/wompi/", data="not json", content_type="application/json"
        )
        assert wompi.parse_webhook(request) is None


REFUND_APPROVED = {
    "id": 1523,
    "status": "APPROVED",
    "status_message": "",
    "v2_refund_id": "v2_refund_abc123",
    "amount_in_cents": 3000000,
    "transaction_id": "1234-2-2",
    "reference": "HT-7K2M9Q-4F7H2K",
    "created_at": "2026-09-26 14:30:45 UTC",
}
REFUND_DECLINED = {
    **REFUND_APPROVED,
    "status": "DECLINED",
    "status_message": "Tiempo límite sin encontrar fondos excedido",
    "v2_refund_id": None,
}


class TestWompiRefund:
    @respx.mock
    def test_card_payments_are_voided_through_the_api(self, wompi, folio):
        payment = PaymentFactory(
            folio=folio, provider="wompi", method="wompi_card", provider_reference="1234-1-1"
        )
        route = respx.post(f"{API}/transactions/1234-1-1/void").mock(
            return_value=httpx.Response(
                201, json={"data": {"status": "APPROVED", "transaction": {"id": "1234-1-1"}}}
            )
        )
        result = wompi.refund(payment, Decimal("30000"))
        assert result["status"] == "approved"
        assert json.loads(route.calls.last.request.read()) == {"amount_in_cents": 3000000}

    @respx.mock
    def test_a_card_payment_that_can_no_longer_be_voided_is_refunded(self, wompi, folio):
        payment = PaymentFactory(
            folio=folio, provider="wompi", method="wompi_card", provider_reference="1234-1-1"
        )
        respx.post(f"{API}/transactions/1234-1-1/void").mock(return_value=httpx.Response(422, json={}))
        refunds = respx.post(f"{API}/refunds").mock(
            return_value=httpx.Response(201, json={"data": REFUND_APPROVED})
        )
        result = wompi.refund(payment, Decimal("30000"))
        assert (result["status"], result["provider_reference"]) == ("approved", "v2_refund_abc123")
        assert json.loads(refunds.calls.last.request.read())["transaction_id"] == "1234-1-1"

    @respx.mock
    def test_an_unanswered_card_void_is_not_followed_by_a_refund(self, wompi, folio):
        """The void may have gone through: asking for a refund too could give the money back twice."""
        payment = PaymentFactory(
            folio=folio, provider="wompi", method="wompi_card", provider_reference="1234-1-1"
        )
        respx.post(f"{API}/transactions/1234-1-1/void").mock(side_effect=httpx.ReadTimeout("slow"))
        refunds = respx.post(f"{API}/refunds").mock(
            return_value=httpx.Response(201, json={"data": REFUND_APPROVED})
        )
        result = wompi.refund(payment, Decimal("30000"))
        assert result["status"] == "pending" and "panel de wompi" in result["instructions"].lower()
        assert not refunds.called

    @respx.mock
    def test_a_card_refund_nobody_accepts_fails(self, wompi, folio):
        payment = PaymentFactory(
            folio=folio, provider="wompi", method="wompi_card", provider_reference="1234-1-1"
        )
        respx.post(f"{API}/transactions/1234-1-1/void").mock(return_value=httpx.Response(422, json={}))
        respx.post(f"{API}/refunds").mock(return_value=httpx.Response(201, json={"data": REFUND_DECLINED}))
        result = wompi.refund(payment, Decimal("30000"))
        assert result["status"] == "failed"
        assert (
            "422" in result["message"] and "Tiempo límite sin encontrar fondos excedido" in result["message"]
        )

    @respx.mock
    @pytest.mark.parametrize("method", ["wompi_pse", "wompi_nequi", "wompi_other"])
    def test_other_methods_are_refunded_with_the_refunds_api(self, wompi, folio, method):
        payment = PaymentFactory(folio=folio, provider="wompi", method=method, provider_reference="1234-2-2")
        route = respx.post(f"{API}/refunds").mock(
            return_value=httpx.Response(201, json={"data": REFUND_APPROVED})
        )
        result = wompi.refund(payment, Decimal("30000"))
        assert (result["status"], result["provider_reference"]) == ("approved", "v2_refund_abc123")
        request = route.calls.last.request
        assert request.headers["Authorization"] == "Bearer prv_test_xyz"
        body = json.loads(request.read())
        assert (body["transaction_id"], body["amount_in_cents"]) == ("1234-2-2", 3000000)
        assert body["test_scenario"] == "approved"  # sandbox only: how Wompi's sandbox simulates the result

    @respx.mock
    def test_production_refunds_carry_no_test_scenario(self, wompi_setting, folio):
        wompi_setting.config = {**wompi_setting.config, "environment": "production"}
        wompi_setting.save()
        provider = integrations.get_provider(wompi_setting.property, "payments")
        payment = PaymentFactory(
            folio=folio, provider="wompi", method="wompi_pse", provider_reference="1234-2-2"
        )
        route = respx.post("https://production.wompi.co/v1/refunds").mock(
            return_value=httpx.Response(201, json={"data": REFUND_APPROVED})
        )
        assert provider.refund(payment, Decimal("30000"))["status"] == "approved"
        assert "test_scenario" not in json.loads(route.calls.last.request.read())

    @respx.mock
    def test_a_refund_wompi_does_not_approve_waits_for_a_manual_transfer(self, wompi, folio):
        payment = PaymentFactory(
            folio=folio, provider="wompi", method="wompi_pse", provider_reference="1234-2-2"
        )
        respx.post(f"{API}/refunds").mock(return_value=httpx.Response(201, json={"data": REFUND_DECLINED}))
        result = wompi.refund(payment, Decimal("30000"))
        assert result["status"] == "pending"
        assert "Tiempo límite sin encontrar fondos excedido" in result["instructions"]
        assert "transferencia" in result["instructions"].lower()

    @respx.mock
    @pytest.mark.parametrize("method", ["wompi_pse", "wompi_nequi", "wompi_other"])
    def test_without_the_refunds_api_other_methods_need_a_manual_transfer(self, wompi, folio, method):
        payment = PaymentFactory(
            folio=folio, provider="wompi", method=method, provider_reference=f"tx-{method}"
        )
        respx.post(f"{API}/refunds").mock(
            return_value=httpx.Response(404, json={"error": {"type": "NOT_FOUND_ERROR"}})
        )
        result = wompi.refund(payment, Decimal("30000"))
        assert result["status"] == "pending" and "transferencia" in result["instructions"].lower()

    @respx.mock
    @pytest.mark.parametrize("answer", [httpx.ConnectTimeout("slow"), httpx.Response(502)])
    def test_an_unanswered_refund_is_checked_in_the_wompi_dashboard_first(self, wompi, folio, answer):
        """Wompi may have applied it: never suggest a second transfer blindly."""
        payment = PaymentFactory(
            folio=folio, provider="wompi", method="wompi_nequi", provider_reference="1234-2-2"
        )
        route = respx.post(f"{API}/refunds")
        if isinstance(answer, Exception):
            route.mock(side_effect=answer)
        else:
            route.mock(return_value=answer)
        result = wompi.refund(payment, Decimal("30000"))
        assert result["status"] == "pending" and "panel de wompi" in result["instructions"].lower()


class TestWompiConnection:
    @respx.mock
    def test_checks_both_keys(self, wompi):
        respx.get(f"{API}/merchants/pub_test_abc").mock(
            return_value=httpx.Response(200, json={"data": {"id": 7, "name": "Hotel Prueba"}})
        )
        respx.get(f"{API}/transactions").mock(return_value=httpx.Response(200, json={"data": []}))
        ok, message = wompi.test_connection()
        assert ok and "Hotel Prueba" in message

    @respx.mock
    def test_reports_an_invalid_private_key(self, wompi):
        respx.get(f"{API}/merchants/pub_test_abc").mock(
            return_value=httpx.Response(200, json={"data": {"id": 7}})
        )
        respx.get(f"{API}/transactions").mock(return_value=httpx.Response(401, json={}))
        ok, message = wompi.test_connection()
        assert not ok and "privada" in message

    def test_reports_keys_of_the_wrong_environment(self, wompi_setting):
        wompi_setting.config = {"environment": "production", "public_key": "pub_test_abc"}
        wompi_setting.save()
        ok, message = integrations.get_provider(wompi_setting.property, "payments").test_connection()
        assert not ok and "pub_prod_" in message
