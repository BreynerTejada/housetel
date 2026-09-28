from django.contrib import admin

from apps.corporate.models import AccountPayment, AccountPaymentAllocation, Company, ReservationBilling


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = (
        "legal_name",
        "nit",
        "dv",
        "kind",
        "organization",
        "credit_enabled",
        "credit_limit",
        "is_active",
    )
    list_filter = ("kind", "credit_enabled", "is_active")
    search_fields = ("legal_name", "trade_name", "nit")


@admin.register(ReservationBilling)
class ReservationBillingAdmin(admin.ModelAdmin):
    list_display = ("reservation", "bill_to", "company", "purchase_order", "updated_at")
    list_filter = ("bill_to",)
    raw_id_fields = ("reservation", "company", "updated_by")


class AllocationInline(admin.TabularInline):
    model = AccountPaymentAllocation
    extra = 0
    raw_id_fields = ("folio", "payment")


@admin.register(AccountPayment)
class AccountPaymentAdmin(admin.ModelAdmin):
    list_display = ("company", "property", "amount", "method", "reference", "received_on", "status")
    list_filter = ("status", "method")
    raw_id_fields = ("company", "created_by", "voided_by")
    inlines = [AllocationInline]
