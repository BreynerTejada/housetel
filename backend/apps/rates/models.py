"""Rates (spec §4): taxes, policies, base/derived plans, defaults, seasons, the DailyRate grid,
extras and promos.

Date conventions: `Season.end_date` is inclusive; DailyRate has one row per night.
"""

import builtins

from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.fields import i18n_field, json_field, money_field
from apps.core.i18n import t
from apps.core.models import BaseModel, Property
from apps.inventory.models import RoomType


class Tax(BaseModel):
    class AppliesTo(models.TextChoices):
        ROOM = "room", "Alojamiento"
        EXTRAS = "extras", "Extras"
        ALL = "all", "Todo"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="taxes")
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=5, decimal_places=2)  # percent: 19.00
    applies_to = models.CharField(max_length=10, choices=AppliesTo.choices, default=AppliesTo.ROOM)
    included_in_price = models.BooleanField(default=False)
    exempt_foreign_non_residents = models.BooleanField(default=False)  # ET art. 481 lit. d
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "taxes"
        constraints = [models.UniqueConstraint(fields=["property", "code"], name="tax_code_unique")]

    def __str__(self) -> str:
        return f"{self.name} ({self.rate}%)"


class CancellationPolicy(BaseModel):
    class PenaltyType(models.TextChoices):
        FIRST_NIGHT = "first_night", "Primera noche"
        PERCENT = "percent", "Porcentaje del total"
        FULL = "full", "Total de la reserva"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="cancellation_policies")
    name = i18n_field()
    non_refundable = models.BooleanField(default=False)
    free_until_hours_before = models.PositiveIntegerField(default=48)  # before check-in date + check_in_time
    penalty_type = models.CharField(
        max_length=20, choices=PenaltyType.choices, default=PenaltyType.FIRST_NIGHT
    )
    penalty_value = models.DecimalField(max_digits=7, decimal_places=2, default=0)  # percent for PERCENT
    description = i18n_field()

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "cancellation policies"

    def __str__(self) -> str:
        return t(self.name) or str(self.pk)


class RatePlan(BaseModel):
    """Base plans have their own prices (DailyRate grid); derived plans are parent ± percent/amount."""

    class Kind(models.TextChoices):
        BASE = "base", "Base"
        DERIVED = "derived", "Derivado"

    class DerivationType(models.TextChoices):
        PERCENT = "percent", "Porcentaje"
        AMOUNT = "amount", "Monto"

    class MealPlan(models.TextChoices):
        ROOM_ONLY = "room_only", "Solo alojamiento"
        BREAKFAST = "breakfast", "Con desayuno"
        HALF_BOARD = "half_board", "Media pensión"
        FULL_BOARD = "full_board", "Pensión completa"
        ALL_INCLUSIVE = "all_inclusive", "Todo incluido"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="rate_plans")
    code = models.CharField(max_length=20)
    name = i18n_field()
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.BASE)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.RESTRICT, related_name="children"
    )
    derivation_type = models.CharField(
        max_length=10, choices=DerivationType.choices, default=DerivationType.PERCENT, blank=True
    )
    derivation_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # ±
    room_types = models.ManyToManyField(RoomType, blank=True, related_name="rate_plans")
    meal_plan = models.CharField(max_length=20, choices=MealPlan.choices, default=MealPlan.ROOM_ONLY)
    cancellation_policy = models.ForeignKey(
        CancellationPolicy, null=True, blank=True, on_delete=models.SET_NULL, related_name="rate_plans"
    )
    deposit_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_public = models.BooleanField(default=True)
    channels = json_field(default=list)  # [] = all; "direct", "marketplace", "booking_engine", OTA codes
    min_los_default = models.PositiveSmallIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["property", "code"], name="rate_plan_code_unique"),
            models.CheckConstraint(
                condition=Q(kind="base", parent__isnull=True) | Q(kind="derived", parent__isnull=False),
                name="rate_plan_parent_matches_kind",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} · {t(self.name)}"

    @builtins.property  # the `property` FK shadows the builtin inside the class body
    def base_plan(self) -> "RatePlan":
        return self if self.kind == self.Kind.BASE else self.parent


class RoomTypeRateDefaults(BaseModel):
    """Default price of a category in a base plan (used when no DailyRate/SeasonRate applies)."""

    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="rate_defaults")
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name="room_type_defaults")
    price = money_field()
    dow_adjustments = json_field()  # percent by weekday: {"mon": 0, ..., "fri": 10, "sat": 15, "sun": 0}
    extra_adult_price = money_field(default=0)
    extra_child_price = money_field(default=0)
    child_age_limit = models.PositiveSmallIntegerField(default=12)
    single_occupancy_price = money_field(null=True, blank=True)

    class Meta:
        verbose_name_plural = "room type rate defaults"
        constraints = [
            models.UniqueConstraint(fields=["room_type", "rate_plan"], name="room_type_rate_defaults_unique")
        ]

    def __str__(self) -> str:
        return f"{self.room_type} / {self.rate_plan}: {self.price}"


class Season(BaseModel):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="seasons")
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()  # inclusive
    priority = models.SmallIntegerField(default=0)  # higher wins when seasons overlap
    color = models.CharField(max_length=7, default="#B98A2E")

    class Meta:
        ordering = ["start_date"]
        constraints = [
            models.CheckConstraint(condition=Q(end_date__gte=F("start_date")), name="season_dates_valid")
        ]

    def __str__(self) -> str:
        return self.name


class SeasonRate(BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="rates")
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="season_rates")
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name="season_rates")
    price = money_field()
    dow_adjustments = json_field()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["season", "room_type", "rate_plan"], name="season_rate_unique")
        ]

    def __str__(self) -> str:
        return f"{self.season} / {self.room_type}: {self.price}"


class DailyRate(BaseModel):
    """Materialized grid (base plans only). Dates without a row resolve season → defaults."""

    class Source(models.TextChoices):
        DEFAULT = "default", "Por defecto"
        SEASON = "season", "Temporada"
        MANUAL = "manual", "Manual"
        REVENUE = "revenue", "Revenue"
        BULK = "bulk", "Edición masiva"
        CHANNEL = "channel", "Canal"

    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name="daily_rates")
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name="daily_rates")
    date = models.DateField()
    price = money_field()
    extra_adult_price = money_field(null=True, blank=True)  # null → RoomTypeRateDefaults
    extra_child_price = money_field(null=True, blank=True)
    min_los = models.PositiveSmallIntegerField(null=True, blank=True)
    max_los = models.PositiveSmallIntegerField(null=True, blank=True)
    closed_to_arrival = models.BooleanField(default=False)
    closed_to_departure = models.BooleanField(default=False)
    stop_sell = models.BooleanField(default=False)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["room_type", "rate_plan", "date"], name="daily_rate_unique")
        ]
        indexes = [models.Index(fields=["rate_plan", "date"], name="daily_rate_plan_date_idx")]

    def __str__(self) -> str:
        return f"{self.room_type} {self.date}: {self.price}"


class Extra(BaseModel):
    class ChargeType(models.TextChoices):
        PER_STAY = "per_stay", "Por estadía"
        PER_NIGHT = "per_night", "Por noche"
        PER_PERSON = "per_person", "Por persona"
        PER_PERSON_NIGHT = "per_person_night", "Por persona por noche"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="extras")
    code = models.CharField(max_length=20)
    name = i18n_field()
    price = money_field()
    charge_type = models.CharField(max_length=20, choices=ChargeType.choices, default=ChargeType.PER_STAY)
    tax = models.ForeignKey(Tax, null=True, blank=True, on_delete=models.SET_NULL, related_name="extras")
    sellable_online = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["property", "code"], name="extra_code_unique")]

    def __str__(self) -> str:
        return t(self.name) or self.code


class PromoCode(BaseModel):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Porcentaje"
        AMOUNT = "amount", "Monto por noche"

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name="promo_codes")
    code = models.CharField(max_length=40)
    discount_type = models.CharField(
        max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT
    )
    value = models.DecimalField(max_digits=12, decimal_places=2)
    valid_from = models.DateField(null=True, blank=True)  # booking window
    valid_to = models.DateField(null=True, blank=True)
    stay_from = models.DateField(null=True, blank=True)  # stay window
    stay_to = models.DateField(null=True, blank=True)
    rate_plans = models.ManyToManyField(RatePlan, blank=True, related_name="promo_codes")  # empty = all
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["property", "code"], name="promo_code_unique")]

    def __str__(self) -> str:
        return self.code
