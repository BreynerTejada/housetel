"""Real WhatsApp provider: Meta WhatsApp Cloud API (Graph API v26.0, the latest version, released 2026-07-29;
verified against developers.facebook.com on 2026-09-27), mocked with respx."""

import json
from datetime import timedelta

import httpx
import pytest
import respx
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory
from apps.core import integrations
from apps.guests.tests.factories import GuestFactory
from apps.messaging.models import Conversation, Message
from apps.messaging.providers import WhatsAppCloudProvider
from apps.messaging.services import send_message
from apps.messaging.tests.factories import MessageTemplateFactory

pytestmark = pytest.mark.django_db

GRAPH = "https://graph.facebook.com/v26.0"
SENT = {
    "messaging_product": "whatsapp",
    "contacts": [{"input": "+573001112233", "wa_id": "573001112233"}],
    "messages": [{"id": "wamid.HBgLNTczMDAxMTEyMjMzFQIAERgS", "message_status": "accepted"}],
}


@pytest.fixture
def setting(prop):
    setting = integrations.get_setting(prop, "whatsapp")
    setting.mode = "real"
    setting.config = {"phone_number_id": "106540352242922"}
    setting.save()
    integrations.set_secrets(setting, {"access_token": "EAAJB-test-token", "app_secret": "s3cret"})
    return setting


@pytest.fixture
def provider(setting):
    return integrations.get_provider(setting.property, "whatsapp")


def test_the_real_mode_uses_the_cloud_api_provider(provider):
    assert isinstance(provider, WhatsAppCloudProvider)


@respx.mock
def test_a_text_message_is_posted_to_the_messages_endpoint(provider):
    route = respx.post(f"{GRAPH}/106540352242922/messages").mock(return_value=httpx.Response(200, json=SENT))
    result = provider.send_whatsapp(to="+573001112233", text="Hola Ana")

    assert (result.status, result.provider_message_id, result.error) == (
        "sent",
        "wamid.HBgLNTczMDAxMTEyMjMzFQIAERgS",
        "",
    )
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer EAAJB-test-token"
    assert json.loads(request.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "+573001112233",
        "type": "text",
        "text": {"preview_url": True, "body": "Hola Ana"},
    }


@respx.mock
def test_an_approved_template_carries_its_body_parameters(provider):
    route = respx.post(f"{GRAPH}/106540352242922/messages").mock(return_value=httpx.Response(200, json=SENT))
    template = {"name": "reserva_confirmada", "language": "es", "parameters": ["Ana", "HT-ABC123"]}
    provider.send_whatsapp(to="+573001112233", text="(no se usa)", template=template)

    assert json.loads(route.calls.last.request.content) == {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": "+573001112233",
        "type": "template",
        "template": {
            "name": "reserva_confirmada",
            "language": {"code": "es"},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": "Ana"}, {"type": "text", "text": "HT-ABC123"}],
                }
            ],
        },
    }


@respx.mock
def test_the_template_language_code_can_be_configured(setting):
    setting.config = {**setting.config, "template_language_en": "en_US", "api_version": "v24.0"}
    setting.save()
    provider = integrations.get_provider(setting.property, "whatsapp")
    route = respx.post("https://graph.facebook.com/v24.0/106540352242922/messages").mock(
        return_value=httpx.Response(200, json=SENT)
    )
    provider.send_whatsapp(
        to="+1202555", text="-", template={"name": "hello", "language": "en", "parameters": []}
    )
    assert json.loads(route.calls.last.request.content)["template"] == {
        "name": "hello",
        "language": {"code": "en_US"},
    }


@respx.mock
def test_outside_the_24_hour_window_meta_error_is_explained(provider):
    error = {
        "error": {
            "message": "(#131047) Re-engagement message",
            "type": "OAuthException",
            "code": 131047,
            "error_data": {
                "messaging_product": "whatsapp",
                "details": "Message failed to send because "
                "more than 24 hours have passed since the customer last replied to this number.",
            },
            "fbtrace_id": "AbCd",
        }
    }
    respx.post(f"{GRAPH}/106540352242922/messages").mock(return_value=httpx.Response(400, json=error))
    result = provider.send_whatsapp(to="+573001112233", text="Hola")
    assert result.status == "failed"
    assert "24 h" in result.error and "131047" in result.error


@respx.mock
def test_network_errors_fail_the_delivery(provider):
    respx.post(f"{GRAPH}/106540352242922/messages").mock(side_effect=httpx.ConnectError("boom"))
    result = provider.send_whatsapp(to="+573001112233", text="Hola")
    assert result.status == "failed" and "boom" in result.error


def test_missing_credentials_fail_without_calling_meta(prop):
    setting = integrations.get_setting(prop, "whatsapp")
    setting.mode = "real"
    setting.save()
    with respx.mock(assert_all_called=False) as mock:
        result = integrations.get_provider(prop, "whatsapp").send_whatsapp(to="+573001112233", text="Hola")
    assert result.status == "failed" and "phone_number_id" in result.error and not mock.calls


@respx.mock
def test_test_connection_reads_the_phone_number(provider):
    respx.get(f"{GRAPH}/106540352242922").mock(
        return_value=httpx.Response(
            200,
            json={
                "display_phone_number": "+57 300 111 2233",
                "verified_name": "Casa Aurora",
                "id": "106540352242922",
            },
        )
    )
    ok, message = provider.test_connection()
    assert ok and "+57 300 111 2233" in message


@respx.mock
def test_test_connection_reports_an_invalid_token(provider):
    respx.get(f"{GRAPH}/106540352242922").mock(
        return_value=httpx.Response(
            401, json={"error": {"message": "Invalid OAuth access token.", "code": 190}}
        )
    )
    ok, message = provider.test_connection()
    assert not ok and "190" in message


class TestServiceWindow:
    @pytest.fixture
    def reservation(self, prop):
        guest = GuestFactory(organization=prop.organization, first_name="Ana", phone="+573001112233")
        return ReservationFactory(property=prop, booker=guest, code="HT-ABC123")

    @pytest.fixture(autouse=True)
    def _approved_template(self, prop, setting):
        MessageTemplateFactory(
            property=prop,
            channel="whatsapp",
            subject="",
            body="Hola {{guest.first_name}}",
            wa_template_name="reserva_confirmada",
            wa_template_params=["guest.first_name", "reservation.code"],
        )

    @respx.mock
    def test_without_a_recent_guest_message_the_approved_template_is_sent(self, prop, reservation):
        route = respx.post(f"{GRAPH}/106540352242922/messages").mock(
            return_value=httpx.Response(200, json=SENT)
        )
        (out,) = send_message(
            property=prop, template_code="confirmation", reservation=reservation, channels=("whatsapp",)
        )
        payload = json.loads(route.calls.last.request.content)
        assert payload["type"] == "template"
        assert payload["template"]["components"][0]["parameters"] == [
            {"type": "text", "text": "Ana"},
            {"type": "text", "text": "HT-ABC123"},
        ]
        assert (out.status, Message.objects.get().provider_message_id) == ("sent", SENT["messages"][0]["id"])

    @respx.mock
    def test_inside_the_window_the_free_text_is_sent(self, prop, reservation):
        Conversation.objects.create(
            property=prop,
            channel="whatsapp",
            external_thread_key="+573001112233",
            last_inbound_at=timezone.now() - timedelta(hours=2),
        )
        route = respx.post(f"{GRAPH}/106540352242922/messages").mock(
            return_value=httpx.Response(200, json=SENT)
        )
        send_message(
            property=prop, template_code="confirmation", reservation=reservation, channels=("whatsapp",)
        )
        payload = json.loads(route.calls.last.request.content)
        assert (payload["type"], payload["text"]["body"]) == ("text", "Hola Ana")
