"""Inbound messages (WhatsApp webhook, simulator, web chat) and delivery receipts."""

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory
from apps.core.tests.factories import PropertyFactory
from apps.guests.models import Guest
from apps.guests.tests.factories import GuestFactory
from apps.messaging.models import Conversation, Message
from apps.messaging.services import apply_status_update, receive_whatsapp, record_inbound_message
from apps.messaging.tests.factories import ConversationFactory, MessageFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def guest(prop):
    return GuestFactory(
        organization=prop.organization, first_name="Laura", last_name="Gómez", phone="+573001112233"
    )


class TestReceiveWhatsApp:
    def test_a_message_from_a_known_phone_lands_in_the_guest_thread(self, prop, guest):
        message = receive_whatsapp(
            prop, phone="+573001112233", body="¿Hay parqueadero?", provider_message_id="w1"
        )

        conversation = message.conversation
        assert (message.direction, message.channel, message.status, message.body) == (
            "in",
            "whatsapp",
            "received",
            "¿Hay parqueadero?",
        )
        assert (conversation.guest, conversation.external_thread_key, conversation.unread_count) == (
            guest,
            "+573001112233",
            1,
        )
        assert conversation.last_inbound_at is not None and conversation.last_message_direction == "in"
        assert message.sender_label == "Laura Gómez"

    def test_local_colombian_numbers_are_matched(self, prop, guest):
        message = receive_whatsapp(prop, phone="300 111 2233", body="Hola")
        assert message.conversation.guest == guest

    def test_an_unknown_phone_becomes_a_whatsapp_contact(self, prop):
        message = receive_whatsapp(prop, phone="+573209998877", body="Hola", profile_name="")
        guest = message.conversation.guest
        assert (guest.first_name, guest.last_name, guest.phone) == ("Contacto", "WhatsApp", "+573209998877")
        assert guest.organization == prop.organization

    def test_the_whatsapp_profile_name_names_a_new_contact(self, prop):
        message = receive_whatsapp(prop, phone="+14155550100", body="Hi", profile_name="Sheena Nelson")
        guest = message.conversation.guest
        assert (guest.first_name, guest.last_name) == ("Sheena", "Nelson")

    def test_guests_of_other_organizations_are_never_matched(self, prop):
        GuestFactory(organization=PropertyFactory().organization, phone="+573001112233")
        message = receive_whatsapp(prop, phone="+573001112233", body="Hola")
        assert message.conversation.guest.organization == prop.organization
        assert Guest.objects.filter(phone="+573001112233").count() == 2

    def test_the_current_reservation_is_linked(self, prop, guest):
        prop.business_date = date(2026, 10, 1)
        prop.save()
        ReservationFactory(
            property=prop,
            booker=guest,
            checkin_date=date(2026, 8, 1),
            checkout_date=date(2026, 8, 3),
            status="checked_out",
        )
        upcoming = ReservationFactory(
            property=prop, booker=guest, checkin_date=date(2026, 10, 5), checkout_date=date(2026, 10, 7)
        )
        ReservationFactory(
            property=prop, booker=guest, checkin_date=date(2026, 12, 20), checkout_date=date(2026, 12, 22)
        )
        message = receive_whatsapp(prop, phone="+573001112233", body="Hola")
        assert (message.reservation, message.conversation.reservation) == (upcoming, upcoming)

    def test_a_retried_webhook_is_recorded_once(self, prop, guest):
        first = receive_whatsapp(prop, phone="+573001112233", body="Hola", provider_message_id="wamid.X")
        again = receive_whatsapp(prop, phone="+573001112233", body="Hola", provider_message_id="wamid.X")
        assert first.pk == again.pk
        assert Message.objects.count() == 1 and Conversation.objects.get().unread_count == 1

    def test_a_closed_conversation_reopens(self, prop, guest):
        ConversationFactory(property=prop, external_thread_key="+573001112233", status="closed", guest=guest)
        message = receive_whatsapp(prop, phone="+573001112233", body="Otra pregunta")
        assert message.conversation.status == "open"


def test_web_chat_messages_open_a_thread_by_session(prop):
    message = record_inbound_message(
        prop,
        channel="web_chat",
        address="chat-session-1",
        body="Quiero hablar con alguien",
        contact_name="María",
    )
    conversation = message.conversation
    assert (conversation.channel, conversation.external_thread_key, conversation.contact_name) == (
        "web_chat",
        "chat-session-1",
        "María",
    )
    assert (message.sender_label, conversation.unread_count, conversation.guest) == ("María", 1, None)


class TestStatusUpdates:
    @pytest.fixture
    def message(self, prop):
        return MessageFactory(
            conversation=ConversationFactory(property=prop),
            direction="out",
            status="sent",
            provider_message_id="wamid.OUT",
        )

    def test_receipts_move_the_status_forward(self, message):
        apply_status_update(channel="whatsapp", provider_message_id="wamid.OUT", status="delivered")
        apply_status_update(channel="whatsapp", provider_message_id="wamid.OUT", status="read")
        message.refresh_from_db()
        assert message.status == "read" and message.status_updated_at is not None

    def test_a_late_receipt_never_moves_it_back(self, message):
        apply_status_update(channel="whatsapp", provider_message_id="wamid.OUT", status="read")
        apply_status_update(channel="whatsapp", provider_message_id="wamid.OUT", status="delivered")
        message.refresh_from_db()
        assert message.status == "read"

    def test_a_failure_keeps_the_reason(self, message):
        apply_status_update(
            channel="whatsapp",
            provider_message_id="wamid.OUT",
            status="failed",
            error="131026 Message Undeliverable",
        )
        message.refresh_from_db()
        assert (message.status, message.error) == ("failed", "131026 Message Undeliverable")

    def test_unknown_messages_are_ignored(self, message):
        assert (
            apply_status_update(channel="whatsapp", provider_message_id="wamid.OTHER", status="read") is None
        )


def test_the_window_is_counted_from_the_last_inbound_message(prop, guest):
    from apps.messaging.services import whatsapp_window_open

    message = receive_whatsapp(prop, phone="+573001112233", body="Hola")
    conversation = message.conversation
    assert whatsapp_window_open(conversation)
    assert not whatsapp_window_open(conversation, now=timezone.now() + timedelta(hours=25))
