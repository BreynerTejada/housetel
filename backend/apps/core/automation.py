"""Automation framework (spec §6). Apps register in `apps/<app>/automations.py`; Celery beat gets a static
schedule from this registry (config/celery.py) and `apps.core.tasks.run_automation_task` fans out per
property.
"""

import logging
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

from django.apps import apps as django_apps
from django.db import transaction
from django.utils import timezone

from apps.core.errors import NotFoundError

logger = logging.getLogger("housetel.automation")


@dataclass(frozen=True)
class RunResult:
    status: str = "success"  # success | partial | failed | skipped
    summary: str = ""
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Automation:
    code: str
    app: str
    name_es: str
    name_en: str
    description_es: str
    schedule: Any  # celery.schedules.crontab(...) or seconds (float)
    handler: Callable  # handler(property_or_None, params: dict) -> RunResult | None
    default_enabled: bool = True
    scope: str = "property"  # property | platform
    default_params: dict = field(default_factory=dict)
    description_en: str = ""


class AutomationNotFound(NotFoundError):
    code = "automation_not_found"


_REGISTRY: dict[str, Automation] = {}


def register(item: Automation) -> None:
    if item.scope not in ("property", "platform"):
        raise ValueError(f"Alcance inválido: {item.scope}")
    _REGISTRY[item.code] = item


def get(code: str) -> Automation:
    try:
        return _REGISTRY[code]
    except KeyError:
        raise AutomationNotFound(f"Automatización desconocida: {code}") from None


def all() -> list[Automation]:  # noqa: A001 - contract name (plan Step 2)
    return sorted(_REGISTRY.values(), key=lambda item: item.code)


def _setting(code: str, property):
    from apps.core.models import AutomationSetting

    return AutomationSetting.objects.filter(property=property, code=code).first()


def is_enabled(code: str, property) -> bool:
    item = get(code)
    setting = _setting(code, property)
    return setting.enabled if setting is not None else item.default_enabled


def params_for(code: str, property) -> dict:
    item = get(code)
    setting = _setting(code, property)
    return {**item.default_params, **(setting.params if setting is not None else {})}


def run(code: str, property=None, *, params=None, triggered_by=None):
    """Execute one automation for one property (or the platform) and record everything.

    The handler runs inside `transaction.atomic()`: if it raises, its changes are rolled back, the run is
    marked `failed` and an alert `automation:<code>` is raised; a later success resolves that alert.
    """
    from apps.core import alerts, audit
    from apps.core.models import AutomationRun

    item = get(code)
    run_obj = AutomationRun.objects.create(property=property, code=code, triggered_by=triggered_by)
    effective_params = {**params_for(code, property), **(params or {})}
    dedupe_key = f"automation:{code}"
    try:
        with transaction.atomic():
            result = item.handler(property, effective_params) or RunResult()
    except Exception as exc:
        logger.exception("Automation %s failed (property=%s)", code, getattr(property, "pk", None))
        run_obj.status = AutomationRun.Status.FAILED
        run_obj.summary = f"Error: {exc}"[:1000]
        run_obj.details = {
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=15),
        }
        alerts.raise_alert(
            property=property,
            kind="automation_failed",
            severity="warning",
            title=f"Falló la automatización «{item.name_es}»",
            message=str(exc)[:2000],
            link="/app/settings/automations",
            dedupe_key=dedupe_key,
            data={"code": code, "run_id": str(run_obj.pk)},
            source="automation",
        )
    else:
        run_obj.status = result.status
        run_obj.summary = result.summary
        run_obj.details = result.details
        if result.status == RunResult().status:
            alerts.resolve_alert(property, dedupe_key)
    run_obj.finished_at = timezone.now()
    run_obj.save()
    audit.record(
        action=f"automation.{code}",
        target=run_obj,
        summary=run_obj.summary or item.name_es,
        actor=triggered_by,
        source="automation",
        property=property,
        actor_label=None if triggered_by is not None else item.name_es,
        changes={"status": run_obj.status},
    )
    return run_obj


def autodiscover() -> None:
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        try:
            import_module(f"{cfg.name}.automations")
        except ModuleNotFoundError as exc:
            if exc.name != f"{cfg.name}.automations":
                raise
