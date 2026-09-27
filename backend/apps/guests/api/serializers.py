import re

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.guests.api.documents import document_file_url, document_filename
from apps.guests.models import Guest, GuestDocument
from apps.guests.normalization import is_usable_phone
from apps.guests.selectors import guest_stats
from apps.guests.services import document_content_type, phone_region

COUNTRY_CODE = re.compile(r"^[A-Za-z]{2}$")
LANGUAGES = [("es", "Español"), ("en", "English")]
MAX_TAGS = 20
MAX_TAG_LENGTH = 40


class GuestListSerializer(serializers.ModelSerializer):
    """Row of `GET guests/` (and of duplicates/lookup, with `reasons`)."""

    full_name = serializers.CharField(read_only=True)
    is_foreign_non_resident = serializers.BooleanField(read_only=True)
    stays_count = serializers.SerializerMethodField()
    reservations_count = serializers.SerializerMethodField()
    last_stay_date = serializers.SerializerMethodField()

    class Meta:
        model = Guest
        fields = [
            "id", "first_name", "last_name", "full_name", "email", "phone", "document_type",
            "document_number", "nationality", "country_of_residence", "city_of_residence", "language",
            "is_vip", "blacklisted", "tags", "is_foreign_non_resident", "anonymized_at", "stays_count",
            "reservations_count", "last_stay_date", "created_at",
        ]  # fmt: skip
        read_only_fields = fields

    @extend_schema_field(OpenApiTypes.INT)
    def get_stays_count(self, guest):
        return getattr(guest, "stays_count", None)

    @extend_schema_field(OpenApiTypes.INT)
    def get_reservations_count(self, guest):
        return getattr(guest, "reservations_count", None)

    @extend_schema_field(OpenApiTypes.DATE)
    def get_last_stay_date(self, guest):
        value = getattr(guest, "last_stay_date", None)
        return value.isoformat() if value else None


class DuplicateSerializer(GuestListSerializer):
    reasons = serializers.SerializerMethodField()

    class Meta(GuestListSerializer.Meta):
        fields = [*GuestListSerializer.Meta.fields, "reasons"]
        read_only_fields = fields

    @extend_schema_field(
        serializers.ListField(child=serializers.ChoiceField(["document", "email", "phone_name"]))
    )
    def get_reasons(self, guest):
        return getattr(guest, "duplicate_reasons", [])


class StayRefSerializer(serializers.Serializer):
    reservation_id = serializers.UUIDField()
    code = serializers.CharField()
    property_id = serializers.UUIDField()
    property_name = serializers.CharField()
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    status = serializers.CharField()


class GuestStatsSerializer(serializers.Serializer):
    reservations_count = serializers.IntegerField()
    stays_count = serializers.IntegerField()
    nights = serializers.IntegerField()
    total_spent = serializers.DecimalField(max_digits=14, decimal_places=2)
    cancellations = serializers.IntegerField()
    no_shows = serializers.IntegerField()
    last_stay = StayRefSerializer(allow_null=True)
    next_stay = StayRefSerializer(allow_null=True)


class GuestSerializer(GuestListSerializer):
    """Detail and write shape of a guest. `data_processing_consent` (write-only) records or revokes the
    Habeas Data consent; the date is `data_processing_consent_at`."""

    document_type = serializers.CharField(max_length=10, required=False, allow_blank=True)
    language = serializers.ChoiceField(choices=LANGUAGES, required=False)
    data_processing_consent = serializers.BooleanField(write_only=True, required=False)
    stats = serializers.SerializerMethodField()
    documents_count = serializers.SerializerMethodField()

    class Meta(GuestListSerializer.Meta):
        fields = [
            *GuestListSerializer.Meta.fields, "birth_date", "gender", "address", "notes", "preferences",
            "marketing_consent", "data_processing_consent", "data_processing_consent_at", "custom_values",
            "merged_into", "updated_at", "stats", "documents_count",
        ]  # fmt: skip
        read_only_fields = [
            "id", "full_name", "is_foreign_non_resident", "anonymized_at", "created_at", "updated_at",
            "data_processing_consent_at", "merged_into",
        ]  # fmt: skip

    def _stats(self, guest) -> dict:
        """Profile numbers, computed once per guest and response (the list counters derive from them)."""
        cached = getattr(guest, "_profile_stats", None)
        if cached is None:
            request = self.context.get("request")
            today = getattr(getattr(request, "property", None), "business_date", None)
            cached = guest._profile_stats = guest_stats(guest, today=today)
        return cached

    @extend_schema_field(GuestStatsSerializer)
    def get_stats(self, guest):
        return GuestStatsSerializer(self._stats(guest)).data

    @extend_schema_field(OpenApiTypes.INT)
    def get_stays_count(self, guest):
        return self._stats(guest)["stays_count"]

    @extend_schema_field(OpenApiTypes.INT)
    def get_reservations_count(self, guest):
        return self._stats(guest)["reservations_count"]

    @extend_schema_field(OpenApiTypes.DATE)
    def get_last_stay_date(self, guest):
        last = self._stats(guest)["last_stay"]
        return last["checkin"] if last else None

    @extend_schema_field(OpenApiTypes.INT)
    def get_documents_count(self, guest):
        return guest.documents.count()

    def validate_document_type(self, value):
        value = value.strip().upper()
        if value and value not in Guest.DocumentType.values:
            raise serializers.ValidationError("Tipo de documento inválido")
        return value

    def _validate_country(self, value):
        value = (value or "").strip()
        if value and not COUNTRY_CODE.match(value):
            raise serializers.ValidationError("Usa el código ISO de dos letras del país (CO, US, ES…)")
        return value.upper()

    def validate_nationality(self, value):
        return self._validate_country(value)

    def validate_country_of_residence(self, value):
        return self._validate_country(value)

    def validate_birth_date(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError("La fecha de nacimiento no puede ser futura")
        return value

    def validate_tags(self, value):
        if not isinstance(value, list) or not all(isinstance(tag, str) for tag in value):
            raise serializers.ValidationError("Las etiquetas deben ser una lista de textos")
        tags = list(dict.fromkeys(tag.strip() for tag in value if tag.strip()))
        if len(tags) > MAX_TAGS or any(len(tag) > MAX_TAG_LENGTH for tag in tags):
            raise serializers.ValidationError(f"Máximo {MAX_TAGS} etiquetas de {MAX_TAG_LENGTH} caracteres")
        return tags

    def validate_preferences(self, value):
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise serializers.ValidationError("Las preferencias deben ser un objeto {clave: valor}")
        return value

    def validate(self, attrs):
        instance = self.instance
        document_type = attrs.get("document_type", getattr(instance, "document_type", ""))
        document_number = attrs.get("document_number", getattr(instance, "document_number", ""))
        if document_number and not document_type:
            raise serializers.ValidationError({"document_type": ["Elige el tipo de documento"]})
        phone = attrs.get("phone")
        if phone:
            region = phone_region(
                attrs.get("country_of_residence", getattr(instance, "country_of_residence", "")),
                attrs.get("nationality", getattr(instance, "nationality", "")),
            )
            if not is_usable_phone(phone, region=region):
                raise serializers.ValidationError(
                    {"phone": ["Escribe un teléfono válido (con el indicativo si no es de Colombia)"]}
                )
        if "custom_values" in attrs:
            attrs["custom_values"] = self._clean_custom_values(attrs["custom_values"])
        return attrs

    def _clean_custom_values(self, values):
        from apps.inventory.models import CustomFieldDefinition
        from apps.inventory.services import validate_custom_values  # contract (spec §4)

        request = self.context["request"]
        definitions = CustomFieldDefinition.objects.filter(
            Q(property__isnull=True) | Q(property=request.property),
            organization=request.organization,
            applies_to="guest",
        ).order_by("sort_order", "key")
        return validate_custom_values(list(definitions), values)


class GuestDocumentSerializer(serializers.ModelSerializer):
    """A document never exposes a /media/ URL: `file_url` is the authenticated file endpoint."""

    file_url = serializers.SerializerMethodField()
    content_type = serializers.SerializerMethodField()
    filename = serializers.SerializerMethodField()
    size = serializers.SerializerMethodField()

    class Meta:
        model = GuestDocument
        fields = [
            "id",
            "guest",
            "kind",
            "uploaded_via",
            "created_at",
            "file_url",
            "content_type",
            "filename",
            "size",
        ]
        read_only_fields = fields

    def get_file_url(self, document) -> str:
        return document_file_url(document)

    def get_content_type(self, document) -> str:
        return document_content_type(document)

    def get_filename(self, document) -> str:
        return document_filename(document)

    @extend_schema_field(OpenApiTypes.INT)
    def get_size(self, document):
        try:
            return document.file.size
        except (FileNotFoundError, ValueError):
            return None


class DocumentUploadSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=GuestDocument.Kind.choices)
    file = serializers.FileField()


class MergeSerializer(serializers.Serializer):
    primary_id = serializers.UUIDField()
    duplicate_id = serializers.UUIDField()
    confirm = serializers.BooleanField(default=False)


class ConfirmSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(default=False)


class StayRowSerializer(serializers.Serializer):
    """Row of `GET guests/<id>/stays/` (one per reservation)."""

    id = serializers.UUIDField()
    code = serializers.CharField()
    status = serializers.CharField()
    source = serializers.CharField()
    channel_code = serializers.CharField()
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    nights = serializers.IntegerField()
    adults = serializers.IntegerField()
    children = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    currency = serializers.CharField()
    property = serializers.DictField()
    role = serializers.ChoiceField(choices=["booker", "occupant"])
    rooms = serializers.ListField(child=serializers.CharField())


def stay_row(reservation, guest) -> dict:
    return {
        "id": reservation.pk,
        "code": reservation.code,
        "status": reservation.status,
        "source": reservation.source,
        "channel_code": reservation.channel_code,
        "checkin": reservation.checkin_date,
        "checkout": reservation.checkout_date,
        "nights": (reservation.checkout_date - reservation.checkin_date).days,
        "adults": reservation.adults,
        "children": reservation.children,
        "total_amount": reservation.total_amount,
        "currency": reservation.currency,
        "property": {"id": str(reservation.property_id), "name": reservation.property.name},
        "role": "booker" if reservation.booker_id == guest.pk else "occupant",
        "rooms": sorted({stay.room.number for stay in reservation.stays.all() if stay.room_id}),
    }
