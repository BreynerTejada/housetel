from django.urls import include, path
from rest_framework.routers import SimpleRouter

from apps.bookings.api import views

app_name = "bookings"

router = SimpleRouter()
router.register("reservations", views.ReservationViewSet, basename="reservation")
router.register("stays", views.StayViewSet, basename="stay")
router.register("groups", views.GroupViewSet, basename="group")
router.register("blocks", views.BlockViewSet, basename="block")

urlpatterns = [
    path("availability/", views.AvailabilityView.as_view(), name="availability"),
    path("offers/", views.OffersView.as_view(), name="offers"),
    path("room-offers/", views.RoomOffersView.as_view(), name="room-offers"),
    path("calendar/", views.CalendarView.as_view(), name="calendar"),
    path("auto-assign/", views.AutoAssignView.as_view(), name="auto-assign"),
    path("inventory/rebuild/", views.InventoryRebuildView.as_view(), name="inventory-rebuild"),
    path("", include(router.urls)),
]
