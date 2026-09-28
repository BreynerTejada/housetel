"""Staff SaaS API (`/api/v1/saas/…`, session + `X-Property-Id`). Billing keeps working while the organization
is suspended (`allow_suspended = True`), so the hotel can always pay and reactivate itself."""

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response

from apps.core.errors import ConfirmationRequired, DomainError
from apps.core.tenancy import PropertyScopedAPIView
from apps.saas.api.serializers import (
    BillingPaymentMethodSerializer,
    CommissionSerializer,
    CommissionSettlementSerializer,
    PlanRefSerializer,
    PlatformInvoiceSerializer,
    SubscriptionCancelSerializer,
    SubscriptionPlanChangeSerializer,
    SubscriptionSerializer,
)
from apps.saas.models import Commission, CommissionSettlement, Plan, PlatformInvoice, Subscription
from apps.saas.services import billing, checklist, commissions
from apps.saas.services.pdf import invoice_pdf
from apps.saas.services.plans import active_plans, ensure_default_plans, plan_fits


class _NoSubscription(DomainError):
    code = "no_subscription"
    status_code = 404


def _require_subscription(org) -> Subscription:
    sub = billing.get_subscription(org)
    if sub is None:
        raise _NoSubscription("Tu organización aún no tiene una suscripción")
    return sub


class BillingBaseView(PropertyScopedAPIView):
    allow_suspended = True


class BillingOverviewView(BillingBaseView):
    """`GET billing/`: plan, status, usage, next charge, open balance and the plans to switch to."""

    required_permissions = {"get": "saas.billing_view"}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        org = request.organization
        ensure_default_plans()
        sub = billing.ensure_subscription(org)
        info = billing.usage(org, sub)
        unpaid = list(billing.unpaid_invoices(org).order_by("issued_at"))
        plans = []
        for plan in active_plans():
            data = PlanRefSerializer(plan).data
            data["description"] = plan.description
            data["fits"] = plan_fits(plan, units=info["units"], properties=info["properties"])
            data["current"] = plan.pk == sub.plan_id
            plans.append(data)
        return Response(
            {
                "organization": {
                    "id": str(org.pk),
                    "name": org.name,
                    "status": org.status,
                    "trial_ends_at": org.trial_ends_at,
                },
                "subscription": SubscriptionSerializer(sub).data,
                "summary": billing.organization_summary(org),
                "usage": info,
                "upcoming_invoice": billing.upcoming_invoice(sub),
                "open_invoices": PlatformInvoiceSerializer(unpaid, many=True).data,
                "plans": plans,
                "billing_mode": billing.billing_mode(),
                "tax_rate": str(billing.TAX_RATE),
                "retry_schedule_days": list(billing.RETRY_SCHEDULE_DAYS),
            }
        )


class BillingStatusView(BillingBaseView):
    """`GET billing/status/` (any member): the small payload of the topbar chip and the suspension banner."""

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(billing.organization_summary(request.organization))


class InvoiceListView(BillingBaseView):
    required_permissions = {"get": "saas.billing_view"}

    @extend_schema(responses=PlatformInvoiceSerializer(many=True))
    def get(self, request):
        invoices = PlatformInvoice.objects.filter(organization=request.organization).select_related(
            "organization"
        )
        return Response(
            PlatformInvoiceSerializer(invoices.order_by("-issued_at", "-number")[:120], many=True).data
        )


def _invoice_of(request, pk) -> PlatformInvoice:
    return get_object_or_404(
        PlatformInvoice.objects.select_related("organization"), pk=pk, organization=request.organization
    )


class InvoiceDetailView(BillingBaseView):
    required_permissions = {"get": "saas.billing_view"}

    @extend_schema(responses=PlatformInvoiceSerializer)
    def get(self, request, pk):
        return Response(PlatformInvoiceSerializer(_invoice_of(request, pk)).data)


class InvoicePdfView(BillingBaseView):
    required_permissions = {"get": "saas.billing_view"}

    @extend_schema(responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        invoice = _invoice_of(request, pk)
        lang = request.query_params.get("lang") or getattr(request.user, "language", "es")
        response = HttpResponse(invoice_pdf(invoice, lang), content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{invoice.number}.pdf"'
        return response


class InvoicePayView(BillingBaseView):
    """`POST billing/invoices/{id}/pay/` → simulated: charged now (`status` approved|declined); real: Wompi
    `checkout_url` (returns to `/app/settings/billing?invoice=<id>`)."""

    required_permissions = {"post": "saas.billing_manage"}

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request, pk):
        with transaction.atomic():
            invoice = _invoice_of(request, pk)
            return_url = f"{settings.FRONTEND_URL}/app/settings/billing?invoice={invoice.pk}"
            result = billing.pay_invoice(invoice, actor=request.user, return_url=return_url)
        invoice.refresh_from_db()
        return Response({**result, "invoice": PlatformInvoiceSerializer(invoice).data})


class InvoiceVerifyView(BillingBaseView):
    required_permissions = {"post": "saas.billing_view"}

    @extend_schema(request=None, responses=PlatformInvoiceSerializer)
    def post(self, request, pk):
        with transaction.atomic():
            invoice = billing.verify_invoice_payment(_invoice_of(request, pk), actor=request.user)
        return Response(PlatformInvoiceSerializer(invoice).data)


class PaymentMethodView(BillingBaseView):
    """`GET billing/payment-method/` → what the card form needs (`{mode}`; real mode adds the Wompi public
    key, the tokenization URL and the two acceptance documents). `POST`: simulated → test card `{holder,
    number, exp_month, exp_year, cvc}` (only brand and last 4 are kept); real → `{token, acceptance_token,
    accept_personal_auth}` (the browser tokenized the card with Wompi). `DELETE` forgets it."""

    required_permissions = {
        "get": "saas.billing_manage",
        "post": "saas.billing_manage",
        "delete": "saas.billing_manage",
    }

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(billing.payment_method_setup())

    @extend_schema(request=BillingPaymentMethodSerializer, responses=SubscriptionSerializer)
    def post(self, request):
        serializer = BillingPaymentMethodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sub = _require_subscription(request.organization)
        with transaction.atomic():
            billing.set_payment_method(sub, serializer.validated_data, actor=request.user)
        return Response(SubscriptionSerializer(sub).data)

    @extend_schema(request=None, responses=SubscriptionSerializer)
    def delete(self, request):
        sub = _require_subscription(request.organization)
        sub.payment_source = {}
        sub.save(update_fields=["payment_source", "updated_at"])
        return Response(SubscriptionSerializer(sub).data)


class ChangePlanView(BillingBaseView):
    required_permissions = {"post": "saas.billing_manage"}

    @extend_schema(request=SubscriptionPlanChangeSerializer, responses=SubscriptionSerializer)
    def post(self, request):
        serializer = SubscriptionPlanChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sub = _require_subscription(request.organization)
        plan = get_object_or_404(Plan, code=serializer.validated_data["plan_code"], is_active=True)
        with transaction.atomic():
            billing.change_plan(
                sub, plan, cycle=serializer.validated_data.get("billing_cycle"), actor=request.user
            )
        sub.refresh_from_db()
        return Response(SubscriptionSerializer(sub).data)


class CancelView(BillingBaseView):
    required_permissions = {"post": "saas.billing_manage"}

    @extend_schema(request=SubscriptionCancelSerializer, responses=SubscriptionSerializer)
    def post(self, request):
        serializer = SubscriptionCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["confirm"] is not True:
            raise ConfirmationRequired("Confirma la cancelación")
        sub = _require_subscription(request.organization)
        with transaction.atomic():
            billing.cancel_subscription(
                sub, actor=request.user, reason=serializer.validated_data.get("reason", "")
            )
        return Response(SubscriptionSerializer(sub).data)


class ResumeView(BillingBaseView):
    required_permissions = {"post": "saas.billing_manage"}

    @extend_schema(request=None, responses=SubscriptionSerializer)
    def post(self, request):
        sub = _require_subscription(request.organization)
        with transaction.atomic():
            billing.resume_subscription(sub, actor=request.user)
        return Response(SubscriptionSerializer(sub).data)


class HotelCommissionsView(BillingBaseView):
    """`GET billing/commissions/`: the organization's marketplace commissions statement."""

    required_permissions = {"get": "saas.billing_view"}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        org = request.organization
        qs = Commission.objects.filter(organization=org)
        today = billing.today()
        month_start = today.replace(day=1)
        this_month = qs.exclude(status=Commission.Status.REVERSED).filter(
            accrual_date__gte=month_start, accrual_date__lte=today
        )
        # Latest marketplace bookings first (the accrual date of a future stay is months away).
        recent = qs.select_related("organization", "property", "reservation").order_by(
            "-reservation__created_at", "-created_at"
        )
        settlements = CommissionSettlement.objects.filter(organization=org).select_related(
            "organization", "invoice"
        )
        return Response(
            {
                "summary": commissions.commissions_summary(qs),
                "this_month": commissions.commissions_summary(this_month),
                "rates": [
                    {
                        "property_id": str(p.pk),
                        "name": p.name,
                        "commission_rate": str(p.commission_rate),
                        "marketplace_listed": p.marketplace_listed,
                    }
                    for p in org.properties.order_by("name")
                ],  # fmt: skip
                "settlements": CommissionSettlementSerializer(settlements[:24], many=True).data,
                "recent": CommissionSerializer(recent[:50], many=True).data,
            }
        )


class GettingStartedView(PropertyScopedAPIView):
    """`GET getting-started/` (any member): the onboarding checklist of the active property + trial info."""

    allow_suspended = True

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        data = checklist.getting_started(request.property, request.organization)
        data["billing"] = billing.organization_summary(request.organization)
        return Response(data)
