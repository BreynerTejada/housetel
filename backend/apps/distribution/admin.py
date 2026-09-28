from django.contrib import admin

from apps.distribution.models import (
    AriUpdate,
    ChannelConnection,
    ExternalReservationMap,
    RateMapping,
    RoomMapping,
    SimOtaBooking,
    SimOtaInventory,
    SyncLog,
)


class RoomMappingInline(admin.TabularInline):
    model = RoomMapping
    extra = 0
    fields = (
        "room_type",
        "room",
        "external_room_id",
        "ical_import_url",
        "ical_last_sync_at",
        "ical_last_error",
    )
    readonly_fields = ("ical_last_sync_at", "ical_last_error")
    raw_id_fields = ("room_type", "room")


class RateMappingInline(admin.TabularInline):
    model = RateMapping
    extra = 0
    fields = ("rate_plan", "room_type", "external_rate_id", "markup_percent")
    raw_id_fields = ("rate_plan", "room_type")


@admin.register(ChannelConnection)
class ChannelConnectionAdmin(admin.ModelAdmin):
    list_display = ("name", "channel_code", "property", "status", "last_sync_at")
    list_filter = ("channel_code", "status")
    search_fields = ("name", "property__name")
    raw_id_fields = ("property",)
    inlines = [RoomMappingInline, RateMappingInline]


@admin.register(AriUpdate)
class AriUpdateAdmin(admin.ModelAdmin):
    list_display = ("connection", "room_type", "start", "end", "status", "attempts", "sent_at")
    list_filter = ("status",)
    raw_id_fields = ("property", "connection", "room_type", "rate_plan")


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "connection", "direction", "kind", "status", "external_id")
    list_filter = ("direction", "status", "kind")
    search_fields = ("message", "external_id")
    raw_id_fields = ("connection", "reservation")


@admin.register(ExternalReservationMap)
class ExternalReservationMapAdmin(admin.ModelAdmin):
    list_display = ("external_id", "connection", "reservation", "last_status", "updated_at")
    search_fields = ("external_id", "reservation__code")
    raw_id_fields = ("connection", "reservation", "room_mapping")


@admin.register(SimOtaInventory)
class SimOtaInventoryAdmin(admin.ModelAdmin):
    list_display = (
        "connection",
        "external_room_id",
        "external_rate_id",
        "date",
        "available",
        "price",
        "stop_sell",
    )
    list_filter = ("stop_sell",)
    raw_id_fields = ("connection",)


@admin.register(SimOtaBooking)
class SimOtaBookingAdmin(admin.ModelAdmin):
    list_display = ("external_id", "connection", "status", "revision", "pms_status", "updated_at")
    list_filter = ("status", "pms_status")
    search_fields = ("external_id",)
    raw_id_fields = ("connection",)
