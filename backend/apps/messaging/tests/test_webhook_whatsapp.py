"""Public WhatsApp webhook: `GET/POST /api/v1/public/messaging/webhooks/whatsapp/` (Meta Cloud API)."""

import hashlib
import hmac
import json

import pytest

from apps.core import integrations
from apps.core.tests.factories import PropertyFactory
from apps.guests.tests.factories import GuestFactory
from apps.messaging.models import Message
from apps.messaging.tests.factories import ConversationFactory, MessageFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/public/messaging/webhooks/whatsapp/"
APP_SECRET = "app-secret-aurora"


@pytest.fixture
def setting(prop):
    setting = integrations.get_setting(prop, "whatsapp")
    setting.mode = "real"
    setting.config = {"phone_number_id": "106540352242922"}
    setting.save()
    integrations.set_secrets(
        setting, {"access_token": "t", "app_secret": APP_SECRET, "verify_token": "verify-me"}
    )
    return setting


def _payload(value: dict, phone_number_id="106540352242922") -> dict:
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550783881", "phone_number_id": phone_number_id},
        **value,
    }
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "102290129340398", "changes": [{"value": value, "field": "messages"}]}],
    }


def _incoming(text="¿Tienen parqueadero?", wamid="wamid.IN1", sender="573001112233", name="Laura Gómez"):
    return _payload(
        {
            "contacts": [{"profile": {"name": name}, "wa_id": sender}],
            "messages": [
                {
                    "from": sender,
                    "id": wamid,
                    "timestamp": "1749416383",
                    "type": "text",
                    "text": {"body": text},
                }
            ],
        }
    )


def _post(client, payload, secret=APP_SECRET, signature=None):
    raw = json.dumps(payload).encode()
    if signature is None:
        signature = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return client.post(URL, data=raw, content_type="application/json", HTTP_X_HUB_SIGNATURE_256=signature)


class TestVerification:
    def test_meta_gets_the_challenge_back_with_the_right_token(self, public_api, setting):
        response = public_api.get(
            URL, {"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "1158201444"}
        )
        assert response.status_code == 200
        assert response.content == b"1158201444" and response["Content-Type"].startswith("text/plain")

    def test_a_wrong_token_is_refused(self, public_api, setting):
        response = public_api.get(
            URL, {"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "1158201444"}
        )
        assert response.status_code == 403


class TestNotifications:
    def test_a_signed_incoming_message_reaches_the_inbox(self, public_api, prop, setting):
        guest = GuestFactory(organization=prop.organization, phone="+573001112233")
        response = _post(public_api, _incoming())

        assert response.status_code == 200
        message = Message.objects.get()
        assert (message.direction, message.body, message.provider_message_id) == (
            "in",
            "¿Tienen parqueadero?",
            "wamid.IN1",
        )
        conversation = message.conversation
        assert (conversation.property, conversation.guest, conversation.unread_count) == (prop, guest, 1)

    def test_retries_do_not_duplicate_messages(self, public_api, setting):
        _post(public_api, _incoming())
        response = _post(public_api, _incoming())
        assert response.status_code == 200 and Message.objects.count() == 1

    def test_an_invalid_signature_is_refused_and_nothing_is_recorded(self, public_api, setting):
        response = _post(public_api, _incoming(), secret="attacker")
        assert response.status_code == 403 and Message.objects.count() == 0

    def test_a_missing_signature_is_refused(self, public_api, setting):
        response = _post(public_api, _incoming(), signature="")
        assert response.status_code == 403 and Message.objects.count() == 0

    def test_a_number_nobody_configured_is_refused(self, public_api, setting):
        response = _post(public_api, _payload({"messages": []}, phone_number_id="999"))
        assert response.status_code == 403

    def test_each_hotel_is_verified_with_its_own_secret(self, public_api, setting):
        other = PropertyFactory()
        other_setting = integrations.get_setting(other, "whatsapp")
        other_setting.mode = "real"
        other_setting.config = {"phone_number_id": "222"}
        other_setting.save()
        integrations.set_secrets(other_setting, {"app_secret": "other-secret"})
        # Signed with Aurora's secret but addressed to the other hotel's number → refused.
        response = _post(public_api, _payload({"messages": []}, phone_number_id="222"))
        assert response.status_code == 403

    def test_delivery_receipts_update_outbound_messages(self, public_api, prop, setting):
        message = MessageFactory(
            conversation=ConversationFactory(property=prop),
            direction="out",
            status="sent",
            provider_message_id="wamid.OUT1",
        )
        statuses = [
            {"id": "wamid.OUT1", "status": "delivered", "timestamp": "1750263773", "recipient_id": "573001"},
            {"id": "wamid.OUT1", "status": "read", "timestamp": "1750263780", "recipient_id": "573001"},
        ]
        response = _post(public_api, _payload({"statuses": statuses}))
        message.refresh_from_db()
        assert response.status_code == 200 and message.status == "read"

    def test_a_failed_receipt_keeps_meta_reason(self, public_api, prop, setting):
        message = MessageFactory(
            conversation=ConversationFactory(property=prop),
            direction="out",
            status="sent",
            provider_message_id="wamid.OUT2",
        )
        status = {
            "id": "wamid.OUT2",
            "status": "failed",
            "timestamp": "1750263773",
            "recipient_id": "573001",
            "errors": [{"code": 131026, "title": "Message undeliverable"}],
        }
        _post(public_api, _payload({"statuses": [status]}))
        message.refresh_from_db()
        assert message.status == "failed" and "131026" in message.error and "undeliverable" in message.error

    def test_non_text_messages_are_recorded_with_a_placeholder(self, public_api, setting):
        payload = _payload(
            {
                "messages": [
                    {
                        "from": "573001112233",
                        "id": "wamid.IMG",
                        "timestamp": "1",
                        "type": "image",
                        "image": {"caption": "Mi pasaporte", "id": "m1"},
                    }
                ]
            }
        )
        _post(public_api, payload)
        assert Message.objects.get().body == "[image] Mi pasaporte"

    def test_malformed_but_signed_bodies_never_crash(self, public_api, setting):
        response = _post(public_api, {"object": "whatsapp_business_account", "entry": "nope"})
        assert response.status_code in (200, 403)
