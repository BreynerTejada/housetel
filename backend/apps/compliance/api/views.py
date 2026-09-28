"""Staff API of compliance (`/api/v1/compliance/`, header `X-Property-Id`).

Permissions (plan §D): compliance.view (read), compliance.invoice (issue / retry), compliance.void_invoice
(credit notes, a risky action that also needs `confirm: true`), compliance.sire, compliance.tra and
compliance.settings (resolutions and settings).
"""

from datetime import date
from io import BytesIO

from django.db import transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.bookings.models import Reservation, Stay
from apps.compliance.api import serializers as s
from apps.compliance.models import Invoice, InvoiceResolution, SireReport, TraRegistration
from apps.compliance.services import invoices as invoice_service
from apps.compliance.services import sire as sire_service
from apps.compliance.services import tra as tra_service
from apps.compliance.services.config import get_settings
from apps.compliance.services.pending import pending_summary, reservation_legal
from apps.core import audit
from apps.core.tenancy import PropertyScopedAPIView, PropertyScopedMixin, PropertyScopedViewSet
from apps.finance.models import Folio

UUID_REGEX = "[0-9a-fA-F-]{36}"


def _date_param(request, name):
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: ["Fecha inválida (AAAA-MM-DD)"]}) from None


def _file_response(data: bytes, *, filename: str, content_type: str, download: bool) -> FileResponse:
    response = FileResponse(
        BytesIO(data), content_type=content_type, as_attachment=download, filename=filename
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


def _wants_download(request) -> bool:
    return request.query_params.get("download") in {"1", "true"}


# ------------------------------------------------------------------------------------------ resolutions


class ResolutionViewSet(PropertyScopedViewSet):
    """DIAN numbering resolutions. Activating one retires the previous active resolution of the same kind."""

    queryset = InvoiceResolution.objects.annotate(invoices_count=Count("invoices")).order_by(
        "document_kind", "-is_active", "-valid_from"
    )
    serializer_class = s.ResolutionSerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {
        "list": "compliance.view",
        "retrieve": "compliance.view",
        "*": "compliance.settings",
    }

    def perform_create(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_active", True):
                InvoiceResolution.objects.filter(
                    property=self.request.property,
                    document_kind=serializer.validated_data.get("document_kind", "invoice"),
                    is_active=True,
                ).update(is_active=False)
            resolution = serializer.save(property=self.request.property)
            audit.record(
                action="compliance.resolution_created",
                target=resolution,
                actor=self.request.user,
                summary=f"Resolución {resolution.prefix} {resolution.from_number}–{resolution.to_number}",
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            if serializer.validated_data.get("is_active"):
                kind = serializer.validated_data.get("document_kind", serializer.instance.document_kind)
                InvoiceResolution.objects.filter(
                    property=self.request.property, document_kind=kind, is_active=True
                ).exclude(pk=serializer.instance.pk).update(is_active=False)
            resolution = serializer.save()
            audit.record(
                action="compliance.resolution_updated",
                target=resolution,
                actor=self.request.user,
                summary=f"Resolución {resolution.prefix} actualizada",
            )

    def perform_destroy(self, instance):
        audit.record(
            action="compliance.resolution_deleted",
            target=instance,
            actor=self.request.user,
            summary=f"Resolución {instance.prefix} eliminada",
            property=instance.property,
        )
        instance.delete()


# --------------------------------------------------------------------------------------------- invoices


class InvoiceViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """Electronic invoices and credit notes of the hotel."""

    queryset = Invoice.objects.select_related("reservation", "related_invoice", "resolution")
    serializer_class = s.InvoiceSummarySerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {
        "list": "compliance.view",
        "retrieve": "compliance.view",
        "pdf": "compliance.view",
        "xml": "compliance.view",
        "summary": "compliance.view",
        "issue": "compliance.invoice",
        "retry": "compliance.invoice",
        "credit_note": "compliance.void_invoice",
    }

    def get_serializer_class(self):
        return s.InvoiceSummarySerializer if self.action == "list" else s.InvoiceDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if self.action != "list":
            return queryset
        if statuses := params.getlist("status"):
            queryset = queryset.filter(status__in=statuses)
        if kind := params.get("kind"):
            queryset = queryset.filter(kind=kind)
        if mode := params.get("mode"):
            queryset = queryset.filter(mode=mode)
        if reservation := params.get("reservation"):
            queryset = queryset.filter(reservation_id=reservation)
        if start := _date_param(self.request, "start"):
            queryset = queryset.filter(issue_date__gte=start)
        if end := _date_param(self.request, "end"):
            queryset = queryset.filter(issue_date__lte=end)
        if q := (params.get("q") or "").strip():
            queryset = queryset.filter(
                Q(full_number__icontains=q)
                | Q(reservation__code__icontains=q)
                | Q(customer__name__icontains=q)
                | Q(customer__document_number__icontains=q)
            )
        return queryset.order_by("-issue_date", "-created_at")

    @extend_schema(
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, many=True),
            OpenApiParameter("kind", OpenApiTypes.STR, enum=["invoice", "credit_note"]),
            OpenApiParameter("mode", OpenApiTypes.STR, enum=["real", "simulated"]),
            OpenApiParameter("reservation", OpenApiTypes.UUID),
            OpenApiParameter("start", OpenApiTypes.DATE),
            OpenApiParameter("end", OpenApiTypes.DATE),
            OpenApiParameter("q", OpenApiTypes.STR, description="Número, reserva, cliente o documento"),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def _detail(self, invoice):
        return s.InvoiceDetailSerializer(self.get_queryset().get(pk=invoice.pk)).data

    @extend_schema(
        parameters=[OpenApiParameter("start", OpenApiTypes.DATE), OpenApiParameter("end", OpenApiTypes.DATE)],
        responses=OpenApiTypes.OBJECT,
    )
    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Totals of the documents issued in `[start, end]` (issue dates, inclusive; default: this month)."""
        today = request.property.business_date or date.today()
        start = _date_param(request, "start") or today.replace(day=1)
        end = _date_param(request, "end") or today
        documents = Invoice.objects.filter(property=request.property, issue_date__range=(start, end))
        valid = documents.filter(kind=Invoice.Kind.INVOICE, status__in=invoice_service.DONE_STATUSES)
        money = DecimalField(max_digits=14, decimal_places=2)
        zero = Value(0, output_field=money)
        totals = valid.aggregate(
            total=Coalesce(Sum("total"), zero),
            tax_total=Coalesce(Sum("tax_total"), zero),
            subtotal=Coalesce(Sum("subtotal"), zero),
        )
        exempt = valid.exclude(exempt_note="")
        return Response(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "invoices": valid.count(),
                "total": f"{totals['total']:.2f}",
                "subtotal": f"{totals['subtotal']:.2f}",
                "tax_total": f"{totals['tax_total']:.2f}",
                "exempt": {
                    "count": exempt.count(),
                    "total": f"{exempt.aggregate(total=Coalesce(Sum('total'), zero))['total']:.2f}",
                },
                "credit_notes": documents.filter(kind=Invoice.Kind.CREDIT_NOTE).count(),
                "failed": documents.filter(status__in=invoice_service.RETRYABLE_STATUSES).count(),
                "waiting_dian": documents.filter(status=Invoice.Status.ISSUED).count(),
            }
        )

    @extend_schema(request=s.IssueSerializer, responses={201: s.InvoiceDetailSerializer})
    @action(detail=False, methods=["post"])
    def issue(self, request):
        data = s.IssueSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if reservation_id := data.validated_data.get("reservation_id"):
            target = get_object_or_404(Reservation, pk=reservation_id, property=request.property)
        else:
            target = get_object_or_404(Folio, pk=data.validated_data["folio_id"], property=request.property)
        invoice = invoice_service.issue_invoice(target, actor=request.user)
        return Response(self._detail(invoice), status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses=s.InvoiceDetailSerializer)
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        invoice = invoice_service.retry_invoice(self.get_object(), actor=request.user)
        return Response(self._detail(invoice))

    @extend_schema(request=s.CreditNoteSerializer, responses={201: s.InvoiceDetailSerializer})
    @action(detail=True, methods=["post"], url_path="credit-note")
    def credit_note(self, request, pk=None):
        invoice = self.get_object()
        data = s.CreditNoteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        note = invoice_service.issue_credit_note(
            invoice,
            reason=data.validated_data["reason"],
            confirm=data.validated_data["confirm"],
            actor=request.user,
        )
        return Response(self._detail(note), status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[OpenApiParameter("download", OpenApiTypes.BOOL)],
        responses={(200, "application/pdf"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        return _file_response(
            invoice_service.ensure_pdf(invoice),
            filename=invoice_service._file_name(invoice, "pdf"),
            content_type="application/pdf",
            download=_wants_download(request),
        )

    @extend_schema(
        parameters=[OpenApiParameter("download", OpenApiTypes.BOOL)],
        responses={(200, "application/xml"): OpenApiTypes.BINARY},
    )
    @action(detail=True, methods=["get"])
    def xml(self, request, pk=None):
        invoice = self.get_object()
        return _file_response(
            invoice_service.ensure_xml(invoice),
            filename=invoice_service._file_name(invoice, "xml"),
            content_type="application/xml",
            download=_wants_download(request),
        )


# ------------------------------------------------------------------------------------------------- SIRE


class SireReportViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """SIRE files (Migración Colombia)."""

    queryset = SireReport.objects.select_related("generated_by", "submitted_by")
    serializer_class = s.SireReportSerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {
        "list": "compliance.view",
        "retrieve": "compliance.view",
        "generate": "compliance.sire",
        "download": "compliance.sire",
        "mark_submitted": "compliance.sire",
    }

    def get_serializer_class(self):
        return s.SireReportSerializer if self.action == "list" else s.SireReportDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "list" and (report_status := self.request.query_params.get("status")):
            queryset = queryset.filter(status=report_status)
        return queryset.order_by("-period_end", "-generated_at")

    @extend_schema(
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, enum=["generated", "submitted", "acknowledged"])
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=s.SireGenerateSerializer, responses={201: s.SireReportDetailSerializer})
    @action(detail=False, methods=["post"])
    def generate(self, request):
        data = s.SireGenerateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        report = sire_service.generate_sire(
            request.property, data.validated_data["start"], data.validated_data["end"], actor=request.user
        )
        return Response(s.SireReportDetailSerializer(report).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={(200, "text/plain"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        report = self.get_object()
        if not report.file:
            raise ValidationError(
                {"detail": "El archivo de este reporte no está disponible", "code": "file_missing"}
            )
        with report.file.open("rb") as handle:
            data = handle.read()
        name = report.file.name.rsplit("/", 1)[-1]
        return _file_response(data, filename=name, content_type="text/plain; charset=utf-8", download=True)

    @extend_schema(request=s.SireSubmitSerializer, responses=s.SireReportDetailSerializer)
    @action(detail=True, methods=["post"], url_path="mark-submitted")
    def mark_submitted(self, request, pk=None):
        data = s.SireSubmitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        report = sire_service.mark_submitted(
            self.get_object(), actor=request.user, ack_code=data.validated_data["ack_code"]
        )
        return Response(s.SireReportDetailSerializer(report).data)


# -------------------------------------------------------------------------------------------------- TRA


class TraRegistrationViewSet(
    PropertyScopedMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    """TRA registrations (MinCIT) of the hotel's guests."""

    queryset = TraRegistration.objects.select_related("guest", "reservation", "stay__room", "stay__bed")
    serializer_class = s.TraRegistrationSerializer
    lookup_value_regex = UUID_REGEX
    required_permissions = {
        "list": "compliance.view",
        "retrieve": "compliance.view",
        "retry": "compliance.tra",
        "register": "compliance.tra",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        if self.action == "list":
            if statuses := params.getlist("status"):
                queryset = queryset.filter(status__in=statuses)
            if reservation := params.get("reservation"):
                queryset = queryset.filter(reservation_id=reservation)
            if day := _date_param(self.request, "date"):
                queryset = queryset.filter(stay__checkin_date=day)
            if q := (params.get("q") or "").strip():
                queryset = queryset.filter(
                    Q(guest__first_name__icontains=q)
                    | Q(guest__last_name__icontains=q)
                    | Q(guest__document_number__icontains=q)
                    | Q(reservation__code__icontains=q)
                    | Q(tra_number__icontains=q)
                )
        return queryset.order_by("-stay__checkin_date", "reservation_id", "-is_main", "created_at")

    @extend_schema(
        parameters=[
            OpenApiParameter("status", OpenApiTypes.STR, many=True),
            OpenApiParameter("reservation", OpenApiTypes.UUID),
            OpenApiParameter("date", OpenApiTypes.DATE, description="Fecha de llegada"),
            OpenApiParameter("q", OpenApiTypes.STR),
        ]
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=s.TraRegistrationSerializer)
    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        registration = tra_service.retry_registration(self.get_object(), actor=request.user)
        return Response(s.TraRegistrationSerializer(self.get_queryset().get(pk=registration.pk)).data)

    @extend_schema(request=s.TraRegisterSerializer, responses={201: s.TraRegistrationSerializer(many=True)})
    @action(detail=False, methods=["post"])
    def register(self, request):
        data = s.TraRegisterSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        stay = get_object_or_404(
            Stay, pk=data.validated_data["stay_id"], reservation__property=request.property
        )
        if stay.status not in (Stay.Status.CHECKED_IN, Stay.Status.CHECKED_OUT):
            raise ValidationError(
                {"detail": "Solo se registran estadías con check-in", "code": "invalid_state"}
            )
        registrations = tra_service.register_stay(stay, actor=request.user)
        rows = (
            self.get_queryset()
            .filter(pk__in=[r.pk for r in registrations])
            .order_by("-is_main", "created_at")
        )
        return Response(s.TraRegistrationSerializer(rows, many=True).data, status=status.HTTP_201_CREATED)


# ------------------------------------------------------------------------------------ settings & pending


class SettingsView(PropertyScopedAPIView):
    """`GET/PATCH settings/`: legal settings of the hotel + effective values, defaults and integration
    modes."""

    required_permissions = {"get": "compliance.view", "patch": "compliance.settings"}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(s.settings_payload(get_settings(request.property)))

    @extend_schema(request=s.ComplianceSettingsSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request):
        settings = get_settings(request.property)
        serializer = s.ComplianceSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = s.ComplianceSettingsSerializer(settings).data
        settings = serializer.save()
        after = s.ComplianceSettingsSerializer(settings).data
        audit.record(
            action="compliance.settings_updated",
            target=settings,
            actor=request.user,
            summary="Configuración legal actualizada",
            property=request.property,
            changes=audit.diff(dict(before), dict(after)),
        )
        return Response(s.settings_payload(settings))


class PendingView(PropertyScopedAPIView):
    """`GET pending/` (what is still to do legally); `?summary=1` returns only the counts (Today widget)."""

    required_permissions = {"get": "compliance.view"}

    @extend_schema(parameters=[OpenApiParameter("summary", OpenApiTypes.BOOL)], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        summary = pending_summary(request.property)
        if request.query_params.get("summary") in {"1", "true"}:
            return Response(
                {"counts": summary["counts"], "resolution_status": summary["resolution"]["status"]}
            )
        return Response(summary)


class ReservationLegalView(PropertyScopedAPIView):
    """`GET reservations/<id>/`: invoices, TRA, SIRE records and warnings of one reservation."""

    required_permissions = {"get": "compliance.view"}

    @extend_schema(
        responses=inline_serializer(
            "ReservationLegal",
            {
                "reservation": serializers.DictField(),
                "invoices": s.InvoiceSummarySerializer(many=True),
                "uninvoiced": serializers.DictField(),
                "can_issue": serializers.BooleanField(),
                "has_accepted_invoice": serializers.BooleanField(),
                "tra": s.TraRegistrationSerializer(many=True),
                "tra_candidates": serializers.ListField(child=serializers.DictField()),
                "sire": serializers.ListField(child=serializers.DictField()),
                "warnings": serializers.ListField(child=serializers.CharField()),
                "resolution": serializers.DictField(),
                "preview": serializers.DictField(allow_null=True),
            },
        )
    )
    def get(self, request, pk):
        reservation = get_object_or_404(
            Reservation.objects.select_related("booker", "property"), pk=pk, property=request.property
        )
        return Response(reservation_legal(reservation))
