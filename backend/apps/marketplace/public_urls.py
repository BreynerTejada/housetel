from django.urls import path

from apps.marketplace.api import public_views as views

app_name = "marketplace_public"

urlpatterns = [
    path("destinations/", views.DestinationsView.as_view(), name="destinations"),
    path("search/", views.SearchView.as_view(), name="search"),
    path("properties/<slug:slug>/", views.PropertyDetailView.as_view(), name="property"),
    path("properties/<slug:slug>/offers/", views.PropertyOffersView.as_view(), name="property-offers"),
    path("properties/<slug:slug>/booking-engine/", views.EngineConfigView.as_view(), name="property-engine"),
    path("checkout/quote/", views.CheckoutQuoteView.as_view(), name="checkout-quote"),
    path("bookings/", views.BookingsView.as_view(), name="bookings"),
    path("bookings/<str:code>/", views.BookingLookupView.as_view(), name="booking-lookup"),
]
