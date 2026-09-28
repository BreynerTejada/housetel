"""Django admin for revenue (support and debugging; the staff UI lives at /app/revenue). Recommendations and
runs are records of what the engine did: they are read-only here."""

from django.contrib import admin

from apps.revenue.models import PriceBounds, PricingRule, RateRecommendation, RevenueRun, RevenueSettings


@admin.register(RevenueSettings)
class RevenueSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "property",
        "enabled",
        "auto_apply",
        "horizon_days",
        "max_daily_change_percent",
        "min_change_percent",
    ]
    list_filter = ["enabled", "auto_apply"]
    list_select_related = ["property"]


@admin.register(PricingRule)
class PricingRuleAdmin(admin.ModelAdmin):
    list_display = ["name", "property", "kind", "combine", "priority", "is_active"]
    list_filter = ["kind", "combine", "is_active"]
    list_select_related = ["property"]
    filter_horizontal = ["room_types"]
    search_fields = ["name"]


@admin.register(PriceBounds)
class PriceBoundsAdmin(admin.ModelAdmin):
    list_display = ["room_type", "rate_plan", "min_price", "max_price"]
    list_select_related = ["room_type", "rate_plan"]


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(RevenueRun)
class RevenueRunAdmin(ReadOnlyAdmin):
    list_display = [
        "started_at",
        "property",
        "trigger",
        "status",
        "recommendations_count",
        "auto_applied_count",
    ]
    list_filter = ["trigger", "status"]
    list_select_related = ["property"]
    date_hierarchy = "started_at"


@admin.register(RateRecommendation)
class RateRecommendationAdmin(ReadOnlyAdmin):
    list_display = [
        "date",
        "property",
        "room_type",
        "rate_plan",
        "current_price",
        "recommended_price",
        "change_percent",
        "status",
    ]
    list_filter = ["status"]
    list_select_related = ["property", "room_type", "rate_plan"]
    date_hierarchy = "date"
