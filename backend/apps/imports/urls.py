from django.urls import path

from apps.imports.api import views as v

app_name = "imports"

urlpatterns = [
    path("catalog/", v.CatalogView.as_view(), name="catalog"),
    path("jobs/", v.JobListView.as_view(), name="jobs"),
    path("jobs/<uuid:pk>/", v.JobDetailView.as_view(), name="job"),
    path("jobs/<uuid:pk>/rows/", v.JobRowsView.as_view(), name="job-rows"),
    path("jobs/<uuid:pk>/dry-run/", v.JobDryRunView.as_view(), name="job-dry-run"),
    path("jobs/<uuid:pk>/run/", v.JobRunView.as_view(), name="job-run"),
    path("jobs/<uuid:pk>/revert/", v.JobRevertView.as_view(), name="job-revert"),
    path("jobs/<uuid:pk>/revert-preview/", v.JobRevertPreviewView.as_view(), name="job-revert-preview"),
    path("jobs/<uuid:pk>/report/", v.JobReportView.as_view(), name="job-report"),
    path("templates/<str:kind>/", v.TemplateView.as_view(), name="template"),
]
