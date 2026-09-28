"""Read-side helpers for lists, filters and the calendar."""

# Same rule as finance.reservation_balance (contract): stays owed = every status but cancelled / no-show.
BILLABLE_STAY_STATUSES = ["tentative", "confirmed", "checked_in", "checked_out"]


def with_balance(queryset):
    """Annotate `balance` = what the guest owes on the reservation, in SQL — exactly
    `finance.services.reservation_balance`: Σ billable stay totals + non-room charges (net + tax, not voided)
    − approved payments + approved refunds, minus the part billed to a company with credit (its company folio
    and, when the lodging is routed to it, the lodging not posted yet). Since the pilot plan (P4 corporate
    billing, applied by P3) the SQL lives in `finance.balances.annotate_reservation_balance`, so lists, Today,
    groups, reports and `check_integrity` agree with the folio."""
    from apps.finance.balances import annotate_reservation_balance

    return annotate_reservation_balance(queryset)
