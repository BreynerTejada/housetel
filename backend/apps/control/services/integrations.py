"""Integrations of a property (spec §1.2 + plan C12): mode real/simulated, non-secret config, write-only
secrets and connection tests, built on `apps.core.integrations`.

- The form of each provider comes from its `CONFIG_FIELDS`; a field with `secret: True` (or type `password`)
  is write-only: it is stored encrypted with `set_secrets` and the API only ever says whether it is set
  (`secrets_configured`).
- `saas_billing` is a platform integration (property null, super-admin): it is not listed per property.
- Listing never creates rows; an integration without a row shows its defaults (`default_mode`,
  `default_enabled`: with simulations off a real integration that needs credentials is off until configured).
- `available_modes` are the modes this installation allows (`core.integrations.available_modes`: production
  offers only `real`, except email and the LLM); `providers` still lists every registered provider. A PATCH to
  a mode that is not allowed here is a 400 (P-INT).
"""

import logging
from urllib.parse import urlparse

from django.db import transaction
from django.utils import timezone

from apps.control.services.scrub import is_secret_key, redact_text, scrub
from apps.core import audit, integrations
from apps.core.errors import DomainError, NotFoundError
from apps.core.models import IntegrationSetting

logger = logging.getLogger("housetel.control")

PLATFORM_KINDS = frozenset({"saas_billing"})
FIELD_TYPES = {"text", "password", "url", "select", "boolean", "number", "textarea", "email"}
STATUS_LABELS = {"ok": "correcta", "error": "con error", "unknown": "sin probar"}


class IntegrationNotFound(NotFoundError):
    code = "integration_not_found"


def property_kinds() -> list[str]:
    return [kind for kind in integrations.KINDS if kind not in PLATFORM_KINDS]


def kind_label(kind: str) -> str:
    return str(IntegrationSetting.Kind(kind).label) if kind in IntegrationSetting.Kind.values else kind


def check_kind(kind: str) -> str:
    if kind not in property_kinds():
        raise IntegrationNotFound(f"Integración desconocida: {kind}")
    return kind


def _clean_field(raw: dict) -> dict:
    field_type = raw.get("type") or "text"
    secret = bool(raw.get("secret")) or field_type == "password"
    options = [
        {
            "value": option.get("value"),
            "label_es": option.get("label_es") or str(option.get("value")),
            "label_en": option.get("label_en") or option.get("label_es") or str(option.get("value")),
        }
        for option in raw.get("options") or []
        if isinstance(option, dict)
    ]
    default = None if secret else raw.get("default")
    if default in (None, "") and field_type == "select" and raw.get("required") and options:
        # A required select always has a value: the providers fall back to their first option
        # (sandbox / staging / gemini), so that is its effective default (and it is not "missing").
        default = options[0]["value"]
    return {
        "name": str(raw.get("name", "")),
        "label_es": raw.get("label_es") or raw.get("name", ""),
        "label_en": raw.get("label_en") or raw.get("label_es") or raw.get("name", ""),
        "type": field_type if field_type in FIELD_TYPES else "text",
        "secret": secret,
        "required": bool(raw.get("required")),
        "options": options,
        "help_es": raw.get("help_es") or "",
        "help_en": raw.get("help_en") or raw.get("help_es") or "",
        "default": default,
    }


def provider_fields(cls) -> list[dict]:
    return [_clean_field(field) for field in getattr(cls, "CONFIG_FIELDS", None) or [] if field.get("name")]


def all_fields(kind: str) -> dict[str, dict]:
    """Every field declared by any provider of `kind`, by name (the first declaration wins)."""
    fields: dict[str, dict] = {}
    for cls in integrations.providers_for(kind).values():
        for field in provider_fields(cls):
            fields.setdefault(field["name"], field)
    return fields


def secret_names(kind: str) -> set[str]:
    return {name for name, field in all_fields(kind).items() if field["secret"]}


def _missing_required(cls, config: dict, secrets: dict) -> list[str]:
    missing = []
    for field in provider_fields(cls):
        source = secrets if field["secret"] else config
        value = source.get(field["name"])
        if field["required"] and value in (None, "") and field["default"] in (None, ""):
            missing.append(field["name"])
    return missing


def serialize(kind: str, setting: IntegrationSetting | None) -> dict:
    providers = integrations.providers_for(kind)
    secrets_hidden = secret_names(kind)
    mode = setting.mode if setting else integrations.default_mode(kind)
    stored_config = (setting.config or {}) if setting else {}
    secrets = integrations.get_secrets(setting) if setting else {}
    config = {
        key: value
        for key, value in stored_config.items()
        if key not in secrets_hidden and not is_secret_key(key)
    }
    current_cls = providers.get(mode)
    return {
        "kind": kind,
        "label": kind_label(kind),
        "configured": setting is not None,
        "mode": mode,
        "default_mode": integrations.default_mode(kind),
        "enabled": setting.enabled if setting else integrations.default_enabled(kind),
        "status": setting.status if setting else IntegrationSetting.Status.UNKNOWN,
        "status_message": redact_text(setting.status_message, secrets) if setting else "",
        "last_checked_at": setting.last_checked_at if setting else None,
        "updated_at": setting.updated_at if setting else None,
        "config": scrub(config),
        "secrets_configured": {name: bool(secrets.get(name)) for name in sorted(secrets_hidden)},
        "missing_required": _missing_required(current_cls, config, secrets) if current_cls else [],
        "available_modes": integrations.available_modes(kind),
        "providers": {
            provider_mode: {
                "label": getattr(cls, "label", "") or provider_mode,
                "label_en": getattr(cls, "label_en", "") or "",
                "config_fields": provider_fields(cls),
            }
            for provider_mode, cls in sorted(providers.items(), key=lambda item: item[0] != "real")
        },
    }


def list_for(property) -> list[dict]:
    rows = {s.kind: s for s in IntegrationSetting.objects.filter(property=property)}
    return [serialize(kind, rows.get(kind)) for kind in property_kinds()]


def detail(property, kind: str) -> dict:
    check_kind(kind)
    return serialize(kind, IntegrationSetting.objects.filter(property=property, kind=kind).first())


# ---- Writes ----------------------------------------------------------------------------------------------


def _coerce(field: dict, value):
    """Normalized value for a non-secret config field, or raise ValueError with the reason."""
    kind = field["type"]
    if value is None:
        return None
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false", "1", "0"}:
            return value.lower() in {"true", "1"}
        raise ValueError("Debe ser verdadero o falso")
    if kind == "number":
        if isinstance(value, bool):
            raise ValueError("Debe ser un número")
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("Debe ser un número") from None
        return int(number) if number.is_integer() else number
    if not isinstance(value, str | int | float) or isinstance(value, bool):
        raise ValueError("Debe ser un texto")
    text = str(value).strip()
    if text == "":
        return None
    if kind == "select" and field["options"]:
        allowed = {str(option["value"]) for option in field["options"]}
        if text not in allowed:
            raise ValueError("Opción inválida")
    if kind == "url":
        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Escribe una URL que empiece por http:// o https://")
    return text[:2000]


def _config_changes(fields: dict[str, dict], incoming: dict, errors: dict) -> dict:
    """Validated config updates: {name: value | None (remove)}."""
    updates = {}
    for name, value in incoming.items():
        field = fields.get(name)
        if field is None:
            errors[f"config.{name}"] = ["Campo desconocido para esta integración"]
            continue
        if field["secret"]:
            errors[f"config.{name}"] = ["Este campo es secreto: envíalo en «secrets»"]
            continue
        try:
            updates[name] = _coerce(field, value)
        except ValueError as exc:
            errors[f"config.{name}"] = [str(exc)]
    return updates


def _secret_changes(fields: dict[str, dict], incoming: dict, errors: dict) -> dict:
    """Validated secret updates for `set_secrets`: {name: str (set) | None (remove)}; "" keeps."""
    updates = {}
    for name, value in incoming.items():
        field = fields.get(name)
        if field is None or not field["secret"]:
            errors[f"secrets.{name}"] = ["No es un campo secreto de esta integración"]
            continue
        if value is not None and not isinstance(value, str):
            errors[f"secrets.{name}"] = ["Debe ser un texto"]
            continue
        if value == "":
            continue
        updates[name] = value.strip() if isinstance(value, str) else None
    return updates


def update(property, kind: str, data: dict, *, actor) -> dict:
    """PATCH `{mode?, enabled?, config?, secrets?}`. Secrets are write-only and never echoed."""
    check_kind(kind)
    fields = all_fields(kind)
    errors: dict[str, list[str]] = {}
    providers = integrations.providers_for(kind)

    mode = data.get("mode")
    if mode is not None and mode not in providers:
        errors["mode"] = [f"No hay un proveedor «{mode}» para esta integración"]
    elif mode is not None and not integrations.mode_allowed(kind, mode):
        errors["mode"] = ["El modo simulado no está disponible en este entorno: configura el modo real"]
    config_updates = _config_changes(fields, data.get("config") or {}, errors)
    secret_updates = _secret_changes(fields, data.get("secrets") or {}, errors)
    if errors:
        first = next(iter(errors.values()))[0]
        raise DomainError(first, code="validation_error", fields=errors)

    with transaction.atomic():
        integrations.get_setting(property, kind)  # creates the row with the defaults if missing
        setting = IntegrationSetting.objects.select_for_update().get(property=property, kind=kind)
        before_secrets = integrations.get_secrets(setting)
        changes: dict[str, list] = {}

        if mode is not None and mode != setting.mode:
            changes["mode"] = [setting.mode, mode]
            setting.mode = mode
        enabled = data.get("enabled")
        if enabled is not None and bool(enabled) != setting.enabled:
            changes["enabled"] = [setting.enabled, bool(enabled)]
            setting.enabled = bool(enabled)

        config = dict(setting.config or {})
        for name, value in config_updates.items():
            old = config.get(name)
            if value is None:
                config.pop(name, None)
            else:
                config[name] = value
            if old != config.get(name):
                changes[f"config.{name}"] = [old, config.get(name)]
        setting.config = config

        credentials_changed = False
        for name, value in secret_updates.items():
            had = bool(before_secrets.get(name))
            if value is None and not had:
                continue
            if value is not None and before_secrets.get(name) == value:
                continue
            credentials_changed = True
            changes[f"secrets.{name}"] = [
                "configurado" if had else None,
                "eliminado" if value is None else "actualizado",
            ]

        if changes:
            if any(key != "enabled" for key in changes):
                setting.status = IntegrationSetting.Status.UNKNOWN
                setting.status_message = ""
            setting.save()
            if credentials_changed:
                integrations.set_secrets(setting, secret_updates)
            audit.record(
                action="control.integration_updated",
                target=setting,
                summary=_update_summary(kind, changes),
                actor=actor,
                property=property,
                changes=changes,
            )
    setting.refresh_from_db()
    return serialize(kind, setting)


def _update_summary(kind: str, changes: dict) -> str:
    label = kind_label(kind)
    parts = []
    if "mode" in changes:
        parts.append("modo real" if changes["mode"][1] == "real" else "modo simulado")
    if "enabled" in changes:
        parts.append("activada" if changes["enabled"][1] else "desactivada")
    if any(key.startswith("config.") for key in changes):
        parts.append("configuración")
    if any(key.startswith("secrets.") for key in changes):
        parts.append("credenciales")
    return f"Integración «{label}» actualizada: {', '.join(parts)}"


def test(property, kind: str, *, actor) -> dict:
    """Run the provider's `test_connection()` and store the result in the setting's status."""
    check_kind(kind)
    setting = integrations.get_setting(property, kind)
    secrets = integrations.get_secrets(setting)
    try:
        provider = integrations.get_provider(property, kind)
        ok, message = provider.test_connection()
    except DomainError as exc:
        ok, message = False, exc.message
    except Exception as exc:  # noqa: BLE001 - a broken provider is a failed test, not a 500
        logger.exception("Integration test failed (%s, property=%s)", kind, property.pk)
        ok, message = False, f"Error inesperado del proveedor: {type(exc).__name__}"
    message = redact_text(str(message or ("OK" if ok else "Error")), secrets)[:2000]
    before = setting.status
    setting.status = IntegrationSetting.Status.OK if ok else IntegrationSetting.Status.ERROR
    setting.status_message = message
    setting.last_checked_at = timezone.now()
    setting.save(update_fields=["status", "status_message", "last_checked_at", "updated_at"])
    audit.record(
        action="control.integration_tested",
        target=setting,
        summary=(
            f"Prueba de conexión de «{kind_label(kind)}» ({setting.mode}): {STATUS_LABELS[setting.status]}"
        ),
        actor=actor,
        property=property,
        changes={"status": [before, setting.status]},
    )
    return {**serialize(kind, setting), "test": {"ok": ok, "message": message}}
