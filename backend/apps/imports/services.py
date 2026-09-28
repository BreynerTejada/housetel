"""Import jobs: create from an upload, configure (mapping, values, options) + validate, launch the dry-run,
the run or the rollback, and the JSON shapes of the API."""

from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.text import slugify

from apps.core.errors import ConfirmationRequired, ConflictError, DomainError
from apps.imports import dispatch, engine
from apps.imports import mapping as mapping_svc
from apps.imports.catalog import DATE_FORMATS, ON_EXISTING, PRESET_LABELS, default_options, spec
from apps.imports.models import ImportJob, ImportRow
from apps.imports.parsing import read_file, safe_filename
from apps.imports.validation import missing_required, validate_job

EDITABLE = (ImportJob.Status.UPLOADED, ImportJob.Status.VALIDATED)
DELETABLE = (ImportJob.Status.UPLOADED, ImportJob.Status.VALIDATED)
ROW_PREVIEW = 8  # rows of the file shown in the mapping step


class JobStateError(ConflictError):
    code = "invalid_job_state"


def _source(preset: str, label: str) -> tuple[str, str]:
    label = (label or "").strip()[:100] or PRESET_LABELS.get(preset, "Otro sistema")
    return (slugify(label)[:60] or "otro-sistema"), label


@transaction.atomic
def create_job(
    prop, *, user, kind: str, preset: str, upload, source_label: str = "", sheet: str = ""
) -> ImportJob:
    if kind not in ImportJob.Kind.values:
        raise DomainError("Tipo de importación inválido", code="invalid_kind", fields={"kind": ["Inválido"]})
    if preset not in ImportJob.Preset.values:
        raise DomainError(
            "Formato de origen inválido", code="invalid_preset", fields={"preset": ["Inválido"]}
        )
    if upload is None:
        raise DomainError(
            "Adjunta un archivo CSV o Excel", code="file_required", fields={"file": ["Obligatorio"]}
        )
    parsed = read_file(upload, sheet=sheet)
    source_system, label = _source(preset, source_label)
    job = ImportJob.objects.create(
        property=prop,
        kind=kind,
        preset=preset,
        source_system=source_system,
        source_label=label,
        filename=safe_filename(getattr(upload, "name", "")),
        file_format=parsed.file_format,
        file_size=getattr(upload, "size", 0) or 0,
        sheet_name=parsed.sheet_name,
        headers=parsed.headers,
        options=default_options(preset),
        total_rows=len(parsed.rows),
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    ImportRow.objects.bulk_create(
        [ImportRow(job=job, number=number, raw=raw) for number, raw in parsed.rows], batch_size=1000
    )
    job.mapping = mapping_svc.suggest_mapping(kind, preset, parsed.headers)
    job.save(update_fields=["mapping", "updated_at"])
    return job


def configure(job: ImportJob, data: dict) -> ImportJob:
    """Save mapping / value mapping / options / source label (any subset) and validate every row again."""
    if job.status not in EDITABLE:
        raise JobStateError("Esta importación ya se ejecutó: crea una nueva para cambiarla")
    if "mapping" in data:
        job.mapping = mapping_svc.clean_mapping(job.kind, job.headers, data.get("mapping") or {})
    if "value_map" in data:
        job.value_map = _clean_value_map(job, data.get("value_map") or {})
    if "options" in data:
        job.options = _clean_options(job, data.get("options") or {})
    if data.get("source_label"):
        job.source_system, job.source_label = _source(job.preset, data["source_label"])
    job.save(update_fields=["mapping", "value_map", "options", "source_system", "source_label", "updated_at"])
    missing = missing_required(job)
    if missing:
        raise DomainError(
            "Faltan columnas obligatorias por asignar",
            code="mapping_incomplete",
            missing=missing,
            fields={"mapping": [", ".join(missing)]},
        )
    return validate_job(job)


def _clean_value_map(job: ImportJob, value_map: dict) -> dict:
    room_types = {option["id"] for option in mapping_svc.room_type_options(job.property)}
    plans = {option["id"] for option in mapping_svc.rate_plan_options(job.property)}
    allowed = {"room_type": room_types, "rate_plan": plans}
    result = {}
    for key, choices in value_map.items():
        if key not in allowed or not isinstance(choices, dict):
            continue
        cleaned = {}
        for value, target in choices.items():
            target = target if isinstance(target, str) else ""
            cleaned[str(value)[:200]] = target if target in allowed[key] else ""
        result[key] = cleaned
    return result


def _clean_options(job: ImportJob, options: dict) -> dict:
    current = {**default_options(job.preset), **(job.options or {})}
    if options.get("date_format") in DATE_FORMATS:
        current["date_format"] = options["date_format"]
    if "amounts_include_tax" in options:
        current["amounts_include_tax"] = bool(options["amounts_include_tax"])
    if options.get("on_existing") in ON_EXISTING:
        current["on_existing"] = options["on_existing"]
    if "default_rate_plan" in options:
        plan = str(options.get("default_rate_plan") or "")
        plans = {option["id"] for option in mapping_svc.rate_plan_options(job.property)}
        current["default_rate_plan"] = plan if plan in plans else ""
    return current


def _ready_rows(job: ImportJob) -> int:
    return job.rows.filter(status__in=(ImportRow.Status.VALID, ImportRow.Status.WARNING)).count()


def start(job: ImportJob, mode: str, *, actor, confirm: bool = False) -> ImportJob:
    """Queue the dry-run, the run or the rollback (409 `invalid_job_state` when the job is not there yet)."""
    stale = job.status in (ImportJob.Status.QUEUED, ImportJob.Status.RUNNING) and engine.is_stale(job)
    if job.status in (ImportJob.Status.QUEUED, ImportJob.Status.RUNNING) and not stale:
        raise JobStateError("Esta importación ya está en proceso")
    if mode in (ImportJob.Phase.RUN, ImportJob.Phase.REVERT) and confirm is not True:
        raise ConfirmationRequired("Confirma la operación")
    with transaction.atomic():
        job = ImportJob.objects.select_for_update().get(pk=job.pk)
        if mode == ImportJob.Phase.DRY_RUN:
            if not (job.status == ImportJob.Status.VALIDATED or (stale and job.phase == mode)):
                raise JobStateError("Revisa el mapeo antes de simular")
            total = _units(job)
        elif mode == ImportJob.Phase.RUN:
            resumable = job.status == ImportJob.Status.FAILED or (stale and job.phase == mode)
            if job.status != ImportJob.Status.VALIDATED and not resumable:
                raise JobStateError("Revisa el mapeo antes de importar")
            if not _ready_rows(job):
                raise JobStateError("No hay filas listas para importar", code="nothing_to_import")
            total = _units(job)
        else:
            if job.kind != ImportJob.Kind.RESERVATIONS:
                raise JobStateError("Solo las importaciones de reservas se pueden revertir")
            if not (
                job.status in (ImportJob.Status.COMPLETED, ImportJob.Status.FAILED)
                or (stale and job.phase == mode)
            ):
                raise JobStateError("Solo se revierte una importación ejecutada")
            total = (
                job.rows.filter(outcome=ImportRow.Outcome.CREATED, target_type="bookings.reservation")
                .values("target_id")
                .distinct()
                .count()
            )
            if not total:
                raise JobStateError(
                    "Esta importación no creó reservas que revertir", code="nothing_to_revert"
                )
        return dispatch.enqueue(job, mode, actor=actor, total=total)


def _units(job: ImportJob) -> int:
    rows = job.rows.filter(status__in=(ImportRow.Status.VALID, ImportRow.Status.WARNING))
    if job.kind == ImportJob.Kind.RESERVATIONS:
        return rows.values("group_key").distinct().count()
    return rows.count()


def delete_job(job: ImportJob) -> None:
    if job.status not in DELETABLE:
        raise JobStateError("Solo se descartan importaciones que no se han ejecutado")
    job.delete()


def revert_preview(job: ImportJob) -> dict:
    """How many reservations of the job a rollback would cancel, and why the others would stay."""
    from apps.bookings.models import Reservation

    rows = list(job.rows.filter(outcome=ImportRow.Outcome.CREATED, target_type="bookings.reservation"))
    by_target: dict = {}
    for row in rows:
        by_target.setdefault(row.target_id, []).append(row)
    reservations = {
        r.pk: r for r in Reservation.objects.filter(pk__in=list(by_target), property=job.property)
    }
    counts = {"revertible": 0, "in_house": 0, "not_active": 0, "activity": 0, "missing": 0}
    for target_id, members in by_target.items():
        reservation = reservations.get(target_id)
        if reservation is None:
            counts["missing"] += 1
        elif reservation.status == "checked_in":
            counts["in_house"] += 1
        elif reservation.status not in ("tentative", "confirmed"):
            counts["not_active"] += 1
        else:
            imported_at = min((row.processed_at for row in members if row.processed_at), default=None)
            payments = {pid for row in members for pid in (row.extra or {}).get("payment_ids", [])}
            if engine._activity(reservation, imported_at, payments):
                counts["activity"] += 1
            else:
                counts["revertible"] += 1
    counts["total"] = len(by_target)
    return counts


# ---- JSON shapes --------------------------------------------------------------------------------------


def _user(user) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.pk), "email": user.email, "name": getattr(user, "full_name", "") or user.email}


def job_summary(job: ImportJob) -> dict:
    """List item."""
    return {
        "id": str(job.pk),
        "kind": job.kind,
        "preset": job.preset,
        "source_label": job.source_label,
        "status": job.status,
        "phase": job.phase,
        "stale": engine.is_stale(job),
        "filename": job.filename,
        "file_format": job.file_format,
        "total_rows": job.total_rows,
        "counts": job.counts or {},
        "summary": job.summary or {},
        "progress": {"done": job.progress_done, "total": job.progress_total},
        "created_by": _user(job.created_by),
        "created_at": job.created_at,
        "finished_at": job.finished_at,
        "reverted_at": job.reverted_at,
        "data_purged": job.data_purged_at is not None,
    }


def job_detail(job: ImportJob) -> dict:
    kind_spec = spec(job.kind)
    preview = list(job.rows.order_by("number").values_list("raw", flat=True)[:500])
    room_types = mapping_svc.room_type_options(job.property) if job.kind != ImportJob.Kind.GUESTS else []
    rate_plans = (
        mapping_svc.rate_plan_options(job.property) if job.kind == ImportJob.Kind.RESERVATIONS else []
    )
    detail = job_summary(job)
    detail.update(
        {
            "source_system": job.source_system,
            "sheet_name": job.sheet_name,
            "file_size": job.file_size,
            "headers": job.headers,
            "samples": mapping_svc.column_samples(job.headers, preview),
            "preview": [
                {"number": number, "raw": raw}
                for number, raw in job.rows.order_by("number").values_list("number", "raw")[:ROW_PREVIEW]
            ],
            "mapping": job.mapping or {},
            "suggested_mapping": mapping_svc.suggest_mapping(job.kind, job.preset, job.headers),
            "missing_required": missing_required(job),
            "fields": [
                {
                    "code": item.code,
                    "type": item.type,
                    "required": item.required,
                    "group": item.group,
                    "value_mapping": item.value_mapping,
                }
                for item in kind_spec.fields
            ],
            "one_of": [list(group) for group in kind_spec.one_of],
            "value_map": job.value_map or {},
            # distinct file values of the category / plan columns: only while the mapping can change (the
            # detail is polled during a run; reading every row each time would be wasted work)
            "values": mapping_svc.value_candidates(
                job, preview_all(job), room_types=room_types, rate_plans=rate_plans
            )
            if job.mapping and job.status in EDITABLE
            else {},
            "room_types": mapping_svc.public_options(room_types),
            "rate_plans": mapping_svc.public_options(rate_plans),
            "options": {**default_options(job.preset), **(job.options or {})},
            "business_date": job.property.business_date,
            "dry_run_at": job.dry_run_at,
            "dry_run_summary": job.dry_run_summary or {},
            "revert_summary": job.revert_summary or {},
            # rows by final outcome, live (after a rollback the reverted rows are counted apart)
            "outcome_counts": _outcome_counts(job),
            "error": job.error,
            "run_by": _user(job.run_by),
            "queued_at": job.queued_at,
            "started_at": job.started_at,
            "heartbeat_at": job.heartbeat_at,
            "reverted_by": _user(job.reverted_by),
            "can_edit": job.status in EDITABLE,
            "can_delete": job.status in DELETABLE,
            "can_revert": job.kind == ImportJob.Kind.RESERVATIONS
            and job.status in (ImportJob.Status.COMPLETED, ImportJob.Status.FAILED)
            and job.rows.filter(
                outcome=ImportRow.Outcome.CREATED, target_type="bookings.reservation"
            ).exists(),
            "ready_rows": _ready_rows(job),
        }
    )
    return detail


def _outcome_counts(job: ImportJob) -> dict:
    if job.status not in (ImportJob.Status.COMPLETED, ImportJob.Status.FAILED, ImportJob.Status.REVERTED):
        return {}
    rows = job.rows.exclude(outcome="").order_by().values("outcome").annotate(total=Count("id"))
    return {row["outcome"]: row["total"] for row in rows}


def preview_all(job: ImportJob) -> list[dict]:
    return list(job.rows.values_list("raw", flat=True))


def row_json(row: ImportRow) -> dict:
    return {
        "id": str(row.id),
        "number": row.number,
        "raw": row.raw,
        "data": row.data,
        "external_id": row.external_id,
        "group_key": row.group_key,
        "status": row.status,
        "issues": row.issues,
        "dry_outcome": row.dry_outcome,
        "dry_message": row.dry_message or {},
        "outcome": row.outcome,
        "outcome_message": row.outcome_message or {},
        "target_type": row.target_type,
        "target_id": str(row.target_id) if row.target_id else None,
        "target_label": row.target_label,
        "revert": (row.extra or {}).get("revert"),
        "processed_at": row.processed_at,
    }


def rows_queryset(job: ImportJob, params) -> "QuerySet":  # noqa: F821
    rows = job.rows.all()
    status = [value for value in params.getlist("status") if value in ImportRow.Status.values]
    if status:
        rows = rows.filter(status__in=status)
    outcome = [value for value in params.getlist("outcome") if value in ImportRow.Outcome.values]
    if outcome:
        rows = rows.filter(outcome__in=outcome)
    dry = [value for value in params.getlist("dry_outcome") if value in ImportRow.DryOutcome.values]
    if dry:
        rows = rows.filter(dry_outcome__in=dry)
    if params.get("issues") in ("1", "true"):
        rows = rows.exclude(issues=[])
    query = (params.get("q") or "").strip()
    if query:
        if query.isdigit():
            rows = rows.filter(number=int(query))
        else:
            rows = rows.filter(external_id__icontains=query) | rows.filter(target_label__icontains=query)
    return rows.order_by("number")


def stale_cleanup_cutoff(days: int):
    return timezone.now() - timedelta(days=days)
