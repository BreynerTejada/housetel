"""The Django admin lists the portal models without ever linking the private signature file."""

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse

from apps.accounts.models import User
from apps.guestportal.models import GuestPortalSettings, OnlineCheckin, ServiceRequest
from apps.guestportal.tests.conftest import png_bytes

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client, reservation):
    checkin = OnlineCheckin.objects.create(reservation=reservation, status="completed")
    checkin.signature.save("signature.png", ContentFile(png_bytes()), save=True)
    GuestPortalSettings.objects.create(property=reservation.property)
    ServiceRequest.objects.create(reservation=reservation, kind="late_checkout")
    client.force_login(User.objects.create_superuser("root@example.com", "pass1234"))
    return client


@pytest.mark.parametrize("model", [GuestPortalSettings, OnlineCheckin, ServiceRequest])
def test_changelist_and_change_pages_render(admin_client, model):
    meta = model._meta
    obj = model.objects.get()

    assert (
        admin_client.get(reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist")).status_code == 200
    )
    change = admin_client.get(reverse(f"admin:{meta.app_label}_{meta.model_name}_change", args=[obj.pk]))
    assert change.status_code == 200
    assert b"guest-portal/signatures" not in change.content
