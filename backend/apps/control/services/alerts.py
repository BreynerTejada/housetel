"""Alert center of a property (plan C12) over `core.Alert`: list with filters, counters for the topbar bell,
resolve one or many (audited). Platform alerts (property null) are not shown to hotel staff."""

from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, QuerySet, Value, When
from django.utils import timezone

from apps.control.services.scrub import scrub
from apps.core import audit
from apps.core.errors import DomainError, NotFoundError
from apps.core.models import Alert

SEVERITY_RANK = Case(
    When(severity=Alert.Severity.CRITICAL, then=Value(3)),
    When(severity=Alert.Severity.WARNING, then=Value(2)),
    default=Value(1),
    output_field=IntegerField(),
)
LATEST = 6
MAX_BULK = 200


def scoped(property) -> QuerySet:
    return Alert.objects.filter(property=property)


def filtered(property, params) -> QuerySet:
    """status=open (default) | resolved | all · severity (comma list) · kind · q (title/message)."""
    qs = scoped(property).select_related("resolved_by").annotate(rank=SEVERITY_RANK)
    status = params.get("status") or "open"
    if status == "open":
        qs = qs.filter(resolved_at__isnull=True).order_by("-rank", "-updated_at", "-id")
    elif status == "resolved":
        qs = qs.filter(resolved_at__isnull=False).order_by("-resolved_at", "-id")
    elif status == "all":
        qs = qs.order_by("resolved_at", "-rank", "-updated_at", "-id")
    else:
        raise DomainError(
            "Estado inválido", code="validation_error", fields={"status": ["Usa open, resolved o all"]}
        )
    if value := params.get("severity"):
        qs = qs.filter(severity__in=[item for item in str(value).split(",") if item])
    if value := params.get("kind"):
        qs = qs.filter(kind=value)
    if value := (params.get("q") or "").strip():
        qs = qs.filter(Q(title__icontains=value) | Q(message__icontains=value))
    return qs


def _user_ref(user) -> dict | None:
    if user is None:
        return None
    return {"id": str(user.pk), "email": user.email, "name": user.full_name or user.email}


def serialize(alert) -> dict:
    link = alert.link or ""
    return {
        "id": str(alert.pk),
        "kind": alert.kind,
        "severity": alert.severity,
        "title": alert.title,
        "message": alert.message,
        "link": link if link.startswith("/") else "",
        "source": alert.source,
        "data": scrub(alert.data or {}),
        "created_at": alert.created_at,
        "updated_at": alert.updated_at,
        "resolved_at": alert.resolved_at,
        "resolved_by": _user_ref(alert.resolved_by),
    }


def counts(property) -> dict:
    """Open alerts by severity + the latest open ones (the topbar bell polls this every minute)."""
    open_alerts = scoped(property).filter(resolved_at__isnull=True)
    totals = open_alerts.aggregate(
        total=Count("id"),
        critical=Count("id", filter=Q(severity=Alert.Severity.CRITICAL)),
        warning=Count("id", filter=Q(severity=Alert.Severity.WARNING)),
        info=Count("id", filter=Q(severity=Alert.Severity.INFO)),
    )
    latest = (
        open_alerts.select_related("resolved_by")
        .annotate(rank=SEVERITY_RANK)
        .order_by("-rank", "-updated_at")
    )
    return {
        "open": totals["total"],
        "by_severity": {key: totals[key] for key in ("critical", "warning", "info")},
        "latest": [serialize(alert) for alert in latest[:LATEST]],
    }


def get(property, pk) -> Alert:
    alert = scoped(property).select_related("resolved_by").filter(pk=pk).first()
    if alert is None:
        raise NotFoundError("Alerta no encontrada")
    return alert


def resolve(property, pk, *, actor) -> dict:
    """Idempotent: resolving a resolved alert returns it unchanged."""
    with transaction.atomic():
        alert = get(property, pk)
        alert = Alert.objects.select_for_update(of=("self",)).select_related("resolved_by").get(pk=alert.pk)
        if alert.resolved_at is None:
            alert.resolved_at = timezone.now()
            alert.resolved_by = actor
            alert.save(update_fields=["resolved_at", "resolved_by", "updated_at"])
            _audit(alert, actor, property)
    return serialize(alert)


def resolve_many(property, ids, *, actor) -> dict:
    if not isinstance(ids, list) or not ids:
        raise DomainError(
            "Indica las alertas a resolver", code="validation_error", fields={"ids": ["Obligatorio"]}
        )
    if len(ids) > MAX_BULK:
        raise DomainError(
            f"Máximo {MAX_BULK} alertas por vez", code="validation_error", fields={"ids": ["Demasiadas"]}
        )
    resolved = 0
    with transaction.atomic():
        alerts = list(
            scoped(property)
            .select_for_update()
            .filter(pk__in=[str(item) for item in ids], resolved_at__isnull=True)
        )
        now = timezone.now()
        for alert in alerts:
            alert.resolved_at = now
            alert.resolved_by = actor
            alert.save(update_fields=["resolved_at", "resolved_by", "updated_at"])
            _audit(alert, actor, property)
            resolved += 1
    return {"resolved": resolved}


def _audit(alert, actor, property) -> None:
    audit.record(
        action="control.alert_resolved",
        target=alert,
        summary=f"Resolvió la alerta «{alert.title}»",
        actor=actor,
        property=property,
        changes={"kind": alert.kind, "severity": alert.severity},
    )
