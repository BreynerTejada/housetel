"""Corporate API (`/api/v1/corporate/`, header `X-Property-Id`).

Companies belong to the organization (every property of a chain shares them); statements, receivables and
payments on account are per property (the active one). Permissions (pilot plan §D): corporate.view (read),
corporate.manage (companies and the billing of reservations), corporate.ar (payments on account, credit,
opening balances).
"""

from datetime import date

from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.bookings.models import Reservation
from apps.core import audit
from apps.core.errors import ConflictError
from apps.core.tenancy import OrganizationScopedMixin, PropertyScopedAPIView, PropertyScopedMixin
from apps.corporate import services
from apps.corporate.api import serializers as s
from apps.corporate.billing import billing_payload
from apps.corporate.models import AccountPayment, Company, ReservationBilling
from apps.corporate.nit import format_nit
from apps.finance.reporting import csv_response

UUID_REGEX = "[0-9a-fA-F-]{36}"


def _date_param(request, name):
    value = request.query_params.get(name)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({name: ["Fecha inválida (AAAA-MM-DD)"]}) from None


def _snapshot(company) -> dict:
    return {
        field: getattr(company, field)
        for field in (
            "kind", "legal_name", "trade_name", "nit", "dv", "vat_responsible", "tax_responsibilities",
            "address", "city", "billing_email", "phone", "credit_enabled", "payment_terms_days", "is_active",
        )
    } | {"credit_limit": str(company.credit_limit) if company.credit_limit is not None else None}  # fmt: skip


class CompanyViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Corporate clients of the organization. `GET companies/?q=&kind=&active=true|false&with_balance=1`."""

    queryset = Company.objects.all()
    serializer_class = s.CompanySerializer
    lookup_value_regex = UUID_REGEX
    filter_backends: list = []
    required_permissions = {
        "list": "corporate.view",
        "retrieve": "corporate.view",
        "statement": "corporate.view",
        "statement_export": "corporate.view",
        "reservations": "corporate.view",
        "create": "corporate.manage",
        "update": "corporate.manage",
        "partial_update": "corporate.manage",
        "destroy": "corporate.manage",
        "payments": "corporate.ar",
        "apply_credit": "corporate.ar",
        "opening_balance": "corporate.ar",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action != "list":
            return queryset
        params = self.request.query_params
        if q := (params.get("q") or "").strip():
            digits = "".join(ch for ch in q if ch.isdigit())
            match = Q(legal_name__icontains=q) | Q(trade_name__icontains=q) | Q(billing_email__icontains=q)
            if digits:
                match |= Q(nit__startswith=digits.split("-")[0][:15])
            queryset = queryset.filter(match)
        if kind := params.get("kind"):
            queryset = queryset.filter(kind=kind)
        active = params.get("active")
        if active in {"true", "1"}:
            queryset = queryset.filter(is_active=True)
        elif active in {"false", "0"}:
            queryset = queryset.filter(is_active=False)
        if params.get("credit") in {"true", "1"}:
            queryset = queryset.filter(credit_enabled=True)
        return queryset.order_by("legal_name")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if getattr(self.request, "organization", None) is not None:
            context["organization"] = self.request.organization
        return context

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "q", OpenApiTypes.STR, description="Razón social, nombre comercial, NIT o email"
            ),
            OpenApiParameter("kind", OpenApiTypes.STR, enum=s.KINDS),
            OpenApiParameter("active", OpenApiTypes.BOOL),
            OpenApiParameter("credit", OpenApiTypes.BOOL),
            OpenApiParameter("with_balance", OpenApiTypes.BOOL, description="Solo empresas con saldo aquí"),
        ]
    )
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        balances = None
        if request.query_params.get("with_balance") in {"true", "1"}:
            balances = services.company_balances(request.property, queryset)
            queryset = queryset.filter(
                pk__in=[pk for pk, row in balances.items() if row["balance"] or row["in_progress"]]
            )
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        if balances is None:
            balances = services.company_balances(request.property, rows)
        data = self.get_serializer(
            rows, many=True, context={**self.get_serializer_context(), "balances": balances}
        ).data
        return self.get_paginated_response(data) if page is not None else Response(data)

    def retrieve(self, request, *args, **kwargs):
        company = self.get_object()
        balances = services.company_balances(request.property, [company])
        data = self.get_serializer(
            company, context={**self.get_serializer_context(), "balances": balances}
        ).data
        data["credit"] = services._credit_payload(services.credit_status(company))
        return Response(data)

    def perform_create(self, serializer):
        company = serializer.save(organization=self.request.organization)
        audit.record(
            action="corporate.company_created",
            target=company,
            actor=self.request.user,
            property=self.request.property,
            summary=f"Empresa {company.legal_name} (NIT {format_nit(company.nit, company.dv)})",
        )

    def perform_update(self, serializer):
        before = _snapshot(serializer.instance)
        company = serializer.save()
        audit.record(
            action="corporate.company_updated",
            target=company,
            actor=self.request.user,
            property=self.request.property,
            summary=f"Empresa {company.legal_name} actualizada",
            changes=audit.diff(before, _snapshot(company)),
        )
        if company.credit_enabled:
            services.check_credit(company, property=self.request.property)

    def perform_destroy(self, instance):
        used = (
            instance.folios.exists()
            or instance.reservation_billings.exists()
            or instance.account_payments.exists()
        )
        if used:
            raise ConflictError(
                "La empresa tiene reservas, folios o pagos: desactívala en lugar de eliminarla",
                code="company_in_use",
            )
        audit.record(
            action="corporate.company_deleted",
            target=instance,
            actor=self.request.user,
            property=self.request.property,
            summary=f"Empresa {instance.legal_name} eliminada",
        )
        instance.delete()

    @extend_schema(parameters=[OpenApiParameter("as_of", OpenApiTypes.DATE)], responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def statement(self, request, pk=None):
        """Account statement at the active property: open items with aging, reservations in progress, payments
        on account, unapplied credit and the credit status."""
        company = self.get_object()
        return Response(
            {
                "company": services.company_ref(company),
                **services.statement(company, request.property, as_of=_date_param(request, "as_of")),
            }
        )

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.STR})
    @action(detail=True, methods=["get"], url_path="statement/export")
    def statement_export(self, request, pk=None):
        """CSV of the statement (`;`, UTF-8 with BOM for Excel)."""
        company = self.get_object()
        data = services.statement(company, request.property)
        rows = [
            [
                item["invoice"]["number"] if item["invoice"] else (item["label"] or ""),
                item["reservation"]["code"] if item["reservation"] else "",
                item["reservation"]["guest_name"] if item["reservation"] else "",
                item["document_date"] or "",
                item["due_date"] or "",
                item["age_days"],
                item["overdue_days"],
                item["charges_total"],
                item["paid"],
                item["balance"],
            ]
            for item in data["items"]
        ]
        totals = data["totals"]
        rows += [
            [],
            ["Saldo", totals["balance"]],
            ["Vencido", totals["overdue"]],
            ["Saldo a favor", totals["unapplied"]],
            ["Saldo neto", totals["net_balance"]],
            ["0-30", data["aging"]["current"]],
            ["31-60", data["aging"]["d31_60"]],
            ["61-90", data["aging"]["d61_90"]],
            ["90+", data["aging"]["d90_plus"]],
        ]
        return csv_response(
            f"estado-de-cuenta-{company.nit}-{data['as_of']}.csv",
            [
                "Documento",
                "Reserva",
                "Huésped",
                "Fecha",
                "Vence",
                "Días",
                "Días vencido",
                "Total",
                "Pagado",
                "Saldo",
            ],
            rows,
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["get"])
    def reservations(self, request, pk=None):
        """Reservations of the active property billed to the company (or with a folio of it)."""
        return Response(services.company_reservations(self.get_object(), request.property))

    @extend_schema(request=s.AccountPaymentCreateSerializer, responses={201: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"])
    def payments(self, request, pk=None):
        """Payment on account: `{amount, method, reference?, notes?, received_on?, allocations: [{folio_id,
        amount}] | auto_allocate: true}` → the payment and the updated statement."""
        company = self.get_object()
        data = s.AccountPaymentCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        payment = services.record_account_payment(
            company,
            request.property,
            amount=values["amount"],
            method=values["method"],
            reference=values["reference"],
            notes=values["notes"],
            received_on=values["received_on"],
            allocations=[dict(item) for item in values["allocations"]],
            auto_allocate=values["auto_allocate"],
            actor=request.user,
        )
        return Response(self._with_statement(company, payment_id=payment.pk), status=status.HTTP_201_CREATED)

    @extend_schema(request=s.ApplyCreditSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="apply-credit")
    def apply_credit(self, request, pk=None):
        """Apply the unapplied credit (oldest payments first): `{allocations: [...]}` or `{auto: true}`."""
        company = self.get_object()
        data = s.ApplyCreditSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        created = services.apply_credit(
            company,
            request.property,
            allocations=[dict(item) for item in data.validated_data["allocations"]],
            auto=data.validated_data["auto"],
            actor=request.user,
        )
        return Response({**self._with_statement(company), "applied": len(created)})

    @extend_schema(request=s.OpeningBalanceSerializer, responses={201: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"], url_path="opening-balance")
    def opening_balance(self, request, pk=None):
        """Receivable from before Housetel (a legacy invoice).

        `{amount, document_date, reference, description?}`"""
        company = self.get_object()
        data = s.OpeningBalanceSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        folio = services.add_opening_balance(
            company,
            request.property,
            amount=values["amount"],
            document_date=values["document_date"],
            reference=values["reference"],
            description=values["description"],
            actor=request.user,
        )
        return Response(
            {**self._with_statement(company), "folio_id": str(folio.pk)}, status=status.HTTP_201_CREATED
        )

    def _with_statement(self, company, payment_id=None) -> dict:
        payload = {
            "company": services.company_ref(company),
            **services.statement(company, self.request.property),
        }
        if payment_id is not None:
            payload["payment"] = next(
                (row for row in payload["payments"] if row["id"] == str(payment_id)), None
            )
        return payload


class AccountPaymentViewSet(PropertyScopedMixin, viewsets.GenericViewSet):
    """Payments on account of the active property (`void`)."""

    queryset = AccountPayment.objects.select_related("company", "property")
    lookup_value_regex = UUID_REGEX
    required_permissions = {"void": "corporate.ar"}

    @extend_schema(request=s.AccountPaymentVoidSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def void(self, request, pk=None):
        """Annul a payment on account recorded by mistake (`{reason, confirm: true}`); its folio payments are
        voided and the folios it settled reopen."""
        data = s.AccountPaymentVoidSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        payment = services.void_account_payment(
            self.get_object(),
            reason=data.validated_data["reason"],
            actor=request.user,
            confirm=data.validated_data["confirm"],
        )
        company = payment.company
        return Response(
            {"company": services.company_ref(company), **services.statement(company, request.property)}
        )


class ReservationBillingView(PropertyScopedAPIView):
    """`GET/PUT reservations/<id>/billing/`: who pays the reservation, its folios and the company's credit."""

    required_permissions = {"get": "corporate.view", "put": "corporate.manage"}

    def _reservation(self, request, pk):
        return get_object_or_404(
            Reservation.objects.select_related("booker", "property"), pk=pk, property=request.property
        )

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        return Response(billing_payload(self._reservation(request, pk)))

    @extend_schema(request=s.BillingUpdateSerializer, responses=OpenApiTypes.OBJECT)
    def put(self, request, pk):
        """`{bill_to, company_id?, routing?, purchase_order?, notes?, move_existing?}` (by default moves the
        posted charges the new rules send elsewhere) → the billing payload + `moved`."""
        reservation = self._reservation(request, pk)
        data = s.BillingUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        values = data.validated_data
        company = None
        if values["bill_to"] == ReservationBilling.BillTo.COMPANY:
            if not values.get("company_id"):
                raise ValidationError({"company_id": ["Elige la empresa"]})
            company = get_object_or_404(Company, pk=values["company_id"], organization=request.organization)
        _, moved = services.set_billing(
            reservation,
            bill_to=values["bill_to"],
            company=company,
            routing=values["routing"],
            purchase_order=values["purchase_order"],
            notes=values["notes"],
            actor=request.user,
            move_existing=values["move_existing"],
        )
        return Response({**billing_payload(reservation), "moved": moved})


class ReceivablesView(PropertyScopedAPIView):
    """`GET receivables/`: receivables of the active property by company (aging, overdue, credit)."""

    required_permissions = {"get": "corporate.view"}

    @extend_schema(parameters=[OpenApiParameter("as_of", OpenApiTypes.DATE)], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(services.receivables(request.property, as_of=_date_param(request, "as_of")))


class ReceivablesExportView(PropertyScopedAPIView):
    """`GET receivables/export/`: the receivables summary as CSV."""

    required_permissions = {"get": "corporate.view"}

    @extend_schema(responses={(200, "text/csv"): OpenApiTypes.STR})
    def get(self, request):
        data = services.receivables(request.property)
        rows = [
            [
                row["company"]["legal_name"],
                row["company"]["nit_display"],
                row["aging"]["current"],
                row["aging"]["d31_60"],
                row["aging"]["d61_90"],
                row["aging"]["d90_plus"],
                row["balance"],
                row["overdue"],
                row["unapplied"],
                row["net_balance"],
                row["in_progress"],
            ]
            for row in data["companies"]
        ]
        totals, aging = data["totals"], data["aging"]
        rows.append(
            [
                "Total",
                "",
                aging["current"],
                aging["d31_60"],
                aging["d61_90"],
                aging["d90_plus"],
                totals["balance"],
                totals["overdue"],
                totals["unapplied"],
                totals["net_balance"],
                totals["in_progress"],
            ]
        )
        return csv_response(
            f"cartera-{data['as_of']}.csv",
            [
                "Empresa",
                "NIT",
                "0-30",
                "31-60",
                "61-90",
                "90+",
                "Saldo",
                "Vencido",
                "A favor",
                "Neto",
                "En curso",
            ],
            rows,
        )
