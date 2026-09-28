"""Draft replies for the unified inbox (`POST /api/v1/ai/draft-reply/`, plan §C: C9 → C6)."""

import json

import pytest

from apps.ai.models import AISettings, PropertyFAQ
from apps.bookings.tests.helpers import book, build_hotel, foreign_input, oct_

pytestmark = pytest.mark.django_db

URL = "/api/v1/ai/draft-reply/"


@pytest.fixture
def hotel(prop, llm_mode):
    llm_mode("simulated")
    PropertyFAQ.objects.create(
        property=prop,
        question="¿Tienen parqueadero?",
        language="es",
        answer="Sí, tenemos parqueadero cubierto por 25.000 la noche.",
    )
    PropertyFAQ.objects.create(
        property=prop,
        question="Do you have parking?",
        language="en",
        answer="Yes, covered parking for 25,000 per night.",
    )
    return build_hotel(prop)


def test_the_offline_draft_answers_from_the_faq_and_greets_the_guest(hotel, api):
    reservation = book(hotel, oct_(3), oct_(5))

    response = api.post(
        URL,
        {"guest_message": "¿Tienen parqueadero para el carro?", "reservation_code": reservation.code},
        format="json",
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["simulated"] is True
    assert "Laura" in body["text"]
    assert "parqueadero cubierto por 25.000" in body["text"]
    assert body["language"] == "es"


def test_the_draft_follows_the_guests_language(hotel, api):
    reservation = book(hotel, oct_(3), oct_(5), booker=foreign_input())

    body = api.post(
        URL, {"guest_message": "Do you have parking?", "reservation_code": reservation.code}, format="json"
    ).json()

    assert body["language"] == "en"
    assert "John" in body["text"] and "covered parking" in body["text"]


def test_the_model_gets_the_message_the_reservation_and_the_hotels_knowledge(hotel, api, monkeypatch):
    from apps.ai.tests.fakes import ScriptedLLM, real_data

    reservation = book(hotel, oct_(3), oct_(5))
    llm = ScriptedLLM([real_data({"text": "Hola Laura, sí tenemos parqueadero."})])
    monkeypatch.setattr("apps.ai.drafts.llm_for", lambda prop, feature, **kwargs: llm)

    body = api.post(
        URL,
        {"guest_message": "¿Hay parqueadero?", "reservation_code": reservation.code, "tone": "formal"},
        format="json",
    ).json()

    assert body == {"text": "Hola Laura, sí tenemos parqueadero.", "simulated": False, "language": "es"}
    payload = json.loads(llm.calls[0]["messages"][-1]["content"])
    assert (payload["guest_message"], payload["reservation"]["code"], payload["tone"]) == (
        "¿Hay parqueadero?",
        reservation.code,
        "formal",
    )
    assert any("parqueadero cubierto" in line for line in payload["knowledge"])


def test_a_reservation_of_another_hotel_is_not_used(hotel, api, organization):
    from apps.core.tests.factories import PropertyFactory

    other = build_hotel(PropertyFactory(organization=organization))
    foreign = book(other, oct_(3), oct_(5))

    body = api.post(URL, {"guest_message": "hola", "reservation_code": foreign.code}, format="json").json()

    assert foreign.booker.first_name not in body["text"]


def test_drafting_needs_the_send_permission(hotel, make_member, api_for):
    housekeeping = api_for(make_member("housekeeping"), hotel.prop)
    front = api_for(make_member("front_desk"), hotel.prop)

    assert housekeeping.post(URL, {"guest_message": "hola"}, format="json").status_code == 403
    assert front.post(URL, {"guest_message": "hola"}, format="json").status_code == 200


def test_the_inbox_hides_the_button_when_drafts_are_off(hotel, api):
    AISettings.objects.update_or_create(property=hotel.prop, defaults={"draft_replies_enabled": False})

    response = api.post(URL, {"guest_message": "hola"}, format="json")

    assert response.status_code == 404


def test_the_guest_message_is_required(hotel, api):
    assert api.post(URL, {"guest_message": ""}, format="json").status_code == 400
