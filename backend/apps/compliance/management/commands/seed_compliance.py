"""`python manage.py seed_compliance`: only the legal demo data (apps/compliance/seed.py) on top of an already
seeded demo (`seed_demo`), without re-running the other seeders. Idempotent, ~50 s."""

import random

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.compliance.seed import seed
from apps.core.models import Property
from apps.core.seed import PROPERTIES, RNG_SEED, SeedContext
from apps.core.signals import seeding


class Command(BaseCommand):
    help = "Siembra los datos legales de demostración (facturas, SIRE, TRA) sobre el demo ya cargado."

    def handle(self, *args, **options):
        ctx = SeedContext(today=timezone.localdate(), rng=random.Random(RNG_SEED), stdout=self.stdout)
        keys = {values["slug"]: key for key, values in PROPERTIES.items()}
        for prop in Property.objects.filter(slug__in=keys):
            ctx.properties[keys[prop.slug]] = prop
        if not ctx.properties:
            self.stdout.write("No hay propiedades de demostración: corre antes `python manage.py seed_demo`.")
            return
        with seeding(), transaction.atomic():
            seed(ctx)
        self.stdout.write("Datos legales de demostración listos")
