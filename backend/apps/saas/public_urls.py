from django.urls import path

from apps.saas.api import public_views

app_name = "saas_public"

urlpatterns = [
    path("plans/", public_views.PublicPlansView.as_view(), name="plans"),
    path("signup/", public_views.SignupView.as_view(), name="signup"),
    path("webhooks/wompi/", public_views.PlatformWompiWebhookView.as_view(), name="wompi-webhook"),
]
