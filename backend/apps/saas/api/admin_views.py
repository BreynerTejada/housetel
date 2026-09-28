"""Platform super-admin API (`/api/v1/saas/admin/…`): session + `is_platform_admin`, no `X-Property-Id`."""

from django.conf import settings
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core import automation
from apps.core.api.pagination import StandardPagination
from apps.core.errors import ConfirmationRequired, DomainError
from apps.core.integrations import get_provider, get_setting
from apps.core.models import Organization
from apps.saas.api.permissions import IsPlatformAdmin
from apps.saas.api.serializers import (
    CommissionSerializer,
    CommissionSettlementSerializer,
    InvoiceVoidSerializer,
    OrganizationSuspendSerializer,
    PlanSerializer,
    PlatformBillingSettingsSerializer,
    PlatformInvoiceSerializer,
    SettlementMonthSerializer,
    SimulateFailureSerializer,
    SubscriptionPlanChangeSerializer,
    SubscriptionSerializer,
    TrialExtensionSerializer,
)
from apps.saas.models import Commission, CommissionSettlement, Plan, PlatformInvoice, Subscription
from apps.saas.services import billing, commissions, metrics
from apps.saas.services.pdf import invoice_pdf
from apps.saas.services.plans import ensure_default_plans, plans_with_counts


class AdminAPIView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]


def _confirmed(data) -> None:
    if data.get("confirm") is not True:
        raise ConfirmationRequired("Confirma la acción enviando confirm: true")


# ---- Metrics ------------------------------------------------------------------------------------


class MetricsView(AdminAPIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(metrics.platform_metrics())


# ---- Organizations ------------------------------------------------------------------------------


def _customer_since(org):
    """When the organization started with Housetel: its creation, or its first invoiced period if earlier
    (organizations migrated or seeded with history)."""
    created = timezone.localtime(org.created_at).date()
    first_invoice = getattr(org, "first_invoice_start", None)
    return min(created, first_invoice) if first_invoice else created


def _org_row(org, units: dict) -> dict:
    sub = getattr(org, "subscription", None)
    return {
        "id": str(org.pk),
        "name": org.name,
        "slug": org.slug,
        "legal_name": org.legal_name,
        "nit": org.nit,
        "status": org.status,
        "created_at": org.created_at,
        "customer_since": _customer_since(org),
        "trial_ends_at": sub.trial_ends_at if sub else org.trial_ends_at,
        "subscription": {
            "status": sub.status,
            "billing_cycle": sub.billing_cycle,
            "current_period_end": sub.current_period_end,
            "cancel_at_period_end": sub.cancel_at_period_end,
            "has_payment_method": bool(sub.payment_source),
        }
        if sub
        else None,
        "plan": {"code": sub.plan.code, "name": sub.plan.name, "max_units": sub.plan.max_units}
        if sub
        else None,
        "units": units.get(org.pk, 0),
        "properties_count": getattr(org, "properties_count", None),
        "users_count": getattr(org, "users_count", None),
        "mrr": billing.money(metrics.organization_mrr(sub)),
        "simulate_payment_failure": bool((org.settings or {}).get("simulate_payment_failure")),
    }


def _orgs_queryset():
    first_invoice = (
        PlatformInvoice.objects.filter(organization=OuterRef("pk"))
        .order_by("period_start")
        .values("period_start")[:1]
    )
    return Organization.objects.select_related("subscription__plan").annotate(
        properties_count=Count("properties", distinct=True),
        users_count=Count("memberships", filter=Q(memberships__is_active=True), distinct=True),
        first_invoice_start=Subquery(first_invoice),
    )


class OrganizationListView(AdminAPIView):
    """`GET admin/organizations/?status=&plan=&q=` (paginated)."""

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str),
            OpenApiParameter("plan", str),
            OpenApiParameter("q", str),
            OpenApiParameter("page", int),
            OpenApiParameter("page_size", int),
        ],
        responses=OpenApiTypes.OBJECT,
        operation_id="saas_admin_organizations_list",
    )
    def get(self, request):
        qs = _orgs_queryset().order_by("name")
        status = request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)
        plan = request.query_params.get("plan")
        if plan:
            qs = qs.filter(subscription__plan__code=plan)
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(slug__icontains=q) | Q(nit__icontains=q))
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        units = billing.units_by_organization([o.pk for o in page])
        return paginator.get_paginated_response([_org_row(org, units) for org in page])


def _org(pk) -> Organization:
    return get_object_or_404(_orgs_queryset(), pk=pk)


def _units_by_property(org) -> dict:
    from apps.inventory.models import Bed, Room

    result: dict = {}
    for row in (
        Room.objects.filter(
            property__organization=org, is_active=True, room_type__is_active=True, room_type__kind="private"
        )
        .values("property_id")
        .annotate(n=Count("id"))
    ):
        result[row["property_id"]] = row["n"]
    for row in (
        Bed.objects.filter(
            room__property__organization=org,
            is_active=True,
            room__is_active=True,
            room__room_type__is_active=True,
            room__room_type__kind="dorm",
        )
        .values("room__property_id")
        .annotate(n=Count("id"))
    ):
        result[row["room__property_id"]] = result.get(row["room__property_id"], 0) + row["n"]
    return result


def _org_detail(org) -> dict:
    from apps.accounts.models import Invitation, Membership
    from apps.bookings.models import Reservation

    units = billing.units_by_organization([org.pk])
    data = _org_row(org, units)
    sub = billing.get_subscription(org)
    per_property = _units_by_property(org)
    reservations = {
        row["property_id"]: row["n"]
        for row in Reservation.objects.filter(property__organization=org)
        .values("property_id")
        .annotate(n=Count("id"))
    }
    data["properties"] = [
        {
            "id": str(p.pk),
            "name": p.name,
            "slug": p.slug,
            "city": p.city,
            "department": p.department,
            "property_type": p.property_type,
            "status": p.status,
            "units": per_property.get(p.pk, 0),
            "reservations": reservations.get(p.pk, 0),
            "marketplace_listed": p.marketplace_listed,
            "commission_rate": str(p.commission_rate),
            "business_date": p.business_date,
        }
        for p in org.properties.order_by("name")
    ]
    data["users"] = [
        {
            "id": str(m.user_id),
            "email": m.user.email,
            "full_name": m.user.full_name,
            "role": {"code": m.role.code, "name": m.role.name},
            "is_active": m.is_active,
            "all_properties": m.all_properties,
            "last_login": m.user.last_login,
        }
        for m in Membership.objects.filter(organization=org)
        .select_related("user", "role")
        .order_by("user__email")
    ]
    data["pending_invitations"] = Invitation.objects.filter(
        organization=org, accepted_at__isnull=True, expires_at__gt=timezone.now()
    ).count()
    data["subscription_detail"] = SubscriptionSerializer(sub).data if sub else None
    data["usage"] = billing.usage(org, sub) if sub else None
    data["upcoming_invoice"] = billing.upcoming_invoice(sub) if sub else None
    data["invoices"] = PlatformInvoiceSerializer(
        PlatformInvoice.objects.filter(organization=org)
        .select_related("organization")
        .order_by("-issued_at")[:24],
        many=True,
    ).data
    comm_qs = Commission.objects.filter(organization=org)
    data["commissions"] = {
        "summary": commissions.commissions_summary(comm_qs),
        "recent": CommissionSerializer(
            comm_qs.select_related("organization", "property", "reservation").order_by("-accrual_date")[:20],
            many=True,
        ).data,
    }
    data["settlements"] = CommissionSettlementSerializer(
        CommissionSettlement.objects.filter(organization=org).select_related("organization", "invoice")[:24],
        many=True,
    ).data
    return data


class OrganizationDetailView(AdminAPIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        return Response(_org_detail(_org(pk)))


class OrganizationSuspendView(AdminAPIView):
    @extend_schema(request=OrganizationSuspendSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        serializer = OrganizationSuspendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _confirmed(serializer.validated_data)
        org = _org(pk)
        with transaction.atomic():
            billing.suspend_organization(
                org, actor=request.user, reason=serializer.validated_data.get("reason", "")
            )
        return Response(_org_detail(_org(pk)))


class OrganizationReactivateView(AdminAPIView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        org = _org(pk)
        with transaction.atomic():
            billing.reactivate_organization(org, actor=request.user)
        return Response(_org_detail(_org(pk)))


class OrganizationExtendTrialView(AdminAPIView):
    @extend_schema(request=TrialExtensionSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        serializer = TrialExtensionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org = _org(pk)
        with transaction.atomic():
            billing.extend_trial(org, serializer.validated_data["days"], actor=request.user)
        return Response(_org_detail(_org(pk)))


class OrganizationEndTrialView(AdminAPIView):
    """`POST admin/organizations/{id}/end-trial/`: the trial ends now; the first invoice is issued and charged
    (card on file → active; no card or declined → past due)."""

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        org = _org(pk)
        with transaction.atomic():
            billing.end_trial_now(org, actor=request.user)
        return Response(_org_detail(_org(pk)))


class OrganizationChangePlanView(AdminAPIView):
    @extend_schema(request=SubscriptionPlanChangeSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        serializer = SubscriptionPlanChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org = _org(pk)
        sub = billing.get_subscription(org)
        if sub is None:
            raise DomainError("La organización no tiene suscripción", code="no_subscription")
        plan = get_object_or_404(Plan, code=serializer.validated_data["plan_code"])
        with transaction.atomic():
            billing.change_plan(
                sub,
                plan,
                cycle=serializer.validated_data.get("billing_cycle"),
                actor=request.user,
                source="user",
                force=True,
            )
        return Response(_org_detail(_org(pk)))


class OrganizationSimulateFailureView(AdminAPIView):
    """Demo helper: the simulated billing provider declines this organization's charges while enabled."""

    @extend_schema(request=SimulateFailureSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        serializer = SimulateFailureSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        org = _org(pk)
        org.settings = {
            **(org.settings or {}),
            "simulate_payment_failure": serializer.validated_data["enabled"],
        }
        org.save(update_fields=["settings", "updated_at"])
        return Response(_org_detail(_org(pk)))


# ---- Plans --------------------------------------------------------------------------------------


class PlanViewSet(viewsets.ModelViewSet):
    """CRUD `admin/plans/`. Deleting a plan with subscriptions → 409 `in_use` (deactivate it instead)."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = PlanSerializer
    pagination_class = None
    lookup_field = "pk"

    def get_queryset(self):
        ensure_default_plans()
        return plans_with_counts()


# ---- Invoices -----------------------------------------------------------------------------------


class InvoiceAdminViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = PlatformInvoiceSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = PlatformInvoice.objects.select_related("organization").order_by("-issued_at", "-number")
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("organization"):
            qs = qs.filter(organization_id=params["organization"])
        if params.get("kind"):
            qs = qs.filter(kind=params["kind"])
        if params.get("q"):
            qs = qs.filter(Q(number__icontains=params["q"]) | Q(organization__name__icontains=params["q"]))
        return qs

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str),
            OpenApiParameter("organization", str),
            OpenApiParameter("kind", str),
            OpenApiParameter("q", str),
        ]
    )
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        totals = PlatformInvoice.objects.aggregate(
            open_total=_sum_filter(status__in=["open", "failed"]),
            paid_month=_sum_filter(status="paid", paid_at__date__gte=billing.today().replace(day=1)),
        )
        response.data["summary"] = {k: billing.money(v) for k, v in totals.items()}
        return response


def _sum_filter(**conditions):
    from django.db.models import Sum

    return Sum("total", filter=Q(**conditions))


def _admin_invoice(pk) -> PlatformInvoice:
    return get_object_or_404(PlatformInvoice.objects.select_related("organization"), pk=pk)


class InvoiceMarkPaidView(AdminAPIView):
    @extend_schema(request=InvoiceVoidSerializer, responses=PlatformInvoiceSerializer)
    def post(self, request, pk):
        _confirmed(request.data)
        invoice = _admin_invoice(pk)
        with transaction.atomic():
            billing.mark_invoice_paid(
                invoice,
                reference=str(request.data.get("reference") or f"MANUAL-{timezone.localdate():%Y%m%d}"),
                method="manual",
                actor=request.user,
            )
        invoice.refresh_from_db()
        return Response(PlatformInvoiceSerializer(invoice).data)


class InvoiceVoidView(AdminAPIView):
    @extend_schema(request=InvoiceVoidSerializer, responses=PlatformInvoiceSerializer)
    def post(self, request, pk):
        serializer = InvoiceVoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        _confirmed(serializer.validated_data)
        invoice = _admin_invoice(pk)
        with transaction.atomic():
            billing.void_invoice(
                invoice, actor=request.user, reason=serializer.validated_data.get("reason", "")
            )
        invoice.refresh_from_db()
        return Response(PlatformInvoiceSerializer(invoice).data)


class InvoiceChargeView(AdminAPIView):
    """Retry the charge now with the saved payment method (simulated: approved unless failures are on)."""

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        invoice = _admin_invoice(pk)
        with transaction.atomic():
            result = billing.charge_invoice(invoice, actor=request.user, source="user")
        invoice.refresh_from_db()
        return Response({"status": result.get("status"), "message": result.get("message", ""),
                         "invoice": PlatformInvoiceSerializer(invoice).data})  # fmt: skip


class InvoiceAdminPdfView(AdminAPIView):
    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        invoice = _admin_invoice(pk)
        lang = request.query_params.get("lang") or getattr(request.user, "language", "es")
        response = HttpResponse(invoice_pdf(invoice, lang), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.number}.pdf"'
        return response


# ---- Commissions & settlements --------------------------------------------------------------------


class CommissionAdminViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = CommissionSerializer
    pagination_class = StandardPagination

    def filtered(self):
        qs = Commission.objects.all()
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("organization"):
            qs = qs.filter(organization_id=params["organization"])
        if params.get("property"):
            qs = qs.filter(property_id=params["property"])
        month = params.get("month")
        if month and len(month) == 7:
            try:
                start, end = billing.month_bounds(int(month[:4]), int(month[5:]))
            except ValueError:
                raise DomainError("Mes inválido (usa AAAA-MM)", code="invalid_month") from None
            qs = qs.filter(accrual_date__gte=start, accrual_date__lte=end)
        if params.get("q"):
            qs = qs.filter(reservation__code__icontains=params["q"])
        return qs

    def get_queryset(self):
        return (
            self.filtered()
            .select_related("organization", "property", "reservation")
            .order_by("-accrual_date", "-created_at")
        )

    @extend_schema(
        parameters=[
            OpenApiParameter("status", str),
            OpenApiParameter("organization", str),
            OpenApiParameter("property", str),
            OpenApiParameter("month", str, description="YYYY-MM (accrual month)"),
            OpenApiParameter("q", str),
        ]
    )
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data["summary"] = commissions.commissions_summary(self.filtered())
        return response


class SettlementAdminViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]
    serializer_class = CommissionSettlementSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        qs = CommissionSettlement.objects.select_related("organization", "invoice").order_by(
            "-period_start", "organization__name"
        )
        if self.request.query_params.get("organization"):
            qs = qs.filter(organization_id=self.request.query_params["organization"])
        return qs


class SettlementRunView(AdminAPIView):
    """`POST admin/settlements/run/` `{month: "2026-08"}` → settles and invoices that month now."""

    @extend_schema(request=SettlementMonthSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = SettlementMonthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        year, month = (int(part) for part in serializer.validated_data["month"].split("-"))
        today = billing.today()
        if (year, month) >= (today.year, today.month):
            raise DomainError("Solo se liquidan meses cerrados", code="month_not_closed")
        run = automation.run(
            "saas.commission_settlement",
            None,
            params={"year": year, "month": month},
            triggered_by=request.user,
        )
        period_start = billing.month_bounds(year, month)[0]
        settlements = CommissionSettlement.objects.filter(period_start=period_start).select_related(
            "organization", "invoice"
        )
        return Response(
            {
                "run": {"id": str(run.pk), "status": run.status, "summary": run.summary},
                "settlements": CommissionSettlementSerializer(settlements, many=True).data,
            }
        )


class BillingCycleRunView(AdminAPIView):
    """`POST admin/billing-cycle/run/` → runs `saas.billing_cycle` now (same as the 03:00 run)."""

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        run = automation.run("saas.billing_cycle", None, triggered_by=request.user)
        return Response(
            {"id": str(run.pk), "status": run.status, "summary": run.summary, "details": run.details}
        )


# ---- Platform billing integration -----------------------------------------------------------------


def _billing_settings_payload() -> dict:
    setting = get_setting(None, "saas_billing")
    return {
        "mode": setting.mode,
        "enabled": setting.enabled,
        "status": setting.status,
        "status_message": setting.status_message,
        "last_checked_at": setting.last_checked_at,
        "wompi": {
            "environment": settings.WOMPI_PLATFORM_ENV,
            "public_key_configured": bool(settings.WOMPI_PLATFORM_PUBLIC_KEY),
            "private_key_configured": bool(settings.WOMPI_PLATFORM_PRIVATE_KEY),
            "integrity_secret_configured": bool(settings.WOMPI_PLATFORM_INTEGRITY_SECRET),
            "events_secret_configured": bool(settings.WOMPI_PLATFORM_EVENTS_SECRET),
            "webhook_url": f"{settings.FRONTEND_URL}/api/v1/public/saas/webhooks/wompi/",
        },
    }


class BillingSettingsView(AdminAPIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(_billing_settings_payload())

    @extend_schema(request=PlatformBillingSettingsSerializer, responses=OpenApiTypes.OBJECT)
    def patch(self, request):
        serializer = PlatformBillingSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        setting = get_setting(None, "saas_billing")
        for key, value in serializer.validated_data.items():
            setattr(setting, key, value)
        setting.status = "unknown"
        setting.status_message = ""
        setting.save()
        return Response(_billing_settings_payload())


class BillingSettingsTestView(AdminAPIView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        setting = get_setting(None, "saas_billing")
        ok, message = get_provider(None, "saas_billing").test_connection()
        setting.status = "ok" if ok else "error"
        setting.status_message = message
        setting.last_checked_at = timezone.now()
        setting.save(update_fields=["status", "status_message", "last_checked_at", "updated_at"])
        return Response(_billing_settings_payload())


class SubscriptionAdminListView(AdminAPIView):
    """`GET admin/subscriptions/` (small helper list for the billing page)."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        subs = Subscription.objects.select_related("plan", "organization").order_by("organization__name")
        return Response(
            [
                {
                    "organization": {"id": str(s.organization_id), "name": s.organization.name},
                    **SubscriptionSerializer(s).data,
                }
                for s in subs
            ]  # fmt: skip
        )
