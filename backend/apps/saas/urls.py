from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.saas.api import admin_views, views

app_name = "saas"

router = SimpleRouter()
router.register("admin/plans", admin_views.PlanViewSet, basename="admin-plan")
router.register("admin/invoices", admin_views.InvoiceAdminViewSet, basename="admin-invoice")
router.register("admin/commissions", admin_views.CommissionAdminViewSet, basename="admin-commission")
router.register("admin/settlements", admin_views.SettlementAdminViewSet, basename="admin-settlement")

urlpatterns = [
    # Staff (X-Property-Id)
    path("billing/", views.BillingOverviewView.as_view(), name="billing"),
    path("billing/status/", views.BillingStatusView.as_view(), name="billing-status"),
    path("billing/invoices/", views.InvoiceListView.as_view(), name="billing-invoices"),
    path("billing/invoices/<uuid:pk>/", views.InvoiceDetailView.as_view(), name="billing-invoice"),
    path("billing/invoices/<uuid:pk>/pdf/", views.InvoicePdfView.as_view(), name="billing-invoice-pdf"),
    path("billing/invoices/<uuid:pk>/pay/", views.InvoicePayView.as_view(), name="billing-invoice-pay"),
    path(
        "billing/invoices/<uuid:pk>/verify/", views.InvoiceVerifyView.as_view(), name="billing-invoice-verify"
    ),
    path("billing/payment-method/", views.PaymentMethodView.as_view(), name="billing-payment-method"),
    path("billing/change-plan/", views.ChangePlanView.as_view(), name="billing-change-plan"),
    path("billing/cancel/", views.CancelView.as_view(), name="billing-cancel"),
    path("billing/resume/", views.ResumeView.as_view(), name="billing-resume"),
    path("billing/commissions/", views.HotelCommissionsView.as_view(), name="billing-commissions"),
    path("getting-started/", views.GettingStartedView.as_view(), name="getting-started"),
    # Platform super-admin (is_platform_admin, no X-Property-Id)
    path("admin/metrics/", admin_views.MetricsView.as_view(), name="admin-metrics"),
    path("admin/organizations/", admin_views.OrganizationListView.as_view(), name="admin-organizations"),
    path(
        "admin/organizations/<uuid:pk>/",
        admin_views.OrganizationDetailView.as_view(),
        name="admin-organization",
    ),
    path(
        "admin/organizations/<uuid:pk>/suspend/",
        admin_views.OrganizationSuspendView.as_view(),
        name="admin-organization-suspend",
    ),
    path(
        "admin/organizations/<uuid:pk>/reactivate/",
        admin_views.OrganizationReactivateView.as_view(),
        name="admin-organization-reactivate",
    ),
    path(
        "admin/organizations/<uuid:pk>/extend-trial/",
        admin_views.OrganizationExtendTrialView.as_view(),
        name="admin-organization-extend-trial",
    ),
    path(
        "admin/organizations/<uuid:pk>/end-trial/",
        admin_views.OrganizationEndTrialView.as_view(),
        name="admin-organization-end-trial",
    ),
    path(
        "admin/organizations/<uuid:pk>/change-plan/",
        admin_views.OrganizationChangePlanView.as_view(),
        name="admin-organization-change-plan",
    ),
    path(
        "admin/organizations/<uuid:pk>/simulate-payment-failure/",
        admin_views.OrganizationSimulateFailureView.as_view(),
        name="admin-organization-simulate-failure",
    ),
    path(
        "admin/invoices/<uuid:pk>/mark-paid/",
        admin_views.InvoiceMarkPaidView.as_view(),
        name="admin-invoice-paid",
    ),
    path("admin/invoices/<uuid:pk>/void/", admin_views.InvoiceVoidView.as_view(), name="admin-invoice-void"),
    path(
        "admin/invoices/<uuid:pk>/charge/",
        admin_views.InvoiceChargeView.as_view(),
        name="admin-invoice-charge",
    ),
    path(
        "admin/invoices/<uuid:pk>/pdf/", admin_views.InvoiceAdminPdfView.as_view(), name="admin-invoice-pdf"
    ),
    path("admin/settlements/run/", admin_views.SettlementRunView.as_view(), name="admin-settlements-run"),
    path(
        "admin/billing-cycle/run/", admin_views.BillingCycleRunView.as_view(), name="admin-billing-cycle-run"
    ),
    path("admin/billing-settings/", admin_views.BillingSettingsView.as_view(), name="admin-billing-settings"),
    path(
        "admin/billing-settings/test/",
        admin_views.BillingSettingsTestView.as_view(),
        name="admin-billing-settings-test",
    ),
    path("admin/subscriptions/", admin_views.SubscriptionAdminListView.as_view(), name="admin-subscriptions"),
    *router.urls,
]
