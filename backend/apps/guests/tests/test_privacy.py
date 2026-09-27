"""Habeas Data (Ley 1581 de 2012): export of a guest's personal data and anonymization."""

import json
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.guests.models import GuestDocument
from apps.guests.services import add_document, anonymize_guest, export_guest, merge_guests, update_guest
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    return settings.PRIVATE_MEDIA_ROOT


@pytest.fixture
def guest(organization):
    return GuestFactory(
        organization=organization,
        first_name="Ana María",
        last_name="Pérez",
        email="ana@example.com",
        phone="+573001112233",
        document_type="CC",
        document_number="52123456",
        birth_date=date(1990, 5, 1),
        address="Calle 1 # 2-3",
        notes="Alérgica al maní",
        preferences={"diet": "sin maní"},
        tags=["frecuente"],
        is_vip=True,
        marketing_consent=True,
    )


class TestAnonymize:
    def test_erases_personal_data_and_keeps_statistics(self, guest, owner):
        anonymize_guest(guest, actor=owner)

        guest.refresh_from_db()
        assert guest.full_name == "Huésped anonimizado"
        cleared = (guest.email, guest.phone, guest.document_type, guest.document_number, guest.address,
                   guest.notes, guest.city_of_residence)  # fmt: skip
        assert cleared == ("",) * 7
        assert (guest.birth_date, guest.preferences, guest.tags) == (None, {}, [])
        assert (guest.is_vip, guest.marketing_consent) == (False, False)
        assert (guest.nationality, guest.country_of_residence) == ("CO", "CO")  # reports by nationality
        assert guest.anonymized_at is not None

    def test_deletes_identity_documents_and_their_files(
        self, guest, owner, django_capture_on_commit_callbacks
    ):
        document = add_document(guest, kind="id_front", file=SimpleUploadedFile("c.png", PNG))
        path = document.file.path

        with django_capture_on_commit_callbacks(execute=True):  # files go only once the erase is committed
            anonymize_guest(guest, actor=owner)

        assert not GuestDocument.objects.filter(pk=document.pk).exists()
        with pytest.raises(FileNotFoundError):
            open(path, "rb")

    def test_keeps_the_reservation_history_attached(self, guest, prop, owner):
        reservation = ReservationFactory(property=prop, booker=guest)

        anonymize_guest(guest, actor=owner)

        reservation.refresh_from_db()
        assert reservation.booker_id == guest.pk

    def test_also_erases_the_records_merged_into_the_guest(self, guest, organization, owner):
        old = GuestFactory(organization=organization, email="ana.vieja@example.com")
        merge_guests(guest, old, actor=owner)

        anonymize_guest(guest, actor=owner)

        old.refresh_from_db()
        assert old.email == "" and old.anonymized_at is not None

    def test_a_merged_record_is_erased_through_the_survivor(self, guest, organization, owner):
        # The survivor holds the merged data too (filled fields, documents): erasing only the old record
        # would leave the person's data behind while looking done.
        old = GuestFactory(organization=organization, email="ana.vieja@example.com")
        merge_guests(guest, old, actor=owner)

        with pytest.raises(DomainError) as exc:
            anonymize_guest(old, actor=owner)

        assert (exc.value.code, exc.value.status_code) == ("guest_merged", 409)
        assert exc.value.extra["guest_id"] == str(guest.pk)
        old.refresh_from_db()
        assert old.anonymized_at is None and old.email == "ana.vieja@example.com"

    def test_audits_without_personal_values_and_leaves_no_trace_in_earlier_diffs(self, guest, owner):
        update_guest(guest, {"email": "nueva@example.com"}, actor=owner)

        anonymize_guest(guest, actor=owner)

        events = AuditEvent.objects.filter(target_id=str(guest.pk))
        assert {"guests.guest_updated", "guests.anonymized"} <= set(events.values_list("action", flat=True))
        dump = json.dumps([e.changes for e in events]) + " ".join(e.summary for e in events)
        for secret in ("ana@example.com", "nueva@example.com", "52123456", "+573001112233", "Pérez"):
            assert secret not in dump

    def test_cannot_run_twice(self, guest, owner):
        anonymize_guest(guest, actor=owner)
        with pytest.raises(DomainError) as exc:
            anonymize_guest(guest, actor=owner)
        assert (exc.value.code, exc.value.status_code) == ("already_anonymized", 409)


class TestExport:
    def test_contains_profile_documents_reservations_and_merged_records(
        self, guest, prop, organization, owner
    ):
        add_document(guest, kind="passport", file=SimpleUploadedFile("p.png", PNG), uploaded_via="portal")
        booked = ReservationFactory(property=prop, booker=guest, code="HT-EXP001")
        StayFactory(reservation=ReservationFactory(property=prop, code="HT-EXP002"), occupants=[guest])
        old = GuestFactory(organization=organization, email="vieja@example.com")
        merge_guests(guest, old, actor=owner)

        data = export_guest(guest)

        json.dumps(data)  # JSON-safe
        assert data["guest"]["email"] == "ana@example.com"
        assert data["guest"]["document_number"] == "52123456"
        assert data["guest"]["birth_date"] == "1990-05-01"
        assert data["organization"]["name"] == organization.name
        assert [(d["kind"], d["uploaded_via"]) for d in data["documents"]] == [("passport", "portal")]
        roles = {(r["code"], r["role"]) for r in data["reservations"]}
        assert roles == {(booked.code, "booker"), ("HT-EXP002", "occupant")}
        assert [m["email"] for m in data["merged_records"]] == ["vieja@example.com"]
        assert "exported_at" in data
