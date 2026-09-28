"""Unified inbox actions of the staff (plan C6): reply on the conversation's channel, internal notes, read,
assignment, close/reopen, and writing to a guest from a reservation or profile.

Staff text goes through the same safe renderer as templates: `{{variables}}` of the conversation's guest and
reservation are filled in, `**bold**` and `[label](url)` become WhatsApp/email formatting, values stay data.
"""

from apps.core.errors import ConflictError, DomainError
from apps.messaging.models import Conversation, Message
from apps.messaging.renderer import render_plain, render_whatsapp
from apps.messaging.services import (
    NO_ADDRESS_REASONS,
    SUPPORTED_CHANNELS,
    _one_line,
    deliver,
    guest_address,
    message_language,
    render_email_document,
    send_message,
)
from apps.messaging.variables import build_variables

# Threads answered on their own channel. A web-chat thread is the chatbot's hand-off (C9): the widget never
# reads staff answers, so the guest is written by email or WhatsApp instead (`send_to_guest`); OTA threads are
# answered in the channel's extranet. Both still take internal notes.
REPLY_CHANNELS = ("email", "whatsapp")
ANONYMIZED_PREFIX = "anonymized:"
WHATSAPP_MAX_LENGTH = 4096  # Cloud API limit of a text message body

_DEFAULT_SUBJECT = {"es": "Mensaje de {name}", "en": "Message from {name}"}


def _check_whatsapp_length(text: str) -> None:
    if len(text) > WHATSAPP_MAX_LENGTH:
        raise DomainError(
            f"WhatsApp admite hasta {WHATSAPP_MAX_LENGTH} caracteres por mensaje",
            code="message_too_long",
            fields={"body": [f"Máximo {WHATSAPP_MAX_LENGTH} caracteres"]},
        )


def default_subject(property, language: str) -> str:
    return _DEFAULT_SUBJECT.get(language, _DEFAULT_SUBJECT["es"]).format(name=property.name)


def author_label(user) -> str:
    return (getattr(user, "full_name", "") or getattr(user, "email", "") or "")[:200]


def _reply_subject(conversation, language: str) -> str:
    last = (
        conversation.messages.exclude(subject="")
        .order_by("-created_at")
        .values_list("subject", flat=True)
        .first()
    )
    if not last:
        return default_subject(conversation.property, language)
    return last if last.lower().startswith("re:") else _one_line(f"Re: {last}", 255)


def mark_read(conversation: Conversation) -> Conversation:
    if conversation.unread_count:
        conversation.unread_count = 0
        conversation.save(update_fields=["unread_count", "updated_at"])
    return conversation


def add_note(conversation: Conversation, *, body: str, author) -> Message:
    """An internal note: seen by the staff only, never sent, and it does not answer the guest (the thread
    keeps its unread count and preview)."""
    return Message.objects.create(
        conversation=conversation,
        reservation=conversation.reservation,
        direction=Message.Direction.OUT,
        channel=Message.Channel.INTERNAL_NOTE,
        sender_label=author_label(author),
        body=body,
        status=Message.Status.SENT,
        sent_by=author,
    )


def reply(
    conversation: Conversation,
    *,
    body: str,
    author,
    subject: str = "",
    template_code: str = "",
    ai_generated: bool = False,
) -> Message:
    """Answer the guest on the conversation's channel. Delivery problems are recorded on the message."""
    if conversation.channel not in REPLY_CHANNELS:
        raise ConflictError(
            "Esta conversación no se responde desde aquí: escríbele al huésped por correo o WhatsApp",
            code="channel_not_supported",
        )
    address = conversation.external_thread_key
    if not address or address.startswith(ANONYMIZED_PREFIX):
        raise ConflictError(
            "Los datos de contacto de esta conversación fueron eliminados", code="conversation_anonymized"
        )
    prop, guest, reservation = conversation.property, conversation.guest, conversation.reservation
    language = message_language(prop, guest, reservation)
    variables = build_variables(property=prop, guest=guest, reservation=reservation, language=language)
    common = {
        "guest": guest,
        "reservation": reservation,
        "template_code": template_code,
        "sender_label": author_label(author),
        "sent_by": author,
        "ai_generated": ai_generated,
        "conversation": conversation,
    }
    if conversation.channel == "email":
        subject = _one_line(render_plain(subject, variables), 255) if subject.strip() else ""
        subject = subject or _reply_subject(conversation, language)
        message = deliver(
            prop,
            channel="email",
            address=address,
            subject=subject,
            body=render_plain(body, variables),
            html=render_email_document(
                prop, subject=subject, body_template=body, variables=variables, language=language
            ),
            **common,
        )
    else:
        text = render_whatsapp(body, variables)
        _check_whatsapp_length(text)
        message = deliver(prop, channel="whatsapp", address=address, body=text, **common)
    mark_read(conversation)
    return message


def assign(conversation: Conversation, user) -> Conversation:
    """Assign the thread to an active member with access to its hotel (`None` = nobody)."""
    if user is not None and not is_member_of(user, conversation.property):
        raise DomainError(
            "Solo puedes asignarla a alguien del equipo de este hotel",
            code="invalid_user",
            fields={"user_id": ["Inválido"]},
        )
    conversation.assigned_to = user
    conversation.save(update_fields=["assigned_to", "updated_at"])
    return conversation


def is_member_of(user, prop) -> bool:
    from apps.accounts.models import Membership

    membership = Membership.objects.filter(
        user=user, organization_id=prop.organization_id, is_active=True
    ).first()
    return membership is not None and (
        membership.all_properties or membership.properties.filter(pk=prop.pk).exists()
    )


def set_status(conversation: Conversation, status: str) -> Conversation:
    if conversation.status != status:
        conversation.status = status
        conversation.save(update_fields=["status", "updated_at"])
    return conversation


def send_to_guest(
    prop,
    *,
    channel: str,
    author,
    guest=None,
    reservation=None,
    to=None,
    template_code: str = "",
    subject: str = "",
    body: str = "",
) -> Message:
    """Write to a guest (starts or continues the conversation of their address on `channel`): a template
    (`send_message`) or free text (rendered with the guest's and reservation's values)."""
    if channel not in SUPPORTED_CHANNELS:
        raise DomainError(
            "Canal no soportado", code="validation_error", fields={"channel": ["Canal no soportado"]}
        )
    guest = guest if guest is not None else getattr(reservation, "booker", None)
    if template_code:
        (result,) = send_message(
            property=prop,
            template_code=template_code,
            guest=guest,
            reservation=reservation,
            to=to,
            channels=(channel,),
        )
        if result.message_id is None:  # skipped: nothing was recorded
            code = "no_address" if result.error == NO_ADDRESS_REASONS.get(channel) else "not_sent"
            raise DomainError(result.error or "El mensaje no se envió", code=code)
        message = Message.objects.get(pk=result.message_id)
        message.sent_by = author
        message.save(update_fields=["sent_by", "updated_at"])
        return message
    address = guest_address(channel, guest, to)
    if not address:
        raise DomainError(NO_ADDRESS_REASONS[channel], code="no_address")
    language = message_language(prop, guest, reservation)
    variables = build_variables(property=prop, guest=guest, reservation=reservation, language=language)
    common = {
        "guest": guest,
        "reservation": reservation,
        "sender_label": author_label(author),
        "sent_by": author,
    }
    if channel == "email":
        subject = (
            _one_line(render_plain(subject, variables), 255)
            if subject.strip()
            else default_subject(prop, language)
        )
        return deliver(
            prop,
            channel="email",
            address=address,
            subject=subject,
            body=render_plain(body, variables),
            html=render_email_document(
                prop, subject=subject, body_template=body, variables=variables, language=language
            ),
            **common,
        )
    text = render_whatsapp(body, variables)
    _check_whatsapp_length(text)
    return deliver(prop, channel="whatsapp", address=address, body=text, **common)
