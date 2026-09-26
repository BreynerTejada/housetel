from django.contrib import admin

from apps.finance.models import CashShift, Charge, Folio, Payment, PaymentIntent, Refund


class ChargeInline(admin.TabularInline):
    model = Charge
    fields = ["business_date", "kind", "description", "quantity", "amount", "tax_amount", "voided_at"]
    extra = 0
    show_change_link = True


class PaymentInline(admin.TabularInline):
    model = Payment
    fields = ["business_date", "method", "amount", "status", "provider_reference"]
    extra = 0
    show_change_link = True


@admin.register(Folio)
class FolioAdmin(admin.ModelAdmin):
    list_display = ["__str__", "property", "folio_type", "status", "currency", "closed_at"]
    list_filter = ["folio_type", "status"]
    list_select_related = ["property", "reservation"]
    search_fields = ["reservation__code"]
    raw_id_fields = ["reservation", "stay", "guest"]
    inlines = [ChargeInline, PaymentInline]


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ["business_date", "folio", "kind", "description", "amount", "tax_amount", "voided_at"]
    list_filter = ["kind"]
    list_select_related = ["folio", "folio__reservation"]
    date_hierarchy = "business_date"
    raw_id_fields = ["folio", "tax", "stay", "extra", "posted_by", "voided_by"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["business_date", "folio", "method", "amount", "status", "provider", "provider_reference"]
    list_filter = ["method", "status", "provider"]
    list_select_related = ["folio", "folio__reservation"]
    search_fields = ["provider_reference"]
    raw_id_fields = ["folio", "received_by"]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["payment", "amount", "status", "created_at"]
    list_filter = ["status"]
    list_select_related = ["payment"]
    raw_id_fields = ["payment", "approved_by"]


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ["reference", "property", "amount", "provider", "mode", "status", "expires_at"]
    list_filter = ["mode", "status", "provider"]
    list_select_related = ["property"]
    search_fields = ["reference"]
    raw_id_fields = ["folio"]


@admin.register(CashShift)
class CashShiftAdmin(admin.ModelAdmin):
    list_display = [
        "opened_at",
        "property",
        "user",
        "closed_at",
        "opening_float",
        "counted_cash",
        "difference",
    ]
    list_select_related = ["property", "user"]
    raw_id_fields = ["user"]
