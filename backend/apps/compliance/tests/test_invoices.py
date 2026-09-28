"""DIAN invoicing: issue from the folio, numbering, totals, exemption, CUFE, files, retries, credit notes."""

import hashlib
import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone
from freezegun import freeze_time

from apps.bookings.models import Stay
from apps.compliance.models import Invoice, InvoiceResolution
from apps.compliance.providers import SimulatedEInvoiceProvider
from apps.compliance.services.config import get_settings
from apps.compliance.services.invoices import (
    ensure_pdf,
    ensure_xml,
    issue_credit_note,
    issue_invoice,
    issue_pending_invoices,
    retry_invoice,
)
from apps.compliance.services.numbering import NumberingError
from apps.compliance.tests.factories import InvoiceResolutionFactory, post
from apps.core import signals
from apps.core.errors import ConfirmationRequired, DomainError
from apps.core.models import Alert, AuditEvent
from apps.finance.models import Folio
from apps.guests.tests.factories import ForeignGuestFactory, GuestFactory

pytestmark = pytest.mark.django_db


def open_alerts(prop, prefix):
    return list(Alert.objects.filter(property=prop, resolved_at__isnull=True, dedupe_key__startswith=prefix))


def folio_of(reservation):
    return Folio.objects.get(reservation=reservation)


class TestIssue:
    def test_it_issues_an_accepted_invoice_numbered_from_the_resolution(
        self, hotel, resolution, make_finished_reservation, owner
    ):
        reservation = make_finished_reservation()

        invoice = issue_invoice(reservation, actor=owner)

        assert (invoice.status, invoice.kind, invoice.mode) == ("accepted", "invoice", "simulated")
        assert (invoice.prefix, invoice.number, invoice.full_number) == ("SETT", 1, "SETT1")
        assert invoice.resolution == resolution
        assert invoice.reservation == reservation and invoice.folio == folio_of(reservation)
        assert invoice.provider == "simulated"
        assert invoice.issued_at is not None and invoice.attempts == 1
        assert invoice.created_by == owner
        assert [line["description"] for line in invoice.lines] == ["Alojamiento Estándar · 2 noches"]

    def test_the_totals_are_the_folio_totals(
        self, hotel, resolution, lodging_tax, extras_tax, make_finished_reservation
    ):
        reservation = make_finished_reservation()  # 2 × 320.000 + 19 %
        folio = folio_of(reservation)
        post(
            folio,
            kind="extra",
            amount="35000",
            quantity=2,
            description="Desayuno",
            tax=extras_tax,
            tax_amount="13300",
        )
        post(folio, kind="adjustment", amount="-20000", description="Cortesía")
        voided = post(
            folio, kind="fee", amount="50000", description="Lavandería", tax=extras_tax, tax_amount="9500"
        )
        voided.voided_at = timezone.now()
        voided.save()

        invoice = issue_invoice(reservation)

        # net 640000 + 70000 − 20000 = 690000 · IVA 121600 + 13300 = 134900
        assert (invoice.subtotal, invoice.tax_total, invoice.total) == (
            Decimal("690000"),
            Decimal("134900"),
            Decimal("824900"),
        )
        assert set(invoice.charges.values_list("pk", flat=True)) == set(
            folio.charges.filter(voided_at__isnull=True).values_list("pk", flat=True)
        )

    def test_a_foreign_non_resident_gets_the_lodging_exempt_with_the_legal_note(
        self, hotel, resolution, make_finished_reservation
    ):
        guest = ForeignGuestFactory(organization=hotel.organization, document_number="X1234567")
        reservation = make_finished_reservation(booker=guest, exempt=True)

        invoice = issue_invoice(reservation)

        assert invoice.tax_total == Decimal("0")
        assert invoice.total == Decimal("640000")
        assert invoice.lines[0]["tax_status"] == "exempt"
        assert "Art. 481 lit. d)" in invoice.exempt_note
        assert (invoice.customer["dian_document_code"], invoice.customer["document_number"]) == (
            "41",
            "X1234567",
        )

    def test_a_booker_without_document_is_invoiced_to_the_final_consumer(
        self, hotel, resolution, make_finished_reservation
    ):
        guest = GuestFactory(organization=hotel.organization, document_type="", document_number="")

        invoice = issue_invoice(make_finished_reservation(booker=guest))

        assert invoice.customer["is_final_consumer"] is True
        assert invoice.customer["document_number"] == "222222222222"

    @freeze_time("2026-10-14 17:30:00")  # 12:30 in Bogotá
    def test_the_simulated_cufe_is_the_sha384_of_the_dian_fields(self, hotel, make_finished_reservation):
        InvoiceResolutionFactory(property=hotel, technical_key="clave-tecnica")
        guest = GuestFactory(organization=hotel.organization, document_type="CC", document_number="52123456")

        invoice = issue_invoice(make_finished_reservation(booker=guest))

        raw = (
            "SETT12026-10-1412:30:00-05:00640000.0001121600.00040.00030.00761600.00"
            "901234567"
            "52123456"
            "clave-tecnica"
            "2"
        )
        assert invoice.issue_date.isoformat() == "2026-10-14"
        assert invoice.cufe == hashlib.sha384(raw.encode()).hexdigest()
        assert f"CUFE={invoice.cufe}" in invoice.qr_data

    def test_it_stores_the_pdf_and_the_xml(self, hotel, resolution, make_finished_reservation):
        invoice = issue_invoice(make_finished_reservation())

        assert invoice.pdf_file and invoice.xml_file
        with invoice.pdf_file.open("rb") as handle:
            pdf = handle.read()
        assert pdf.startswith(b"%PDF") and len(pdf) > 1024
        with invoice.xml_file.open("rb") as handle:
            assert b"SETT1" in handle.read()

    def test_missing_files_are_generated_on_demand(self, hotel, resolution, make_finished_reservation):
        invoice = issue_invoice(make_finished_reservation(), render=False)
        assert not invoice.pdf_file

        pdf = ensure_pdf(invoice)
        xml = ensure_xml(invoice)

        invoice.refresh_from_db()
        assert pdf.startswith(b"%PDF") and xml.startswith(b"<?xml")
        assert invoice.pdf_file and invoice.xml_file

    def test_numbers_are_consecutive_across_reservations(self, hotel, resolution, make_finished_reservation):
        first = issue_invoice(make_finished_reservation())
        second = issue_invoice(make_finished_reservation())

        assert (first.full_number, second.full_number) == ("SETT1", "SETT2")

    def test_charges_are_invoiced_only_once(self, hotel, resolution, extras_tax, make_finished_reservation):
        reservation = make_finished_reservation()
        issue_invoice(reservation)

        with pytest.raises(DomainError) as caught:
            issue_invoice(reservation)
        assert (caught.value.code, caught.value.status_code) == ("nothing_to_invoice", 409)

        late = post(
            folio_of(reservation),
            kind="extra",
            amount="25000",
            description="Minibar",
            tax=extras_tax,
            tax_amount="4750",
        )
        second = issue_invoice(reservation)
        assert list(second.charges.all()) == [late]
        assert second.total == Decimal("29750")

    def test_a_folio_can_be_invoiced_directly(self, hotel, resolution, make_finished_reservation):
        folio = folio_of(make_finished_reservation())

        invoice = issue_invoice(folio)

        assert invoice.folio == folio and invoice.total == Decimal("761600")

    def test_without_an_active_resolution_nothing_is_created_and_a_critical_alert_stays(
        self, hotel, make_finished_reservation
    ):
        reservation = make_finished_reservation()

        with pytest.raises(NumberingError) as caught:
            issue_invoice(reservation)

        assert caught.value.code == "no_active_resolution"
        assert not Invoice.objects.filter(property=hotel).exists()
        assert [a.severity for a in open_alerts(hotel, "compliance:resolution")] == ["critical"]

    def test_an_expired_resolution_blocks_the_issue(self, hotel, make_finished_reservation):
        today = hotel.business_date
        InvoiceResolutionFactory(
            property=hotel, valid_from=today - timedelta(days=400), valid_to=today - timedelta(days=2)
        )

        with pytest.raises(NumberingError) as caught:
            issue_invoice(make_finished_reservation())

        assert caught.value.code == "resolution_expired"

    def test_the_issue_is_audited(self, hotel, resolution, make_finished_reservation, owner):
        invoice = issue_invoice(make_finished_reservation(), actor=owner)

        event = AuditEvent.objects.get(action="compliance.invoice_issued", target_id=str(invoice.pk))
        assert event.actor == owner and event.property == hotel


class TestProviderFailures:
    def test_a_provider_error_keeps_the_number_and_the_invoice_can_be_retried(
        self, hotel, resolution, make_finished_reservation, monkeypatch
    ):
        failing = {
            "status": "error",
            "number": "",
            "cufe": "",
            "qr_data": "",
            "provider_ref": "",
            "message": "Tiempo de espera agotado",
            "response": {},
            "xml": None,
        }
        monkeypatch.setattr(SimulatedEInvoiceProvider, "issue", lambda self, invoice, supplier: failing)

        invoice = issue_invoice(make_finished_reservation())

        assert (invoice.status, invoice.full_number, invoice.attempts) == ("error", "SETT1", 1)
        assert invoice.error_message == "Tiempo de espera agotado"
        assert not invoice.pdf_file
        [alert] = open_alerts(hotel, f"compliance:invoice:{invoice.pk}")
        assert alert.severity == "warning"

        monkeypatch.undo()
        retried = retry_invoice(invoice)

        assert (retried.status, retried.full_number, retried.attempts) == ("accepted", "SETT1", 2)
        assert retried.cufe and retried.error_message == ""
        assert open_alerts(hotel, f"compliance:invoice:{invoice.pk}") == []

    def test_an_exception_in_the_provider_is_recorded_as_an_error(
        self, hotel, resolution, make_finished_reservation, monkeypatch
    ):
        def boom(self, invoice, supplier):
            raise RuntimeError("sin conexión")

        monkeypatch.setattr(SimulatedEInvoiceProvider, "issue", boom)

        invoice = issue_invoice(make_finished_reservation())

        assert invoice.status == "error" and "sin conexión" in invoice.error_message

    def test_retrying_a_rejected_invoice_takes_the_corrected_customer(
        self, hotel, resolution, make_finished_reservation, monkeypatch
    ):
        guest = GuestFactory(organization=hotel.organization, document_type="CC", document_number="1")
        rejected = {
            "status": "rejected",
            "number": "",
            "cufe": "",
            "qr_data": "",
            "provider_ref": "",
            "message": "customer.identification: inválido",
            "response": {},
            "xml": None,
        }
        monkeypatch.setattr(SimulatedEInvoiceProvider, "issue", lambda self, invoice, supplier: rejected)
        invoice = issue_invoice(make_finished_reservation(booker=guest))
        assert invoice.status == "rejected"
        assert open_alerts(hotel, f"compliance:invoice:{invoice.pk}")[0].severity == "critical"

        guest.document_number = "52123456"
        guest.save()
        monkeypatch.undo()
        retried = retry_invoice(invoice)

        assert retried.status == "accepted"
        assert retried.customer["document_number"] == "52123456"

    def test_an_accepted_invoice_cannot_be_retried(self, hotel, resolution, make_finished_reservation):
        invoice = issue_invoice(make_finished_reservation())

        with pytest.raises(DomainError) as caught:
            retry_invoice(invoice)

        assert (caught.value.code, caught.value.status_code) == ("invalid_state", 409)


class TestCreditNote:
    def test_it_requires_an_explicit_confirmation_and_a_reason(
        self, hotel, resolution, make_finished_reservation
    ):
        invoice = issue_invoice(make_finished_reservation())

        with pytest.raises(ConfirmationRequired):
            issue_credit_note(invoice, reason="Error", confirm=False)
        with pytest.raises(DomainError) as caught:
            issue_credit_note(invoice, reason="  ", confirm=True)
        assert caught.value.code == "reason_required"

    def test_it_annuls_the_invoice_with_its_own_numbering_and_frees_the_charges(
        self, hotel, resolution, make_finished_reservation, owner
    ):
        reservation = make_finished_reservation()
        invoice = issue_invoice(reservation)

        note = issue_credit_note(invoice, reason="Datos del cliente errados", confirm=True, actor=owner)

        invoice.refresh_from_db()
        assert invoice.status == "cancelled"
        assert (note.kind, note.status, note.full_number) == ("credit_note", "accepted", "NC1")
        assert note.related_invoice == invoice and note.reason == "Datos del cliente errados"
        assert (note.subtotal, note.tax_total, note.total) == (
            invoice.subtotal,
            invoice.tax_total,
            invoice.total,
        )
        assert note.lines == invoice.lines
        assert note.cufe and note.cufe != invoice.cufe
        assert note.pdf_file
        assert AuditEvent.objects.filter(
            action="compliance.credit_note_issued", target_id=str(note.pk)
        ).exists()
        reissued = issue_invoice(reservation)
        assert (reissued.full_number, reissued.total) == ("SETT2", invoice.total)

    def test_only_issued_invoices_can_be_annulled_once(self, hotel, resolution, make_finished_reservation):
        invoice = issue_invoice(make_finished_reservation())
        issue_credit_note(invoice, reason="Error", confirm=True)
        invoice.refresh_from_db()

        with pytest.raises(DomainError) as caught:
            issue_credit_note(invoice, reason="Otra vez", confirm=True)

        assert (caught.value.code, caught.value.status_code) == ("invalid_state", 409)


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_issues_get_distinct_numbers(prop):
    """Two reservations invoiced at the same time (two connections) never share a DIAN number."""
    from apps.bookings.tests.factories import ReservationFactory, StayFactory
    from apps.compliance.tests.factories import ComplianceSettingsFactory
    from apps.finance.tests.factories import FolioFactory
    from apps.rates.tests.factories import TaxFactory

    ComplianceSettingsFactory(property=prop)
    InvoiceResolutionFactory(property=prop)
    tax = TaxFactory(property=prop)
    reservations = []
    for _ in range(2):
        reservation = ReservationFactory(property=prop, status="checked_out")
        stay = StayFactory(reservation=reservation, status="checked_out")
        post(
            FolioFactory(reservation=reservation),
            kind="room",
            amount="100000",
            description="Noche",
            tax=tax,
            tax_amount="19000",
            stay=stay,
            night_date=reservation.checkin_date,
        )
        reservations.append(reservation)
    barrier = threading.Barrier(2)
    numbers, errors = [], []

    def worker(reservation):
        try:
            barrier.wait(5)
            numbers.append(issue_invoice(reservation).number)
        except Exception as exc:  # noqa: BLE001 - reported by the assertion below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(r,)) for r in reservations]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(15)

    assert errors == []
    assert sorted(numbers) == [1, 2]
    assert InvoiceResolution.objects.get(property=prop, document_kind="invoice").current_number == 2


class TestAutoIssueOnCheckout:
    def send_checkout(self, stay, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True):
            signals.send_on_commit(signals.stay_checked_out, stay=stay)

    def test_the_last_checkout_issues_the_invoice(
        self, hotel, resolution, make_finished_reservation, django_capture_on_commit_callbacks
    ):
        reservation = make_finished_reservation()

        self.send_checkout(reservation.stays.get(), django_capture_on_commit_callbacks)

        invoice = Invoice.objects.get(reservation=reservation)
        assert (invoice.status, invoice.full_number) == ("accepted", "SETT1")
        assert AuditEvent.objects.get(action="compliance.invoice_issued").source == "automation"

    def test_nothing_is_issued_while_another_stay_is_still_in_house(
        self, hotel, resolution, make_finished_reservation, django_capture_on_commit_callbacks
    ):
        from apps.bookings.tests.factories import StayFactory

        reservation = make_finished_reservation()
        StayFactory(reservation=reservation, status="checked_in")

        self.send_checkout(
            reservation.stays.filter(status="checked_out").first(), django_capture_on_commit_callbacks
        )

        assert not Invoice.objects.filter(reservation=reservation).exists()

    def test_nothing_is_issued_when_automatic_invoicing_is_off(
        self, hotel, resolution, make_finished_reservation, django_capture_on_commit_callbacks
    ):
        settings = get_settings(hotel)
        settings.auto_issue_invoices = False
        settings.save()
        reservation = make_finished_reservation()

        self.send_checkout(reservation.stays.get(), django_capture_on_commit_callbacks)

        assert not Invoice.objects.exists()

    def test_the_demo_seed_replay_issues_nothing(
        self, hotel, resolution, make_finished_reservation, django_capture_on_commit_callbacks
    ):
        reservation = make_finished_reservation()

        with signals.seeding():
            self.send_checkout(reservation.stays.get(), django_capture_on_commit_callbacks)

        assert not Invoice.objects.exists()

    def test_a_numbering_problem_does_not_break_the_checkout(
        self, hotel, make_finished_reservation, django_capture_on_commit_callbacks
    ):
        reservation = make_finished_reservation()

        self.send_checkout(reservation.stays.get(), django_capture_on_commit_callbacks)

        assert not Invoice.objects.exists()
        assert [a.severity for a in open_alerts(hotel, "compliance:resolution")] == ["critical"]


class TestPendingAutomation:
    def test_it_retries_errors_and_issues_the_departures_left_without_invoice(
        self, hotel, resolution, make_finished_reservation, monkeypatch
    ):
        failing = {
            "status": "error",
            "number": "",
            "cufe": "",
            "qr_data": "",
            "provider_ref": "",
            "message": "caído",
            "response": {},
            "xml": None,
        }
        monkeypatch.setattr(SimulatedEInvoiceProvider, "issue", lambda self, invoice, supplier: failing)
        errored = issue_invoice(make_finished_reservation())
        monkeypatch.undo()
        forgotten = make_finished_reservation()

        report = issue_pending_invoices(hotel)

        errored.refresh_from_db()
        assert errored.status == "accepted"
        assert Invoice.objects.get(reservation=forgotten).status == "accepted"
        assert (report["retried"], report["auto_issued"], report["failed"]) == (1, 1, 0)

    def test_departures_before_the_go_live_date_or_the_lookback_are_left_alone(
        self, hotel, resolution, make_finished_reservation
    ):
        settings = get_settings(hotel)
        settings.go_live_date = hotel.business_date - timedelta(days=1)
        settings.save()
        old = make_finished_reservation(checkin=hotel.business_date - timedelta(days=5))  # left 3 days ago

        report = issue_pending_invoices(hotel)

        assert report["auto_issued"] == 0
        assert not Invoice.objects.filter(reservation=old).exists()

    def test_reservations_still_in_house_are_not_invoiced(self, hotel, resolution, make_finished_reservation):
        reservation = make_finished_reservation(status="checked_in")

        issue_pending_invoices(hotel)

        assert not Invoice.objects.filter(reservation=reservation).exists()
        assert Stay.objects.filter(reservation=reservation, status="checked_in").exists()
