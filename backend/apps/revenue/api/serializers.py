"""Serializers of the revenue API. Related ids (categories, plans, rules) must belong to the request's
property (`X-Property-Id`); a foreign id is a validation error of its field. Money and percentages are
strings."""

from rest_framework import serializers

from apps.inventory.models import RoomType
from apps.rates.models import RatePlan
from apps.revenue.models import PriceBounds, PricingRule, RateRecommendation, RevenueRun, RevenueSettings
from apps.revenue.rules import clean_params

MAX_IDS = 1000
MAX_RANGE_DAYS = 366
MAX_CALENDAR_DAYS = 186


def request_property(serializer):
    request = serializer.context.get("request")
    return getattr(request, "property", None)


class ScopedRelatedField(serializers.PrimaryKeyRelatedField):
    """Primary key of an object of the request's property (`scope(property)` → allowed queryset)."""

    def __init__(self, *, model, scope, **kwargs):
        self.model, self.scope = model, scope
        kwargs.setdefault("queryset", model.objects.none())
        super().__init__(**kwargs)

    def get_queryset(self):
        prop = request_property(self.root) if self.root is not None else None
        return self.scope(prop) if prop is not None else self.model.objects.none()


def user_ref(user) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.pk), "full_name": user.full_name, "email": user.email}


def room_type_ref(room_type) -> dict:
    return {"id": str(room_type.pk), "code": room_type.code, "name": room_type.name, "color": room_type.color}


def rate_plan_ref(plan) -> dict:
    return {"id": str(plan.pk), "code": plan.code, "name": plan.name}


class RevenueSettingsSerializer(serializers.ModelSerializer):
    price_rounding = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, max_value=1_000_000
    )

    class Meta:
        model = RevenueSettings
        fields = [
            "enabled",
            "auto_apply",
            "horizon_days",
            "max_daily_change_percent",
            "min_change_percent",
            "price_rounding",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


class PricingRuleSerializer(serializers.ModelSerializer):
    room_types = ScopedRelatedField(
        many=True,
        required=False,
        model=RoomType,
        scope=lambda prop: RoomType.objects.filter(property=prop),
    )

    class Meta:
        model = PricingRule
        fields = [
            "id",
            "name",
            "kind",
            "room_types",
            "params",
            "priority",
            "combine",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Ponle un nombre a la regla")
        return value

    def validate(self, attrs):
        instance = self.instance
        kind = attrs.get("kind", instance.kind if instance else None)
        params = attrs.get("params", instance.params if instance else None)
        attrs["params"] = clean_params(
            kind, params
        )  # DomainError invalid_rule_params → 400 with fields.params
        return attrs


class PriceBoundsSerializer(serializers.ModelSerializer):
    room_type = ScopedRelatedField(model=RoomType, scope=lambda prop: RoomType.objects.filter(property=prop))
    rate_plan = ScopedRelatedField(model=RatePlan, scope=lambda prop: RatePlan.objects.filter(property=prop))
    min_price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    max_price = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)

    class Meta:
        model = PriceBounds
        fields = ["id", "room_type", "rate_plan", "min_price", "max_price", "updated_at"]
        read_only_fields = ["id", "updated_at"]
        validators = []  # (room_type, rate_plan) is an upsert key, not a uniqueness error

    def validate(self, attrs):
        instance = self.instance
        room_type = attrs.get("room_type", instance.room_type if instance else None)
        plan = attrs.get("rate_plan", instance.rate_plan if instance else None)
        low = attrs.get("min_price", instance.min_price if instance else None)
        high = attrs.get("max_price", instance.max_price if instance else None)
        errors = {}
        if plan is not None and plan.kind != RatePlan.Kind.BASE:
            errors["rate_plan"] = ["Los límites se fijan en planes base: los derivados siguen a su plan base"]
        elif (
            plan is not None
            and room_type is not None
            and not plan.room_types.filter(pk=room_type.pk).exists()
        ):
            errors["room_type"] = ["El plan no vende esta categoría"]
        if low is None and high is None:
            errors["min_price"] = ["Indica un precio mínimo, un máximo o ambos"]
        for field, value in (("min_price", low), ("max_price", high)):
            if value is not None and value <= 0:
                errors[field] = ["El precio debe ser mayor que 0"]
        if low is not None and high is not None and low > high:
            errors["max_price"] = ["El máximo no puede ser menor que el mínimo"]
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


class RecommendationSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    room_type = serializers.SerializerMethodField()
    rate_plan = serializers.SerializerMethodField()
    decided_by = serializers.SerializerMethodField()
    run = serializers.SerializerMethodField()

    class Meta:
        model = RateRecommendation
        fields = [
            "id",
            "room_type",
            "rate_plan",
            "date",
            "current_price",
            "current_source",
            "anchor_price",
            "anchor_source",
            "recommended_price",
            "change_percent",
            "adjustment_percent",
            "occupancy",
            "available_units",
            "reasons",
            "explanation",
            "status",
            "decided_by",
            "decided_at",
            "applied_at",
            "apply_error",
            "run",
            "created_at",
        ]

    def get_id(self, obj) -> str | None:
        return None if obj._state.adding else str(obj.pk)  # simulated recommendations are never saved

    def get_room_type(self, obj) -> dict:
        return room_type_ref(obj.room_type)

    def get_rate_plan(self, obj) -> dict:
        return rate_plan_ref(obj.rate_plan)

    def get_decided_by(self, obj) -> dict | None:
        return user_ref(obj.decided_by) if obj.decided_by_id else None

    def get_run(self, obj) -> str | None:
        return str(obj.run_id) if obj.run_id else None


class RunSerializer(serializers.ModelSerializer):
    triggered_by = serializers.SerializerMethodField()

    class Meta:
        model = RevenueRun
        fields = [
            "id",
            "started_at",
            "finished_at",
            "status",
            "trigger",
            "triggered_by",
            "start_date",
            "end_date",
            "recommendations_count",
            "auto_applied_count",
            "expired_count",
            "summary",
            "ai_summary",
            "ai_provider",
            "details",
        ]

    def get_triggered_by(self, obj) -> dict | None:
        return user_ref(obj.triggered_by) if obj.triggered_by_id else None


class DecisionSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=MAX_IDS)


class RangeSerializer(serializers.Serializer):
    start = serializers.DateField(required=False)
    end = serializers.DateField(required=False, help_text="Exclusivo")
    max_days = MAX_RANGE_DAYS

    def validate(self, attrs):
        start, end = attrs.get("start"), attrs.get("end")
        if start and end:
            if end <= start:
                raise serializers.ValidationError({"end": ["El fin debe ser posterior al inicio"]})
            if (end - start).days > self.max_days:
                raise serializers.ValidationError({"end": [f"El rango máximo es de {self.max_days} días"]})
        return attrs


class CalendarQuerySerializer(RangeSerializer):
    start = serializers.DateField()
    end = serializers.DateField(help_text="Exclusivo")
    lang = serializers.ChoiceField(choices=["es", "en"], required=False)
    max_days = MAX_CALENDAR_DAYS


class SimulateSerializer(RangeSerializer):
    rule = serializers.DictField(
        required=False, help_text="Regla en borrador (con `id` para reemplazar una guardada)"
    )
