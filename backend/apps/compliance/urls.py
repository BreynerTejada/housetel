from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.compliance.api.views import (
    InvoiceViewSet,
    PendingView,
    ReservationLegalView,
    ResolutionViewSet,
    SettingsView,
    SireReportViewSet,
    TraRegistrationViewSet,
)

app_name = "compliance"

router = SimpleRouter()
router.register("resolutions", ResolutionViewSet, basename="resolution")
router.register("invoices", InvoiceViewSet, basename="invoice")
router.register("sire", SireReportViewSet, basename="sire")
router.register("tra", TraRegistrationViewSet, basename="tra")

urlpatterns = [
    path("settings/", SettingsView.as_view(), name="settings"),
    path("pending/", PendingView.as_view(), name="pending"),
    path("reservations/<uuid:pk>/", ReservationLegalView.as_view(), name="reservation-legal"),
    *router.urls,
]
