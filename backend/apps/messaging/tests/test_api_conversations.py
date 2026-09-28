"""Unified inbox API: `/api/v1/messaging/conversations/…` (staff, `X-Property-Id`)."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.tests.factories import PropertyFactory
from apps.guests.tests.factories import GuestFactory
from apps.inventory.tests.factories import RoomFactory, RoomTypeFactory
from apps.messaging.models import Conversation, Message
from apps.messaging.tests.factories import ConversationFactory, MessageFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/messaging/conversations/"


def _at(minutes_ago: int):
    return timezone.now() - timedelta(minutes=minutes_ago)


@pytest.fixture
def guest(prop):
    return GuestFactory(
        organization=prop.organization,
        first_name="Laura",
        last_name="Gómez",
        email="laura@example.com",
        phone="+573001112233",
        language="es",
        is_vip=True,
    )


@pytest.fixture
def reservation(prop, guest):
    return ReservationFactory(
        property=prop,
        booker=guest,
        code="HT-LAURA1",
        checkin_date=date(2026, 10, 9),
        checkout_date=date(2026, 10, 11),
        adults=2,
        children=0,
        total_amount=Decimal("761600"),
    )


@pytest.fixture
def whatsapp_thread(prop, guest, reservation):
    conversation = ConversationFactory(
        property=prop,
        guest=guest,
        reservation=reservation,
        channel="whatsapp",
        external_thread_key="+573001112233",
        contact_name="Laura Gómez",
        unread_count=2,
        last_message_at=_at(5),
        last_message_preview="¿Hay parqueadero?",
        last_message_direction="in",
        last_inbound_at=_at(5),
    )
    MessageFactory(conversation=conversation, body="Hola", sender_label="Laura Gómez")
    MessageFactory(conversation=conversation, body="¿Hay parqueadero?", sender_label="Laura Gómez")
    return conversation


class TestList:
    def test_rows_carry_the_thread_summary(self, api, whatsapp_thread, guest, reservation):
        response = api.get(URL)

        assert response.status_code == 200
        (row,) = response.json()["results"]
        assert row == {
            "id": str(whatsapp_thread.pk),
            "channel": "whatsapp",
            "status": "open",
            "contact_name": "Laura Gómez",
            "address": "+573001112233",
            "display_name": "Laura Gómez",
            "guest": {
                "id": str(guest.pk),
                "full_name": "Laura Gómez",
                "email": "laura@example.com",
                "phone": "+573001112233",
                "language": "es",
                "is_vip": True,
            },
            "reservation": {
                "id": str(reservation.pk),
                "code": "HT-LAURA1",
                "status": reservation.status,
                "checkin_date": "2026-10-09",
                "checkout_date": "2026-10-11",
                "room": "",
            },
            "assigned_to": None,
            "last_message_at": row["last_message_at"],
            "last_message_preview": "¿Hay parqueadero?",
            "last_message_direction": "in",
            "last_inbound_at": row["last_inbound_at"],
            "unread_count": 2,
            "whatsapp_window_open": True,
            "created_at": row["created_at"],
        }
        assert row["last_message_at"] is not None
        # The inbox counts down the WhatsApp 24 h window from the guest's last message.
        assert (
            row["last_inbound_at"]
            == whatsapp_thread.last_inbound_at.astimezone(timezone.get_current_timezone()).isoformat()
        )

    def test_the_room_of_the_reservation_is_shown_like_its_key_tag(self, api, prop, whatsapp_thread):
        room_type = RoomTypeFactory(property=prop)
        room = RoomFactory(room_type=room_type, number="301")
        StayFactory(reservation=whatsapp_thread.reservation, room_type=room_type, room=room)
        (row,) = api.get(URL).json()["results"]
        assert row["reservation"]["room"] == "301"

    def test_newest_activity_first(self, api, prop):
        old = ConversationFactory(property=prop, last_message_at=_at(60))
        new = ConversationFactory(property=prop, last_message_at=_at(1))
        empty = ConversationFactory(property=prop, last_message_at=None)
        ids = [row["id"] for row in api.get(URL).json()["results"]]
        assert ids == [str(new.pk), str(old.pk), str(empty.pk)]

    def test_other_hotels_threads_are_invisible(self, api, prop):
        ConversationFactory(property=PropertyFactory(organization=prop.organization))
        ConversationFactory(property=PropertyFactory())
        mine = ConversationFactory(property=prop)
        assert [row["id"] for row in api.get(URL).json()["results"]] == [str(mine.pk)]

    def test_filters(self, api, prop, owner, whatsapp_thread, reservation, guest):
        email = ConversationFactory(
            property=prop,
            channel="email",
            external_thread_key="x@example.com",
            assigned_to=owner,
            last_message_at=_at(30),
        )
        closed = ConversationFactory(
            property=prop, status="closed", last_message_at=_at(40), contact_name="Pedro Pérez"
        )

        def ids(**params):
            return {row["id"] for row in api.get(URL, params).json()["results"]}

        assert ids(unread=1) == {str(whatsapp_thread.pk)}
        assert ids(channel="email") == {str(email.pk)}
        assert ids(status="closed") == {str(closed.pk)}
        assert ids(status="open") == {str(whatsapp_thread.pk), str(email.pk)}
        assert ids(assigned="me") == {str(email.pk)}
        assert ids(assigned="none") == {str(whatsapp_thread.pk), str(closed.pk)}
        assert ids(reservation=str(reservation.pk)) == {str(whatsapp_thread.pk)}
        assert ids(guest=str(guest.pk)) == {str(whatsapp_thread.pk)}
        assert ids(q="pérez") == {str(closed.pk)}
        assert ids(q="HT-LAURA1") == {str(whatsapp_thread.pk)}
        assert ids(q="3001112233") == {str(whatsapp_thread.pk)}

    def test_an_invalid_filter_is_a_validation_error(self, api):
        response = api.get(URL, {"reservation": "nope"})
        assert response.status_code == 400 and response.json()["code"] == "validation_error"

    def test_the_query_count_does_not_grow_with_the_threads(self, api, prop, django_assert_max_num_queries):
        for number in range(6):
            guest = GuestFactory(organization=prop.organization)
            reservation = ReservationFactory(property=prop, booker=guest)
            room_type = RoomTypeFactory(property=prop)
            room = RoomFactory(room_type=room_type, number=f"4{number:02d}")
            StayFactory(reservation=reservation, room_type=room_type, room=room)
            ConversationFactory(property=prop, guest=guest, reservation=reservation)
        with django_assert_max_num_queries(12):
            assert len(api.get(URL).json()["results"]) == 6


class TestDetail:
    def test_the_sidebar_context_of_the_reservation(self, api, prop, whatsapp_thread, reservation):
        room_type = RoomTypeFactory(property=prop, name={"es": "Suite", "en": "Suite"})
        StayFactory(
            reservation=reservation,
            room_type=room_type,
            room=RoomFactory(room_type=room_type, number="301"),
            total_amount=Decimal("761600"),
        )

        data = api.get(f"{URL}{whatsapp_thread.pk}/").json()

        assert data["reservation"]["code"] == "HT-LAURA1"
        assert data["context"]["reservation"] == {
            "id": str(reservation.pk),
            "code": "HT-LAURA1",
            "status": reservation.status,
            "source": reservation.source,
            "checkin_date": "2026-10-09",
            "checkout_date": "2026-10-11",
            "nights": 2,
            "adults": 2,
            "children": 0,
            "currency": "COP",
            "total_amount": "761600.00",
            "balance": "761600.00",
            "room_types": ["Suite"],
            "rooms": ["301"],
        }
        assert data["context"]["guest"]["full_name"] == "Laura Gómez"

    def test_another_hotels_thread_is_not_found(self, api):
        other = ConversationFactory(property=PropertyFactory())
        assert api.get(f"{URL}{other.pk}/").status_code == 404
        assert api.get(f"{URL}{other.pk}/messages/").status_code == 404
        assert api.post(f"{URL}{other.pk}/messages/", {"body": "x"}, format="json").status_code == 404


class TestMessages:
    def test_the_thread_oldest_first(self, api, whatsapp_thread):
        MessageFactory(
            conversation=whatsapp_thread,
            direction="out",
            status="read",
            body="Sí, gratis",
            sender_label="Recepción",
        )
        data = api.get(f"{URL}{whatsapp_thread.pk}/messages/").json()
        assert [m["body"] for m in data["results"]] == ["Hola", "¿Hay parqueadero?", "Sí, gratis"]
        assert data["has_more"] is False
        last = data["results"][-1]
        assert {k: last[k] for k in ("direction", "channel", "status", "sender_label", "ai_generated")} == {
            "direction": "out",
            "channel": "whatsapp",
            "status": "read",
            "sender_label": "Recepción",
            "ai_generated": False,
        }

    def test_older_pages_with_before_and_limit(self, api, whatsapp_thread):
        for n in range(3):
            MessageFactory(conversation=whatsapp_thread, body=f"m{n}")
        first = api.get(f"{URL}{whatsapp_thread.pk}/messages/", {"limit": 2}).json()
        assert [m["body"] for m in first["results"]] == ["m1", "m2"] and first["has_more"] is True
        older = api.get(
            f"{URL}{whatsapp_thread.pk}/messages/", {"limit": 2, "before": first["results"][0]["created_at"]}
        ).json()
        assert [m["body"] for m in older["results"]] == ["¿Hay parqueadero?", "m0"] and older[
            "has_more"
        ] is True


class TestReply:
    def test_a_whatsapp_reply_goes_out_and_clears_the_unread_count(self, api, owner, whatsapp_thread):
        response = api.post(
            f"{URL}{whatsapp_thread.pk}/messages/", {"body": "Sí, **gratis** 🚗"}, format="json"
        )

        assert response.status_code == 201
        data = response.json()
        assert {k: data[k] for k in ("direction", "channel", "status", "body", "recipient")} == {
            "direction": "out",
            "channel": "whatsapp",
            "status": "delivered",
            "body": "Sí, *gratis* 🚗",
            "recipient": "+573001112233",
        }
        assert data["sent_by"]["id"] == str(owner.pk)
        whatsapp_thread.refresh_from_db()
        assert (whatsapp_thread.unread_count, whatsapp_thread.last_message_direction) == (0, "out")

    def test_an_email_reply_keeps_the_thread_subject(self, api, prop, guest, reservation):
        conversation = ConversationFactory(
            property=prop,
            guest=guest,
            reservation=reservation,
            channel="email",
            external_thread_key="laura@example.com",
        )
        MessageFactory(
            conversation=conversation,
            channel="email",
            subject="Traslado desde el aeropuerto",
            body="¿Tienen traslado?",
        )

        response = api.post(
            f"{URL}{conversation.pk}/messages/", {"body": "Hola {{guest.first_name}}, sí."}, format="json"
        )

        assert response.status_code == 201
        (email,) = mail.outbox
        assert (email.to, email.subject, email.body) == (
            ["laura@example.com"],
            "Re: Traslado desde el aeropuerto",
            "Hola Laura, sí.",
        )
        assert "Hola Laura, sí." in email.alternatives[0][0]
        assert Message.objects.get(pk=response.json()["id"]).subject == "Re: Traslado desde el aeropuerto"

    def test_an_explicit_subject_wins(self, api, prop, guest):
        conversation = ConversationFactory(
            property=prop, guest=guest, channel="email", external_thread_key="laura@example.com"
        )
        api.post(
            f"{URL}{conversation.pk}/messages/", {"body": "Hola", "subject": "Tu factura"}, format="json"
        )
        assert mail.outbox[0].subject == "Tu factura"

    def test_an_internal_note_is_never_sent(self, api, whatsapp_thread):
        response = api.post(
            f"{URL}{whatsapp_thread.pk}/messages/",
            {"body": "Pedir a mantenimiento", "internal": True},
            format="json",
        )
        assert response.status_code == 201
        data = response.json()
        assert (data["channel"], data["direction"], data["recipient"]) == ("internal_note", "out", "")
        assert mail.outbox == []
        whatsapp_thread.refresh_from_db()
        # A note does not answer the guest: the thread keeps its unread count and preview.
        assert (whatsapp_thread.unread_count, whatsapp_thread.last_message_preview) == (
            2,
            "¿Hay parqueadero?",
        )

    def test_an_ai_draft_is_flagged(self, api, whatsapp_thread):
        response = api.post(
            f"{URL}{whatsapp_thread.pk}/messages/", {"body": "Hola", "ai_generated": True}, format="json"
        )
        assert Message.objects.get(pk=response.json()["id"]).ai_generated is True

    def test_an_empty_reply_is_rejected(self, api, whatsapp_thread):
        response = api.post(f"{URL}{whatsapp_thread.pk}/messages/", {"body": "   "}, format="json")
        assert response.status_code == 400 and "body" in response.json()["fields"]

    def test_ota_threads_cannot_be_answered_from_here(self, api, prop):
        conversation = ConversationFactory(property=prop, channel="ota", external_thread_key="booksim:1")
        response = api.post(f"{URL}{conversation.pk}/messages/", {"body": "Hola"}, format="json")
        assert response.status_code == 409 and response.json()["code"] == "channel_not_supported"

    def test_an_anonymized_thread_has_no_address(self, api, prop):
        conversation = ConversationFactory(property=prop, external_thread_key="anonymized:1")
        response = api.post(f"{URL}{conversation.pk}/messages/", {"body": "Hola"}, format="json")
        assert response.status_code == 409 and response.json()["code"] == "conversation_anonymized"


class TestActions:
    def test_read(self, api, whatsapp_thread):
        response = api.post(f"{URL}{whatsapp_thread.pk}/read/")
        assert response.status_code == 200 and response.json()["unread_count"] == 0

    def test_assign_to_a_member_and_back_to_nobody(self, api, whatsapp_thread, make_member):
        colleague = make_member("front_desk", full_name="Andrés Gómez")
        response = api.post(
            f"{URL}{whatsapp_thread.pk}/assign/", {"user_id": str(colleague.pk)}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["assigned_to"] == {
            "id": str(colleague.pk),
            "full_name": "Andrés Gómez",
            "email": colleague.email,
        }
        response = api.post(f"{URL}{whatsapp_thread.pk}/assign/", {"user_id": None}, format="json")
        assert response.json()["assigned_to"] is None

    def test_only_members_of_this_hotel_can_be_assigned(self, api, prop, whatsapp_thread, make_member):
        sibling = PropertyFactory(organization=prop.organization)
        elsewhere = make_member("front_desk", properties=[sibling])
        from apps.accounts.tests.factories import UserFactory

        for user in (elsewhere, UserFactory()):
            response = api.post(
                f"{URL}{whatsapp_thread.pk}/assign/", {"user_id": str(user.pk)}, format="json"
            )
            assert response.status_code == 400 and response.json()["code"] == "invalid_user"

    def test_close_and_reopen(self, api, whatsapp_thread):
        assert api.post(f"{URL}{whatsapp_thread.pk}/close/").json()["status"] == "closed"
        assert api.post(f"{URL}{whatsapp_thread.pk}/reopen/").json()["status"] == "open"

    def test_unread_count(self, api, prop, whatsapp_thread):
        ConversationFactory(property=prop, unread_count=1)
        ConversationFactory(property=prop, unread_count=3, status="closed")
        ConversationFactory(property=PropertyFactory(), unread_count=9)
        assert api.get(f"{URL}unread-count/").json() == {"conversations": 2, "messages": 3}


class TestPermissions:
    def test_housekeeping_cannot_read_the_inbox(self, api_for, prop, make_member):
        response = api_for(make_member("housekeeping"), prop).get(URL)
        assert response.status_code == 403 and response.json()["permission"] == "messaging.view"

    def test_reading_is_not_answering(self, api_for, prop, member_with, whatsapp_thread):
        reader = api_for(member_with("messaging.view"), prop)
        assert reader.get(URL).status_code == 200
        assert reader.post(f"{URL}{whatsapp_thread.pk}/read/").status_code == 200
        for path, body in (("messages/", {"body": "x"}), ("assign/", {"user_id": None}), ("close/", {})):
            response = reader.post(f"{URL}{whatsapp_thread.pk}/{path}", body, format="json")
            assert response.status_code == 403 and response.json()["permission"] == "messaging.send", path

    def test_front_desk_answers(self, api_for, prop, make_member, whatsapp_thread):
        response = api_for(make_member("front_desk"), prop).post(
            f"{URL}{whatsapp_thread.pk}/messages/", {"body": "Hola"}, format="json"
        )
        assert response.status_code == 201

    def test_anonymous_is_rejected(self, public_api):
        assert public_api.get(URL).status_code == 401


def test_conversations_track_messages_created_through_the_services(api, prop, guest):
    from apps.messaging.services import receive_whatsapp

    receive_whatsapp(prop, phone="+573001112233", body="Hola")
    row = api.get(URL).json()["results"][0]
    assert (row["unread_count"], row["last_message_preview"], row["guest"]["id"]) == (
        1,
        "Hola",
        str(guest.pk),
    )
    assert Conversation.objects.count() == 1
