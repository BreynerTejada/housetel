from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.housekeeping.api.views import (
    BoardView,
    RoomStatusView,
    SettingsView,
    StaffView,
    SummaryView,
    TaskViewSet,
    TicketPhotoFileView,
    TicketViewSet,
)

app_name = "housekeeping"

router = SimpleRouter()
router.register("tasks", TaskViewSet, basename="task")
router.register("tickets", TicketViewSet, basename="ticket")

urlpatterns = [
    path("board/", BoardView.as_view(), name="board"),
    path("summary/", SummaryView.as_view(), name="summary"),
    path("staff/", StaffView.as_view(), name="staff"),
    path("settings/", SettingsView.as_view(), name="settings"),
    path("rooms/<uuid:pk>/status/", RoomStatusView.as_view(), name="room-status"),
    path("ticket-photos/<uuid:pk>/file/", TicketPhotoFileView.as_view(), name="ticket-photo-file"),
    *router.urls,
]
