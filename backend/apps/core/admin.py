from django.contrib import admin
from django.db import models

from apps.core.models import (
    Alert,
    AuditEvent,
    AutomationRun,
    AutomationSetting,
    IntegrationSetting,
    Organization,
    Property,
)


class PropertyInline(admin.TabularInline):
    model = Property
    fields = ["name", "slug", "property_type", "city", "status"]
    extra = 0
    show_change_link = True


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "status", "trial_ends_at", "created_at"]
    list_filter = ["status"]
    search_fields = ["name", "slug", "nit"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [PropertyInline]


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    formfield_overrides = {models.URLField: {"assume_scheme": "https"}}
    list_display = [
        "name",
        "organization",
        "property_type",
        "city",
        "business_date",
        "marketplace_listed",
        "status",
    ]
    list_filter = ["property_type", "status", "marketplace_listed"]
    list_select_related = ["organization"]
    search_fields = ["name", "slug", "city"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "action",
        "source",
        "actor_label",
        "property",
        "target_type",
        "reversible",
        "undone_at",
    ]
    list_filter = ["source", "reversible"]
    list_select_related = ["property"]
    search_fields = ["action", "summary", "actor_label", "target_id"]
    raw_id_fields = ["organization", "property", "actor", "undone_by"]


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ["created_at", "severity", "kind", "title", "property", "resolved_at"]
    list_filter = ["severity", "kind"]
    list_select_related = ["property"]
    search_fields = ["title", "message", "dedupe_key"]
    raw_id_fields = ["property", "resolved_by"]


@admin.register(IntegrationSetting)
class IntegrationSettingAdmin(admin.ModelAdmin):
    list_display = ["kind", "property", "mode", "enabled", "status", "last_checked_at"]
    list_filter = ["kind", "mode", "status"]
    list_select_related = ["property"]
    exclude = ["secrets_encrypted"]  # never shown, not even encrypted
    raw_id_fields = ["property"]


@admin.register(AutomationSetting)
class AutomationSettingAdmin(admin.ModelAdmin):
    list_display = ["code", "property", "enabled"]
    list_filter = ["enabled"]
    list_select_related = ["property"]
    search_fields = ["code"]
    raw_id_fields = ["property"]


@admin.register(AutomationRun)
class AutomationRunAdmin(admin.ModelAdmin):
    list_display = ["started_at", "code", "property", "status", "finished_at", "summary"]
    list_filter = ["status", "code"]
    list_select_related = ["property"]
    search_fields = ["code", "summary"]
    raw_id_fields = ["property", "triggered_by"]
