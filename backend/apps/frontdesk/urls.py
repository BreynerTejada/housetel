from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.frontdesk.api import views

app_name = "frontdesk"

router = SimpleRouter()
router.register("night-audit/reports", views.NightAuditReportViewSet, basename="night-audit-report")

urlpatterns = [
    path("today/", views.TodayView.as_view(), name="today"),
    path("night-audit/preview/", views.NightAuditPreviewView.as_view(), name="night-audit-preview"),
    path("night-audit/run/", views.NightAuditRunView.as_view(), name="night-audit-run"),
    path("reservations/export/", views.ReservationExportView.as_view(), name="reservations-export"),
    path(
        "groups/<uuid:group_id>/rooming-list/",
        views.GroupRoomingExportView.as_view(),
        name="group-rooming-export",
    ),
    path(
        "reservations/<uuid:reservation_id>/online-checkin/",
        views.OnlineCheckinView.as_view(),
        name="reservation-online-checkin",
    ),
    path("", include(router.urls)),
]
