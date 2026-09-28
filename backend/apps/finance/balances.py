"""SQL version of `finance.services.reservation_balance` with the P4 rule, for lists.

`annotate_reservation_balance(queryset)` annotates `balance` = the whole reservation (billable stay totals +
non-room charges − approved payments + approved refunds, every folio) minus the part of the companies **with
credit**: their company folios' balances plus, when the reservation's lodging is routed to such a company, the
lodging not posted yet. It is exactly `services.reservation_balance` in one query.

`bookings.services.queries.with_balance` (owner: bookings) mirrors the old rule; P-INT replaces its body with
`return annotate_reservation_balance(queryset)` so lists, reports and `check_integrity` agree with the folio.
"""

from decimal import Decimal

from django.db.models import Case, DecimalField, Exists, F, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce

MONEY = DecimalField(max_digits=14, decimal_places=2)
BILLABLE_STAY_STATUSES = ["tentative", "confirmed", "checked_in", "checked_out"]


def _total(model_queryset, group_by, expression):
    return Coalesce(
        Subquery(
            model_queryset.order_by()
            .values(group_by)
            .annotate(total=Sum(expression, output_field=MONEY))
            .values("total")[:1]
        ),
        Value(Decimal("0"), output_field=MONEY),
        output_field=MONEY,
    )


def annotate_reservation_balance(queryset, *, name: str = "balance"):
    from apps.bookings.models import Stay
    from apps.corporate.models import ReservationBilling
    from apps.finance.models import Charge, Payment, Refund

    stays = _total(
        Stay.objects.filter(reservation=OuterRef("pk"), status__in=BILLABLE_STAY_STATUSES),
        "reservation",
        F("total_amount"),
    )
    other_charges = _total(
        Charge.objects.filter(folio__reservation=OuterRef("pk"), voided_at__isnull=True).exclude(kind="room"),
        "folio__reservation",
        F("amount") + F("tax_amount"),
    )
    room_charges = _total(
        Charge.objects.filter(folio__reservation=OuterRef("pk"), voided_at__isnull=True, kind="room"),
        "folio__reservation",
        F("amount") + F("tax_amount"),
    )
    payments = _total(
        Payment.objects.filter(folio__reservation=OuterRef("pk"), status="approved"),
        "folio__reservation",
        F("amount"),
    )
    refunds = _total(
        Refund.objects.filter(payment__folio__reservation=OuterRef("pk"), status="approved"),
        "payment__folio__reservation",
        F("amount"),
    )
    credit_folio = {"folio_type": "company", "company__credit_enabled": True}
    credit_charges = _total(
        Charge.objects.filter(
            folio__reservation=OuterRef("pk"),
            voided_at__isnull=True,
            **{f"folio__{key}": value for key, value in credit_folio.items()},
        ),
        "folio__reservation",
        F("amount") + F("tax_amount"),
    )
    credit_payments = _total(
        Payment.objects.filter(
            folio__reservation=OuterRef("pk"),
            status="approved",
            **{f"folio__{key}": value for key, value in credit_folio.items()},
        ),
        "folio__reservation",
        F("amount"),
    )
    credit_refunds = _total(
        Refund.objects.filter(
            payment__folio__reservation=OuterRef("pk"),
            status="approved",
            **{f"payment__folio__{key}": value for key, value in credit_folio.items()},
        ),
        "payment__folio__reservation",
        F("amount"),
    )
    lodging_on_credit = Exists(
        ReservationBilling.objects.filter(
            reservation=OuterRef("pk"), bill_to="company", company__credit_enabled=True
        ).filter(Q(routing__contains=["lodging"]) | Q(routing__contains=["all"]))
    )
    unposted = Case(
        When(lodging_on_credit, then=stays - room_charges),
        default=Value(Decimal("0"), output_field=MONEY),
        output_field=MONEY,
    )
    total = stays + other_charges - payments + refunds
    credit_part = credit_charges - credit_payments + credit_refunds + unposted
    return queryset.annotate(**{name: total - credit_part})
