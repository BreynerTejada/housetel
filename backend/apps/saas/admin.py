from django.contrib import admin

from apps.saas.models import Commission, CommissionSettlement, Plan, PlatformInvoice, Subscription


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "max_units",
        "max_properties",
        "price_monthly",
        "price_yearly",
        "is_active",
        "sort",
    )
    list_editable = ("is_active", "sort")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("organization", "plan", "status", "billing_cycle", "current_period_end", "trial_ends_at")
    list_filter = ("status", "plan", "billing_cycle")
    search_fields = ("organization__name",)


@admin.register(PlatformInvoice)
class PlatformInvoiceAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "organization",
        "kind",
        "period_start",
        "total",
        "status",
        "due_date",
        "paid_at",
    )
    list_filter = ("status", "kind")
    search_fields = ("number", "organization__name")


@admin.register(CommissionSettlement)
class CommissionSettlementAdmin(admin.ModelAdmin):
    list_display = ("organization", "period_start", "total", "commissions_count", "status", "invoice")
    list_filter = ("status",)


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = (
        "reservation",
        "property",
        "basis",
        "base_amount",
        "rate",
        "amount",
        "status",
        "accrual_date",
    )
    list_filter = ("status", "basis", "property")
    search_fields = ("reservation__code",)
    raw_id_fields = ("reservation", "settlement")
