"""Password and email-verification endpoints (P2).

Public, `/api/v1/public/accounts/` (CSRF like the login; rate-limited per IP, see apps/accounts/throttles.py):
- `POST password/forgot/` {email} → 200 whatever the address (no user enumeration).
- `POST password/reset/check/` {uid, token} → {email: masked} while the link works; 400 `invalid_token`.
- `POST password/reset/` {uid, token, new_password} → `Me` and a new session; every other session ends.
- `POST verify-email/` {token} → {email, email_verified, already_verified}; 400 `invalid_token` or
  `token_expired`.

Staff, `/api/v1/accounts/` (session + CSRF; rate-limited per user):
- `POST me/password/` {current_password, new_password} → keeps this session and ends the others.
- `POST me/verify-email/resend/` → emails a new verification link.
"""

from django.contrib.auth import login, update_session_auth_hash
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.security_serializers import (
    AccountMessageSerializer,
    PasswordChangeRequestSerializer,
    PasswordForgotRequestSerializer,
    PasswordResetLinkInfoSerializer,
    PasswordResetLinkSerializer,
    PasswordResetRequestSerializer,
    VerificationResendSerializer,
    VerifyEmailRequestSerializer,
    VerifyEmailResultSerializer,
)
from apps.accounts.api.serializers import MeSerializer
from apps.accounts.errors import EmailUnavailable
from apps.accounts.passwords import (
    change_password,
    check_reset_link,
    mask_email,
    request_password_reset,
    reset_password,
)
from apps.accounts.throttles import AccountThrottle
from apps.accounts.verification import send_verification, verify_email
from apps.core.api.authentication import enforce_csrf


def _page_language(request) -> str | None:
    """The language on screen: what LocaleMiddleware picked from the SPA's `Accept-Language` (signed in, the
    profile language wins). None if the client sent no language (or there is no LocaleMiddleware): then the
    messages follow the user's profile language."""
    if not request.META.get("HTTP_ACCEPT_LANGUAGE"):
        return None
    return getattr(request, "LANGUAGE_CODE", None)


FORGOT_DONE = (
    "Si el correo corresponde a una cuenta de Housetel, te enviamos un enlace para restablecer la contraseña."
)
PASSWORD_CHANGED = "Contraseña actualizada. Cerramos la sesión en tus otros dispositivos."
EMAIL_FAILED = "No pudimos enviar el correo. Intenta de nuevo en unos minutos."


class _PublicAccountView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [AccountThrottle]


class PasswordForgotView(_PublicAccountView):
    """`POST password/forgot/` {email}: emails a reset link if the address has an active account."""

    throttle_scope = "password_forgot"

    @extend_schema(request=PasswordForgotRequestSerializer, responses=AccountMessageSerializer, auth=[])
    def post(self, request):
        enforce_csrf(request)
        serializer = PasswordForgotRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_password_reset(serializer.validated_data["email"])
        return Response({"detail": FORGOT_DONE})


class PasswordResetCheckView(_PublicAccountView):
    """`POST password/reset/check/` {uid, token}: whether the link still works (the page asks before the
    user types a new password). Changes nothing."""

    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetLinkSerializer, responses=PasswordResetLinkInfoSerializer, auth=[])
    def post(self, request):
        enforce_csrf(request)
        serializer = PasswordResetLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = check_reset_link(serializer.validated_data["uid"], serializer.validated_data["token"])
        return Response({"email": mask_email(user.email)})


class PasswordResetView(_PublicAccountView):
    """`POST password/reset/` {uid, token, new_password} → `Me`: the user is signed in on this browser and
    signed out everywhere else (the password hash is part of every session)."""

    throttle_scope = "password_reset"

    @extend_schema(request=PasswordResetRequestSerializer, responses=MeSerializer, auth=[])
    def post(self, request):
        enforce_csrf(request)
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = reset_password(
            data["uid"], data["token"], data["new_password"], language=_page_language(request)
        )
        login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(MeSerializer(user).data)


class VerifyEmailView(_PublicAccountView):
    """`POST verify-email/` {token}: confirms the address of the emailed link (no session needed)."""

    throttle_scope = "email_verify"

    @extend_schema(request=VerifyEmailRequestSerializer, responses=VerifyEmailResultSerializer, auth=[])
    def post(self, request):
        enforce_csrf(request)
        serializer = VerifyEmailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, verified_now = verify_email(serializer.validated_data["token"])
        return Response({"email": user.email, "email_verified": True, "already_verified": not verified_now})


class PasswordChangeView(APIView):
    """`POST me/password/` {current_password, new_password}: this session stays open, the others end."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountThrottle]
    throttle_scope = "password_change"

    @extend_schema(request=PasswordChangeRequestSerializer, responses=AccountMessageSerializer)
    def post(self, request):
        serializer = PasswordChangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = change_password(request.user, **serializer.validated_data, language=_page_language(request))
        update_session_auth_hash(request._request, user)
        return Response({"detail": PASSWORD_CHANGED})


class VerificationResendView(APIView):
    """`POST me/verify-email/resend/`: a new verification link to the signed-in user's address (nothing to
    send if it is already verified). 503 `email_unavailable` if the mail server fails."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountThrottle]
    throttle_scope = "email_verify_resend"

    @extend_schema(request=None, responses=VerificationResendSerializer)
    def post(self, request):
        user = request.user
        if user.email_verified_at is not None:
            return Response({"sent": False, "email": user.email, "email_verified": True})
        if not send_verification(user):
            raise EmailUnavailable(EMAIL_FAILED)
        return Response({"sent": True, "email": user.email, "email_verified": False})
