"""Serializers of the compliance API. Money goes out as strings with two decimals."""

from rest_framework import serializers

from apps.compliance.codes import SIRE_COUNTRY_CODES, SIRE_DOCUMENT_TYPES, TRA_TRAVEL_REASONS
from apps.compliance.models import ComplianceSettings, Invoice, InvoiceResolution, SireReport, TraRegistration
from apps.compliance.services.cufe import validation_url


def _user_name(user):
    return (user.full_name or user.email) if user else None


# ------------------------------------------------------------------------------------------ resolutions


class ResolutionSerializer(serializers.ModelSerializer):
    next_number = serializers.IntegerField(read_only=True)
    remaining = serializers.IntegerField(read_only=True)
    invoices_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = InvoiceResolution
        fields = [
            "id", "document_kind", "prefix", "resolution_number", "from_number", "to_number",
            "current_number",
            "next_number", "remaining", "valid_from", "valid_to", "technical_key", "environment",
            "provider_range_id", "is_active", "invoices_count", "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = ["current_number", "created_at", "updated_at"]
        # the one-active-per-kind rule is applied by the view (it retires the previous active resolution)
        validators: list = []

    LOCKED_WHEN_USED = ("document_kind", "prefix", "from_number")

    def validate_prefix(self, value):
        value = (value or "").strip().upper()
        if value and not value.isalnum():
            raise serializers.ValidationError("El prefijo solo admite letras y números")
        return value

    def validate(self, attrs):
        instance = self.instance
        get = lambda key: attrs.get(key, getattr(instance, key, None))  # noqa: E731
        errors = {}
        if get("from_number") is not None and get("from_number") < 1:
            errors["from_number"] = ["El rango empieza en 1 o más"]
        if get("from_number") and get("to_number") and get("to_number") < get("from_number"):
            errors["to_number"] = ["El número final debe ser mayor o igual al inicial"]
        if get("valid_from") and get("valid_to") and get("valid_to") < get("valid_from"):
            errors["valid_to"] = ["La vigencia termina antes de empezar"]
        if instance is not None and instance.invoices.exists():
            for field in self.LOCKED_WHEN_USED:
                if field in attrs and attrs[field] != getattr(instance, field):
                    errors[field] = ["No se puede cambiar: la resolución ya numeró documentos"]
            if "to_number" in attrs and attrs["to_number"] < instance.current_number:
                errors["to_number"] = [f"Ya se usó hasta el número {instance.current_number}"]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


# --------------------------------------------------------------------------------------------- invoices


class InvoiceSummarySerializer(serializers.ModelSerializer):
    number = serializers.CharField(source="full_number")
    customer_name = serializers.SerializerMethodField()
    customer_document = serializers.SerializerMethodField()
    reservation_code = serializers.SerializerMethodField()
    related_number = serializers.SerializerMethodField()
    subtotal = serializers.DecimalField(max_digits=14, decimal_places=2)
    tax_total = serializers.DecimalField(max_digits=14, decimal_places=2)
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    has_pdf = serializers.SerializerMethodField()
    is_exempt = serializers.SerializerMethodField()

    is_company = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id", "kind", "status", "number", "prefix", "issue_date", "issued_at", "currency", "subtotal",
            "tax_total", "total", "customer_name", "customer_document", "reservation_id", "reservation_code",
            "related_invoice_id", "related_number", "mode", "environment", "attempts", "error_message",
            "has_pdf",
            "is_exempt", "created_at", "due_date", "is_company",
        ]  # fmt: skip

    def get_customer_name(self, obj) -> str:
        return (obj.customer or {}).get("name", "")

    def get_customer_document(self, obj) -> str:
        customer = obj.customer or {}
        number = customer.get("document_number", "")
        if customer.get("dv"):
            number = f"{number}-{customer['dv']}"
        return f"{customer.get('document_type', '')} {number}".strip()

    def get_is_company(self, obj) -> bool:
        """P4: invoiced to a company (company folio)."""
        return bool((obj.customer or {}).get("company_id"))

    def get_reservation_code(self, obj) -> str:
        return obj.reservation.code if obj.reservation_id else ""

    def get_related_number(self, obj) -> str:
        return obj.related_invoice.full_number if obj.related_invoice_id else ""

    def get_has_pdf(self, obj) -> bool:
        return bool(obj.pdf_file)

    def get_is_exempt(self, obj) -> bool:
        return bool(obj.exempt_note)


class InvoiceDetailSerializer(InvoiceSummarySerializer):
    validation_url = serializers.SerializerMethodField()
    credit_notes = serializers.SerializerMethodField()
    resolution = serializers.SerializerMethodField()
    charges_count = serializers.SerializerMethodField()

    class Meta(InvoiceSummarySerializer.Meta):
        fields = InvoiceSummarySerializer.Meta.fields + [
            "customer", "lines", "exempt_note", "cufe", "qr_data", "validation_url", "provider",
            "provider_ref",
            "reason", "credit_notes", "resolution", "folio_id", "charges_count", "last_attempt_at",
        ]  # fmt: skip

    def get_validation_url(self, obj) -> str:
        return validation_url(obj.cufe, obj.environment) if obj.cufe else ""

    def get_credit_notes(self, obj) -> list[dict]:
        return [
            {
                "id": str(note.pk),
                "number": note.full_number,
                "status": note.status,
                "issue_date": note.issue_date,
                "reason": note.reason,
            }
            for note in obj.credit_notes.order_by("created_at")
        ]

    def get_resolution(self, obj) -> dict | None:
        resolution = obj.resolution
        if resolution is None:
            return None
        return {
            "id": str(resolution.pk),
            "prefix": resolution.prefix,
            "resolution_number": resolution.resolution_number,
            "from_number": resolution.from_number,
            "to_number": resolution.to_number,
            "valid_from": resolution.valid_from,
            "valid_to": resolution.valid_to,
        }

    def get_charges_count(self, obj) -> int:
        return obj.charges.count()


class IssueSerializer(serializers.Serializer):
    reservation_id = serializers.UUIDField(required=False)
    folio_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if bool(attrs.get("reservation_id")) == bool(attrs.get("folio_id")):
            raise serializers.ValidationError({"reservation_id": ["Indica la reserva o el folio a facturar"]})
        return attrs


class CreditNoteSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")
    confirm = serializers.BooleanField(required=False, default=False)


# ------------------------------------------------------------------------------------------------- SIRE


class SireReportSerializer(serializers.ModelSerializer):
    missing_count = serializers.SerializerMethodField()
    generated_by_name = serializers.SerializerMethodField()
    submitted_by_name = serializers.SerializerMethodField()
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = SireReport
        fields = [
            "id", "period_start", "period_end", "status", "records_count", "missing_count", "mode",
            "generated_at",
            "generated_by_name", "submitted_at", "submitted_by_name", "ack_code", "file_name",
        ]  # fmt: skip

    def get_missing_count(self, obj) -> int:
        return len(obj.missing or [])

    def get_generated_by_name(self, obj) -> str | None:
        return _user_name(obj.generated_by)

    def get_submitted_by_name(self, obj) -> str | None:
        return _user_name(obj.submitted_by)

    def get_file_name(self, obj) -> str:
        return obj.file.name.rsplit("/", 1)[-1] if obj.file else ""


class SireReportDetailSerializer(SireReportSerializer):
    records = serializers.SerializerMethodField()

    class Meta(SireReportSerializer.Meta):
        fields = SireReportSerializer.Meta.fields + ["missing", "records"]

    def get_records(self, obj) -> list[dict]:
        return [
            {
                "id": str(record.pk),
                "guest_id": str(record.guest_id),
                "guest_name": record.guest.full_name,
                "reservation_id": str(record.stay.reservation_id),
                "reservation_code": record.stay.reservation.code,
                "movement": record.movement,
                "movement_date": record.movement_date,
                "complete": record.complete,
                "missing_fields": record.missing_fields,
                "document": record.data.get("document_number", ""),
                "nationality": record.data.get("nationality", ""),
            }
            for record in obj.records.select_related("guest", "stay__reservation").order_by(
                "movement_date", "movement", "created_at"
            )
        ]


class SireGenerateSerializer(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()


class SireSubmitSerializer(serializers.Serializer):
    ack_code = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


# -------------------------------------------------------------------------------------------------- TRA


class TraRegistrationSerializer(serializers.ModelSerializer):
    guest = serializers.SerializerMethodField()
    reservation_code = serializers.SerializerMethodField()
    room = serializers.SerializerMethodField()
    checkin_date = serializers.DateField(source="stay.checkin_date", read_only=True)
    checkout_date = serializers.DateField(source="stay.checkout_date", read_only=True)

    class Meta:
        model = TraRegistration
        fields = [
            "id", "status", "tra_number", "guest", "reservation_id", "reservation_code", "stay_id", "room",
            "checkin_date", "checkout_date", "is_main", "parent_id", "mode", "missing_fields", "error",
            "attempts",
            "registered_at", "last_attempt_at", "payload", "created_at",
        ]  # fmt: skip

    def get_guest(self, obj) -> dict:
        guest = obj.guest
        return {
            "id": str(guest.pk),
            "full_name": guest.full_name,
            "document_type": guest.document_type,
            "document_number": guest.document_number,
            "nationality": guest.nationality,
        }

    def get_reservation_code(self, obj) -> str:
        return obj.reservation.code

    def get_room(self, obj) -> str:
        stay = obj.stay
        if not stay.room_id:
            return ""
        return f"{stay.room.number} · {stay.bed.label}" if stay.bed_id else stay.room.number


class TraRegisterSerializer(serializers.Serializer):
    stay_id = serializers.UUIDField()


# ---------------------------------------------------------------------------------------------- settings


def _code_table(value, field):
    if not isinstance(value, dict):
        raise serializers.ValidationError("Debe ser un objeto {código: valor}")
    table = {}
    for key, code in value.items():
        if not isinstance(key, str) or not isinstance(code, str) or not key.strip() or not code.strip():
            raise serializers.ValidationError('Cada entrada debe ser texto → texto (por ejemplo {"PA": "3"})')
        table[key.strip().upper()] = code.strip()
    return table


class ComplianceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplianceSettings
        fields = [
            "go_live_date", "auto_issue_invoices", "final_consumer_id", "invoice_notes",
            "sire_establishment_code",
            "sire_city_code", "sire_document_codes", "sire_country_codes", "sire_second_surname_column",
            "tra_auto_register", "tra_establishment_id", "tra_travel_reason", "tra_accommodation_type",
        ]  # fmt: skip

    def validate_final_consumer_id(self, value):
        value = (value or "").strip()
        if not value.isdigit():
            raise serializers.ValidationError("Solo números (la DIAN usa 222222222222)")
        return value

    def validate_sire_city_code(self, value):
        value = (value or "").strip()
        if value and (not value.isdigit() or len(value) != 5):
            raise serializers.ValidationError("Código DIVIPOLA de 5 dígitos (Cartagena: 13001)")
        return value

    def validate_sire_document_codes(self, value):
        return _code_table(value, "sire_document_codes")

    def validate_sire_country_codes(self, value):
        return _code_table(value, "sire_country_codes")


def settings_payload(settings) -> dict:
    from apps.compliance.services.config import (
        sire_city_code,
        supplier_info,
        tra_accommodation_type,
        tra_establishment_id,
    )
    from apps.core import integrations

    prop = settings.property
    supplier = supplier_info(prop)
    data = ComplianceSettingsSerializer(settings).data
    data["effective"] = {
        "sire_city_code": sire_city_code(settings),
        "tra_establishment_id": tra_establishment_id(settings),
        "tra_accommodation_type": tra_accommodation_type(settings),
    }
    data["defaults"] = {
        "sire_document_codes": SIRE_DOCUMENT_TYPES,
        "sire_country_codes": SIRE_COUNTRY_CODES,
        "travel_reasons": TRA_TRAVEL_REASONS,
    }
    data["integrations"] = {}
    for kind in ("einvoice", "sire", "tra"):
        setting = integrations.get_setting(prop, kind)
        providers = integrations.providers_for(kind)
        provider = providers.get(setting.mode)
        data["integrations"][kind] = {
            "mode": setting.mode,
            "enabled": setting.enabled,
            "status": setting.status,
            "provider_label": provider.label if provider else "",
        }
    profile = {
        "legal_name": prop.legal_name,
        "nit": prop.nit,
        "address": prop.address,
        "rnt": prop.rnt_number,
    }
    data["supplier"] = {
        "legal_name": supplier["legal_name"],
        "nit": supplier["nit_display"],
        "rnt": supplier["rnt"],
        "city": supplier["city"],
        "missing": [key for key, value in profile.items() if not value],
    }
    return data
