"""Public compliance API (`/api/v1/public/compliance/`, no session): the invoices of a reservation for its
guest,
through the signed portal link (plan §C, C7 → C5). Only documents that reached the DIAN are shown."""

from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.compliance.api.views import _file_response
from apps.compliance.models import Invoice
from apps.compliance.services.invoices import _file_name, ensure_pdf
from apps.core.tokens import read_reservation_token

VISIBLE = {
    Invoice.Kind.INVOICE: (Invoice.Status.ISSUED, Invoice.Status.ACCEPTED, Invoice.Status.CANCELLED),
    Invoice.Kind.CREDIT_NOTE: (Invoice.Status.ISSUED, Invoice.Status.ACCEPTED),
}


class PortalThrottle(AnonRateThrottle):
    scope = "compliance_portal"
    rate = "60/min"


class PortalView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [PortalThrottle]

    def reservation(self, token):
        reservation = read_reservation_token(token)
        if reservation is None:
            raise Http404("Enlace inválido")
        return reservation

    def invoices(self, reservation):
        visible = Invoice.objects.none()
        for kind, statuses in VISIBLE.items():
            visible |= Invoice.objects.filter(reservation=reservation, kind=kind, status__in=statuses)
        return visible.order_by("created_at")


class PortalInvoicesView(PortalView):
    """`GET portal/<token>/invoices/` → `[{id, number, kind, status, total, currency, issued_at,
    pdf_url}]`."""

    @extend_schema(
        auth=[],
        responses=inline_serializer(
            "PortalInvoice",
            {
                "id": serializers.UUIDField(),
                "number": serializers.CharField(),
                "kind": serializers.CharField(),
                "status": serializers.CharField(),
                "total": serializers.CharField(),
                "currency": serializers.CharField(),
                "issued_at": serializers.DateTimeField(),
                "pdf_url": serializers.CharField(),
            },
            many=True,
        ),
    )
    def get(self, request, token):
        reservation = self.reservation(token)
        return Response(
            [
                {
                    "id": str(invoice.pk),
                    "number": invoice.full_number,
                    "kind": invoice.kind,
                    "status": invoice.status,
                    "total": f"{invoice.total:.2f}",
                    "currency": invoice.currency,
                    "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
                    "pdf_url": f"/api/v1/public/compliance/portal/{token}/invoices/{invoice.pk}/pdf/",
                }
                for invoice in self.invoices(reservation)
            ]
        )


class PortalInvoicePdfView(PortalView):
    """`GET portal/<token>/invoices/<id>/pdf/` → the PDF (inline; `?download=1` as attachment)."""

    @extend_schema(auth=[], responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, token, pk):
        reservation = self.reservation(token)
        invoice = self.invoices(reservation).filter(pk=pk).select_related("property").first()
        if invoice is None:
            raise Http404("Factura no encontrada")
        return _file_response(
            ensure_pdf(invoice),
            filename=_file_name(invoice, "pdf"),
            content_type="application/pdf",
            download=request.query_params.get("download") in {"1", "true"},
        )
