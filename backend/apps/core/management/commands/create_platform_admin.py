"""`manage.py create_platform_admin` — the first Housetel super-admin of a new installation (plan P1).

Creates the user, or promotes an existing one, with `is_platform_admin` (the `/admin` panel of the SPA) plus
Django's `is_staff`/`is_superuser` (`/django-admin/` when ADMIN_ENABLED=1, `/api/docs/` in production).

    make prod-createsuperuser                                   # interactive (production stack)
    python manage.py create_platform_admin --email admin@example.com --name "Ana Pérez"
    ADMIN_PASSWORD=… python manage.py create_platform_admin --email admin@example.com \
        --password-env ADMIN_PASSWORD
"""

import getpass
import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create or promote a Housetel platform admin (is_platform_admin + Django staff/superuser)."

    def add_arguments(self, parser):
        parser.add_argument("--email", help="E-mail of the admin (asked for when missing).")
        parser.add_argument("--name", default="", help="Full name (new users only).")
        parser.add_argument(
            "--password-env",
            metavar="VAR",
            help="Read the password from this environment variable instead of asking (non-interactive).",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        email = (options["email"] or input("Email: ")).strip().lower()
        if not email or "@" not in email:
            raise CommandError("Escribe un email válido.")
        user = User.objects.filter(email__iexact=email).first()

        password = None
        if options["password_env"]:
            password = os.environ.get(options["password_env"], "")
            if not password:
                raise CommandError(f"La variable de entorno {options['password_env']} está vacía.")
        elif user is None or self._confirm("¿Cambiar su contraseña? [s/N] "):
            password = self._ask_password()
        if password is not None:
            try:
                validate_password(password, user=user)
            except ValidationError as exc:
                raise CommandError(" ".join(exc.messages)) from exc

        with transaction.atomic():
            if user is None:
                user = User.objects.create_superuser(
                    email=email, password=password, full_name=options["name"], is_platform_admin=True
                )
                self.stdout.write(self.style.SUCCESS(f"Super-admin creado: {user.email}"))
                return
            user.is_platform_admin = user.is_staff = user.is_superuser = user.is_active = True
            if password is not None:
                user.set_password(password)
            user.save()
        self.stdout.write(self.style.SUCCESS(f"{user.email} ahora es super-admin de la plataforma"))

    @staticmethod
    def _confirm(question: str) -> bool:
        return input(question).strip().lower() in {"s", "si", "sí", "y", "yes"}

    @staticmethod
    def _ask_password() -> str:
        first = getpass.getpass("Contraseña: ")
        if first != getpass.getpass("Repite la contraseña: "):
            raise CommandError("Las contraseñas no coinciden.")
        if not first:
            raise CommandError("La contraseña no puede estar vacía.")
        return first
