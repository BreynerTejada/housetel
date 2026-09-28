"""SaaS API serializers. Choice fields are exposed as plain strings (read-only CharFields) so the OpenAPI
schema does not generate colliding `StatusEnum`s with other apps."""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.core import integrations
from apps.core.models import Property
from apps.saas.models import Commission, CommissionSettlement, Plan, PlatformInvoice, Subscription


def _i18n(value, field_name: str, *, required_es: bool = True) -> dict:
    if not isinstance(value, dict):
        raise serializers.ValidationError({field_name: ["Debe ser un objeto {es, en}"]})
    clean = {k: str(v).strip() for k, v in value.items() if k in ("es", "en") and v is not None}
    if required_es and not clean.get("es"):
        raise serializers.ValidationError({field_name: ["El texto en español es obligatorio"]})
    return clean


class PlanSerializer(serializers.ModelSerializer):
    subscriptions_count = serializers.IntegerField(read_only=True, required=False)
    active_subscriptions_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name",
            "description",
            "max_units",
            "max_properties",
            "price_monthly",
            "price_yearly",
            "is_active",
            "sort",
            "subscriptions_count",
            "active_subscriptions_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        return _i18n(value, "name")

    def validate_description(self, value):
        return _i18n(value, "description", required_es=False)

    def validate(self, attrs):
        for key in ("price_monthly", "price_yearly"):
            if key in attrs and attrs[key] is not None and attrs[key] < 0:
                raise serializers.ValidationError({key: ["El precio no puede ser negativo"]})
        return attrs


class PublicPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "code",
            "name",
            "description",
            "max_units",
            "max_properties",
            "price_monthly",
            "price_yearly",
        ]


class PlanRefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "code", "name", "max_units", "max_properties", "price_monthly", "price_yearly"]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanRefSerializer(read_only=True)
    status = serializers.CharField(read_only=True)
    billing_cycle = serializers.CharField(read_only=True)
    monthly_amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    payment_source = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "status",
            "billing_cycle",
            "current_period_start",
            "current_period_end",
            "trial_ends_at",
            "cancel_at_period_end",
            "payment_source",
            "retries",
            "next_retry_at",
            "past_due_since",
            "cancelled_at",
            "monthly_amount",
        ]

    def get_payment_source(self, obj) -> dict | None:
        source = obj.payment_source or {}
        if not source:
            return None
        keys = ("type", "brand", "last4", "exp_month", "exp_year", "holder", "simulated")
        return {key: source.get(key) for key in keys}


class PlatformInvoiceSerializer(serializers.ModelSerializer):
    kind = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    organization = serializers.SerializerMethodField()

    class Meta:
        model = PlatformInvoice
        fields = [
            "id",
            "number",
            "kind",
            "organization",
            "period_start",
            "period_end",
            "lines",
            "currency",
            "subtotal",
            "tax_rate",
            "tax",
            "total",
            "status",
            "issued_at",
            "due_date",
            "paid_at",
            "payment_reference",
            "payment_method",
            "attempts",
            "last_error",
        ]

    def get_organization(self, obj) -> dict:
        return {"id": str(obj.organization_id), "name": obj.organization.name, "slug": obj.organization.slug}


class CommissionSettlementSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    organization = serializers.SerializerMethodField()
    invoice = serializers.SerializerMethodField()

    class Meta:
        model = CommissionSettlement
        fields = [
            "id",
            "organization",
            "period_start",
            "period_end",
            "total",
            "commissions_count",
            "status",
            "invoice",
            "created_at",
        ]

    def get_organization(self, obj) -> dict:
        return {"id": str(obj.organization_id), "name": obj.organization.name, "slug": obj.organization.slug}

    def get_invoice(self, obj) -> dict | None:
        if obj.invoice_id is None:
            return None
        return {"id": str(obj.invoice_id), "number": obj.invoice.number, "status": obj.invoice.status}


class CommissionSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)
    basis = serializers.CharField(read_only=True)
    organization = serializers.SerializerMethodField()
    property = serializers.SerializerMethodField()
    reservation = serializers.SerializerMethodField()
    settlement_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = Commission
        fields = [
            "id",
            "organization",
            "property",
            "reservation",
            "basis",
            "base_amount",
            "rate",
            "amount",
            "currency",
            "status",
            "accrual_date",
            "settlement_id",
            "reversed_at",
            "created_at",
        ]

    def get_organization(self, obj) -> dict:
        return {"id": str(obj.organization_id), "name": obj.organization.name}

    def get_property(self, obj) -> dict:
        return {"id": str(obj.property_id), "name": obj.property.name, "slug": obj.property.slug}

    def get_reservation(self, obj) -> dict:
        r = obj.reservation
        return {
            "id": str(r.pk),
            "code": r.code,
            "status": r.status,
            "checkin_date": r.checkin_date.isoformat(),
            "checkout_date": r.checkout_date.isoformat(),
            "total_amount": str(r.total_amount),
        }


# ---- Requests ------------------------------------------------------------------------------------


class SignupSerializer(serializers.Serializer):
    hotel_name = serializers.CharField(max_length=120, trim_whitespace=True)
    property_type = serializers.ChoiceField(choices=Property.PropertyType.choices)
    city = serializers.CharField(max_length=100, trim_whitespace=True)
    department = serializers.CharField(max_length=100, trim_whitespace=True, required=False, allow_blank=True)
    rooms_estimate = serializers.IntegerField(min_value=1, max_value=5000)
    owner_name = serializers.CharField(max_length=120, trim_whitespace=True)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, write_only=True, trim_whitespace=False)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, trim_whitespace=True)
    accept_terms = serializers.BooleanField()
    language = serializers.CharField(max_length=2, required=False, allow_blank=True)

    def validate_language(self, value):
        if value and value not in ("es", "en"):
            raise serializers.ValidationError("Idioma no soportado (es o en)")
        return value

    def validate_hotel_name(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Escribe el nombre de tu hotel (mínimo 3 caracteres)")
        return value.strip()

    def validate_email(self, value):
        from apps.accounts.models import User

        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "Ya existe una cuenta con este email. Inicia sesión o usa otro correo."
            )
        return value

    def validate_accept_terms(self, value):
        if value is not True:
            raise serializers.ValidationError(
                "Debes aceptar los términos del servicio y la política de tratamiento de datos"
            )
        return value

    def validate(self, attrs):
        from apps.accounts.models import User

        try:
            validate_password(
                attrs["password"], User(email=attrs.get("email", ""), full_name=attrs.get("owner_name", ""))
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs


class SubscriptionPlanChangeSerializer(serializers.Serializer):
    plan_code = serializers.SlugField()
    billing_cycle = serializers.ChoiceField(choices=Subscription.Cycle.choices, required=False)


class SubscriptionCancelSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class BillingPaymentMethodSerializer(serializers.Serializer):
    holder = serializers.CharField(max_length=80, required=False, allow_blank=True)
    number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    exp_month = serializers.IntegerField(required=False)
    exp_year = serializers.IntegerField(required=False)
    cvc = serializers.CharField(max_length=4, required=False, allow_blank=True)
    token = serializers.CharField(max_length=200, required=False, allow_blank=True)
    acceptance_token = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    accept_personal_auth = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class TrialExtensionSerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=90)


class OrganizationSuspendSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class SimulateFailureSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class SettlementMonthSerializer(serializers.Serializer):
    month = serializers.RegexField(r"^\d{4}-(0[1-9]|1[0-2])$", help_text="YYYY-MM")


class InvoiceVoidSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class PlatformBillingSettingsSerializer(serializers.Serializer):
    mode = serializers.CharField(max_length=10, required=False)
    enabled = serializers.BooleanField(required=False)

    def validate_mode(self, value):
        if value not in ("real", "simulated"):
            raise serializers.ValidationError("Modo inválido (real o simulated)")
        if not integrations.mode_allowed("saas_billing", value):  # production: only the real Wompi (P-INT)
            raise serializers.ValidationError("El modo simulado no está disponible en este entorno")
        return value
