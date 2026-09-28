"""DIAN numbering: consecutive numbers from the active `InvoiceResolution`, handed out atomically.

The resolution row is locked with `select_for_update()` for the few statements that read and bump
`current_number`, so two concurrent issues never get the same number (the caller's transaction keeps the
lock until it commits). Problems raise `NumberingError` and a critical alert; a range that is running out
(≥ 90 % used) or about to expire (< 30 days) raises a warning. Both share the dedupe key
`compliance:resolution:<kind>` and a healthy assignment resolves it.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import IntegrityError, transaction

from apps.compliance.models import InvoiceResolution
from apps.core import alerts
from apps.core.errors import DomainError

NEAR_EXHAUSTION_RATIO = 0.9
NEAR_EXPIRY_DAYS = 30
DEFAULT_CREDIT_NOTE_PREFIX = "NC"


class NumberingError(DomainError):
    code = "numbering_error"
    status_code = 409


@dataclass
class _Failure:
    code: str
    message: str
    extra: dict = field(default_factory=dict)


def alert_key(kind: str) -> str:
    return f"compliance:resolution:{kind}"


def assign_number(property, kind: str, *, on_date: date) -> tuple[InvoiceResolution, int]:
    """Next number of the active resolution of `kind` ("invoice" | "credit_note") for a document dated
    `on_date`. Credit notes get a default internal range ("NC") when none is configured."""
    failure = None
    number = None
    with transaction.atomic():
        resolution = _locked_active(property, kind, on_date)
        if resolution is None:
            failure = _Failure(
                "no_active_resolution",
                "No hay una resolución de facturación activa: configúrala en Facturación y reportes legales",
            )
        else:
            failure = _validate(resolution, on_date)
            if failure is None:
                number = resolution.next_number
                resolution.current_number = number
                resolution.save(update_fields=["current_number", "updated_at"])
    if failure is not None:
        extra = {**failure.extra, "kind": kind, "resolution_id": str(resolution.pk) if resolution else None}
        error = NumberingError(failure.message, code=failure.code, **extra)
        raise_failure_alert(property, error)
        raise error
    _check_runway(property, kind, resolution, number, on_date)
    return resolution, number


def _locked_active(property, kind, on_date):
    queryset = InvoiceResolution.objects.select_for_update().filter(
        property=property, document_kind=kind, is_active=True
    )
    resolution = queryset.first()
    if resolution is None and kind == InvoiceResolution.DocumentKind.CREDIT_NOTE:
        resolution = _default_credit_note_range(property, on_date) or queryset.first()
    return resolution


def _default_credit_note_range(property, on_date):
    """Credit notes need their own consecutive numbering but no DIAN authorization: an internal range."""
    invoice_range = InvoiceResolution.objects.filter(
        property=property, document_kind=InvoiceResolution.DocumentKind.INVOICE, is_active=True
    ).first()
    try:
        with transaction.atomic():
            return InvoiceResolution.objects.create(
                property=property,
                document_kind=InvoiceResolution.DocumentKind.CREDIT_NOTE,
                prefix=DEFAULT_CREDIT_NOTE_PREFIX,
                from_number=1,
                to_number=99_999_999,
                valid_from=on_date.replace(month=1, day=1),
                valid_to=on_date.replace(month=1, day=1) + timedelta(days=3652),
                environment=invoice_range.environment
                if invoice_range
                else InvoiceResolution.Environment.TEST,
                technical_key=invoice_range.technical_key if invoice_range else "",
            )
    except IntegrityError:  # created concurrently: use that one
        return None


def _validate(resolution, on_date):
    if on_date < resolution.valid_from:
        return _Failure(
            "resolution_not_valid_yet",
            f"La resolución {resolution.prefix} rige desde el {resolution.valid_from:%d/%m/%Y}",
            {"valid_from": resolution.valid_from},
        )
    if on_date > resolution.valid_to:
        return _Failure(
            "resolution_expired",
            f"La resolución {resolution.prefix} venció el {resolution.valid_to:%d/%m/%Y}",
            {"valid_to": resolution.valid_to},
        )
    if resolution.next_number > resolution.to_number:
        return _Failure(
            "resolution_exhausted",
            f"Se agotó el rango de numeración {resolution.prefix} "
            f"{resolution.from_number}–{resolution.to_number}",
            {"to_number": resolution.to_number},
        )
    return None


def raise_failure_alert(property, error: NumberingError) -> None:
    """Critical alert for a numbering failure. Callers that roll back their transaction (and with it the alert
    raised inside `assign_number`) call it again after the rollback so the alert stays."""
    kind = error.extra.get("kind", InvoiceResolution.DocumentKind.INVOICE)
    alerts.raise_alert(
        property=property,
        kind="invoice_resolution",
        severity="critical",
        title="No se pueden numerar facturas electrónicas",
        message=error.message,
        link="/app/settings/compliance",
        dedupe_key=alert_key(kind),
        data={"code": error.code, "resolution_id": error.extra.get("resolution_id")},
        source="compliance",
    )


def _check_runway(property, kind, resolution, number, on_date):
    total = resolution.to_number - resolution.from_number + 1
    used = number - resolution.from_number + 1
    remaining = resolution.to_number - number
    days_left = (resolution.valid_to - on_date).days
    running_out = used / total >= NEAR_EXHAUSTION_RATIO
    expiring = days_left < NEAR_EXPIRY_DAYS
    if not (running_out or expiring):
        alerts.resolve_alert(property, alert_key(kind))
        return
    reasons = []
    if running_out:
        reasons.append(f"quedan {remaining} números de {total}")
    if expiring:
        reasons.append(f"vence en {days_left} días ({resolution.valid_to:%d/%m/%Y})")
    alerts.raise_alert(
        property=property,
        kind="invoice_resolution",
        severity="warning",
        title=f"La resolución de facturación {resolution.prefix} requiere atención",
        message="La resolución " + " y ".join(reasons) + ". Solicita una nueva a la DIAN.",
        link="/app/settings/compliance",
        dedupe_key=alert_key(kind),
        data={
            "resolution_id": str(resolution.pk),
            "remaining": remaining,
            "days_left": days_left,
            "used_percent": round(used * 100 / total, 1),
        },
        source="compliance",
    )
