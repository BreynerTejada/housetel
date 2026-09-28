from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.guestportal.api import views

app_name = "guestportal"

router = SimpleRouter()
router.register("service-requests", views.ServiceRequestViewSet, basename="service-request")

urlpatterns: list = [
    path("checkins/", views.ArrivalsCheckinsView.as_view(), name="checkins"),
    path(
        "reservations/<uuid:pk>/checkin/", views.ReservationCheckinView.as_view(), name="reservation-checkin"
    ),
    path(
        "reservations/<uuid:pk>/checkin/signature/",
        views.ReservationSignatureView.as_view(),
        name="reservation-signature",
    ),
    path("reservations/<uuid:pk>/link/", views.ReservationLinkView.as_view(), name="reservation-link"),
    path("reservations/<uuid:pk>/send-link/", views.SendLinkView.as_view(), name="reservation-send-link"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    *router.urls,
]
