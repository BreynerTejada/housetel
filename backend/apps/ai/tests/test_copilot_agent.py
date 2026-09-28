"""The copilot's agent loop: the model asks for tools, the tools run with the hotel's data, the answer comes
back; at most 5 model calls per turn; actions only become proposals; every turn is stored."""

import json

import pytest

from apps.ai.copilot.agent import MAX_ITERATIONS, run_turn
from apps.ai.models import CopilotAction, CopilotMessage, CopilotSession
from apps.ai.tests.fakes import ScriptedLLM, real_calls, real_text
from apps.bookings.models import Reservation
from apps.bookings.tests.helpers import book, build_hotel, oct_

pytestmark = pytest.mark.django_db


@pytest.fixture
def hotel(prop):
    return build_hotel(prop)  # business date 2026-10-01


@pytest.fixture
def session(hotel, owner):
    return CopilotSession.objects.create(property=hotel.prop, user=owner)


def stored(session):
    return list(CopilotMessage.objects.filter(session=session).values_list("role", "name", "content"))


def test_a_question_runs_the_read_tool_and_answers_from_its_data(hotel, session, owner):
    arriving = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})
    llm = ScriptedLLM([real_calls(("list_arrivals", {})), real_text("Hoy llega 1 reserva.")])

    turn = run_turn(session, "¿Cuántas llegadas hay hoy?", user=owner, llm=llm)

    roles = [(role, name) for role, name, _ in stored(session)]
    assert roles == [("user", ""), ("assistant", ""), ("tool", "list_arrivals"), ("assistant", "")]
    tool_output = json.loads(stored(session)[2][2])
    assert (tool_output["count"], tool_output["items"][0]["code"]) == (1, arriving.code)
    # The second model call saw the tool result (with the real reservation code).
    assert arriving.code in llm.calls[1]["messages"][-1]["content"]
    assert [message.role for message in turn["messages"]] == ["user", "assistant", "tool", "assistant"]
    assert turn["messages"][-1].content == "Hoy llega 1 reserva."
    assert turn["proposals"] == []


def test_the_model_is_offered_only_the_tools_of_the_users_role(hotel, make_member):
    accountant = make_member("accountant")
    session = CopilotSession.objects.create(property=hotel.prop, user=accountant)
    llm = ScriptedLLM([real_text("ok")])

    run_turn(session, "hola", user=accountant, llm=llm)

    offered = set(llm.calls[0]["tools"])
    assert "get_balance" in offered and "add_extra" in offered
    assert not offered & {"create_reservation", "move_room", "check_in", "block_room"}


def test_the_system_prompt_carries_the_business_date_the_language_and_the_hotel(hotel, session, owner):
    llm = ScriptedLLM([real_text("Hi")])

    run_turn(session, "hello", user=owner, llm=llm, lang="en")

    system = llm.calls[0]["system"]
    assert "Fecha de hoy: 2026-10-01" in system
    assert "Idioma: en" in system
    assert hotel.prop.name in system


def test_the_loop_stops_after_five_model_calls(hotel, session, owner):
    llm = ScriptedLLM([real_calls(("get_today_summary", {})) for _ in range(MAX_ITERATIONS + 1)])

    turn = run_turn(session, "resumen", user=owner, llm=llm)

    assert MAX_ITERATIONS == 5
    assert len(llm.calls) == 5
    assert len(llm.results) == 1  # the sixth answer was never requested
    last = turn["messages"][-1]
    assert (last.role, last.tool_calls) == ("assistant", [])
    assert last.content  # tells the user it could not finish


def test_an_action_becomes_a_proposal_and_nothing_is_written(hotel, session, owner):
    llm = ScriptedLLM(
        [
            real_calls(
                (
                    "create_reservation",
                    {
                        "checkin": "2026-10-12",
                        "checkout": "2026-10-14",
                        "adults": 2,
                        "room_type": "DBL",
                        "guest_name": "Ana Pérez",
                    },
                )
            ),
            real_text("Preparé la reserva; confírmala en la tarjeta."),
        ]
    )

    turn = run_turn(session, "Reserva para Ana Pérez del 12 al 14 de octubre en DBL", user=owner, llm=llm)

    (proposal,) = turn["proposals"]
    action = CopilotAction.objects.get(pk=proposal.pk)
    assert (action.status, action.action_code, action.session) == ("proposed", "create_reservation", session)
    assert action.message.role == "assistant" and action.message.tool_calls[0]["name"] == "create_reservation"
    assert not Reservation.objects.exists()


def test_the_next_turn_sends_the_conversation_history(hotel, session, owner):
    llm = ScriptedLLM([real_text("Hoy no hay llegadas."), real_text("Mañana tampoco.")])
    run_turn(session, "¿Llegadas hoy?", user=owner, llm=llm)

    run_turn(session, "¿Y mañana?", user=owner, llm=llm)

    sent = [(message["role"], message["content"]) for message in llm.calls[1]["messages"]]
    assert sent == [
        ("user", "¿Llegadas hoy?"),
        ("assistant", "Hoy no hay llegadas."),
        ("user", "¿Y mañana?"),
    ]


def test_the_session_gets_a_title_and_its_last_activity(hotel, session, owner):
    run_turn(session, "¿Cuál es la ocupación de la semana?", user=owner, llm=ScriptedLLM([real_text("70 %")]))

    session.refresh_from_db()
    assert session.title == "¿Cuál es la ocupación de la semana?"
    assert session.last_message_at is not None


def test_an_empty_model_answer_is_replaced_by_a_readable_message(hotel, session, owner):
    turn = run_turn(session, "hola", user=owner, llm=ScriptedLLM([real_text("")]))

    assert turn["messages"][-1].content


def test_the_offline_assistant_answers_a_real_question_end_to_end(hotel, session, owner, llm_mode):
    """No credentials: the simulated client picks the tool, the tool reads the hotel, the answer uses it."""
    llm_mode("simulated")
    arriving = book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["101"].pk})

    turn = run_turn(session, "¿Cuántas llegadas hay hoy?", user=owner)

    answer = turn["messages"][-1]
    assert answer.simulated
    assert arriving.code in answer.content and "101" in answer.content
