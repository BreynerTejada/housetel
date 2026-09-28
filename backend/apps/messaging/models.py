"""Messaging (plan C6): templates, conversations (unified inbox), messages and the guest-lifecycle rules.

- Templates resolve property → organization → system default (`apps.messaging.defaults`), per channel and
  language. An inactive template switches its channel off for that code (nothing is sent).
- One conversation per (property, channel, address): a WhatsApp chat is one phone number, an email thread one
  address. It points to the guest and to the reservation of its latest message.
- `LifecycleDispatch` makes every automatic lifecycle message idempotent: one row per (reservation, event).
"""

import builtins
from datetime import time

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.fields import json_field
from apps.core.models import BaseModel, Organization, Property

USER_MODEL = settings.AUTH_USER_MODEL


class Language(models.TextChoices):
    ES = "es", "Español"
    EN = "en", "English"


class TemplateChannel(models.TextChoices):
    EMAIL = "email", "Email"
    WHATSAPP = "whatsapp", "WhatsApp"


class ConversationChannel(models.TextChoices):
    EMAIL = "email", "Email"
    WHATSAPP = "whatsapp", "WhatsApp"
    WEB_CHAT = "web_chat", "Chat web"
    OTA = "ota", "OTA"


class MessageChannel(models.TextChoices):
    EMAIL = "email", "Email"
    WHATSAPP = "whatsapp", "WhatsApp"
    WEB_CHAT = "web_chat", "Chat web"
    OTA = "ota", "OTA"
    INTERNAL_NOTE = "internal_note", "Nota interna"


class LifecycleEvent(models.TextChoices):
    CONFIRMATION = "confirmation", "Confirmación"
    PRE_ARRIVAL = "pre_arrival", "Pre-llegada"
    ARRIVAL_DAY = "arrival_day", "Día de llegada"
    POST_STAY = "post_stay", "Post-estancia"
    PAYMENT_REMINDER = "payment_reminder", "Recordatorio de pago"
    CANCELLATION = "cancellation", "Cancelación"


class MessageTemplate(BaseModel):
    Channel = TemplateChannel

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="message_templates")
    # null = the template of the whole organization; set = override for one property.
    property = models.ForeignKey(
        Property, null=True, blank=True, on_delete=models.CASCADE, related_name="message_templates"
    )
    code = models.SlugField(max_length=64)  # confirmation, pre_arrival, …, payment_link, or a custom code
    name = models.CharField(max_length=120, blank=True)  # label shown for custom codes
    channel = models.CharField(max_length=10, choices=TemplateChannel.choices)
    language = models.CharField(max_length=2, choices=Language.choices, default=Language.ES)
    subject = models.CharField(max_length=255, blank=True)  # email only
    body = models.TextField()
    is_active = models.BooleanField(default=True)
    # WhatsApp outside the 24 h customer-service window only accepts a template approved by Meta: its name and
    # the variables that fill its body parameters {{1}}, {{2}}… in order.
    wa_template_name = models.CharField(max_length=512, blank=True)
    wa_template_params = json_field(default=list)
    updated_by = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["code", "channel", "language"]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "code", "channel", "language"],
                condition=Q(property__isnull=False),
                name="msg_template_property_unique",
            ),
            models.UniqueConstraint(
                fields=["organization", "code", "channel", "language"],
                condition=Q(property__isnull=True),
                name="msg_template_org_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {self.channel} · {self.language}"

    @builtins.property  # the `property` FK shadows the builtin inside the class body
    def scope(self) -> str:
        return "organization" if self.property_id is None else "property"


class Conversation(BaseModel):
    Channel = ConversationChannel

    class Status(models.TextChoices):
        OPEN = "open", "Abierta"
        CLOSED = "closed", "Cerrada"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="conversations")
    guest = models.ForeignKey(
        "guests.Guest", null=True, blank=True, on_delete=models.SET_NULL, related_name="conversations"
    )
    reservation = models.ForeignKey(
        "bookings.Reservation", null=True, blank=True, on_delete=models.SET_NULL, related_name="conversations"
    )
    channel = models.CharField(max_length=20, choices=ConversationChannel.choices)
    # The guest's address on the channel: E.164 phone (WhatsApp), lowercase email, chat session id…
    external_thread_key = models.CharField(max_length=255, blank=True)
    contact_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    last_message_at = models.DateTimeField(null=True, blank=True)
    last_message_preview = models.CharField(max_length=200, blank=True)
    last_message_direction = models.CharField(max_length=3, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)  # opens the WhatsApp 24 h window
    unread_count = models.PositiveIntegerField(default=0)
    assigned_to = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["property", "channel", "external_thread_key"],
                condition=~Q(external_thread_key=""),
                name="conversation_thread_unique",
            )
        ]
        indexes = [models.Index(fields=["property", "-last_message_at"], name="conversation_recent_idx")]

    def __str__(self) -> str:
        return f"{self.channel}: {self.contact_name or self.external_thread_key}"


class Message(BaseModel):
    Channel = MessageChannel

    class Direction(models.TextChoices):
        IN = "in", "Entrante"
        OUT = "out", "Saliente"

    class Status(models.TextChoices):
        QUEUED = "queued", "En cola"
        SENT = "sent", "Enviado"
        DELIVERED = "delivered", "Entregado"
        READ = "read", "Leído"
        FAILED = "failed", "Fallido"
        RECEIVED = "received", "Recibido"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    reservation = models.ForeignKey(
        "bookings.Reservation", null=True, blank=True, on_delete=models.SET_NULL, related_name="messages"
    )
    direction = models.CharField(max_length=3, choices=Direction.choices)
    channel = models.CharField(max_length=20, choices=MessageChannel.choices)
    sender_label = models.CharField(max_length=200, blank=True)
    recipient = models.CharField(max_length=255, blank=True)  # outbound: email address or E.164 phone
    subject = models.CharField(max_length=255, blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    provider_message_id = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    template_code = models.CharField(max_length=64, blank=True)
    sent_by = models.ForeignKey(
        USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    ai_generated = models.BooleanField(default=False)
    status_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["channel", "provider_message_id"],
                condition=~Q(provider_message_id=""),
                name="message_provider_id_unique",
            )
        ]
        indexes = [models.Index(fields=["conversation", "created_at"], name="message_thread_idx")]

    def __str__(self) -> str:
        return f"{self.direction} {self.channel} {self.status}"


class LifecycleRule(BaseModel):
    Event = LifecycleEvent

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="lifecycle_rules")
    event = models.CharField(max_length=20, choices=LifecycleEvent.choices)
    enabled = models.BooleanField(default=True)
    # pre_arrival: days before check-in · post_stay: days after check-out · payment_reminder: arrival within
    # this many days · confirmation / arrival_day / cancellation: unused (0).
    days_offset = models.PositiveSmallIntegerField(default=0)
    channels = json_field(default=list)  # ["email", "whatsapp"]
    template_code = models.SlugField(max_length=64)
    send_after = models.TimeField(default=time(9, 0))  # scheduled events go out from this local time

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["property", "event"], name="lifecycle_rule_unique")]

    def __str__(self) -> str:
        return f"{self.event} ({'on' if self.enabled else 'off'})"


class LifecycleDispatch(BaseModel):
    class Status(models.TextChoices):
        SENT = "sent", "Enviado"
        PARTIAL = "partial", "Parcial"
        FAILED = "failed", "Fallido"
        SKIPPED = "skipped", "Omitido"

    reservation = models.ForeignKey(
        "bookings.Reservation", on_delete=models.CASCADE, related_name="lifecycle_dispatches"
    )
    event = models.CharField(max_length=20, choices=LifecycleEvent.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SENT)
    channels = json_field(default=list)
    detail = models.CharField(max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["reservation", "event"], name="lifecycle_dispatch_unique")
        ]

    def __str__(self) -> str:
        return f"{self.event} → {self.status}"
