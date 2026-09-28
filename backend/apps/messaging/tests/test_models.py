"""Database guarantees of the messaging models (plan C6)."""

import pytest
from django.db import IntegrityError, transaction

from apps.bookings.tests.factories import ReservationFactory
from apps.core.tests.factories import PropertyFactory
from apps.messaging.models import Conversation, LifecycleDispatch, Message, MessageTemplate

pytestmark = pytest.mark.django_db


def _template(**kwargs):
    values = {"code": "confirmation", "channel": "email", "language": "es", "subject": "Hola", "body": "Hola"}
    values.update(kwargs)
    return MessageTemplate.objects.create(**values)


class TestMessageTemplateUniqueness:
    def test_one_property_template_per_code_channel_and_language(self, prop):
        _template(organization=prop.organization, property=prop)
        _template(organization=prop.organization, property=prop, language="en")
        _template(organization=prop.organization, property=prop, channel="whatsapp")
        with pytest.raises(IntegrityError), transaction.atomic():
            _template(organization=prop.organization, property=prop)

    def test_one_organization_template_per_code_channel_and_language(self, prop):
        _template(organization=prop.organization, property=None)
        with pytest.raises(IntegrityError), transaction.atomic():
            _template(organization=prop.organization, property=None)

    def test_other_organizations_and_property_overrides_do_not_collide(self, prop):
        other = PropertyFactory()
        _template(organization=prop.organization, property=None)
        _template(organization=other.organization, property=None)
        _template(organization=prop.organization, property=prop)
        assert MessageTemplate.objects.count() == 3


def test_a_lifecycle_event_is_dispatched_once_per_reservation(prop):
    reservation = ReservationFactory(property=prop)
    LifecycleDispatch.objects.create(reservation=reservation, event="confirmation")
    LifecycleDispatch.objects.create(reservation=reservation, event="cancellation")
    with pytest.raises(IntegrityError), transaction.atomic():
        LifecycleDispatch.objects.create(reservation=reservation, event="confirmation")


def test_a_provider_message_id_is_stored_once_per_channel(prop):
    conversation = Conversation.objects.create(
        property=prop, channel="whatsapp", external_thread_key="+57300"
    )
    Message.objects.create(
        conversation=conversation,
        direction="in",
        channel="whatsapp",
        body="a",
        status="received",
        provider_message_id="wamid.1",
    )
    Message.objects.create(
        conversation=conversation,
        direction="out",
        channel="whatsapp",
        body="b",
        status="sent",
        provider_message_id="",
    )
    Message.objects.create(
        conversation=conversation,
        direction="out",
        channel="whatsapp",
        body="c",
        status="sent",
        provider_message_id="",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        Message.objects.create(
            conversation=conversation,
            direction="in",
            channel="whatsapp",
            body="dup",
            status="received",
            provider_message_id="wamid.1",
        )
