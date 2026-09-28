"""Draft replies for the unified inbox (plan §C: `POST /api/v1/ai/draft-reply/` → `{text, simulated}`).

The model gets the guest's message, the reservation (when known), the hotel's knowledge (the chatbot's facts
and FAQ) and the tone; it answers with a ready-to-edit reply in the guest's language. Offline, the reply is
composed from the matching FAQ line with a greeting and a sign-off.
"""

from __future__ import annotations

import json

from apps.ai import nlp
from apps.ai.chatbot import knowledge
from apps.ai.llm import llm_for
from apps.ai.simulated import register_structured

TONES = ("friendly", "formal", "brief")
LANGUAGES = ("es", "en")
DRAFT_SCHEMA = {
    "title": "draft_reply",
    "type": "object",
    "properties": {"text": {"type": "string", "description": "La respuesta lista para enviar"}},
    "required": ["text"],
}
DRAFT_SYSTEM = (
    "Eres parte del equipo de recepción de un hotel. Escribe la respuesta a un mensaje de un huésped con los "
    "datos del JSON: en su idioma (campo language), con el tono pedido (friendly = cálido y cercano, formal "
    "= cortés y de usted, brief = dos frases como máximo), usando solo el conocimiento del hotel y los datos "
    "de la reserva. Si no sabes algo, di que lo confirmas en breve; nunca inventes precios, horarios ni "
    "disponibilidad. Firma con el nombre del hotel. Devuelve solo el texto del mensaje."
)


def _language(requested, reservation, prop) -> str:
    """Explicit → the guest's → the reservation's → the hotel's (the same order as the messaging app)."""
    guest = getattr(reservation, "booker", None)
    for value in (
        requested,
        getattr(guest, "language", None),
        getattr(reservation, "language", None),
        prop.default_language,
    ):
        if value in LANGUAGES:
            return value
    return "es"


def draft_reply(
    prop, *, guest_message: str, reservation=None, language=None, tone="friendly", llm=None
) -> dict:
    lang = _language(language, reservation, prop)
    guest = getattr(reservation, "booker", None)
    payload = {
        "hotel": prop.name,
        "language": lang,
        "tone": tone if tone in TONES else "friendly",
        "guest_message": guest_message.strip()[:2000],
        "guest_name": guest.full_name if guest else "",
        "guest_first_name": guest.first_name if guest else "",
        "reservation": {
            "code": reservation.code,
            "status": reservation.status,
            "checkin": reservation.checkin_date.isoformat(),
            "checkout": reservation.checkout_date.isoformat(),
            "adults": reservation.adults,
            "children": reservation.children,
        }
        if reservation is not None
        else None,
        "knowledge": knowledge(prop, lang),
    }
    llm = llm or llm_for(prop, "draft_reply")
    result = llm.generate(
        [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        system=DRAFT_SYSTEM,
        response_schema=DRAFT_SCHEMA,
        temperature=0.4,
    )
    text = str(result.data.get("text") or "").strip() if isinstance(result.data, dict) else ""
    return {"text": text or compose_draft(payload), "simulated": bool(result.simulated), "language": lang}


def compose_draft(payload: dict) -> str:
    en = payload.get("language") == "en"
    name = payload.get("guest_first_name") or ""
    tone = payload.get("tone")
    if tone == "formal":
        greeting = (
            f"Dear {payload.get('guest_name') or 'guest'},"
            if en
            else f"Estimado(a) {payload.get('guest_name') or 'huésped'}:"
        )
    else:
        greeting = (f"Hi {name}," if name else "Hi,") if en else (f"Hola, {name}:" if name else "Hola:")
    answer = nlp.best_answer(payload.get("guest_message", ""), payload.get("knowledge") or [])
    body = answer or (
        "Thank you for your message. We'll check and get back to you shortly."
        if en
        else "Gracias por escribirnos. Lo revisamos y te respondemos en breve."
    )
    reservation = payload.get("reservation")
    extra = ""
    if reservation and tone != "brief":
        extra = (
            f"We look forward to welcoming you on {nlp.format_date(reservation['checkin'], 'en')} "
            f"(reservation {reservation['code']})."
            if en
            else f"Te esperamos el {nlp.format_date(reservation['checkin'])} (reserva {reservation['code']})."
        )
    closing = f"Best regards,\n{payload.get('hotel')}" if en else f"Saludos,\n{payload.get('hotel')}"
    return "\n\n".join(part for part in (greeting, body, extra, closing) if part)


@register_structured("draft_reply")
def _simulated_draft(prompt: str, system: str | None) -> dict | None:
    try:
        payload = json.loads(prompt)
    except ValueError:
        return None
    return {"text": compose_draft(payload)}
