"""Integration providers: e-invoicing (simulated / Factus), SIRE (simulated / portal), TRA (sim. / MinCIT)."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from apps.compliance.providers import (
    FactusProvider,
    MincitTraProvider,
    PortalSireProvider,
    SimulatedEInvoiceProvider,
    SimulatedSireProvider,
    SimulatedTraProvider,
)
from apps.compliance.services.config import supplier_info
from apps.compliance.tests.factories import InvoiceFactory, InvoiceResolutionFactory
from apps.core import integrations

pytestmark = pytest.mark.django_db

SANDBOX = "https://api-sandbox.factus.com.co"
BOGOTA = ZoneInfo("America/Bogota")


@pytest.fixture
def hotel_prop(prop):
    prop.nit = "901234567-7"
    prop.legal_name = "Casa Aurora Hoteles S.A.S."
    prop.save()
    return prop


@pytest.fixture
def invoice(hotel_prop):
    resolution = InvoiceResolutionFactory(
        property=hotel_prop, technical_key="fc8eac422eba16e22ffd8c6f94b3f40a6e38162c", provider_range_id="389"
    )
    return InvoiceFactory(
        property=hotel_prop,
        resolution=resolution,
        number=123,
        full_number="SETT123",
        issued_at=datetime(2026, 10, 14, 12, 30, tzinfo=BOGOTA),
        issue_date=datetime(2026, 10, 14).date(),
        cufe="",
        qr_data="",
        status="draft",
    )


def setting_for(prop, kind, mode, config=None, secrets=None):
    setting = integrations.get_setting(prop, kind)
    setting.mode = mode
    setting.config = config or {}
    setting.save()
    if secrets:
        integrations.set_secrets(setting, secrets)
    return setting


class TestSimulatedEInvoice:
    def test_it_accepts_with_the_cufe_of_the_dian_concatenation(self, invoice, hotel_prop):
        provider = SimulatedEInvoiceProvider(setting_for(hotel_prop, "einvoice", "simulated"))

        result = provider.issue(invoice, supplier=supplier_info(hotel_prop))

        raw = (
            "SETT1232026-10-1412:30:00-05:00640000.0001121600.00040.00030.00761600.00"
            "901234567"
            "52123456"
            "fc8eac422eba16e22ffd8c6f94b3f40a6e38162c"
            "2"
        )
        assert result["status"] == "accepted"
        assert result["cufe"] == hashlib.sha384(raw.encode()).hexdigest()
        assert "NumFac=SETT123" in result["qr_data"] and f"CUFE={result['cufe']}" in result["qr_data"]
        assert result["number"] == "SETT123"

    def test_the_same_invoice_always_gets_the_same_cufe(self, invoice, hotel_prop):
        provider = SimulatedEInvoiceProvider(setting_for(hotel_prop, "einvoice", "simulated"))
        supplier = supplier_info(hotel_prop)

        first = provider.issue(invoice, supplier=supplier)["cufe"]
        invoice.total = Decimal("761601")
        changed = provider.issue(invoice, supplier=supplier)["cufe"]
        invoice.total = Decimal("761600")

        assert provider.issue(invoice, supplier=supplier)["cufe"] == first
        assert changed != first


def factus_setting(prop, **config):
    return setting_for(
        prop,
        "einvoice",
        "real",
        config={"environment": "sandbox", "client_id": "cid", "username": "api@hotel.co", **config},
        secrets={"client_secret": "csecret", "password": "pw"},
    )


def token_route():
    return respx.post(f"{SANDBOX}/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "token_type": "Bearer",
                "expires_in": 3600,
                "access_token": "tok-1",
                "refresh_token": "r-1",
            },
        )
    )


VALIDATED_BILL = {
    "status": "Created",
    "message": "Documento con el código de referencia registrado y validado con éxito",
    "data": {
        "number": "SETP990000550",
        "is_validated": True,
        "cufe": "a1b2c3",
        "errors": {},
        "links": {
            "qr": "https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey=a1b2c3",
            "public_url": "https://portal.factus.com.co/view/invoice/x",
        },
    },
}


class TestFactus:
    @respx.mock
    def test_it_authenticates_with_the_password_grant_and_validates_the_bill(self, invoice, hotel_prop):
        token = token_route()
        validate = respx.post(f"{SANDBOX}/v2/bills/validate").mock(
            return_value=httpx.Response(201, json=VALIDATED_BILL)
        )
        provider = FactusProvider(factus_setting(hotel_prop))

        result = provider.issue(invoice, supplier=supplier_info(hotel_prop))

        form = parse_qs(token.calls.last.request.content.decode())
        assert form == {
            "grant_type": ["password"],
            "client_id": ["cid"],
            "client_secret": ["csecret"],
            "username": ["api@hotel.co"],
            "password": ["pw"],
        }
        request = validate.calls.last.request
        assert request.headers["Authorization"] == "Bearer tok-1"
        body = json.loads(request.content)
        assert body["reference_code"] == f"HTL{invoice.pk.hex}"
        assert body["numbering_range_id"] == 389
        assert body["document"] == "01"
        assert body["customer"] == {
            "identification_document_code": "13",
            "identification": "52123456",
            "legal_organization_code": "2",
            "tribute_code": "ZZ",
            "names": "Laura Gómez",
            "address": "Cra 7 # 12-34",
            "email": "laura@example.com",
            "phone": "+573001234567",
            "country_code": "CO",
            "municipality_code": "11001",
        }
        assert body["items"] == [
            {
                "code_reference": "ALOJ-DBL",
                "name": "Alojamiento Estándar · 2 noches",
                "quantity": "2.00",
                "discount_rate": "0.00",
                "price": "320000.00",
                "unit_measure_code": "94",
                "standard_code": "999",
                "taxes": [{"code": "01", "rate": "19.00", "is_excluded": False}],
            }
        ]
        assert body["payment_details"] == [
            {"payment_form": "1", "payment_method_code": "ZZZ", "amount": "761600.00"}
        ]
        assert result["status"] == "accepted"
        assert (result["number"], result["cufe"]) == ("SETP990000550", "a1b2c3")
        assert result["qr_data"].endswith("documentkey=a1b2c3")

    @respx.mock
    def test_the_token_is_reused_until_it_expires(self, invoice, hotel_prop):
        token = token_route()
        respx.post(f"{SANDBOX}/v2/bills/validate").mock(return_value=httpx.Response(201, json=VALIDATED_BILL))
        supplier = supplier_info(hotel_prop)

        FactusProvider(factus_setting(hotel_prop)).issue(invoice, supplier=supplier)
        FactusProvider(factus_setting(hotel_prop)).issue(invoice, supplier=supplier)

        assert token.call_count == 1

    @respx.mock
    def test_exempt_and_excluded_lines_are_sent_with_rate_zero(self, invoice, hotel_prop):
        token_route()
        validate = respx.post(f"{SANDBOX}/v2/bills/validate").mock(
            return_value=httpx.Response(201, json=VALIDATED_BILL)
        )
        invoice.lines = [
            {**invoice.lines[0], "tax_status": "exempt", "tax_rate": "0.00", "tax_amount": "0.00"},
            {
                "code": "PEN",
                "kind": "cancellation_fee",
                "description": "Penalidad",
                "quantity": 1,
                "unit_price": "80000.00",
                "net": "80000.00",
                "tax_code": "",
                "tax_status": "excluded",
                "tax_rate": "0.00",
                "tax_amount": "0.00",
                "total": "80000.00",
            },
        ]

        FactusProvider(factus_setting(hotel_prop)).issue(invoice, supplier=supplier_info(hotel_prop))

        items = json.loads(validate.calls.last.request.content)["items"]
        assert [item["taxes"] for item in items] == [
            [{"code": "01", "rate": "0.00", "is_excluded": False}],
            [{"code": "01", "rate": "0.00", "is_excluded": True}],
        ]

    @respx.mock
    def test_a_bill_waiting_for_the_dian_is_issued_not_accepted(self, invoice, hotel_prop):
        token_route()
        pending = {**VALIDATED_BILL, "data": {**VALIDATED_BILL["data"], "is_validated": False}}
        respx.post(f"{SANDBOX}/v2/bills/validate").mock(return_value=httpx.Response(201, json=pending))

        result = FactusProvider(factus_setting(hotel_prop)).issue(invoice, supplier=supplier_info(hotel_prop))

        assert result["status"] == "issued"

    @respx.mock
    def test_validation_errors_reject_the_document_with_the_reasons(self, invoice, hotel_prop):
        token_route()
        respx.post(f"{SANDBOX}/v2/bills/validate").mock(
            return_value=httpx.Response(
                422,
                json={
                    "message": "Error de validación",
                    "data": {"errors": {"customer.identification": ["inválido"]}},
                },
            )
        )

        result = FactusProvider(factus_setting(hotel_prop)).issue(invoice, supplier=supplier_info(hotel_prop))

        assert result["status"] == "rejected"
        assert "customer.identification" in result["message"] and "inválido" in result["message"]

    @respx.mock
    def test_server_errors_and_timeouts_are_technical_errors(self, invoice, hotel_prop):
        token_route()
        route = respx.post(f"{SANDBOX}/v2/bills/validate")
        supplier = supplier_info(hotel_prop)

        route.mock(return_value=httpx.Response(503, text="unavailable"))
        assert (
            FactusProvider(factus_setting(hotel_prop)).issue(invoice, supplier=supplier)["status"] == "error"
        )
        route.mock(side_effect=httpx.ConnectTimeout("timeout"))
        assert (
            FactusProvider(factus_setting(hotel_prop)).issue(invoice, supplier=supplier)["status"] == "error"
        )

    @respx.mock
    def test_a_credit_note_annuls_the_bill_by_its_number(self, invoice, hotel_prop):
        token_route()
        validate = respx.post(f"{SANDBOX}/v2/credit-notes/validate").mock(
            return_value=httpx.Response(
                201,
                json={
                    "message": "ok",
                    "data": {
                        "number": "NC990000010",
                        "cude": "c0de",
                        "is_validated": True,
                        "links": {"qr": "https://dian/qr?documentkey=c0de"},
                    },
                },
            )
        )
        invoice.full_number = "SETP990000550"
        note = InvoiceFactory(
            property=hotel_prop,
            folio=invoice.folio,
            kind="credit_note",
            prefix="NC",
            number=1,
            full_number="NC1",
            related_invoice=invoice,
            reason="Datos del cliente errados",
        )

        result = FactusProvider(factus_setting(hotel_prop, credit_note_range_id="1776")).issue(
            note, supplier=supplier_info(hotel_prop)
        )

        body = json.loads(validate.calls.last.request.content)
        assert (body["correction_concept_code"], body["customization_id"]) == ("2", "20")
        assert body["bill_number"] == "SETP990000550"
        assert body["numbering_range_id"] == 1776
        assert body["observation"] == "Datos del cliente errados"
        assert (result["status"], result["number"], result["cufe"]) == ("accepted", "NC990000010", "c0de")

    @respx.mock
    def test_production_uses_the_production_host(self, invoice, hotel_prop):
        respx.post("https://api.factus.com.co/oauth/token").mock(
            return_value=httpx.Response(200, json={"access_token": "p", "expires_in": 3600})
        )
        route = respx.post("https://api.factus.com.co/v2/bills/validate").mock(
            return_value=httpx.Response(201, json=VALIDATED_BILL)
        )

        FactusProvider(factus_setting(hotel_prop, environment="production")).issue(
            invoice, supplier=supplier_info(hotel_prop)
        )

        assert route.called

    @respx.mock
    def test_test_connection_lists_the_active_numbering_ranges(self, hotel_prop):
        token_route()
        respx.get(f"{SANDBOX}/v2/numbering-ranges").mock(
            return_value=httpx.Response(200, json={"data": [{"id": 389, "prefix": "SETP", "is_active": 1}]})
        )

        ok, message = FactusProvider(factus_setting(hotel_prop)).test_connection()

        assert ok is True
        assert "SETP" in message

    def test_test_connection_reports_missing_credentials(self, hotel_prop):
        ok, message = FactusProvider(setting_for(hotel_prop, "einvoice", "real")).test_connection()

        assert ok is False
        assert "client_id" in message


class TestSire:
    def test_the_simulated_portal_acknowledges_the_upload(self, hotel_prop):
        result = SimulatedSireProvider(setting_for(hotel_prop, "sire", "simulated")).submit(None)

        assert result["status"] == "acknowledged"
        assert result["ack_code"].startswith("SIRE-")

    def test_the_real_portal_is_a_manual_upload_without_acknowledgement(self, hotel_prop):
        result = PortalSireProvider(setting_for(hotel_prop, "sire", "real")).submit(None)

        assert (result["status"], result["ack_code"]) == ("submitted", "")


class TestTra:
    def test_the_simulated_service_returns_a_local_tra_number(self, hotel_prop):
        result = SimulatedTraProvider(setting_for(hotel_prop, "tra", "simulated")).register(
            {"nombres": "Ana"}
        )

        assert result["status"] == "registered"
        assert result["tra_number"].startswith("TRA-")

    @respx.mock
    def test_mincit_registers_the_main_guest_with_the_pms_token(self, hotel_prop):
        route = respx.post("https://pms.mincit.gov.co/one/").mock(
            return_value=httpx.Response(201, json={"code": 4567, "message": "ok"})
        )
        provider = MincitTraProvider(setting_for(hotel_prop, "tra", "real", secrets={"token": "t0k"}))

        result = provider.register({"nombres": "Ana", "numero_acompanantes": 1})

        request = route.calls.last.request
        assert request.headers["Authorization"] == "token t0k"
        assert json.loads(request.content) == {"nombres": "Ana", "numero_acompanantes": 1}
        assert (result["status"], result["tra_number"]) == ("registered", "4567")

    @respx.mock
    def test_mincit_links_companions_to_the_main_guest(self, hotel_prop):
        route = respx.post("https://tra.example.gov.co/api/two/").mock(
            return_value=httpx.Response(200, json={"code": 4568})
        )
        provider = MincitTraProvider(
            setting_for(
                hotel_prop,
                "tra",
                "real",
                config={"base_url": "https://tra.example.gov.co/api"},
                secrets={"token": "t0k"},
            )
        )

        result = provider.register({"nombres": "Luis"}, parent_number="4567")

        assert json.loads(route.calls.last.request.content) == {"nombres": "Luis", "padre": "4567"}
        assert result["tra_number"] == "4568"

    @respx.mock
    def test_mincit_errors_keep_the_registration_retryable(self, hotel_prop):
        respx.post("https://pms.mincit.gov.co/one/").mock(
            return_value=httpx.Response(401, json={"detail": "Token inválido"})
        )
        provider = MincitTraProvider(setting_for(hotel_prop, "tra", "real", secrets={"token": "bad"}))

        result = provider.register({"nombres": "Ana"})

        assert result["status"] == "error"
        assert "Token inválido" in result["message"]

    def test_mincit_without_a_token_is_an_error(self, hotel_prop):
        result = MincitTraProvider(setting_for(hotel_prop, "tra", "real")).register({"nombres": "Ana"})

        assert result["status"] == "error"
        assert "token" in result["message"].lower()


def test_every_kind_has_a_simulated_and_a_real_provider():
    for kind in ("einvoice", "sire", "tra"):
        assert set(integrations.providers_for(kind)) == {"simulated", "real"}
