from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.distribution.api.views import (
    AriQueueViewSet,
    CatalogView,
    ConnectionViewSet,
    OptionsView,
    SimulatorBookingActionView,
    SimulatorBookingsView,
    SimulatorInventoryView,
    SyncLogViewSet,
)

app_name = "distribution"

router = SimpleRouter()
router.register("connections", ConnectionViewSet, basename="connection")
router.register("logs", SyncLogViewSet, basename="log")
router.register("queue", AriQueueViewSet, basename="queue")

SIM = "simulator/<uuid:connection_id>"

urlpatterns = [
    path("options/", OptionsView.as_view(), name="options"),
    path("options/catalog/", CatalogView.as_view(), name="catalog"),
    path(f"{SIM}/inventory/", SimulatorInventoryView.as_view(), name="simulator-inventory"),
    path(f"{SIM}/bookings/", SimulatorBookingsView.as_view(), name="simulator-bookings"),
    path(
        f"{SIM}/bookings/<str:external_id>/modify/",
        SimulatorBookingActionView.as_view(action_name="modify"),
        name="simulator-booking-modify",
    ),
    path(
        f"{SIM}/bookings/<str:external_id>/cancel/",
        SimulatorBookingActionView.as_view(action_name="cancel"),
        name="simulator-booking-cancel",
    ),
    path(
        f"{SIM}/bookings/<str:external_id>/deliver/",
        SimulatorBookingActionView.as_view(action_name="deliver"),
        name="simulator-booking-deliver",
    ),
    *router.urls,
]
