"""Serializers of the rates API. Every related object must belong to the request's property
(`X-Property-Id`); a foreign id is rejected as a validation error of its field."""

from decimal import Decimal, InvalidOperation

from rest_framework import serializers

from apps.core.errors import DomainError
from apps.inventory.models import RoomType
from apps.rates.models import (
    CancellationPolicy,
    Extra,
    PromoCode,
    RatePlan,
    RoomTypeRateDefaults,
    Season,
    SeasonRate,
    Tax,
)
from apps.rates.services.promos import normalize_code
from apps.rates.services.resolution import WEEKDAYS

MAX_GRID_DAYS = 186
MAX_BULK_DAYS = 366
MAX_QUOTE_NIGHTS = 366
LANGS = ("es", "en")


def request_property(serializer):
    request = serializer.context.get("request")
    return getattr(request, "property", None)


class ScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """Primary key of an object of the request's property; `scope(property)` returns the allowed queryset."""

    def __init__(self, *, model, scope, **kwargs):
        self.model = model
        self.scope = scope
        kwargs.setdefault("queryset", model.objects.none())
        super().__init__(**kwargs)

    def get_queryset(self):
        prop = request_property(self.root) if self.root is not None else None
        return self.scope(prop) if prop is not None else self.model.objects.none()


def scoped(model, path="property", **kwargs):
    return ScopedPrimaryKeyRelatedField(
        model=model, scope=lambda prop: model.objects.filter(**{path: prop}), **kwargs
    )


class I18nField(serializers.JSONField):
    """Translatable text `{"es": str, "en": str}`; Spanish is required unless `require_es=False`."""

    def __init__(self, *, require_es=True, **kwargs):
        self.require_es = require_es
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError('Debe ser un objeto {"es": ..., "en": ...}')
        unknown = set(data) - set(LANGS)
        if unknown:
            raise serializers.ValidationError(f"Idiomas no soportados: {', '.join(sorted(unknown))}")
        clean = {}
        for lang in LANGS:
            value = data.get(lang) or ""
            if not isinstance(value, str):
                raise serializers.ValidationError("Cada traducción debe ser un texto")
            clean[lang] = value.strip()
        if self.require_es and not clean["es"]:
            raise serializers.ValidationError("El texto en español es obligatorio")
        return clean


class WeekdayAdjustmentsField(serializers.JSONField):
    """Percentages by weekday: `{"fri": 10, "sat": 15}` (keys mon…sun, values between -100 and 1000)."""

    def to_internal_value(self, data):
        if data in (None, ""):
            return {}
        if not isinstance(data, dict):
            raise serializers.ValidationError('Debe ser un objeto {"mon": 0, …, "sun": 0}')
        clean = {}
        for key, value in data.items():
            if key not in WEEKDAYS:
                raise serializers.ValidationError(f"Día inválido: {key} (usa {', '.join(WEEKDAYS)})")
            if isinstance(value, bool):
                raise serializers.ValidationError("Los ajustes son porcentajes numéricos")
            try:
                number = Decimal(str(value))
            except InvalidOperation:
                raise serializers.ValidationError("Los ajustes son porcentajes numéricos") from None
            if not number.is_finite() or not Decimal("-100") <= number <= Decimal("1000"):
                raise serializers.ValidationError("Cada ajuste debe estar entre -100 % y 1000 %")
            clean[key] = int(number) if number == number.to_integral_value() else float(number)
        return clean


def money(**kwargs):
    kwargs.setdefault("min_value", Decimal("0"))
    return serializers.DecimalField(max_digits=14, decimal_places=2, **kwargs)


class UniqueCodeMixin:
    """Codes are unique per property (`code_model`, compared without case when `code_iexact`)."""

    code_model = None
    code_iexact = False

    def validate_code(self, value):
        value = value.strip()
        lookup = {"code__iexact" if self.code_iexact else "code": value}
        clashes = self.code_model.objects.filter(property=request_property(self), **lookup)
        if self.instance is not None:
            clashes = clashes.exclude(pk=self.instance.pk)
        if clashes.exists():
            raise serializers.ValidationError("Ya existe un registro con este código en la propiedad")
        return value


# ---- configuration ------------------------------------------------------------------------------


class TaxSerializer(UniqueCodeMixin, serializers.ModelSerializer):
    code_model = Tax
    rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100")
    )

    class Meta:
        model = Tax
        fields = [
            "id",
            "code",
            "name",
            "rate",
            "applies_to",
            "included_in_price",
            "exempt_foreign_non_residents",
            "is_active",
        ]


class CancellationPolicySerializer(serializers.ModelSerializer):
    name = I18nField()
    description = I18nField(require_es=False, required=False)
    free_until_hours_before = serializers.IntegerField(min_value=0, max_value=8760, required=False)
    penalty_value = serializers.DecimalField(
        max_digits=7, decimal_places=2, min_value=Decimal("0"), required=False
    )
    plans_count = serializers.SerializerMethodField()

    class Meta:
        model = CancellationPolicy
        fields = [
            "id",
            "name",
            "non_refundable",
            "free_until_hours_before",
            "penalty_type",
            "penalty_value",
            "description",
            "plans_count",
        ]

    def get_plans_count(self, obj) -> int:
        annotated = getattr(obj, "plans_count", None)
        return annotated if annotated is not None else obj.rate_plans.count()

    def validate(self, attrs):
        penalty_type = attrs.get("penalty_type", getattr(self.instance, "penalty_type", None))
        value = attrs.get("penalty_value", getattr(self.instance, "penalty_value", Decimal("0")))
        if penalty_type == CancellationPolicy.PenaltyType.PERCENT and value > 100:
            raise serializers.ValidationError({"penalty_value": ["El porcentaje no puede superar 100"]})
        return attrs


class RatePlanSerializer(UniqueCodeMixin, serializers.ModelSerializer):
    code_model = RatePlan
    name = I18nField()
    parent = scoped(RatePlan, allow_null=True, required=False)
    room_types = scoped(RoomType, many=True, required=False)
    cancellation_policy = scoped(CancellationPolicy, allow_null=True, required=False)
    derivation_value = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    deposit_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), max_value=Decimal("100"), required=False
    )
    min_los_default = serializers.IntegerField(min_value=1, max_value=365, required=False)
    channels = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, allow_empty=True
    )
    children = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = RatePlan
        fields = [
            "id",
            "code",
            "name",
            "kind",
            "parent",
            "derivation_type",
            "derivation_value",
            "room_types",
            "meal_plan",
            "cancellation_policy",
            "deposit_percent",
            "is_public",
            "channels",
            "min_los_default",
            "is_active",
            "sort_order",
            "children",
        ]

    def validate_channels(self, value):
        return list(dict.fromkeys(channel.strip().lower() for channel in value))

    def validate(self, attrs):
        instance = self.instance
        kind = attrs.get("kind", instance.kind if instance else RatePlan.Kind.BASE)
        parent = attrs["parent"] if "parent" in attrs else (instance.parent if instance else None)
        if "room_types" in attrs:
            room_type_ids = {rt.pk for rt in attrs["room_types"]}
        else:
            room_type_ids = set(instance.room_types.values_list("pk", flat=True)) if instance else set()

        if kind == RatePlan.Kind.BASE:
            if parent is not None:
                raise serializers.ValidationError({"parent": ["Un plan base no tiene plan padre"]})
            attrs["parent"] = None
            attrs["derivation_value"] = Decimal("0")
            if instance is not None:
                for child in instance.children.prefetch_related("room_types"):
                    missing = {rt.pk for rt in child.room_types.all()} - room_type_ids
                    if missing:
                        raise serializers.ValidationError(
                            {"room_types": [f"El plan derivado {child.code} vende categorías que quitaste"]}
                        )
            return attrs

        if parent is None:
            raise serializers.ValidationError({"parent": ["Un plan derivado necesita su plan base"]})
        if instance is not None and parent.pk == instance.pk:
            raise serializers.ValidationError({"parent": ["Un plan no puede derivar de sí mismo"]})
        if parent.kind != RatePlan.Kind.BASE:
            message = "Un plan derivado solo puede derivar de un plan base"
            raise DomainError(message, code="parent_not_base", fields={"parent": [message]})
        if instance is not None and instance.children.exists():
            message = "Este plan tiene planes derivados: no puede volverse derivado"
            raise DomainError(message, code="plan_has_children", fields={"kind": [message]})
        parent_types = set(parent.room_types.values_list("pk", flat=True))
        if not room_type_ids <= parent_types:
            raise serializers.ValidationError(
                {"room_types": ["Un plan derivado solo vende categorías de su plan base"]}
            )
        derivation_type = attrs.get(
            "derivation_type", instance.derivation_type if instance else RatePlan.DerivationType.PERCENT
        )
        if derivation_type not in RatePlan.DerivationType.values:
            raise serializers.ValidationError(
                {"derivation_type": ["Elige cómo se calcula: porcentaje o monto"]}
            )
        value = attrs.get("derivation_value", instance.derivation_value if instance else Decimal("0"))
        if derivation_type == RatePlan.DerivationType.PERCENT and value < -100:
            raise serializers.ValidationError(
                {"derivation_value": ["Un descuento porcentual no puede superar el 100 %"]}
            )
        return attrs


class BasePlanOnlyMixin:
    def validate_rate_plan(self, plan):
        if plan.kind != RatePlan.Kind.BASE:
            raise serializers.ValidationError("Los precios se configuran en planes base")
        return plan


class RoomTypeRateDefaultsSerializer(BasePlanOnlyMixin, serializers.ModelSerializer):
    room_type = scoped(RoomType)
    rate_plan = scoped(RatePlan)
    price = money()
    dow_adjustments = WeekdayAdjustmentsField(required=False)
    extra_adult_price = money(required=False)
    extra_child_price = money(required=False)
    child_age_limit = serializers.IntegerField(min_value=0, max_value=17, required=False)
    single_occupancy_price = money(required=False, allow_null=True)

    class Meta:
        model = RoomTypeRateDefaults
        fields = [
            "id",
            "room_type",
            "rate_plan",
            "price",
            "dow_adjustments",
            "extra_adult_price",
            "extra_child_price",
            "child_age_limit",
            "single_occupancy_price",
        ]
        validators: list = []  # POST upserts by (room_type, rate_plan)


class SeasonRateNestedSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeasonRate
        fields = ["id", "room_type", "rate_plan", "price", "dow_adjustments"]
        read_only_fields = fields


class SeasonSerializer(serializers.ModelSerializer):
    color = serializers.RegexField(r"^#[0-9A-Fa-f]{6}$", required=False)
    rates = SeasonRateNestedSerializer(many=True, read_only=True)

    class Meta:
        model = Season
        fields = ["id", "name", "start_date", "end_date", "priority", "color", "rates"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": ["La temporada no puede terminar antes de empezar"]}
            )
        return attrs


class SeasonRateSerializer(BasePlanOnlyMixin, serializers.ModelSerializer):
    season = scoped(Season)
    room_type = scoped(RoomType)
    rate_plan = scoped(RatePlan)
    price = money()
    dow_adjustments = WeekdayAdjustmentsField(required=False)

    class Meta:
        model = SeasonRate
        fields = ["id", "season", "room_type", "rate_plan", "price", "dow_adjustments"]
        validators: list = []  # POST upserts by (season, room_type, rate_plan)


class ExtraSerializer(UniqueCodeMixin, serializers.ModelSerializer):
    code_model = Extra
    name = I18nField()
    price = money()
    tax = scoped(Tax, allow_null=True, required=False)

    class Meta:
        model = Extra
        fields = ["id", "code", "name", "price", "charge_type", "tax", "sellable_online", "is_active"]

    def validate_tax(self, tax):
        if tax is not None and tax.applies_to not in (Tax.AppliesTo.EXTRAS, Tax.AppliesTo.ALL):
            raise serializers.ValidationError("Usa un impuesto que aplique a extras")
        return tax


class PromoCodeSerializer(UniqueCodeMixin, serializers.ModelSerializer):
    code_model = PromoCode
    code_iexact = True
    code = serializers.RegexField(
        r"^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$",
        error_messages={"invalid": "Usa de 2 a 40 letras, números, guiones o guiones bajos"},
    )
    value = serializers.DecimalField(max_digits=12, decimal_places=2)
    rate_plans = scoped(RatePlan, many=True, required=False)
    max_uses = serializers.IntegerField(min_value=1, allow_null=True, required=False)

    class Meta:
        model = PromoCode
        fields = [
            "id",
            "code",
            "discount_type",
            "value",
            "valid_from",
            "valid_to",
            "stay_from",
            "stay_to",
            "rate_plans",
            "max_uses",
            "uses",
            "is_active",
        ]
        read_only_fields = ["uses"]

    def validate_code(self, value):
        return normalize_code(super().validate_code(value))

    def validate(self, attrs):
        def current(field):
            return attrs.get(field, getattr(self.instance, field, None))

        discount_type = current("discount_type") or PromoCode.DiscountType.PERCENT
        value = current("value")
        if value is not None:
            if value <= 0:
                raise serializers.ValidationError({"value": ["El descuento debe ser mayor que cero"]})
            if discount_type == PromoCode.DiscountType.PERCENT and value > 100:
                raise serializers.ValidationError({"value": ["El porcentaje no puede superar 100"]})
        for first, last in (("valid_from", "valid_to"), ("stay_from", "stay_to")):
            if current(first) and current(last) and current(last) < current(first):
                raise serializers.ValidationError(
                    {last: ["La fecha final no puede ser anterior a la inicial"]}
                )
        return attrs


class RoomTypeLookupSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomType
        fields = [
            "id",
            "code",
            "name",
            "kind",
            "color",
            "base_occupancy",
            "max_adults",
            "max_children",
            "max_occupancy",
            "is_active",
            "sort_order",
        ]
        read_only_fields = fields


# ---- grid, bulk, quote, holidays ------------------------------------------------------------------


class DateRangeMixin:
    max_days = MAX_GRID_DAYS

    def validate_range(self, attrs):
        start, end = attrs["start"], attrs["end"]
        if end <= start:
            raise serializers.ValidationError({"end": ["La fecha final debe ser posterior a la inicial"]})
        if (end - start).days > self.max_days:
            raise serializers.ValidationError({"end": [f"El rango no puede superar {self.max_days} días"]})
        return attrs


def language_field():
    """`?lang=es|en`: language of the holiday names (default: the user's). The screen asks for the language it
    shows, because it switches before the user's profile is saved."""
    return serializers.ChoiceField(choices=LANGS, required=False)


class GridQuerySerializer(DateRangeMixin, serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()
    rate_plan = scoped(RatePlan, required=False, allow_null=True)
    lang = language_field()

    def validate(self, attrs):
        return self.validate_range(attrs)


class BulkSetSerializer(serializers.Serializer):
    price = money(required=False)
    price_delta_percent = serializers.DecimalField(
        max_digits=7, decimal_places=2, min_value=Decimal("-100"), required=False
    )
    price_delta_amount = serializers.DecimalField(max_digits=14, decimal_places=2, required=False)
    min_los = serializers.IntegerField(min_value=1, max_value=365, allow_null=True, required=False)
    max_los = serializers.IntegerField(min_value=1, max_value=365, allow_null=True, required=False)
    cta = serializers.BooleanField(required=False)
    ctd = serializers.BooleanField(required=False)
    stop_sell = serializers.BooleanField(required=False)

    PRICE_FIELDS = ("price", "price_delta_percent", "price_delta_amount")

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Elige al menos un cambio")
        if sum(field in attrs for field in self.PRICE_FIELDS) > 1:
            raise serializers.ValidationError(
                "Cambia el precio de una sola forma: exacto, porcentaje o monto"
            )
        return attrs


class GridBulkSerializer(DateRangeMixin, serializers.Serializer):
    max_days = MAX_BULK_DAYS

    room_type_ids = scoped(RoomType, many=True, allow_empty=False)
    rate_plan_id = scoped(RatePlan)
    start = serializers.DateField()
    end = serializers.DateField()
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6), required=False, allow_empty=True
    )
    set = BulkSetSerializer()
    source = serializers.ChoiceField(choices=["manual", "bulk"], default="bulk")

    def validate(self, attrs):
        attrs = self.validate_range(attrs)
        sold = set(attrs["rate_plan_id"].room_types.values_list("pk", flat=True))
        if any(room_type.pk not in sold for room_type in attrs["room_type_ids"]):
            raise serializers.ValidationError(
                {"room_type_ids": ["El plan no vende alguna de las categorías"]}
            )
        return attrs


class GridBulkResultSerializer(serializers.Serializer):
    updated = serializers.IntegerField()
    audit_event_id = serializers.UUIDField(allow_null=True)


class QuoteRequestSerializer(serializers.Serializer):
    room_type_id = scoped(RoomType)
    rate_plan_id = scoped(RatePlan)
    checkin = serializers.DateField()
    checkout = serializers.DateField()
    adults = serializers.IntegerField(min_value=1, max_value=50, default=2)
    children = serializers.IntegerField(min_value=0, max_value=50, default=0)
    children_ages = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=17), required=False, default=list
    )
    promo_code = serializers.CharField(required=False, allow_blank=True, max_length=40, default="")
    guest_is_foreign_non_resident = serializers.BooleanField(default=False)

    def validate(self, attrs):
        # dates in the wrong order are left to the quote (`invalid_dates`); a stay longer than a year is not
        if (attrs["checkout"] - attrs["checkin"]).days > MAX_QUOTE_NIGHTS:
            raise serializers.ValidationError({"checkout": [f"Cotiza como máximo {MAX_QUOTE_NIGHTS} noches"]})
        return attrs


class HolidaysQuerySerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=2000, max_value=2100, required=False)
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False)
    lang = language_field()

    def validate(self, attrs):
        if ("start" in attrs) != ("end" in attrs):
            raise serializers.ValidationError({"end": ["Envía start y end juntos"]})
        if "start" in attrs and attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": ["La fecha final debe ser posterior a la inicial"]})
        return attrs


class HolidaySerializer(serializers.Serializer):
    date = serializers.DateField()
    name = serializers.CharField()
