"""Public chatbot (`/api/v1/public/ai/chat/<slug>/`): hotel knowledge + FAQ, availability with offer cards
that link to the booking engine, hand-off to a person (alert + inbox thread) and per-session rate limit."""

import pytest
from freezegun import freeze_time

from apps.ai.models import AISettings, ChatbotConversation, PropertyFAQ
from apps.bookings.tests.helpers import build_hotel
from apps.core.models import Alert

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("frozen_today")]


@pytest.fixture
def frozen_today():
    from django.urls import get_resolver

    # Import every view (and DRF's throttles, which keep `time.time` as a class attribute) before freezing.
    get_resolver().url_patterns  # noqa: B018
    with freeze_time("2026-10-01 10:00:00-05:00"):  # Thursday, the hotel's business date
        yield


@pytest.fixture
def hotel(prop, llm_mode):
    llm_mode("simulated")
    return build_hotel(prop)


def url(hotel, suffix=""):
    return f"/api/v1/public/ai/chat/{hotel.prop.slug}/{suffix}"


def chat(public_api, hotel, message, session_id=None, language="es"):
    payload = {"message": message, "language": language}
    if session_id:
        payload["session_id"] = session_id
    return public_api.post(url(hotel), payload, format="json")


def test_the_chatbot_answers_availability_with_offer_cards(hotel, public_api):
    response = chat(public_api, hotel, "¿Tienen habitación del 12 al 14 de octubre para 2 personas?")

    assert response.status_code == 200, response.json()
    body = response.json()
    reply = body["reply"]
    assert "Categoría DBL" in reply["content"] and "$ 761.600" in reply["content"]
    cards = {card["room_type_code"]: card for card in reply["cards"]}
    assert cards["DBL"] == {
        **cards["DBL"],
        "type": "offer",
        "total": "761600.00",
        "nights": 2,
        "currency": "COP",
        "url": f"/h/{hotel.prop.slug}?checkin=2026-10-12&checkout=2026-10-14&adults=2&children=0",
    }
    assert body["session_id"]
    conversation = ChatbotConversation.objects.get(session_id=body["session_id"])
    assert [message["role"] for message in conversation.messages] == ["user", "assistant"]
    assert conversation.messages[1]["cards"] == reply["cards"]


def test_the_chatbot_answers_from_the_hotels_faq(hotel, public_api):
    PropertyFAQ.objects.create(
        property=hotel.prop,
        question="¿Tienen parqueadero?",
        answer="Sí, parqueadero cubierto por 25.000 la noche.",
        language="es",
    )

    reply = chat(public_api, hotel, "¿hay estacionamiento para el carro?").json()["reply"]

    assert reply["content"] == "Sí, parqueadero cubierto por 25.000 la noche."
    assert reply["cards"] == []


def test_the_knowledge_includes_check_in_hours(hotel, public_api):
    reply = chat(public_api, hotel, "¿A qué hora es el check in?").json()["reply"]

    assert "15:00" in reply["content"]


def test_asking_for_a_person_hands_off_and_raises_an_alert(hotel, public_api):
    body = chat(public_api, hotel, "Quiero hablar con una persona").json()

    assert body["handoff"] == {"requested": True, "contact_needed": True, "contact_received": False}
    conversation = ChatbotConversation.objects.get(session_id=body["session_id"])
    assert (conversation.handoff_requested, conversation.handoff_reason) == (True, "requested")
    alert = Alert.objects.get(property=hotel.prop, kind="chatbot_handoff", resolved_at__isnull=True)
    assert alert.link == f"/app/settings/chatbot?conversation={conversation.pk}"
    assert alert.dedupe_key == f"ai:chatbot_handoff:{conversation.pk}"


def test_a_question_it_cannot_answer_is_handed_off(hotel, public_api):
    body = chat(public_api, hotel, "¿Cuál es la capital de Francia?").json()

    assert body["handoff"]["requested"] is True
    conversation = ChatbotConversation.objects.get(session_id=body["session_id"])
    assert conversation.handoff_reason == "low_confidence"


def test_the_contact_updates_the_alert_and_opens_an_inbox_thread(hotel, public_api):
    from apps.messaging.models import Conversation

    session_id = chat(public_api, hotel, "Quiero hablar con una persona").json()["session_id"]

    response = public_api.post(
        url(hotel, "contact/"),
        {
            "session_id": session_id,
            "name": "Marta Ruiz",
            "email": "marta@example.com",
            "phone": "",
            "message": "Quiero celebrar un cumpleaños",
        },
        format="json",
    )

    assert response.status_code == 200, response.json()
    assert response.json()["handoff"] == {
        "requested": True,
        "contact_needed": False,
        "contact_received": True,
    }
    conversation = ChatbotConversation.objects.get(session_id=session_id)
    assert conversation.contact["email"] == "marta@example.com"
    alert = Alert.objects.get(kind="chatbot_handoff", resolved_at__isnull=True)
    assert "marta@example.com" in alert.message
    thread = Conversation.objects.get(property=hotel.prop, channel="web_chat")
    assert "Quiero celebrar un cumpleaños" in thread.messages.get().body


def test_the_contact_needs_an_email_or_a_phone(hotel, public_api):
    session_id = chat(public_api, hotel, "Quiero hablar con una persona").json()["session_id"]

    response = public_api.post(
        url(hotel, "contact/"), {"session_id": session_id, "name": "Marta"}, format="json"
    )

    assert response.status_code == 400


def test_the_conversation_continues_with_its_session(hotel, public_api):
    session_id = chat(public_api, hotel, "Hola").json()["session_id"]

    chat(public_api, hotel, "¿Tienen habitación para mañana?", session_id=session_id)
    history = public_api.get(url(hotel), {"session_id": session_id}).json()

    assert [message["role"] for message in history["messages"]] == ["user", "assistant", "user", "assistant"]
    assert ChatbotConversation.objects.count() == 1


def test_the_widget_config_of_an_unknown_or_disabled_chatbot_is_404(hotel, public_api):
    assert public_api.get("/api/v1/public/ai/chat/no-existe/").status_code == 404
    config = public_api.get(url(hotel))
    assert config.status_code == 200 and config.json()["property"]["name"] == hotel.prop.name

    AISettings.objects.update_or_create(property=hotel.prop, defaults={"chatbot_enabled": False})

    assert public_api.get(url(hotel)).status_code == 404
    assert chat(public_api, hotel, "Hola").status_code == 404


def test_a_session_cannot_send_unlimited_messages(hotel, public_api, monkeypatch):
    monkeypatch.setattr("apps.ai.chatbot.SESSION_MESSAGE_LIMIT", 2)
    session_id = chat(public_api, hotel, "Hola").json()["session_id"]
    chat(public_api, hotel, "Hola otra vez", session_id=session_id)

    response = chat(public_api, hotel, "¿Sigues ahí?", session_id=session_id)

    assert (response.status_code, response.json()["code"]) == (429, "rate_limited")


def test_the_guest_portal_chat_knows_the_reservation(hotel, public_api, monkeypatch):
    from apps.ai.tests.fakes import ScriptedLLM, real_text
    from apps.bookings.tests.helpers import book, oct_
    from apps.core.tokens import make_reservation_token

    reservation = book(hotel, oct_(3), oct_(5))
    llm = ScriptedLLM([real_text("Tu reserva está confirmada.")])
    monkeypatch.setattr("apps.ai.chatbot.llm_for", lambda prop, feature, **kwargs: llm)

    response = public_api.post(
        f"/api/v1/public/ai/portal-chat/{make_reservation_token(reservation)}/",
        {"message": "¿Mi reserva está confirmada?", "language": "es"},
        format="json",
    )

    assert response.status_code == 200, response.json()
    assert reservation.code in llm.calls[0]["system"]
    assert ChatbotConversation.objects.get().reservation == reservation


def test_a_forged_portal_token_is_404(hotel, public_api):
    assert (
        public_api.post(
            "/api/v1/public/ai/portal-chat/forged/", {"message": "hola"}, format="json"
        ).status_code
        == 404
    )


def test_past_dates_are_explained_instead_of_searched(hotel):
    from apps.ai.chatbot import guest_tool

    output = guest_tool(
        hotel.prop, None, "check_availability", {"checkin": "2026-09-01", "checkout": "2026-09-03"}, lang="es"
    )

    assert "error" in output
