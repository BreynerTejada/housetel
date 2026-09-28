"""Night audit (plan C1, spec §5 C1 and §6 `frontdesk.night_audit`).

`close_business_day(property)` closes the property's business date `D`, in one transaction with the property
row locked:

1. posts the room charge of every night < D+1 still unposted of the guests in house
   (`bookings.post_room_charges(stay, until_date=D+1)`; idempotent, so a missed night is posted too);
2. moves the business date to D+1;
3. marks as no-show the confirmed reservations arriving before D+1 that never checked in
   (`bookings.mark_no_show`, which charges the policy's fee dated D+1), when
   `property.settings["auto_no_show"]` (default True); tentative ones are only listed;
4. raises the alert `frontdesk:overdue_departures` for guests still in house whose checkout was ≤ D (or
   resolves it), and `frontdesk:night_audit_errors` when a stay or reservation failed (or resolves it);
5. writes the closing report (`NightAuditReport`) with what it did and the figures of D, and audits
   `frontdesk.night_audit`.

A failing stay or reservation (a domain error such as a closed folio) does not stop the audit: it is listed in
`summary.errors` and the report is `partial`; the next audit retries it (charges and no-shows are idempotent).

One audit per date: closing a date that already has a report returns that report and changes nothing. A day
that has not started in the property's timezone cannot be closed (`audit_ahead`); the current day can be
closed early (manual run). The scheduled automation only closes days that already ended, catching up at most
`MAX_CATCH_UP_DAYS` per run. `preview_night_audit` runs the same audit in a transaction that is rolled back.
"""

from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.bookings.models import Reservation, Stay
from apps.bookings.services.charges import post_room_charges
from apps.bookings.services.reservations import mark_no_show
from apps.core import alerts, audit, automation
from apps.core.automation import RunResult
from apps.core.dates import property_now
from apps.core.errors import DomainError
from apps.core.models import AutomationRun, Property
from apps.frontdesk.models import NightAuditReport
from apps.frontdesk.services.figures import day_figures, money

CODE = "frontdesk.night_audit"
MAX_CATCH_UP_DAYS = 7
OVERDUE_ALERT = "frontdesk:overdue_departures"
ERRORS_ALERT = "frontdesk:night_audit_errors"
CLOSED = (NightAuditReport.Status.COMPLETED, NightAuditReport.Status.PARTIAL)
ZERO = Decimal("0")


class NightAuditError(DomainError):
    code = "night_audit_error"
    status_code = 409


class NightAuditFailed(DomainError):
    code = "night_audit_failed"
    status_code = 500


class _DryRun(Exception):
    def __init__(self, summary: dict):
        super().__init__("dry run")
        self.summary = summary


def audit_state(prop) -> dict:
    """Whether the current business date can be closed now, and why not (`audit_ahead`)."""
    today = property_now(prop).date()
    day = prop.business_date
    reason = "audit_ahead" if day > today else None
    return {
        "business_date": day.isoformat(),
        "next_business_date": (day + timedelta(days=1)).isoformat(),
        "calendar_date": today.isoformat(),
        "due": day < today,
        "can_run": reason is None,
        "reason": reason,
    }


def close_business_day(
    prop, *, business_date: date | None = None, actor=None, run=None, auto_no_show: bool | None = None
) -> tuple[NightAuditReport, bool]:
    """Close the business date (`business_date` defaults to the current one). Returns `(report, closed_now)`:
    `closed_now` is False when that date already had its report (nothing changes)."""
    with transaction.atomic():
        return _close(prop, business_date=business_date, actor=actor, run=run, auto_no_show=auto_no_show)


def preview_night_audit(prop) -> dict:
    """What closing the current business date would do, computed by the real audit and rolled back."""
    state = audit_state(prop)
    if not state["can_run"]:
        return {**state, "summary": None}
    try:
        with transaction.atomic():
            report, _ = _close(prop, business_date=None, actor=None, run=None, auto_no_show=None)
            raise _DryRun(report.summary)
    except _DryRun as dry:
        return {**state, "summary": dry.summary}


def run_manual(prop, *, business_date: date, actor) -> tuple[NightAuditReport, bool]:
    """Front desk button: close `business_date` through the automation (so the control center shows the run
    and who triggered it). Returns `(report, closed_now)`; a date already closed returns its report."""
    existing = _closed_report(prop, business_date)
    if existing is not None:
        return existing, False
    prop = Property.objects.get(pk=prop.pk)
    _check(prop, business_date)
    run = automation.run(
        CODE, prop, params={"mode": "manual", "business_date": business_date.isoformat()}, triggered_by=actor
    )
    report = _closed_report(prop, business_date)
    if report is None:
        raise NightAuditFailed(run.summary or "La auditoría nocturna falló")
    return report, run.status != "skipped"


def run_night_audit(prop, params: dict) -> RunResult:
    """Handler of the `frontdesk.night_audit` automation.

    - scheduled (beat, or "run now" in the control center): closes every business day that already ended in
      the property's timezone, oldest first, at most `MAX_CATCH_UP_DAYS` (`partial` if still behind);
    - `params={"mode": "manual", "business_date": "YYYY-MM-DD"}` (front desk button): closes that date if it
      is still the current one, even before it ends; already closed → `skipped` with the same report.
    """
    run = _current_run(prop)
    actor = run.triggered_by if run is not None else None
    auto = params.get("auto_no_show")
    if params.get("mode") == "manual":
        requested = date.fromisoformat(params["business_date"]) if params.get("business_date") else None
        try:
            report, closed = close_business_day(
                prop, business_date=requested, actor=actor, run=run, auto_no_show=auto
            )
        except NightAuditError as exc:
            return RunResult(status="skipped", summary=exc.message, details={"code": exc.code})
        if not closed:
            return RunResult(
                status="skipped",
                summary=f"El día {report.business_date.isoformat()} ya estaba cerrado",
                details={"report": str(report.pk), "closed": []},
            )
        prop.refresh_from_db(fields=["business_date"])  # the audit moved it on a locked copy
        return _run_result(prop, [report])
    today = property_now(prop).date()
    reports = []
    while len(reports) < MAX_CATCH_UP_DAYS:
        prop.refresh_from_db(fields=["business_date"])
        if prop.business_date >= today:
            break
        report, _ = close_business_day(prop, actor=None, run=run, auto_no_show=auto)
        reports.append(report)
    if not reports:
        return RunResult(
            status="skipped",
            summary=f"La fecha de negocio ({prop.business_date.isoformat()}) está al día",
            details={"closed": []},
        )
    prop.refresh_from_db(fields=["business_date"])
    return _run_result(prop, reports, behind=prop.business_date < today)


# --- the audit ----------------------------------------------------------------------------------------


def _close(prop, *, business_date, actor, run, auto_no_show) -> tuple[NightAuditReport, bool]:
    prop = Property.objects.select_for_update().get(pk=prop.pk)
    day = prop.business_date
    target = business_date or day
    existing = _closed_report(prop, target)
    if existing is not None:
        return existing, False
    _check(prop, target)
    if auto_no_show is None:
        auto_no_show = bool((prop.settings or {}).get("auto_no_show", True))
    user = actor if actor is not None and getattr(actor, "is_authenticated", False) else None
    source = "user" if user is not None else "automation"
    report, _ = NightAuditReport.objects.update_or_create(
        property=prop,
        business_date=day,
        defaults={
            "status": NightAuditReport.Status.RUNNING,
            "started_at": timezone.now(),
            "run": run,
            "triggered_by": user,
        },
    )
    next_day = day + timedelta(days=1)
    errors: list[dict] = []

    room_charges = _post_room_charges(prop, next_day, user, source, errors)
    prop.business_date = next_day
    prop.save(update_fields=["business_date", "updated_at"])
    no_shows = _mark_no_shows(prop, next_day, user, source, errors) if auto_no_show else []
    overdue = _overdue_departures(prop, day)
    _alert_overdue(prop, overdue, day)
    _alert_errors(prop, errors, day)

    report.summary = {
        "business_date": day.isoformat(),
        "next_business_date": next_day.isoformat(),
        "auto_no_show": auto_no_show,
        "room_charges": room_charges,
        "no_shows": no_shows,
        "no_show_fees": money(sum((Decimal(item["fee"]) for item in no_shows), ZERO)),
        "overdue_departures": overdue,
        "pending_tentative": _pending_tentative(prop, next_day),
        "errors": errors,
        "activity": _activity(prop, day, len(no_shows)),
        "figures": day_figures(prop, day),
    }
    report.status = NightAuditReport.Status.PARTIAL if errors else NightAuditReport.Status.COMPLETED
    report.finished_at = timezone.now()
    report.save()
    audit.record(
        action="frontdesk.night_audit",
        target=report,
        summary=(
            f"Auditoría nocturna del {day.isoformat()}: {room_charges['nights']} noches publicadas, "
            f"{len(no_shows)} no-shows" + (f", {len(errors)} errores" if errors else "")
        ),
        actor=user,
        source=source,
        property=prop,
        changes={"business_date": [day.isoformat(), next_day.isoformat()]},
    )
    return report, True


def _closed_report(prop, day: date) -> NightAuditReport | None:
    return NightAuditReport.objects.filter(property=prop, business_date=day, status__in=CLOSED).first()


def _check(prop, target: date) -> None:
    """`target` must be the current business date, and that day must have started in the property's zone."""
    day = prop.business_date
    if target != day:
        raise NightAuditError(
            f"La fecha de negocio ya no es el {target.isoformat()}: ahora es el {day.isoformat()}",
            code="business_date_changed",
            business_date=day.isoformat(),
        )
    today = property_now(prop).date()
    if day > today:
        raise NightAuditError(
            f"El día {day.isoformat()} todavía no ha empezado: no se puede cerrar",
            code="audit_ahead",
            business_date=day.isoformat(),
            calendar_date=today.isoformat(),
        )


def _post_room_charges(prop, until: date, actor, source, errors) -> dict:
    stays = (
        Stay.objects.filter(reservation__property=prop, status="checked_in")
        .select_related("reservation")
        .order_by("checkin_date", "created_at")
    )
    posted, charged = [], 0
    for stay in stays:
        try:
            with transaction.atomic():
                charges = post_room_charges(stay, until_date=until, actor=actor, source=source)
        except DomainError as exc:
            errors.append(_error("room_charges", stay.reservation, exc, stay_id=str(stay.pk)))
            continue
        if charges:
            charged += 1
            posted.extend(charges)
    net = sum((charge.amount for charge in posted), ZERO)
    tax = sum((charge.tax_amount for charge in posted), ZERO)
    return {
        "stays": charged,
        "nights": len(posted),
        "net": money(net),
        "tax": money(tax),
        "total": money(net + tax),
    }


def _mark_no_shows(prop, next_day: date, actor, source, errors) -> list[dict]:
    reservations = (
        Reservation.objects.filter(property=prop, status="confirmed", checkin_date__lt=next_day)
        .select_related("booker")
        .order_by("checkin_date", "code")
    )
    marked = []
    for reservation in reservations:
        try:
            with transaction.atomic():
                done = mark_no_show(reservation, actor=actor, source=source)
        except DomainError as exc:
            errors.append(_error("no_show", reservation, exc))
            continue
        marked.append(
            {
                "reservation_id": str(reservation.pk),
                "code": reservation.code,
                "guest_name": reservation.booker.full_name,
                "checkin": reservation.checkin_date.isoformat(),
                "fee": money(done.cancellation_fee),
            }
        )
    return marked


def _overdue_departures(prop, day: date) -> list[dict]:
    stays = (
        Stay.objects.filter(reservation__property=prop, status="checked_in", checkout_date__lte=day)
        .select_related("reservation__booker", "room", "bed")
        .order_by("checkout_date", "created_at")
    )
    return [
        {
            "stay_id": str(stay.pk),
            "reservation_id": str(stay.reservation_id),
            "code": stay.reservation.code,
            "guest_name": stay.reservation.booker.full_name,
            "room": stay.room.number if stay.room_id else None,
            "bed": stay.bed.label if stay.bed_id else None,
            "checkout": stay.checkout_date.isoformat(),
        }
        for stay in stays
    ]


def _pending_tentative(prop, next_day: date) -> list[dict]:
    reservations = (
        Reservation.objects.filter(property=prop, status="tentative", checkin_date__lt=next_day)
        .select_related("booker")
        .order_by("checkin_date", "code")
    )
    return [
        {
            "reservation_id": str(reservation.pk),
            "code": reservation.code,
            "guest_name": reservation.booker.full_name,
            "checkin": reservation.checkin_date.isoformat(),
            "hold_expires_at": reservation.hold_expires_at.isoformat()
            if reservation.hold_expires_at
            else None,
        }
        for reservation in reservations
    ]


def _activity(prop, day: date, no_shows: int) -> dict:
    stays = Stay.objects.filter(reservation__property=prop)
    return {
        "arrivals": stays.filter(checkin_date=day, status__in=["checked_in", "checked_out"]).count(),
        "departures": stays.filter(checkout_date=day, status="checked_out").count(),
        "in_house": stays.filter(status="checked_in").count(),
        "cancellations": Reservation.objects.filter(
            property=prop, status="cancelled", cancelled_at__date=day
        ).count(),
        "no_shows": no_shows,
    }


def _alert_overdue(prop, overdue: list[dict], day: date) -> None:
    if not overdue:
        alerts.resolve_alert(prop, OVERDUE_ALERT)
        return
    count = len(overdue)
    codes = ", ".join(item["code"] for item in overdue)
    alerts.raise_alert(
        property=prop,
        kind="overdue_departures",
        severity="warning",
        title=f"{count} huésped(es) debían salir y siguen en casa",
        message=f"Haz el check-out o extiende la estadía: {codes}.",
        link="/app",
        dedupe_key=OVERDUE_ALERT,
        data={
            "business_date": day.isoformat(),
            "stays": [item["stay_id"] for item in overdue],
            "reservations": [item["code"] for item in overdue],
        },
        source="automation",
    )


def _alert_errors(prop, errors: list[dict], day: date) -> None:
    if not errors:
        alerts.resolve_alert(prop, ERRORS_ALERT)
        return
    alerts.raise_alert(
        property=prop,
        kind="night_audit_errors",
        severity="warning",
        title=f"La auditoría nocturna del {day.isoformat()} dejó {len(errors)} pendiente(s)",
        message="; ".join(f"{item['code']}: {item['error']}" for item in errors)[:2000],
        link="/app/night-audit",
        dedupe_key=ERRORS_ALERT,
        data={"business_date": day.isoformat(), "errors": errors},
        source="automation",
    )


def _error(step: str, reservation, exc: DomainError, **extra) -> dict:
    return {
        "step": step,
        "reservation_id": str(reservation.pk),
        "code": reservation.code,
        "error_code": exc.code,
        "error": exc.message,
        **extra,
    }


# --- automation helpers -------------------------------------------------------------------------------


def _current_run(prop) -> AutomationRun | None:
    """The `AutomationRun` that `automation.run` opened just before calling the handler."""
    return (
        AutomationRun.objects.filter(property=prop, code=CODE, status=AutomationRun.Status.RUNNING)
        .select_related("triggered_by")
        .order_by("-started_at")
        .first()
    )


def _run_result(prop, reports: list[NightAuditReport], *, behind: bool = False) -> RunResult:
    closed = [report.business_date.isoformat() for report in reports]
    partial = behind or any(report.status == NightAuditReport.Status.PARTIAL for report in reports)
    no_shows = sum(len(report.summary.get("no_shows", [])) for report in reports)
    nights = sum(report.summary.get("room_charges", {}).get("nights", 0) for report in reports)
    errors = sum(len(report.summary.get("errors", [])) for report in reports)
    summary = (
        f"{len(reports)} día(s) cerrado(s) ({', '.join(closed)}): {nights} noches publicadas, "
        f"{no_shows} no-shows; fecha de negocio {prop.business_date.isoformat()}"
    )
    if behind:
        summary += " (aún quedan días por cerrar)"
    return RunResult(
        status="partial" if partial else "success",
        summary=summary,
        details={
            "closed": closed,
            "reports": [str(report.pk) for report in reports],
            "business_date": prop.business_date.isoformat(),
            "no_shows": no_shows,
            "room_nights": nights,
            "errors": errors,
        },
    )
