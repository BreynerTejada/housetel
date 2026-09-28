"""`python manage.py portal_links [--property casa-aurora] [--days 7] [--status not_started]`

Prints the guest-portal magic links of the upcoming arrivals of a property (from its business date), with the
state of their online check-in: a quick way to open `/g/<token>` in a browser for a demo or a manual test
without going through the staff UI (reservation → "Copiar link / QR"). Read-only.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from apps.bookings.models import Reservation
from apps.core.models import Property
from apps.core.tokens import portal_url


class Command(BaseCommand):
    help = "Links del portal del huésped de las próximas llegadas (con el estado del check-in online)."

    def add_arguments(self, parser):
        parser.add_argument("--property", default="casa-aurora", help="Slug de la propiedad")
        parser.add_argument("--days", type=int, default=7, help="Llegadas de hoy a N días (hoy incluido)")
        parser.add_argument(
            "--status",
            choices=["any", "not_started", "in_progress", "completed"],
            default="any",
            help="Filtra por estado del check-in online",
        )
        parser.add_argument("--limit", type=int, default=15)

    def handle(self, *args, property, days, status, limit, **options):
        prop = Property.objects.filter(slug=property).first()
        if prop is None:
            raise CommandError(f"No existe la propiedad «{property}»")
        today = prop.business_date
        reservations = (
            Reservation.objects.filter(
                property=prop,
                status__in=[Reservation.Status.CONFIRMED, Reservation.Status.CHECKED_IN],
                checkin_date__gte=today,
                checkin_date__lt=today + timedelta(days=max(days, 1)),
            )
            .select_related("booker", "online_checkin")
            .order_by("checkin_date", "code")
        )
        shown = 0
        self.stdout.write(f"{prop.name} · fecha de negocio {today.isoformat()}")
        for reservation in reservations:
            checkin = getattr(reservation, "online_checkin", None)
            state = checkin.status if checkin else "not_started"
            if status != "any" and state != status:
                continue
            self.stdout.write(
                f"{reservation.code}  {reservation.checkin_date.isoformat()}  {reservation.status:<10}  "
                f"check-in online: {state:<11}  {reservation.booker.full_name}\n    {portal_url(reservation)}"
            )
            shown += 1
            if shown >= limit:
                break
        if not shown:
            self.stdout.write("Sin llegadas que coincidan.")
