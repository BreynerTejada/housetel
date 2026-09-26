"""Every app follows the layout the core auto-discovers (spec §2.3, §9.7; plan Step 6)."""

from importlib import import_module
from importlib.util import find_spec

import pytest
from django.apps import apps
from django.conf import settings


@pytest.mark.parametrize("app", settings.LOCAL_APPS)
def test_app_layout(app):
    config = apps.get_app_config(app)
    assert (config.name, config.label) == (f"apps.{app}", app)
    for module in ("urls", "public_urls"):
        assert isinstance(import_module(f"apps.{app}.{module}").urlpatterns, list)
    assert find_spec(f"apps.{app}.migrations") is not None
    assert find_spec(f"apps.{app}.tests") is not None
    assert isinstance(import_module(f"apps.{app}.permissions").PERMISSIONS, list)


def test_local_apps_are_the_planned_ones():
    assert settings.LOCAL_APPS == [
        "core", "accounts", "inventory", "rates", "bookings", "guests", "finance", "frontdesk",
        "housekeeping", "distribution", "marketplace", "guestportal", "messaging", "compliance", "revenue",
        "ai", "reports", "saas", "control",
    ]  # fmt: skip
