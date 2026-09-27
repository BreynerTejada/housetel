"""Read-side helpers for lists, filters and the calendar."""

from decimal import Decimal

from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.bookings.models import Stay

# Same rule as finance.reservation_balance (contract): stays owed = every status but cancelled / no-show.
BILLABLE_STAY_STATUSES = ["tentative", "confirmed", "checked_in", "checked_out"]
MONEY = DecimalField(max_digits=14, decimal_places=2)


def with_balance(queryset):
    """Annotate `balance` = Σ billable stay totals + non-room charges (net + tax, not voided) − approved
    payments + approved refunds, in SQL. Mirrors `finance.services.reservation_balance` (a test keeps both
    in sync)."""
    from apps.finance.models import Charge, Payment, Refund

    zero = Value(Decimal("0"), output_field=MONEY)

    def total(model_queryset, group_by, expression):
        return Coalesce(
            Subquery(
                model_queryset.values(group_by)
                .annotate(total=Sum(expression, output_field=MONEY))
                .values("total")
            ),
            zero,
            output_field=MONEY,
        )

    stays = total(
        Stay.objects.filter(reservation=OuterRef("pk"), status__in=BILLABLE_STAY_STATUSES),
        "reservation",
        F("total_amount"),
    )
    charges = total(
        Charge.objects.filter(folio__reservation=OuterRef("pk"), voided_at__isnull=True).exclude(kind="room"),
        "folio__reservation",
        F("amount") + F("tax_amount"),
    )
    payments = total(
        Payment.objects.filter(folio__reservation=OuterRef("pk"), status="approved"),
        "folio__reservation",
        F("amount"),
    )
    refunds = total(
        Refund.objects.filter(payment__folio__reservation=OuterRef("pk"), status="approved"),
        "payment__folio__reservation",
        F("amount"),
    )
    return queryset.annotate(balance=stays + charges - payments + refunds)
