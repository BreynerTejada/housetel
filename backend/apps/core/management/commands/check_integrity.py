"""`python manage.py check_integrity [--property <slug>]`: read-only invariants of inventory and money.

What every phase integration checks after the full demo seed (plan B-INT) and anyone can re-run on live data:

- inventory: `rebuild_inventory` over the stays' span and the horizon finds no drift (it runs inside a
  transaction that is rolled back: nothing is written) and no future night is oversold;
- stays: `total_amount` = Σ `nightly_rates` (one per night); reservation total = Σ its stays;
- balances: `finance.reservation_balance` = the SQL annotation the lists use (`bookings…with_balance`); nobody
  is overpaid; a closed folio owes nothing (folio and reservation);
- charges: a checked-out stay has room charges = its total, an in-house one exactly the nights before the
  business date, a pending/cancelled/no-show one none; penalty charges = `cancellation_fee`;
- payments: an approved payment link has its payment; no charge or payment dated after the business date and
  no payment created in the future.

Exits with an error listing each failed check (with a few examples) when one fails.
"""

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max, Min, Sum
from django.utils import timezone

ZERO = Decimal("0")
EXAMPLES = 3


class Command(BaseCommand):
    help = "Verifica (sin escribir nada) las invariantes de inventario y dinero de cada propiedad."

    def add_arguments(self, parser):
        parser.add_argument("--property", help="Slug de una sola propiedad (por defecto, todas).")

    def handle(self, *args, **options):
        from apps.core.models import Property

        properties = Property.objects.order_by("name")
        if options["property"]:
            properties = properties.filter(slug=options["property"])
        failed = 0
        for prop in properties:
            self.stdout.write(f"== {prop.name} ({prop.slug}) · fecha de negocio {prop.business_date}")
            for label, problems in property_checks(prop):
                if problems:
                    failed += 1
                    examples = "; ".join(str(problem) for problem in problems[:EXAMPLES])
                    self.stdout.write(self.style.ERROR(f"  FALLA {label}: {len(problems)} · {examples}"))
                else:
                    self.stdout.write(f"  ok    {label}")
        if failed:
            raise CommandError(f"{failed} verificación(es) de integridad fallaron")
        self.stdout.write(self.style.SUCCESS("Integridad OK"))


def property_checks(prop) -> list[tuple[str, list]]:
    """[(label, problems)] for one property; an empty list of problems means the check passed."""
    from apps.bookings.models import InventoryDay, Reservation, Stay
    from apps.bookings.services.inventory import rebuild_inventory
    from apps.bookings.services.queries import with_balance
    from apps.finance.models import Charge, Folio, Payment, PaymentIntent
    from apps.finance.services import folio_balance, reservation_balance

    today = prop.business_date
    reservations = Reservation.objects.filter(property=prop)
    stays = Stay.objects.filter(reservation__property=prop).select_related("reservation")
    checks = []

    span = stays.aggregate(start=Min("checkin_date"), end=Max("checkout_date"))
    with transaction.atomic():
        drift = []
        if span["start"]:
            drift += rebuild_inventory(prop, span["start"], span["end"]).drift
        drift += rebuild_inventory(prop).drift
        transaction.set_rollback(True)
    checks.append(("inventario: rebuild_inventory no encuentra deriva", drift))
    oversold = [
        (str(row.room_type_id), row.date.isoformat(), row.available)
        for row in InventoryDay.objects.filter(property=prop, date__gte=today)
        if row.available < 0
    ]
    checks.append(("inventario: ninguna noche futura sobrevendida", oversold))

    nightly, totals = [], []
    for reservation in reservations.prefetch_related("stays"):
        members = list(reservation.stays.all())
        for stay in members:
            amounts = sum((Decimal(str(night["amount"])) for night in stay.nightly_rates), ZERO)
            if amounts != stay.total_amount or len(stay.nightly_rates) != len(stay.nights):
                nightly.append((reservation.code, str(amounts), str(stay.total_amount)))
        if sum((stay.total_amount for stay in members), ZERO) != reservation.total_amount:
            totals.append(reservation.code)
    checks.append(("estadías: total = Σ nightly_rates (una por noche)", nightly))
    checks.append(("reservas: total = Σ estadías", totals))

    in_sql = dict(with_balance(reservations).values_list("pk", "balance"))
    balances, mismatch = {}, []
    for reservation in reservations:
        balances[reservation.pk] = balance = reservation_balance(reservation)
        if balance != in_sql[reservation.pk]:
            mismatch.append((reservation.code, str(balance), str(in_sql[reservation.pk])))
    checks.append(("saldos: reservation_balance = with_balance (SQL)", mismatch))
    checks.append((
        "saldos: ninguna reserva con saldo a favor",
        [(code, str(balance)) for code, balance in
         ((r.code, balances[r.pk]) for r in reservations) if balance < 0],
    ))  # fmt: skip
    closed = [
        (folio.reservation.code if folio.reservation_id else str(folio.pk), str(folio_balance(folio)))
        for folio in Folio.objects.filter(property=prop, status=Folio.Status.CLOSED).select_related(
            "reservation"
        )
        if folio_balance(folio) != 0 or balances.get(folio.reservation_id, ZERO) != 0
    ]
    checks.append(("folios: un folio cerrado no debe nada", closed))

    room_total, room_nights = defaultdict(lambda: ZERO), defaultdict(set)
    for charge in Charge.objects.filter(folio__property=prop, kind=Charge.Kind.ROOM, voided_at__isnull=True):
        room_total[charge.stay_id] += charge.amount + charge.tax_amount
        room_nights[charge.stay_id].add(charge.night_date)
    checked_out, in_house, pending = [], [], []
    for stay in stays:
        if stay.status == "checked_out" and room_total[stay.pk] != stay.total_amount:
            checked_out.append((stay.reservation.code, str(room_total[stay.pk]), str(stay.total_amount)))
        elif stay.status == "checked_in":
            expected = {night for night in stay.nights if night < today}
            if room_nights[stay.pk] != expected:
                in_house.append((stay.reservation.code, len(room_nights[stay.pk]), len(expected)))
        elif stay.status in ("tentative", "confirmed", "cancelled", "no_show") and room_nights[stay.pk]:
            pending.append((stay.reservation.code, stay.status))
    checks.append(("cargos: estadía finalizada = Σ cargos de alojamiento", checked_out))
    checks.append(("cargos: en casa, noches cobradas hasta ayer", in_house))
    checks.append(("cargos: pendientes, canceladas y no-show sin cargos de alojamiento", pending))
    fees = []
    for reservation in reservations.filter(status__in=["cancelled", "no_show"]):
        posted = (
            Charge.objects.filter(
                folio__reservation=reservation, kind=Charge.Kind.CANCELLATION_FEE, voided_at__isnull=True
            ).aggregate(total=Sum("amount"))["total"]
            or ZERO
        )
        if posted != reservation.cancellation_fee:
            fees.append((reservation.code, str(posted), str(reservation.cancellation_fee)))
    checks.append(("cargos: penalidades = cancellation_fee", fees))

    orphans = list(
        PaymentIntent.objects.filter(property=prop, status="approved", payment__isnull=True).values_list(
            "reference", flat=True
        )
    )
    checks.append(("pagos: cada link aprobado tiene su pago", orphans))
    late = [
        ("cargo", str(pk)) for pk in
        Charge.objects.filter(folio__property=prop, business_date__gt=today).values_list("pk", flat=True)
    ] + [
        ("pago", str(pk)) for pk in
        Payment.objects.filter(folio__property=prop, business_date__gt=today).values_list("pk", flat=True)
    ] + [
        ("pago creado en el futuro", str(pk)) for pk in
        Payment.objects.filter(folio__property=prop, created_at__gt=timezone.now() + timedelta(minutes=1))
        .values_list("pk", flat=True)
    ]  # fmt: skip
    checks.append(("fechas: nada fechado después de la fecha de negocio", late))
    return checks
