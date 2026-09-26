import pytest
from django.db import IntegrityError, transaction

from apps.core.tests.factories import OrganizationFactory
from apps.guests.models import Guest
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db


class TestDocumentUniqueness:
    def test_same_document_in_the_same_organization_is_rejected(self, organization):
        GuestFactory(organization=organization, document_type="CC", document_number="1020304050")
        with pytest.raises(IntegrityError), transaction.atomic():
            GuestFactory(organization=organization, document_type="CC", document_number="1020304050")

    def test_guests_without_document_are_not_constrained(self, organization):
        GuestFactory(organization=organization, document_type="", document_number="")
        GuestFactory(organization=organization, document_type="", document_number="")
        assert Guest.objects.filter(organization=organization, document_number="").count() == 2

    def test_same_document_is_allowed_in_another_organization_or_type(self, organization):
        GuestFactory(organization=organization, document_type="CC", document_number="1020304050")
        GuestFactory(organization=OrganizationFactory(), document_type="CC", document_number="1020304050")
        GuestFactory(organization=organization, document_type="PA", document_number="1020304050")
        assert Guest.objects.filter(document_number="1020304050").count() == 3


@pytest.mark.parametrize(
    ("nationality", "residence", "expected"),
    [
        ("CO", "CO", False),
        ("US", "US", True),
        ("US", "CO", False),  # foreigner living in Colombia pays IVA
        ("CO", "US", False),  # Colombian abroad is not a foreigner
        ("us", "fr", True),
        ("US", "", True),  # unknown residence of a foreigner: treated as non-resident
        ("", "", False),  # without nationality we never exempt
    ],
)
def test_is_foreign_non_resident(nationality, residence, expected):
    guest = Guest(nationality=nationality, country_of_residence=residence)
    assert guest.is_foreign_non_resident is expected


def test_full_name():
    assert Guest(first_name="Ana María", last_name="Pérez").full_name == "Ana María Pérez"
    assert Guest(first_name="Ana", last_name="").full_name == "Ana"
