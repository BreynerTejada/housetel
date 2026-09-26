import pytest
from django.db import IntegrityError, transaction

from apps.core.alerts import raise_alert, resolve_alert
from apps.core.models import Alert
from apps.core.tests.factories import PropertyFactory

pytestmark = pytest.mark.django_db


def _raise(prop, dedupe_key="overbooking:2026-10-01", **overrides):
    values = {
        "kind": "overbooking",
        "severity": "critical",
        "title": "Sobreventa",
        "message": "2 reservas de más",
    }
    values.update(overrides)
    return raise_alert(property=prop, dedupe_key=dedupe_key, **values)


def test_raise_alert_creates_an_open_alert(prop):
    alert = _raise(prop, link="/app/calendar", data={"extra": 2})
    assert (alert.kind, alert.severity, alert.source, alert.resolved_at) == (
        "overbooking",
        "critical",
        "system",
        None,
    )
    assert (alert.link, alert.data) == ("/app/calendar", {"extra": 2})


def test_same_dedupe_key_updates_the_open_alert_instead_of_duplicating(prop):
    first = _raise(prop, title="Sobreventa A")
    second = _raise(prop, title="Sobreventa B", severity="warning")
    assert second.pk == first.pk
    assert Alert.objects.filter(property=prop).count() == 1
    first.refresh_from_db()
    assert (first.title, first.severity) == ("Sobreventa B", "warning")


def test_resolve_alert_closes_open_alerts_and_returns_how_many(prop, owner):
    _raise(prop, dedupe_key="k")
    assert resolve_alert(prop, "k", actor=owner) == 1
    alert = Alert.objects.get(property=prop)
    assert alert.resolved_at is not None and alert.resolved_by == owner
    assert resolve_alert(prop, "k") == 0


def test_a_resolved_alert_is_raised_again_as_a_new_alert(prop):
    _raise(prop, dedupe_key="k")
    resolve_alert(prop, "k")
    _raise(prop, dedupe_key="k")
    assert Alert.objects.filter(property=prop).count() == 2
    assert Alert.objects.filter(property=prop, resolved_at__isnull=True).count() == 1


def test_dedupe_is_per_property(organization):
    a, b = PropertyFactory.create_batch(2, organization=organization)
    _raise(a, dedupe_key="k")
    _raise(b, dedupe_key="k")
    assert Alert.objects.count() == 2


def test_platform_alerts_without_property_are_deduplicated_too():
    _raise(None, dedupe_key="saas:billing")
    _raise(None, dedupe_key="saas:billing")
    assert Alert.objects.filter(property__isnull=True).count() == 1


def test_database_forbids_two_open_alerts_with_the_same_key(prop):
    Alert.objects.create(property=prop, kind="x", title="t", dedupe_key="k")
    with pytest.raises(IntegrityError), transaction.atomic():
        Alert.objects.create(property=prop, kind="x", title="t", dedupe_key="k")


def test_unknown_severity_is_rejected(prop):
    with pytest.raises(ValueError):
        _raise(prop, severity="urgent")
