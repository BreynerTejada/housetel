from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.inventory.views import (
    AmenityViewSet,
    BedViewSet,
    CustomFieldViewSet,
    PhotoViewSet,
    PropertyLogoView,
    PropertyProfileView,
    RoomBlockViewSet,
    RoomTypeViewSet,
    RoomViewSet,
    SummaryView,
)

app_name = "inventory"

router = SimpleRouter()
router.register("amenities", AmenityViewSet, basename="amenity")
router.register("room-types", RoomTypeViewSet, basename="room-type")
router.register("rooms", RoomViewSet, basename="room")
router.register("custom-fields", CustomFieldViewSet, basename="custom-field")
router.register("blocks", RoomBlockViewSet, basename="block")

photos = PhotoViewSet.as_view({"get": "list", "post": "create"})
photo = PhotoViewSet.as_view({"patch": "partial_update", "delete": "destroy"})
photos_reorder = PhotoViewSet.as_view({"post": "reorder"})
beds = BedViewSet.as_view({"get": "list", "post": "create"})
bed = BedViewSet.as_view({"get": "retrieve", "put": "update", "patch": "partial_update", "delete": "destroy"})
beds_bulk = BedViewSet.as_view({"post": "bulk"})

urlpatterns = [
    path("property/", PropertyProfileView.as_view(), name="property"),
    path("property/logo/", PropertyLogoView.as_view(), name="property-logo"),
    path("property/photos/", photos, name="property-photos"),
    path("property/photos/reorder/", photos_reorder, name="property-photos-reorder"),
    path("property/photos/<uuid:photo_id>/", photo, name="property-photo"),
    path("room-types/<uuid:room_type_id>/photos/", photos, name="room-type-photos"),
    path("room-types/<uuid:room_type_id>/photos/reorder/", photos_reorder, name="room-type-photos-reorder"),
    path("room-types/<uuid:room_type_id>/photos/<uuid:photo_id>/", photo, name="room-type-photo"),
    path("rooms/<uuid:room_id>/beds/", beds, name="room-beds"),
    path("rooms/<uuid:room_id>/beds/bulk/", beds_bulk, name="room-beds-bulk"),
    path("rooms/<uuid:room_id>/beds/<uuid:pk>/", bed, name="room-bed"),
    path("summary/", SummaryView.as_view(), name="summary"),
    *router.urls,
]
