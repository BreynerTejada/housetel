"""merge_guests (plan §C / B3): every relation of the duplicate — including other apps' FKs and M2Ms, found
generically through Guest._meta.related_objects — moves to the primary; empty fields are filled; the
duplicate is marked `merged_into`."""

from datetime import UTC, datetime

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.bookings.models import Reservation
from apps.bookings.tests.factories import ReservationFactory, ReservationGroupFactory, StayFactory
from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.core.tests.factories import OrganizationFactory
from apps.finance.tests.factories import FolioFactory
from apps.guests.models import Guest
from apps.guests.services import add_document, anonymize_guest, find_duplicates, merge_guests, upsert_guest
from apps.guests.tests.factories import GuestFactory
from apps.guests.types import GuestInput

pytestmark = pytest.mark.django_db


@pytest.fixture
def pair(organization):
    primary = GuestFactory(organization=organization, first_name="Ana", last_name="Pérez")
    duplicate = GuestFactory(organization=organization, first_name="Ana", last_name="Perez")
    return primary, duplicate


class TestRelations:
    def test_moves_bookers_and_stay_occupants_of_other_apps_and_marks_the_duplicate(self, pair, prop, owner):
        primary, duplicate = pair
        booked = ReservationFactory(property=prop, booker=duplicate)
        shared_stay = StayFactory(reservation=ReservationFactory(property=prop), occupants=[duplicate])

        merge_guests(primary, duplicate, actor=owner)

        assert Reservation.objects.get(pk=booked.pk).booker_id == primary.pk
        assert list(shared_stay.occupants.all()) == [primary]
        duplicate.refresh_from_db()
        assert duplicate.merged_into_id == primary.pk

    def test_a_stay_with_both_guests_keeps_a_single_occupant(self, pair, prop, owner):
        primary, duplicate = pair
        stay = StayFactory(reservation=ReservationFactory(property=prop), occupants=[primary, duplicate])

        merge_guests(primary, duplicate, actor=owner)

        assert list(stay.occupants.all()) == [primary]

    def test_every_other_relation_follows_the_primary(self, pair, prop, owner, settings, tmp_path):
        settings.PRIVATE_MEDIA_ROOT = tmp_path
        primary, duplicate = pair
        folio = FolioFactory(reservation=ReservationFactory(property=prop, booker=primary), guest=duplicate)
        group = ReservationGroupFactory(property=prop, contact_guest=duplicate)
        document = add_document(
            duplicate, kind="passport", file=SimpleUploadedFile("p.png", b"\x89PNG\r\n\x1a\nfake")
        )
        merged_earlier = GuestFactory(organization=primary.organization, merged_into=duplicate)

        merge_guests(primary, duplicate, actor=owner)

        folio.refresh_from_db()
        group.refresh_from_db()
        document.refresh_from_db()
        merged_earlier.refresh_from_db()
        assert (folio.guest_id, group.contact_guest_id, document.guest_id) == (primary.pk,) * 3
        assert merged_earlier.merged_into_id == primary.pk  # chains collapse onto the survivor


class TestFields:
    def test_fills_empty_fields_and_keeps_the_primary_values(self, organization, owner):
        primary = GuestFactory(
            organization=organization, email="ana@example.com", phone="", city_of_residence="",
            birth_date=None, tags=["frecuente"], preferences={"pillow": "firme"}, notes="Prefiere piso alto",
            is_vip=False, data_processing_consent_at=None,
        )  # fmt: skip
        consent = datetime(2025, 1, 2, 15, 0, tzinfo=UTC)
        duplicate = GuestFactory(
            organization=organization, email="otro@example.com", phone="+573001112233",
            city_of_residence="Medellín", birth_date=datetime(1990, 5, 1).date(),
            tags=["corporativo", "frecuente"], preferences={"pillow": "suave", "diet": "vegetariana"},
            notes="Alérgica al maní", is_vip=True, data_processing_consent_at=consent,
        )  # fmt: skip

        merge_guests(primary, duplicate, actor=owner)

        primary.refresh_from_db()
        assert primary.email == "ana@example.com"
        assert (primary.phone, primary.city_of_residence) == ("+573001112233", "Medellín")
        assert primary.birth_date == datetime(1990, 5, 1).date()
        assert primary.tags == ["frecuente", "corporativo"]
        assert primary.preferences == {"pillow": "firme", "diet": "vegetariana"}
        assert "Prefiere piso alto" in primary.notes and "Alérgica al maní" in primary.notes
        assert primary.is_vip is True and primary.data_processing_consent_at == consent

    def test_the_document_moves_to_a_primary_without_one(self, organization, owner):
        primary = GuestFactory(organization=organization, document_type="", document_number="")
        duplicate = GuestFactory(organization=organization, document_type="CC", document_number="52123456")

        merge_guests(primary, duplicate, actor=owner)

        primary.refresh_from_db()
        assert (primary.document_type, primary.document_number) == ("CC", "52123456")
        found = upsert_guest(
            organization,
            GuestInput(first_name="Ana", last_name="P", document_type="CC", document_number="52123456"),
        )
        assert found.pk == primary.pk

    def test_the_duplicate_document_still_leads_to_the_primary(self, organization, owner):
        primary = GuestFactory(organization=organization, document_type="CC", document_number="111")
        duplicate = GuestFactory(organization=organization, document_type="PA", document_number="X9")

        merge_guests(primary, duplicate, actor=owner)
        found = upsert_guest(
            organization,
            GuestInput(first_name="Ana", last_name="P", document_type="PA", document_number="X9"),
        )

        assert found.pk == primary.pk
        primary.refresh_from_db()
        assert (primary.document_type, primary.document_number) == ("CC", "111")  # never overwritten
        assert Guest.objects.filter(organization=organization).count() == 2


class TestRules:
    def test_rejects_guests_of_different_organizations(self, organization, owner):
        with pytest.raises(DomainError) as exc:
            merge_guests(
                GuestFactory(organization=organization),
                GuestFactory(organization=OrganizationFactory()),
                actor=owner,
            )
        assert exc.value.code == "different_organization"

    def test_rejects_merging_a_guest_into_itself(self, organization, owner):
        guest = GuestFactory(organization=organization)
        with pytest.raises(DomainError) as exc:
            merge_guests(guest, guest, actor=owner)
        assert exc.value.code == "same_guest"

    def test_rejects_anonymized_guests(self, organization, owner):
        # Merging fills the primary's empty fields from the duplicate: an erased record (Habeas Data) must
        # never get personal data back, whoever calls the contract.
        erased = GuestFactory(organization=organization)
        anonymize_guest(erased, actor=owner)
        other = GuestFactory(organization=organization, email="ana@example.com", phone="+573001112233")

        for primary, duplicate in ((erased, other), (other, erased)):
            with pytest.raises(DomainError) as exc:
                merge_guests(primary, duplicate, actor=owner)
            assert (exc.value.code, exc.value.status_code) == ("guest_anonymized", 409)

        erased.refresh_from_db()
        other.refresh_from_db()
        assert (erased.email, erased.phone) == ("", "")
        assert (erased.merged_into_id, other.merged_into_id) == (None, None)

    def test_rejects_guests_already_merged(self, pair, owner):
        primary, duplicate = pair
        merge_guests(primary, duplicate, actor=owner)
        with pytest.raises(DomainError) as exc:
            merge_guests(primary, duplicate, actor=owner)
        assert (exc.value.code, exc.value.status_code) == ("already_merged", 409)

    def test_audits_the_merge_without_personal_values(self, pair, prop, owner):
        primary, duplicate = pair
        ReservationFactory(property=prop, booker=duplicate)

        merge_guests(primary, duplicate, actor=owner)

        event = AuditEvent.objects.get(action="guests.merged")
        assert (event.target_id, event.actor, event.organization) == (
            str(primary.pk),
            owner,
            primary.organization,
        )
        assert event.changes["duplicate_id"] == str(duplicate.pk)
        assert event.changes["relations"] == {"bookings.Reservation.booker": 1}
        assert duplicate.email not in str(event.changes)

    def test_merged_guest_no_longer_shows_up_as_a_duplicate(self, organization, owner):
        primary = GuestFactory(organization=organization, email="same@example.com")
        duplicate = GuestFactory(organization=organization, email="same@example.com")
        assert find_duplicates(primary) == [duplicate]
        merge_guests(primary, duplicate, actor=owner)
        assert find_duplicates(primary) == []
