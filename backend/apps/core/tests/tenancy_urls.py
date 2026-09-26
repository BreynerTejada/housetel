"""Test-only URLconf exercising apps.core.tenancy (used with @pytest.mark.urls)."""

from django.urls import include, path
from rest_framework import serializers, viewsets
from rest_framework.response import Response
from rest_framework.routers import SimpleRouter

from apps.accounts.models import Role
from apps.core.models import Alert
from apps.core.tenancy import OrganizationScopedMixin, PropertyScopedAPIView, PropertyScopedViewSet


class PingView(PropertyScopedAPIView):
    required_permissions = {"get": "bookings.view", "post": "finance.refund"}

    def get(self, request):
        return Response(
            {
                "property": str(request.property.pk),
                "organization": str(request.organization.pk),
                "role": request.membership.role.code,
            }
        )

    def post(self, request):
        return Response({"refunded": True})


class BillingView(PropertyScopedAPIView):
    allow_suspended = True
    required_permissions = {"*": "saas.billing_view"}

    def get(self, request):
        return Response({"ok": True})


class AlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = Alert
        fields = ["id", "property", "kind", "title", "dedupe_key"]
        read_only_fields = ["property"]


class AlertViewSet(PropertyScopedViewSet):
    queryset = Alert.objects.all()
    serializer_class = AlertSerializer
    required_permissions = {"create": "control.alerts", "*": "control.alerts"}


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "code"]


class RoleViewSet(OrganizationScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    pagination_class = None
    required_permissions = {"*": "accounts.roles_manage"}


router = SimpleRouter()
router.register("alerts", AlertViewSet, basename="alert")
router.register("roles", RoleViewSet, basename="role")

urlpatterns = [
    path("t/ping/", PingView.as_view()),
    path("t/billing/", BillingView.as_view()),
    path("t/", include(router.urls)),
]
