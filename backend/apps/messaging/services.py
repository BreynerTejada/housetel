"""Messaging services (spec §4.2 contract `send_message`, plan C6).

Every outbound message goes: template (property → organization → system, in the guest's language) → values
(`variables.build_variables`) → safe renderer → provider of the channel (`core.integrations`) → a `Message` in
the `Conversation` of that address. Delivery problems never raise: they are recorded on the message.
"""

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Case, F, Max, Q, Value, When
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.safestring import mark_safe

from apps.core import integrations
from apps.core.errors import DomainError
from apps.messaging.defaults import SYSTEM_TEMPLATES
from apps.messaging.models import Conversation, Message, MessageTemplate
from apps.messaging.providers import DeliveryResult
from apps.messaging.renderer import BRAND_ACCENT, render_html, render_plain, render_whatsapp
from apps.messaging.types import OutboundMessage
from apps.messaging.variables import LANGUAGES, build_variables, normalize_language

logger = logging.getLogger("housetel.messaging")

SUPPORTED_CHANNELS = ("email", "whatsapp")
WHATSAPP_WINDOW = timedelta(hours=24)
_E164_RE = re.compile(r"^\+\d{7,15}$")
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


class TemplateNotFound(DomainError):
    code = "template_not_found"
    status_code = 400


# Built-in code for free text sent through the contract (e.g. the AI copilot): the body is the caller's
# `context["message"]` and the email subject `context["subject"]` or "Mensaje de <hotel>". It is not a
# template of the editor (there is nothing to edit) and never a lifecycle message.
CUSTOM_MESSAGE = "custom_message"
_CUSTOM_SUBJECT = {"es": "Mensaje de {{property.name}}", "en": "Message from {{property.name}}"}


# --- templates -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedTemplate:
    code: str
    channel: str
    language: str
    subject: str
    body: str
    is_active: bool
    source: str  # property | organization | system
    template_id: UUID | None = None
    name: str = ""
    wa_template_name: str = ""
    wa_template_params: tuple = ()


def _from_row(row: MessageTemplate) -> ResolvedTemplate:
    return ResolvedTemplate(
        code=row.code,
        channel=row.channel,
        language=row.language,
        subject=row.subject,
        body=row.body,
        is_active=row.is_active,
        source=row.scope,
        template_id=row.pk,
        name=row.name,
        wa_template_name=row.wa_template_name,
        wa_template_params=tuple(row.wa_template_params or ()),
    )


def _custom_message_template(channel, language, subject: str = "") -> ResolvedTemplate:
    lang = normalize_language(language)
    return ResolvedTemplate(
        code=CUSTOM_MESSAGE,
        channel=channel,
        language=lang,
        subject=("{{subject}}" if subject else _CUSTOM_SUBJECT[lang]) if channel == "email" else "",
        body="{{message}}",
        is_active=True,
        source="system",
    )


def resolve_template(property, code, channel, language) -> ResolvedTemplate | None:
    """The template a message uses. For each language (requested → hotel default → es → en) the property's
    template wins over the organization's, which wins over the system default; the first hit is returned
    even when inactive (an inactive template switches that channel off). None if the code is unknown."""
    if code == CUSTOM_MESSAGE:
        return _custom_message_template(channel, language)
    rows = MessageTemplate.objects.filter(
        organization_id=property.organization_id, code=code, channel=channel
    ).filter(Q(property=property) | Q(property__isnull=True))
    by_scope = {(row.property_id is not None, row.language): row for row in rows}
    languages = dict.fromkeys(
        [normalize_language(language), normalize_language(property.default_language), "es", "en"]
    )
    for lang in languages:
        row = by_scope.get((True, lang)) or by_scope.get((False, lang))
        if row is not None:
            return _from_row(row)
        default = SYSTEM_TEMPLATES.get((code, channel, lang))
        if default is not None:
            return ResolvedTemplate(
                code=code,
                channel=channel,
                language=lang,
                subject=default["subject"],
                body=default["body"],
                is_active=True,
                source="system",
            )
    return None


# --- addresses and language ----------------------------------------------------------------------------


def _supported_language(value) -> str | None:
    code = str(value or "").strip().lower()[:2]
    return code if code in LANGUAGES else None


def message_language(property, guest=None, reservation=None, language=None) -> str:
    """Explicit language → guest's → reservation's → hotel default → Spanish."""
    for candidate in (
        language,
        getattr(guest, "language", None),
        getattr(reservation, "language", None),
        property.default_language,
    ):
        code = _supported_language(candidate)
        if code:
            return code
    return "es"


def email_address(value) -> str:
    text = str(value or "").strip().lower()
    return text if "@" in text and " " not in text else ""


def whatsapp_address(value, *, region: str | None = None) -> str:
    """E.164 phone for WhatsApp ('' if `value` is not a usable phone). Numbers without a country code are read
    in `region` and then as Colombian, exactly as guest phones are stored (guests.normalization)."""
    from apps.guests.normalization import normalize_phone

    text = str(value or "").strip()
    if not text or "@" in text:
        return ""
    phone = normalize_phone(text, region=region or "CO")
    return phone if _E164_RE.match(phone) else ""


def guest_address(channel: str, guest=None, to=None) -> str:
    """Recipient on `channel`: the explicit `to` when it fits the channel (a str, or a {channel: address}
    dict), else the guest's email / phone."""
    explicit = to.get(channel) if isinstance(to, dict) else to
    region = getattr(guest, "country_of_residence", "") or getattr(guest, "nationality", "") or None
    for candidate in (explicit, getattr(guest, "email" if channel == "email" else "phone", "")):
        address = (
            email_address(candidate) if channel == "email" else whatsapp_address(candidate, region=region)
        )
        if address:
            return address
    return ""


# --- rendering -----------------------------------------------------------------------------------------

_EMAIL_STRINGS = {
    "es": {"powered_by": "Enviado con Housetel"},
    "en": {"powered_by": "Sent with Housetel"},
}


def brand_accent(property) -> str:
    color = str((property.branding or {}).get("primary_color") or "")
    return color if _HEX_COLOR_RE.match(color) else BRAND_ACCENT


def render_email_document(
    property, *, subject: str, body_template: str, variables: dict, language: str
) -> str:
    """The full HTML email: Housetel layout with the hotel's name and accent around the rendered body."""
    lang = normalize_language(language)
    accent = brand_accent(property)
    address_line = ", ".join(part for part in (property.address, property.city) if part)
    contact_line = " · ".join(part for part in (property.phone, property.email) if part)
    text_preview = render_plain(body_template, variables)
    preheader = next((line.strip() for line in text_preview.splitlines()[1:] if line.strip()), "")[:140]
    return render_to_string(
        "messaging/email.html",
        {
            "lang": lang,
            "subject": subject,
            "preheader": preheader,
            "accent": accent,
            "content": mark_safe(render_html(body_template, variables, accent=accent)),  # noqa: S308 - escaped
            "property_name": property.name,
            "property_city": property.city,
            "address_line": address_line,
            "contact_line": contact_line,
            "powered_by": _EMAIL_STRINGS[lang]["powered_by"],
        },
    )


# --- delivery ------------------------------------------------------------------------------------------


def _one_line(text: str, limit: int = 200) -> str:
    return " ".join((text or "").split())[:limit]


def _conversation(property, channel, address, *, guest=None, reservation=None) -> Conversation:
    conversation, created = Conversation.objects.get_or_create(
        property=property,
        channel=channel,
        external_thread_key=address,
        defaults={
            "guest": guest,
            "reservation": reservation,
            "contact_name": guest.full_name if guest is not None else "",
        },
    )
    if created:
        return conversation
    changed = []
    if guest is not None and conversation.guest_id != guest.pk:
        conversation.guest = guest
        changed.append("guest")
    if guest is not None and not conversation.contact_name:
        conversation.contact_name = guest.full_name
        changed.append("contact_name")
    if reservation is not None and conversation.reservation_id != reservation.pk:
        conversation.reservation = reservation
        changed.append("reservation")
    if changed:
        conversation.save(update_fields=[*changed, "updated_at"])
    return conversation


def whatsapp_window_open(conversation, *, now=None) -> bool:
    """WhatsApp only accepts free-form messages within 24 h of the guest's last message."""
    last = conversation.last_inbound_at
    return last is not None and (now or timezone.now()) - last < WHATSAPP_WINDOW


def _call_provider(property, message: Message, conversation, *, html="", wa_template=None) -> DeliveryResult:
    try:
        provider = integrations.get_provider(property, message.channel)
        if message.channel == "email":
            return provider.send_email(
                to=message.recipient, subject=message.subject, text=message.body, html=html
            )
        template = None if whatsapp_window_open(conversation) else wa_template
        return provider.send_whatsapp(to=message.recipient, text=message.body, template=template)
    except Exception as exc:  # a provider bug or outage is recorded on the message, never raised
        logger.exception("Delivery through %s failed", message.channel)
        return DeliveryResult("failed", error=str(exc)[:1000] or type(exc).__name__)


def _touch(conversation: Conversation, message: Message) -> None:
    conversation.last_message_at = message.created_at
    conversation.last_message_preview = _one_line(message.body)
    conversation.last_message_direction = message.direction
    conversation.save(
        update_fields=["last_message_at", "last_message_preview", "last_message_direction", "updated_at"]
    )


def deliver(
    property,
    *,
    channel,
    address,
    body,
    subject="",
    html="",
    guest=None,
    reservation=None,
    template_code="",
    sender_label="",
    sent_by=None,
    ai_generated=False,
    wa_template=None,
    conversation=None,
) -> Message:
    """Record an outbound message in the conversation of `address` and hand it to the channel's provider."""
    conversation = conversation or _conversation(
        property, channel, address, guest=guest, reservation=reservation
    )
    message = Message.objects.create(
        conversation=conversation,
        reservation=reservation,
        direction=Message.Direction.OUT,
        channel=channel,
        sender_label=sender_label or property.name,
        recipient=address,
        subject=subject,
        body=body,
        status=Message.Status.QUEUED,
        template_code=template_code,
        sent_by=sent_by,
        ai_generated=ai_generated,
    )
    result = _call_provider(property, message, conversation, html=html, wa_template=wa_template)
    message.status = result.status
    message.provider_message_id = result.provider_message_id
    message.error = result.error
    message.status_updated_at = timezone.now()
    message.save(update_fields=["status", "provider_message_id", "error", "status_updated_at", "updated_at"])
    _touch(conversation, message)
    return message


# --- inbound -------------------------------------------------------------------------------------------

_STATUS_RANK = {"queued": 0, "sent": 1, "delivered": 2, "read": 3}


def find_guest(property, channel: str, address: str):
    """The organization's guest behind an address (WhatsApp phone or email); with several, the one who stayed
    at this hotel most recently."""
    from apps.guests.models import Guest

    if not address or channel not in SUPPORTED_CHANNELS:
        return None
    lookup = {"phone": address} if channel == "whatsapp" else {"email": address}
    return (
        Guest.objects.filter(organization_id=property.organization_id, merged_into__isnull=True, **lookup)
        .annotate(last_arrival=Max("reservations__checkin_date", filter=Q(reservations__property=property)))
        .order_by(F("last_arrival").desc(nulls_last=True), "-updated_at")
        .first()
    )


def current_reservation(property, guest):
    """The reservation a guest's message is most likely about: in house → next arrival → latest stay."""
    from apps.bookings.models import Reservation

    reservations = (
        Reservation.objects.filter(property=property)
        .filter(Q(booker=guest) | Q(stays__occupants=guest))
        .distinct()
    )
    in_house = reservations.filter(status="checked_in").order_by("-checkin_date").first()
    if in_house is not None:
        return in_house
    upcoming = (
        reservations.filter(status__in=["tentative", "confirmed"], checkout_date__gte=property.business_date)
        .order_by("checkin_date")
        .first()
    )
    if upcoming is not None:
        return upcoming
    return reservations.exclude(status="cancelled").order_by("-checkout_date").first()


def record_inbound_message(
    property,
    *,
    channel,
    body,
    address="",
    guest=None,
    reservation=None,
    contact_name="",
    provider_message_id="",
    subject="",
) -> Message:
    """A guest's message into the conversation of its address (WhatsApp webhook and simulator, web chat
    handoff of the chatbot, OTA messages…): reopens the thread, counts it unread and opens the WhatsApp 24 h
    window. Idempotent by `provider_message_id` (webhooks are retried)."""
    if provider_message_id:
        existing = Message.objects.filter(channel=channel, provider_message_id=provider_message_id).first()
        if existing is not None:
            return existing
    if guest is None:
        guest = find_guest(property, channel, address)
    if reservation is None and guest is not None:
        reservation = current_reservation(property, guest)
    sender = contact_name or (guest.full_name if guest is not None else "") or address
    try:
        with transaction.atomic():
            conversation = _conversation(property, channel, address, guest=guest, reservation=reservation)
            conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
            message = Message.objects.create(
                conversation=conversation,
                reservation=reservation or conversation.reservation,
                direction=Message.Direction.IN,
                channel=channel,
                sender_label=sender[:200],
                subject=subject,
                body=body,
                status=Message.Status.RECEIVED,
                provider_message_id=provider_message_id,
            )
            if contact_name and (guest is None or not conversation.contact_name):
                conversation.contact_name = contact_name[:200]
            conversation.status = Conversation.Status.OPEN
            conversation.unread_count += 1
            conversation.last_inbound_at = message.created_at
            conversation.last_message_at = message.created_at
            conversation.last_message_preview = _one_line(body)
            conversation.last_message_direction = Message.Direction.IN
            conversation.save()
    except IntegrityError:  # the same webhook delivered twice at the same time
        existing = Message.objects.filter(channel=channel, provider_message_id=provider_message_id).first()
        if existing is None:
            raise
        return existing
    return message


def _whatsapp_contact(property, phone: str, profile_name: str):
    from apps.guests.services import upsert_guest
    from apps.guests.types import GuestInput

    first, _, last = (profile_name or "").strip().partition(" ")
    if not first:
        first, last = "Contacto", "WhatsApp"
    return upsert_guest(
        property.organization, GuestInput(first_name=first, last_name=last.strip(), phone=phone)
    )


def receive_whatsapp(property, *, phone, body, profile_name="", provider_message_id="") -> Message:
    """An incoming WhatsApp message (real webhook or simulator): the guest is found by phone in the
    organization or created as a WhatsApp contact (named after the WhatsApp profile when known)."""
    address = whatsapp_address(phone)
    if not address:
        raise DomainError(
            "El número de teléfono no es válido", code="invalid_phone", fields={"phone": ["Inválido"]}
        )
    if provider_message_id:
        existing = Message.objects.filter(channel="whatsapp", provider_message_id=provider_message_id).first()
        if existing is not None:
            return existing
    guest = find_guest(property, "whatsapp", address) or _whatsapp_contact(property, address, profile_name)
    return record_inbound_message(
        property,
        channel="whatsapp",
        address=address,
        body=body,
        guest=guest,
        contact_name=profile_name,
        provider_message_id=provider_message_id,
    )


def apply_status_update(*, channel, provider_message_id, status, error="") -> Message | None:
    """Delivery receipt from a provider (sent → delivered → read, or failed). Receipts arrive out of order: a
    status never moves back. Unknown messages are ignored (None)."""
    message = Message.objects.filter(
        channel=channel, provider_message_id=provider_message_id, direction=Message.Direction.OUT
    ).first()
    if message is None:
        return None
    if status == Message.Status.FAILED:
        if _STATUS_RANK.get(message.status, -1) >= _STATUS_RANK["delivered"]:
            return message
        message.error = (error or message.error)[:2000]
    elif status not in _STATUS_RANK or _STATUS_RANK[status] <= _STATUS_RANK.get(message.status, -1):
        return message
    message.status = status
    message.status_updated_at = timezone.now()
    message.save(update_fields=["status", "error", "status_updated_at", "updated_at"])
    return message


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _inbound_body(item: dict) -> str:
    kind = str(item.get("type") or "")
    content = item.get(kind) if isinstance(item.get(kind), dict) else {}
    if kind == "text":
        return str(content.get("body") or "")
    if kind == "button":
        return str(content.get("text") or "")
    if kind == "interactive":
        reply = content.get("button_reply") or content.get("list_reply") or {}
        return str(reply.get("title") or "[interactive]")
    detail = content.get("caption") or content.get("filename") or content.get("emoji") or ""
    if kind == "location":
        detail = f"{content.get('latitude', '')}, {content.get('longitude', '')}"
    return f"[{kind or 'message'}] {detail}".strip()


def process_whatsapp_webhook(payload: dict, properties: dict) -> dict:
    """Apply a (signature-verified) Cloud API notification. `properties` maps phone_number_id → Property;
    changes for other numbers are ignored. Returns counts."""
    counts = {"messages": 0, "statuses": 0}
    for entry in _as_list(payload.get("entry")):
        for change in _as_list(entry.get("changes") if isinstance(entry, dict) else None):
            value = change.get("value") if isinstance(change, dict) else None
            if not isinstance(value, dict):
                continue
            metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
            prop = properties.get(str(metadata.get("phone_number_id") or ""))
            if prop is None:
                continue
            names = {
                str(contact.get("wa_id")): str((contact.get("profile") or {}).get("name") or "")
                for contact in _as_list(value.get("contacts"))
                if isinstance(contact, dict)
            }
            for item in _as_list(value.get("messages")):
                if not isinstance(item, dict):
                    continue
                sender = str(item.get("from") or "").lstrip("+")
                try:
                    receive_whatsapp(
                        prop,
                        phone=f"+{sender}",
                        body=_inbound_body(item),
                        profile_name=names.get(sender, ""),
                        provider_message_id=str(item.get("id") or ""),
                    )
                except DomainError:
                    logger.warning("Ignored a WhatsApp message with an unusable sender")
                    continue
                counts["messages"] += 1
            for status in _as_list(value.get("statuses")):
                if not isinstance(status, dict):
                    continue
                errors = "; ".join(
                    f"{error.get('code', '')} {error.get('title') or error.get('message') or ''}".strip()
                    for error in _as_list(status.get("errors"))
                    if isinstance(error, dict)
                )
                apply_status_update(
                    channel="whatsapp",
                    provider_message_id=str(status.get("id") or ""),
                    status=str(status.get("status") or ""),
                    error=errors,
                )
                counts["statuses"] += 1
    return counts


ANONYMIZED_LABEL = "Huésped anonimizado"


def erase_guest_conversations(guest_ids) -> int:
    """Habeas Data: erase the personal data of these guests' threads (addresses, names, message texts). The
    threads stay (counts, dates, statuses) so the hotel's history remains coherent. Returns the threads."""
    conversations = list(Conversation.objects.filter(guest_id__in=list(guest_ids)))
    for conversation in conversations:
        conversation.messages.update(
            body="",
            subject="",
            recipient="",
            error="",
            sender_label=Case(
                When(direction=Message.Direction.IN, then=Value(ANONYMIZED_LABEL)), default=F("sender_label")
            ),
            updated_at=timezone.now(),
        )
        conversation.external_thread_key = f"anonymized:{conversation.pk}"
        conversation.contact_name = ""
        conversation.last_message_preview = ""
        conversation.save(
            update_fields=["external_thread_key", "contact_name", "last_message_preview", "updated_at"]
        )
    return len(conversations)


def _outbound(message: Message) -> OutboundMessage:
    return OutboundMessage(
        channel=message.channel,
        to=message.recipient,
        status=message.status,
        subject=message.subject,
        body=message.body,
        template_code=message.template_code,
        provider_message_id=message.provider_message_id,
        error=message.error,
        message_id=message.pk,
    )


def _skipped(channel: str, code: str, reason: str) -> OutboundMessage:
    return OutboundMessage(channel=channel, to="", status="skipped", template_code=code, error=reason)


NO_ADDRESS_REASONS = {
    "email": "El huésped no tiene un correo electrónico",
    "whatsapp": "El huésped no tiene un teléfono válido para WhatsApp",
}


def _wa_template(template: ResolvedTemplate, variables: dict) -> dict | None:
    if not template.wa_template_name:
        return None
    return {
        "name": template.wa_template_name,
        "language": template.language,
        "parameters": [variables.get(name, "") for name in template.wa_template_params],
    }


def send_message(
    *,
    property,
    template_code,
    guest=None,
    reservation=None,
    to=None,
    channels=("email",),
    context=None,
    language=None,
) -> list[OutboundMessage]:
    """Render `template_code` in the guest's language and send it through each channel (email | whatsapp).

    - `guest` defaults to the reservation's booker; `to` (str or {channel: address}) replaces the guest's
      address on the channel it fits. `context` adds or overrides template values (e.g. the payment link).
    - One `OutboundMessage` per channel: `sent`/`delivered`/`failed` (recorded as a `Message`) or `skipped`
      (no address, template or integration switched off; nothing recorded). Never raises for delivery
      problems; raises `TemplateNotFound` (400) when no channel knows `template_code`.
    """
    guest = guest if guest is not None else getattr(reservation, "booker", None)
    lang = message_language(property, guest, reservation, language)
    channels = list(dict.fromkeys(channels or ()))
    if template_code == CUSTOM_MESSAGE:
        if not str((context or {}).get("message") or "").strip():
            raise DomainError(
                "Escribe el texto del mensaje", code="message_required", fields={"message": ["Vacío"]}
            )
        subject = str((context or {}).get("subject") or "").strip()
        templates = {
            channel: _custom_message_template(channel, lang, subject)
            for channel in channels
            if channel in SUPPORTED_CHANNELS
        }
    else:
        templates = {
            channel: resolve_template(property, template_code, channel, lang)
            for channel in channels
            if channel in SUPPORTED_CHANNELS
        }
    if not any(templates.values()):
        raise TemplateNotFound(f"No existe la plantilla «{template_code}»", template_code=template_code)

    values_by_language: dict[str, dict] = {}
    results = []
    for channel in channels:
        template = templates.get(channel)
        if channel not in SUPPORTED_CHANNELS:
            results.append(_skipped(channel, template_code, f"Canal no soportado: {channel}"))
            continue
        if template is None:
            results.append(_skipped(channel, template_code, "No hay plantilla para este canal"))
            continue
        if not template.is_active:
            results.append(_skipped(channel, template_code, "La plantilla está desactivada para este canal"))
            continue
        address = guest_address(channel, guest, to)
        if not address:
            results.append(_skipped(channel, template_code, NO_ADDRESS_REASONS[channel]))
            continue
        if not integrations.get_setting(property, channel).enabled:
            results.append(_skipped(channel, template_code, "La integración de este canal está desactivada"))
            continue
        if template.language not in values_by_language:
            values_by_language[template.language] = build_variables(
                property=property,
                guest=guest,
                reservation=reservation,
                language=template.language,
                context=context,
            )
        variables = values_by_language[template.language]
        if channel == "email":
            subject = _one_line(render_plain(template.subject, variables), 255)
            message = deliver(
                property,
                channel=channel,
                address=address,
                subject=subject,
                body=render_plain(template.body, variables),
                html=render_email_document(
                    property,
                    subject=subject,
                    body_template=template.body,
                    variables=variables,
                    language=template.language,
                ),
                guest=guest,
                reservation=reservation,
                template_code=template_code,
            )
        else:
            message = deliver(
                property,
                channel=channel,
                address=address,
                body=render_whatsapp(template.body, variables),
                guest=guest,
                reservation=reservation,
                template_code=template_code,
                wa_template=_wa_template(template, variables),
            )
        results.append(_outbound(message))
    return results
