"""Serializers of the corporate API. Money goes out as strings with two decimals.

Choice-like fields are plain `CharField`s validated by hand (like finance's): a `ChoiceField` named `kind` or
`status` would collide in the OpenAPI schema with the enums of other apps."""

from decimal import Decimal

from rest_framework import serializers

from apps.corporate.models import TAX_RESPONSIBILITIES, Company, ReservationBilling
from apps.corporate.nit import MAX_DIGITS, check_digit, format_nit, normalize_nit
from apps.corporate.routing import ROUTE_VALUES
from apps.corporate.services import AR_METHODS

MONEY = {"max_digits": 14, "decimal_places": 2}
KINDS = [kind.value for kind in Company.Kind]


def money(value) -> str | None:
    return f"{value:.2f}" if value is not None else None


class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    role = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")


class CompanySerializer(serializers.ModelSerializer):
    kind = serializers.CharField(required=False, help_text="corporate | travel_agency | government | other")
    nit = serializers.CharField(
        max_length=20, help_text="NIT with or without the check digit (900.123.456-7)"
    )
    dv = serializers.CharField(
        max_length=1, required=False, allow_blank=True, help_text="Computed when empty"
    )
    nit_display = serializers.SerializerMethodField()
    tax_responsibilities = serializers.ListField(child=serializers.CharField(), required=False)
    contacts = ContactSerializer(many=True, required=False)
    credit_limit = serializers.DecimalField(**MONEY, required=False, allow_null=True, min_value=Decimal("0"))
    payment_terms_days = serializers.IntegerField(required=False, min_value=0, max_value=365)
    receivable = serializers.SerializerMethodField()

    class Meta:
        model = Company
        fields = [
            "id", "kind", "legal_name", "trade_name", "nit", "dv", "nit_display", "vat_responsible",
            "tax_responsibilities", "address", "city", "department", "country", "billing_email", "phone",
            "credit_enabled", "credit_limit", "payment_terms_days", "contacts", "notes", "is_active",
            "receivable", "created_at", "updated_at",
        ]  # fmt: skip
        read_only_fields = ["created_at", "updated_at"]
        validators: list = []  # the (organization, nit) uniqueness is checked in `validate`

    def get_nit_display(self, obj) -> str:
        return format_nit(obj.nit, obj.dv)

    def get_receivable(self, obj) -> dict | None:
        """At the active property: open balance, overdue part and reservations in progress (list/detail)."""
        balances = self.context.get("balances")
        if balances is None:
            return None
        row = balances.get(obj.pk) or {}
        return {
            "balance": money(row.get("balance", Decimal("0"))),
            "overdue": money(row.get("overdue", Decimal("0"))),
            "in_progress": money(row.get("in_progress", Decimal("0"))),
        }

    def validate_kind(self, value):
        if value not in KINDS:
            raise serializers.ValidationError(f"Tipo inválido. Opciones: {', '.join(KINDS)}")
        return value

    def validate_legal_name(self, value):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Escribe la razón social")
        return value

    def validate_tax_responsibilities(self, value):
        codes = [code.strip().upper() for code in value or [] if code and code.strip()]
        unknown = [code for code in codes if code not in TAX_RESPONSIBILITIES]
        if unknown:
            raise serializers.ValidationError(f"Responsabilidad desconocida: {', '.join(unknown)}")
        return list(dict.fromkeys(codes))

    def validate_country(self, value):
        return (value or "CO").strip().upper()[:2] or "CO"

    def validate(self, attrs):
        instance = self.instance
        raw_nit = attrs.get("nit", instance.nit if instance else "")
        digits, typed_dv = normalize_nit(raw_nit)
        typed_dv = (attrs.get("dv") or "").strip() or typed_dv
        errors = {}
        if "nit" in attrs or instance is None:
            if not digits or len(digits) < 5 or len(digits) > MAX_DIGITS:
                errors["nit"] = ["Escribe un NIT válido (solo números, sin el dígito de verificación)"]
        if digits and not errors:
            expected = check_digit(digits)
            if typed_dv and typed_dv != expected:
                errors["dv"] = [f"El dígito de verificación no coincide: para el NIT {digits} es {expected}"]
            attrs["nit"], attrs["dv"] = digits, expected
            organization = self.context["organization"]
            clash = Company.objects.filter(organization=organization, nit=digits)
            if instance is not None:
                clash = clash.exclude(pk=instance.pk)
            if clash.exists():
                errors["nit"] = ["Ya existe una empresa con ese NIT"]
        credit_enabled = attrs.get("credit_enabled", instance.credit_enabled if instance else False)
        if (
            credit_enabled
            and attrs.get("payment_terms_days", instance.payment_terms_days if instance else 30) < 1
        ):
            errors["payment_terms_days"] = ["Con crédito, el plazo es de al menos 1 día"]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    # `contacts` is a JSON list: store plain dicts (DRF refuses nested writes by default).
    def create(self, validated_data):
        validated_data["contacts"] = [dict(item) for item in validated_data.get("contacts", [])]
        return Company.objects.create(**validated_data)

    def update(self, instance, validated_data):
        if "contacts" in validated_data:
            validated_data["contacts"] = [dict(item) for item in validated_data["contacts"]]
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        return instance


class CompanyRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    legal_name = serializers.CharField()
    trade_name = serializers.CharField()
    kind = serializers.CharField()
    nit = serializers.CharField()
    dv = serializers.CharField()
    nit_display = serializers.CharField()
    credit_enabled = serializers.BooleanField()
    payment_terms_days = serializers.IntegerField()
    is_active = serializers.BooleanField()


class BillingUpdateSerializer(serializers.Serializer):
    bill_to = serializers.CharField(help_text="guest | company")
    company_id = serializers.UUIDField(required=False, allow_null=True)
    routing = serializers.ListField(
        child=serializers.CharField(), required=False, default=list, help_text=f"Subset of {ROUTE_VALUES}"
    )
    purchase_order = serializers.CharField(required=False, allow_blank=True, default="", max_length=60)
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    move_existing = serializers.BooleanField(required=False, default=True)

    def validate_bill_to(self, value):
        if value not in ReservationBilling.BillTo.values:
            raise serializers.ValidationError("Opciones: guest, company")
        return value

    def validate_routing(self, value):
        unknown = [item for item in value if item not in ROUTE_VALUES]
        if unknown:
            raise serializers.ValidationError(f"Regla desconocida: {', '.join(unknown)}")
        return value


class AccountAllocationSerializer(serializers.Serializer):
    folio_id = serializers.UUIDField()
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))


class AccountPaymentCreateSerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    method = serializers.CharField(help_text=" | ".join(AR_METHODS))
    reference = serializers.CharField(required=False, allow_blank=True, default="", max_length=120)
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)
    received_on = serializers.DateField(required=False, allow_null=True, default=None)
    allocations = AccountAllocationSerializer(many=True, required=False, default=list)
    auto_allocate = serializers.BooleanField(required=False, default=False)

    def validate_method(self, value):
        if value not in AR_METHODS:
            raise serializers.ValidationError(f"Opciones: {', '.join(AR_METHODS)}")
        return value


class ApplyCreditSerializer(serializers.Serializer):
    allocations = AccountAllocationSerializer(many=True, required=False, default=list)
    auto = serializers.BooleanField(required=False, default=False)


class AccountPaymentVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)
    confirm = serializers.BooleanField(required=False, default=False)


class OpeningBalanceSerializer(serializers.Serializer):
    amount = serializers.DecimalField(**MONEY, min_value=Decimal("0.01"))
    document_date = serializers.DateField()
    reference = serializers.CharField(max_length=120)
    description = serializers.CharField(required=False, allow_blank=True, default="", max_length=255)
