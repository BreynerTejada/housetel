"""Serializers of the front desk API. Shapes are documented in docs/integration-notes/C1-frontdesk.md."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.frontdesk.models import NightAuditReport


class FrontdeskUserRefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    email = serializers.EmailField()


class NightAuditRunSerializer(serializers.Serializer):
    """The business date the user saw in the preview: the audit closes it only if it is still the current one
    (a double click or a second tab never closes two days)."""

    business_date = serializers.DateField()


class NightAuditReportSerializer(serializers.ModelSerializer):
    # plain strings: a `status` enum would collide with the other apps' `status` enums in the OpenAPI schema
    status = serializers.CharField(read_only=True)
    triggered_by = serializers.SerializerMethodField()
    run_id = serializers.UUIDField(read_only=True, allow_null=True)

    class Meta:
        model = NightAuditReport
        fields = [
            "id",
            "business_date",
            "status",
            "started_at",
            "finished_at",
            "triggered_by",
            "run_id",
            "summary",
            "created_at",
        ]

    @extend_schema_field(FrontdeskUserRefSerializer(allow_null=True))
    def get_triggered_by(self, obj):
        user = obj.triggered_by
        return (
            None if user is None else {"id": str(user.pk), "full_name": user.full_name, "email": user.email}
        )
