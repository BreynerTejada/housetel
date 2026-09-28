from django.contrib import admin

from apps.marketplace.models import BookingEngineSettings, ListingContent, ListingPhoto


@admin.register(BookingEngineSettings)
class BookingEngineSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "property",
        "enabled",
        "primary_color",
        "min_advance_hours",
        "max_advance_days",
        "updated_at",
    )
    list_filter = ("enabled",)
    search_fields = ("property__name", "property__slug")
    raw_id_fields = ("property",)
    filter_horizontal = ("allowed_rate_plans",)


class ListingPhotoInline(admin.TabularInline):
    model = ListingPhoto
    extra = 0
    raw_id_fields = ("photo",)


@admin.register(ListingContent)
class ListingContentAdmin(admin.ModelAdmin):
    list_display = ("property", "neighborhood", "updated_at")
    search_fields = ("property__name", "property__slug", "neighborhood")
    raw_id_fields = ("property",)
    exclude = ("featured_photos",)
    inlines = [ListingPhotoInline]
