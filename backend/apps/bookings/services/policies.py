"""Cancellation policy snapshot and penalties (plan B2b › cancel_reservation / mark_no_show)."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.bookings.services.pricing import money_str
from apps.core.money import D, quantize
from apps.rates.models import RatePlan

ZERO = Decimal("0")


def effective_policy(rate_plan):
    """The plan's policy; a derived plan without one inherits its parent's."""
    policy = rate_plan.cancellation_policy
    if policy is None and rate_plan.kind == RatePlan.Kind.DERIVED and rate_plan.parent_id:
        policy = rate_plan.parent.cancellation_policy
    return policy


def policy_snapshot(rate_plan) -> dict:
    """Frozen copy of the policy stored in `Reservation.cancellation_policy_snapshot` ({} without policy)."""
    policy = effective_policy(rate_plan)
    if policy is None:
        return {}
    return {
        "id": str(policy.pk),
        "name": policy.name,
        "description": policy.description,
        "non_refundable": policy.non_refundable,
        "free_until_hours_before": policy.free_until_hours_before,
        "penalty_type": policy.penalty_type,
        "penalty_value": money_str(policy.penalty_value),
        "rate_plan_id": str(rate_plan.pk),
    }


@dataclass(frozen=True)
class FeeQuote:
    """Penalty that applies now. `reason`: tentative | no_policy | non_refundable | free_window |
    first_night | percent | full. `free_until`: end of the free window (aware datetime) or None."""

    amount: Decimal
    reason: str
    free_until: datetime | None
    policy: dict

    def as_dict(self, currency: str) -> dict:
        return {
            "fee": money_str(self.amount),
            "currency": currency,
            "reason": self.reason,
            "free_until": self.free_until.isoformat() if self.free_until else None,
            "non_refundable": bool(self.policy.get("non_refundable")),
            "policy": self.policy,
        }


def free_until(reservation, snapshot) -> datetime | None:
    """`checkin_date` at the property's check-in time, in its timezone, minus `free_until_hours_before`."""
    hours = snapshot.get("free_until_hours_before")
    if hours is None or snapshot.get("non_refundable"):
        return None
    prop = reservation.property
    arrival = datetime.combine(
        reservation.checkin_date,
        prop.check_in_time or time(15, 0),
        tzinfo=ZoneInfo(prop.timezone or "America/Bogota"),
    )
    return arrival - timedelta(hours=int(hours))


def cancellation_fee(reservation, *, now=None) -> FeeQuote:
    """Penalty for cancelling now, from the reservation's policy snapshot.

    Tentative reservations (never guaranteed) and reservations without policy cancel for free. Non-refundable
    → the whole stay. Otherwise free until `free_until`; after it `first_night` (the first night of every
    stay), `percent` (of the total) or `full`. Amounts include taxes (what the guest pays)."""
    snapshot = reservation.cancellation_policy_snapshot or {}
    if reservation.status == "tentative":
        return FeeQuote(ZERO, "tentative", None, snapshot)
    if not snapshot:
        return FeeQuote(ZERO, "no_policy", None, {})
    stays = _billable_stays(reservation)
    if snapshot.get("non_refundable"):
        return FeeQuote(_total(stays), "non_refundable", None, snapshot)
    deadline = free_until(reservation, snapshot)
    if deadline is not None and (now or timezone.now()) <= deadline:
        return FeeQuote(ZERO, "free_window", deadline, snapshot)
    penalty_type = snapshot.get("penalty_type") or "first_night"
    return FeeQuote(
        _penalty(penalty_type, snapshot, stays, reservation.currency), penalty_type, deadline, snapshot
    )


def no_show_fee(reservation) -> FeeQuote:
    """No-show penalty: non-refundable → the whole stay; otherwise the policy's penalty type; the first night
    when there is no policy."""
    snapshot = reservation.cancellation_policy_snapshot or {}
    stays = _billable_stays(reservation)
    if snapshot.get("non_refundable"):
        return FeeQuote(_total(stays), "non_refundable", None, snapshot)
    penalty_type = snapshot.get("penalty_type") or "first_night"
    reason = penalty_type if snapshot else "no_policy"
    return FeeQuote(_penalty(penalty_type, snapshot, stays, reservation.currency), reason, None, snapshot)


def _billable_stays(reservation) -> list:
    return list(reservation.stays.filter(status__in=["tentative", "confirmed"]))


def _total(stays) -> Decimal:
    return sum((D(stay.total_amount) for stay in stays), ZERO)


def _penalty(penalty_type, snapshot, stays, currency) -> Decimal:
    if penalty_type == "full":
        return _total(stays)
    if penalty_type == "percent":
        return quantize(_total(stays) * D(snapshot.get("penalty_value")) / 100, currency)
    return sum((first_night_amount(stay) for stay in stays), ZERO)


def first_night_amount(stay) -> Decimal:
    entries = sorted(stay.nightly_rates or [], key=lambda item: item["date"])
    if entries:
        return D(entries[0]["amount"])
    nights = max((stay.checkout_date - stay.checkin_date).days, 1)
    return D(stay.total_amount) / nights
