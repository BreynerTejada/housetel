"""Serializers of the AI API."""

from rest_framework import serializers

from apps.ai.models import ChatbotConversation, CopilotAction, CopilotMessage, CopilotSession, PropertyFAQ

LANGUAGE_CHOICES = ["es", "en"]


# ---- copilot --------------------------------------------------------------------------------------------


class CopilotMessageSerializer(serializers.ModelSerializer):
    tool_calls = serializers.SerializerMethodField()

    class Meta:
        model = CopilotMessage
        fields = [
            "id",
            "role",
            "content",
            "tool_calls",
            "tool_call_id",
            "name",
            "provider",
            "simulated",
            "created_at",
        ]

    def get_tool_calls(self, message) -> list[dict]:
        # Provider metadata (e.g. Gemini's thought signature) stays on the server.
        return [
            {"id": call.get("id", ""), "name": call.get("name", ""), "arguments": call.get("arguments") or {}}
            for call in message.tool_calls or []
        ]


class CopilotActionSerializer(serializers.ModelSerializer):
    action = serializers.CharField(source="action_code", read_only=True)
    message_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = CopilotAction
        fields = [
            "id",
            "action",
            "summary",
            "details",
            "status",
            "permission",
            "result",
            "error",
            "message_id",
            "created_at",
            "decided_at",
            "executed_at",
        ]
        read_only_fields = fields


class CopilotSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CopilotSession
        fields = ["id", "title", "created_at", "last_message_at"]
        read_only_fields = ["id", "created_at", "last_message_at"]
        extra_kwargs = {"title": {"required": False, "allow_blank": True}}


class CopilotSessionDetailSerializer(CopilotSessionSerializer):
    messages = CopilotMessageSerializer(many=True, read_only=True)
    actions = CopilotActionSerializer(many=True, read_only=True)

    class Meta(CopilotSessionSerializer.Meta):
        fields = [*CopilotSessionSerializer.Meta.fields, "messages", "actions"]


class CopilotAskSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=2000, trim_whitespace=True)
    language = serializers.ChoiceField(choices=LANGUAGE_CHOICES, required=False)


class CopilotTurnSerializer(serializers.Serializer):
    session = CopilotSessionSerializer()
    messages = CopilotMessageSerializer(many=True)
    proposals = CopilotActionSerializer(many=True)


# ---- public chatbot ---------------------------------------------------------------------------------------


class ChatMessageSerializer(serializers.Serializer):
    session_id = serializers.CharField(required=False, allow_blank=True, max_length=64)
    message = serializers.CharField(max_length=1000, trim_whitespace=True)
    language = serializers.ChoiceField(choices=LANGUAGE_CHOICES, required=False, default="es")


class ChatContactSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=120, trim_whitespace=True)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.RegexField(
        r"^[+\d][\d\s().-]{6,39}$",
        required=False,
        allow_blank=True,
        default="",
        error_messages={"invalid": "Teléfono inválido"},
    )
    message = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("phone"):
            raise serializers.ValidationError({"email": ["Déjanos un correo o un teléfono para contactarte"]})
        return attrs


class ChatCardSerializer(serializers.Serializer):
    type = serializers.CharField()
    room_type_id = serializers.CharField()
    room_type_code = serializers.CharField()
    room_type = serializers.CharField()
    rate_plan = serializers.CharField()
    total = serializers.CharField()
    per_night = serializers.CharField()
    currency = serializers.CharField()
    available = serializers.IntegerField()
    nights = serializers.IntegerField()
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    adults = serializers.IntegerField()
    children = serializers.IntegerField()
    url = serializers.CharField()


class ChatEntrySerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["user", "assistant"])
    content = serializers.CharField()
    cards = ChatCardSerializer(many=True)
    at = serializers.DateTimeField(allow_null=True)


class HandoffSerializer(serializers.Serializer):
    requested = serializers.BooleanField()
    contact_needed = serializers.BooleanField()
    contact_received = serializers.BooleanField()


class ChatReplySerializer(serializers.Serializer):
    session_id = serializers.CharField()
    reply = ChatEntrySerializer()
    handoff = HandoffSerializer()


class ChatConfigSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    property = serializers.DictField()
    greeting = serializers.CharField()
    suggestions = serializers.ListField(child=serializers.CharField())
    languages = serializers.ListField(child=serializers.CharField())
    session_id = serializers.CharField(allow_null=True)
    messages = ChatEntrySerializer(many=True)
    handoff = HandoffSerializer(allow_null=True)


# ---- onboarding -------------------------------------------------------------------------------------------


class OnboardingProposeSerializer(serializers.Serializer):
    description = serializers.CharField(required=False, allow_blank=True, max_length=5000, default="")
    website_url = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class OnboardingApplySerializer(serializers.Serializer):
    proposal = serializers.DictField()


class OnboardingProposalSerializer(serializers.Serializer):
    proposal = serializers.DictField()
    warnings = serializers.ListField(child=serializers.CharField())
    simulated = serializers.BooleanField()
    provider = serializers.CharField()
    website = serializers.DictField(allow_null=True)


class OnboardingNormalizedSerializer(serializers.Serializer):
    proposal = serializers.DictField()
    warnings = serializers.ListField(child=serializers.CharField())


class OnboardingSummarySerializer(serializers.Serializer):
    room_types = serializers.ListField(child=serializers.DictField())
    rooms_created = serializers.IntegerField()
    rate_plans = serializers.ListField(child=serializers.CharField())
    extras = serializers.ListField(child=serializers.CharField())
    profile_updated = serializers.ListField(child=serializers.CharField())
    links = serializers.DictField()


# ---- draft replies ----------------------------------------------------------------------------------------


class DraftReplyRequestSerializer(serializers.Serializer):
    guest_message = serializers.CharField(max_length=2000, trim_whitespace=True)
    reservation_code = serializers.CharField(required=False, allow_blank=True, max_length=20, default="")
    language = serializers.ChoiceField(
        choices=LANGUAGE_CHOICES, required=False, allow_null=True, default=None
    )
    tone = serializers.ChoiceField(
        choices=["friendly", "formal", "brief"], required=False, default="friendly"
    )


class DraftReplySerializer(serializers.Serializer):
    text = serializers.CharField()
    simulated = serializers.BooleanField()
    language = serializers.CharField()


# ---- settings, FAQ, usage, chatbot conversations ----------------------------------------------------------


class GreetingField(serializers.JSONField):
    """`{"es": str, "en": str}` (each at most 300 characters)."""

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(LANGUAGE_CHOICES):
            raise serializers.ValidationError('Debe ser un objeto {"es": ..., "en": ...}')
        clean = {}
        for lang in LANGUAGE_CHOICES:
            value = data.get(lang) or ""
            if not isinstance(value, str) or len(value) > 300:
                raise serializers.ValidationError("Cada saludo es un texto de máximo 300 caracteres")
            clean[lang] = value.strip()
        return clean


class AISettingsUpdateSerializer(serializers.Serializer):
    copilot_enabled = serializers.BooleanField(required=False)
    chatbot_enabled = serializers.BooleanField(required=False)
    draft_replies_enabled = serializers.BooleanField(required=False)
    chatbot_greeting = GreetingField(required=False)
    mode = serializers.ChoiceField(choices=["real", "simulated"], required=False)
    provider = serializers.ChoiceField(choices=["gemini", "claude"], required=False)
    model = serializers.CharField(required=False, allow_blank=True, max_length=100)


class AISettingsSerializer(serializers.Serializer):
    copilot_enabled = serializers.BooleanField()
    chatbot_enabled = serializers.BooleanField()
    draft_replies_enabled = serializers.BooleanField()
    chatbot_greeting = serializers.DictField()
    provider = serializers.DictField()


class PropertyFAQSerializer(serializers.ModelSerializer):
    question = serializers.CharField(max_length=300, trim_whitespace=True)
    answer = serializers.CharField(max_length=2000, trim_whitespace=True)

    class Meta:
        model = PropertyFAQ
        fields = ["id", "question", "answer", "language", "sort", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ChatbotConversationSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    messages_count = serializers.SerializerMethodField()
    reservation = serializers.SerializerMethodField()
    contact = serializers.SerializerMethodField()

    class Meta:
        model = ChatbotConversation
        fields = [
            "id",
            "language",
            "handoff_requested",
            "handoff_reason",
            "handoff_at",
            "handoff_resolved_at",
            "contact",
            "reservation",
            "messages_count",
            "last_message",
            "last_message_at",
            "created_at",
        ]

    def get_last_message(self, conversation) -> str:
        return next(
            (
                item.get("content", "")
                for item in reversed(conversation.messages or [])
                if item.get("role") == "user"
            ),
            "",
        )[:300]

    def get_messages_count(self, conversation) -> int:
        return len(conversation.messages or [])

    def get_reservation(self, conversation) -> dict | None:
        reservation = conversation.reservation
        return {"id": str(reservation.pk), "code": reservation.code} if reservation else None

    def get_contact(self, conversation) -> dict:
        """What the guest left in the chat or, in the guest portal, the booker of the reservation
        (`from: "reservation"`)."""
        from apps.ai.chatbot import _known_contact

        return _known_contact(conversation)


class ChatbotConversationDetailSerializer(ChatbotConversationSerializer):
    messages = serializers.SerializerMethodField()

    class Meta(ChatbotConversationSerializer.Meta):
        fields = [*ChatbotConversationSerializer.Meta.fields, "messages"]

    def get_messages(self, conversation) -> list[dict]:
        return [
            {
                "role": item.get("role"),
                "content": item.get("content", ""),
                "cards": item.get("cards") or [],
                "at": item.get("at"),
            }
            for item in conversation.messages or []
        ]


class CopilotStatusSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    effective = serializers.ChoiceField(choices=["real", "simulated"])
    provider_label = serializers.CharField()
    suggestions = serializers.ListField(child=serializers.CharField())
