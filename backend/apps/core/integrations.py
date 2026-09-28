"""Integration framework: every external integration has a `real` and a `simulated` provider (spec §1.2).

Apps register providers in `apps/<app>/providers.py` with `register_provider(kind, mode, cls)`.
`get_provider()` does not check `setting.enabled`; callers decide what "disabled" means for them.

Real mode (plan P1, `apps.core.runtime`):
- With simulations off (production, or HOUSETEL_ALLOW_SIMULATIONS=0) a new integration starts in `real` mode,
  and disabled while its real provider still lacks required settings (Wompi keys, Channex API key…). It turns
  itself on when `set_secrets` completes its configuration. Email and the LLM keep their own defaults.
- `get_provider` refuses the simulated provider (IntegrationNotAvailable) unless simulations are on; email and
  the LLM are exempt (the simulated LLM is the assistant's legitimate offline fallback).
- `is_live(property, kind)`: enabled + real mode + nothing required missing.
- `is_operational(property, kind)`: live, or simulated where simulations are allowed (P-INT: what automatic
  flows check before calling a provider).
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
from apps.core.runtime import simulations_enabled

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
# Kinds whose simulated provider stays available with simulations off, and whose defaults never change.
SIMULATION_EXEMPT_KINDS = frozenset({"email", "llm"})
# Real providers configured through Django settings (environment) instead of CONFIG_FIELDS: those settings
# must be non-empty for the integration to count as configured (`missing_required`, `is_live`).
REQUIRED_DJANGO_SETTINGS: dict[tuple[str, str], tuple[str, ...]] = {
    ("saas_billing", "real"): (
        "WOMPI_PLATFORM_PUBLIC_KEY",
        "WOMPI_PLATFORM_PRIVATE_KEY",
        "WOMPI_PLATFORM_INTEGRITY_SECRET",
    ),
}


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


def mode_allowed(kind: str, mode: str) -> bool:
    """Whether `mode` may be used for `kind` in this installation (simulated only with simulations on)."""
    return mode != "simulated" or kind in SIMULATION_EXEMPT_KINDS or simulations_enabled()


def available_modes(kind: str) -> list[str]:
    """Modes with a registered provider that this installation allows (for pickers such as the control
    center: production offers only `real` for payments, channels, DIAN, TRA, SIRE and WhatsApp)."""
    registered = providers_for(kind)
    return [mode for mode in MODES if mode in registered and mode_allowed(kind, mode)]


def default_mode(kind: str) -> str:
    if kind == "email":
        return "real"
    if kind == "llm":
        return "real" if getattr(settings, "GEMINI_API_KEY", "") else "simulated"
    return "simulated" if simulations_enabled() else "real"


# ---- Configuration completeness ---------------------------------------------------------------------------


def _field_is_secret(field: dict) -> bool:
    return bool(field.get("secret")) or field.get("type") == "password"


def _effective_default(field: dict):
    """A required select without a default falls back to its first option (what the providers do at runtime
    and what the control center shows), so it never counts as missing."""
    if _field_is_secret(field):
        return None
    default = field.get("default")
    options = [option for option in field.get("options") or [] if isinstance(option, dict)]
    if default in (None, "") and field.get("type") == "select" and field.get("required") and options:
        return options[0].get("value")
    return default


def missing_fields(provider_cls, config: dict | None, secrets: dict | None) -> list[str]:
    """Names of the required CONFIG_FIELDS of `provider_cls` that have no value and no default, plus the
    required Django settings (environment) of platform-configured providers."""
    config, secrets = config or {}, secrets or {}
    missing = []
    for field in getattr(provider_cls, "CONFIG_FIELDS", None) or []:
        name = field.get("name")
        if not name or not field.get("required"):
            continue
        value = (secrets if _field_is_secret(field) else config).get(name)
        if value in (None, "") and _effective_default(field) in (None, ""):
            missing.append(name)
    key = (getattr(provider_cls, "kind", ""), getattr(provider_cls, "mode", ""))
    missing += [name for name in REQUIRED_DJANGO_SETTINGS.get(key, ()) if not getattr(settings, name, "")]
    return missing


def missing_required(setting, *, mode: str | None = None) -> list[str]:
    """Required settings still missing for the provider of `mode` (default: the setting's own mode). A mode
    without a registered provider reports `["provider"]`."""
    mode = mode or setting.mode
    cls = _PROVIDERS.get((setting.kind, mode))
    if cls is None:
        return ["provider"]
    return missing_fields(cls, setting.config, get_secrets(setting))


def default_enabled(kind: str, mode: str | None = None) -> bool:
    """`enabled` of a new setting of `kind` (in `mode`, default `default_mode(kind)`): True, except — with
    simulations off — a real integration that cannot work before the hotel fills in its credentials ("disabled
    until configured"). What a list of integrations should show for a kind without a stored row."""
    mode = mode or default_mode(kind)
    if kind in SIMULATION_EXEMPT_KINDS or mode != "real" or simulations_enabled():
        return True
    cls = _PROVIDERS.get((kind, mode))
    return cls is not None and not missing_fields(cls, {}, {})


def get_setting(property, kind: str) -> IntegrationSetting:
    """IntegrationSetting of (property, kind); created with `default_mode(kind)` if missing (enabled, or —
    real mode with simulations off — disabled until its required settings are filled in)."""
    if kind not in KINDS:
        raise ValueError(f"Tipo de integración desconocido: {kind}")
    from apps.core.models import IntegrationSetting

    mode = default_mode(kind)
    setting, _ = IntegrationSetting.objects.get_or_create(
        property=property, kind=kind, defaults={"mode": mode, "enabled": default_enabled(kind, mode)}
    )
    return setting


def is_live(property, kind: str) -> bool:
    """True if the integration is enabled, in real mode and configured (no required setting missing). Reads
    the stored setting without creating it (a missing row is judged by its defaults)."""
    if kind not in KINDS:
        raise ValueError(f"Tipo de integración desconocido: {kind}")
    from apps.core.models import IntegrationSetting

    setting = IntegrationSetting.objects.filter(property=property, kind=kind).first()
    if setting is None:
        mode = default_mode(kind)
        if mode != "real" or not default_enabled(kind, mode):
            return False
        cls = _PROVIDERS.get((kind, mode))
        return cls is not None and not missing_fields(cls, {}, {})
    return setting.enabled and setting.mode == "real" and not missing_required(setting)


def is_operational(property, kind: str) -> bool:
    """Whether the provider of `kind` can do its job here right now: the simulated one where simulations are
    allowed, or the real one when it is live (`is_live`: enabled and configured). Automatic flows (the invoice
    at check-out, the TRA at check-in and their retries) use it to leave the work pending ("configure the
    integration") instead of sending it to a provider that cannot take it — production starts every real
    integration disabled until its credentials are in (P-INT). Reads without creating the row."""
    if kind not in KINDS:
        raise ValueError(f"Tipo de integración desconocido: {kind}")
    from apps.core.models import IntegrationSetting

    setting = IntegrationSetting.objects.filter(property=property, kind=kind).first()
    mode = setting.mode if setting is not None else default_mode(kind)
    if mode == "simulated":
        return mode_allowed(kind, "simulated")
    return is_live(property, kind)


def get_provider(property, kind: str) -> BaseProvider:
    setting = get_setting(property, kind)
    if not mode_allowed(kind, setting.mode):
        raise IntegrationNotAvailable(
            f"La integración «{kind}» está en modo simulado y las simulaciones están desactivadas en este "
            "entorno. Configura su modo real en Configuración → Integraciones.",
            kind=kind,
            mode=setting.mode,
        )
    cls = _PROVIDERS.get((kind, setting.mode))
    if cls is None:
        cls = _PROVIDERS.get((kind, "simulated")) if mode_allowed(kind, "simulated") else None
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


# ---- Secrets --------------------------------------------------------------------------------------------


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
    """Merge `data` into the stored secrets (None removes a key, "" keeps it) and save them encrypted.

    With simulations off, a disabled real-mode integration whose configuration becomes complete with these
    secrets is switched on ("disabled until configured"); one that was already complete keeps its state, so an
    integration someone turned off stays off when its keys are rotated.
    """
    current = get_secrets(setting)
    completes = _completes_configuration(setting, current, data)
    for key, value in data.items():
        if value is None:
            current.pop(key, None)
        elif value != "":
            current[key] = value
    setting.secrets_encrypted = _fernet().encrypt(json.dumps(current).encode()).decode() if current else ""
    fields = ["secrets_encrypted", "updated_at"]
    provider_cls = _PROVIDERS.get((setting.kind, setting.mode))
    if completes and not missing_fields(provider_cls, setting.config, current):
        setting.enabled = True
        fields.append("enabled")
        logger.info("Integration %s (%s) enabled: its configuration is complete", setting.kind, setting.pk)
    if setting.pk and not setting._state.adding:
        setting.save(update_fields=fields)
    else:
        setting.save()


def _completes_configuration(setting, current: dict, data: dict) -> bool:
    """True when these secrets may finish the setup of a disabled real integration (simulations off)."""
    if simulations_enabled() or setting.enabled or setting.mode != "real":
        return False
    if setting.kind in SIMULATION_EXEMPT_KINDS or not data:
        return False
    cls = _PROVIDERS.get((setting.kind, setting.mode))
    return cls is not None and bool(missing_fields(cls, setting.config, current))


def autodiscover() -> None:
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        try:
            import_module(f"{cfg.name}.providers")
        except ModuleNotFoundError as exc:
            if exc.name != f"{cfg.name}.providers":
                raise
