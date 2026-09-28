"""WhatsApp simulator API (`/api/v1/messaging/simulator/whatsapp/…`): the staff plays a guest on a phone
mockup. Only available while the hotel's WhatsApp integration is simulated (in real mode a reply would reach
a real phone)."""

from datetime import timedelta

import pytest

from apps.bookings.tests.factories import ReservationFactory
from apps.core import integrations
from apps.core.tests.factories import PropertyFactory
from apps.guests.models import Guest
from apps.guests.tests.factories import GuestFactory
from apps.messaging.models import Message

pytestmark = pytest.mark.django_db

BASE = "/api/v1/messaging/simulator/whatsapp/"


@pytest.fixture
def guest(prop):
    return GuestFactory(
        organization=prop.organization, first_name="Laura", last_name="Gómez", phone="+573001112233"
    )


class TestInbound:
    def test_a_message_as_the_guest_lands_in_the_inbox_linked_by_phone(self, api, prop, guest):
        response = api.post(
            f"{BASE}inbound/", {"phone": "300 111 2233", "body": "¿A qué hora es el check-in?"}, format="json"
        )

        assert response.status_code == 201
        data = response.json()
        message = Message.objects.get(pk=data["message"]["id"])
        assert (message.direction, message.channel, message.body, message.status) == (
            "in",
            "whatsapp",
            "¿A qué hora es el check-in?",
            "received",
        )
        conversation = message.conversation
        assert (str(conversation.pk), conversation.guest, conversation.property) == (
            data["conversation_id"],
            guest,
            prop,
        )
        assert conversation.unread_count == 1

    def test_an_unknown_number_becomes_a_contact(self, api, prop):
        response = api.post(
            f"{BASE}inbound/", {"phone": "+14155550100", "body": "Hi", "name": "Sheena Nelson"}, format="json"
        )
        assert response.status_code == 201
        guest = Guest.objects.get(phone="+14155550100")
        assert (guest.first_name, guest.last_name, guest.organization) == (
            "Sheena",
            "Nelson",
            prop.organization,
        )

    def test_validation(self, api):
        response = api.post(f"{BASE}inbound/", {"phone": "abc", "body": "Hola"}, format="json")
        assert response.status_code == 400 and response.json()["code"] == "invalid_phone"
        response = api.post(f"{BASE}inbound/", {"phone": "+573001112233", "body": ""}, format="json")
        assert response.status_code == 400 and "body" in response.json()["fields"]

    def test_disabled_while_whatsapp_is_real(self, api, prop):
        setting = integrations.get_setting(prop, "whatsapp")
        setting.mode = "real"
        setting.save()
        response = api.post(f"{BASE}inbound/", {"phone": "+573001112233", "body": "Hola"}, format="json")
        assert response.status_code == 409 and response.json()["code"] == "simulator_disabled"
        assert Message.objects.count() == 0


class TestThread:
    def test_the_phone_sees_both_sides_of_the_chat(self, api, prop, guest):
        api.post(f"{BASE}inbound/", {"phone": "+573001112233", "body": "Hola"}, format="json")
        conversation_id = api.get(f"{BASE}thread/", {"phone": "+573001112233"}).json()["conversation_id"]
        api.post(
            f"/api/v1/messaging/conversations/{conversation_id}/messages/",
            {"body": "¡Hola Laura!"},
            format="json",
        )
        api.post(
            f"/api/v1/messaging/conversations/{conversation_id}/messages/",
            {"body": "Nota", "internal": True},
            format="json",
        )

        data = api.get(f"{BASE}thread/", {"phone": "3001112233"}).json()

        assert (data["phone"], data["simulator_enabled"], data["guest"]["full_name"]) == (
            "+573001112233",
            True,
            "Laura Gómez",
        )
        # The guest never sees internal notes.
        assert [(m["direction"], m["body"]) for m in data["messages"]] == [
            ("in", "Hola"),
            ("out", "¡Hola Laura!"),
        ]

    def test_a_phone_without_messages(self, api, guest):
        data = api.get(f"{BASE}thread/", {"phone": "+573001112233"}).json()
        assert (data["conversation_id"], data["messages"], data["guest"]["id"]) == (None, [], str(guest.pk))

    def test_an_invalid_phone(self, api):
        response = api.get(f"{BASE}thread/", {"phone": "hola"})
        assert response.status_code == 400 and response.json()["code"] == "invalid_phone"

    def test_other_hotels_threads_are_not_shown(self, api, prop, guest):
        from apps.messaging.services import receive_whatsapp

        receive_whatsapp(
            PropertyFactory(organization=prop.organization), phone="+573001112233", body="Otro hotel"
        )
        assert api.get(f"{BASE}thread/", {"phone": "+573001112233"}).json()["messages"] == []


class TestContacts:
    def test_guests_with_a_phone_are_searchable(self, api, prop, guest):
        GuestFactory(organization=prop.organization, first_name="Sin", last_name="Teléfono", phone="")
        GuestFactory(organization=PropertyFactory().organization, first_name="Laura", phone="+573009998877")
        data = api.get(f"{BASE}contacts/", {"q": "laura"}).json()
        assert data["simulator_enabled"] is True
        assert [(r["guest_id"], r["full_name"], r["phone"]) for r in data["results"]] == [
            (str(guest.pk), "Laura Gómez", "+573001112233")
        ]
        assert api.get(f"{BASE}contacts/", {"q": "2233"}).json()["results"][0]["guest_id"] == str(guest.pk)

    def test_without_a_search_the_guests_arriving_or_in_house_come_first(self, api, prop, guest):
        arriving = GuestFactory(organization=prop.organization, first_name="Mateo", phone="+573005556677")
        ReservationFactory(
            property=prop,
            booker=arriving,
            status="confirmed",
            checkin_date=prop.business_date + timedelta(days=1),
            checkout_date=prop.business_date + timedelta(days=3),
        )
        rows = api.get(f"{BASE}contacts/").json()["results"]
        assert rows[0]["guest_id"] == str(arriving.pk)
        assert rows[0]["reservation"]["status"] == "confirmed"


def test_the_simulator_needs_the_send_permission(api_for, prop, member_with):
    client = api_for(member_with("messaging.view"), prop)
    for method, path, body in (
        ("post", "inbound/", {"phone": "+573001112233", "body": "x"}),
        ("get", "thread/", {"phone": "+573001112233"}),
        ("get", "contacts/", {}),
    ):
        response = getattr(client, method)(
            f"{BASE}{path}", body, **({"format": "json"} if method == "post" else {})
        )
        assert response.status_code == 403 and response.json()["permission"] == "messaging.send", path
