from rest_framework import serializers

from apps.imports.models import ImportJob


class ImportUploadSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=ImportJob.Kind.choices)
    preset = serializers.ChoiceField(choices=ImportJob.Preset.choices, default=ImportJob.Preset.GENERIC)
    file = serializers.FileField()
    source_label = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")
    sheet = serializers.CharField(max_length=100, required=False, allow_blank=True, default="")


class ImportConfigureSerializer(serializers.Serializer):
    mapping = serializers.DictField(child=serializers.CharField(allow_blank=True), required=False)
    value_map = serializers.DictField(
        child=serializers.DictField(child=serializers.CharField(allow_blank=True, allow_null=True)),
        required=False,
    )
    options = serializers.DictField(required=False)
    source_label = serializers.CharField(max_length=100, required=False, allow_blank=True)


class ImportConfirmSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(required=False, default=False)
