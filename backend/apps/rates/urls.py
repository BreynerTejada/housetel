"""`/api/v1/rates/` (staff, header `X-Property-Id`)."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.rates.api import views

app_name = "rates"

router = SimpleRouter()
router.register("taxes", views.TaxViewSet, basename="tax")
router.register("cancellation-policies", views.CancellationPolicyViewSet, basename="cancellation-policy")
router.register("rate-plans", views.RatePlanViewSet, basename="rate-plan")
router.register("room-type-defaults", views.RoomTypeRateDefaultsViewSet, basename="room-type-defaults")
router.register("seasons", views.SeasonViewSet, basename="season")
router.register("season-rates", views.SeasonRateViewSet, basename="season-rate")
router.register("extras", views.ExtraViewSet, basename="extra")
router.register("promo-codes", views.PromoCodeViewSet, basename="promo-code")

urlpatterns = [
    path("grid/", views.GridView.as_view(), name="grid"),
    path("grid/bulk/", views.GridBulkView.as_view(), name="grid-bulk"),
    path("quote/", views.QuoteView.as_view(), name="quote"),
    path("holidays/", views.HolidaysView.as_view(), name="holidays"),
    path("room-types/", views.RoomTypesView.as_view(), name="room-types"),
    *router.urls,
]
