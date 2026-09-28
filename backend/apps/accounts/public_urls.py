from django.urls import path

from apps.accounts.api.security_views import (
    PasswordForgotView,
    PasswordResetCheckView,
    PasswordResetView,
    VerifyEmailView,
)
from apps.accounts.api.team_views import AcceptInvitationView, PublicInvitationView

app_name = "accounts_public"

urlpatterns = [
    path("invitations/<str:token>/", PublicInvitationView.as_view(), name="invitation"),
    path("invitations/<str:token>/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
    # P2: password recovery and email verification.
    path("password/forgot/", PasswordForgotView.as_view(), name="password-forgot"),
    path("password/reset/check/", PasswordResetCheckView.as_view(), name="password-reset-check"),
    path("password/reset/", PasswordResetView.as_view(), name="password-reset"),
    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
]
