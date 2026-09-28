"""Automations of `guests` (plan P6): `guests.purge_identity_documents`, daily at 03:40 (hotel time zone of
beat). Registered on import (auto-discovered by the core).

Habeas Data retention: deletes the photos of identity documents and the signatures N days after the departure
(`retention_days`, default 180, per property from the automation's parameters; 0 = never). See
`apps.guests.retention`."""

from celery.schedules import crontab

from apps.core.automation import Automation, RunResult, register
from apps.guests.retention import DEFAULT_RETENTION_DAYS, purge_identity_documents


def _count(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def purge_documents(property, params) -> RunResult:
    try:
        days = int(params.get("retention_days", DEFAULT_RETENTION_DAYS))
    except (TypeError, ValueError):
        days = DEFAULT_RETENTION_DAYS
    if days <= 0:
        return RunResult(
            status="skipped",
            summary="Retención en 0 días: este hotel conserva los documentos y las firmas (no se borran)",
            details={"retention_days": days},
        )
    result = purge_identity_documents(property, retention_days=days)
    details = {"retention_days": days, **result.as_dict()}
    if not result.documents and not result.signatures:
        return RunResult(
            summary=f"Nada que borrar: ninguna salida hasta el {result.cutoff:%d/%m/%Y} guarda documentos",
            details=details,
        )
    return RunResult(
        summary=(
            f"Borrados {_count(result.documents, 'documento', 'documentos')} de "
            f"{_count(result.guests, 'huésped', 'huéspedes')} y "
            f"{_count(result.signatures, 'firma', 'firmas')} (salidas hasta el {result.cutoff:%d/%m/%Y})"
        ),
        details=details,
    )


register(
    Automation(
        code="guests.purge_identity_documents",
        app="guests",
        name_es="Retención de documentos (Habeas Data)",
        name_en="Document retention (Habeas Data)",
        description_es=(
            "Borra las fotos de los documentos de identidad y las firmas del check-in online cuando han "
            "pasado los días configurados desde la salida del huésped (por defecto 180; 0 = nunca). Cada "
            "borrado queda en la auditoría."
        ),
        description_en=(
            "Deletes the photos of identity documents and the online check-in signatures once the configured "
            "days have passed since the guest's departure (180 by default; 0 = never). Every deletion is "
            "audited."
        ),
        schedule=crontab(minute=40, hour=3),
        handler=purge_documents,
        default_params={"retention_days": DEFAULT_RETENTION_DAYS},
    )
)
