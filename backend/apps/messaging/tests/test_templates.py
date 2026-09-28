"""Which template a message uses: property → organization → system default, in the guest's language."""

import pytest

from apps.core.tests.factories import PropertyFactory
from apps.messaging.services import resolve_template
from apps.messaging.tests.factories import MessageTemplateFactory

pytestmark = pytest.mark.django_db

REQUIRED_CODES = [
    "confirmation",
    "pre_arrival",
    "arrival_day",
    "post_stay",
    "payment_reminder",
    "cancellation",
    "checkin_invitation",
    "payment_link",
]


@pytest.mark.parametrize("code", REQUIRED_CODES)
@pytest.mark.parametrize("channel", ["email", "whatsapp"])
@pytest.mark.parametrize("language", ["es", "en"])
def test_every_lifecycle_and_shared_template_has_a_system_default(prop, code, channel, language):
    template = resolve_template(prop, code, channel, language)
    assert template is not None
    assert (template.source, template.code, template.channel, template.language) == (
        "system",
        code,
        channel,
        language,
    )
    assert template.body.strip() and template.is_active
    assert bool(template.subject.strip()) is (channel == "email")


def test_the_organization_template_replaces_the_system_default(prop):
    row = MessageTemplateFactory(
        property=None, organization=prop.organization, body="Org {{guest.first_name}}"
    )
    template = resolve_template(prop, "confirmation", "email", "es")
    assert (template.source, template.template_id, template.body) == ("organization", row.pk, row.body)


def test_the_property_template_replaces_the_organization_one(prop):
    MessageTemplateFactory(property=None, organization=prop.organization, body="Org")
    row = MessageTemplateFactory(property=prop, body="Propiedad")
    template = resolve_template(prop, "confirmation", "email", "es")
    assert (template.source, template.template_id, template.body) == ("property", row.pk, "Propiedad")


def test_templates_of_other_hotels_are_ignored(prop):
    sibling = PropertyFactory(organization=prop.organization)
    stranger = PropertyFactory()
    MessageTemplateFactory(property=sibling, body="Hermano")
    MessageTemplateFactory(property=None, organization=stranger.organization, body="Otra org")
    assert resolve_template(prop, "confirmation", "email", "es").source == "system"


def test_a_missing_language_falls_back_to_the_hotel_language_then_spanish(prop):
    MessageTemplateFactory(property=prop, code="welcome_drink", language="es", body="Cóctel de bienvenida")
    template = resolve_template(prop, "welcome_drink", "email", "en")
    assert (template.language, template.body) == ("es", "Cóctel de bienvenida")


def test_an_inactive_template_is_returned_so_the_channel_can_be_skipped(prop):
    MessageTemplateFactory(property=None, organization=prop.organization, body="Org activa")
    MessageTemplateFactory(property=prop, is_active=False, body="Apagada")
    template = resolve_template(prop, "confirmation", "email", "es")
    assert (template.source, template.is_active) == ("property", False)


def test_an_unknown_code_has_no_template(prop):
    assert resolve_template(prop, "does_not_exist", "email", "es") is None
