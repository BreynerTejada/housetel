"""Django admin (support tool): every messaging model is registered and its pages render."""

import pytest
from django.apps import apps
from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import User
from apps.messaging.tests.factories import ConversationFactory, LifecycleRuleFactory, MessageFactory

LABELS = sorted(model._meta.label for model in apps.get_app_config("messaging").get_models())


def test_every_messaging_model_is_registered():
    registered = {model._meta.label for model in admin.site._registry}
    assert set(LABELS) - registered == set()


@pytest.mark.django_db
@pytest.mark.parametrize("label", LABELS)
def test_changelist_and_add_pages_render(client, label, prop):
    MessageFactory(conversation=ConversationFactory(property=prop))
    LifecycleRuleFactory(property=prop)
    client.force_login(User.objects.create_superuser("root@example.com", "pass1234"))
    meta = apps.get_model(label)._meta
    for page in ("changelist", "add"):
        response = client.get(reverse(f"admin:{meta.app_label}_{meta.model_name}_{page}"))
        assert response.status_code == 200, f"{label} {page}"
