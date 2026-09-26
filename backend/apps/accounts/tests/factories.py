import factory

from apps.accounts.models import Membership, Role, User
from apps.core.tests.factories import OrganizationFactory


class UserFactory(factory.django.DjangoModelFactory):
    """Every factory user has the password `pass1234`."""

    class Meta:
        model = User
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    full_name = factory.Sequence(lambda n: f"Usuario {n}")
    password = factory.django.Password("pass1234")


class RoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Role

    organization = factory.SubFactory(OrganizationFactory)
    code = factory.Sequence(lambda n: f"custom_{n}")
    name = factory.Sequence(lambda n: f"Rol {n}")
    permissions = factory.LazyFunction(list)
    is_system = False


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership
        skip_postgeneration_save = True

    user = factory.SubFactory(UserFactory)
    organization = factory.SubFactory(OrganizationFactory)
    role = factory.SubFactory(RoleFactory, organization=factory.SelfAttribute("..organization"))
    all_properties = True
    is_active = True

    @factory.post_generation
    def properties(self, create, extracted, **kwargs):
        if create and extracted:
            self.properties.set(extracted)
