"""Guests API (`/api/v1/guests/`). Guests belong to the organization (every property of a chain shares
them): `OrganizationScopedMixin` + the `X-Property-Id` header, like every staff endpoint."""

import json

from django.http import HttpResponse
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from apps.core import audit
from apps.core.errors import ConfirmationRequired, ConflictError
from apps.core.tenancy import OrganizationScopedMixin, PropertyScopedAPIView
from apps.guests.api.filters import GuestFilter, StableOrderingFilter
from apps.guests.api.serializers import (
    ConfirmSerializer,
    DocumentUploadSerializer,
    DuplicateSerializer,
    GuestDocumentSerializer,
    GuestListSerializer,
    GuestSerializer,
    MergeSerializer,
    StayRowSerializer,
    stay_row,
)
from apps.guests.models import Guest, GuestDocument
from apps.guests.selectors import annotate_stays, reservations_of
from apps.guests.services import (
    add_document,
    anonymize_guest,
    create_guest,
    delete_document,
    delete_guest,
    document_owner,
    export_guest,
    find_duplicates,
    merge_guests,
    update_guest,
)

LOOKUP_PARAMS = (
    "first_name", "last_name", "email", "phone", "document_type", "document_number", "nationality",
    "country_of_residence",
)  # fmt: skip


def ensure_editable(guest: Guest) -> None:
    if guest.merged_into_id:
        raise ConflictError(
            "Este huésped fue fusionado con otro; edita el perfil principal",
            code="guest_merged",
            guest_id=str(guest.merged_into_id),
        )
    if guest.anonymized_at:
        raise ConflictError("Los datos de este huésped fueron anonimizados", code="guest_anonymized")


def require_confirmation(request, message: str) -> None:
    serializer = ConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    if not serializer.validated_data["confirm"]:
        raise ConfirmationRequired(message)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Nombre, email, teléfono o documento"),
            OpenApiParameter(
                "ordering",
                str,
                description="last_name, first_name, created_at, stays_count, "
                "last_stay_date (prefijo - = descendente)",
            ),
        ]
    )
)
class GuestViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Guest.objects.all()
    serializer_class = GuestSerializer
    filter_backends = [DjangoFilterBackend, StableOrderingFilter]
    filterset_class = GuestFilter
    ordering_fields = ["last_name", "first_name", "created_at", "stays_count", "last_stay_date"]
    required_permissions = {
        "list": "guests.view",
        "retrieve": "guests.view",
        "stays": "guests.view",
        "documents": "guests.view",
        "duplicates": "guests.view",
        "lookup": "guests.view",
        "tags": "guests.view",
        "create": "guests.manage",
        "update": "guests.manage",
        "partial_update": "guests.manage",
        "destroy": "guests.manage",
        "upload_document": "guests.manage",
        "merge": "guests.merge",
        "export": "guests.export",
        "anonymize": "guests.export",
        "*": "guests.manage",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list":
            queryset = annotate_stays(queryset.filter(merged_into__isnull=True))
        return queryset

    def get_serializer_class(self):
        return GuestListSerializer if self.action == "list" else GuestSerializer

    def perform_create(self, serializer):
        serializer.instance = create_guest(
            self.request.organization, serializer.validated_data, actor=self.request.user
        )

    def update(self, request, *args, **kwargs):
        ensure_editable(self.get_object())
        return super().update(request, *args, **kwargs)

    def perform_update(self, serializer):
        guest = serializer.instance
        data = dict(serializer.validated_data)
        consent = data.pop("data_processing_consent", None)
        if consent is True and guest.data_processing_consent_at is None:
            data["data_processing_consent_at"] = timezone.now()
        elif consent is False and guest.data_processing_consent_at is not None:
            data["data_processing_consent_at"] = None
        if "document_number" in data or "document_type" in data:
            holder = document_owner(
                guest.organization,
                data.get("document_type", guest.document_type),
                data.get("document_number", guest.document_number),
                exclude=guest,
            )
            if holder is not None and holder.pk != guest.pk:
                raise ConflictError(
                    "Otro huésped ya tiene ese documento; considera fusionarlos",
                    code="guest_exists",
                    guest_id=str(holder.pk),
                )
        serializer.instance = update_guest(guest, data, actor=self.request.user)

    def perform_destroy(self, instance):
        delete_guest(instance, actor=self.request.user)

    @extend_schema(responses=StayRowSerializer(many=True))
    @action(detail=True, methods=["get"])
    def stays(self, request, pk=None):
        """Reservations of the guest (booker or occupant), newest first, in every property of the chain."""
        guest = self.get_object()
        reservations = (
            reservations_of(guest)
            .select_related("property")
            .prefetch_related("stays__room")
            .order_by("-checkin_date", "-created_at")
        )
        page = self.paginate_queryset(reservations)
        rows = StayRowSerializer([stay_row(r, guest) for r in page], many=True).data
        return self.get_paginated_response(rows)

    @extend_schema(responses=GuestDocumentSerializer(many=True))
    @action(detail=True, methods=["get"])
    def documents(self, request, pk=None):
        guest = self.get_object()
        return Response(GuestDocumentSerializer(guest.documents.all(), many=True).data)

    @extend_schema(
        request={"multipart/form-data": DocumentUploadSerializer}, responses={201: GuestDocumentSerializer}
    )
    @documents.mapping.post
    def upload_document(self, request, pk=None):
        guest = self.get_object()
        ensure_editable(guest)
        serializer = DocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = add_document(
            guest,
            kind=serializer.validated_data["kind"],
            file=serializer.validated_data["file"],
            uploaded_via="staff",
        )
        audit.record(
            action="guests.document_added",
            target=guest,
            summary="Agregó un documento a un huésped",
            actor=request.user,
            organization=guest.organization,
            changes={"kind": document.kind},
        )
        return Response(GuestDocumentSerializer(document).data, status=status.HTTP_201_CREATED)

    def _duplicate_rows(self, guests: list[Guest]):
        reasons = {g.pk: g.duplicate_reasons for g in guests}
        rows = {g.pk: g for g in annotate_stays(Guest.objects.filter(pk__in=reasons))}
        ordered = []
        for pk, why in reasons.items():
            rows[pk].duplicate_reasons = why
            ordered.append(rows[pk])
        return Response(DuplicateSerializer(ordered, many=True).data)

    @extend_schema(responses=DuplicateSerializer(many=True))
    @action(detail=True, methods=["get"])
    def duplicates(self, request, pk=None):
        """Likely duplicates of the guest, each with `reasons` (document, email, phone_name)."""
        return self._duplicate_rows(find_duplicates(self.get_object()))

    @extend_schema(
        parameters=[OpenApiParameter(name, str) for name in LOOKUP_PARAMS],
        responses=DuplicateSerializer(many=True),
    )
    @action(detail=False, methods=["get"])
    def lookup(self, request):
        """Existing guests that look like the data being typed (before creating a new guest)."""
        values = {name: request.query_params.get(name, "") for name in LOOKUP_PARAMS}
        draft = Guest(organization=request.organization, **values)
        return self._duplicate_rows(find_duplicates(draft))

    @extend_schema(request=MergeSerializer, responses=GuestSerializer)
    @action(detail=False, methods=["post"])
    def merge(self, request):
        """Merge `duplicate_id` into `primary_id` (both of the organization). Requires `confirm: true`."""
        serializer = MergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data["confirm"]:
            raise ConfirmationRequired("Confirma la fusión de los dos perfiles")
        guests = Guest.objects.filter(organization=request.organization)
        primary = guests.filter(pk=serializer.validated_data["primary_id"]).first()
        duplicate = guests.filter(pk=serializer.validated_data["duplicate_id"]).first()
        if primary is None or duplicate is None:
            raise NotFound("Huésped no encontrado")
        merged = merge_guests(primary, duplicate, actor=request.user)  # 409 already_merged / guest_anonymized
        return Response(GuestSerializer(merged, context=self.get_serializer_context()).data)

    @extend_schema(responses={(200, "application/json"): OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        """Habeas Data (right of access): everything stored about the guest, as a JSON download."""
        guest = self.get_object()
        payload = export_guest(guest)
        audit.record(
            action="guests.exported",
            target=guest,
            summary="Exportó los datos personales de un huésped (Habeas Data)",
            actor=request.user,
            property=request.property,
        )
        response = HttpResponse(
            json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8"
        )
        response["Content-Disposition"] = f'attachment; filename="huesped-{guest.pk}.json"'
        return response

    @extend_schema(request=ConfirmSerializer, responses=GuestSerializer)
    @action(detail=True, methods=["post"])
    def anonymize(self, request, pk=None):
        """Habeas Data (right of deletion): erase the guest's personal data and documents. Irreversible;
        requires `confirm: true`."""
        guest = self.get_object()
        require_confirmation(request, "Confirma la anonimización: no se puede deshacer")
        guest = anonymize_guest(guest, actor=request.user)
        return Response(GuestSerializer(guest, context=self.get_serializer_context()).data)

    @extend_schema(responses={200: {"type": "array", "items": {"type": "string"}}})
    @action(detail=False, methods=["get"])
    def tags(self, request):
        """Tags used by the organization's guests (for filters and autocompletion)."""
        found = set()
        rows = Guest.objects.filter(organization=request.organization, merged_into__isnull=True)
        for tags in rows.values_list("tags", flat=True):
            found.update(tag for tag in tags or [] if isinstance(tag, str))
        return Response(sorted(found, key=str.lower))


class GuestDocumentView(OrganizationScopedMixin, PropertyScopedAPIView):
    """`DELETE documents/<id>/` (`guests.manage`)."""

    required_permissions = {"delete": "guests.manage"}

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        document = (
            GuestDocument.objects.select_related("guest")
            .filter(pk=pk, guest__organization=request.organization)
            .first()
        )
        if document is None:
            raise NotFound("Documento no encontrado")
        delete_document(document, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
