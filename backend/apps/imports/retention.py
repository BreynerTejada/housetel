"""Habeas Data retention of the importer's own copy of the file (Ley 1581).

The rows keep the original cells (`raw`) and the normalized values (`data`) only while they are useful: to
review, run, look at the result and download the report. Afterwards they are erased, keeping the outcome
(what was created, where) so the history stays meaningful:

- `purge(retention_days, abandoned_days)` (automation `imports.purge_data`, daily): erases the cells of the
  jobs finished more than `retention_days` ago (default 30) and deletes the jobs that were uploaded but never
  run for `abandoned_days` (default 14).
- `erase_guest_rows(guest_ids)`: when a guest is anonymized, the rows that imported them (as a guest or as
  the booker of a reservation) lose their cells right away.
"""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.imports.models import ImportJob, ImportRow

FINISHED = (ImportJob.Status.COMPLETED, ImportJob.Status.FAILED, ImportJob.Status.REVERTED)
UNRUN = (ImportJob.Status.UPLOADED, ImportJob.Status.VALIDATED)


def erase_guest_rows(guest_ids) -> int:
    ids = [str(value) for value in guest_ids if value]
    if not ids:
        return 0
    return ImportRow.objects.filter(
        Q(target_type="guests.guest", target_id__in=ids) | Q(extra__guest_id__in=ids)
    ).update(raw={}, data={}, issues=[], target_label="")


def purge(*, retention_days: int = 30, abandoned_days: int = 14) -> dict:
    now = timezone.now()
    finished = ImportJob.objects.filter(
        status__in=FINISHED, data_purged_at__isnull=True, finished_at__lt=now - timedelta(days=retention_days)
    )
    job_ids = list(finished.values_list("pk", flat=True))
    rows = ImportRow.objects.filter(job_id__in=job_ids).update(raw={}, data={}, issues=[])
    ImportJob.objects.filter(pk__in=job_ids).update(data_purged_at=now, headers=[])
    abandoned = ImportJob.objects.filter(
        status__in=UNRUN, updated_at__lt=now - timedelta(days=abandoned_days)
    )
    deleted = abandoned.count()
    abandoned.delete()
    return {"jobs_purged": len(job_ids), "rows_purged": rows, "abandoned_deleted": deleted}
