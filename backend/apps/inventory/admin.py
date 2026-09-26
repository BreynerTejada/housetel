from django.contrib import admin

from apps.inventory.models import Amenity, Bed, CustomFieldDefinition, Photo, Room, RoomBlock, RoomType


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ["code", "__str__", "category", "icon", "organization"]
    list_filter = ["category"]
    search_fields = ["code"]


class RoomInline(admin.TabularInline):
    model = Room
    fields = ["number", "floor", "housekeeping_status", "is_active"]
    extra = 0
    show_change_link = True


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "property",
        "kind",
        "base_occupancy",
        "max_occupancy",
        "is_active",
        "sort_order",
    ]
    list_filter = ["kind", "is_active"]
    list_select_related = ["property"]
    search_fields = ["code"]
    filter_horizontal = ["amenities"]
    inlines = [RoomInline]


class BedInline(admin.TabularInline):
    model = Bed
    extra = 0


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ["number", "property", "room_type", "floor", "housekeeping_status", "is_active"]
    list_filter = ["housekeeping_status", "is_active"]
    list_select_related = ["property", "room_type"]
    search_fields = ["number", "name"]
    filter_horizontal = ["extra_amenities", "removed_amenities", "connecting_rooms"]
    inlines = [BedInline]


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ["__str__", "bed_type", "is_active"]
    list_select_related = ["room"]
    raw_id_fields = ["room"]


@admin.register(CustomFieldDefinition)
class CustomFieldDefinitionAdmin(admin.ModelAdmin):
    list_display = ["key", "applies_to", "field_type", "organization", "property", "required"]
    list_filter = ["applies_to", "field_type"]
    list_select_related = ["organization", "property"]
    search_fields = ["key"]


@admin.register(Photo)
class PhotoAdmin(admin.ModelAdmin):
    list_display = ["__str__", "property", "room_type", "room", "sort_order"]
    list_select_related = ["property", "room_type", "room"]
    raw_id_fields = ["room_type", "room"]


@admin.register(RoomBlock)
class RoomBlockAdmin(admin.ModelAdmin):
    list_display = ["room", "bed", "start_date", "end_date", "kind", "released_at"]
    list_filter = ["kind"]
    list_select_related = ["room", "bed", "bed__room"]
    raw_id_fields = ["room", "bed", "created_by"]
