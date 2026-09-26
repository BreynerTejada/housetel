"""Integration framework: every external integration has a `real` and a `simulated` provider (spec §1.2).

Apps register providers in `apps/<app>/providers.py` with `register_provider(kind, mode, cls)`.
`get_provider()` does not check `setting.enabled`; callers decide what "disabled" means for them.
"""

from __future__ import annotations

import json
import logging
from importlib import import_module
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet, InvalidToken
from django.apps import apps as django_apps
from django.conf import settings

from apps.core.errors import DomainError

if TYPE_CHECKING:  # the models module is imported lazily (this module loads from CoreConfig.ready)
    from apps.core.models import IntegrationSetting

logger = logging.getLogger("housetel.integrations")

KINDS = [
    "payments",
    "channel_ical",
    "channel_channex",
    "einvoice",
    "sire",
    "tra",
    "email",
    "whatsapp",
    "llm",
    "saas_billing",
]
MODES = ("real", "simulated")


class IntegrationNotAvailable(DomainError):
    code = "integration_not_available"


class BaseProvider:
    kind: str = ""
    mode: str = ""  # "real" | "simulated"
    label: str = ""
    CONFIG_FIELDS: list[dict] = []
    # each field: {"name", "label_es", "label_en", "type": "text|password|url|select|boolean|number",
    #              "secret": bool, "required": bool, "options": [{"value", "label_es", "label_en"}],
    #              "help_es": "", "help_en": ""}

    def __init__(self, setting):
        self.setting = setting
        self.config = setting.config or {}
        self.secrets = get_secrets(setting)

    def test_connection(self) -> tuple[bool, str]:
        return True, "OK"


_PROVIDERS: dict[tuple[str, str], type[BaseProvider]] = {}


def register_provider(kind: str, mode: str, cls: type[BaseProvider]) -> None:
    if kind not in KINDS:
        raise ValueError(f"Tipo de integración desconocido: {kind}")
    if mode not in MODES:
        raise ValueError(f"Modo desconocido: {mode}")
    _PROVIDERS[(kind, mode)] = cls


def providers_for(kind: str) -> dict[str, type[BaseProvider]]:
    return {mode: cls for (registered_kind, mode), cls in _PROVIDERS.items() if registered_kind == kind}


def default_mode(kind: str) -> str:
    if kind == "email":
        return "real"
    if kind == "llm":
        return "real" if getattr(settings, "GEMINI_API_KEY", "") else "simulated"
    return "simulated"


def get_setting(property, kind: str) -> IntegrationSetting:
    """IntegrationSetting of (property, kind); created enabled with `default_mode(kind)` if missing."""
    if kind not in KINDS:
        raise ValueError(f"Tipo de integración desconocido: {kind}")
    from apps.core.models import IntegrationSetting

    setting, _ = IntegrationSetting.objects.get_or_create(
        property=property, kind=kind, defaults={"mode": default_mode(kind), "enabled": True}
    )
    return setting


def get_provider(property, kind: str) -> BaseProvider:
    setting = get_setting(property, kind)
    cls = _PROVIDERS.get((kind, setting.mode))
    if cls is None:
        cls = _PROVIDERS.get((kind, "simulated"))
        if cls is None:
            raise IntegrationNotAvailable(f"No hay un proveedor disponible para la integración «{kind}»")
        from apps.core.alerts import raise_alert

        raise_alert(
            property=property,
            kind="integration_fallback",
            severity="warning",
            title=f"La integración «{kind}» está funcionando en modo simulado",
            message=f"No hay proveedor «{setting.mode}» para «{kind}»; se usa el simulado.",
            link="/app/settings/integrations",
            dedupe_key=f"integration:{kind}:fallback",
            data={"kind": kind, "mode": setting.mode},
            source="integration",
        )
    return cls(setting)


def _fernet() -> Fernet:
    return Fernet(settings.FERNET_KEY)


def get_secrets(setting) -> dict:
    if not setting.secrets_encrypted:
        return {}
    try:
        return json.loads(_fernet().decrypt(setting.secrets_encrypted.encode()))
    except (InvalidToken, ValueError):
        logger.error("Could not decrypt the secrets of integration %s (%s)", setting.kind, setting.pk)
        return {}


def set_secrets(setting, data: dict) -> None:
    """Merge `data` into the stored secrets (None removes a key, "" keeps it) and save them encrypted."""
    current = get_secrets(setting)
    for key, value in data.items():
        if value is None:
            current.pop(key, None)
        elif value != "":
            current[key] = value
    setting.secrets_encrypted = _fernet().encrypt(json.dumps(current).encode()).decode() if current else ""
    if setting.pk and not setting._state.adding:
        setting.save(update_fields=["secrets_encrypted", "updated_at"])
    else:
        setting.save()


def autodiscover() -> None:
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        try:
            import_module(f"{cfg.name}.providers")
        except ModuleNotFoundError as exc:
            if exc.name != f"{cfg.name}.providers":
                raise
