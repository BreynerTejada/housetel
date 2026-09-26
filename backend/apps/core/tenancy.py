"""Property context for staff APIs (spec §3).

The SPA sends `X-Property-Id: <uuid>` on every staff request. `PropertyAccess` validates that the user has an
active membership giving access to that property, exposes `request.property`, `request.organization` and
`request.membership`, blocks suspended organizations (402) unless the view sets `allow_suspended = True`, and
checks the view's required permission. A `property_id` coming in the body is never trusted.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.views import APIView

from apps.core.api.schema import PropertyScopedAutoSchema
from apps.core.errors import PaymentRequiredError
from apps.core.permissions import codes_match

PROPERTY_HEADER = "HTTP_X_PROPERTY_ID"


def resolve_property(request):
    """Return `(property, membership)` for the `X-Property-Id` header or raise 400/404."""
    from apps.accounts.models import Membership
    from apps.core.models import Property

    raw = request.META.get(PROPERTY_HEADER)
    if not raw:
        raise ValidationError({"detail": "Falta el encabezado X-Property-Id", "code": "property_required"})
    try:
        prop = Property.objects.select_related("organization").get(pk=raw)
    except (Property.DoesNotExist, ValueError, DjangoValidationError):
        raise NotFound("Propiedad no encontrada") from None
    membership = (
        Membership.objects.select_related("role")
        .filter(user=request.user, organization=prop.organization, is_active=True)
        .first()
    )
    if membership is None or not (
        membership.all_properties or membership.properties.filter(pk=prop.pk).exists()
    ):
        raise NotFound("Propiedad no encontrada")
    return prop, membership


class PropertyAccess(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        prop, membership = resolve_property(request)
        request.property = prop
        request.organization = prop.organization
        request.membership = membership
        if prop.organization.status == "suspended" and not getattr(view, "allow_suspended", False):
            raise PaymentRequiredError("La organización está suspendida por falta de pago")
        code = view.get_required_permission() if hasattr(view, "get_required_permission") else None
        if code and not codes_match(membership.role.permissions, code):
            raise PermissionDenied(
                {
                    "detail": "No tienes permiso para esta acción",
                    "code": "permission_denied",
                    "permission": code,
                }
            )
        return True


class PropertyScopedMixin:
    """required_permissions: {"list": "x.view", "create": "x.manage", "*": "x.view"} (ViewSet: per action;
    APIView: per lowercase HTTP method: {"get": ..., "post": ...})."""

    property_field = "property"
    required_permissions: dict = {}
    permission_classes = [permissions.IsAuthenticated, PropertyAccess]
    schema = PropertyScopedAutoSchema()  # documents the X-Property-Id header in /api/docs/

    def get_required_permission(self):
        key = getattr(self, "action", None) or self.request.method.lower()
        return self.required_permissions.get(key) or self.required_permissions.get("*")

    def get_queryset(self):
        return super().get_queryset().filter(**{self.property_field: self.request.property})

    def perform_create(self, serializer):
        if self.property_field == "property":
            serializer.save(property=self.request.property)
        else:
            serializer.save()


class OrganizationScopedMixin(PropertyScopedMixin):
    """Same access rules (the header still selects the property), but rows are scoped by organization."""

    property_field = "organization"

    def get_queryset(self):
        return super(PropertyScopedMixin, self).get_queryset().filter(organization=self.request.organization)

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)


class PropertyScopedViewSet(PropertyScopedMixin, viewsets.ModelViewSet):
    pass


class PropertyScopedAPIView(PropertyScopedMixin, APIView):
    def get_queryset(self):  # APIView has no base queryset
        raise NotImplementedError
