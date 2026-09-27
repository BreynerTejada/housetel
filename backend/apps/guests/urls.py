from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.guests.api.documents import GuestDocumentFileView
from apps.guests.api.views import GuestDocumentView, GuestViewSet

app_name = "guests"

router = SimpleRouter()
router.register("guests", GuestViewSet, basename="guest")

urlpatterns = [
    path("documents/<uuid:pk>/", GuestDocumentView.as_view(), name="document-detail"),
    path("documents/<uuid:pk>/file/", GuestDocumentFileView.as_view(), name="document-file"),
    *router.urls,
]
