"""Every revenue model is visible in the Django admin (support and debugging), and its pages render."""

from decimal import Decimal

import pytest
from django.apps import apps
from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import User
from apps.revenue.models import RateRecommendation
from apps.revenue.services.runs import run_revenue
from apps.revenue.tests.conftest import make_rule, oct_

LABELS = sorted(model._meta.label for model in apps.get_app_config("revenue").get_models())


def test_every_revenue_model_is_registered():
    registered = {model._meta.label for model in admin.site._registry}
    assert set(LABELS) - registered == set()


@pytest.fixture
def admin_client(client, hotel):
    from apps.revenue.models import PriceBounds

    make_rule(hotel.prop, "holiday", {"adjust": 12})
    PriceBounds.objects.create(room_type=hotel.room_type, rate_plan=hotel.plan, min_price=Decimal("250000"))
    run_revenue(hotel.prop)
    assert RateRecommendation.objects.filter(date=oct_(12)).exists()
    client.force_login(User.objects.create_superuser("root@example.com", "pass1234"))
    return client


@pytest.mark.django_db
@pytest.mark.parametrize("label", LABELS)
def test_changelist_and_change_pages_render(admin_client, label):
    model = apps.get_model(label)
    meta = model._meta
    changelist = admin_client.get(reverse(f"admin:{meta.app_label}_{meta.model_name}_changelist"))
    assert changelist.status_code == 200, label
    obj = model.objects.first()
    change = admin_client.get(reverse(f"admin:{meta.app_label}_{meta.model_name}_change", args=[obj.pk]))
    assert change.status_code == 200, label
