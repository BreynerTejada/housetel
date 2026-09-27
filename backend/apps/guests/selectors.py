"""Read-side queries of the CRM. They read bookings and finance through the ORM (reading other apps' models
is allowed); they never write there.

Definitions used on the guest profile (organization-wide: every property of a chain):
- reservations of a guest: the ones they booked or where they are an occupant of a stay;
- stays: reservations `checked_in` or `checked_out`; nights = Σ (checkout − checkin) of those;
- total spent: Σ (net amount + tax) of non-voided charges on folios of reservations the guest BOOKED
  (companions do not pay); in the property currency (COP);
- last stay: the stay with the latest check-in; next stay: the earliest `tentative`/`confirmed`
  reservation with check-in on or after `today`.
"""

from decimal import Decimal

from django.db.models import Exists, F, Func, IntegerField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

STAYED_STATUSES = ("checked_in", "checked_out")
UPCOMING_STATUSES = ("tentative", "confirmed")


def reservations_of(guest):
    from apps.bookings.models import Reservation

    return Reservation.objects.filter(Q(booker=guest) | Q(stays__occupants=guest)).distinct()


def _reservations_of_outer_guest():
    from apps.bookings.models import Reservation

    return Reservation.objects.filter(
        Q(booker=OuterRef("pk")) | Q(stays__occupants=OuterRef("pk"))
    ).order_by()


def _count_distinct(queryset) -> Coalesce:
    counted = queryset.annotate(
        n=Func(F("pk"), function="COUNT", template="%(function)s(DISTINCT %(expressions)s)")
    ).values("n")[:1]
    return Coalesce(Subquery(counted, output_field=IntegerField()), Value(0))


def annotate_stays(queryset):
    """List columns: `stays_count`, `reservations_count`, `last_stay_date` (check-in of the latest stay)."""
    reservations = _reservations_of_outer_guest()
    stayed = reservations.filter(status__in=STAYED_STATUSES)
    return queryset.annotate(
        stays_count=_count_distinct(stayed),
        reservations_count=_count_distinct(reservations),
        last_stay_date=Subquery(stayed.order_by("-checkin_date").values("checkin_date")[:1]),
    )


def has_stayed() -> Exists:
    """Filter expression: the guest has at least one stay (checked in or out)."""
    return Exists(_reservations_of_outer_guest().filter(status__in=STAYED_STATUSES))


def reservation_summary(reservation) -> dict:
    return {
        "reservation_id": str(reservation.pk),
        "code": reservation.code,
        "property_id": str(reservation.property_id),
        "property_name": reservation.property.name,
        "checkin": reservation.checkin_date.isoformat(),
        "checkout": reservation.checkout_date.isoformat(),
        "status": reservation.status,
    }


def total_spent(guest) -> Decimal:
    from apps.finance.models import Charge

    total = Charge.objects.filter(folio__reservation__booker=guest, voided_at__isnull=True).aggregate(
        total=Sum(F("amount") + F("tax_amount"))
    )["total"]
    return total or Decimal("0")


def guest_stats(guest, *, today=None) -> dict:
    today = today or timezone.localdate()
    reservations = list(reservations_of(guest).select_related("property"))
    stayed = [r for r in reservations if r.status in STAYED_STATUSES]
    upcoming = [r for r in reservations if r.status in UPCOMING_STATUSES and r.checkin_date >= today]
    last = max(stayed, key=lambda r: (r.checkin_date, r.code), default=None)
    following = min(upcoming, key=lambda r: (r.checkin_date, r.code), default=None)
    return {
        "reservations_count": len(reservations),
        "stays_count": len(stayed),
        "nights": sum((r.checkout_date - r.checkin_date).days for r in stayed),
        "total_spent": total_spent(guest),
        "cancellations": sum(r.status == "cancelled" for r in reservations),
        "no_shows": sum(r.status == "no_show" for r in reservations),
        "last_stay": reservation_summary(last) if last else None,
        "next_stay": reservation_summary(following) if following else None,
    }
