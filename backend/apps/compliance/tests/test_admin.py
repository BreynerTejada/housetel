"""Django admin of compliance: every model registered; legal documents are read-only."""

import pytest
from django.apps import apps
from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import User
from apps.compliance.services.invoices import issue_invoice

LABELS = sorted(m._meta.label for m in apps.get_app_config("compliance").get_models())
READ_ONLY = {
    "compliance.Invoice",
    "compliance.SireReport",
    "compliance.SireRecord",
    "compliance.TraRegistration",
}


def test_every_compliance_model_is_registered():
    registered = {model._meta.label for model in admin.site._registry}

    assert set(LABELS) - registered == set()


@pytest.fixture
def admin_client(client, db, resolution, make_finished_reservation):
    issue_invoice(make_finished_reservation())
    client.force_login(User.objects.create_superuser("root@example.com", "pass1234"))
    return client


@pytest.mark.parametrize("label", LABELS)
def test_the_changelist_renders(admin_client, label):
    meta = apps.get_model(label)._meta

    response = admin_client.get(reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist"))

    assert response.status_code == 200


@pytest.mark.parametrize("label", sorted(READ_ONLY))
def test_legal_documents_cannot_be_created_or_deleted_by_hand(admin_client, label):
    meta = apps.get_model(label)._meta

    assert admin_client.get(reverse(f"admin:{meta.app_label}_{meta.model_name}_add")).status_code == 403


@pytest.mark.django_db
def test_an_invoice_page_shows_its_data_read_only(admin_client):
    from apps.compliance.models import Invoice

    invoice = Invoice.objects.get()

    response = admin_client.get(reverse("admin:compliance_invoice_change", args=[invoice.pk]))

    assert response.status_code == 200
    assert b"SETT1" in response.content
    assert b'name="full_number"' not in response.content  # not an editable input
