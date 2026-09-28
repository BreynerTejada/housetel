"""Admin of compliance. Invoices, SIRE reports/records and TRA registrations are legal records: read-only here
(they are issued, corrected and annulled only through apps.compliance.services)."""

from django.contrib import admin

from apps.compliance.models import (
    ComplianceSettings,
    Invoice,
    InvoiceResolution,
    SireRecord,
    SireReport,
    TraRegistration,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ComplianceSettings)
class ComplianceSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "property",
        "go_live_date",
        "auto_issue_invoices",
        "sire_establishment_code",
        "tra_auto_register",
    ]
    list_select_related = ["property"]
    raw_id_fields = ["property"]


@admin.register(InvoiceResolution)
class InvoiceResolutionAdmin(admin.ModelAdmin):
    list_display = ["__str__", "property", "document_kind", "resolution_number", "current_number", "valid_to",
                    "environment", "is_active"]  # fmt: skip
    list_filter = ["document_kind", "environment", "is_active"]
    list_select_related = ["property"]
    raw_id_fields = ["property"]
    readonly_fields = ["current_number"]


@admin.register(Invoice)
class InvoiceAdmin(ReadOnlyAdmin):
    list_display = ["full_number", "property", "kind", "status", "issue_date", "total", "mode"]
    list_filter = ["kind", "status", "mode", "environment"]
    list_select_related = ["property"]
    search_fields = ["full_number", "cufe", "reservation__code"]
    date_hierarchy = "issue_date"
    exclude = ["charges", "pdf_file", "xml_file"]  # private storage without URLs: shown by name below
    readonly_fields = ["pdf_name", "xml_name"]

    @admin.display(description="PDF")
    def pdf_name(self, obj):
        return obj.pdf_file.name or "—"

    @admin.display(description="XML")
    def xml_name(self, obj):
        return obj.xml_file.name or "—"


class SireRecordInline(admin.TabularInline):
    model = SireRecord
    fields = ["movement", "movement_date", "guest", "complete", "missing_fields"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(SireReport)
class SireReportAdmin(ReadOnlyAdmin):
    list_display = ["__str__", "property", "status", "records_count", "generated_at", "ack_code"]
    list_filter = ["status", "mode"]
    list_select_related = ["property"]
    inlines = [SireRecordInline]
    exclude = ["file"]
    readonly_fields = ["file_name"]

    @admin.display(description="Archivo")
    def file_name(self, obj):
        return obj.file.name or "—"


@admin.register(SireRecord)
class SireRecordAdmin(ReadOnlyAdmin):
    list_display = ["__str__", "report", "movement", "movement_date", "complete"]
    list_filter = ["movement", "complete"]
    list_select_related = ["report", "guest"]


@admin.register(TraRegistration)
class TraRegistrationAdmin(ReadOnlyAdmin):
    list_display = ["__str__", "property", "status", "tra_number", "is_main", "registered_at", "attempts"]
    list_filter = ["status", "mode", "is_main"]
    list_select_related = ["property", "guest"]
    search_fields = ["tra_number", "reservation__code", "guest__last_name"]
