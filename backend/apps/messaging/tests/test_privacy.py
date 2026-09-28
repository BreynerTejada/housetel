"""Habeas Data (Ley 1581): anonymizing a guest (guests.anonymize_guest) erases our copies of their data."""

import pytest

from apps.guests.services import anonymize_guest
from apps.guests.tests.factories import GuestFactory
from apps.messaging.models import Conversation, Message
from apps.messaging.tests.factories import ConversationFactory, MessageFactory

pytestmark = pytest.mark.django_db


def test_the_guest_threads_lose_every_personal_detail(prop, owner, django_capture_on_commit_callbacks):
    guest = GuestFactory(organization=prop.organization, first_name="Laura", phone="+573001112233")
    conversation = ConversationFactory(
        property=prop,
        guest=guest,
        external_thread_key="+573001112233",
        contact_name="Laura Gómez",
        last_message_preview="Mi pasaporte es X123",
    )
    MessageFactory(conversation=conversation, body="Mi pasaporte es X123", sender_label="Laura Gómez")
    MessageFactory(
        conversation=conversation,
        direction="out",
        status="delivered",
        body="Hola Laura",
        sender_label="Hotel Prueba",
        recipient="+573001112233",
    )
    other = MessageFactory(conversation=ConversationFactory(property=prop), body="Otro huésped")

    with django_capture_on_commit_callbacks(execute=True):
        anonymize_guest(guest, actor=owner)

    conversation.refresh_from_db()
    assert conversation.external_thread_key == f"anonymized:{conversation.pk}"
    assert (conversation.contact_name, conversation.last_message_preview) == ("", "")
    inbound, outbound = conversation.messages.order_by("direction")
    assert (inbound.body, inbound.sender_label) == ("", "Huésped anonimizado")
    assert (outbound.body, outbound.recipient, outbound.sender_label) == ("", "", "Hotel Prueba")
    other.refresh_from_db()
    assert other.body == "Otro huésped"
    assert Conversation.objects.count() == 2 and Message.objects.count() == 3
