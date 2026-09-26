import factory

from apps.core.tests.factories import OrganizationFactory
from apps.guests.models import Guest


class GuestFactory(factory.django.DjangoModelFactory):
    """Colombian resident guest (IVA applies)."""

    class Meta:
        model = Guest

    organization = factory.SubFactory(OrganizationFactory)
    first_name = factory.Sequence(lambda n: f"Camila{n}")
    last_name = "Rodríguez"
    email = factory.Sequence(lambda n: f"huesped{n}@example.com")
    phone = factory.Sequence(lambda n: f"+57300{n:07d}")
    document_type = Guest.DocumentType.CC
    document_number = factory.Sequence(lambda n: f"{1010000000 + n}")
    nationality = "CO"
    country_of_residence = "CO"
    city_of_residence = "Bogotá"
    language = "es"


class ForeignGuestFactory(GuestFactory):
    """Foreign non-resident guest (IVA-exempt lodging, reported to SIRE)."""

    first_name = factory.Sequence(lambda n: f"John{n}")
    last_name = "Smith"
    phone = factory.Sequence(lambda n: f"+1202555{n:04d}")
    document_type = Guest.DocumentType.PA
    document_number = factory.Sequence(lambda n: f"X{n:08d}")
    nationality = "US"
    country_of_residence = "US"
    city_of_residence = "Austin"
    language = "en"
