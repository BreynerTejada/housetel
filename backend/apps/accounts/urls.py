from django.urls import path

from apps.accounts.api.views import CsrfView, LoginView, LogoutView, MeView

app_name = "accounts"

urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
]
