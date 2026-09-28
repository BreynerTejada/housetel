"""Revenue management (plan C8): rules → recommended prices per category × base plan × night.

- `RevenueSettings` (1-1 with the property): on/off, auto-apply, horizon, maximum daily change, minimum
  change worth recommending and the commercial rounding of recommended prices.
- `PricingRule`: one rule of a kind (occupancy, lead time, day of week, holidays, event) with its params,
  the categories it applies to (none = all), a priority and how it combines with the others (stack | max).
- `PriceBounds`: floor/ceiling of a category in a base plan (a recommendation never leaves them).
- `RevenueRun`: one evaluation of the rules (scheduled, manual or seed) with its summaries.
- `RateRecommendation`: a proposed price for one night, with its reasons and explanation. At most one
  pending recommendation exists per (category, plan, night).
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.fields import i18n_field, json_field, money_field
from apps.core.models import BaseModel, Property
from apps.inventory.models import RoomType
from apps.rates.models import RatePlan

PERCENT = {"max_digits": 7, "decimal_places": 2}


class RevenueSettings(BaseModel):
    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="revenue_settings")
    enabled = models.BooleanField(default=True)
    auto_apply = models.BooleanField(default=False)
    horizon_days = models.PositiveSmallIntegerField(
        default=120, validators=[MinValueValidator(7), MaxValueValidator(365)]
    )
    max_daily_change_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=20,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )
    min_change_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
    )
    # Recommended prices are rounded to a multiple of this amount (0 = only the currency unit).
    price_rounding = models.DecimalField(max_digits=12, decimal_places=2, default=1000)

    class Meta:
        verbose_name_plural = "revenue settings"

    def __str__(self) -> str:
        return f"Revenue · {self.property}"


class PricingRule(BaseModel):
    class Kind(models.TextChoices):
        OCCUPANCY = "occupancy", "Ocupación"
        LEAD_TIME = "lead_time", "Anticipación"
        DAY_OF_WEEK = "day_of_week", "Día de la semana"
        HOLIDAY = "holiday", "Festivos y puentes"
        EVENT = "event", "Evento"

    class Combine(models.TextChoices):
        STACK = "stack", "Sumar"
        MAX = "max", "Máximo"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="pricing_rules")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    room_types = models.ManyToManyField(RoomType, blank=True, related_name="pricing_rules")  # none = all
    params = json_field()
    priority = models.PositiveSmallIntegerField(default=10)  # higher first (display, ties of `max`)
    combine = models.CharField(max_length=10, choices=Combine.choices, default=Combine.STACK)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-priority", "created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.kind})"


class PriceBounds(BaseModel):
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="price_bounds")
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name="price_bounds")
    min_price = money_field(null=True, blank=True)
    max_price = money_field(null=True, blank=True)

    class Meta:
        verbose_name_plural = "price bounds"
        ordering = ["rate_plan__sort_order", "room_type__sort_order", "room_type__code"]
        constraints = [
            models.UniqueConstraint(fields=["room_type", "rate_plan"], name="price_bounds_unique"),
            models.CheckConstraint(
                condition=Q(min_price__isnull=True)
                | Q(max_price__isnull=True)
                | Q(min_price__lte=F("max_price")),
                name="price_bounds_min_lte_max",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.room_type} · {self.rate_plan}: {self.min_price}–{self.max_price}"


class RevenueRun(BaseModel):
    class Status(models.TextChoices):
        RUNNING = "running", "En curso"
        SUCCESS = "success", "Exitosa"
        FAILED = "failed", "Fallida"

    class Trigger(models.TextChoices):
        AUTOMATION = "automation", "Programada"
        MANUAL = "manual", "Manual"
        SEED = "seed", "Datos de demo"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="revenue_runs")
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    trigger = models.CharField(max_length=12, choices=Trigger.choices, default=Trigger.AUTOMATION)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)  # exclusive
    recommendations_count = models.PositiveIntegerField(default=0)
    auto_applied_count = models.PositiveIntegerField(default=0)
    expired_count = models.PositiveIntegerField(default=0)
    summary = i18n_field()  # deterministic {"es", "en"}
    ai_summary = i18n_field()  # {"es", "en"} from the LLM; empty when it was not available
    ai_provider = models.CharField(max_length=40, blank=True)
    details = json_field()

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Revenue run {self.started_at:%Y-%m-%d %H:%M} · {self.property}"


class RateRecommendation(BaseModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        APPLIED = "applied", "Aplicada"
        AUTO_APPLIED = "auto_applied", "Aplicada automáticamente"
        EXPIRED = "expired", "Vencida"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="rate_recommendations")
    run = models.ForeignKey(
        RevenueRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="recommendations"
    )
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="rate_recommendations")
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name="rate_recommendations")
    date = models.DateField()
    current_price = money_field()
    current_source = models.CharField(max_length=20, blank=True)
    anchor_price = money_field()
    anchor_source = models.CharField(max_length=20, blank=True)
    adjustment_percent = models.DecimalField(default=0, **PERCENT)  # rules combined, over the anchor
    recommended_price = money_field()
    change_percent = models.DecimalField(**PERCENT)  # vs the current price
    occupancy = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    available_units = models.IntegerField(null=True, blank=True)
    reasons = json_field(default=list)
    explanation = i18n_field()
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    apply_error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["date", "room_type__sort_order", "room_type__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["room_type", "rate_plan", "date"],
                condition=Q(status="pending"),
                name="rate_recommendation_one_pending",
            ),
        ]
        indexes = [
            models.Index(fields=["property", "status", "date"], name="rate_rec_prop_status_date"),
            models.Index(fields=["room_type", "rate_plan", "date"], name="rate_rec_key_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.room_type} {self.date}: {self.current_price} → {self.recommended_price}"
