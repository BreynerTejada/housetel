from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import path, reverse
from django.utils.html import format_html

from apps.core.errors import DomainError
from apps.guests.api.documents import document_filename
from apps.guests.models import Guest, GuestDocument
from apps.guests.services import check_document_file, delete_document, document_content_type

# Identity documents live in a private storage without URLs (apps/guests/storage.py): the admin never renders
# `file.url` (it raises); it links to its own staff-only download view instead.


def download_link(document: GuestDocument) -> str:
    if not document.pk or not document.file:
        return "—"
    return format_html(
        '<a href="{}">Descargar</a>', reverse("admin:guests_guestdocument_file", args=[document.pk])
    )


class GuestDocumentInline(admin.TabularInline):
    model = GuestDocument
    extra = 0
    can_delete = False  # deleting goes through the document admin, which also removes the file
    fields = ["kind", "uploaded_via", "created_at", "download"]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False  # uploads go through the API or the document admin (validated)

    @admin.display(description="Archivo")
    def download(self, document):
        return download_link(document)


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


class GuestDocumentAddForm(forms.ModelForm):
    """Same checks as the API upload (content-sniffed type, 10 MB) before the file reaches the storage."""

    class Meta:
        model = GuestDocument
        fields = ["guest", "kind", "file", "uploaded_via"]

    def clean_file(self):
        file = self.cleaned_data["file"]
        try:
            extension = check_document_file(file)
        except DomainError as exc:
            raise forms.ValidationError(exc.message) from None
        file.name = f"document{extension}"  # only the suffix is kept; the stored name is random
        return file


@admin.register(GuestDocument)
class GuestDocumentAdmin(admin.ModelAdmin):
    list_display = ["guest", "kind", "uploaded_via", "created_at"]
    list_filter = ["kind", "uploaded_via"]
    list_select_related = ["guest"]
    raw_id_fields = ["guest"]
    add_form = GuestDocumentAddForm

    def get_form(self, request, obj=None, change=False, **kwargs):
        if obj is None:
            kwargs["form"] = self.add_form
        return super().get_form(request, obj, change=change, **kwargs)

    def get_fields(self, request, obj=None):
        if obj is None:
            return ["guest", "kind", "file", "uploaded_via"]
        return ["guest", "kind", "uploaded_via", "stored_name", "download", "created_at"]

    def get_readonly_fields(self, request, obj=None):
        return [] if obj is None else ["guest", "uploaded_via", "stored_name", "download", "created_at"]

    @admin.display(description="Nombre almacenado")
    def stored_name(self, document):
        return document.file.name

    @admin.display(description="Archivo")
    def download(self, document):
        return download_link(document)

    def delete_model(self, request, obj):
        delete_document(obj, actor=request.user)

    def delete_queryset(self, request, queryset):
        for document in queryset.select_related("guest__organization"):
            delete_document(document, actor=request.user)

    def get_urls(self):
        return [
            path(
                "<uuid:pk>/file/",
                self.admin_site.admin_view(self.file_view),
                name="guests_guestdocument_file",
            ),
            *super().get_urls(),
        ]

    def file_view(self, request, pk):
        """Staff-only download (Django admin session + view permission on documents)."""
        document = get_object_or_404(GuestDocument, pk=pk)
        if not self.has_view_permission(request, document):
            raise PermissionDenied
        try:
            handle = document.file.open("rb")
        except FileNotFoundError:
            raise Http404("El archivo del documento no está disponible") from None
        response = FileResponse(
            handle,
            content_type=document_content_type(document),
            as_attachment=True,
            filename=document_filename(document),
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
