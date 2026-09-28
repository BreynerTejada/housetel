"""The offline assistant (spec §1.2): intent rules that call the same tools a real model would, answers
composed from the tool results, the chatbot's FAQ answers and hand-off, and structured outputs."""

import json

import pytest

from apps.ai import nlp
from apps.ai.simulated import SimulatedLLMClient, register_structured

COPILOT_TOOLS = [
    {"name": name, "description": "", "parameters": {"type": "object", "properties": {}}}
    for name in (
        "get_today_summary",
        "list_arrivals",
        "list_departures",
        "search_reservations",
        "get_reservation",
        "check_availability",
        "get_occupancy",
        "find_guest",
        "get_balance",
        "list_alerts",
        "get_rates",
        "create_reservation",
        "move_room",
        "check_in",
        "check_out",
        "send_message",
        "block_room",
        "add_extra",
    )
]
CHATBOT_TOOLS = [
    {"name": "check_availability", "description": "", "parameters": {"type": "object", "properties": {}}},
    {"name": "request_human", "description": "", "parameters": {"type": "object", "properties": {}}},
]
COPILOT_SYSTEM = "Eres el copiloto de Hotel Casa Aurora.\nFecha de hoy: 2026-10-01\nIdioma: es"
CHATBOT_SYSTEM = """Eres el asistente virtual de Hotel Casa Aurora.
Fecha de hoy: 2026-10-01
Idioma: es

## Conocimiento
- ¿Tienen parqueadero? → Sí, parqueadero cubierto por 25.000 la noche.
- ¿Aceptan mascotas? → No aceptamos mascotas.
- Horarios: check-in desde las 15:00 y check-out hasta las 12:00.

## Reglas
- Responde en pocas frases."""


def ask(text, *, tools=COPILOT_TOOLS, system=COPILOT_SYSTEM):
    return SimulatedLLMClient().generate([{"role": "user", "content": text}], system=system, tools=tools)


def call_of(result):
    assert result.simulated and result.provider == "simulated"
    assert len(result.tool_calls) == 1, result
    (call,) = result.tool_calls
    assert call.id
    return call.name, call.arguments


# ---- copilot: intents → tool calls ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("¿Cuántas llegadas hay hoy?", ("list_arrivals", {"date": "2026-10-01"})),
        ("arrivals tomorrow", ("list_arrivals", {"date": "2026-10-02"})),
        ("¿Quién sale hoy?", ("list_departures", {"date": "2026-10-01"})),
        ("check-outs de mañana", ("list_departures", {"date": "2026-10-02"})),
        ("Dame el resumen del día", ("get_today_summary", {})),
        (
            "¿Cómo va la ocupación esta semana?",
            ("get_occupancy", {"start": "2026-10-01", "end": "2026-10-08"}),
        ),
        (
            "¿Hay disponibilidad del 12 al 14 de octubre para 3 adultos?",
            (
                "check_availability",
                {"checkin": "2026-10-12", "checkout": "2026-10-14", "adults": 3, "children": 0},
            ),
        ),
        ("¿Cuál es el saldo de ht-7k2m9q?", ("get_balance", {"code": "HT-7K2M9Q"})),
        ("Muéstrame la reserva HT-7K2M9Q", ("get_reservation", {"code": "HT-7K2M9Q"})),
        ("busca al huésped Mariana Ríos", ("find_guest", {"query": "Mariana Ríos"})),
        ("busca las reservas de Gómez", ("search_reservations", {"query": "Gómez"})),
        ("¿Qué alertas hay abiertas?", ("list_alerts", {})),
        ("tarifas de la próxima semana", ("get_rates", {"start": "2026-10-05", "end": "2026-10-12"})),
        (
            "precios de DBL esta semana",
            ("get_rates", {"start": "2026-10-01", "end": "2026-10-08", "room_type": "DBL"}),
        ),
    ],
)
def test_read_questions_call_the_matching_tool(text, expected):
    assert call_of(ask(text)) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Mueve HT-7K2M9Q a la habitación 205",
            ("move_room", {"reservation_code": "HT-7K2M9Q", "room_number": "205"}),
        ),
        (
            "move HT-7K2M9Q to room 301",
            ("move_room", {"reservation_code": "HT-7K2M9Q", "room_number": "301"}),
        ),
        ("Haz el check-in de HT-7K2M9Q", ("check_in", {"reservation_code": "HT-7K2M9Q"})),
        ("check out HT-7K2M9Q", ("check_out", {"reservation_code": "HT-7K2M9Q"})),
        (
            "Bloquea la 301 mañana por mantenimiento",
            (
                "block_room",
                {
                    "room_number": "301",
                    "start": "2026-10-02",
                    "end": "2026-10-03",
                    "kind": "maintenance",
                    "reason": "mantenimiento",
                },
            ),
        ),
        (
            "Agrega 2 desayunos a HT-7K2M9Q",
            ("add_extra", {"reservation_code": "HT-7K2M9Q", "extra": "desayuno", "quantity": 2}),
        ),
        (
            "Envía un WhatsApp a HT-7K2M9Q: Su habitación ya está lista",
            (
                "send_message",
                {
                    "reservation_code": "HT-7K2M9Q",
                    "channel": "whatsapp",
                    "message": "Su habitación ya está lista",
                },
            ),
        ),
        (
            "Crea una reserva para Ana Pérez del 12 al 14 de octubre para 2 adultos en DBL",
            (
                "create_reservation",
                {
                    "guest_name": "Ana Pérez",
                    "checkin": "2026-10-12",
                    "checkout": "2026-10-14",
                    "adults": 2,
                    "children": 0,
                    "room_type": "DBL",
                },
            ),
        ),
    ],
)
def test_action_requests_call_the_action_tool(text, expected):
    assert call_of(ask(text)) == expected


def test_a_tool_that_was_not_offered_is_never_called():
    tools = [tool for tool in COPILOT_TOOLS if tool["name"] != "block_room"]

    result = ask("Bloquea la 301 mañana", tools=tools)

    assert result.tool_calls == []
    assert "permiso" in result.text.lower() or "no puedo" in result.text.lower()


def test_a_greeting_is_answered_with_text():
    result = ask("Hola")

    assert result.tool_calls == []
    assert "llegadas" in result.text.lower()


def test_an_unknown_request_explains_what_it_can_do_in_english():
    system = COPILOT_SYSTEM.replace("Idioma: es", "Idioma: en")

    result = ask("Sing me a song", system=system)

    assert result.tool_calls == []
    assert "arrivals" in result.text.lower()


# ---- copilot: answers composed from tool results ------------------------------------------------------


def after_tool(name, output, *, system=COPILOT_SYSTEM, question="¿Cuántas llegadas hay hoy?"):
    messages = [
        {"role": "user", "content": question},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "sim-1", "name": name, "arguments": {}}]},
        {"role": "tool", "tool_call_id": "sim-1", "name": name, "content": json.dumps(output)},
    ]
    return SimulatedLLMClient().generate(messages, system=system, tools=COPILOT_TOOLS)


def test_the_answer_lists_the_arrivals_the_tool_returned():
    output = {
        "date": "2026-10-01",
        "count": 2,
        "items": [
            {
                "code": "HT-AAAAAA",
                "guest": "Laura Gómez",
                "vip": False,
                "status": "confirmed",
                "checkin": "2026-10-01",
                "checkout": "2026-10-03",
                "rooms": ["101"],
                "room_status": "clean",
                "eta": "15:30",
                "balance": "761600.00",
            },
            {
                "code": "HT-BBBBBB",
                "guest": "John Smith",
                "vip": True,
                "status": "confirmed",
                "checkin": "2026-10-01",
                "checkout": "2026-10-02",
                "rooms": [],
                "room_status": None,
                "eta": None,
                "balance": "0.00",
            },
        ],
    }

    result = after_tool("list_arrivals", output)

    assert result.tool_calls == []
    assert "2 llegadas" in result.text
    assert "HT-AAAAAA" in result.text and "Laura Gómez" in result.text and "101" in result.text
    assert "$ 761.600" in result.text
    assert "HT-BBBBBB" in result.text and "sin habitación" in result.text


def test_no_arrivals_is_said_plainly():
    result = after_tool("list_arrivals", {"date": "2026-10-01", "count": 0, "items": []})

    assert "no hay llegadas" in result.text.lower()


def test_a_proposal_is_announced_and_left_for_confirmation():
    output = {
        "proposal": {
            "id": "x",
            "action": "move_room",
            "summary": "Mover HT-AAAAAA de la 101 a la 205",
            "details": {},
            "status": "proposed",
        }
    }

    result = after_tool("move_room", output, question="Mueve HT-AAAAAA a la 205")

    assert "Mover HT-AAAAAA de la 101 a la 205" in result.text
    assert "confirm" in nlp.norm(result.text)  # "confírmala"


def test_a_tool_error_is_explained():
    result = after_tool("get_balance", {"error": "No encontré la reserva HT-ZZZZZZ"})

    assert "No encontré la reserva HT-ZZZZZZ" in result.text


def test_availability_options_are_listed_in_english_when_asked_in_english():
    system = COPILOT_SYSTEM.replace("Idioma: es", "Idioma: en")
    output = {
        "checkin": "2026-10-12",
        "checkout": "2026-10-14",
        "nights": 2,
        "adults": 2,
        "children": 0,
        "currency": "COP",
        "options": [
            {
                "room_type": "Standard",
                "room_type_code": "DBL",
                "available": 3,
                "total": "761600.00",
                "per_night": "380800.00",
                "rate_plan": "Flexible rate",
            }
        ],
    }

    result = after_tool("check_availability", output, system=system, question="rooms for Oct 12-14?")

    assert "Standard" in result.text and "$ 761.600" in result.text
    assert "available" in result.text.lower()


# ---- chatbot ------------------------------------------------------------------------------------------


def test_the_chatbot_checks_availability_when_dates_are_given():
    name, arguments = call_of(
        ask(
            "¿Tienen habitación del 12 al 14 de octubre para 2 personas?",
            tools=CHATBOT_TOOLS,
            system=CHATBOT_SYSTEM,
        )
    )

    assert (name, arguments) == (
        "check_availability",
        {"checkin": "2026-10-12", "checkout": "2026-10-14", "adults": 2, "children": 0},
    )


def test_the_chatbot_asks_for_dates_when_they_are_missing():
    result = ask("¿Tienen disponibilidad?", tools=CHATBOT_TOOLS, system=CHATBOT_SYSTEM)

    assert result.tool_calls == []
    assert "fechas" in result.text.lower()


def test_the_chatbot_answers_from_the_hotel_knowledge():
    result = ask("hay estacionamiento para el carro?", tools=CHATBOT_TOOLS, system=CHATBOT_SYSTEM)

    assert result.tool_calls == []
    assert result.text == "Sí, parqueadero cubierto por 25.000 la noche."


@pytest.mark.parametrize("text", ["Quiero hablar con una persona", "Can I talk to a human?"])
def test_the_chatbot_hands_off_when_a_person_is_requested(text):
    name, arguments = call_of(ask(text, tools=CHATBOT_TOOLS, system=CHATBOT_SYSTEM))

    assert (name, arguments["reason"]) == ("request_human", "requested")


def test_the_chatbot_hands_off_when_it_does_not_know():
    name, arguments = call_of(
        ask("¿Cuál es la capital de Francia?", tools=CHATBOT_TOOLS, system=CHATBOT_SYSTEM)
    )

    assert (name, arguments["reason"]) == ("request_human", "low_confidence")


def test_the_chatbot_turns_offers_into_a_short_answer():
    messages = [
        {"role": "user", "content": "habitación del 12 al 14 de octubre"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "name": "check_availability", "arguments": {}}],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "check_availability",
            "content": json.dumps(
                {
                    "checkin": "2026-10-12",
                    "checkout": "2026-10-14",
                    "nights": 2,
                    "currency": "COP",
                    "options": [
                        {
                            "room_type": "Estándar",
                            "total": "761600.00",
                            "per_night": "380800.00",
                            "available": 2,
                        }
                    ],
                }
            ),
        },
    ]

    result = SimulatedLLMClient().generate(messages, system=CHATBOT_SYSTEM, tools=CHATBOT_TOOLS)

    assert "Estándar" in result.text and "$ 761.600" in result.text


# ---- structured output --------------------------------------------------------------------------------


def test_structured_output_comes_from_the_registered_generator():
    @register_structured("test_schema_echo")
    def echo(prompt, system):
        return {"echo": prompt}

    result = SimulatedLLMClient().generate(
        [{"role": "user", "content": "doce habitaciones"}],
        response_schema={"title": "test_schema_echo", "type": "object"},
    )

    assert result.data == {"echo": "doce habitaciones"}
    assert json.loads(result.text) == {"echo": "doce habitaciones"}


def test_an_unknown_schema_gives_no_data():
    result = SimulatedLLMClient().generate(
        [{"role": "user", "content": "x"}], response_schema={"title": "nobody", "type": "object"}
    )

    assert result.data is None
