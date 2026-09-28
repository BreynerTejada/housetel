"""Models of `ai` (plan C9): settings, usage, copilot sessions/actions, chatbot FAQ and conversations."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel, Property

LANGUAGES = [("es", "Español"), ("en", "English")]


class AISettings(BaseModel):
    """AI features of a property. The provider and its mode live in IntegrationSetting(kind="llm")."""

    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="ai_settings")
    copilot_enabled = models.BooleanField(default=True)
    chatbot_enabled = models.BooleanField(default=True)
    draft_replies_enabled = models.BooleanField(default=True)
    chatbot_greeting = models.JSONField(default=dict, blank=True)  # {"es": "...", "en": "..."}

    class Meta:
        verbose_name = "ajustes de IA"
        verbose_name_plural = "ajustes de IA"

    def __str__(self):
        return f"IA · {self.property}"


class AIUsage(BaseModel):
    """One LLM call (a failed attempt and its simulated fallback are two rows)."""

    property = models.ForeignKey(
        Property, null=True, blank=True, on_delete=models.CASCADE, related_name="ai_usage"
    )
    feature = models.CharField(max_length=40, default="general")
    provider = models.CharField(max_length=20)  # gemini | claude | simulated
    model = models.CharField(max_length=100, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    success = models.BooleanField(default=True)
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["property", "created_at"], name="ai_usage_property_created")]

    def __str__(self):
        return f"{self.feature} · {self.provider} · {'ok' if self.success else 'error'}"


class CopilotSession(BaseModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="copilot_sessions")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="copilot_sessions"
    )
    title = models.CharField(max_length=200, blank=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(fields=["property", "user", "last_message_at"], name="ai_copilot_session_recent")
        ]

    def __str__(self):
        return self.title or f"Sesión {self.pk}"


class CopilotMessage(BaseModel):
    class Role(models.TextChoices):
        USER = "user", "Usuario"
        ASSISTANT = "assistant", "Asistente"
        TOOL = "tool", "Herramienta"

    session = models.ForeignKey(CopilotSession, on_delete=models.CASCADE, related_name="messages")
    position = models.PositiveIntegerField()
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField(blank=True)
    tool_calls = models.JSONField(default=list, blank=True)  # [{id, name, arguments, meta?}]
    tool_call_id = models.CharField(max_length=100, blank=True)
    name = models.CharField(max_length=80, blank=True)  # tool name of a `tool` message
    provider = models.CharField(max_length=20, blank=True)
    simulated = models.BooleanField(default=False)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["session", "position"], name="ai_copilot_message_position")
        ]

    def __str__(self):
        return f"{self.role}: {self.content[:40]}"


class CopilotAction(BaseModel):
    """An action the copilot proposed; it only runs when the user confirms it."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Propuesta"
        EXECUTED = "executed", "Ejecutada"
        REJECTED = "rejected", "Rechazada"
        FAILED = "failed", "Falló"

    session = models.ForeignKey(CopilotSession, on_delete=models.CASCADE, related_name="actions")
    message = models.ForeignKey(
        CopilotMessage, null=True, blank=True, on_delete=models.SET_NULL, related_name="actions"
    )
    action_code = models.CharField(max_length=40)
    params = models.JSONField(default=dict)
    summary = models.CharField(max_length=500)
    details = models.JSONField(default=dict, blank=True)  # what the proposal card shows
    permission = models.CharField(max_length=60)  # checked again when the user confirms
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PROPOSED)
    result = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.action_code} · {self.status}"


class PropertyFAQ(BaseModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="faqs")
    question = models.CharField(max_length=300)
    answer = models.TextField()
    language = models.CharField(max_length=2, choices=LANGUAGES, default="es")
    sort = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["language", "sort", "created_at"]
        verbose_name = "pregunta frecuente"
        verbose_name_plural = "preguntas frecuentes"

    def __str__(self):
        return self.question


class ChatbotConversation(BaseModel):
    """A conversation of the public chatbot (website, booking engine or guest portal)."""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="chatbot_conversations")
    session_id = models.CharField(max_length=64)
    reservation = models.ForeignKey(
        "bookings.Reservation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    language = models.CharField(max_length=2, choices=LANGUAGES, default="es")
    messages = models.JSONField(default=list, blank=True)  # [{role, content, at, cards?}]
    handoff_requested = models.BooleanField(default=False)
    handoff_reason = models.CharField(max_length=300, blank=True)
    handoff_at = models.DateTimeField(null=True, blank=True)
    handoff_resolved_at = models.DateTimeField(null=True, blank=True)
    contact = models.JSONField(default=dict, blank=True)  # {name, email, phone, message}
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["property", "session_id"], name="ai_chatbot_conversation_session")
        ]

    def __str__(self):
        return f"Chat {self.session_id[:8]} · {self.property}"
