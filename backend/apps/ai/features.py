"""AI features of a property (`AISettings`): copilot, chatbot and draft replies can be switched off."""

from apps.ai.models import AISettings
from apps.core.errors import DomainError

FEATURE_LABELS = {
    "copilot_enabled": "El copiloto",
    "chatbot_enabled": "El chatbot",
    "draft_replies_enabled": "Los borradores con IA",
}


class FeatureDisabled(DomainError):
    code = "feature_disabled"
    status_code = 409


def ai_settings(prop) -> AISettings:
    found = AISettings.objects.filter(property=prop).first()
    if found is not None:
        return found
    settings_row, _ = AISettings.objects.get_or_create(property=prop)
    return settings_row


def require_feature(prop, field: str) -> AISettings:
    row = ai_settings(prop)
    if not getattr(row, field):
        raise FeatureDisabled(f"{FEATURE_LABELS[field]} está desactivado en este hotel", feature=field)
    return row
