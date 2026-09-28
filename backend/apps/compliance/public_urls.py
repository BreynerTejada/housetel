from django.urls import path

from apps.compliance.api.public_views import PortalInvoicePdfView, PortalInvoicesView

app_name = "compliance_public"

urlpatterns = [
    path("portal/<str:token>/invoices/", PortalInvoicesView.as_view(), name="portal-invoices"),
    path(
        "portal/<str:token>/invoices/<uuid:pk>/pdf/",
        PortalInvoicePdfView.as_view(),
        name="portal-invoice-pdf",
    ),
]
