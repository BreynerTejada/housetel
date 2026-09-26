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
from apps.core.tenancy import PropertyScopedAPIView


class HealthView(APIView):
    """`GET /api/v1/public/core/health/` → `{"status": "ok"}` (public; no session, no database)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(responses=inline_serializer("Health", {"status": serializers.CharField()}), auth=[])
    def get(self, request):
        return Response({"status": "ok"})


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
