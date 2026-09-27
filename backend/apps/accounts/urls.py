from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.accounts.api.team_views import InvitationViewSet, MemberViewSet, PermissionCatalogView, RoleViewSet
from apps.accounts.api.views import CsrfView, LoginView, LogoutView, MeView

app_name = "accounts"

router = SimpleRouter()
router.register("users", MemberViewSet, basename="member")
router.register("invitations", InvitationViewSet, basename="invitation")
router.register("roles", RoleViewSet, basename="role")

urlpatterns = [
    path("auth/csrf/", CsrfView.as_view(), name="csrf"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("permissions/", PermissionCatalogView.as_view(), name="permissions"),
    *router.urls,
]
