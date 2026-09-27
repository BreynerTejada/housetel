"""find_duplicates (plan §C / B3): same document, same email, or same phone + similar last name."""

import pytest

from apps.core.tests.factories import OrganizationFactory
from apps.guests.models import Guest
from apps.guests.services import find_duplicates
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db


def ids(guests):
    return {g.pk for g in guests}


def test_same_document_number_even_with_another_type(organization):
    guest = GuestFactory(organization=organization, document_type="CC", document_number="1020304050")
    twin = GuestFactory(organization=organization, document_type="", document_number="1020304050")
    GuestFactory(organization=organization, document_type="CC", document_number="999")

    result = find_duplicates(guest)

    assert ids(result) == {twin.pk}
    assert result[0].duplicate_reasons == ["document"]


def test_same_email_ignoring_case(organization):
    guest = GuestFactory(organization=organization, email="ana@example.com")
    twin = GuestFactory(organization=organization, email="ANA@example.com")
    assert ids(find_duplicates(guest)) == {twin.pk}


def test_same_phone_needs_a_similar_last_name(organization):
    guest = GuestFactory(organization=organization, phone="+573001112233", last_name="Pérez Gómez")
    accent_and_second_surname = GuestFactory(
        organization=organization, phone="+573001112233", last_name="Perez"
    )
    typo = GuestFactory(organization=organization, phone="+573001112233", last_name="Pérez Gomes")
    GuestFactory(
        organization=organization, phone="+573001112233", last_name="Martínez"
    )  # shared family phone

    result = find_duplicates(guest)

    assert ids(result) == {accent_and_second_surname.pk, typo.pk}
    assert all(g.duplicate_reasons == ["phone_name"] for g in result)


def test_strongest_matches_come_first_with_every_reason(organization):
    guest = GuestFactory(
        organization=organization, email="a@example.com", phone="+573001112233", last_name="Rojas"
    )
    by_email = GuestFactory(organization=organization, email="a@example.com", last_name="Otro")
    by_everything = GuestFactory(
        organization=organization,
        email="a@example.com",
        phone="+573001112233",
        last_name="Rojas",
        document_number=guest.document_number,
        document_type="",
    )

    result = find_duplicates(guest)

    assert [g.pk for g in result] == [by_everything.pk, by_email.pk]
    assert result[0].duplicate_reasons == ["document", "email", "phone_name"]


def test_ignores_self_merged_other_organizations_and_guests_without_identifiers(organization):
    guest = GuestFactory(organization=organization, email="a@example.com")
    GuestFactory(organization=organization, email="a@example.com", merged_into=guest)
    GuestFactory(organization=OrganizationFactory(), email="a@example.com")
    assert find_duplicates(guest) == []

    bare = GuestFactory(organization=organization, email="", phone="", document_type="", document_number="")
    GuestFactory(organization=organization, email="", phone="", document_type="", document_number="")
    assert find_duplicates(bare) == []


def test_works_for_unsaved_input(organization):
    # The staff "new guest" form checks for duplicates before saving.
    existing = GuestFactory(organization=organization, document_type="PA", document_number="X123")
    draft = Guest(organization=organization, first_name="John", document_type="PA", document_number="X123")
    assert ids(find_duplicates(draft)) == {existing.pk}
