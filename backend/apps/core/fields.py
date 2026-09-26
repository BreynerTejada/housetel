"""Field helpers shared by every app (all return plain Django fields, so migrations stay decoupled)."""

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.core.i18n import i18n_field
from apps.core.money import money_field

__all__ = ["i18n_field", "json_field", "money_field"]


def json_field(default=dict, **kwargs) -> models.JSONField:
    """JSONField that accepts Decimal/date/UUID values (DjangoJSONEncoder); optional by default."""
    kwargs.setdefault("blank", True)
    kwargs.setdefault("encoder", DjangoJSONEncoder)
    return models.JSONField(default=default, **kwargs)
