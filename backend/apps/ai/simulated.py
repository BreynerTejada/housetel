"""Deterministic offline LLM client (spec §1.2: the app works end to end without credentials).

Same contract as the real providers, driven by rules instead of a model:

- **Copilot** (tools offered): recognizes the intent of the staff request (arrivals, departures, summary,
  occupancy, availability, balance, reservations, guests, alerts, rates and the actions) and answers with the
  same tool call a real model would make; once the tool results come back it writes the answer from them.
- **Chatbot** (the `request_human` tool is offered): checks availability when the guest gives dates, answers
  from the hotel knowledge in the system prompt (lines under `## Conocimiento`) and hands off to a person when
  asked or when it does not know.
- **Structured output** (`response_schema`): generators registered by title (`register_structured`), e.g. the
  onboarding proposal built with heuristics.

Conventions read from the system prompt (the real providers get the same prompt): `Fecha de hoy: AAAA-MM-DD`
(what "hoy"/"mañana" mean) and `Idioma: es|en` (answer language).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from importlib import import_module

from apps.ai import nlp
from apps.ai.clients.base import parse_tool_content
from apps.ai.types import LLMResult, ToolCall

StructuredGenerator = Callable[[str, "str | None"], "dict | None"]
STRUCTURED: dict[str, StructuredGenerator] = {}
# Modules that register structured generators; imported on first use (they import this module).
STRUCTURED_MODULES = ("apps.ai.onboarding", "apps.ai.anomalies", "apps.ai.drafts")

TODAY_LINE = re.compile(r"(?:fecha de hoy|today(?:'s date)?(?:\s+is)?)\s*[:=]?\s*(\d{4}-\d{2}-\d{2})", re.I)
LANGUAGE_LINE = re.compile(r"(?:idioma|language)\s*[:=]\s*(es|en)\b", re.I)
KNOWLEDGE_HEADINGS = ("## conocimiento", "## knowledge")


def register_structured(title: str):
    """Decorator: `fn(prompt, system) -> dict | None` answers `response_schema={"title": title, ...}`."""

    def register(fn: StructuredGenerator) -> StructuredGenerator:
        STRUCTURED[title] = fn
        return fn

    return register


def _load_structured_modules() -> None:
    for module in STRUCTURED_MODULES:
        try:
            import_module(module)
        except ModuleNotFoundError as exc:
            if exc.name != module:
                raise


@dataclass
class Turn:
    """What the rules need from a conversation."""

    question: str
    lang: str
    today: date
    knowledge: list[str] = field(default_factory=list)
    results: list[tuple[str, object]] = field(default_factory=list)  # trailing tool results (name, output)

    def text(self, es: str, en: str) -> str:
        return en if self.lang == "en" else es


def _read_turn(messages: list[dict], system: str | None, default_today: date | None, *, guest: bool) -> Turn:
    system = system or ""
    question = next((m.get("content") or "" for m in reversed(messages) if m.get("role") == "user"), "")
    found_today = TODAY_LINE.search(system)
    if found_today:
        today = date.fromisoformat(found_today[1])
    else:
        from django.utils import timezone

        today = default_today or timezone.localdate()
    found_lang = LANGUAGE_LINE.search(system)
    system_lang = found_lang[1].lower() if found_lang else "es"
    # Guests may write in another language than the page; staff get the language of their UI.
    lang = nlp.language(question, default=system_lang) if guest or not found_lang else system_lang
    results = []
    for message in reversed(messages):
        if message.get("role") != "tool":
            break
        results.append((message.get("name") or "", parse_tool_content(message.get("content"))))
    results.reverse()
    return Turn(question=question, lang=lang, today=today, knowledge=_knowledge(system), results=results)


def _knowledge(system: str) -> list[str]:
    lines, inside = [], False
    for raw in system.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            inside = line.lower().startswith(KNOWLEDGE_HEADINGS)
            continue
        if inside and line.startswith("- "):
            lines.append(line[2:].strip())
    return lines


class SimulatedLLMClient:
    """Same contract as the real providers."""

    provider = "simulated"
    model = "simulated"

    def __init__(self, today=None):
        self.today = today
        self._calls = 0

    def generate(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> LLMResult:
        names = {tool["name"] for tool in tools or []}
        guest = "request_human" in names
        turn = _read_turn(messages, system, self.today, guest=guest)
        if response_schema:
            return self._structured(response_schema, turn.question, system)
        if turn.results:
            compose = compose_guest_answer if guest else compose_answer
            return self._text(compose(turn))
        if guest:
            return self._decide(chatbot_intent(turn, names))
        if names:
            return self._decide(copilot_intent(turn, names))
        text = turn.text(
            f"(modo simulado) Recibí tu mensaje: «{turn.question[:200]}»."
            if turn.question
            else "(modo simulado) ¿En qué puedo ayudarte?",
            f"(simulated mode) I got your message: “{turn.question[:200]}”."
            if turn.question
            else "(simulated mode) How can I help you?",
        )
        return self._text(text)

    # ---- results -------------------------------------------------------------------------------------

    def _text(self, text: str) -> LLMResult:
        return LLMResult(text=text, provider=self.provider, model=self.model, simulated=True)

    def _decide(self, decision) -> LLMResult:
        if isinstance(decision, str):
            return self._text(decision)
        name, arguments = decision
        self._calls += 1
        call = ToolCall(name=name, arguments=arguments, id=f"sim-{self._calls}")
        return LLMResult(tool_calls=[call], provider=self.provider, model=self.model, simulated=True)

    def _structured(self, schema: dict, prompt: str, system: str | None) -> LLMResult:
        _load_structured_modules()
        generator = STRUCTURED.get(str(schema.get("title") or ""))
        data = generator(prompt, system) if generator else None
        return LLMResult(
            text=json.dumps(data, ensure_ascii=False) if data is not None else "",
            data=data,
            provider=self.provider,
            model=self.model,
            simulated=True,
        )


# ---- copilot intents ---------------------------------------------------------------------------------

GREETING = re.compile(
    r"^(?:hola|buen(?:os|as)\s+(?:dias|tardes|noches)|hello|hi|hey|good\s+(?:morning|afternoon|evening))\b"
)
THANKS = re.compile(r"\b(?:gracias|thanks|thank\s+you|muy\s+amable)\b")

SEND_VERB = re.compile(
    r"\b(?:envia|enviar|enviale|manda|mandale|mandar|escribe|escribele|send|text|message)\b"
)
CREATE_VERB = re.compile(
    r"\b(?:crea|crear|creame|haz|hazme|registra|nueva|new|create|make|book)\b.*\b(?:reserva|reservation|booking)\b|\breserva\s+para\b|\bbook\s+(?:a\s+room\s+)?for\b"
)
MOVE_VERB = re.compile(
    r"\b(?:mueve|mover|muevela|muevelo|cambia|cambiala|cambialo|cambiar|pasa|pasala|pasalo|traslada|trasladar|reasigna|asigna|asignale|move|switch|transfer|assign|reassign|upgrade)\b"
)
BLOCK_VERB = re.compile(r"\b(?:bloquea|bloquear|bloqueala|inhabilita|block)\b")
EXTRA_VERB = re.compile(
    r"\b(?:agrega|agregar|agregale|anade|anadir|suma|sumale|carga|cargale|cobra|add|charge)\b"
)
CHECKIN = re.compile(r"\bcheckin\b")
CHECKOUT = re.compile(r"\bcheckout\b")

BALANCE = re.compile(r"\b(?:saldo|saldos|debe|deben|deuda|balance|owes?|outstanding)\b")
ARRIVALS = re.compile(r"\b(?:llegadas?|llegan|llega|arrivals?|arriving|check-?ins?|checkins)\b")
DEPARTURES = re.compile(r"\b(?:salidas?|salen|sale|departures?|departing|leaving|check-?outs?|checkouts)\b")
AVAILABILITY = re.compile(
    r"\b(?:disponibilidad|disponible|disponibles|libres?|availability|available|vacancy|vacancies|cupo|cupos)\b"
)
OCCUPANCY = re.compile(r"\b(?:ocupacion|occupancy|ocupad[oa]s?|lleno|llenos|full)\b")
RATES = re.compile(r"\b(?:tarifas?|precios?|rates?|prices?|pricing)\b")
ALERTS = re.compile(r"\b(?:alertas?|alerts?|problemas?|issues?|incidencias?)\b")
SUMMARY = re.compile(
    r"\b(?:resumen|summary|overview|panorama|como\s+va(?:mos)?(?:\s+el\s+dia)?|how\s+is\s+(?:the\s+)?day)\b"
)
GUEST = re.compile(r"\b(?:hu[eé]sped(?:es)?|guests?|cliente)\s+(?:llamad[oa]\s+|named\s+)?(.+)$", re.I)
RESERVATIONS_OF = re.compile(
    r"\b(?:reservas?|reservations?|bookings?)\s+(?:de|del|a\s+nombre\s+de|for|of|by|under)\s+(.+)$", re.I
)
NEXT_WEEK = re.compile(r"\b(?:proxima\s+semana|semana\s+que\s+viene|next\s+week)\b")
MONTH = re.compile(r"\b(?:mes|month)\b")
ROOM_TYPE_CODE = re.compile(
    r"\b(?:en|in|categoria|categoría|category|tipo|type|de|of|for)\s+(?:la\s+|el\s+|the\s+)?([A-Z][A-Z0-9]{1,5})\b"
)
GUEST_NAME = re.compile(
    r"\b(?:a\s+nombre\s+de|para|for)\s+([A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñü'-]+(?:\s+[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñü'-]+){0,3})"
)
MESSAGE_BODY = re.compile(
    r"(?::|\b(?:diciendo|que\s+diga|que\s+dice|saying|that\s+says)\b)\s*(.+)$", re.I | re.S
)
REASON = re.compile(r"\b(?:por|for|porque|because)\s+(.+)$", re.I)
QUANTITY = re.compile(rf"\b({nlp._NUM})\b")

BLOCK_KINDS = [
    (re.compile(r"\b(?:mantenimiento|maintenance|reparacion|repair|pintura|painting)\b"), "maintenance"),
    (
        re.compile(r"\b(?:dano|danada|danado|averia|averiada|broken|damaged|out\s+of\s+order)\b"),
        "out_of_order",
    ),
    (re.compile(r"\b(?:propietario|dueno|owner)\b"), "owner_hold"),
]
TEMPLATES = [
    (re.compile(r"\b(?:confirmacion|confirmation)\b"), "confirmation"),
    (re.compile(r"\b(?:recordatorio\s+de\s+pago|payment\s+reminder|cobro)\b"), "payment_reminder"),
    (
        re.compile(r"\b(?:check-?in\s+online|checkin\s+online|link\s+de\s+checkin|checkin\s+link)\b"),
        "checkin_invitation",
    ),
    (re.compile(r"\b(?:pre-?llegada|pre-?arrival)\b"), "pre_arrival"),
]
ACTION_LABELS = {
    "create_reservation": ("crear reservas", "create reservations"),
    "move_room": ("mover reservas de habitación", "move reservations to another room"),
    "check_in": ("hacer check-in", "check guests in"),
    "check_out": ("hacer check-out", "check guests out"),
    "send_message": ("enviar mensajes", "send messages"),
    "block_room": ("bloquear habitaciones", "block rooms"),
    "add_extra": ("agregar extras al folio", "add extras to the folio"),
    "get_balance": ("consultar saldos", "look up balances"),
    "list_alerts": ("ver las alertas", "see the alerts"),
    "get_rates": ("consultar tarifas", "look up rates"),
    "find_guest": ("buscar huéspedes", "look up guests"),
}


def _clean_tail(value: str) -> str:
    return value.strip().strip("¿?¡!.,;:\"'«»“” ").strip()


def _first_date(turn: Turn) -> date | None:
    found = nlp.stay_dates(turn.question, turn.today)
    return found[0] if found else None


def _period(turn: Turn, q: str) -> tuple[date, date]:
    found = nlp.stay_dates(turn.question, turn.today)
    if found:
        return found
    if NEXT_WEEK.search(q):
        monday = turn.today + timedelta(days=7 - turn.today.weekday())
        return monday, monday + timedelta(days=7)
    if MONTH.search(q):
        return turn.today, turn.today + timedelta(days=30)
    return turn.today, turn.today + timedelta(days=7)


def _room_type_code(question: str) -> str | None:
    for match in ROOM_TYPE_CODE.finditer(question):
        code = match[1]
        if not code.startswith("HT") and code not in {"VIP", "IVA"}:
            return code
    return None


def _party(turn: Turn) -> tuple[int, int]:
    adults, children = nlp.party(turn.question)
    return adults or 2, children


def _without_codes(text: str) -> str:
    return nlp.RESERVATION_CODE.sub(" ", text)


def _extra_request(turn: Turn, q: str) -> tuple[str, int | None]:
    """("desayuno", 2) from "Agrega 2 desayunos a HT-…"."""
    body = nlp.norm(_without_codes(turn.question))
    body = EXTRA_VERB.sub(" ", body, count=1)
    body = re.split(r"\s(?:a|al|to|para|for|en|in)\s", f" {body} ")[0]
    quantity = None
    quantity_match = QUANTITY.search(body)
    if quantity_match:
        # "un/una/one" is an article ("agrega un parqueadero"): the extra's own rule sets the quantity.
        if quantity_match[1] not in ("un", "una", "uno", "one"):
            quantity = nlp.to_int(quantity_match[1])
        body = body[: quantity_match.start()] + body[quantity_match.end() :]
    words = [
        word
        for word in re.findall(r"[a-z-]+", body)
        if word not in {"un", "una", "el", "la", "los", "las", "de", "del", "a", "an", "the", "some"}
    ]
    name = " ".join(words)
    if name.endswith("es") and len(name) > 6 and name[:-2].endswith(("r", "l", "n")):
        name = name[:-2]
    elif name.endswith("s") and len(name) > 4:
        name = name[:-1]
    return name, quantity


def copilot_intent(turn: Turn, offered: set[str]):
    """(tool name, arguments) for the staff request, or the text to answer."""
    q = nlp.norm(turn.question)
    codes = nlp.reservation_codes(turn.question)
    code = codes[0] if codes else None
    room = nlp.room_number(_without_codes(turn.question))

    def use(name: str, arguments: dict):
        if name in offered:
            return name, arguments
        es, en = ACTION_LABELS.get(name, ("hacer eso", "do that"))
        return turn.text(
            f"No puedo {es} con tu usuario: tu rol no tiene ese permiso.",
            f"I can't {en} with your user: your role doesn't have that permission.",
        )

    # Actions first: their wording would also match the read intents (e.g. a message that says "check-in").
    if code and SEND_VERB.search(q):
        channel = "whatsapp" if re.search(r"\b(?:whatsapp|wasap|wpp|whats)\b", q) else "email"
        body = MESSAGE_BODY.search(_without_codes(turn.question))
        arguments = {"reservation_code": code, "channel": channel}
        if body and _clean_tail(body[1]):
            arguments["message"] = body[1].strip()
            return use("send_message", arguments)
        template = next((value for pattern, value in TEMPLATES if pattern.search(q)), None)
        if template:
            return use("send_message", {**arguments, "template_code": template})
        return turn.text(
            f"¿Qué mensaje le envío a {code}? Escríbelo después de dos puntos, p. ej. «Envía un WhatsApp a "
            f"{code}: tu habitación está lista».",
            f"What should I send to {code}? Write it after a colon, e.g. “Send a WhatsApp to {code}: your "
            "room is ready”.",
        )
    if CREATE_VERB.search(q):
        dates = nlp.stay_dates(turn.question, turn.today)
        if not dates:
            return turn.text(
                "¿Para qué fechas es la reserva? Dime la llegada y la salida (p. ej. del 12 al 14 de "
                "octubre).",
                "For which dates? Tell me the arrival and departure (e.g. October 12 to 14).",
            )
        adults, children = _party(turn)
        arguments = {
            "checkin": dates[0].isoformat(),
            "checkout": dates[1].isoformat(),
            "adults": adults,
            "children": children,
        }
        name = GUEST_NAME.search(turn.question)
        if name:
            arguments["guest_name"] = name[1].strip()
        if room_type := _room_type_code(turn.question):
            arguments["room_type"] = room_type
        return use("create_reservation", arguments)
    if code and room and MOVE_VERB.search(q):
        return use("move_room", {"reservation_code": code, "room_number": room})
    if room and BLOCK_VERB.search(q):
        start, end = nlp.stay_dates(turn.question, turn.today) or (turn.today, turn.today + timedelta(days=1))
        kind = next((value for pattern, value in BLOCK_KINDS if pattern.search(q)), "out_of_service")
        arguments = {"room_number": room, "start": start.isoformat(), "end": end.isoformat(), "kind": kind}
        reason = REASON.search(turn.question)
        if reason and _clean_tail(reason[1]):
            arguments["reason"] = _clean_tail(reason[1])
        return use("block_room", arguments)
    if code and EXTRA_VERB.search(q):
        extra, quantity = _extra_request(turn, q)
        if extra:
            arguments = {"reservation_code": code, "extra": extra}
            if quantity:
                arguments["quantity"] = quantity
            return use("add_extra", arguments)
    if code and CHECKIN.search(q):
        return use("check_in", {"reservation_code": code})
    if code and CHECKOUT.search(q):
        return use("check_out", {"reservation_code": code})

    # Reads.
    if code and BALANCE.search(q):
        return use("get_balance", {"code": code})
    if ARRIVALS.search(q):
        return use("list_arrivals", {"date": (_first_date(turn) or turn.today).isoformat()})
    if DEPARTURES.search(q):
        return use("list_departures", {"date": (_first_date(turn) or turn.today).isoformat()})
    if AVAILABILITY.search(q) or re.search(r"\bhay\s+(?:habitacion|habitaciones|cuartos?)\b", q):
        dates = nlp.stay_dates(turn.question, turn.today)
        if not dates:
            return turn.text(
                "¿Para qué fechas reviso la disponibilidad? Dime la llegada y la salida.",
                "For which dates should I check availability? Tell me the arrival and departure.",
            )
        adults, children = _party(turn)
        return use(
            "check_availability",
            {
                "checkin": dates[0].isoformat(),
                "checkout": dates[1].isoformat(),
                "adults": adults,
                "children": children,
            },
        )
    if OCCUPANCY.search(q):
        start, end = _period(turn, q)
        return use("get_occupancy", {"start": start.isoformat(), "end": end.isoformat()})
    if RATES.search(q):
        start, end = _period(turn, q)
        arguments = {"start": start.isoformat(), "end": end.isoformat()}
        if room_type := _room_type_code(turn.question):
            arguments["room_type"] = room_type
        return use("get_rates", arguments)
    if ALERTS.search(q):
        return use("list_alerts", {})
    guest = GUEST.search(turn.question)
    if guest and _clean_tail(guest[1]) and not code:
        return use("find_guest", {"query": _clean_tail(guest[1])})
    reservations_of = RESERVATIONS_OF.search(turn.question)
    if reservations_of and _clean_tail(reservations_of[1]):
        return use("search_reservations", {"query": _clean_tail(reservations_of[1])})
    if code:
        return use("get_reservation", {"code": code})
    if SUMMARY.search(q) or re.search(r"\b(?:hoy|today)\b", q):
        return use("get_today_summary", {})
    if GREETING.search(q):
        return turn.text(
            "¡Hola! Soy tu copiloto. Puedo contarte las llegadas y salidas, la ocupación, la disponibilidad "
            "y los saldos, y preparar acciones (crear o mover reservas, check-in/out, mensajes, bloqueos, "
            "extras) que tú confirmas.",
            "Hi! I'm your copilot. I can tell you about arrivals and departures, occupancy, availability and "
            "balances, and prepare actions (create or move reservations, check-in/out, messages, room "
            "blocks, extras) that you confirm.",
        )
    if THANKS.search(q):
        return turn.text("¡Con gusto! ¿Algo más?", "You're welcome! Anything else?")
    return turn.text(
        "En modo simulado entiendo pedidos concretos como: «¿cuántas llegadas hay hoy?», «salidas de "
        "mañana», «ocupación de la semana», «disponibilidad del 12 al 14 de octubre», «saldo de HT-XXXXXX», "
        "«mueve HT-XXXXXX a la 205» o «bloquea la 301 mañana por mantenimiento».",
        "In simulated mode I understand concrete requests such as: “how many arrivals today?”, “departures "
        "tomorrow”, “occupancy this week”, “availability October 12 to 14”, “balance of HT-XXXXXX”, “move "
        "HT-XXXXXX to room 205” or “block room 301 tomorrow for maintenance”.",
    )


# ---- chatbot intents ---------------------------------------------------------------------------------

HUMAN = re.compile(
    r"\b(?:humano|humana|persona|agente|asesor|asesora|recepcion|recepcionista|alguien|operador|human|person|agent|someone|representative|staff|operator)\b"
)
BOOKING_WORDS = re.compile(
    r"\b(?:disponibilidad|disponible|disponibles|reservar|reserva|cupo|libre|libres|availability|available|vacancy|book|booking)\b"
)
# Questions about the guest's own booking (guest portal): answered with the reservation line of the knowledge.
MY_BOOKING = re.compile(
    r"\b(?:mi|mis|my|our|nuestra)\s+(?:reservas?|reservacion|llegada|salida|checkin|checkout|estadia|habitacion|booking|reservation|arrival|departure|stay|room)\b"
    r"|\bcuando\s+(?:llego|llegamos|salgo|salimos|es\s+mi)\b|\bwhen\s+(?:do\s+|can\s+)?(?:i|we)\s+(?:arrive|leave|check)"
)
CANCEL_WORDS = re.compile(r"\b(?:cancelar|cancelacion|cancel|cancellation|reembolso|refund)\b")
RESERVATION_LINE = ("Reserva del huésped", "The guest's reservation")


def chatbot_intent(turn: Turn, offered: set[str]):
    q = nlp.norm(turn.question)
    if HUMAN.search(q) and re.search(
        r"\b(?:hablar|comunicar|contactar|pasar|quiero|necesito|talk|speak|contact|connect|want|need|can)\b",
        q,
    ):
        return "request_human", {"reason": "requested", "summary": turn.question[:300]}
    dates = nlp.stay_dates(turn.question, turn.today)
    if dates and "check_availability" in offered:
        adults, children = _party(turn)
        return "check_availability", {
            "checkin": dates[0].isoformat(),
            "checkout": dates[1].isoformat(),
            "adults": adults,
            "children": children,
        }
    own = next((line for line in turn.knowledge if line.startswith(RESERVATION_LINE)), None)
    if own and MY_BOOKING.search(q) and not CANCEL_WORDS.search(q):
        details = own.split(":", 1)[1].strip().rstrip(".")
        return turn.text(f"Tu reserva: {details}.", f"Your reservation: {details}.")
    if BOOKING_WORDS.search(q):
        return turn.text(
            "¡Claro! ¿Para qué fechas y cuántas personas? Por ejemplo: «del 12 al 14 de octubre para 2 "
            "adultos».",
            "Sure! For which dates and how many guests? For example: “October 12 to 14 for 2 adults”.",
        )
    answer = nlp.best_answer(turn.question, turn.knowledge)
    if answer:
        return answer
    if GREETING.search(q):
        return turn.text(
            "¡Hola! Soy el asistente virtual del hotel. Puedo ayudarte con disponibilidad, precios y "
            "preguntas sobre tu estadía. ¿En qué te ayudo?",
            "Hi! I'm the hotel's virtual assistant. I can help you with availability, prices and questions "
            "about your stay. How can I help?",
        )
    if THANKS.search(q):
        return turn.text(
            "¡Con gusto! Si necesitas algo más, aquí estoy.",
            "You're welcome! I'm here if you need anything else.",
        )
    return "request_human", {"reason": "low_confidence", "summary": turn.question[:300]}


# ---- answers composed from tool results ---------------------------------------------------------------


def _money(value, currency: str = "COP") -> str:
    return nlp.format_money(value, currency)


def _day(turn: Turn, value) -> str:
    return nlp.format_date(value, turn.lang)


def _plural(turn: Turn, count: int, es: tuple[str, str], en: tuple[str, str]) -> str:
    words = en if turn.lang == "en" else es
    return f"{count} {words[0] if count == 1 else words[1]}"


def _reservation_line(turn: Turn, item: dict, currency: str = "COP") -> str:
    rooms = ", ".join(item.get("rooms") or [])
    status = item.get("room_status")
    place = (
        turn.text(f"hab. {rooms}", f"room {rooms}") + (f" ({_room_status(turn, status)})" if status else "")
        if rooms
        else turn.text("sin habitación", "no room yet")
    )
    parts = [item.get("code", ""), item.get("guest", "") + (" · VIP" if item.get("vip") else ""), place]
    if item.get("eta"):
        parts.append(f"ETA {item['eta']}")
    balance = item.get("balance")
    if balance not in (None, "", "0.00", "0"):
        parts.append(turn.text(f"saldo {_money(balance, currency)}", f"balance {_money(balance, currency)}"))
    return "- " + " · ".join(part for part in parts if part)


ROOM_STATUS = {
    "clean": ("limpia", "clean"),
    "dirty": ("sucia", "dirty"),
    "inspected": ("inspeccionada", "inspected"),
    "out_of_service": ("fuera de servicio", "out of service"),
}


def _room_status(turn: Turn, status: str) -> str:
    es, en = ROOM_STATUS.get(status, (status, status))
    return turn.text(es, en)


def _list(turn: Turn, output: dict, *, arrivals: bool) -> str:
    count, items = output.get("count", 0), output.get("items") or []
    when = _day(turn, output.get("date", turn.today.isoformat()))
    if not count:
        return turn.text(
            f"No hay {'llegadas' if arrivals else 'salidas'} el {when}.",
            f"There are no {'arrivals' if arrivals else 'departures'} on {when}.",
        )
    noun = (
        (("llegada", "llegadas"), ("arrival", "arrivals"))
        if arrivals
        else (("salida", "salidas"), ("departure", "departures"))
    )
    lines = [
        turn.text(
            f"Hay {_plural(turn, count, *noun)} el {when}:",
            f"There are {_plural(turn, count, *noun)} on {when}:",
        )
    ]
    lines += [_reservation_line(turn, item) for item in items]
    if count > len(items):
        lines.append(turn.text(f"… y {count - len(items)} más.", f"… and {count - len(items)} more."))
    return "\n".join(lines)


def _availability(turn: Turn, output: dict, *, guest: bool) -> str:
    options = output.get("options") or []
    currency = output.get("currency", "COP")
    span = f"{_day(turn, output.get('checkin'))} → {_day(turn, output.get('checkout'))}"
    nights = output.get("nights") or 1
    if not options:
        return turn.text(
            f"No hay disponibilidad para {span}. ¿Probamos otras fechas?",
            f"There is no availability for {span}. Shall we try other dates?",
        )
    head = turn.text(
        f"Para {span} ({_plural(turn, nights, ('noche', 'noches'), ('night', 'nights'))}) hay "
        "disponibilidad:",
        f"For {span} ({_plural(turn, nights, ('noche', 'noches'), ('night', 'nights'))}) we have "
        "availability:",
    )
    lines = [head]
    for option in options:
        price = turn.text(
            f"{_money(option['total'], currency)} en total ({_money(option['per_night'], currency)} por "
            "noche)",
            f"{_money(option['total'], currency)} in total ({_money(option['per_night'], currency)} per "
            "night)",
        )
        left = option.get("available")
        stock = (
            turn.text(f"{left} disponible{'' if left == 1 else 's'}", f"{left} available")
            if left is not None
            else ""
        )
        lines.append("- " + " · ".join(part for part in (option.get("room_type", ""), price, stock) if part))
    if guest:
        lines.append(
            turn.text(
                "Puedes reservar directamente desde las opciones de abajo.",
                "You can book directly from the options below.",
            )
        )
    return "\n".join(lines)


def _summary(turn: Turn, output: dict) -> str:
    arrivals, departures = output.get("arrivals") or {}, output.get("departures") or {}
    currency = output.get("currency", "COP")
    return turn.text(
        f"Resumen del {_day(turn, output.get('date'))}: {arrivals.get('total', 0)} llegadas "
        f"({arrivals.get('done', 0)} con check-in), {departures.get('total', 0)} salidas "
        f"({departures.get('done', 0)} hechas), {output.get('in_house', 0)} huéspedes en casa y ocupación "
        "del "
        f"{output.get('occupancy_pct', 0)} % ({output.get('units_sold', 0)}/{output.get('units_total', 0)}). "
        f"Cobrado hoy: {_money(output.get('collected_today', 0), currency)}.",
        f"Summary for {_day(turn, output.get('date'))}: {arrivals.get('total', 0)} arrivals "
        f"({arrivals.get('done', 0)} checked in), {departures.get('total', 0)} departures "
        f"({departures.get('done', 0)} done), {output.get('in_house', 0)} guests in house and "
        f"{output.get('occupancy_pct', 0)} % occupancy ({output.get('units_sold', 0)}/"
        f"{output.get('units_total', 0)}). Collected today: "
        f"{_money(output.get('collected_today', 0), currency)}.",
    )


def _occupancy(turn: Turn, output: dict) -> str:
    lines = [
        turn.text(
            f"Ocupación promedio del {_day(turn, output.get('start'))} al {_day(turn, output.get('end'))}: "
            f"{output.get('average_pct', 0)} %.",
            f"Average occupancy from {_day(turn, output.get('start'))} to {_day(turn, output.get('end'))}: "
            f"{output.get('average_pct', 0)} %.",
        )
    ]
    for night in (output.get("nights") or [])[:14]:
        lines.append(f"- {_day(turn, night['date'])}: {night['pct']} % ({night['sold']}/{night['total']})")
    return "\n".join(lines)


def _balance(turn: Turn, output: dict) -> str:
    currency = output.get("currency", "COP")
    return turn.text(
        f"{output.get('code')} ({output.get('guest')}): total {_money(output.get('total'), currency)}, "
        "pagado "
        f"{_money(output.get('paid'), currency)}, saldo pendiente {_money(output.get('balance'), currency)}.",
        f"{output.get('code')} ({output.get('guest')}): total {_money(output.get('total'), currency)}, paid "
        f"{_money(output.get('paid'), currency)}, balance due {_money(output.get('balance'), currency)}.",
    )


def _reservation(turn: Turn, output: dict) -> str:
    currency = output.get("currency", "COP")
    rooms = ", ".join(output.get("rooms") or []) or turn.text("sin habitación", "no room yet")
    return turn.text(
        f"{output.get('code')} · {output.get('guest')} · {output.get('status')} · "
        f"{_day(turn, output.get('checkin'))} → {_day(turn, output.get('checkout'))} "
        f"({output.get('nights', '?')} noches) · hab. {rooms} · total "
        f"{_money(output.get('total', 0), currency)} · saldo {_money(output.get('balance', 0), currency)}.",
        f"{output.get('code')} · {output.get('guest')} · {output.get('status')} · "
        f"{_day(turn, output.get('checkin'))} → {_day(turn, output.get('checkout'))} "
        f"({output.get('nights', '?')} nights) · room {rooms} · total "
        f"{_money(output.get('total', 0), currency)} · balance {_money(output.get('balance', 0), currency)}.",
    )


def _found_reservations(turn: Turn, output: dict) -> str:
    count, items = output.get("count", 0), output.get("items") or []
    if not count:
        return turn.text("No encontré reservas con esos datos.", "I found no reservations matching that.")
    lines = [
        turn.text(
            f"Encontré {_plural(turn, count, ('reserva', 'reservas'), ('reservation', 'reservations'))}:",
            f"I found {_plural(turn, count, ('reserva', 'reservas'), ('reservation', 'reservations'))}:",
        )
    ]
    lines += [_reservation_line(turn, item) for item in items]
    return "\n".join(lines)


def _guests(turn: Turn, output: dict) -> str:
    count, items = output.get("count", 0), output.get("items") or []
    if not count:
        return turn.text("No encontré huéspedes con esos datos.", "I found no guests matching that.")
    lines = [
        turn.text(
            f"Encontré {_plural(turn, count, ('huésped', 'huéspedes'), ('guest', 'guests'))}:",
            f"I found {_plural(turn, count, ('huésped', 'huéspedes'), ('guest', 'guests'))}:",
        )
    ]
    for item in items:
        details = [item.get("email"), item.get("phone"), item.get("document")]
        lines.append(
            "- "
            + " · ".join(
                [item.get("name", "") + (" · VIP" if item.get("vip") else "")]
                + [value for value in details if value]
            )
        )
    return "\n".join(lines)


def _alerts(turn: Turn, output: dict) -> str:
    count, items = output.get("count", 0), output.get("items") or []
    if not count:
        return turn.text("No hay alertas abiertas. 👌", "There are no open alerts. 👌")
    lines = [
        turn.text(
            "Hay "
            f"{_plural(turn, count, ('alerta abierta', 'alertas abiertas'), ('open alert', 'open alerts'))}:",
            f"There {'is' if count == 1 else 'are'} "
            f"{_plural(turn, count, ('alerta abierta', 'alertas abiertas'), ('open alert', 'open alerts'))}:",
        )
    ]
    lines += [f"- [{item.get('severity')}] {item.get('title')}" for item in items]
    return "\n".join(lines)


def _rates(turn: Turn, output: dict) -> str:
    currency = output.get("currency", "COP")
    lines = [
        turn.text(
            f"Tarifas ({output.get('plan')}) del {_day(turn, output.get('start'))} al "
            f"{_day(turn, output.get('end'))}:",
            f"Rates ({output.get('plan')}) from {_day(turn, output.get('start'))} to "
            f"{_day(turn, output.get('end'))}:",
        )
    ]
    for room_type in output.get("room_types") or []:
        nights = " · ".join(
            f"{_day(turn, night['date'])} {_money(night['price'], currency)}"
            + (turn.text(" (cerrada)", " (closed)") if night.get("stop_sell") else "")
            for night in room_type.get("nights") or []
        )
        lines.append(f"- {room_type.get('code')} {room_type.get('name')}: {nights}")
    return "\n".join(lines)


COMPOSERS: dict[str, Callable[[Turn, dict], str]] = {
    "list_arrivals": lambda turn, output: _list(turn, output, arrivals=True),
    "list_departures": lambda turn, output: _list(turn, output, arrivals=False),
    "get_today_summary": _summary,
    "check_availability": lambda turn, output: _availability(turn, output, guest=False),
    "get_occupancy": _occupancy,
    "get_balance": _balance,
    "get_reservation": _reservation,
    "search_reservations": _found_reservations,
    "find_guest": _guests,
    "list_alerts": _alerts,
    "get_rates": _rates,
}


def compose_answer(turn: Turn) -> str:
    """The copilot's answer from this turn's tool results."""
    parts = []
    for name, output in turn.results:
        if not isinstance(output, dict):
            parts.append(str(output))
        elif output.get("error"):
            parts.append(
                turn.text(f"No pude completarlo: {output['error']}", f"I couldn't do it: {output['error']}")
            )
        elif output.get("proposal"):
            summary = output["proposal"].get("summary", "")
            parts.append(
                turn.text(
                    f"Preparé esta acción: {summary}. Revísala y confírmala en la tarjeta para ejecutarla.",
                    f"I prepared this action: {summary}. Review it and confirm it on the card to run it.",
                )
            )
        elif name in COMPOSERS:
            parts.append(COMPOSERS[name](turn, output))
        else:
            parts.append(turn.text("Listo.", "Done."))
    return "\n\n".join(parts)


def compose_guest_answer(turn: Turn) -> str:
    """The chatbot's answer from this turn's tool results."""
    parts = []
    for name, output in turn.results:
        if not isinstance(output, dict):
            continue
        if output.get("error"):
            parts.append(
                turn.text(
                    f"Lo siento, no pude consultarlo: {output['error']}",
                    f"Sorry, I couldn't check that: {output['error']}",
                )
            )
        elif name == "check_availability":
            parts.append(_availability(turn, output, guest=True))
        elif name == "request_human" and output.get("contact_needed") is False:
            parts.append(
                turn.text(
                    "Listo, ya le avisé al equipo del hotel: te escribirán pronto a los datos de contacto de "
                    "tu reserva.",
                    "Done, I've let the hotel team know: they'll write to you soon using the contact details "
                    "of your reservation.",
                )
            )
        elif name == "request_human":
            parts.append(
                turn.text(
                    "Con gusto te comunico con el equipo del hotel. Déjanos tu nombre y un correo o teléfono "
                    "y te contactaremos pronto.",
                    "I'll gladly put you in touch with the hotel team. Leave us your name and an email or "
                    "phone number and we'll contact you soon.",
                )
            )
    return "\n\n".join(parts) or turn.text("¿En qué más te puedo ayudar?", "How else can I help you?")
