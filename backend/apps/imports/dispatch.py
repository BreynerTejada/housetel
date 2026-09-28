"""Queueing a job's dry-run, run or rollback.

Production: always Celery (`imports.process_job`); a job waits in the queue until a worker with this code
takes it (e.g. during a deploy). Development (`DEBUG`): when no running worker knows the task — the dev
worker was started before this app existed and is not restarted automatically — or the broker is down, the
job runs in a background thread of the web process, so the importer works in the UI right away. A queued job
that nobody picked up for 2 minutes (or a run whose worker died) can be launched again (`engine.is_stale`).
"""

import logging
import threading

from django.conf import settings
from django.core.cache import cache
from django.db import connection, transaction
from django.utils import timezone

from apps.imports.models import ImportJob

logger = logging.getLogger("housetel.imports")

TASK_NAME = "imports.process_job"
WORKER_CACHE_KEY = "imports:worker-knows-task"


def enqueue(job: ImportJob, mode: str, *, actor, total: int = 0) -> ImportJob:
    job.status = ImportJob.Status.QUEUED
    job.phase = mode
    job.queued_at = timezone.now()
    job.started_at = None
    job.finished_at = None
    job.heartbeat_at = None
    job.progress_done = 0
    job.progress_total = total
    job.error = ""
    job.run_by = actor if getattr(actor, "is_authenticated", False) else None
    job.save(
        update_fields=[
            "status", "phase", "queued_at", "started_at", "finished_at", "heartbeat_at", "progress_done",
            "progress_total", "error", "run_by", "updated_at",
        ]
    )  # fmt: skip
    job_id = str(job.pk)
    transaction.on_commit(lambda: send(job_id, mode))
    return job


def send(job_id: str, mode: str) -> str:
    """'worker' | 'inline' (how the job was handed over)."""
    from apps.imports.tasks import process_import_job

    if settings.DEBUG and not worker_knows_task():
        run_inline(job_id, mode)
        return "inline"
    try:
        process_import_job.delay(job_id, mode)
        return "worker"
    except Exception:  # noqa: BLE001 - broker down: better slow than lost
        logger.exception("Could not queue import job %s; running it in the web process", job_id)
        run_inline(job_id, mode)
        return "inline"


def worker_knows_task() -> bool:
    """Some Celery worker answered that it has `imports.process_job` registered (cached for a minute)."""
    cached = cache.get(WORKER_CACHE_KEY)
    if cached is not None:
        return bool(cached)
    try:
        from config.celery import app

        replies = app.control.inspect(timeout=1.0).registered() or {}
        known = any(
            any(str(name).split(" ")[0] == TASK_NAME for name in (tasks or [])) for tasks in replies.values()
        )
    except Exception:  # noqa: BLE001 - broker down or no worker
        known = False
    cache.set(WORKER_CACHE_KEY, known, 60 if known else 15)
    return known


def run_inline(job_id: str, mode: str) -> None:
    def target():
        from apps.imports.engine import process

        try:
            process(job_id, mode)
        finally:
            connection.close()

    threading.Thread(target=target, name=f"import-{job_id[:8]}", daemon=True).start()
