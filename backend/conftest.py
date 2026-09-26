"""Shared pytest fixtures for every app (spec §8). App factories live in apps/<app>/tests/factories.py."""

import pytest
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _isolated_cache():
    """Tests use a local-memory cache (see settings.TESTING); clear it so throttles/caches never leak."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def organization(db):
    from apps.accounts.services import ensure_system_roles
    from apps.core.tests.factories import OrganizationFactory

    org = OrganizationFactory(status="active")
    ensure_system_roles(org)
    return org


@pytest.fixture
def prop(organization):
    from apps.core.tests.factories import PropertyFactory

    return PropertyFactory(organization=organization)


@pytest.fixture
def make_member(organization):
    from apps.accounts.services import add_member
    from apps.accounts.tests.factories import UserFactory

    def _make(role_code="owner", *, properties=None, org=None, **user_kwargs):
        user = UserFactory(**user_kwargs)
        add_member(
            org or organization, user, role_code, all_properties=properties is None, properties=properties
        )
        return user

    return _make


@pytest.fixture
def owner(make_member):
    return make_member("owner")


@pytest.fixture
def api_for():
    def _api(user, property_obj):
        client = APIClient()
        client.force_authenticate(user=user)
        client.credentials(HTTP_X_PROPERTY_ID=str(property_obj.pk))
        return client

    return _api


@pytest.fixture
def api(api_for, owner, prop):
    return api_for(owner, prop)


@pytest.fixture
def public_api():
    return APIClient()
