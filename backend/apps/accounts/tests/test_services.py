import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import Membership, Role, User
from apps.accounts.services import add_member, ensure_system_roles
from apps.accounts.tests.factories import UserFactory
from apps.core.tests.factories import OrganizationFactory, PropertyFactory

pytestmark = pytest.mark.django_db

SYSTEM_ROLE_CODES = {
    "owner",
    "manager",
    "front_desk",
    "housekeeping_supervisor",
    "housekeeping",
    "maintenance",
    "accountant",
}


class TestEnsureSystemRoles:
    def test_creates_one_system_role_per_template(self):
        org = OrganizationFactory()
        roles = ensure_system_roles(org)
        assert set(roles) == SYSTEM_ROLE_CODES
        owner = roles["owner"]
        assert (owner.organization, owner.is_system, owner.permissions, owner.name) == (
            org,
            True,
            ["*"],
            "Dueño",
        )
        assert roles["housekeeping"].permissions == [
            "housekeeping.view",
            "housekeeping.work",
            "inventory.view",
        ]

    def test_is_idempotent_and_restores_template_permissions(self):
        org = OrganizationFactory()
        first = ensure_system_roles(org)
        Role.objects.filter(pk=first["housekeeping"].pk).update(permissions=["finance.refund"])

        second = ensure_system_roles(org)

        assert Role.objects.filter(organization=org).count() == len(SYSTEM_ROLE_CODES)
        assert second["housekeeping"].pk == first["housekeeping"].pk
        assert Role.objects.get(pk=first["housekeeping"].pk).permissions == [
            "housekeeping.view",
            "housekeeping.work",
            "inventory.view",
        ]

    def test_each_organization_gets_its_own_copies(self):
        a, b = OrganizationFactory(), OrganizationFactory()
        assert ensure_system_roles(a)["owner"].pk != ensure_system_roles(b)["owner"].pk


class TestAddMember:
    def test_member_with_access_to_all_properties(self, organization):
        membership = add_member(organization, UserFactory(), "front_desk")
        assert membership.role.code == "front_desk"
        assert membership.role.organization == organization
        assert membership.all_properties and membership.is_active

    def test_member_restricted_to_given_properties(self, organization):
        allowed, _other = PropertyFactory.create_batch(2, organization=organization)
        membership = add_member(
            organization, UserFactory(), "housekeeping", all_properties=False, properties=[allowed]
        )
        assert not membership.all_properties
        assert list(membership.properties.all()) == [allowed]

    def test_adding_again_updates_the_single_membership(self, organization):
        user = UserFactory()
        add_member(
            organization,
            user,
            "housekeeping",
            all_properties=False,
            properties=[PropertyFactory(organization=organization)],
        )
        membership = add_member(organization, user, "manager")
        assert Membership.objects.filter(user=user).count() == 1
        assert membership.role.code == "manager"
        assert membership.all_properties and membership.properties.count() == 0

    def test_creates_the_system_roles_when_missing(self):
        org = OrganizationFactory()
        membership = add_member(org, UserFactory(), "owner")
        assert membership.role.permissions == ["*"]


class TestUserManager:
    def test_create_user_normalizes_email_and_hashes_password(self):
        user = User.objects.create_user("  Ana.Perez@Example.COM ", "secret-pass-1")
        assert user.email == "ana.perez@example.com"
        assert user.password != "secret-pass-1"
        assert user.check_password("secret-pass-1")

    def test_create_user_requires_an_email(self):
        with pytest.raises(ValueError):
            User.objects.create_user("", "secret-pass-1")

    def test_natural_key_lookup_ignores_case(self):
        user = User.objects.create_user("ana@example.com", "secret-pass-1")
        assert User.objects.get_by_natural_key("ANA@Example.com") == user

    def test_every_save_stores_the_email_trimmed_and_lowercased(self):
        user = User.objects.create(email="  Mixed.Case@Example.COM ")
        assert User.objects.get(pk=user.pk).email == "mixed.case@example.com"

    def test_emails_are_unique_ignoring_case(self):
        User.objects.create(email="Mixed@Example.com")
        with pytest.raises(IntegrityError), transaction.atomic():
            User.objects.create(email="mixed@example.com")

    def test_create_superuser_sets_staff_and_superuser(self):
        admin = User.objects.create_superuser("root@example.com", "secret-pass-1")
        assert admin.is_staff and admin.is_superuser
