"""Pure Wompi helpers: integrity signature, event checksum, checkout URL and the HTTP client (respx).

Vectors: the integrity example is the official one from docs.wompi.co (Widget & Checkout Web). The events
page prints an example checksum that does NOT match SHA256 of its own example string, so the expected event
checksums below were computed independently with hashlib from the documented algorithm.
"""

import copy
import json
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx

from apps.finance import wompi
from apps.finance.errors import ProviderError

INTEGRITY_SECRET = "prod_integrity_Z5mMke9x0k8gpErbDqwrJXMqsI6SFli6"
EVENTS_SECRET = "prod_events_OcHnIzeBl5socpwByQ4hA52Em3USQ93Z"

DOC_EVENT = {
    "event": "transaction.updated",
    "data": {
        "transaction": {
            "id": "1234-1610641025-49201",
            "amount_in_cents": 4490000,
            "reference": "MZQ3X2DE2SMX",
            "customer_email": "juan.perez@gmail.com",
            "currency": "COP",
            "payment_method_type": "NEQUI",
            "redirect_url": "https://mitienda.com.co/pagos/redireccion",
            "status": "APPROVED",
            "shipping_address": None,
            "payment_link_id": None,
            "payment_source_id": None,
        }
    },
    "environment": "prod",
    "signature": {
        "properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"],
        "checksum": "5A18EC5E8FDB7DF463E9F94774CBA8F583BA21BD04A09CEFF2EA68A4BC0AEFBE",
    },
    "timestamp": 1530291411,
    "sent_at": "2018-07-20T16:45:05.000Z",
}


class TestIntegritySignature:
    def test_matches_the_official_example(self):
        assert (
            wompi.integrity_signature("sk8-438k4-xmxm392-sn2m", 2490000, "COP", INTEGRITY_SECRET)
            == "37c8407747e595535433ef8f6a811d853cd943046624a0ec04662b17bbf33bf5"
        )

    def test_includes_the_expiration_time_before_the_secret(self):
        assert (
            wompi.integrity_signature(
                "sk8-438k4-xmxm392-sn2m",
                2490000,
                "COP",
                INTEGRITY_SECRET,
                expiration_time="2023-06-09T20:28:50.000Z",
            )
            == "e972f58e7de36b283fbb93d9318d39a54ffdff4e8e917b534f30d63c9d7bb89c"
        )


def test_amounts_go_in_cents():
    assert wompi.amount_in_cents(Decimal("150000.00")) == 15000000
    assert wompi.amount_in_cents(Decimal("99.5")) == 9950


class TestEventChecksum:
    def test_concatenates_the_signed_properties_the_timestamp_and_the_secret(self):
        assert (
            wompi.event_checksum(DOC_EVENT, EVENTS_SECRET)
            == "5a18ec5e8fdb7df463e9f94774cba8f583ba21bd04a09ceff2ea68a4bc0aefbe"
        )

    def test_verifies_a_genuine_event_in_any_case(self):
        assert wompi.verify_event(DOC_EVENT, EVENTS_SECRET)
        lower = copy.deepcopy(DOC_EVENT)
        lower["signature"]["checksum"] = lower["signature"]["checksum"].lower()
        assert wompi.verify_event(lower, EVENTS_SECRET)

    def test_prefers_the_header_checksum_when_present(self):
        unsigned = copy.deepcopy(DOC_EVENT)
        unsigned["signature"]["checksum"] = ""
        assert wompi.verify_event(
            unsigned,
            EVENTS_SECRET,
            header_checksum="5a18ec5e8fdb7df463e9f94774cba8f583ba21bd04a09ceff2ea68a4bc0aefbe",
        )
        assert not wompi.verify_event(DOC_EVENT, EVENTS_SECRET, header_checksum="deadbeef")

    def test_non_ascii_checksums_are_rejected_not_crashed_on(self):
        assert not wompi.verify_event(DOC_EVENT, EVENTS_SECRET, header_checksum="ñandú")
        tampered = copy.deepcopy(DOC_EVENT)
        tampered["signature"]["checksum"] = "café"
        assert not wompi.verify_event(tampered, EVENTS_SECRET)

    def test_rejects_tampered_events_and_wrong_secrets(self):
        tampered = copy.deepcopy(DOC_EVENT)
        tampered["data"]["transaction"]["status"] = "DECLINED"
        assert not wompi.verify_event(tampered, EVENTS_SECRET)
        assert not wompi.verify_event(DOC_EVENT, "prod_events_other")
        assert not wompi.verify_event(DOC_EVENT, "")

    @pytest.mark.parametrize(
        "broken",
        [
            {"event": "transaction.updated"},
            {**DOC_EVENT, "signature": {"properties": "transaction.id", "checksum": "x"}},
            {**DOC_EVENT, "timestamp": None},
            {**DOC_EVENT, "signature": "5A18EC5E8FDB7DF463E9F94774CBA8F583BA21BD04A09CEFF2EA68A4BC0AEFBE"},
            {**DOC_EVENT, "data": ["transaction"]},
        ],
    )
    def test_malformed_events_do_not_verify(self, broken):
        assert not wompi.verify_event(broken, EVENTS_SECRET)
        checksum = "5a18ec5e8fdb7df463e9f94774cba8f583ba21bd04a09ceff2ea68a4bc0aefbe"
        assert not wompi.verify_event(broken, EVENTS_SECRET, header_checksum=checksum)


def test_checkout_url_carries_the_signed_parameters():
    url = wompi.checkout_url(
        public_key="pub_test_Q5yDA9xoKdePzhSGeVe9HAez7HgGORGf",
        reference="HT-7K2M9Q-4F7H2K",
        amount_in_cents=15000000,
        currency="COP",
        integrity_secret="test_integrity_secret",
        redirect_url="http://localhost:5173/booking/HT-7K2M9Q/confirmed?payment_ref=HT-7K2M9Q-4F7H2K",
        expiration_time="2026-09-26T20:00:00.000Z",
        customer_email="camila@example.com",
        customer_name="Camila Rodríguez",
    )
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://checkout.wompi.co/p/"
    query = {key: values[0] for key, values in parse_qs(parts.query).items()}
    assert query == {
        "public-key": "pub_test_Q5yDA9xoKdePzhSGeVe9HAez7HgGORGf",
        "currency": "COP",
        "amount-in-cents": "15000000",
        "reference": "HT-7K2M9Q-4F7H2K",
        # sha256("HT-7K2M9Q-4F7H2K" "15000000" "COP" "2026-09-26T20:00:00.000Z" "test_integrity_secret")
        "signature:integrity": "d6179881d28d86cd0474e8bccc541f998a20991d3acbbe986c4d37a9a9956562",
        "redirect-url": "http://localhost:5173/booking/HT-7K2M9Q/confirmed?payment_ref=HT-7K2M9Q-4F7H2K",
        "expiration-time": "2026-09-26T20:00:00.000Z",
        "customer-data:email": "camila@example.com",
        "customer-data:full-name": "Camila Rodríguez",
    }


class TestClient:
    @pytest.fixture
    def client(self):
        return wompi.WompiClient(environment="sandbox", public_key="pub_test_abc", private_key="prv_test_xyz")

    def test_base_urls_follow_the_environment(self):
        assert wompi.WompiClient(environment="sandbox").base_url == "https://sandbox.wompi.co/v1"
        assert wompi.WompiClient(environment="production").base_url == "https://production.wompi.co/v1"

    @respx.mock
    def test_reads_a_transaction_with_the_private_key(self, client):
        route = respx.get("https://sandbox.wompi.co/v1/transactions/1234-1-1").mock(
            return_value=httpx.Response(200, json={"data": {"id": "1234-1-1", "status": "APPROVED"}})
        )
        assert client.get_transaction("1234-1-1") == {"id": "1234-1-1", "status": "APPROVED"}
        assert route.calls.last.request.headers["Authorization"] == "Bearer prv_test_xyz"

    @respx.mock
    def test_searches_transactions_by_reference(self, client):
        route = respx.get("https://sandbox.wompi.co/v1/transactions").mock(
            return_value=httpx.Response(200, json={"data": [{"id": "1", "status": "DECLINED"}]})
        )
        assert client.find_transactions("HT-7K2M9Q-4F7H2K") == [{"id": "1", "status": "DECLINED"}]
        request = route.calls.last.request
        assert request.url.params["reference"] == "HT-7K2M9Q-4F7H2K"
        assert request.headers["Authorization"] == "Bearer prv_test_xyz"

    @respx.mock
    def test_voids_card_transactions_by_amount(self, client):
        route = respx.post("https://sandbox.wompi.co/v1/transactions/1234-1-1/void").mock(
            return_value=httpx.Response(201, json={"data": {"status": "APPROVED"}})
        )
        client.void_transaction("1234-1-1", amount_in_cents=3000000)
        request = route.calls.last.request
        assert json.loads(request.read()) == {"amount_in_cents": 3000000}
        assert request.headers["Authorization"] == "Bearer prv_test_xyz"

    @respx.mock
    def test_reads_the_merchant_with_the_public_key(self, client):
        respx.get("https://sandbox.wompi.co/v1/merchants/pub_test_abc").mock(
            return_value=httpx.Response(200, json={"data": {"id": 42, "name": "Hotel"}})
        )
        assert client.merchant() == {"id": 42, "name": "Hotel"}

    @respx.mock
    def test_http_errors_become_provider_errors(self, client):
        respx.get("https://sandbox.wompi.co/v1/transactions/nope").mock(
            return_value=httpx.Response(404, json={"error": {"type": "NOT_FOUND_ERROR"}})
        )
        with pytest.raises(ProviderError) as exc:
            client.get_transaction("nope")
        assert exc.value.status == 404

    @respx.mock
    def test_network_failures_become_provider_errors(self, client):
        respx.get("https://sandbox.wompi.co/v1/transactions/x").mock(side_effect=httpx.ConnectTimeout("slow"))
        with pytest.raises(ProviderError):
            client.get_transaction("x")
