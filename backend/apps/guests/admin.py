from django.contrib import admin

from apps.guests.models import Guest, GuestDocument


class GuestDocumentInline(admin.TabularInline):
    model = GuestDocument
    extra = 0


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "organization",
        "email",
        "phone",
        "document_type",
        "document_number",
        "nationality",
        "is_vip",
    ]
    list_filter = ["is_vip", "document_type", "nationality", "blacklisted"]
    list_select_related = ["organization"]
    search_fields = ["first_name", "last_name", "email", "phone", "document_number"]
    raw_id_fields = ["merged_into"]
    inlines = [GuestDocumentInline]


@admin.register(GuestDocument)
class GuestDocumentAdmin(admin.ModelAdmin):
    list_display = ["guest", "kind", "uploaded_via", "created_at"]
    list_filter = ["kind", "uploaded_via"]
    list_select_related = ["guest"]
    raw_id_fields = ["guest"]
