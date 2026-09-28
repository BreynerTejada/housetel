"""`/api/v1/revenue/` (staff, header `X-Property-Id`)."""

from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.revenue.api import views

app_name = "revenue"

router = SimpleRouter()
router.register("rules", views.PricingRuleViewSet, basename="rule")
router.register("bounds", views.PriceBoundsViewSet, basename="bounds")
router.register("recommendations", views.RecommendationViewSet, basename="recommendation")
router.register("runs", views.RunViewSet, basename="run")

urlpatterns = [
    path("settings/", views.RevenueSettingsView.as_view(), name="settings"),
    path("run-now/", views.RunNowView.as_view(), name="run-now"),
    path("simulate/", views.SimulateView.as_view(), name="simulate"),
    path("options/", views.OptionsView.as_view(), name="options"),
    *router.urls,
]
