from django.contrib import admin

from apps.imports.models import ImportedRecord, ImportJob, ImportRow


@admin.register(ImportJob)
class ImportJobAdmin(admin.ModelAdmin):
    list_display = [
        "filename",
        "kind",
        "preset",
        "source_label",
        "status",
        "property",
        "total_rows",
        "created_at",
    ]
    list_filter = ["kind", "status", "preset"]
    search_fields = ["filename", "source_label"]
    readonly_fields = [field.name for field in ImportJob._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ImportRow)
class ImportRowAdmin(admin.ModelAdmin):
    list_display = ["job", "number", "status", "outcome", "target_label"]
    list_filter = ["status", "outcome"]
    readonly_fields = [field.name for field in ImportRow._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(ImportedRecord)
class ImportedRecordAdmin(admin.ModelAdmin):
    list_display = ["kind", "source_system", "external_id", "target_type", "target_id", "property"]
    list_filter = ["kind", "source_system"]
    search_fields = ["external_id"]
    readonly_fields = [field.name for field in ImportedRecord._meta.fields]

    def has_add_permission(self, request):
        return False
