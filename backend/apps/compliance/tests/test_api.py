"""Staff API of compliance (`/api/v1/compliance/`): permissions, isolation and the main flows."""

from datetime import date

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.compliance.models import Invoice, InvoiceResolution, TraRegistration
from apps.compliance.services.invoices import issue_invoice
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.guests.tests.factories import ForeignGuestFactory

pytestmark = pytest.mark.django_db

BASE = "/api/v1/compliance"


@pytest.fixture
def front_desk_api(api_for, make_member, hotel):
    return api_for(make_member("front_desk"), hotel)


@pytest.fixture
def owner_api(api_for, owner, hotel):
    return api_for(owner, hotel)


class TestResolutions:
    def payload(self, **extra):
        return {
            "prefix": "FE",
            "resolution_number": "18764000000123",
            "from_number": 1,
            "to_number": 1000,
            "valid_from": "2026-01-01",
            "valid_to": "2027-12-31",
            "technical_key": "abc",
            "environment": "test",
            **extra,
        }

    def test_creating_an_active_resolution_retires_the_previous_one(self, owner_api, resolution):
        response = owner_api.post(f"{BASE}/resolutions/", self.payload(), format="json")

        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["prefix"], body["next_number"], body["remaining"], body["is_active"]) == (
            "FE",
            1,
            1000,
            True,
        )
        resolution.refresh_from_db()
        assert resolution.is_active is False

    def test_an_inverted_range_is_rejected(self, owner_api, hotel):
        response = owner_api.post(
            f"{BASE}/resolutions/", self.payload(from_number=10, to_number=5), format="json"
        )

        assert response.status_code == 400
        assert "to_number" in response.json()["fields"]

    def test_the_numbering_of_a_resolution_in_use_cannot_change(
        self, owner_api, resolution, make_finished_reservation
    ):
        issue_invoice(make_finished_reservation())

        response = owner_api.patch(f"{BASE}/resolutions/{resolution.pk}/", {"from_number": 50}, format="json")
        assert response.status_code == 400
        assert "from_number" in response.json()["fields"]
        assert owner_api.delete(f"{BASE}/resolutions/{resolution.pk}/").status_code == 409

    def test_the_front_desk_sees_but_does_not_configure(self, front_desk_api, resolution):
        assert front_desk_api.get(f"{BASE}/resolutions/").status_code == 200
        response = front_desk_api.post(f"{BASE}/resolutions/", self.payload(), format="json")
        assert (response.status_code, response.json()["permission"]) == (403, "compliance.settings")


class TestInvoices:
    def test_issue_list_and_detail(self, front_desk_api, resolution, make_finished_reservation):
        reservation = make_finished_reservation()

        created = front_desk_api.post(
            f"{BASE}/invoices/issue/", {"reservation_id": str(reservation.pk)}, format="json"
        )

        assert created.status_code == 201, created.json()
        invoice = created.json()
        assert (invoice["number"], invoice["status"], invoice["total"], invoice["kind"]) == (
            "SETT1",
            "accepted",
            "761600.00",
            "invoice",
        )
        assert invoice["reservation_code"] == reservation.code
        assert invoice["lines"][0]["description"] == "Alojamiento Estándar · 2 noches"
        assert invoice["validation_url"].endswith(invoice["cufe"])
        listing = front_desk_api.get(f"{BASE}/invoices/", {"status": "accepted"}).json()
        assert [row["number"] for row in listing["results"]] == ["SETT1"]
        assert front_desk_api.get(f"{BASE}/invoices/", {"q": reservation.code}).json()["count"] == 1
        assert front_desk_api.get(f"{BASE}/invoices/", {"q": "nada"}).json()["count"] == 0

    def test_issuing_twice_is_a_conflict(self, front_desk_api, resolution, make_finished_reservation):
        reservation = make_finished_reservation()
        front_desk_api.post(f"{BASE}/invoices/issue/", {"reservation_id": str(reservation.pk)}, format="json")

        response = front_desk_api.post(
            f"{BASE}/invoices/issue/", {"reservation_id": str(reservation.pk)}, format="json"
        )

        assert (response.status_code, response.json()["code"]) == (409, "nothing_to_invoice")

    def test_a_reservation_of_another_hotel_cannot_be_invoiced(
        self, front_desk_api, resolution, organization
    ):
        other = ReservationFactory(property=PropertyFactory(organization=organization))

        response = front_desk_api.post(
            f"{BASE}/invoices/issue/", {"reservation_id": str(other.pk)}, format="json"
        )

        assert response.status_code == 404

    def test_pdf_and_xml_downloads(self, front_desk_api, resolution, make_finished_reservation):
        invoice = issue_invoice(make_finished_reservation())

        pdf = front_desk_api.get(f"{BASE}/invoices/{invoice.pk}/pdf/")
        xml = front_desk_api.get(f"{BASE}/invoices/{invoice.pk}/xml/", {"download": "1"})

        assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
        assert b"".join(pdf.streaming_content).startswith(b"%PDF")
        assert xml.status_code == 200 and xml["Content-Type"] == "application/xml"
        assert (
            "attachment" in xml["Content-Disposition"] and "factura-SETT1.xml" in xml["Content-Disposition"]
        )

    def test_the_credit_note_needs_the_void_permission_and_a_confirmation(
        self, front_desk_api, owner_api, resolution, make_finished_reservation
    ):
        invoice = issue_invoice(make_finished_reservation())
        url = f"{BASE}/invoices/{invoice.pk}/credit-note/"

        denied = front_desk_api.post(url, {"reason": "Error", "confirm": True}, format="json")
        unconfirmed = owner_api.post(url, {"reason": "Error"}, format="json")
        done = owner_api.post(url, {"reason": "Datos errados", "confirm": True}, format="json")

        assert (denied.status_code, denied.json()["permission"]) == (403, "compliance.void_invoice")
        assert (unconfirmed.status_code, unconfirmed.json()["code"]) == (400, "confirmation_required")
        assert done.status_code == 201
        assert (done.json()["kind"], done.json()["number"], done.json()["related_number"]) == (
            "credit_note",
            "NC1",
            "SETT1",
        )
        detail = owner_api.get(f"{BASE}/invoices/{invoice.pk}/").json()
        assert detail["status"] == "cancelled"
        assert [note["number"] for note in detail["credit_notes"]] == ["NC1"]

    def test_retrying_an_accepted_invoice_is_a_conflict(
        self, front_desk_api, resolution, make_finished_reservation
    ):
        invoice = issue_invoice(make_finished_reservation())

        response = front_desk_api.post(f"{BASE}/invoices/{invoice.pk}/retry/")

        assert (response.status_code, response.json()["code"]) == (409, "invalid_state")


class TestSire:
    @pytest.fixture
    def foreign_stay(self, hotel):
        from apps.compliance.services.config import get_settings

        settings = get_settings(hotel)
        settings.sire_establishment_code = "123456"
        settings.save()
        guest = ForeignGuestFactory(organization=hotel.organization, birth_date=date(1980, 1, 1))
        reservation = ReservationFactory(
            property=hotel,
            booker=guest,
            status="checked_out",
            checkin_date=date(2026, 10, 10),
            checkout_date=date(2026, 10, 12),
        )
        return StayFactory(reservation=reservation, status="checked_out")

    def test_generate_download_and_mark_submitted(self, front_desk_api, foreign_stay):
        created = front_desk_api.post(
            f"{BASE}/sire/generate/", {"start": "2026-10-10", "end": "2026-10-12"}, format="json"
        )

        assert created.status_code == 201, created.json()
        report = created.json()
        assert (report["records_count"], report["missing_count"], report["status"]) == (2, 0, "generated")
        detail = front_desk_api.get(f"{BASE}/sire/{report['id']}/").json()
        assert [r["movement"] for r in detail["records"]] == ["E", "S"]
        download = front_desk_api.get(f"{BASE}/sire/{report['id']}/download/")
        assert download.status_code == 200
        assert download["Content-Type"].startswith("text/plain")
        assert len(b"".join(download.streaming_content).decode().splitlines()) == 2
        submitted = front_desk_api.post(f"{BASE}/sire/{report['id']}/mark-submitted/", {}, format="json")
        assert (submitted.status_code, submitted.json()["status"]) == (200, "acknowledged")
        assert front_desk_api.get(f"{BASE}/sire/").json()["count"] == 1

    def test_an_invalid_period_is_a_validation_error(self, front_desk_api, hotel):
        response = front_desk_api.post(
            f"{BASE}/sire/generate/", {"start": "2026-10-12", "end": "2026-10-10"}, format="json"
        )

        assert (response.status_code, response.json()["code"]) == (400, "invalid_period")

    def test_housekeeping_has_no_access(self, api_for, make_member, hotel):
        response = api_for(make_member("housekeeping"), hotel).get(f"{BASE}/sire/")

        assert (response.status_code, response.json()["permission"]) == (403, "compliance.view")


class TestTra:
    def test_register_a_stay_by_hand_and_list(self, front_desk_api, hotel, room):
        reservation = ReservationFactory(property=hotel, status="checked_in")
        stay = StayFactory(reservation=reservation, room=room, status="checked_in")

        created = front_desk_api.post(f"{BASE}/tra/register/", {"stay_id": str(stay.pk)}, format="json")

        assert created.status_code == 201, created.json()
        [registration] = created.json()
        assert (registration["status"], registration["is_main"]) == ("registered", True)
        assert registration["tra_number"].startswith("TRA-")
        listing = front_desk_api.get(f"{BASE}/tra/", {"status": "registered"}).json()
        assert listing["count"] == 1 and listing["results"][0]["room"] == room.number

    def test_retrying_a_registered_guest_is_a_conflict(self, front_desk_api, hotel, room):
        stay = StayFactory(
            reservation=ReservationFactory(property=hotel, status="checked_in"),
            room=room,
            status="checked_in",
        )
        front_desk_api.post(f"{BASE}/tra/register/", {"stay_id": str(stay.pk)}, format="json")
        registration = TraRegistration.objects.get()

        response = front_desk_api.post(f"{BASE}/tra/{registration.pk}/retry/")

        assert (response.status_code, response.json()["code"]) == (409, "invalid_state")


class TestSettingsAndPending:
    def test_settings_read_and_update(self, owner_api, front_desk_api, hotel):
        read = front_desk_api.get(f"{BASE}/settings/").json()
        assert read["auto_issue_invoices"] is True
        assert read["effective"]["tra_establishment_id"] == "98765"
        assert read["effective"]["sire_city_code"] == "13001"  # derived from the hotel's city (Cartagena)
        assert read["defaults"]["sire_document_codes"]["PA"] == "3"
        assert read["integrations"]["einvoice"]["mode"] == "simulated"

        denied = front_desk_api.patch(f"{BASE}/settings/", {"auto_issue_invoices": False}, format="json")
        assert (denied.status_code, denied.json()["permission"]) == (403, "compliance.settings")

        updated = owner_api.patch(
            f"{BASE}/settings/",
            {
                "auto_issue_invoices": False,
                "sire_city_code": "13430",
                "sire_country_codes": {"us": "840"},
                "go_live_date": "2026-09-01",
            },
            format="json",
        )
        assert updated.status_code == 200, updated.json()
        body = updated.json()
        assert (body["auto_issue_invoices"], body["effective"]["sire_city_code"], body["go_live_date"]) == (
            False,
            "13430",
            "2026-09-01",
        )
        assert body["sire_country_codes"] == {"US": "840"}

    def test_code_tables_must_map_codes_to_text(self, owner_api, hotel):
        response = owner_api.patch(f"{BASE}/settings/", {"sire_document_codes": {"PA": 3}}, format="json")

        assert response.status_code == 400
        assert "sire_document_codes" in response.json()["fields"]

    def test_pending_summary_and_counts(self, front_desk_api, resolution, make_finished_reservation):
        make_finished_reservation()

        full = front_desk_api.get(f"{BASE}/pending/").json()
        counts = front_desk_api.get(f"{BASE}/pending/", {"summary": "1"}).json()

        assert full["counts"]["invoices"] == 1 and full["resolution"]["status"] == "ok"
        assert counts == {"counts": full["counts"], "resolution_status": "ok"}

    def test_the_legal_summary_of_a_reservation(
        self, front_desk_api, resolution, make_finished_reservation, organization
    ):
        reservation = make_finished_reservation()
        issue_invoice(reservation)

        body = front_desk_api.get(f"{BASE}/reservations/{reservation.pk}/").json()

        assert [i["number"] for i in body["invoices"]] == ["SETT1"]
        assert body["can_issue"] is False
        other = ReservationFactory(property=PropertyFactory(organization=organization))
        assert front_desk_api.get(f"{BASE}/reservations/{other.pk}/").status_code == 404


class TestIsolation:
    def test_another_organization_sees_nothing(
        self, api_for, make_member, resolution, make_finished_reservation
    ):
        invoice = issue_invoice(make_finished_reservation())
        stranger_org = OrganizationFactory()
        stranger_prop = PropertyFactory(organization=stranger_org)
        from apps.accounts.services import ensure_system_roles

        ensure_system_roles(stranger_org)
        stranger = api_for(make_member("owner", org=stranger_org), stranger_prop)

        assert stranger.get(f"{BASE}/invoices/").json()["count"] == 0
        assert stranger.get(f"{BASE}/invoices/{invoice.pk}/").status_code == 404
        assert stranger.get(f"{BASE}/invoices/{invoice.pk}/pdf/").status_code == 404
        assert stranger.get(f"{BASE}/resolutions/").json()["count"] == 0
        assert (
            stranger.post(
                f"{BASE}/invoices/{invoice.pk}/credit-note/", {"reason": "x", "confirm": True}, format="json"
            ).status_code
            == 404
        )

    def test_anonymous_requests_are_rejected(self, public_api, hotel):
        response = public_api.get(f"{BASE}/invoices/", HTTP_X_PROPERTY_ID=str(hotel.pk))

        assert response.status_code == 401


def test_the_resolution_of_the_credit_notes_is_created_on_demand(
    owner_api, resolution, make_finished_reservation
):
    invoice = issue_invoice(make_finished_reservation())
    owner_api.post(
        f"{BASE}/invoices/{invoice.pk}/credit-note/", {"reason": "Error", "confirm": True}, format="json"
    )

    kinds = sorted(InvoiceResolution.objects.values_list("document_kind", flat=True))
    assert kinds == ["credit_note", "invoice"]
    assert Invoice.objects.filter(kind="credit_note").count() == 1
