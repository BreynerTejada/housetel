"""Public chatbot of a hotel (plan C9), mounted by the public layouts (website, booking engine, guest portal).

- Knowledge: the hotel's profile (description, location, hours, house rules, policies, amenities), its room
  types, cancellation policies, extras sold online and its FAQ in the guest's language, written in the system
  prompt under `## Conocimiento` (the offline assistant answers from those lines too).
- Tools: `check_availability` (the booking engine's offers, `search_offers(channel="booking_engine")`) → the
  answer plus offer cards linking to `/h/<slug>?checkin&checkout&adults&children`; `request_human` → hand-off:
  the conversation is flagged, an alert `chatbot_handoff` is raised (link to the conversation) and the guest
  is asked for a way to reach them. The contact updates the alert and opens a thread in the unified inbox
  (`messaging.record_inbound_message`, channel `web_chat`).
- Limits: 1000 characters per message and SESSION_MESSAGE_LIMIT messages per session every 10 minutes (the
  public view also throttles by IP).
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

from django.db import transaction
from django.utils import timezone

from apps.ai import nlp
from apps.ai.copilot.tools import MAX_NIGHTS as _COPILOT_MAX_NIGHTS
from apps.ai.copilot.tools import offer_options
from apps.ai.llm import assistant_message, llm_for, tool_message
from apps.ai.models import ChatbotConversation, PropertyFAQ
from apps.core.dates import property_now
from apps.core.errors import DomainError
from apps.core.i18n import t

logger = logging.getLogger("housetel.ai")

SESSION_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
MAX_ITERATIONS = 3
HISTORY_MESSAGES = 12
MAX_MESSAGE_CHARS = 1000
SESSION_MESSAGE_LIMIT = 20
SESSION_WINDOW = timedelta(minutes=10)
MAX_NIGHTS = min(_COPILOT_MAX_NIGHTS, 30)
LANGUAGES = ("es", "en")
HANDOFF_REASONS = ("requested", "low_confidence", "complaint", "other")

GUEST_TOOLS = [
    {
        "name": "check_availability",
        "description": "Disponibilidad y precio por categoría para unas fechas y huéspedes (el motor de "
        "reservas del hotel). Úsala siempre que el huésped mencione fechas.",
        "parameters": {
            "type": "object",
            "properties": {
                "checkin": {"type": "string", "description": "Llegada AAAA-MM-DD"},
                "checkout": {"type": "string", "description": "Salida AAAA-MM-DD (el día que se va)"},
                "adults": {"type": "integer", "description": "Adultos (por defecto 2)"},
                "children": {"type": "integer", "description": "Niños"},
            },
            "required": ["checkin", "checkout"],
        },
    },
    {
        "name": "request_human",
        "description": "Pasa la conversación a una persona del hotel: cuando el huésped lo pide, se queja o "
        "preguntas algo que no está en el conocimiento.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "enum": list(HANDOFF_REASONS)},
                "summary": {"type": "string", "description": "Qué necesita el huésped, en una frase"},
            },
            "required": ["reason"],
        },
    },
]

TEXT = {
    "greeting": (
        "¡Hola! Soy el asistente virtual de {name}. Te ayudo con disponibilidad, precios y preguntas sobre "
        "tu estadía.",
        "Hi! I'm {name}'s virtual assistant. I can help with availability, prices and "
        "questions about your stay.",
    ),
    "fallback": (
        "Déjame comunicarte con el equipo del hotel para ayudarte mejor.",
        "Let me put you in touch with the hotel team so they can help you.",
    ),
}
SUGGESTIONS = {
    "es": [
        "¿Tienen disponibilidad este fin de semana?",
        "¿A qué hora es el check-in?",
        "¿Tienen parqueadero?",
        "Quiero hablar con una persona",
    ],
    "en": [
        "Do you have rooms this weekend?",
        "What time is check-in?",
        "Do you have parking?",
        "I want to talk to a person",
    ],
}
BED_NAMES = {
    "single": ("sencilla", "single"),
    "twin": ("twin", "twin"),
    "double": ("doble", "double"),
    "queen": ("queen", "queen"),
    "king": ("king", "king"),
    "bunk": ("camarote", "bunk"),
    "sofa_bed": ("sofá cama", "sofa bed"),
    "crib": ("cuna", "crib"),
}


class RateLimited(DomainError):
    code = "rate_limited"
    status_code = 429


@dataclass
class ChatReply:
    conversation: ChatbotConversation
    content: str
    cards: list[dict] = field(default_factory=list)


def _lang(value) -> str:
    return value if value in LANGUAGES else "es"


def _text(key: str, lang: str, **values) -> str:
    es, en = TEXT[key]
    return (en if lang == "en" else es).format(**values)


def local_today(prop) -> date:
    """ "Today" for a guest: the hotel's calendar date (the business date may lag until the night audit)."""
    return property_now(prop).date()


# ---- property and conversation ---------------------------------------------------------------------------


def chatbot_property(slug: str):
    """The active hotel with its chatbot switched on, or None."""
    from apps.ai.features import ai_settings
    from apps.core.models import Property

    prop = (
        Property.objects.select_related("organization")
        .filter(slug=slug, status="active", organization__status__in=["trial", "active", "past_due"])
        .first()
    )
    if prop is None or not ai_settings(prop).chatbot_enabled:
        return None
    return prop


def portal_reservation(token: str):
    """The reservation behind a guest portal token whose hotel has the chatbot switched on, or None."""
    from apps.core.tokens import read_reservation_token

    reservation = read_reservation_token(token)
    if reservation is None or chatbot_property(reservation.property.slug) is None:
        return None
    return reservation


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


def get_conversation(prop, session_id: str | None, *, reservation=None, lang="es", create=False):
    if session_id and not SESSION_ID.match(session_id):
        raise DomainError(
            "Sesión inválida", code="validation_error", fields={"session_id": ["Sesión inválida"]}
        )
    if session_id:
        conversation = ChatbotConversation.objects.filter(property=prop, session_id=session_id).first()
        if conversation is not None or not create:
            return conversation
    if not create:
        return None
    conversation, _ = ChatbotConversation.objects.get_or_create(
        property=prop,
        session_id=session_id or new_session_id(),
        defaults={"reservation": reservation, "language": _lang(lang)},
    )
    return conversation


def _check_rate(conversation) -> None:
    since = timezone.now() - SESSION_WINDOW
    recent = 0
    for message in conversation.messages or []:
        if message.get("role") != "user":
            continue
        try:
            at = datetime.fromisoformat(message.get("at", ""))
        except (TypeError, ValueError):
            continue
        if at >= since:
            recent += 1
    if recent >= SESSION_MESSAGE_LIMIT:
        raise RateLimited("Enviaste muchos mensajes seguidos; espera unos minutos, por favor.")


# ---- knowledge and prompt ------------------------------------------------------------------------------


def _amenity_names(prop, codes, lang) -> list[str]:
    from django.db.models import Q

    from apps.inventory.models import Amenity

    codes = [code for code in codes or [] if code]
    if not codes:
        return []
    found = {
        amenity.code: t(amenity.name, lang)
        for amenity in Amenity.objects.filter(
            Q(organization__isnull=True) | Q(organization=prop.organization), code__in=codes
        ).order_by("organization_id")
    }
    return [found.get(code, code.replace("_", " ")) for code in codes]


def _beds(beds, lang) -> str:
    parts = []
    for bed in beds or []:
        names = BED_NAMES.get(str(bed.get("type")), (str(bed.get("type")), str(bed.get("type"))))
        count = int(bed.get("count") or 1)
        name = names[1] if lang == "en" else names[0]
        parts.append(f"{count} × {name}" if count > 1 else name)
    return ", ".join(parts)


def _policies(prop, lang) -> str:
    policies = {
        "pets_allowed": False,
        "smoking_allowed": False,
        "children_allowed": True,
        "min_checkin_age": 18,
        **((prop.settings or {}).get("policies") or {}),
    }
    if lang == "en":
        return (
            f"pets {'allowed' if policies.get('pets_allowed') else 'not allowed'}; smoking "
            f"{'allowed' if policies.get('smoking_allowed') else 'not allowed'}; children "
            f"{'welcome' if policies.get('children_allowed') else 'not accepted'}; minimum check-in age "
            f"{policies.get('min_checkin_age', 18)}."
        )
    return (
        f"mascotas {'permitidas' if policies.get('pets_allowed') else 'no permitidas'}; "
        f"{'se permite fumar' if policies.get('smoking_allowed') else 'no se permite fumar'}; niños "
        f"{'bienvenidos' if policies.get('children_allowed') else 'no admitidos'}; edad mínima para "
        f"registrarse {policies.get('min_checkin_age', 18)} años."
    )


def knowledge(prop, lang: str, *, reservation=None) -> list[str]:
    """Facts the assistant may use, one per line (FAQ lines are "question → answer")."""
    from apps.inventory.models import RoomType
    from apps.rates.models import CancellationPolicy, Extra

    en = lang == "en"
    lines = []
    kind = t({"es": "hotel", "en": "hotel"}, lang) if prop.property_type == "hotel" else prop.property_type
    stars = f", {prop.star_rating} {'stars' if en else 'estrellas'}" if prop.star_rating else ""
    lines.append(f"{'Name' if en else 'Nombre'}: {prop.name} ({kind}{stars}).")
    location = ", ".join(part for part in (prop.address, prop.city, prop.department) if part)
    if location:
        lines.append(
            f"{'Location, address, how to get here' if en else 'Ubicación, dirección, cómo llegar'}: "
            f"{location}."
        )
    if description := t(prop.description, lang):
        lines.append(f"{'Description' if en else 'Descripción'}: {description[:700]}")
    lines.append(
        f"Schedule: check-in from {prop.check_in_time:%H:%M} and check-out until {prop.check_out_time:%H:%M}."
        if en
        else f"Horarios: check-in desde las {prop.check_in_time:%H:%M} y check-out hasta las "
        f"{prop.check_out_time:%H:%M}."
    )
    if rules := t(prop.house_rules, lang):
        lines.append(f"{'House rules' if en else 'Reglas de la casa'}: {rules[:500]}")
    lines.append(f"{'Policies' if en else 'Políticas'}: {_policies(prop, lang)}")
    if amenities := _amenity_names(prop, (prop.settings or {}).get("amenities"), lang):
        lines.append(
            f"{'Hotel services and amenities' if en else 'Servicios del hotel'}: {', '.join(amenities)}."
        )
    room_types = RoomType.objects.filter(property=prop, is_active=True).prefetch_related("amenities")
    for room_type in room_types.order_by("sort_order", "code"):
        details = [
            (f"up to {room_type.max_occupancy} guests" if en else f"hasta {room_type.max_occupancy} personas")
            if room_type.kind == "private"
            else ("bed in a shared dorm" if en else "cama en dormitorio compartido"),
            _beds(room_type.beds, lang),
            f"{room_type.size_m2:g} m²" if room_type.size_m2 else "",
            ", ".join(t(item.name, lang) for item in list(room_type.amenities.all())[:6]),
        ]
        lines.append(
            f"{'Room' if en else 'Habitación'} {t(room_type.name, lang)}: "
            f"{'; '.join(part for part in details if part)}."
        )
    for policy in CancellationPolicy.objects.filter(property=prop):
        text = t(policy.description, lang) or (
            ("Non-refundable." if en else "No reembolsable.")
            if policy.non_refundable
            else (
                f"Free cancellation until {policy.free_until_hours_before} h before arrival."
                if en
                else f"Cancelación gratis hasta {policy.free_until_hours_before} h antes de la llegada."
            )
        )
        lines.append(f"{'Cancellation' if en else 'Cancelación'} «{t(policy.name, lang)}»: {text}")
    extras = Extra.objects.filter(property=prop, is_active=True, sellable_online=True).order_by("code")[:10]
    if extras:
        items = [f"{t(extra.name, lang)} {nlp.format_money(extra.price, prop.currency)}" for extra in extras]
        lines.append(f"{'Extras' if en else 'Extras'}: {'; '.join(items)}.")
    contact = " · ".join(part for part in (prop.phone, prop.email) if part)
    if contact:
        lines.append(f"{'Contact' if en else 'Contacto'}: {contact}.")
    if reservation is not None:
        lines.append(_reservation_line(reservation, lang))
    faqs = PropertyFAQ.objects.filter(property=prop, is_active=True)
    same_language = list(faqs.filter(language=lang).order_by("sort", "created_at"))
    for faq in same_language or list(faqs.order_by("sort", "created_at")):
        lines.append(f"{' '.join(faq.question.split())} → {' '.join(faq.answer.split())}")
    return lines


RESERVATION_STATUS = {
    "tentative": ("pendiente de pago", "pending payment"),
    "confirmed": ("confirmada", "confirmed"),
    "checked_in": ("en curso", "in progress"),
    "checked_out": ("finalizada", "completed"),
    "cancelled": ("cancelada", "cancelled"),
    "no_show": ("no show", "no-show"),
}


def _reservation_line(reservation, lang) -> str:
    stays = list(reservation.stays.select_related("room_type").all())
    kinds = ", ".join(sorted({t(stay.room_type.name, lang) for stay in stays}))
    status = reservation.status
    es_status, en_status = RESERVATION_STATUS.get(status, (status, status))
    if lang == "en":
        return (
            f"The guest's reservation: {reservation.code}, {en_status}, arrival "
            f"{nlp.format_date(reservation.checkin_date, 'en')} (check-in from "
            f"{reservation.property.check_in_time:%H:%M}), departure "
            f"{nlp.format_date(reservation.checkout_date, 'en')} (check-out until "
            f"{reservation.property.check_out_time:%H:%M}), {reservation.adults} adults, {kinds}."
        )
    return (
        f"Reserva del huésped: {reservation.code}, {es_status}, llegada "
        f"{nlp.format_date(reservation.checkin_date)} (check-in desde las "
        f"{reservation.property.check_in_time:%H:%M}), salida {nlp.format_date(reservation.checkout_date)} "
        f"(check-out hasta las {reservation.property.check_out_time:%H:%M}), {reservation.adults} adultos, "
        f"{kinds}."
    )


def system_prompt(prop, lang: str, *, reservation=None) -> str:
    language = "inglés" if lang == "en" else "español"
    lines = [
        f"Eres el asistente virtual de {prop.name}. Atiendes a huéspedes y viajeros en la página del hotel.",
        f"Fecha de hoy: {local_today(prop).isoformat()}",
        f"Idioma: {lang}",
        f"Moneda: {prop.currency}",
        "",
        "## Conocimiento",
        *[f"- {line}" for line in knowledge(prop, lang, reservation=reservation)],
        "",
        "## Reglas",
        f"- Responde en el idioma del huésped (por defecto {language}), en 1 a 3 frases, con tono cálido.",
        "- Usa solo el conocimiento de arriba y las herramientas; si no lo sabes, no inventes: llama a "
        "request_human.",
        "- Si el huésped da fechas, usa check_availability. Las reservas se hacen en el motor de reservas "
        "del hotel (las opciones aparecen como tarjetas debajo de tu respuesta).",
        "- Si pide hablar con una persona o hace un reclamo, llama a request_human.",
        "- Nunca pidas datos de tarjetas ni contraseñas por el chat.",
    ]
    return "\n".join(lines)


# ---- tools -------------------------------------------------------------------------------------------------


def _parse_day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def check_availability(prop, arguments: dict, *, lang: str) -> dict:
    en = lang == "en"
    start, end = _parse_day(arguments.get("checkin")), _parse_day(arguments.get("checkout"))
    if start is None or end is None:
        return {
            "error": "Give the arrival and departure dates"
            if en
            else "Indica la fecha de llegada y la de salida"
        }
    if end <= start:
        return {
            "error": "Departure must be after arrival" if en else "La salida debe ser posterior a la llegada"
        }
    if start < local_today(prop):
        return {"error": "That date has already passed" if en else "Esa fecha ya pasó"}
    if (end - start).days > MAX_NIGHTS:
        return {"error": f"At most {MAX_NIGHTS} nights" if en else f"Máximo {MAX_NIGHTS} noches"}
    adults = max(1, min(int(arguments.get("adults") or 2), 20))
    children = max(0, min(int(arguments.get("children") or 0), 10))
    options = offer_options(
        prop, start, end, adults=adults, children=children, lang=lang, channel="booking_engine"
    )
    return {
        "checkin": start.isoformat(),
        "checkout": end.isoformat(),
        "nights": (end - start).days,
        "adults": adults,
        "children": children,
        "currency": prop.currency,
        "options": options,
    }


def offer_cards(prop, output: dict) -> list[dict]:
    query = urlencode(
        {
            "checkin": output["checkin"],
            "checkout": output["checkout"],
            "adults": output["adults"],
            "children": output["children"],
        }
    )
    return [
        {
            "type": "offer",
            "room_type_id": option["room_type_id"],
            "room_type_code": option["room_type_code"],
            "room_type": option["room_type"],
            "rate_plan": option["rate_plan"],
            "total": option["total"],
            "per_night": option["per_night"],
            "currency": output["currency"],
            "available": option["available"],
            "nights": output["nights"],
            "checkin": output["checkin"],
            "checkout": output["checkout"],
            "adults": output["adults"],
            "children": output["children"],
            "url": f"/h/{prop.slug}?{query}",
        }
        for option in output.get("options") or []
    ]


def _known_contact(conversation) -> dict:
    if conversation.contact:
        return conversation.contact
    reservation = conversation.reservation
    if reservation is not None and (reservation.booker.email or reservation.booker.phone):
        booker = reservation.booker
        return {"name": booker.full_name, "email": booker.email, "phone": booker.phone, "from": "reservation"}
    return {}


def _raise_handoff_alert(conversation) -> None:
    from apps.core.alerts import raise_alert

    contact = _known_contact(conversation)
    who = contact.get("name") or "Un visitante"
    if conversation.handoff_reason == "low_confidence":
        lines = ["El asistente del chat no supo responder una pregunta y pasó la conversación al equipo."]
    else:
        lines = [f"{who} pidió hablar con una persona en el chat de la página."]
    if summary := (conversation.contact or {}).get("message") or _last_user_message(conversation):
        lines.append(f"Mensaje: «{summary[:300]}».")
    reach = " · ".join(value for value in (contact.get("email"), contact.get("phone")) if value)
    lines.append(f"Contacto: {reach}." if reach else "Aún no dejó sus datos de contacto.")
    if conversation.reservation_id:
        lines.append(f"Reserva: {conversation.reservation.code}.")
    raise_alert(
        property=conversation.property,
        kind="chatbot_handoff",
        severity="warning",
        title="Un huésped pide hablar con el equipo",
        message=" ".join(lines),
        link=f"/app/settings/chatbot?conversation={conversation.pk}",
        dedupe_key=f"ai:chatbot_handoff:{conversation.pk}",
        data={"conversation_id": str(conversation.pk), "reason": conversation.handoff_reason, **contact},
        source="ai",
    )


def _last_user_message(conversation) -> str:
    return next(
        (m.get("content", "") for m in reversed(conversation.messages or []) if m.get("role") == "user"), ""
    )


def request_human(conversation, arguments: dict, *, lang: str) -> dict:
    reason = arguments.get("reason") if arguments.get("reason") in HANDOFF_REASONS else "other"
    conversation.handoff_requested = True
    conversation.handoff_reason = reason
    conversation.handoff_at = conversation.handoff_at or timezone.now()
    conversation.handoff_resolved_at = None
    conversation.save(
        update_fields=[
            "handoff_requested",
            "handoff_reason",
            "handoff_at",
            "handoff_resolved_at",
            "updated_at",
        ]
    )
    _raise_handoff_alert(conversation)
    return {"ok": True, "contact_needed": not _known_contact(conversation)}


def guest_tool(prop, conversation, name: str, arguments, *, lang: str) -> dict:
    arguments = arguments if isinstance(arguments, dict) else {}
    try:
        if name == "check_availability":
            return check_availability(prop, arguments, lang=lang)
        if name == "request_human" and conversation is not None:
            return request_human(conversation, arguments, lang=lang)
    except DomainError as exc:
        return {"error": exc.message}
    except (TypeError, ValueError):
        return {"error": "Datos inválidos" if lang != "en" else "Invalid data"}
    return {"error": f"Herramienta desconocida: {name}"}


# ---- the turn ----------------------------------------------------------------------------------------------


def handoff_state(conversation) -> dict:
    received = bool(conversation.contact)
    return {
        "requested": conversation.handoff_requested,
        "contact_needed": conversation.handoff_requested and not _known_contact(conversation),
        "contact_received": received,
    }


def _append(conversation, role: str, content: str, cards=None) -> None:
    entry = {"role": role, "content": content, "at": timezone.now().isoformat()}
    if cards:
        entry["cards"] = cards
    conversation.messages = [*(conversation.messages or []), entry]


def reply(prop, message: str, *, session_id=None, lang="es", reservation=None, llm=None) -> ChatReply:
    lang = _lang(lang)
    text = " ".join(str(message or "").split())[:MAX_MESSAGE_CHARS]
    if not text:
        raise DomainError("Escribe un mensaje", code="validation_error", fields={"message": ["Obligatorio"]})
    conversation = get_conversation(prop, session_id, reservation=reservation, lang=lang, create=True)
    if reservation is not None and conversation.reservation_id is None:
        conversation.reservation = reservation
    _check_rate(conversation)
    history = [
        {"role": item["role"], "content": item.get("content", "")}
        for item in (conversation.messages or [])[-HISTORY_MESSAGES:]
    ]
    history.append({"role": "user", "content": text})
    _append(conversation, "user", text)
    conversation.language = lang
    conversation.last_message_at = timezone.now()
    conversation.save(update_fields=["messages", "language", "last_message_at", "reservation", "updated_at"])

    llm = llm or llm_for(prop, "chatbot")
    system = system_prompt(prop, lang, reservation=conversation.reservation)
    cards: list[dict] = []
    answer = ""
    for _ in range(MAX_ITERATIONS):
        result = llm.generate(history, system=system, tools=GUEST_TOOLS, temperature=0.3)
        if not result.tool_calls:
            answer = result.text
            break
        history.append(assistant_message(result))
        for call in result.tool_calls:
            output = guest_tool(prop, conversation, call.name, call.arguments, lang=lang)
            if call.name == "check_availability" and "options" in output:
                cards = offer_cards(prop, output)
            history.append(tool_message(call, output))
    answer = answer.strip() or _text("fallback", lang)

    with transaction.atomic():
        conversation = ChatbotConversation.objects.select_for_update().get(pk=conversation.pk)
        _append(conversation, "assistant", answer, cards)
        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=["messages", "last_message_at", "updated_at"])
    return ChatReply(conversation=conversation, content=answer, cards=cards)


def submit_contact(conversation, *, name: str, email: str = "", phone: str = "", message: str = ""):
    """The guest's contact after a hand-off: saved, added to the alert and sent to the inbox as a web chat."""
    contact = {
        "name": name.strip()[:120],
        "email": email.strip()[:254],
        "phone": phone.strip()[:40],
        "message": message.strip()[:MAX_MESSAGE_CHARS],
        "at": timezone.now().isoformat(),
    }
    first = not conversation.contact
    conversation.contact = contact
    if not conversation.handoff_requested:
        conversation.handoff_requested, conversation.handoff_reason = True, "other"
        conversation.handoff_at = timezone.now()
    conversation.save(
        update_fields=["contact", "handoff_requested", "handoff_reason", "handoff_at", "updated_at"]
    )
    _raise_handoff_alert(conversation)
    if first:
        _send_to_inbox(conversation)
    return conversation


def _send_to_inbox(conversation) -> None:
    try:
        from apps.messaging.services import record_inbound_message
    except ImportError:  # pragma: no cover - messaging (C6) not installed
        return
    contact = conversation.contact
    reach = " · ".join(value for value in (contact.get("email"), contact.get("phone")) if value)
    transcript = "\n".join(
        f"{'Huésped' if item['role'] == 'user' else 'Asistente'}: {item.get('content', '')}"
        for item in (conversation.messages or [])[-10:]
    )
    body = "\n".join(
        part
        for part in [
            "Solicitud desde el chat de la página.",
            f"Contacto: {contact.get('name')} · {reach}",
            f"Mensaje: {contact['message']}" if contact.get("message") else "",
            "",
            "Conversación:",
            transcript,
        ]
        if part is not None
    )
    try:
        record_inbound_message(
            conversation.property,
            channel="web_chat",
            body=body,
            address=f"chatbot:{conversation.session_id}",
            guest=conversation.reservation.booker if conversation.reservation_id else None,
            reservation=conversation.reservation,
            contact_name=contact.get("name", ""),
            provider_message_id=f"chatbot:{conversation.pk}",
            subject="Chat de la página",
        )
    except Exception:  # the inbox is a convenience: the alert already has everything
        logger.exception("Could not open the inbox thread of chatbot conversation %s", conversation.pk)


def widget_config(prop, lang: str) -> dict:
    from apps.ai.features import ai_settings

    lang = _lang(lang)
    greeting = t(ai_settings(prop).chatbot_greeting, lang) or _text("greeting", lang, name=prop.name)
    return {
        "enabled": True,
        "property": {
            "name": prop.name,
            "slug": prop.slug,
            "city": prop.city,
            "primary_color": (prop.branding or {}).get("primary_color", ""),
        },
        "greeting": greeting,
        "suggestions": SUGGESTIONS[lang],
        "languages": list(LANGUAGES),
    }


def public_messages(conversation) -> list[dict]:
    return [
        {
            "role": item.get("role"),
            "content": item.get("content", ""),
            "cards": item.get("cards") or [],
            "at": item.get("at"),
        }
        for item in conversation.messages or []
    ]
