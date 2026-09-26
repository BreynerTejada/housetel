from django.urls import path

from apps.core.api.views import PropertyContextView

app_name = "core"

urlpatterns = [
    path("context/", PropertyContextView.as_view(), name="context"),
]
