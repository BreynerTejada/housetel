from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    path("", views.ReportCatalogView.as_view(), name="catalog"),
    path("<slug:report_id>/", views.ReportView.as_view(), name="report"),
]
