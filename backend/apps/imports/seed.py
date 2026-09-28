# ruff: noqa: E501 - example rows and demo data are long literal lines (kept in `fmt: skip` blocks)
"""Demo data of imports (pilot plan P5): Casa Aurora's history shows one finished import — the guest list
exported from Cloudbeds three days ago — run through the real importer (upsert of every guest):

- 6 new guests, 2 rows that matched guests already in Housetel (same email: their data was completed), one
  row with an invalid email (imported without it) and one without a name (error), so the result page and
  the downloadable report have something to show.

Idempotent: skipped when the property already has that job. Needs `SEED_ORDER` to include "imports"
(P-INT). Runs in well under a second.
"""

from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

FILENAME = "huespedes-cloudbeds.csv"
HEADER = "Guest ID,First Name,Last Name,Email,Phone,Gender,Date of Birth,Country,City,Document Type,Document Number"
NEW_GUESTS = [
    "CB-20431,Mariana,Ospina Duque,mariana.ospina@example.com,+57 311 555 0101,Female,1988-02-11,Colombia,Pereira,CC,1088234567",
    "CB-20432,Thomas,Müller,thomas.muller@example.de,+49 151 5550 1234,Male,1979-06-02,Germany,Munich,Passport,C4F7K9L21",
    "CB-20433,Isabella,Rossi,isabella.rossi@example.it,,Female,1992-09-30,Italy,Milan,Passport,YA7654321",
    "CB-20434,Andrés Felipe,Cárdenas,andres.cardenas@example.com,+57 300 555 0144,Male,1985-12-19,Colombia,Bogotá,CC,80765432",
    "CB-20435,Emily,Johnson,emily.johnson@example.com,+1 212 555 0187,Female,1995-04-07,United States,New York,Passport,584930216",
    "CB-20436,Juliana,Pérez Vélez,juliana.perez@example,+57 320 555 0133,Female,,Colombia,Cartagena,,",
    "CB-20437,,,sin.nombre@example.com,+57 301 555 0199,,,Colombia,,,",
    "CB-20438,Carlos,Mendoza Ríos,carlos.mendoza@example.com,,Male,1970-01-25,Mexico,Guadalajara,Passport,G12345678",
]  # fmt: skip


def seed(ctx) -> None:
    from apps.guests.models import Guest
    from apps.imports import services
    from apps.imports.engine import Runner
    from apps.imports.models import ImportJob

    prop = ctx.properties.get("aurora")
    user = ctx.users.get("aurora_owner")
    if prop is None or user is None:
        ctx.log("  imports: sin Casa Aurora, se omite")
        return
    if ImportJob.objects.filter(property=prop, filename=FILENAME).exists():
        ctx.log("  imports: ya existe la importación de demo")
        return
    existing = list(
        Guest.objects.filter(
            organization=prop.organization, merged_into__isnull=True, anonymized_at__isnull=True
        )
        .exclude(email="")
        .order_by("created_at", "email")[:2]
    )
    matched = [
        f"CB-2044{index},{guest.first_name},{guest.last_name},{guest.email},,,,,,,"
        for index, guest in enumerate(existing, start=1)
    ]
    content = "\n".join([HEADER, *NEW_GUESTS, *matched]) + "\n"
    upload = SimpleUploadedFile(FILENAME, content.encode("utf-8"), content_type="text/csv")
    job = services.create_job(prop, user=user, kind="guests", preset="cloudbeds", upload=upload)
    job = services.configure(job, {"mapping": job.mapping})
    ImportJob.objects.filter(pk=job.pk).update(
        status=ImportJob.Status.RUNNING, phase=ImportJob.Phase.RUN, run_by=user, started_at=timezone.now()
    )
    job.refresh_from_db()
    Runner(job, ImportJob.Phase.RUN).execute()
    when = timezone.now() - timedelta(days=3)
    ImportJob.objects.filter(pk=job.pk).update(
        created_at=when,
        queued_at=when,
        started_at=when,
        finished_at=when + timedelta(seconds=4),
        heartbeat_at=when + timedelta(seconds=4),
    )
    job.refresh_from_db()
    ctx.log(f"  imports: importación de demo «{FILENAME}» · {job.summary}")
