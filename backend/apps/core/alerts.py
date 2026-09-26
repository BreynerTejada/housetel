"""Operational alerts with de-duplication: one open alert per (property, dedupe_key)."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.models import Alert

SEVERITIES = frozenset(Alert.Severity.values)


def raise_alert(
    *, property, kind, severity, title, message, link="", dedupe_key, data=None, source="system"
) -> Alert:
    """Create the alert, or update the open one with the same dedupe_key (property None = platform)."""
    if severity not in SEVERITIES:
        raise ValueError(f"Severidad inválida: {severity}")
    values = {
        "kind": kind,
        "severity": severity,
        "title": title[:200],
        "message": message,
        "link": link,
        "data": data or {},
        "source": source,
    }
    while True:
        alert = Alert.objects.filter(
            property=property, dedupe_key=dedupe_key, resolved_at__isnull=True
        ).first()
        if alert is not None:
            for field, value in values.items():
                setattr(alert, field, value)
            alert.save()
            return alert
        try:
            with transaction.atomic():
                return Alert.objects.create(property=property, dedupe_key=dedupe_key, **values)
        except IntegrityError:
            continue  # created concurrently: loop and update it


def resolve_alert(property, dedupe_key, *, actor=None) -> int:
    now = timezone.now()
    return Alert.objects.filter(property=property, dedupe_key=dedupe_key, resolved_at__isnull=True).update(
        resolved_at=now, resolved_by=actor, updated_at=now
    )
