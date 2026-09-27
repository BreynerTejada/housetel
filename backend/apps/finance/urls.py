from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.finance.api.views import (
    CashShiftViewSet,
    ChargeViewSet,
    FolioViewSet,
    PaymentIntentViewSet,
    PaymentViewSet,
    RefundViewSet,
    SummaryView,
)

app_name = "finance"

router = SimpleRouter()
router.register("folios", FolioViewSet, basename="folio")
router.register("charges", ChargeViewSet, basename="charge")
router.register("payments", PaymentViewSet, basename="payment")
router.register("refunds", RefundViewSet, basename="refund")
router.register("intents", PaymentIntentViewSet, basename="intent")
router.register("cash-shifts", CashShiftViewSet, basename="cash-shift")

urlpatterns = [
    path("summary/", SummaryView.as_view(), name="summary"),
    *router.urls,
]
