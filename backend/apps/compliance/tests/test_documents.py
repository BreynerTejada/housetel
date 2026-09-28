"""Graphic representation (PDF, reportlab) and UBL XML of invoices and credit notes."""

import base64
import re
import zlib
from decimal import Decimal
from xml.etree import ElementTree

import pytest

from apps.compliance.services.documents import amount_in_words, render_invoice_pdf, render_invoice_xml
from apps.compliance.tests.factories import InvoiceFactory, InvoiceResolutionFactory

pytestmark = pytest.mark.django_db

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}
INVOICE_NS = "{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}"
CREDIT_NOTE_NS = "{urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2}"


def pdf_text(data: bytes) -> str:
    """Text drawn in a PDF (test helper): decodes every content stream (reportlab writes ASCII85 + Flate) and
    the octal escapes of its strings."""
    chunks = []
    for raw in re.findall(rb"stream\r?\n(.*?)endstream", data, re.S):
        body = raw.strip()
        if body.endswith(b"~>"):
            body = base64.a85decode(body[:-2])
        try:
            chunks.append(zlib.decompress(body).decode("latin-1"))
        except zlib.error:
            chunks.append(body.decode("latin-1"))
    text = "\n".join(chunks)
    text = re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), text)
    return text.replace("\\(", "(").replace("\\)", ")")


@pytest.fixture
def invoice(prop):
    prop.legal_name = "Casa Aurora Hoteles S.A.S."
    prop.nit = "901234567-7"
    prop.rnt_number = "98765"
    prop.save()
    resolution = InvoiceResolutionFactory(property=prop, prefix="SETT", resolution_number="18760000001")
    return InvoiceFactory(property=prop, resolution=resolution, number=123, full_number="SETT123")


class TestPdf:
    def test_it_is_a_real_pdf_of_more_than_one_kilobyte(self, invoice):
        data = render_invoice_pdf(invoice)

        assert data.startswith(b"%PDF")
        assert len(data) > 1024

    def test_it_shows_the_number_the_supplier_the_customer_and_the_totals(self, invoice):
        text = pdf_text(render_invoice_pdf(invoice))

        assert "SETT123" in text
        assert "Casa Aurora Hoteles S.A.S." in text
        assert "901.234.567-7" in text
        assert "Laura Gómez" in text and "52123456" in text
        assert "Alojamiento Estándar · 2 noches" in text
        assert "$ 761.600" in text  # total
        assert "$ 121.600" in text  # IVA
        assert "18760000001" in text  # DIAN resolution

    def test_it_prints_the_whole_cufe(self, invoice):
        text = pdf_text(render_invoice_pdf(invoice))

        assert invoice.cufe[:48] in text and invoice.cufe[48:] in text

    def test_a_simulated_invoice_says_it_has_no_fiscal_validity(self, invoice):
        assert "SIN VALIDEZ FISCAL" in pdf_text(render_invoice_pdf(invoice))

        invoice.mode = "real"
        assert "SIN VALIDEZ FISCAL" not in pdf_text(render_invoice_pdf(invoice))

    def test_an_exempt_invoice_carries_the_legal_note(self, invoice):
        invoice.exempt_note = "Exento de IVA — Art. 481 lit. d) E.T., servicios hoteleros a no residentes"

        assert "Art. 481 lit. d)" in pdf_text(render_invoice_pdf(invoice))

    def test_a_credit_note_references_the_invoice_it_annuls_and_its_reason(self, invoice, prop):
        note = InvoiceFactory(
            property=prop,
            folio=invoice.folio,
            kind="credit_note",
            prefix="NC",
            number=1,
            full_number="NC1",
            related_invoice=invoice,
            reason="Datos del cliente errados",
        )

        text = pdf_text(render_invoice_pdf(note))

        assert "NOTA CRÉDITO ELECTRÓNICA" in text
        assert "SETT123" in text
        assert "Datos del cliente errados" in text


class TestXml:
    def test_the_invoice_xml_is_ubl_with_the_dian_identifiers_and_totals(self, invoice):
        root = ElementTree.fromstring(render_invoice_xml(invoice))

        assert root.tag == f"{INVOICE_NS}Invoice"
        assert root.findtext("cbc:ID", namespaces=NS) == "SETT123"
        uuid = root.find("cbc:UUID", NS)
        assert (uuid.text, uuid.get("schemeName")) == (invoice.cufe, "CUFE-SHA384")
        assert root.findtext("cbc:InvoiceTypeCode", namespaces=NS) == "01"
        assert root.findtext("cbc:ProfileExecutionID", namespaces=NS) == "2"  # test environment
        assert root.findtext("cbc:IssueDate", namespaces=NS) == invoice.issue_date.isoformat()
        totals = root.find("cac:LegalMonetaryTotal", NS)
        assert Decimal(totals.findtext("cbc:LineExtensionAmount", namespaces=NS)) == Decimal("640000")
        assert Decimal(totals.findtext("cbc:PayableAmount", namespaces=NS)) == Decimal("761600")
        assert Decimal(root.findtext("cac:TaxTotal/cbc:TaxAmount", namespaces=NS)) == Decimal("121600")
        customer_id = root.findtext(
            "cac:AccountingCustomerParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID", namespaces=NS
        )
        assert customer_id == "52123456"
        assert len(root.findall("cac:InvoiceLine", NS)) == 1

    def test_the_supplier_nit_goes_without_its_check_digit(self, invoice):
        root = ElementTree.fromstring(render_invoice_xml(invoice))

        company = root.find("cac:AccountingSupplierParty/cac:Party/cac:PartyTaxScheme/cbc:CompanyID", NS)
        assert (company.text, company.get("schemeID")) == ("901234567", "7")

    def test_the_credit_note_xml_references_the_annulled_invoice(self, invoice, prop):
        note = InvoiceFactory(
            property=prop,
            folio=invoice.folio,
            kind="credit_note",
            prefix="NC",
            number=1,
            full_number="NC1",
            related_invoice=invoice,
            reason="Datos del cliente errados",
            cufe="ab" * 48,
        )

        root = ElementTree.fromstring(render_invoice_xml(note))

        assert root.tag == f"{CREDIT_NOTE_NS}CreditNote"
        assert root.find("cbc:UUID", NS).get("schemeName") == "CUDE-SHA384"
        reference = root.find("cac:BillingReference/cac:InvoiceDocumentReference", NS)
        assert reference.findtext("cbc:ID", namespaces=NS) == "SETT123"
        assert reference.findtext("cbc:UUID", namespaces=NS) == invoice.cufe
        discrepancy = root.find("cac:DiscrepancyResponse", NS)
        assert discrepancy.findtext("cbc:ResponseCode", namespaces=NS) == "2"
        assert discrepancy.findtext("cbc:Description", namespaces=NS) == "Datos del cliente errados"
        assert len(root.findall("cac:CreditNoteLine", NS)) == 1


@pytest.mark.parametrize(
    ("amount", "words"),
    [
        (Decimal("0"), "cero pesos M/CTE"),
        (Decimal("1"), "un peso M/CTE"),
        (Decimal("21"), "veintiún pesos M/CTE"),
        (Decimal("100"), "cien pesos M/CTE"),
        (Decimal("115"), "ciento quince pesos M/CTE"),
        (Decimal("761600"), "setecientos sesenta y un mil seiscientos pesos M/CTE"),
        (Decimal("1000000"), "un millón de pesos M/CTE"),
        (Decimal("2350000"), "dos millones trescientos cincuenta mil pesos M/CTE"),
        (Decimal("1001"), "mil un pesos M/CTE"),
        (Decimal("516"), "quinientos dieciséis pesos M/CTE"),
    ],
)
def test_amount_in_words_reads_the_total_in_spanish(amount, words):
    assert amount_in_words(amount) == words
