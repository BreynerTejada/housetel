"""Fixtures shared by the inventory API tests."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.core.tests.factories import OrganizationFactory
from apps.inventory.tests.test_services_basic import listen

BASE = "/api/v1/inventory"


@pytest.fixture
def hk_api(api_for, make_member, prop):
    """Housekeeping staff: `inventory.view` only."""
    return api_for(make_member("housekeeping"), prop)


@pytest.fixture
def front_api(api_for, make_member, prop):
    """Front desk: `inventory.view` only."""
    return api_for(make_member("front_desk"), prop)


@pytest.fixture
def stranger_api(api_for, prop):
    """Owner of another organization sending our property's header (must get 404, never data)."""
    from apps.accounts.services import add_member, ensure_system_roles
    from apps.accounts.tests.factories import UserFactory

    other = OrganizationFactory(status="active")
    ensure_system_roles(other)
    user = UserFactory()
    add_member(other, user, "owner")
    return api_for(user, prop)


def image_bytes(fmt="PNG", size=(40, 30), color=(180, 88, 59)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


@pytest.fixture
def make_image():
    def _make(name="room.png", fmt="PNG", size=(40, 30)):
        content_type = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}[fmt]
        return SimpleUploadedFile(name, image_bytes(fmt, size), content_type=content_type)

    return _make


@pytest.fixture
def capture(django_capture_on_commit_callbacks):
    """`received = capture(signal, lambda: ...)` → kwargs every receiver got after commit."""

    def _capture(signal, action):
        received, stop = listen(signal)
        try:
            with django_capture_on_commit_callbacks(execute=True):
                action()
        finally:
            stop()
        return received

    return _capture
