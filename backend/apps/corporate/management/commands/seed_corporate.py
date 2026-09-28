"""`python manage.py seed_corporate [--dry-run]`: only the corporate demo data (apps/corporate/seed.py) on top
of an already seeded demo (`seed_demo`), without re-running the other seeders. Idempotent. `--dry-run` runs it
inside a transaction that is rolled back (prints what it would create)."""

import random
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.core.models import Property
from apps.core.seed import PROPERTIES, RNG_SEED, SeedContext
from apps.core.signals import seeding
from apps.corporate.seed import seed


class _Rollback(Exception):
    pass


class Command(BaseCommand):
    help = "Siembra las empresas, reservas facturadas a empresa y la cartera de demostración (P4)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Corre el seed y revierte la transacción")

    def handle(self, *args, **options):
        ctx = SeedContext(today=timezone.localdate(), rng=random.Random(RNG_SEED), stdout=self.stdout)
        keys = {values["slug"]: key for key, values in PROPERTIES.items()}
        for prop in Property.objects.filter(slug__in=keys):
            ctx.properties[keys[prop.slug]] = prop
        if not ctx.properties:
            self.stdout.write("No hay propiedades de demostración: corre antes `python manage.py seed_demo`.")
            return
        started = time.monotonic()
        try:
            with seeding(), transaction.atomic():
                seed(ctx)
                if options["dry_run"]:
                    raise _Rollback
        except _Rollback:
            self.stdout.write(f"Dry run: todo revertido ({time.monotonic() - started:.1f} s)")
            return
        self.stdout.write(f"Datos corporativos de demostración listos ({time.monotonic() - started:.1f} s)")
