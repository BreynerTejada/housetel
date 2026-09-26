from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.api.serializers import LoginSerializer, MeSerializer, MeUpdateSerializer
from apps.core.api.authentication import enforce_csrf
from apps.core.errors import DomainError


class InvalidCredentials(DomainError):
    code = "invalid_credentials"
    status_code = 400


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CsrfView(APIView):
    """`GET auth/csrf/` → sets the `csrftoken` cookie (readable by JS) and returns it."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses=inline_serializer("CsrfToken", {"csrf_token": serializers.CharField()}), auth=[])
    def get(self, request):
        return Response({"csrf_token": get_token(request._request)})


class LoginView(APIView):
    """`POST auth/login/` `{email, password}` → `Me` + session cookie. CSRF is required, like any write."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=LoginSerializer, responses={200: MeSerializer}, auth=[])
    def post(self, request):
        enforce_csrf(request)
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            request._request,
            username=serializer.validated_data["email"].strip(),
            password=serializer.validated_data["password"],
        )
        if user is None:
            raise InvalidCredentials("Email o contraseña incorrectos")
        login(request._request, user)
        return Response(MeSerializer(user).data)


class LogoutView(APIView):
    """`POST auth/logout/` → 204. Idempotent; a logged-in session must send the CSRF token."""

    permission_classes = [AllowAny]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """`GET/PATCH me/` (PATCH: full_name, language, phone)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        return Response(MeSerializer(request.user).data)

    @extend_schema(request=MeUpdateSerializer, responses=MeSerializer)
    def patch(self, request):
        serializer = MeUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(MeSerializer(request.user).data)
