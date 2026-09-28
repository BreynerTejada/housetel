"""Guest portal endpoints (plan §C, C7 → C5): the invoices of a reservation through its signed link."""

import pytest

from apps.compliance.models import Invoice
from apps.compliance.providers import SimulatedEInvoiceProvider
from apps.compliance.services.invoices import issue_credit_note, issue_invoice
from apps.core.tokens import make_reservation_token

pytestmark = pytest.mark.django_db

BASE = "/api/v1/public/compliance/portal"


def test_the_portal_lists_the_issued_invoices_of_the_reservation(
    public_api, resolution, make_finished_reservation
):
    reservation = make_finished_reservation()
    invoice = issue_invoice(reservation)
    issue_invoice(make_finished_reservation())  # another reservation's invoice
    token = make_reservation_token(reservation)

    response = public_api.get(f"{BASE}/{token}/invoices/")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(invoice.pk),
            "number": "SETT1",
            "kind": "invoice",
            "status": "accepted",
            "total": "761600.00",
            "currency": "COP",
            "issued_at": invoice.issued_at.isoformat(),
            "pdf_url": f"/api/v1/public/compliance/portal/{token}/invoices/{invoice.pk}/pdf/",
        }
    ]


def test_documents_that_did_not_reach_the_dian_are_hidden(
    public_api, resolution, make_finished_reservation, monkeypatch
):
    reservation = make_finished_reservation()
    failing = {"status": "error", "message": "caído", "response": {}}
    monkeypatch.setattr(SimulatedEInvoiceProvider, "issue", lambda self, invoice, supplier: failing)
    issue_invoice(reservation)

    assert public_api.get(f"{BASE}/{make_reservation_token(reservation)}/invoices/").json() == []


def test_an_annulled_invoice_is_shown_with_its_credit_note(public_api, resolution, make_finished_reservation):
    reservation = make_finished_reservation()
    invoice = issue_invoice(reservation)
    issue_credit_note(invoice, reason="Error", confirm=True)

    rows = public_api.get(f"{BASE}/{make_reservation_token(reservation)}/invoices/").json()

    assert [(r["number"], r["kind"], r["status"]) for r in rows] == [
        ("SETT1", "invoice", "cancelled"),
        ("NC1", "credit_note", "accepted"),
    ]


def test_the_pdf_is_served_to_the_guest(public_api, resolution, make_finished_reservation):
    reservation = make_finished_reservation()
    invoice = issue_invoice(reservation)

    response = public_api.get(f"{BASE}/{make_reservation_token(reservation)}/invoices/{invoice.pk}/pdf/")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert b"".join(response.streaming_content).startswith(b"%PDF")


def test_a_tampered_token_or_another_reservations_invoice_is_not_found(
    public_api, resolution, make_finished_reservation
):
    reservation = make_finished_reservation()
    other_invoice = issue_invoice(make_finished_reservation())
    token = make_reservation_token(reservation)

    assert public_api.get(f"{BASE}/{token}x/invoices/").status_code == 404
    assert public_api.get(f"{BASE}/{token}/invoices/{other_invoice.pk}/pdf/").status_code == 404
    assert Invoice.objects.count() == 1
