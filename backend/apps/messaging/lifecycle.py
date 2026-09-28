"""Automatic messages of the guest lifecycle (plan C6).

- Immediate events come from domain signals (`receivers.py`): confirmation and cancellation.
- Scheduled events run in the automation `messaging.lifecycle_dispatch` (every 10 min, from each rule's local
  send time): pre-arrival (N days before check-in, with the online check-in link), arrival day, post-stay
  (N days after check-out) and payment reminder (balance due and arrival within N days).
- One `LifecycleDispatch` per (reservation, event) makes everything idempotent; a dispatch whose channels all
  failed is retried by the automation (up to `MAX_ATTEMPTS`, for two days).
"""

import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.automation import RunResult
from apps.core.errors import DomainError
from apps.messaging.defaults import CODE_LABELS, EVENTS, SCHEDULED_EVENTS, default_rule
from apps.messaging.models import LifecycleDispatch, LifecycleRule

logger = logging.getLogger("housetel.messaging")

MAX_ATTEMPTS = 3
RETRY_WINDOW = timedelta(days=2)
POST_STAY_GRACE_DAYS = 2  # post-stay messages still go out if the automation was down for a couple of days
MAX_PER_RUN = 500


def _rule_values(row: LifecycleRule) -> dict:
    return {
        "event": row.event,
        "enabled": row.enabled,
        "days_offset": row.days_offset,
        "channels": list(row.channels or []),
        "template_code": row.template_code or row.event,
        "send_after": row.send_after,
    }


def effective_rule(property, event: str) -> dict:
    """The property's rule for `event`, or the default one (enabled) when it was never configured."""
    row = LifecycleRule.objects.filter(property=property, event=event).first()
    return _rule_values(row) if row is not None else default_rule(event)


def ensure_rules(property) -> list[LifecycleRule]:
    """The six rules of the property (missing ones created with the defaults), in lifecycle order."""
    existing = set(LifecycleRule.objects.filter(property=property).values_list("event", flat=True))
    missing = [
        LifecycleRule(property=property, **default_rule(event)) for event in EVENTS if event not in existing
    ]
    if missing:
        LifecycleRule.objects.bulk_create(missing, ignore_conflicts=True)
    return sorted(LifecycleRule.objects.filter(property=property), key=lambda rule: EVENTS.index(rule.event))


def _deliver(dispatch: LifecycleDispatch, rule: dict) -> None:
    from apps.messaging.services import send_message

    reservation = dispatch.reservation
    try:
        results = send_message(
            property=reservation.property,
            template_code=rule["template_code"],
            reservation=reservation,
            channels=tuple(rule["channels"]),
        )
    except DomainError as exc:
        dispatch.status, dispatch.detail = LifecycleDispatch.Status.FAILED, exc.message[:255]
    except Exception as exc:  # a bug must not lose the event: it is retried like a failed delivery
        logger.exception("Lifecycle %s failed for reservation %s", dispatch.event, reservation.pk)
        dispatch.status, dispatch.detail = LifecycleDispatch.Status.FAILED, str(exc)[:255]
    else:
        delivered = [r for r in results if r.status in ("sent", "delivered")]
        failed = [r for r in results if r.status == "failed"]
        if delivered and failed:
            dispatch.status = LifecycleDispatch.Status.PARTIAL
        elif delivered:
            dispatch.status = LifecycleDispatch.Status.SENT
        elif failed:
            dispatch.status = LifecycleDispatch.Status.FAILED
        else:
            dispatch.status = LifecycleDispatch.Status.SKIPPED
        dispatch.detail = "; ".join(f"{r.channel}: {r.error}" for r in results if r.error)[:255]
    dispatch.channels = list(rule["channels"])
    dispatch.save(update_fields=["status", "detail", "channels", "attempts", "updated_at"])


def dispatch_event(reservation, event: str) -> LifecycleDispatch | None:
    """Send the lifecycle message `event` of a reservation once. None when the rule is off (or has no
    channels) or the event was already dispatched."""
    rule = effective_rule(reservation.property, event)
    if not rule["enabled"] or not rule["channels"]:
        return None
    try:
        with transaction.atomic():
            dispatch = LifecycleDispatch.objects.create(
                reservation=reservation, event=event, channels=rule["channels"], attempts=1
            )
    except IntegrityError:
        return None
    _deliver(dispatch, rule)
    return dispatch


def was_dispatched(reservation, event: str) -> bool:
    return LifecycleDispatch.objects.filter(reservation=reservation, event=event).exists()


def due_reservations(property, event: str, offset: int, today) -> list:
    """Reservations whose scheduled `event` is due on the hotel's `today` and was not dispatched yet."""
    from apps.bookings.models import Reservation

    reservations = (
        Reservation.objects.filter(property=property)
        .exclude(lifecycle_dispatches__event=event)
        .select_related("property", "booker")
    )
    if event == "pre_arrival":
        reservations = reservations.filter(
            status="confirmed", checkin_date__gt=today, checkin_date__lte=today + timedelta(days=offset)
        )
    elif event == "arrival_day":
        reservations = reservations.filter(status="confirmed", checkin_date=today)
    elif event == "post_stay":
        last = today - timedelta(days=offset)
        reservations = reservations.filter(
            status="checked_out",
            checkout_date__lte=last,
            checkout_date__gte=last - timedelta(days=POST_STAY_GRACE_DAYS),
        )
    elif event == "payment_reminder":
        from apps.bookings.services.queries import with_balance

        reservations = with_balance(
            reservations.filter(
                status="confirmed", checkin_date__gte=today, checkin_date__lte=today + timedelta(days=offset)
            )
        ).filter(balance__gt=0)
    else:
        return []
    return list(reservations.order_by("checkin_date", "created_at")[:MAX_PER_RUN])


def retry_failed(property, *, now=None) -> int:
    """Send again the dispatches whose every channel failed (recent ones, a few attempts)."""
    now = now or timezone.now()
    failed = LifecycleDispatch.objects.filter(
        reservation__property=property,
        status=LifecycleDispatch.Status.FAILED,
        attempts__lt=MAX_ATTEMPTS,
        updated_at__gte=now - RETRY_WINDOW,
    ).select_related("reservation__property", "reservation__booker")
    retried = 0
    for dispatch in failed:
        if dispatch.event != "cancellation" and dispatch.reservation.status in ("cancelled", "no_show"):
            continue
        rule = effective_rule(property, dispatch.event)
        if not rule["enabled"] or not rule["channels"]:
            continue
        dispatch.attempts += 1
        _deliver(dispatch, rule)
        retried += 1
    return retried


def run_lifecycle_dispatch(property, params) -> RunResult:
    """Handler of the automation `messaging.lifecycle_dispatch`."""
    now = timezone.now()
    local = timezone.localtime(now, ZoneInfo(property.timezone or "America/Bogota"))
    sent: dict[str, int] = {}
    for event in SCHEDULED_EVENTS:
        rule = effective_rule(property, event)
        if not rule["enabled"] or not rule["channels"] or local.time() < rule["send_after"]:
            continue
        count = sum(
            1
            for reservation in due_reservations(property, event, rule["days_offset"], local.date())
            if dispatch_event(reservation, event) is not None
        )
        if count:
            sent[event] = count
    retried = retry_failed(property, now=now)
    parts = [f"{count} {CODE_LABELS[event]['es'].lower()}" for event, count in sent.items()]
    if retried:
        parts.append(f"{retried} reintentos")
    summary = ("Mensajes: " + ", ".join(parts)) if parts else "Sin mensajes pendientes"
    return RunResult(status="success", summary=summary, details={"sent": sent, "retried": retried})
