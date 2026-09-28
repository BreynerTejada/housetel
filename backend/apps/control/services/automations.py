"""Automations of a property (spec §6 + plan C12) on top of `apps.core.automation`: list with schedule, state,
last run and recent history; enable/disable and params (`AutomationSetting`); run now; run history.

Only `scope="property"` automations are listed (platform ones belong to the super-admin). "Run now" runs
synchronously when the automation usually takes < 10 s (median of its last finished runs in this property,
or unknown) and is queued on Celery otherwise (`apps.control.tasks.run_automation_now`).
"""

import logging
from datetime import timedelta
from statistics import median

from django.db import transaction
from django.db.models import Count, F, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

from apps.control.services import schedules
from apps.control.services.scrub import scrub
from apps.core import audit, automation
from apps.core.errors import ConflictError, DomainError
from apps.core.models import AutomationRun, AutomationSetting

logger = logging.getLogger("housetel.control")

SYNC_LIMIT_SECONDS = 10
RECENT_RUNS = 10
RUNNING_WINDOW = timedelta(minutes=15)  # a "running" row older than this is a crashed run, not a live one


def property_automations() -> list[automation.Automation]:
    return [item for item in automation.all() if item.scope == "property"]


def get_item(code: str) -> automation.Automation:
    item = automation.get(code)  # 404 automation_not_found
    if item.scope != "property":
        raise automation.AutomationNotFound(f"Automatización desconocida: {code}")
    return item


# ---- Serialization ---------------------------------------------------------------------------------------


def _user_ref(user) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.pk), "email": user.email, "name": user.full_name or user.email}


def _duration_ms(run) -> int | None:
    if run.finished_at is None or run.started_at is None:
        return None
    return max(0, int((run.finished_at - run.started_at).total_seconds() * 1000))


def names(item) -> dict:
    return {"es": item.name_es, "en": item.name_en or item.name_es}


def _item_or_none(code: str):
    try:
        return automation.get(code)
    except automation.AutomationNotFound:
        return None


def serialize_run(run, *, with_details: bool = True) -> dict:
    item = _item_or_none(run.code)
    data = {
        "id": str(run.pk),
        "code": run.code,
        "name": names(item) if item else {"es": run.code, "en": run.code},
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "duration_ms": _duration_ms(run),
        "summary": run.summary,
        "triggered_by": _user_ref(run.triggered_by),
        "manual": run.triggered_by_id is not None,
    }
    if with_details:
        details = scrub(run.details or {})
        data["details"] = details
    return data


def _param_spec(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "text"
    return "json"


def serialize(item, property, *, setting=None, last_run=None, recent=None, stats=None, now=None) -> dict:
    params = {**item.default_params, **(setting.params if setting else {})}
    return {
        "code": item.code,
        "app": item.app,
        "name": names(item),
        "description": {"es": item.description_es, "en": item.description_en or item.description_es},
        "schedule": schedules.describe(item.schedule),
        "next_run_at": schedules.next_run_at(item.schedule, now),
        "enabled": setting.enabled if setting else item.default_enabled,
        "default_enabled": item.default_enabled,
        "customized": setting is not None,
        "params": scrub(params),
        "default_params": scrub(dict(item.default_params)),
        "param_types": {key: _param_spec(value) for key, value in item.default_params.items()},
        "last_run": serialize_run(last_run, with_details=False) if last_run else None,
        "recent_runs": recent or [],
        "stats_7d": stats or {"runs": 0, "failed": 0},
    }


def list_for(property) -> list[dict]:
    items = property_automations()
    codes = [item.code for item in items]
    settings = {s.code: s for s in AutomationSetting.objects.filter(property=property, code__in=codes)}
    runs = AutomationRun.objects.filter(property=property, code__in=codes)
    last_runs = {
        run.code: run
        for run in runs.select_related("triggered_by").order_by("code", "-started_at").distinct("code")
    }
    recent: dict[str, list] = {}
    ranked = runs.annotate(
        rank=Window(RowNumber(), partition_by=[F("code")], order_by=F("started_at").desc())
    ).filter(rank__lte=RECENT_RUNS)
    for row in ranked.values("id", "code", "status", "started_at").order_by("code", "-started_at"):
        recent.setdefault(row["code"], []).append(
            {"id": str(row["id"]), "status": row["status"], "started_at": row["started_at"]}
        )
    since = timezone.now() - timedelta(days=7)
    stats = {
        row["code"]: {"runs": row["runs"], "failed": row["failed"]}
        for row in runs.filter(started_at__gte=since)
        .values("code")
        .annotate(runs=Count("id"), failed=Count("id", filter=Q(status=AutomationRun.Status.FAILED)))
    }
    now = timezone.now()
    return [
        serialize(
            item,
            property,
            setting=settings.get(item.code),
            last_run=last_runs.get(item.code),
            recent=recent.get(item.code),
            stats=stats.get(item.code),
            now=now,
        )
        for item in items
    ]


def detail(property, code: str) -> dict:
    code = get_item(code).code
    return next(item for item in list_for(property) if item["code"] == code)


# ---- Writes ----------------------------------------------------------------------------------------------


def _coerce_param(default, value):
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false", "1", "0"}:
            return value.lower() in {"true", "1"}
        raise ValueError("Debe ser verdadero o falso")
    if isinstance(default, int):
        if isinstance(value, bool):
            raise ValueError("Debe ser un número entero")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError("Debe ser un número entero") from None
        if not number.is_integer():
            raise ValueError("Debe ser un número entero")
        return int(number)
    if isinstance(default, float):
        if isinstance(value, bool):
            raise ValueError("Debe ser un número")
        try:
            return float(value)
        except (TypeError, ValueError):
            raise ValueError("Debe ser un número") from None
    if isinstance(default, str):
        if not isinstance(value, str):
            raise ValueError("Debe ser un texto")
        return value.strip()[:500]
    if isinstance(default, list) and isinstance(value, list):
        return value
    if isinstance(default, dict) and isinstance(value, dict):
        return value
    raise ValueError("Tipo de valor inválido")


def update(property, code: str, data: dict, *, actor) -> dict:
    """PATCH `{enabled?, params?}`. `params` only accepts the keys the automation declares in `default_params`
    (typed like their defaults); `params: {}` or null restores the defaults."""
    item = get_item(code)
    errors: dict[str, list[str]] = {}
    params_in = data.get("params", ...)
    new_params = None
    if params_in is not ... and params_in is not None:
        if not isinstance(params_in, dict):
            raise DomainError("Los parámetros deben ser un objeto", code="validation_error")
        new_params = {}
        for key, value in params_in.items():
            if key not in item.default_params:
                errors[f"params.{key}"] = ["Parámetro desconocido"]
                continue
            try:
                new_params[key] = _coerce_param(item.default_params[key], value)
            except ValueError as exc:
                errors[f"params.{key}"] = [str(exc)]
    if errors:
        raise DomainError(next(iter(errors.values()))[0], code="validation_error", fields=errors)

    with transaction.atomic():
        setting, _ = AutomationSetting.objects.select_for_update().get_or_create(
            property=property, code=item.code, defaults={"enabled": item.default_enabled, "params": {}}
        )
        changes: dict[str, list] = {}
        enabled = data.get("enabled")
        if enabled is not None and bool(enabled) != setting.enabled:
            changes["enabled"] = [setting.enabled, bool(enabled)]
            setting.enabled = bool(enabled)
        if params_in is not ...:
            before = {**item.default_params, **(setting.params or {})}
            # only the values that differ from the defaults are stored
            stored = {k: v for k, v in (new_params or {}).items() if v != item.default_params.get(k)}
            after = {**item.default_params, **stored}
            for key in sorted(set(before) | set(after)):
                if before.get(key) != after.get(key):
                    changes[f"params.{key}"] = [before.get(key), after.get(key)]
            setting.params = stored
        if changes:
            setting.save()
            audit.record(
                action="control.automation_updated",
                target=setting,
                summary=_update_summary(item, changes),
                actor=actor,
                property=property,
                changes=scrub(changes),
            )
    return detail(property, item.code)


def _update_summary(item, changes: dict) -> str:
    parts = []
    if "enabled" in changes:
        parts.append("activada" if changes["enabled"][1] else "desactivada")
    if any(key.startswith("params.") for key in changes):
        parts.append("parámetros actualizados")
    return f"Automatización «{item.name_es}»: {', '.join(parts)}"


def estimated_seconds(property, code: str) -> float | None:
    durations = [
        (run.finished_at - run.started_at).total_seconds()
        for run in AutomationRun.objects.filter(property=property, code=code, finished_at__isnull=False)
        .exclude(status=AutomationRun.Status.RUNNING)
        .only("started_at", "finished_at")
        .order_by("-started_at")[:5]
    ]
    return median(durations) if durations else None


def run_now(property, code: str, *, actor) -> dict:
    """`{"queued": bool, "run": run | None, "estimated_seconds": float | None}`."""
    item = get_item(code)
    running = AutomationRun.objects.filter(
        property=property,
        code=item.code,
        status=AutomationRun.Status.RUNNING,
        started_at__gte=timezone.now() - RUNNING_WINDOW,
    ).exists()
    if running:
        raise ConflictError("Esta automatización ya se está ejecutando", code="automation_running")
    estimate = estimated_seconds(property, item.code)
    if estimate is not None and estimate >= SYNC_LIMIT_SECONDS:
        from apps.control.tasks import run_automation_now

        try:
            run_automation_now.delay(item.code, str(property.pk), str(actor.pk) if actor else None)
            return {"queued": True, "run": None, "estimated_seconds": round(estimate, 1)}
        except Exception:  # noqa: BLE001 - broker down: run it here instead of failing the click
            logger.exception("Could not queue automation %s; running it synchronously", item.code)
    run = automation.run(item.code, property, triggered_by=actor)
    run.refresh_from_db()
    return {"queued": False, "run": serialize_run(run), "estimated_seconds": estimate}
