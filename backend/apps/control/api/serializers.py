"""Request bodies of the control center API (responses are plain dicts built by `apps.control.services`)."""

from rest_framework import serializers


class IntegrationUpdateSerializer(serializers.Serializer):
    mode = serializers.CharField(required=False)
    enabled = serializers.BooleanField(required=False)
    config = serializers.DictField(required=False)
    secrets = serializers.DictField(
        required=False, child=serializers.CharField(allow_blank=True, allow_null=True)
    )


class AutomationUpdateSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    params = serializers.DictField(required=False, allow_null=True)


class AuditUndoSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(required=False, default=False)


class AlertIdsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=200)
