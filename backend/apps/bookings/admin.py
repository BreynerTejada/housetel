from django.contrib import admin

from apps.bookings.models import GroupBlock, InventoryDay, Reservation, ReservationGroup, Stay


class StayInline(admin.TabularInline):
    model = Stay
    fields = [
        "room_type",
        "rate_plan",
        "room",
        "bed",
        "checkin_date",
        "checkout_date",
        "status",
        "total_amount",
    ]
    raw_id_fields = ["room_type", "rate_plan", "room", "bed"]
    extra = 0
    show_change_link = True


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = [
        "code",
        "property",
        "booker",
        "status",
        "source",
        "checkin_date",
        "checkout_date",
        "total_amount",
    ]
    list_filter = ["status", "source"]
    list_select_related = ["property", "booker"]
    search_fields = ["code", "external_id", "booker__first_name", "booker__last_name", "booker__email"]
    date_hierarchy = "checkin_date"
    raw_id_fields = ["booker", "group", "created_by"]
    inlines = [StayInline]


@admin.register(Stay)
class StayAdmin(admin.ModelAdmin):
    list_display = ["reservation", "room_type", "room", "bed", "checkin_date", "checkout_date", "status"]
    list_filter = ["status"]
    list_select_related = ["reservation", "room_type", "room", "bed", "bed__room"]
    search_fields = ["reservation__code"]
    raw_id_fields = ["reservation", "room_type", "rate_plan", "room", "bed"]
    filter_horizontal = ["occupants"]


class GroupBlockInline(admin.TabularInline):
    """Read-only here: changing a block must go through `services.blocks` (it moves `held_units`)."""

    model = GroupBlock
    fields = ["room_type", "start", "end", "units", "release_date", "released_at"]
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = False


@admin.register(ReservationGroup)
class ReservationGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "property", "contact_guest"]
    list_select_related = ["property", "contact_guest"]
    raw_id_fields = ["contact_guest"]
    inlines = [GroupBlockInline]


@admin.register(GroupBlock)
class GroupBlockAdmin(admin.ModelAdmin):
    """Read-only (the hold in InventoryDay is kept by `services.blocks`)."""

    list_display = ["group", "room_type", "start", "end", "units", "release_date", "released_at"]
    list_select_related = ["group", "room_type"]
    list_filter = ["released_at"]
    search_fields = ["group__name"]
    readonly_fields = ["group", "room_type", "start", "end", "units", "release_date", "released_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(InventoryDay)
class InventoryDayAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "room_type",
        "total_units",
        "sold_units",
        "blocked_units",
        "held_units",
        "available",
    ]
    list_select_related = ["room_type"]
    date_hierarchy = "date"
    raw_id_fields = ["room_type"]
