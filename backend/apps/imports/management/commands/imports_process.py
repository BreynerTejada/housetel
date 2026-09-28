"""Run a queued (or stuck) import job synchronously, in this process — for support or when no worker runs:

docker compose exec -T backend python manage.py imports_process <job id>            # its queued phase
docker compose exec -T backend python manage.py imports_process <job id> --mode run  # queue + run now
"""

from django.core.management.base import BaseCommand, CommandError

from apps.imports.engine import process
from apps.imports.models import ImportJob


class Command(BaseCommand):
    help = "Procesa en este proceso la simulación, importación o reversión de un job de importación."

    def add_arguments(self, parser):
        parser.add_argument("job_id")
        parser.add_argument("--mode", choices=["dry_run", "run", "revert"], default=None)

    def handle(self, *args, job_id, mode, **options):
        job = ImportJob.objects.filter(pk=job_id).first()
        if job is None:
            raise CommandError("No existe ese job de importación")
        if mode:
            ImportJob.objects.filter(pk=job.pk).update(status=ImportJob.Status.QUEUED, phase=mode)
        elif job.status not in (ImportJob.Status.QUEUED, ImportJob.Status.RUNNING):
            raise CommandError(f"El job está «{job.get_status_display()}»: indica --mode")
        job.refresh_from_db()
        process(str(job.pk), job.phase)
        job.refresh_from_db()
        self.stdout.write(
            f"{job.get_status_display()} · {job.progress_done}/{job.progress_total} · "
            f"{job.summary or job.dry_run_summary or job.revert_summary}"
            + (f" · error: {job.error}" if job.error else "")
        )
