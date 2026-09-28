from celery import shared_task


@shared_task(name="imports.process_job")
def process_import_job(job_id: str, mode: str) -> None:
    """Dry-run, run or rollback of an import job (apps.imports.engine.process). Never raises."""
    from apps.imports.engine import process

    process(job_id, mode)
