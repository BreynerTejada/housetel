"""`python manage.py seed_groups [--dry-run]`: only the pilot-plan P3 demo data of bookings — groups with
allotments, pickups and rooming names, and a two-room family reservation (`apps.bookings.seed.seed_groups`) —
on top of an already seeded demo, without re-running the other seeders. Idempotent: a group that exists by
name is left as it is. `--dry-run` runs it inside a transaction that is rolled back."""

import random
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.bookings.seed import seed_groups
from apps.core.models import Property
from apps.core.seed import PROPERTIES, RNG_SEED, SeedContext
from apps.core.signals import seeding


class _Rollback(Exception):
    pass


class Command(BaseCommand):
    help = "Siembra los grupos con cupos, pickups y rooming list, y una reserva de dos habitaciones (P3)."

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
                for key, prop in ctx.properties.items():
                    self.stdout.write(f"  {prop.name}")
                    seed_groups(ctx, key, prop)
                if options["dry_run"]:
                    raise _Rollback
        except _Rollback:
            self.stdout.write(f"Dry run: todo revertido ({time.monotonic() - started:.1f} s)")
            return
        self.stdout.write(f"Grupos y cupos de demostración listos ({time.monotonic() - started:.1f} s)")
