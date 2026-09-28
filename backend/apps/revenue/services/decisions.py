"""Decisions on recommendations: approve (and apply), reject, apply (pending or approved ones).

Applying writes the base plan's grid through the rates contract
`set_daily_rates(source="revenue", actor=...)`, grouping the contiguous nights of a category and plan that
share the same recommended price into one write (one reversible `rates.bulk_update` audit event each; with
no actor its source is "automation"). A write that fails leaves its recommendations `approved` with the error
in `apply_error` (a human approval) or `pending` (auto-apply); `apply` retries them. Recommendations of
nights before the business date expire instead of being applied. Only recommendations of the given property
are touched (others are reported as `not_found`).
"""

from dataclasses import dataclass, field
from datetime import timedelta
from itertools import groupby

from django.db import transaction
from django.utils import timezone

from apps.core import audit
from apps.core.errors import DomainError
from apps.rates.services.quote import set_daily_rates
from apps.revenue.models import RateRecommendation

Status = RateRecommendation.Status
DECISION_FIELDS = ["status", "decided_by", "decided_at", "applied_at", "apply_error", "updated_at"]


@dataclass
class DecisionResult:
    recommendations: list = field(default_factory=list)  # the ones whose status changed
    skipped: list = field(default_factory=list)  # [{"id", "reason": not_found | not_pending | expired}]
    errors: list = field(default_factory=list)  # [{"id", "code", "detail"}]: approved but not written


def approve(property, ids, *, actor) -> DecisionResult:
    return _decide(property, ids, actor=actor, allowed=(Status.PENDING,), action="approved")


def apply(property, ids, *, actor) -> DecisionResult:
    return _decide(property, ids, actor=actor, allowed=(Status.PENDING, Status.APPROVED), action="approved")


def reject(property, ids, *, actor) -> DecisionResult:
    return _decide(property, ids, actor=actor, allowed=(Status.PENDING,), action="rejected")


def _decide(property, ids, *, actor, allowed, action) -> DecisionResult:
    result = DecisionResult()
    now = timezone.now()
    user = actor if getattr(actor, "is_authenticated", False) else None
    wanted = list(dict.fromkeys(str(value) for value in ids))
    with transaction.atomic():
        found = {
            str(rec.pk): rec
            for rec in RateRecommendation.objects.select_for_update()
            .select_related("room_type", "rate_plan")
            .filter(property=property, pk__in=wanted)
        }
        chosen, expired = [], []
        for rec_id in wanted:
            rec = found.get(rec_id)
            if rec is None:
                result.skipped.append({"id": rec_id, "reason": "not_found"})
            elif rec.status not in allowed:
                result.skipped.append({"id": rec_id, "reason": "not_pending"})
            elif rec.date < property.business_date:
                rec.status, rec.updated_at = Status.EXPIRED, now
                expired.append(rec)
                result.skipped.append({"id": rec_id, "reason": "expired"})
            else:
                if rec.status == Status.PENDING:
                    rec.decided_by, rec.decided_at = user, now
                rec.status = Status.REJECTED if action == "rejected" else Status.APPROVED
                rec.updated_at = now
                chosen.append(rec)
        if action == "approved" and chosen:
            result.errors = write_rates(property, chosen, actor=user, status=Status.APPLIED, now=now)
        RateRecommendation.objects.bulk_update([*chosen, *expired], DECISION_FIELDS)
        result.recommendations = chosen
        if chosen:
            audit.record(
                action=f"revenue.recommendations_{action}",
                property=property,
                actor=user,
                summary=_summary(action, chosen),
                changes={
                    "count": len(chosen),
                    "ids": [str(rec.pk) for rec in chosen],
                    "errors": len(result.errors),
                    "start": min(rec.date for rec in chosen).isoformat(),
                    "end": (max(rec.date for rec in chosen) + timedelta(days=1)).isoformat(),
                },
            )
    return result


def write_rates(property, recommendations, *, actor, status, now=None) -> list[dict]:
    """Write the recommended prices (see the module docstring); marks the written ones with `status` and
    returns the errors of the groups that could not be written. Does not save the recommendations."""
    now = now or timezone.now()
    errors = []
    ordered = sorted(
        recommendations, key=lambda rec: (str(rec.room_type_id), str(rec.rate_plan_id), rec.date)
    )
    for group in _contiguous_groups(ordered):
        first, last = group[0], group[-1]
        try:
            with transaction.atomic():
                set_daily_rates(
                    property=property,
                    room_type=first.room_type,
                    rate_plan=first.rate_plan,
                    start=first.date,
                    end=last.date + timedelta(days=1),
                    price=first.recommended_price,
                    source="revenue",
                    actor=actor,
                )
        except DomainError as exc:
            for rec in group:
                rec.apply_error = exc.message[:300]
                errors.append({"id": str(rec.pk), "code": exc.code, "detail": exc.message})
            continue
        for rec in group:
            rec.status, rec.applied_at, rec.apply_error, rec.updated_at = status, now, "", now
    return errors


def _contiguous_groups(ordered):
    """Runs of consecutive nights of the same category and plan with the same recommended price."""
    for _, same_key in groupby(ordered, key=lambda rec: (rec.room_type_id, rec.rate_plan_id)):
        group = []
        for rec in same_key:
            if group and (
                rec.date != group[-1].date + timedelta(days=1)
                or rec.recommended_price != group[-1].recommended_price
            ):
                yield group
                group = []
            group.append(rec)
        if group:
            yield group


def _summary(action, recommendations) -> str:
    verb = "aprobadas y aplicadas" if action == "approved" else "rechazadas"
    return f"{len(recommendations)} recomendaciones de precio {verb}"
