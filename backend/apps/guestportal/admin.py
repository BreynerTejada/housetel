from django.contrib import admin

from apps.guestportal.models import GuestPortalSettings, OnlineCheckin, ServiceRequest


@admin.register(GuestPortalSettings)
class GuestPortalSettingsAdmin(admin.ModelAdmin):
    list_display = ["property", "checkin_opens_days_before", "require_document_photo", "require_signature",
                    "auto_approve_extras"]  # fmt: skip
    list_select_related = ["property"]


@admin.register(OnlineCheckin)
class OnlineCheckinAdmin(admin.ModelAdmin):
    """The signature lives in private storage without URL: it is shown as signed / not signed only (the staff
    reads it through the authenticated API)."""

    list_display = ["reservation", "status", "current_step", "completed_at", "has_signature"]
    list_filter = ["status"]
    list_select_related = ["reservation"]
    exclude = ["signature"]
    readonly_fields = [
        "reservation",
        "has_signature",
        "accepted_terms_at",
        "completed_at",
        "ip",
        "user_agent",
    ]
    search_fields = ["reservation__code"]

    @admin.display(boolean=True, description="Firmado")
    def has_signature(self, obj):
        return bool(obj.signature)


@admin.register(ServiceRequest)
class ServiceRequestAdmin(admin.ModelAdmin):
    list_display = ["reservation", "kind", "status", "quantity", "price", "created_at"]
    list_filter = ["kind", "status"]
    list_select_related = ["reservation"]
    raw_id_fields = ["reservation", "extra", "charge", "decided_by"]
    search_fields = ["reservation__code"]
