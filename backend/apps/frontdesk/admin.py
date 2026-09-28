from django.contrib import admin

from apps.frontdesk.models import NightAuditReport


@admin.register(NightAuditReport)
class NightAuditReportAdmin(admin.ModelAdmin):
    list_display = ["business_date", "property", "status", "started_at", "finished_at", "triggered_by"]
    list_filter = ["status", "property"]
    date_hierarchy = "business_date"
    raw_id_fields = ["property", "run", "triggered_by"]
    readonly_fields = ["created_at", "updated_at"]
