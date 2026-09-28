from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.corporate.api.views import (
    AccountPaymentViewSet,
    CompanyViewSet,
    ReceivablesExportView,
    ReceivablesView,
    ReservationBillingView,
)

app_name = "corporate"

router = SimpleRouter()
router.register("companies", CompanyViewSet, basename="company")
router.register("account-payments", AccountPaymentViewSet, basename="account-payment")

urlpatterns = [
    path("receivables/", ReceivablesView.as_view(), name="receivables"),
    path("receivables/export/", ReceivablesExportView.as_view(), name="receivables-export"),
    path("reservations/<uuid:pk>/billing/", ReservationBillingView.as_view(), name="reservation-billing"),
    *router.urls,
]
