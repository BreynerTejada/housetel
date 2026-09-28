"""`POST /api/v1/messaging/send/`: write to a guest from a reservation or guest profile (starts or continues
the conversation of the guest's address on that channel)."""

import pytest
from django.core import mail

from apps.bookings.tests.factories import ReservationFactory
from apps.core.tests.factories import PropertyFactory
from apps.guests.tests.factories import GuestFactory
from apps.messaging.models import Conversation, Message

pytestmark = pytest.mark.django_db

URL = "/api/v1/messaging/send/"


@pytest.fixture
def guest(prop):
    return GuestFactory(
        organization=prop.organization, first_name="Ana", email="ana@example.com", phone="+573001112233"
    )


@pytest.fixture
def reservation(prop, guest):
    return ReservationFactory(property=prop, booker=guest, code="HT-ANA001")


def test_a_template_by_email_for_a_reservation(api, prop, reservation):
    response = api.post(
        URL,
        {"channel": "email", "reservation_id": str(reservation.pk), "template_code": "checkin_invitation"},
        format="json",
    )

    assert response.status_code == 201
    data = response.json()
    (email,) = mail.outbox
    assert email.to == ["ana@example.com"] and "/checkin" in email.body
    message = Message.objects.get(pk=data["message"]["id"])
    assert (message.template_code, message.reservation, str(message.conversation_id)) == (
        "checkin_invitation",
        reservation,
        data["conversation_id"],
    )
    assert message.sent_by is not None


def test_free_text_by_whatsapp_to_a_guest(api, owner, guest):
    response = api.post(
        URL,
        {"channel": "whatsapp", "guest_id": str(guest.pk), "body": "Hola {{guest.first_name}}"},
        format="json",
    )
    assert response.status_code == 201
    message = Message.objects.get(pk=response.json()["message"]["id"])
    assert (message.body, message.recipient, message.status, message.sent_by) == (
        "Hola Ana",
        "+573001112233",
        "delivered",
        owner,
    )
    assert Conversation.objects.get().guest == guest


def test_free_text_by_email_gets_a_default_subject(api, prop, reservation):
    api.post(
        URL,
        {"channel": "email", "reservation_id": str(reservation.pk), "body": "¿Llegas en la tarde?"},
        format="json",
    )
    assert mail.outbox[0].subject == f"Mensaje de {prop.name}"


def test_an_explicit_address(api, reservation):
    api.post(
        URL,
        {
            "channel": "email",
            "reservation_id": str(reservation.pk),
            "to": "otra@example.com",
            "body": "Hola",
            "subject": "Hola",
        },
        format="json",
    )
    assert mail.outbox[0].to == ["otra@example.com"]


def test_without_an_address_nothing_is_sent(api, prop):
    silent = GuestFactory(organization=prop.organization, email="", phone="")
    response = api.post(
        URL, {"channel": "whatsapp", "guest_id": str(silent.pk), "body": "Hola"}, format="json"
    )
    assert response.status_code == 400 and response.json()["code"] == "no_address"
    assert Message.objects.count() == 0


def test_validation(api, guest):
    assert (
        api.post(URL, {"channel": "sms", "guest_id": str(guest.pk), "body": "x"}, format="json").status_code
        == 400
    )
    response = api.post(URL, {"channel": "email", "guest_id": str(guest.pk)}, format="json")
    assert response.status_code == 400 and response.json()["code"] == "validation_error"
    response = api.post(URL, {"channel": "email", "body": "x"}, format="json")
    assert response.status_code == 400


def test_other_organizations_guests_and_reservations_are_not_found(api):
    stranger = GuestFactory(organization=PropertyFactory().organization, email="x@example.com")
    foreign = ReservationFactory(property=PropertyFactory())
    assert (
        api.post(
            URL, {"channel": "email", "guest_id": str(stranger.pk), "body": "x"}, format="json"
        ).status_code
        == 404
    )
    assert (
        api.post(
            URL, {"channel": "email", "reservation_id": str(foreign.pk), "body": "x"}, format="json"
        ).status_code
        == 404
    )


def test_sending_needs_the_send_permission(api_for, prop, member_with, guest):
    response = api_for(member_with("messaging.view"), prop).post(
        URL, {"channel": "email", "guest_id": str(guest.pk), "body": "x"}, format="json"
    )
    assert response.status_code == 403 and response.json()["permission"] == "messaging.send"
