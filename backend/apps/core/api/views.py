import logging
import time

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.api.serializers import (
    OrganizationRef,
    PropertyRef,
    RoleRef,
    organization_payload,
    property_payload,
    role_payload,
)
from apps.core.runtime import public_config
from apps.core.tenancy import PropertyScopedAPIView

logger = logging.getLogger("housetel.health")


class HealthView(APIView):
    """`GET /api/v1/public/core/health/` → `{"status": "ok"}` (public; no session, no database): liveness."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses=inline_serializer("Health", {"status": serializers.CharField()}), auth=[])
    def get(self, request):
        return Response({"status": "ok"})


def _timed(check) -> dict:
    started = time.perf_counter()
    try:
        check()
    except Exception:  # noqa: BLE001 - any failure means "not ready"; the details go to the log only
        logger.exception("Readiness check failed: %s", check.__name__)
        return {"ok": False, "ms": round((time.perf_counter() - started) * 1000, 1)}
    return {"ok": True, "ms": round((time.perf_counter() - started) * 1000, 1)}


def _database() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()


def _redis() -> None:
    import redis

    client = redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
    try:
        if not client.ping():
            raise ConnectionError("Redis did not answer PING")
    finally:
        client.close()


class ReadyView(APIView):
    """`GET /api/v1/public/core/health/ready/` → 200 `{"status": "ok", "checks": {"database": {ok, ms},
    "redis": {ok, ms}}}` when PostgreSQL and Redis answer; 503 with `"status": "error"` otherwise (for load
    balancers, uptime monitors and container healthchecks). Public: it never reveals why a check failed."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: inline_serializer(
                "Readiness",
                {
                    "status": serializers.CharField(),
                    "checks": serializers.DictField(child=serializers.DictField()),
                },
            ),
            503: inline_serializer(
                "ReadinessFailed",
                {
                    "status": serializers.CharField(),
                    "checks": serializers.DictField(child=serializers.DictField()),
                },
            ),
        },
        auth=[],
    )
    def get(self, request):
        checks = {"database": _timed(_database), "redis": _timed(_redis)}
        ok = all(check["ok"] for check in checks.values())
        response = Response({"status": "ok" if ok else "error", "checks": checks}, status=200 if ok else 503)
        response["Cache-Control"] = "no-store"
        return response


class RuntimeConfigView(APIView):
    """`GET /api/v1/public/core/config/` → what the SPA needs to know about this installation
    (`useRuntimeConfig()` in the frontend):

    `{"environment": "development" | "production", "simulations_enabled": bool, "public_base_url": str,
    "support": {"whatsapp": str, "email": str, "docs_url": str}}`.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        responses=inline_serializer(
            "RuntimeConfig",
            {
                # A plain string (not an enum): "environment" choice fields of other apps would collide.
                "environment": serializers.CharField(help_text="development | production"),
                "simulations_enabled": serializers.BooleanField(),
                "public_base_url": serializers.CharField(),
                "support": inline_serializer(
                    "SupportContact",
                    {
                        "whatsapp": serializers.CharField(),
                        "email": serializers.CharField(),
                        "docs_url": serializers.CharField(),
                    },
                ),
            },
        ),
        auth=[],
    )
    def get(self, request):
        response = Response(public_config())
        # Read once per page load by the SPA; no-cache so a change of simulations or support channels shows at
        # once.
        response["Cache-Control"] = "no-cache"
        return response


class PropertyContextSerializer(serializers.Serializer):
    """Documentation-only shape of `GET /api/v1/core/context/`."""

    property = PropertyRef()
    organization = OrganizationRef()
    role = RoleRef()
    permissions = serializers.ListField(child=serializers.CharField())


class PropertyContextView(PropertyScopedAPIView):
    """`GET /api/v1/core/context/` (header `X-Property-Id`) → the context the request runs in.

    `{property, organization, role, permissions}` for the active property, resolved by the same tenancy
    rules as every staff endpoint (400 without the header, 404 for a property the user cannot access,
    402 when the organization is suspended). Any member of the property may read it; `permissions` are the
    role's codes/patterns as stored, like in `Me`.
    """

    required_permissions: dict = {}

    @extend_schema(responses=PropertyContextSerializer)
    def get(self, request):
        role = request.membership.role
        return Response(
            {
                "property": property_payload(request.property),
                "organization": organization_payload(request.organization),
                "role": role_payload(role),
                "permissions": list(role.permissions or []),
            }
        )
