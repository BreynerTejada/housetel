"""OpenAPI (drf-spectacular) helpers: session-cookie auth scheme and the `X-Property-Id` header on every
property-scoped view (set as `schema = PropertyScopedAutoSchema()` on
apps.core.tenancy.PropertyScopedMixin)."""

from drf_spectacular.authentication import SessionScheme
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter

PROPERTY_HEADER_PARAMETER = OpenApiParameter(
    name="X-Property-Id",
    type=OpenApiTypes.UUID,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Propiedad activa (UUID). Obligatorio en toda la API de staff.",
)


class HousetelSessionScheme(SessionScheme):
    """Documents apps.core.api.authentication.SessionAuthentication as the session cookie scheme."""

    target_class = "apps.core.api.authentication.SessionAuthentication"
    name = "cookieAuth"


class PropertyScopedAutoSchema(AutoSchema):
    def get_override_parameters(self):
        return [*super().get_override_parameters(), PROPERTY_HEADER_PARAMETER]
