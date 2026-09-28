"""Request serializers of the guest portal API. They document the payloads in /api/docs/; the domain rules
(required TRA/SIRE data, windows, policies) are validated by the services, which report errors with stable
codes."""

from rest_framework import serializers

from apps.guestportal.models import GuestPortalSettings, ServiceRequest
from apps.guestportal.services.checkin import DOCUMENT_KINDS, TRAVEL_REASONS


class CheckinGuestEntrySerializer(serializers.Serializer):
    stay_id = serializers.UUIDField()
    role = serializers.ChoiceField(["booker", "companion"])
    guest_id = serializers.UUIDField(required=False, allow_null=True, help_text="Acompañante ya registrado")
    keep = serializers.BooleanField(
        required=False, help_text="Conserva un acompañante ya registrado sin cambios"
    )
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)
    document_type = serializers.CharField(required=False, allow_blank=True)
    document_number = serializers.CharField(required=False, allow_blank=True)
    nationality = serializers.CharField(required=False, allow_blank=True, help_text="ISO 3166-1 alfa-2")
    country_of_residence = serializers.CharField(required=False, allow_blank=True)
    city_of_residence = serializers.CharField(required=False, allow_blank=True)
    birth_date = serializers.DateField(required=False, allow_null=True)
    email = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    travel_reason = serializers.ChoiceField(TRAVEL_REASONS, required=False, allow_blank=True)
    origin = serializers.CharField(required=False, allow_blank=True, help_text="Procedencia")
    destination = serializers.CharField(required=False, allow_blank=True, help_text="Destino")


class CheckinStepSerializer(serializers.Serializer):
    step = serializers.ChoiceField(["guests", "documents", "arrival", "signature"])
    guests = CheckinGuestEntrySerializer(many=True, required=False)
    guest_id = serializers.UUIDField(required=False, help_text="documents: huésped dueño del archivo")
    kind = serializers.ChoiceField(DOCUMENT_KINDS, required=False)
    file = serializers.FileField(
        required=False, help_text="documents: foto (JPG/PNG/WebP/HEIC) o PDF ≤ 10 MB"
    )
    eta = serializers.TimeField(required=False, allow_null=True, format="%H:%M")
    signature = serializers.CharField(required=False, allow_blank=True, help_text="data:image/png;base64,…")
    accept_terms = serializers.BooleanField(required=False)
    marketing_consent = serializers.BooleanField(required=False)


class PaySerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False,
                                      help_text="Por defecto, todo el saldo")  # fmt: skip


class ServiceRequestCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(ServiceRequest.Kind.choices)
    extra_id = serializers.UUIDField(required=False, help_text="kind=extra: un extra vendible en línea")
    quantity = serializers.IntegerField(required=False, min_value=1, max_value=99)
    requested_time = serializers.TimeField(required=False, allow_null=True, format="%H:%M")
    notes = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class CancelSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(help_text="Debe ser true: el huésped vio la penalidad")
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


class ModifySerializer(serializers.Serializer):
    checkin = serializers.DateField()
    checkout = serializers.DateField(help_text="Exclusiva")


# --- staff -----------------------------------------------------------------------------------------------


class SendLinkSerializer(serializers.Serializer):
    """Same shape as finance's payment link (`send_via`); email when empty."""

    send_via = serializers.ListField(
        child=serializers.ChoiceField(choices=["email", "whatsapp"]), required=False, max_length=2
    )


class ApproveRequestSerializer(serializers.Serializer):
    extra_id = serializers.UUIDField(required=False, help_text="Extra del catálogo que se cobra al aprobar")
    quantity = serializers.IntegerField(required=False, min_value=1, max_value=99)
    note = serializers.CharField(required=False, allow_blank=True, max_length=300)


class RejectRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=300)


class GuestPortalSettingsSerializer(serializers.ModelSerializer):
    checkin_opens_days_before = serializers.IntegerField(min_value=0, max_value=60, required=False)

    class Meta:
        model = GuestPortalSettings
        fields = [
            "checkin_opens_days_before",
            "require_document_photo",
            "require_signature",
            "auto_approve_extras",
            "allow_guest_cancellation",
            "allow_guest_modification",
            "terms",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]

    def validate_terms(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("Usa un objeto {es, en}")
        clean = {}
        for lang in ("es", "en"):
            text = value.get(lang, "")
            if not isinstance(text, str) or len(text) > 5000:
                raise serializers.ValidationError(f"Texto inválido en {lang} (máximo 5000 caracteres)")
            clean[lang] = text.strip()
        return clean
