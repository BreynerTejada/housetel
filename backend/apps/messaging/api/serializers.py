"""Serializers of the staff messaging API (`/api/v1/messaging/`)."""

from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.i18n import t
from apps.messaging.defaults import EVENTS, SCHEDULED_EVENTS, SYSTEM_CODES
from apps.messaging.editor import (
    CATALOG,
    CHANNELS,
    CODE_RE,
    LANGUAGES,
    MAX_BODY,
    WA_TEMPLATE_NAME_RE,
    code_label,
    unknown_message,
)
from apps.messaging.inbox import ANONYMIZED_PREFIX
from apps.messaging.models import Conversation, LifecycleRule, Message, MessageTemplate
from apps.messaging.renderer import unknown_variables
from apps.messaging.services import CUSTOM_MESSAGE, resolve_template, whatsapp_window_open

MAX_OFFSET_DAYS = 60
INACTIVE_STAYS = ("cancelled", "no_show")


@extend_schema_field(OpenApiTypes.STR)
class PlainChoiceField(serializers.ChoiceField):
    """Validates like a ChoiceField, documented as a plain string: `status`, `channel`, `language`… exist in
    other apps with other choices, and drf-spectacular would hoist them into colliding shared enums."""


class MessagingModelSerializer(serializers.ModelSerializer):
    serializer_choice_field = PlainChoiceField


def money(value) -> str:
    return f"{Decimal(value or 0):.2f}"


# --- conversations -------------------------------------------------------------------------------------


class MessagingUserRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.EmailField()


class MessagingGuestRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.CharField()
    phone = serializers.CharField()
    language = serializers.CharField()
    is_vip = serializers.BooleanField()


class MessagingReservationRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.CharField()
    checkin_date = serializers.DateField()
    checkout_date = serializers.DateField()


class ConversationReservationSerializer(MessagingReservationRefSerializer):
    room = serializers.SerializerMethodField()

    def get_room(self, obj) -> str:
        """Room (and bed) of the reservation, as its key tag: the first active stay with a unit assigned.
        Reads `stays` prefetched with their room and bed."""
        stays = sorted(obj.stays.all(), key=lambda stay: (stay.status in INACTIVE_STAYS, stay.checkin_date))
        for stay in stays:
            if stay.room_id is not None:
                return f"{stay.room.number} · {stay.bed.label}" if stay.bed_id else stay.room.number
        return ""


class ConversationSerializer(MessagingModelSerializer):
    address = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    guest = MessagingGuestRefSerializer(allow_null=True, read_only=True)
    reservation = ConversationReservationSerializer(allow_null=True, read_only=True)
    assigned_to = MessagingUserRefSerializer(allow_null=True, read_only=True)
    whatsapp_window_open = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "channel",
            "status",
            "contact_name",
            "address",
            "display_name",
            "guest",
            "reservation",
            "assigned_to",
            "last_message_at",
            "last_message_preview",
            "last_message_direction",
            "last_inbound_at",
            "unread_count",
            "whatsapp_window_open",
            "created_at",
        ]
        read_only_fields = fields

    def get_address(self, obj) -> str:
        key = obj.external_thread_key
        return "" if key.startswith(ANONYMIZED_PREFIX) else key

    def get_display_name(self, obj) -> str:
        if obj.guest_id is not None:
            return obj.guest.full_name
        return obj.contact_name or self.get_address(obj)

    def get_whatsapp_window_open(self, obj) -> bool | None:
        return whatsapp_window_open(obj) if obj.channel == Conversation.Channel.WHATSAPP else None


class GuestContextSerializer(MessagingGuestRefSerializer):
    first_name = serializers.CharField()
    nationality = serializers.CharField()
    country_of_residence = serializers.CharField()


class ReservationContextSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.CharField()
    source = serializers.CharField()
    checkin_date = serializers.DateField()
    checkout_date = serializers.DateField()
    nights = serializers.IntegerField()
    adults = serializers.IntegerField()
    children = serializers.IntegerField()
    currency = serializers.CharField()
    total_amount = serializers.CharField()
    balance = serializers.CharField()
    room_types = serializers.ListField(child=serializers.CharField())
    rooms = serializers.ListField(child=serializers.CharField())


class ContextSerializer(serializers.Serializer):
    guest = GuestContextSerializer(allow_null=True)
    reservation = ReservationContextSerializer(allow_null=True)


def reservation_context(reservation, language: str) -> dict:
    from apps.finance.services import reservation_balance

    stays = list(
        reservation.stays.select_related("room_type", "room", "bed").order_by("checkin_date", "created_at")
    )
    active = [stay for stay in stays if stay.status not in ("cancelled", "no_show")] or stays
    rooms = []
    for stay in active:
        if stay.room_id is not None:
            rooms.append(f"{stay.room.number} · {stay.bed.label}" if stay.bed_id else stay.room.number)
    return {
        "id": reservation.pk,
        "code": reservation.code,
        "status": reservation.status,
        "source": reservation.source,
        "checkin_date": reservation.checkin_date,
        "checkout_date": reservation.checkout_date,
        "nights": (reservation.checkout_date - reservation.checkin_date).days,
        "adults": reservation.adults,
        "children": reservation.children,
        "currency": reservation.currency,
        "total_amount": money(reservation.total_amount),
        "balance": money(reservation_balance(reservation)),
        "room_types": list(dict.fromkeys(t(stay.room_type.name, language) for stay in active)),
        "rooms": list(dict.fromkeys(rooms)),
    }


class ConversationDetailSerializer(ConversationSerializer):
    context = serializers.SerializerMethodField()

    class Meta(ConversationSerializer.Meta):
        fields = [*ConversationSerializer.Meta.fields, "context"]
        read_only_fields = fields

    @extend_schema_field(ContextSerializer)
    def get_context(self, obj):
        language = (
            getattr(self.context.get("request").user, "language", "es")
            if self.context.get("request")
            else "es"
        )
        guest = obj.guest
        return {
            "guest": None
            if guest is None
            else {
                "id": guest.pk,
                "full_name": guest.full_name,
                "first_name": guest.first_name,
                "email": guest.email,
                "phone": guest.phone,
                "language": guest.language,
                "is_vip": guest.is_vip,
                "nationality": guest.nationality,
                "country_of_residence": guest.country_of_residence,
            },
            "reservation": None
            if obj.reservation is None
            else reservation_context(obj.reservation, language),
        }


class MessageSerializer(MessagingModelSerializer):
    sent_by = MessagingUserRefSerializer(allow_null=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "direction",
            "channel",
            "sender_label",
            "recipient",
            "subject",
            "body",
            "status",
            "error",
            "template_code",
            "ai_generated",
            "sent_by",
            "created_at",
            "status_updated_at",
        ]
        read_only_fields = fields


class MessagePageSerializer(serializers.Serializer):
    results = MessageSerializer(many=True)
    has_more = serializers.BooleanField()


class ReplySerializer(serializers.Serializer):
    body = serializers.CharField(max_length=MAX_BODY["email"], trim_whitespace=True)
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    internal = serializers.BooleanField(required=False, default=False)
    template_code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    ai_generated = serializers.BooleanField(required=False, default=False)


class AssignSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(allow_null=True)


class UnreadCountSerializer(serializers.Serializer):
    conversations = serializers.IntegerField()
    messages = serializers.IntegerField()


class SendSerializer(serializers.Serializer):
    channel = PlainChoiceField(choices=CHANNELS)
    reservation_id = serializers.UUIDField(required=False, allow_null=True)
    guest_id = serializers.UUIDField(required=False, allow_null=True)
    to = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    template_code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    body = serializers.CharField(max_length=MAX_BODY["email"], required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if not (attrs.get("reservation_id") or attrs.get("guest_id") or attrs.get("to")):
            raise serializers.ValidationError({"guest_id": ["Indica el huésped, la reserva o la dirección"]})
        if not attrs["template_code"] and not attrs["body"].strip():
            raise serializers.ValidationError({"body": ["Escribe el mensaje o elige una plantilla"]})
        return attrs


class SendResultSerializer(serializers.Serializer):
    message = MessageSerializer()
    conversation_id = serializers.UUIDField()


class RecipientGuestSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_blank=True)
    language = serializers.CharField(allow_blank=True)


class RecipientAddressesSerializer(serializers.Serializer):
    email = serializers.CharField(allow_blank=True)
    whatsapp = serializers.CharField(allow_blank=True)


class RecipientSerializer(serializers.Serializer):
    guest = RecipientGuestSerializer(allow_null=True)
    reservation = MessagingReservationRefSerializer(allow_null=True)
    language = serializers.CharField()
    addresses = RecipientAddressesSerializer()


# --- templates -----------------------------------------------------------------------------------------


class EffectiveTemplateSerializer(serializers.Serializer):
    key = serializers.CharField()
    code = serializers.CharField()
    label = serializers.DictField(child=serializers.CharField())
    is_system_code = serializers.BooleanField()
    channel = serializers.CharField()
    language = serializers.CharField()
    source = serializers.CharField()
    id = serializers.UUIDField(allow_null=True)
    subject = serializers.CharField(allow_blank=True)
    body = serializers.CharField()
    is_active = serializers.BooleanField()
    wa_template_name = serializers.CharField(allow_blank=True)
    wa_template_params = serializers.ListField(child=serializers.CharField())
    updated_at = serializers.DateTimeField(allow_null=True)
    organization_template_id = serializers.UUIDField(allow_null=True)
    property_template_id = serializers.UUIDField(allow_null=True)


class TemplateSerializer(MessagingModelSerializer):
    """A template row (organization- or property-level override). `code`, `channel`, `language` and `scope`
    are fixed once created."""

    scope = PlainChoiceField(choices=["property", "organization"], default="property")
    label = serializers.SerializerMethodField()
    wa_template_params = serializers.ListField(
        child=serializers.CharField(max_length=64), required=False, default=list, max_length=20
    )

    class Meta:
        model = MessageTemplate
        fields = [
            "id",
            "code",
            "name",
            "label",
            "channel",
            "language",
            "scope",
            "subject",
            "body",
            "is_active",
            "wa_template_name",
            "wa_template_params",
            "updated_at",
        ]
        read_only_fields = ["id", "label", "updated_at"]

    def get_label(self, obj) -> dict:
        return code_label(obj.code, obj.name)

    def get_fields(self):
        fields = super().get_fields()
        if (
            self.instance is not None
        ):  # updates never move a template to another code, channel, language or scope
            for name in ("code", "channel", "language", "scope"):
                fields[name].read_only = True
        return fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["scope"] = instance.scope
        return data

    def validate_code(self, value):
        value = (value or "").strip()
        if not CODE_RE.match(value):
            raise serializers.ValidationError("Usa minúsculas, números y guion bajo (ej. bienvenida_spa)")
        if value == CUSTOM_MESSAGE:
            raise serializers.ValidationError("Este código está reservado para los mensajes libres")
        return value

    def validate_wa_template_name(self, value):
        value = (value or "").strip()
        if value and not WA_TEMPLATE_NAME_RE.match(value):
            raise serializers.ValidationError("El nombre de la plantilla de Meta usa minúsculas, números y _")
        return value

    def validate(self, attrs):
        instance = self.instance
        code = attrs.get("code", getattr(instance, "code", ""))
        channel = attrs.get("channel", getattr(instance, "channel", ""))
        if channel not in CHANNELS:
            raise serializers.ValidationError({"channel": ["Canal inválido"]})
        if attrs.get("language", getattr(instance, "language", "es")) not in LANGUAGES:
            raise serializers.ValidationError({"language": ["Idioma inválido"]})
        name = attrs.get("name", getattr(instance, "name", ""))
        if code not in SYSTEM_CODES and not (name or "").strip():
            raise serializers.ValidationError({"name": ["Ponle un nombre a la plantilla personalizada"]})
        subject = attrs.get("subject", getattr(instance, "subject", "")) or ""
        body = attrs.get("body", getattr(instance, "body", "")) or ""
        errors = {}
        if channel == "email" and not subject.strip():
            errors["subject"] = ["El asunto es obligatorio en el correo"]
        if channel == "whatsapp":
            attrs["subject"] = ""
        if not body.strip():
            errors["body"] = ["El mensaje no puede estar vacío"]
        elif len(body) > MAX_BODY[channel]:
            errors["body"] = [f"Máximo {MAX_BODY[channel]} caracteres"]
        for field, text in (("subject", subject if channel == "email" else ""), ("body", body)):
            unknown = unknown_variables(text, CATALOG)
            if unknown and field not in errors:
                errors[field] = [unknown_message(unknown)]
        params = attrs.get("wa_template_params", getattr(instance, "wa_template_params", []) or [])
        wa_name = attrs.get("wa_template_name", getattr(instance, "wa_template_name", ""))
        if channel == "email" and (wa_name or params):
            errors["wa_template_name"] = ["Las plantillas aprobadas de Meta solo aplican a WhatsApp"]
        unknown_params = [name for name in params if name not in CATALOG]
        if unknown_params:
            errors["wa_template_params"] = [unknown_message(unknown_params)]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class PreviewRequestSerializer(serializers.Serializer):
    channel = PlainChoiceField(choices=CHANNELS)
    language = PlainChoiceField(choices=LANGUAGES, required=False, allow_null=True)
    template_code = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True, allow_null=True)
    body = serializers.CharField(
        max_length=MAX_BODY["email"], required=False, allow_blank=True, allow_null=True
    )
    reservation_id = serializers.UUIDField(required=False, allow_null=True)
    conversation_id = serializers.UUIDField(required=False, allow_null=True)
    guest_id = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs.get("body") is None and not attrs["template_code"]:
            raise serializers.ValidationError({"template_code": ["Elige una plantilla o escribe el texto"]})
        return attrs


class PreviewSerializer(serializers.Serializer):
    channel = serializers.CharField()
    language = serializers.CharField()
    source = serializers.CharField()
    sample = serializers.BooleanField()
    subject = serializers.CharField(allow_blank=True)
    text = serializers.CharField(allow_blank=True)
    whatsapp = serializers.CharField(allow_blank=True)
    markup = serializers.CharField(allow_blank=True)
    html = serializers.CharField(allow_blank=True)
    missing = serializers.ListField(child=serializers.CharField())
    unknown = serializers.ListField(child=serializers.CharField())


class VariableSerializer(serializers.Serializer):
    key = serializers.CharField()
    group = serializers.CharField()
    label = serializers.DictField(child=serializers.CharField())
    example = serializers.DictField(child=serializers.CharField())


# --- lifecycle rules -----------------------------------------------------------------------------------


class LifecycleRuleSerializer(MessagingModelSerializer):
    label = serializers.SerializerMethodField()
    scheduled = serializers.SerializerMethodField()
    uses_offset = serializers.SerializerMethodField()
    channels = serializers.ListField(child=serializers.CharField(), max_length=2, allow_empty=True)
    send_after = serializers.TimeField(format="%H:%M", input_formats=["%H:%M", "%H:%M:%S"])
    days_offset = serializers.IntegerField(min_value=0, max_value=MAX_OFFSET_DAYS)

    class Meta:
        model = LifecycleRule
        fields = [
            "id",
            "event",
            "label",
            "enabled",
            "days_offset",
            "uses_offset",
            "channels",
            "template_code",
            "send_after",
            "scheduled",
        ]
        read_only_fields = ["id", "event", "label", "uses_offset", "scheduled"]

    def get_label(self, obj) -> dict:
        return code_label(obj.event)

    def get_scheduled(self, obj) -> bool:
        return obj.event in SCHEDULED_EVENTS

    def get_uses_offset(self, obj) -> bool:
        return obj.event in ("pre_arrival", "post_stay", "payment_reminder")

    def validate_channels(self, value):
        unknown = [channel for channel in value if channel not in CHANNELS]
        if unknown:
            raise serializers.ValidationError(f"Canales inválidos: {', '.join(unknown)}")
        return [channel for channel in CHANNELS if channel in value]

    def validate_template_code(self, value):
        value = (value or "").strip()
        prop = self.instance.property
        if value == CUSTOM_MESSAGE or not any(
            resolve_template(prop, value, channel, "es") for channel in CHANNELS
        ):
            raise serializers.ValidationError("No existe esa plantilla")
        return value

    def validate(self, attrs):
        if not self.get_uses_offset(self.instance):
            attrs["days_offset"] = 0
        return attrs


LIFECYCLE_ORDER = EVENTS


# --- simulator -----------------------------------------------------------------------------------------


class SimulatorInboundSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=40)
    body = serializers.CharField(max_length=4000, trim_whitespace=True)
    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class SimulatorGuestSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    language = serializers.CharField()


class SimulatorThreadSerializer(serializers.Serializer):
    phone = serializers.CharField()
    simulator_enabled = serializers.BooleanField()
    conversation_id = serializers.UUIDField(allow_null=True)
    guest = SimulatorGuestSerializer(allow_null=True)
    messages = MessageSerializer(many=True)


class SimulatorContactSerializer(serializers.Serializer):
    guest_id = serializers.UUIDField()
    full_name = serializers.CharField()
    phone = serializers.CharField()
    reservation = MessagingReservationRefSerializer(allow_null=True)


class SimulatorContactsSerializer(serializers.Serializer):
    simulator_enabled = serializers.BooleanField()
    results = SimulatorContactSerializer(many=True)
