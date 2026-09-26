import pytest
from django.apps import apps
from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import User

MODEL_APPS = ["core", "accounts", "inventory", "rates", "bookings", "guests", "finance"]
LABELS = sorted(m._meta.label for app in MODEL_APPS for m in apps.get_app_config(app).get_models())


def test_every_domain_model_is_registered_in_the_admin():
    registered = {model._meta.label for model in admin.site._registry}
    assert set(LABELS) - registered == set()


@pytest.fixture
def admin_client(client, db):
    from apps.bookings.tests.factories import StayFactory
    from apps.finance.tests.factories import ChargeFactory, FolioFactory, PaymentFactory
    from apps.inventory.tests.factories import BedFactory, RoomFactory

    # Some rows so list_display columns are rendered too.
    stay = StayFactory(room=RoomFactory())
    folio = FolioFactory(reservation=stay.reservation, stay=stay)
    ChargeFactory(folio=folio)
    PaymentFactory(folio=folio)
    BedFactory()
    client.force_login(User.objects.create_superuser("root@example.com", "pass1234"))
    return client


@pytest.mark.parametrize("label", LABELS)
def test_changelist_and_add_pages_render(admin_client, label):
    meta = apps.get_model(label)._meta
    for page in ("changelist", "add"):
        url = reverse(f"admin:{meta.app_label}_{meta.model_name}_{page}")
        response = admin_client.get(url)
        assert response.status_code == 200, f"{label} {page}: {response.status_code}"


@pytest.mark.django_db
def test_superuser_can_create_a_user_from_the_admin(admin_client):
    url = reverse("admin:accounts_user_add")
    response = admin_client.post(
        url,
        {
            "email": "New.User@Example.com",
            "full_name": "Nuevo",
            "password1": "S3cure-pass!x",
            "password2": "S3cure-pass!x",
            "usable_password": "true",
        },
    )
    assert response.status_code == 302, response.content[:500]
    assert User.objects.get(email="new.user@example.com").check_password("S3cure-pass!x")
