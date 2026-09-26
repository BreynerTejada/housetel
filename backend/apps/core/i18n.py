"""Translatable fields are JSON dicts: {"es": "...", "en": "..."}."""

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


def i18n_field(**kwargs) -> models.JSONField:
    kwargs.setdefault("default", dict)
    kwargs.setdefault("blank", True)
    kwargs.setdefault("encoder", DjangoJSONEncoder)
    return models.JSONField(**kwargs)


def t(value, lang: str = "es") -> str:
    """Pick `lang`, then Spanish, then the first non-empty value. Plain strings pass through."""
    if value is None:
        return ""
    if not isinstance(value, dict):
        return str(value)
    for key in (lang, "es"):
        if value.get(key):
            return value[key]
    return next((v for v in value.values() if v), "")
