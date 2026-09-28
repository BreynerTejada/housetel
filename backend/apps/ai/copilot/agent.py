"""The copilot's agent loop (plan C9).

One turn: the user's message is stored, the model gets the conversation, the hotel context and the tools the
user's role allows; every tool call it asks for runs against the hotel's data (`copilot.tools.run_tool`) and
its result goes back to the model, until it answers with text or 5 model calls were made. Action tools only
create proposals (`CopilotAction`), confirmed later by the user. Every message is stored, so the next turn
(and a reload of the panel) sees the whole conversation.

No database transaction is held across model calls (they can take seconds): each message is saved on its
own.
"""

from __future__ import annotations

from django.db.models import Max
from django.utils import timezone

from apps.ai.clients.base import to_json
from apps.ai.copilot.tools import ToolContext, available_tools, run_tool
from apps.ai.llm import assistant_message, llm_for, serialize_tool_call, tool_message
from apps.ai.models import CopilotAction, CopilotMessage
from apps.core.i18n import t

MAX_ITERATIONS = 5
HISTORY_USER_TURNS = 8  # previous user turns sent back to the model (with everything after them)
LANGUAGES = ("es", "en")

TEXT = {
    "exhausted": (
        "Necesité más pasos de los permitidos para responder. Prueba con una pregunta más concreta.",
        "I needed more steps than I'm allowed to answer. Try a more specific question.",
    ),
    "empty": (
        "No pude generar una respuesta. ¿Puedes reformular la pregunta?",
        "I couldn't come up with an answer. Could you rephrase the question?",
    ),
}


def _text(key: str, lang: str) -> str:
    es, en = TEXT[key]
    return en if lang == "en" else es


def system_prompt(prop, lang: str) -> str:
    language = "inglés" if lang == "en" else "español"
    place = f", en {prop.city}" if prop.city else ""
    return "\n".join(
        [
            f"Eres el copiloto de {prop.name}{place}. Ayudas al equipo del hotel con la operación diaria.",
            f"Fecha de hoy: {prop.business_date.isoformat()} (fecha de negocio del hotel)",
            f"Idioma: {lang}",
            f"Moneda: {prop.currency}",
            f"Hora de check-in: {prop.check_in_time:%H:%M} · check-out: {prop.check_out_time:%H:%M}",
            "",
            "## Reglas",
            f"- Responde siempre en {language}, en pocas frases y con Markdown simple (listas si hay varios "
            "elementos).",
            "- Usa las herramientas para cualquier dato del hotel; nunca inventes reservas, huéspedes, "
            "cifras ni fechas.",
            "- Las acciones (crear o mover reservas, check-in, check-out, mensajes, bloqueos, extras) solo "
            "se proponen: la herramienta devuelve una propuesta que el usuario confirma en una tarjeta. "
            "Nunca digas que ya se ejecutaron.",
            "- Si falta un dato para una acción (fechas, huésped, habitación), pregúntalo antes de "
            "proponerla.",
            "- Si una herramienta devuelve un error, explícalo con claridad y sugiere cómo seguir.",
            "- En las herramientas las fechas van como AAAA-MM-DD; «hoy» es la fecha de negocio.",
            "- Solo tienes las herramientas que permite el rol del usuario; si te piden otra cosa, dilo.",
            f"- Hotel: {t(prop.description, lang)[:600]}" if prop.description else "",
        ]
    ).strip()


def _next_position(session) -> int:
    last = CopilotMessage.objects.filter(session=session).aggregate(last=Max("position"))["last"]
    return 0 if last is None else last + 1


class _Writer:
    """Appends messages to the session with consecutive positions."""

    def __init__(self, session):
        self.session = session
        self.position = _next_position(session)
        self.messages: list[CopilotMessage] = []

    def add(self, role: str, content: str = "", **fields) -> CopilotMessage:
        message = CopilotMessage.objects.create(
            session=self.session, position=self.position, role=role, content=content or "", **fields
        )
        self.position += 1
        self.messages.append(message)
        return message


def to_llm_message(message: CopilotMessage) -> dict:
    if message.role == CopilotMessage.Role.TOOL:
        return {
            "role": "tool",
            "tool_call_id": message.tool_call_id,
            "name": message.name,
            "content": message.content,
        }
    data = {"role": message.role, "content": message.content}
    if message.role == CopilotMessage.Role.ASSISTANT and message.tool_calls:
        data["tool_calls"] = message.tool_calls
    return data


def history(session) -> list[dict]:
    """The conversation for the model: the last HISTORY_USER_TURNS user turns and everything after them (a
    turn is never cut, so every tool result keeps the call that asked for it)."""
    user_positions = list(
        CopilotMessage.objects.filter(session=session, role=CopilotMessage.Role.USER)
        .order_by("-position")
        .values_list("position", flat=True)[:HISTORY_USER_TURNS]
    )
    if not user_positions:
        return []
    messages = CopilotMessage.objects.filter(session=session, position__gte=min(user_positions))
    return [to_llm_message(message) for message in messages.order_by("position")]


def run_turn(session, text: str, *, user, lang: str | None = None, llm=None) -> dict:
    """Run one copilot turn. Returns `{"messages": [CopilotMessage of this turn], "proposals":
    [CopilotAction created in this turn]}`."""
    prop = session.property
    lang = lang if lang in LANGUAGES else (getattr(user, "language", "") or "es")
    lang = lang if lang in LANGUAGES else "es"
    llm = llm or llm_for(prop, "copilot")
    writer = _Writer(session)
    writer.add(CopilotMessage.Role.USER, text)
    conversation = history(session)
    system = system_prompt(prop, lang)
    tools = [item.schema() for item in available_tools(user, prop)] or None
    proposal_ids: list = []

    for _ in range(MAX_ITERATIONS):
        result = llm.generate(conversation, system=system, tools=tools, temperature=0.2)
        content = result.text or ("" if result.tool_calls else _text("empty", lang))
        assistant = writer.add(
            CopilotMessage.Role.ASSISTANT,
            content,
            tool_calls=[serialize_tool_call(call) for call in result.tool_calls],
            provider=(result.provider or "")[:20],
            simulated=bool(result.simulated),
        )
        conversation.append({**assistant_message(result), "content": content})
        if not result.tool_calls:
            break
        ctx = ToolContext(property=prop, user=user, session=session, lang=lang, message=assistant)
        for call in result.tool_calls:
            output = run_tool(ctx, call.name, call.arguments)
            if isinstance(output, dict) and isinstance(output.get("proposal"), dict):
                proposal_ids.append(output["proposal"]["id"])
            writer.add(
                CopilotMessage.Role.TOOL,
                to_json(output),
                tool_call_id=(call.id or "")[:100],
                name=(call.name or "")[:80],
            )
            conversation.append(tool_message(call, output))
    else:
        writer.add(CopilotMessage.Role.ASSISTANT, _text("exhausted", lang), provider="system")

    session.last_message_at = timezone.now()
    fields = ["last_message_at", "updated_at"]
    if not session.title:
        session.title = " ".join(text.split())[:200]
        fields.append("title")
    session.save(update_fields=fields)
    proposals = list(CopilotAction.objects.filter(pk__in=proposal_ids).order_by("created_at"))
    return {"messages": writer.messages, "proposals": proposals}
