from django.contrib import admin

from apps.housekeeping.models import HousekeepingSettings, HousekeepingTask, MaintenanceTicket, TicketPhoto


@admin.register(HousekeepingSettings)
class HousekeepingSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "stayover_frequency_days",
        "require_inspection",
        "auto_assign",
        "minutes_per_shift",
    )
    list_select_related = ("property",)


@admin.register(HousekeepingTask)
class HousekeepingTaskAdmin(admin.ModelAdmin):
    list_display = ("business_date", "property", "room", "kind", "status", "priority", "assigned_to")
    list_filter = ("status", "kind", "priority", "business_date")
    list_select_related = ("property", "room", "assigned_to")
    raw_id_fields = ("room", "bed", "assigned_to", "finished_by", "reservation")
    search_fields = ("room__number", "notes")


class TicketPhotoInline(admin.TabularInline):
    model = TicketPhoto
    extra = 0
    fields = ("content_type", "size", "uploaded_by", "created_at")
    readonly_fields = fields


@admin.register(MaintenanceTicket)
class MaintenanceTicketAdmin(admin.ModelAdmin):
    list_display = ("title", "property", "room", "priority", "status", "blocks_room", "created_at")
    list_filter = ("status", "priority", "blocks_room")
    list_select_related = ("property", "room")
    raw_id_fields = ("room", "block", "reported_by", "assigned_to", "resolved_by")
    search_fields = ("title", "description", "location")
    inlines = [TicketPhotoInline]
