from django.urls import path

from apps.guestportal.api import public_views as views

app_name = "guestportal_public"

urlpatterns: list = [
    path("<str:token>/", views.PortalSummaryView.as_view(), name="summary"),
    path("<str:token>/checkin/", views.CheckinView.as_view(), name="checkin"),
    path("<str:token>/checkin/complete/", views.CheckinCompleteView.as_view(), name="checkin-complete"),
    path("<str:token>/pay/", views.PayView.as_view(), name="pay"),
    path("<str:token>/extras/", views.ExtrasView.as_view(), name="extras"),
    path("<str:token>/requests/", views.RequestsView.as_view(), name="requests"),
    path("<str:token>/cancel/", views.CancelView.as_view(), name="cancel"),
    path("<str:token>/modify-preview/", views.ModifyPreviewView.as_view(), name="modify-preview"),
    path("<str:token>/modify/", views.ModifyView.as_view(), name="modify"),
]
