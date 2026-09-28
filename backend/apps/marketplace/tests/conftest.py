"""Fixtures of the marketplace tests. Time is frozen at 2026-10-01 09:00 in Bogotá (14:00 UTC, a Thursday)."""

import pytest
import rest_framework.throttling  # noqa: F401 — see _frozen_clock
from freezegun import freeze_time

from apps.marketplace.tests.helpers import build_hotel

PUBLIC = "/api/v1/public/marketplace"
STAFF = "/api/v1/marketplace"


@pytest.fixture(autouse=True)
def _frozen_clock():
    # DRF keeps `time.time` as a class attribute of its throttles, captured when `rest_framework.throttling`
    # is first imported: importing it above (before the clock is frozen) keeps the real function there, so
    # the throttles of other apps' public endpoints (e.g. the simulated gateway) keep working under freezegun.
    with freeze_time("2026-10-01 14:00:00+00:00"):
        yield


@pytest.fixture
def hotel(prop):
    return build_hotel(prop)


@pytest.fixture
def stranger_api(api_for, prop):
    """Owner of another organization sending our property's header (must get 404, never data)."""
    from apps.accounts.services import add_member, ensure_system_roles
    from apps.accounts.tests.factories import UserFactory
    from apps.core.tests.factories import OrganizationFactory

    other = OrganizationFactory(status="active")
    ensure_system_roles(other)
    user = UserFactory()
    add_member(other, user, "owner")
    return api_for(user, prop)
