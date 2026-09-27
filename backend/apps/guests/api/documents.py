"""Private file endpoint for guest identity documents (never served from /media/)."""

from pathlib import Path

from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound

from apps.core.tenancy import OrganizationScopedMixin, PropertyScopedAPIView
from apps.guests.models import GuestDocument
from apps.guests.services import document_content_type


def document_file_url(document: GuestDocument) -> str:
    """The only URL a document is exposed with (serializers use it instead of `file.url`)."""
    return f"/api/v1/guests/documents/{document.pk}/file/"


def document_filename(document: GuestDocument) -> str:
    """Download name without personal data: `<kind>-<yyyymmdd><ext>`."""
    return f"{document.kind}-{document.created_at:%Y%m%d}{Path(document.file.name).suffix.lower()}"


class GuestDocumentFileView(OrganizationScopedMixin, PropertyScopedAPIView):
    """`GET documents/<id>/file/` (`guests.view`) → the file, streamed.

    Organization-scoped like every guest endpoint (header `X-Property-Id`); `?download=1` makes it an
    attachment. Responses are never cached and never content-sniffed by the browser."""

    required_permissions = {"get": "guests.view"}

    @extend_schema(
        parameters=[OpenApiParameter("download", OpenApiTypes.BOOL, required=False)],
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY},
    )
    def get(self, request, pk):
        document = (
            GuestDocument.objects.select_related("guest")
            .filter(pk=pk, guest__organization=request.organization)
            .first()
        )
        if document is None:
            raise NotFound("Documento no encontrado")
        try:
            handle = document.file.open("rb")
        except FileNotFoundError:
            raise NotFound("El archivo del documento no está disponible") from None
        response = FileResponse(
            handle,
            content_type=document_content_type(document),
            as_attachment=request.query_params.get("download") in {"1", "true"},
            filename=document_filename(document),
        )
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response
