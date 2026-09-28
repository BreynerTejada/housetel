"""Copilot API (`/api/v1/ai/copilot/…`, permission ai.copilot): sessions, messages (agent loop) and the
confirmation or rejection of proposals. Runs with the offline assistant (no credentials)."""

import pytest

from apps.ai.models import AISettings, CopilotAction, CopilotSession
from apps.bookings.tests.helpers import book, build_hotel, oct_

pytestmark = pytest.mark.django_db

BASE = "/api/v1/ai/copilot"


@pytest.fixture
def hotel(prop, llm_mode):
    llm_mode("simulated")
    return build_hotel(prop)  # business date 2026-10-01


def new_session(client) -> str:
    response = client.post(f"{BASE}/sessions/", {}, format="json")
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def ask(client, session_id, text):
    return client.post(f"{BASE}/sessions/{session_id}/messages/", {"message": text}, format="json")


def test_a_conversation_through_the_api(hotel, api):
    arriving = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    session_id = new_session(api)

    response = ask(api, session_id, "¿Cuántas llegadas hay hoy?")

    assert response.status_code == 200, response.json()
    body = response.json()
    assert [message["role"] for message in body["messages"]] == ["user", "assistant", "tool", "assistant"]
    assert body["messages"][1]["tool_calls"][0]["name"] == "list_arrivals"
    assert "meta" not in body["messages"][1]["tool_calls"][0]
    assert arriving.code in body["messages"][-1]["content"]
    assert body["messages"][-1]["simulated"] is True
    assert body["proposals"] == []
    assert body["session"]["title"] == "¿Cuántas llegadas hay hoy?"

    detail = api.get(f"{BASE}/sessions/{session_id}/").json()
    assert len(detail["messages"]) == 4 and detail["actions"] == []
    listed = api.get(f"{BASE}/sessions/").json()
    assert [item["id"] for item in listed["results"]] == [session_id]


def test_a_proposal_is_confirmed_through_the_api(hotel, api):
    from apps.inventory.models import RoomBlock

    session_id = new_session(api)

    body = ask(api, session_id, "Bloquea la 201 mañana por mantenimiento").json()

    (proposal,) = body["proposals"]
    assert (proposal["action"], proposal["status"], proposal["details"]["room"]) == (
        "block_room",
        "proposed",
        "201",
    )
    assert not RoomBlock.objects.exists()

    confirmed = api.post(f"{BASE}/actions/{proposal['id']}/confirm/", {}, format="json")

    assert confirmed.status_code == 200, confirmed.json()
    assert confirmed.json()["status"] == "executed"
    assert RoomBlock.objects.get().room == hotel.rooms["201"]
    detail = api.get(f"{BASE}/sessions/{session_id}/").json()
    assert [(action["id"], action["status"]) for action in detail["actions"]] == [
        (proposal["id"], "executed")
    ]


def test_a_proposal_can_be_rejected(hotel, api):
    session_id = new_session(api)
    (proposal,) = ask(api, session_id, "Bloquea la 201 mañana").json()["proposals"]

    rejected = api.post(f"{BASE}/actions/{proposal['id']}/reject/", {}, format="json")
    again = api.post(f"{BASE}/actions/{proposal['id']}/confirm/", {}, format="json")

    assert rejected.json()["status"] == "rejected"
    assert (again.status_code, again.json()["code"]) == (409, "action_not_pending")


def test_housekeeping_cannot_use_the_copilot(hotel, make_member, api_for):
    client = api_for(make_member("housekeeping"), hotel.prop)

    response = client.get(f"{BASE}/sessions/")

    assert response.status_code == 403
    assert response.json()["permission"] == "ai.copilot"


def test_confirming_needs_the_actions_permission_at_that_moment(hotel, make_member, api_for, organization):
    """A role with the copilot but without bookings.manage cannot confirm a reservation proposed earlier."""
    from apps.accounts.models import Membership
    from apps.accounts.tests.factories import RoleFactory

    front = make_member("front_desk")
    client = api_for(front, hotel.prop)
    session_id = new_session(client)
    (proposal,) = ask(client, session_id, "Crea una reserva para Ana Pérez del 12 al 14 de octubre").json()[
        "proposals"
    ]
    membership = Membership.objects.get(user=front)
    membership.role = RoleFactory(organization=organization, permissions=["ai.copilot", "bookings.view"])
    membership.save()

    response = client.post(f"{BASE}/actions/{proposal['id']}/confirm/", {}, format="json")

    assert response.status_code == 403
    assert (response.json()["code"], response.json()["permission"]) == (
        "permission_denied",
        "bookings.manage",
    )
    assert CopilotAction.objects.get(pk=proposal["id"]).status == "proposed"


def test_sessions_and_proposals_of_other_users_or_hotels_are_invisible(
    hotel, api, make_member, api_for, organization
):
    from apps.core.tests.factories import PropertyFactory

    session_id = new_session(api)
    (proposal,) = ask(api, session_id, "Bloquea la 201 mañana").json()["proposals"]
    colleague = api_for(make_member("owner"), hotel.prop)
    other_hotel = PropertyFactory(organization=organization)
    same_user_other_hotel = api_for(CopilotSession.objects.get().user, other_hotel)

    assert colleague.get(f"{BASE}/sessions/{session_id}/").status_code == 404
    assert colleague.post(f"{BASE}/actions/{proposal['id']}/confirm/", {}, format="json").status_code == 404
    assert same_user_other_hotel.get(f"{BASE}/sessions/{session_id}/").status_code == 404
    assert same_user_other_hotel.post(f"{BASE}/actions/{proposal['id']}/confirm/", {}).status_code == 404
    assert colleague.get(f"{BASE}/sessions/").json()["results"] == []


def test_the_copilot_can_be_switched_off(hotel, api):
    AISettings.objects.update_or_create(property=hotel.prop, defaults={"copilot_enabled": False})
    session_id = new_session(api)

    response = ask(api, session_id, "hola")

    assert (response.status_code, response.json()["code"]) == (409, "feature_disabled")


def test_an_empty_message_is_rejected(hotel, api):
    session_id = new_session(api)

    response = ask(api, session_id, "   ")

    assert response.status_code == 400
    assert "message" in response.json()["fields"]


def test_a_session_can_be_deleted(hotel, api):
    session_id = new_session(api)

    assert api.delete(f"{BASE}/sessions/{session_id}/").status_code == 204
    assert not CopilotSession.objects.exists()
