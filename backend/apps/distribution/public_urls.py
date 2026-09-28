from django.urls import path

from apps.distribution.api.public_views import IcalExportView

app_name = "distribution_public"

urlpatterns = [
    path("ical/<str:token>.ics", IcalExportView.as_view(), name="ical-export"),
]
