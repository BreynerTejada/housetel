"""Normalization of guest data (plan B3): names in title case, email lowercase, phone E.164 (CO by default),
document without dots or spaces. Applied by upsert_guest and update_guest."""

import pytest

from apps.core.models import AuditEvent
from apps.guests.models import Guest
from apps.guests.normalization import normalize_document, normalize_name, normalize_phone
from apps.guests.services import update_guest, upsert_guest
from apps.guests.tests.factories import GuestFactory
from apps.guests.types import GuestInput


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ana maría", "Ana María"),
        ("ANA MARÍA", "Ana María"),
        ("  juan   pablo  ", "Juan Pablo"),
        ("maría de los ángeles", "María de los Ángeles"),
        ("DE LA HOZ", "De la Hoz"),  # a particle that opens the name is capitalized
        ("pedro y pablo", "Pedro y Pablo"),
        ("o'brien", "O'Brien"),
        ("jean-luc", "Jean-Luc"),
        ("McDonald", "McDonald"),  # deliberate mixed case is kept
        ("DiCaprio", "DiCaprio"),
        ("", ""),
    ],
)
def test_normalize_name(raw, expected):
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "region", "expected"),
    [
        ("300 123 4567", "CO", "+573001234567"),
        ("(300) 123-4567", "CO", "+573001234567"),
        ("+57 300 123 4567", "CO", "+573001234567"),
        ("57 300 123 4567", "CO", "+573001234567"),
        ("+34 612 345 678", "CO", "+34612345678"),  # an explicit country code wins over the region
        ("(212) 555-0123", "US", "+12125550123"),
        ("3001234567", "US", "+573001234567"),  # not valid in the hint region → tried as Colombian
        ("", "CO", ""),
        ("  ", "CO", ""),
        ("12", "CO", "12"),  # unusable input is kept (trimmed) rather than lost
        ("ext. 5", "CO", "ext. 5"),
    ],
)
def test_normalize_phone(raw, region, expected):
    assert normalize_phone(raw, region=region) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.020.304.050", "1020304050"),
        (" 1 020 304 050 ", "1020304050"),
        ("x 123 456", "X123456"),
        ("900.123.456-7", "900123456-7"),  # the NIT check digit keeps its dash
        ("", ""),
    ],
)
def test_normalize_document(raw, expected):
    assert normalize_document(raw) == expected


@pytest.mark.django_db
class TestUpsertNormalizes:
    def test_new_guest_is_stored_normalized(self, organization):
        guest = upsert_guest(
            organization,
            GuestInput(
                first_name="  ANA maría ",
                last_name="pérez GÓMEZ",
                email=" Ana.Perez@Example.COM",
                phone="300 123 4567",
                document_type="cc",
                document_number="1.020.304.050",
                nationality="co",
            ),
        )
        guest.refresh_from_db()
        assert (guest.first_name, guest.last_name) == ("Ana María", "Pérez Gómez")
        assert (guest.email, guest.phone) == ("ana.perez@example.com", "+573001234567")
        assert (guest.document_type, guest.document_number) == ("CC", "1020304050")

    def test_formatted_document_matches_the_stored_guest(self, organization):
        existing = GuestFactory(organization=organization, document_type="CC", document_number="1020304050")
        guest = upsert_guest(
            organization,
            GuestInput(
                first_name="Ana", last_name="Pérez", document_type="CC", document_number="1.020.304.050"
            ),
        )
        assert guest.pk == existing.pk
        assert Guest.objects.filter(organization=organization).count() == 1

    def test_foreign_phone_uses_the_residence_country_as_region(self, organization):
        guest = upsert_guest(
            organization,
            GuestInput(
                first_name="John",
                last_name="Smith",
                phone="(212) 555-0123",
                nationality="US",
                country_of_residence="US",
            ),
        )
        assert guest.phone == "+12125550123"


@pytest.mark.django_db
class TestUpdateNormalizes:
    def test_update_normalizes_names_phone_and_document(self, organization, owner):
        guest = GuestFactory(organization=organization, nationality="CO", country_of_residence="CO")
        update_guest(
            guest,
            {
                "first_name": "CAMILA",
                "last_name": "de la torre",
                "phone": "310 555 0101",
                "document_number": "52.123.456",
                "document_type": "cc",
                "nationality": "co",
                "email": " Camila@Example.com ",
            },
            actor=owner,
        )
        guest.refresh_from_db()
        assert (guest.first_name, guest.last_name) == ("Camila", "De la Torre")
        assert (guest.phone, guest.document_number, guest.document_type) == (
            "+573105550101",
            "52123456",
            "CC",
        )
        assert (guest.nationality, guest.email) == ("CO", "camila@example.com")

    def test_audit_diff_masks_personal_data_but_keeps_flags(self, organization, owner):
        guest = GuestFactory(organization=organization, email="old@example.com", is_vip=False)
        update_guest(guest, {"email": "new@example.com", "is_vip": True}, actor=owner)
        event = AuditEvent.objects.get(action="guests.guest_updated")
        assert event.changes["is_vip"] == [False, True]
        assert "email" in event.changes
        assert "old@example.com" not in str(event.changes) and "new@example.com" not in str(event.changes)
