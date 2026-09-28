from django.urls import path

from apps.marketplace.api import staff_views as views

app_name = "marketplace"

urlpatterns = [
    path("booking-engine/", views.BookingEngineView.as_view(), name="booking-engine"),
    path("booking-engine/<str:kind>/", views.EngineImageView.as_view(), name="booking-engine-image"),
    path("listing/", views.ListingView.as_view(), name="listing"),
    path("embed-snippet/", views.EmbedSnippetView.as_view(), name="embed-snippet"),
]
