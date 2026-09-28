"""Downloadable report of a job (CSV, `;`-separated, UTF-8 with BOM for Excel in Spanish).

One line per file row: row number, id, validation status, issues, dry-run result, final result and what it
created, followed by the original columns, so the hotel can fix the rows with errors in the same file and
upload only those again.
"""

import csv
import io

from apps.imports.messages import text
from apps.imports.models import ImportJob, ImportRow

LABELS = {
    "es": {
        "row": "Fila", "external_id": "Id", "status": "Revisión", "issues": "Observaciones",
        "dry": "Simulación", "outcome": "Resultado", "detail": "Detalle", "target": "Creado / actualizado",
        "revert": "Reversión",
    },
    "en": {
        "row": "Row", "external_id": "Id", "status": "Review", "issues": "Notes", "dry": "Dry run",
        "outcome": "Result", "detail": "Detail", "target": "Created / updated", "revert": "Rollback",
    },
}  # fmt: skip

STATUS = {
    "es": {
        "pending": "Sin revisar",
        "valid": "Lista",
        "warning": "Advertencia",
        "error": "Error",
        "skip": "Se omite",
    },
    "en": {
        "pending": "Not reviewed",
        "valid": "Ready",
        "warning": "Warning",
        "error": "Error",
        "skip": "Skipped",
    },
}
OUTCOME = {
    "es": {
        "": "", "created": "Creado", "updated": "Actualizado", "skipped": "Omitido", "failed": "Con error",
        "reverted": "Revertido", "create": "Se crearía", "update": "Se actualizaría", "skip": "Se omitiría",
        "fail": "Fallaría",
    },
    "en": {
        "": "", "created": "Created", "updated": "Updated", "skipped": "Skipped", "failed": "Failed",
        "reverted": "Rolled back", "create": "Would create", "update": "Would update", "skip": "Would skip",
        "fail": "Would fail",
    },
}  # fmt: skip


def job_report(job: ImportJob, *, lang: str = "es", only: str = "") -> tuple[bytes, str]:
    """(content, filename). `only="issues"` keeps rows with errors or warnings (or failed ones)."""
    lang = "en" if lang == "en" else "es"
    labels = LABELS[lang]
    headers = list(job.headers or [])
    rows = job.rows.order_by("number")
    if only == "issues":
        rows = rows.filter(status__in=(ImportRow.Status.ERROR, ImportRow.Status.WARNING)) | job.rows.filter(
            outcome=ImportRow.Outcome.FAILED
        )
        rows = rows.order_by("number").distinct()
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [labels["row"], labels["external_id"], labels["status"], labels["issues"], labels["dry"],
         labels["outcome"], labels["detail"], labels["target"], labels["revert"], *headers]
    )  # fmt: skip
    for row in rows.iterator():
        issues = " | ".join(
            text(item, lang)
            for item in (row.issues or [])
            if item.get("level") in ("error", "warning", "skip")
        )
        dry = OUTCOME[lang].get(row.dry_outcome, row.dry_outcome)
        if row.dry_outcome and row.dry_message:
            dry = f"{dry}: {text(row.dry_message, lang)}"
        writer.writerow(
            [
                row.number,
                row.external_id,
                STATUS[lang].get(row.status, row.status),
                issues,
                dry,
                OUTCOME[lang].get(row.outcome, row.outcome),
                text(row.outcome_message, lang),
                row.target_label,
                text((row.extra or {}).get("revert"), lang),
                *[(row.raw or {}).get(header, "") for header in headers],
            ]
        )
    stem = job.filename.rsplit(".", 1)[0][:60] or "importacion"
    suffix = (
        "errores"
        if only == "issues" and lang == "es"
        else "issues"
        if only == "issues"
        else ("reporte" if lang == "es" else "report")
    )
    return ("﻿" + buffer.getvalue()).encode("utf-8"), f"{stem}-{suffix}.csv"
