"""What is still pending legally: invoices, TRA, SIRE files and the health of the numbering resolution."""

from datetime import date, timedelta

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.compliance.models import SireReport
from apps.compliance.providers import SimulatedEInvoiceProvider
from apps.compliance.services.config import get_settings
from apps.compliance.services.invoices import issue_invoice
from apps.compliance.services.pending import pending_summary, reservation_legal, resolution_health
from apps.compliance.services.sire import generate_sire, mark_submitted
from apps.compliance.services.tra import register_stay
from apps.compliance.tests.factories import InvoiceResolutionFactory
from apps.guests.tests.factories import ForeignGuestFactory, GuestFactory

pytestmark = pytest.mark.django_db


class TestResolutionHealth:
    def test_without_a_resolution_it_is_missing(self, hotel):
        assert resolution_health(hotel)["status"] == "missing"

    def test_a_healthy_resolution_reports_its_runway(self, hotel):
        InvoiceResolutionFactory(property=hotel, from_number=1, to_number=5000, current_number=100)

        health = resolution_health(hotel)

        assert (health["status"], health["next_number"], health["remaining"]) == ("ok", 101, 4900)
        assert health["days_left"] == 365

    @pytest.mark.parametrize(
        ("current", "valid_days", "status"),
        [(4600, 365, "warning"), (100, 20, "warning"), (5000, 365, "critical"), (100, -1, "critical")],
    )
    def test_running_out_or_expiring_is_flagged(self, hotel, current, valid_days, status):
        today = hotel.business_date
        InvoiceResolutionFactory(
            property=hotel,
            from_number=1,
            to_number=5000,
            current_number=current,
            valid_from=today - timedelta(days=400),
            valid_to=today + timedelta(days=valid_days),
        )

        assert resolution_health(hotel)["status"] == status


class TestInvoices:
    def test_departures_without_invoice_and_failed_documents_are_pending(
        self, hotel, resolution, make_finished_reservation, monkeypatch
    ):
        forgotten = make_finished_reservation()
        failing = {"status": "error", "message": "caído", "response": {}}
        monkeypatch.setattr(SimulatedEInvoiceProvider, "issue", lambda self, invoice, supplier: failing)
        failed = issue_invoice(make_finished_reservation())
        monkeypatch.undo()
        issue_invoice(make_finished_reservation())  # done: not pending
        make_finished_reservation(status="checked_in")  # still in house: not pending

        summary = pending_summary(hotel)

        items = {item["reservation_code"]: item for item in summary["invoices"]["items"]}
        assert set(items) == {forgotten.code, failed.reservation.code}
        assert items[forgotten.code]["status"] == "not_issued"
        assert items[forgotten.code]["total"] == "761600.00"
        assert (items[failed.reservation.code]["status"], items[failed.reservation.code]["invoice_id"]) == (
            "error",
            str(failed.pk),
        )
        assert summary["counts"]["invoices"] == 2

    def test_departures_before_the_go_live_date_are_not_pending(
        self, hotel, resolution, make_finished_reservation
    ):
        settings = get_settings(hotel)
        settings.go_live_date = hotel.business_date
        settings.save()
        make_finished_reservation(checkin=hotel.business_date - timedelta(days=5))

        assert pending_summary(hotel)["invoices"]["count"] == 0


class TestTra:
    def test_missing_data_and_in_house_stays_without_registration_are_pending(self, hotel, room):
        booker = GuestFactory(organization=hotel.organization, document_type="", document_number="")
        reservation = ReservationFactory(property=hotel, booker=booker, status="checked_in")
        stay = StayFactory(reservation=reservation, room=room, status="checked_in")
        register_stay(stay)
        unregistered = StayFactory(
            reservation=ReservationFactory(property=hotel, status="checked_in"), status="checked_in"
        )

        summary = pending_summary(hotel)

        statuses = {item["reservation_code"]: item for item in summary["tra"]["items"]}
        assert statuses[reservation.code]["status"] == "pending"
        assert statuses[reservation.code]["missing_fields"] == [
            "tipo_identificacion",
            "numero_identificacion",
        ]
        assert statuses[unregistered.reservation.code]["status"] == "not_registered"
        assert summary["counts"]["tra"] == 2


class TestSire:
    def test_files_to_upload_and_days_without_a_file_are_pending(self, hotel):
        guest = ForeignGuestFactory(organization=hotel.organization, birth_date=date(1980, 1, 1))
        yesterday = hotel.business_date - timedelta(days=1)
        reservation = ReservationFactory(
            property=hotel,
            booker=guest,
            status="checked_in",
            checkin_date=yesterday - timedelta(days=1),
            checkout_date=yesterday + timedelta(days=3),
        )
        StayFactory(reservation=reservation, status="checked_in")
        report = generate_sire(hotel, yesterday, yesterday)  # nothing that day: the entry was the day before

        summary = pending_summary(hotel)

        assert [r["report_id"] for r in summary["sire"]["reports"]] == [str(report.pk)]
        assert summary["sire"]["unreported_days"] == [(yesterday - timedelta(days=1)).isoformat()]
        mark_submitted(report)
        assert pending_summary(hotel)["sire"]["reports"] == []
        assert SireReport.objects.get().status == "acknowledged"


class TestReservation:
    def test_the_legal_summary_of_a_reservation(
        self, hotel, resolution, make_finished_reservation, extras_tax
    ):
        from apps.compliance.tests.factories import post
        from apps.finance.models import Folio

        guest = GuestFactory(organization=hotel.organization, document_type="", document_number="")
        reservation = make_finished_reservation(booker=guest)
        invoice = issue_invoice(reservation)
        post(
            Folio.objects.get(reservation=reservation),
            kind="extra",
            amount="10000",
            description="Minibar",
            tax=extras_tax,
            tax_amount="1900",
        )

        legal = reservation_legal(reservation)

        assert [i["id"] for i in legal["invoices"]] == [str(invoice.pk)]
        assert legal["uninvoiced"] == {"count": 1, "total": "11900.00"}
        assert legal["can_issue"] is True
        assert "final_consumer" in legal["warnings"]
        assert legal["tra"] == []
