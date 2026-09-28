from django.urls import path

from apps.control.api import views as v

app_name = "control"

urlpatterns = [
    path("integrations/", v.IntegrationListView.as_view(), name="integrations"),
    path("integrations/<str:kind>/", v.IntegrationDetailView.as_view(), name="integration"),
    path("integrations/<str:kind>/test/", v.IntegrationTestView.as_view(), name="integration-test"),
    path("automations/", v.AutomationListView.as_view(), name="automations"),
    path("automations/<str:code>/", v.AutomationDetailView.as_view(), name="automation"),
    path("automations/<str:code>/run/", v.AutomationRunNowView.as_view(), name="automation-run"),
    path("automation-runs/", v.AutomationRunListView.as_view(), name="automation-runs"),
    path("automation-runs/<uuid:pk>/", v.AutomationRunDetailView.as_view(), name="automation-run-detail"),
    path("audit/", v.AuditListView.as_view(), name="audit"),
    path("audit/facets/", v.AuditFacetsView.as_view(), name="audit-facets"),
    path("audit/<uuid:pk>/", v.AuditDetailView.as_view(), name="audit-detail"),
    path("audit/<uuid:pk>/undo/", v.AuditUndoView.as_view(), name="audit-undo"),
    path("alerts/", v.AlertListView.as_view(), name="alerts"),
    path("alerts/count/", v.AlertCountView.as_view(), name="alerts-count"),
    path("alerts/resolve/", v.AlertResolveManyView.as_view(), name="alerts-resolve"),
    path("alerts/<uuid:pk>/", v.AlertDetailView.as_view(), name="alert"),
    path("alerts/<uuid:pk>/resolve/", v.AlertResolveView.as_view(), name="alert-resolve"),
]
