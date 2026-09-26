import factory

from apps.core.models import Organization, Property


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Organización {n}")
    slug = factory.Sequence(lambda n: f"org-{n}")
    legal_name = factory.LazyAttribute(lambda o: f"{o.name} S.A.S.")
    nit = factory.Sequence(lambda n: f"900{n:06d}-1")
    status = Organization.Status.ACTIVE


class PropertyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Property

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Hotel Prueba {n}")
    slug = factory.Sequence(lambda n: f"hotel-prueba-{n}")
    property_type = Property.PropertyType.HOTEL
    description = factory.LazyFunction(lambda: {"es": "Hotel de prueba", "en": "Test hotel"})
    city = "Cartagena"
    department = "Bolívar"
    email = factory.Sequence(lambda n: f"reservas{n}@hotel.test")
