"""Phase A guest services (plan Step 5): upsert (document, then email), update, add_document."""

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.core.tests.factories import OrganizationFactory
from apps.guests.models import Guest
from apps.guests.services import add_document, update_guest, upsert_guest
from apps.guests.tests.factories import GuestFactory
from apps.guests.types import GuestInput

pytestmark = pytest.mark.django_db


class TestUpsertGuest:
    def test_creates_a_guest_when_nothing_matches(self, organization):
        guest = upsert_guest(
            organization,
            GuestInput(
                first_name=" Ana ",
                last_name="Pérez",
                email=" Ana.Perez@Example.COM ",
                phone="+573001112233",
                document_type="CC",
                document_number="1020304050",
                nationality="co",
                country_of_residence="CO",
                birth_date=date(1990, 5, 1),
                language="es",
                marketing_consent=True,
                data_processing_consent=True,
            ),
        )
        guest.refresh_from_db()
        assert (guest.organization, guest.first_name, guest.email, guest.nationality) == (
            organization,
            "Ana",
            "ana.perez@example.com",
            "CO",
        )
        assert (guest.document_type, guest.document_number, guest.birth_date) == (
            "CC",
            "1020304050",
            date(1990, 5, 1),
        )
        assert guest.marketing_consent is True and guest.data_processing_consent_at is not None

    def test_matches_by_document_and_fills_without_blanking(self, organization):
        existing = GuestFactory(
            organization=organization,
            document_type="PA",
            document_number="X123",
            email="old@example.com",
            phone="+15550000",
        )
        guest = upsert_guest(
            organization,
            GuestInput(
                first_name="John",
                last_name="Smith",
                document_type="PA",
                document_number="X123",
                phone="",
                city_of_residence="Austin",
            ),
        )
        assert guest.pk == existing.pk
        guest.refresh_from_db()
        assert (guest.email, guest.phone, guest.city_of_residence) == (
            "old@example.com",
            "+15550000",
            "Austin",
        )
        assert Guest.objects.filter(organization=organization).count() == 1

    def test_matches_by_email_ignoring_case_when_there_is_no_document(self, organization):
        existing = GuestFactory(organization=organization, email="camila@example.com")
        guest = upsert_guest(
            organization, GuestInput(first_name="Camila", last_name="R", email="CAMILA@example.com")
        )
        assert guest.pk == existing.pk

    def test_falls_back_to_email_for_a_guest_without_document_and_fills_it(self, organization):
        existing = GuestFactory(
            organization=organization, email="nodoc@example.com", document_type="", document_number=""
        )
        guest = upsert_guest(
            organization,
            GuestInput(
                first_name="Sin",
                last_name="Doc",
                email="nodoc@example.com",
                document_type="CC",
                document_number="777",
            ),
        )
        assert guest.pk == existing.pk
        guest.refresh_from_db()
        assert (guest.document_type, guest.document_number) == ("CC", "777")

    def test_a_different_document_is_a_different_guest_even_with_the_same_email(self, organization):
        GuestFactory(
            organization=organization, email="shared@example.com", document_type="CC", document_number="111"
        )
        guest = upsert_guest(
            organization,
            GuestInput(
                first_name="Otra",
                last_name="Persona",
                email="shared@example.com",
                document_type="CC",
                document_number="222",
            ),
        )
        assert (
            Guest.objects.filter(email="shared@example.com").count() == 2 and guest.document_number == "222"
        )

    def test_merged_guests_are_never_matched(self, organization):
        primary = GuestFactory(organization=organization, email="p@example.com")
        GuestFactory(organization=organization, email="dup@example.com", merged_into=primary)
        guest = upsert_guest(
            organization, GuestInput(first_name="Dup", last_name="X", email="dup@example.com")
        )
        assert guest.merged_into is None and Guest.objects.filter(email="dup@example.com").count() == 2

    def test_guests_are_per_organization(self, organization):
        GuestFactory(organization=OrganizationFactory(), document_type="CC", document_number="999")
        guest = upsert_guest(
            organization, GuestInput(first_name="A", last_name="B", document_type="CC", document_number="999")
        )
        assert guest.organization == organization

    def test_consent_timestamp_is_kept_once_given(self, organization):
        guest = upsert_guest(
            organization,
            GuestInput(first_name="A", last_name="B", email="a@example.com", data_processing_consent=True),
        )
        first = guest.data_processing_consent_at
        again = upsert_guest(
            organization,
            GuestInput(first_name="A", last_name="B", email="a@example.com", data_processing_consent=True),
        )
        assert again.data_processing_consent_at == first


class TestUpdateGuest:
    def test_updates_fields_and_audits_the_diff(self, organization, owner):
        guest = GuestFactory(organization=organization, is_vip=False, notes="")
        updated = update_guest(
            guest,
            {"is_vip": True, "notes": "Prefiere piso alto", "tags": ["frecuente"]},
            source="user",
            actor=owner,
        )
        updated.refresh_from_db()
        assert (updated.is_vip, updated.notes, updated.tags) == (True, "Prefiere piso alto", ["frecuente"])
        event = AuditEvent.objects.get(action="guests.guest_updated")
        assert event.changes["is_vip"] == [False, True] and event.actor == owner
        assert event.organization == organization

    def test_rejects_unknown_or_protected_fields(self, organization):
        guest = GuestFactory(organization=organization)
        for bad in ({"organization": None}, {"merged_into": None}, {"shoe_size": 42}):
            with pytest.raises(DomainError) as exc:
                update_guest(guest, bad)
            assert exc.value.code == "invalid_field"


def test_add_document_stores_the_file(organization, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    guest = GuestFactory(organization=organization)
    upload = SimpleUploadedFile("pasaporte.png", b"\x89PNG fake", content_type="image/png")
    document = add_document(guest, kind="passport", file=upload, uploaded_via="portal")
    document.refresh_from_db()
    assert (document.guest, document.kind, document.uploaded_via) == (guest, "passport", "portal")
    assert document.file.read() == b"\x89PNG fake"
