from django.core.management.base import BaseCommand

from apps.core import seed


class Command(BaseCommand):
    help = (
        "Carga los datos de demo de Housetel (idempotente). "
        "--reset borra antes las organizaciones y los usuarios que no son superadmin."
    )

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Borra y recrea los datos de demo")

    def handle(self, *args, **options):
        seed.run(reset=options["reset"], stdout=self.stdout)
        self.stdout.write(
            self.style.SUCCESS("Datos de demo listos · clave de los usuarios demo: housetel123")
        )
