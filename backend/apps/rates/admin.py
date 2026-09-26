from django.contrib import admin

from apps.rates.models import (
    CancellationPolicy,
    DailyRate,
    Extra,
    PromoCode,
    RatePlan,
    RoomTypeRateDefaults,
    Season,
    SeasonRate,
    Tax,
)


@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "name",
        "property",
        "rate",
        "applies_to",
        "included_in_price",
        "exempt_foreign_non_residents",
        "is_active",
    ]
    list_filter = ["applies_to", "is_active"]
    list_select_related = ["property"]


@admin.register(CancellationPolicy)
class CancellationPolicyAdmin(admin.ModelAdmin):
    list_display = ["__str__", "property", "non_refundable", "free_until_hours_before", "penalty_type"]
    list_select_related = ["property"]


@admin.register(RatePlan)
class RatePlanAdmin(admin.ModelAdmin):
    list_display = ["__str__", "property", "kind", "parent", "meal_plan", "is_public", "is_active"]
    list_filter = ["kind", "meal_plan", "is_public", "is_active"]
    list_select_related = ["property", "parent"]
    filter_horizontal = ["room_types"]


@admin.register(RoomTypeRateDefaults)
class RoomTypeRateDefaultsAdmin(admin.ModelAdmin):
    list_display = ["room_type", "rate_plan", "price", "extra_adult_price", "extra_child_price"]
    list_select_related = ["room_type", "rate_plan"]


class SeasonRateInline(admin.TabularInline):
    model = SeasonRate
    extra = 0


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = ["name", "property", "start_date", "end_date", "priority"]
    list_select_related = ["property"]
    inlines = [SeasonRateInline]


@admin.register(SeasonRate)
class SeasonRateAdmin(admin.ModelAdmin):
    list_display = ["season", "room_type", "rate_plan", "price"]
    list_select_related = ["season", "room_type", "rate_plan"]


@admin.register(DailyRate)
class DailyRateAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "room_type",
        "rate_plan",
        "price",
        "min_los",
        "closed_to_arrival",
        "closed_to_departure",
        "stop_sell",
        "source",
    ]
    list_filter = ["source", "stop_sell"]
    list_select_related = ["room_type", "rate_plan"]
    date_hierarchy = "date"
    raw_id_fields = ["room_type", "rate_plan", "updated_by"]


@admin.register(Extra)
class ExtraAdmin(admin.ModelAdmin):
    list_display = ["code", "__str__", "property", "price", "charge_type", "sellable_online", "is_active"]
    list_filter = ["charge_type", "is_active"]
    list_select_related = ["property"]


@admin.register(PromoCode)
class PromoCodeAdmin(admin.ModelAdmin):
    list_display = ["code", "property", "discount_type", "value", "uses", "max_uses", "is_active"]
    list_filter = ["discount_type", "is_active"]
    list_select_related = ["property"]
    filter_horizontal = ["rate_plans"]
