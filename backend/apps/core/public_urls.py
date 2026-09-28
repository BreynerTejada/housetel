from django.urls import path

from apps.core.api.views import HealthView, ReadyView, RuntimeConfigView

app_name = "core_public"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("health/ready/", ReadyView.as_view(), name="health-ready"),
    path("config/", RuntimeConfigView.as_view(), name="config"),
]
