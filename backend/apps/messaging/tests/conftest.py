import pytest

from apps.accounts.tests.factories import MembershipFactory, RoleFactory, UserFactory


@pytest.fixture(autouse=True)
def _frontend_url(settings):
    settings.FRONTEND_URL = "http://front.test"


@pytest.fixture
def member_with(organization):
    """A member of `organization` whose custom role grants exactly `permissions`."""

    def _make(*permissions, all_properties=True, properties=None):
        role = RoleFactory(organization=organization, permissions=list(permissions))
        membership = MembershipFactory(
            user=UserFactory(),
            organization=organization,
            role=role,
            all_properties=all_properties,
            properties=properties or [],
        )
        return membership.user

    return _make
