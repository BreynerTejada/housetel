"""DIAN numbering: consecutive, atomic, inside the authorized range and validity window."""

import threading
import time
from datetime import timedelta

import pytest
from django.db import connection, transaction

from apps.compliance.models import InvoiceResolution
from apps.compliance.services.numbering import NumberingError, assign_number
from apps.compliance.tests.factories import InvoiceResolutionFactory
from apps.core.models import Alert


def open_alerts(prop, prefix):
    return list(Alert.objects.filter(property=prop, resolved_at__isnull=True, dedupe_key__startswith=prefix))


@pytest.mark.django_db
class TestAssignNumber:
    def test_numbers_run_consecutively_from_the_start_of_the_range(self, prop):
        resolution = InvoiceResolutionFactory(property=prop, from_number=990, to_number=5000)
        today = prop.business_date

        numbers = [assign_number(prop, "invoice", on_date=today)[1] for _ in range(3)]

        assert numbers == [990, 991, 992]
        resolution.refresh_from_db()
        assert resolution.current_number == 992

    def test_the_number_comes_from_the_active_resolution_of_the_kind(self, prop):
        InvoiceResolutionFactory(property=prop, prefix="OLD", is_active=False)
        active = InvoiceResolutionFactory(property=prop, prefix="SETT", from_number=10)

        resolution, number = assign_number(prop, "invoice", on_date=prop.business_date)

        assert (resolution.pk, number) == (active.pk, 10)

    def test_an_exhausted_range_is_rejected_and_raises_a_critical_alert(self, prop):
        InvoiceResolutionFactory(property=prop, from_number=1, to_number=2, current_number=2)

        with pytest.raises(NumberingError) as caught:
            assign_number(prop, "invoice", on_date=prop.business_date)

        assert caught.value.code == "resolution_exhausted"
        [alert] = open_alerts(prop, "compliance:resolution")
        assert alert.severity == "critical"

    def test_an_expired_resolution_is_rejected_and_raises_a_critical_alert(self, prop):
        today = prop.business_date
        InvoiceResolutionFactory(
            property=prop, valid_from=today - timedelta(days=400), valid_to=today - timedelta(days=1)
        )

        with pytest.raises(NumberingError) as caught:
            assign_number(prop, "invoice", on_date=today)

        assert caught.value.code == "resolution_expired"
        assert [a.severity for a in open_alerts(prop, "compliance:resolution")] == ["critical"]

    def test_a_resolution_that_is_not_valid_yet_is_rejected(self, prop):
        today = prop.business_date
        InvoiceResolutionFactory(
            property=prop, valid_from=today + timedelta(days=1), valid_to=today + timedelta(days=300)
        )

        with pytest.raises(NumberingError) as caught:
            assign_number(prop, "invoice", on_date=today)

        assert caught.value.code == "resolution_not_valid_yet"

    def test_without_an_active_resolution_invoices_cannot_be_numbered(self, prop):
        with pytest.raises(NumberingError) as caught:
            assign_number(prop, "invoice", on_date=prop.business_date)

        assert caught.value.code == "no_active_resolution"
        assert [a.severity for a in open_alerts(prop, "compliance:resolution")] == ["critical"]

    def test_reaching_90_percent_of_the_range_raises_a_warning(self, prop):
        InvoiceResolutionFactory(property=prop, from_number=1, to_number=10, current_number=8)

        assign_number(prop, "invoice", on_date=prop.business_date)  # 9 of 10

        [alert] = open_alerts(prop, "compliance:resolution")
        assert alert.severity == "warning"
        assert alert.data["remaining"] == 1

    def test_below_90_percent_and_far_from_expiry_there_is_no_alert(self, prop):
        InvoiceResolutionFactory(property=prop, from_number=1, to_number=10, current_number=7)

        assign_number(prop, "invoice", on_date=prop.business_date)  # 8 of 10

        assert open_alerts(prop, "compliance:resolution") == []

    def test_less_than_30_days_of_validity_raises_a_warning(self, prop):
        today = prop.business_date
        InvoiceResolutionFactory(property=prop, valid_to=today + timedelta(days=29))

        assign_number(prop, "invoice", on_date=today)

        [alert] = open_alerts(prop, "compliance:resolution")
        assert (alert.severity, alert.data["days_left"]) == ("warning", 29)

    def test_credit_notes_get_a_default_internal_range_when_none_is_configured(self, prop):
        InvoiceResolutionFactory(property=prop, environment="production")

        resolution, number = assign_number(prop, "credit_note", on_date=prop.business_date)

        assert (resolution.document_kind, resolution.prefix, number) == ("credit_note", "NC", 1)
        assert resolution.environment == "production"
        assert InvoiceResolution.objects.filter(property=prop, document_kind="credit_note").count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_concurrent_assignments_are_serialized_and_get_distinct_numbers(prop):
    """Thread A takes a number and keeps its transaction open; thread B must wait for A's commit instead of
    reading the same `current_number` (that would hand out the same DIAN number twice)."""
    InvoiceResolutionFactory(property=prop, from_number=1, to_number=5000)
    today = prop.business_date
    a_assigned, release = threading.Event(), threading.Event()
    results, b_done_at = {}, {}

    def thread_a():
        try:
            with transaction.atomic():
                results["a"] = assign_number(prop, "invoice", on_date=today)[1]
                a_assigned.set()
                release.wait(10)
        finally:
            connection.close()

    def thread_b():
        try:
            a_assigned.wait(10)
            with transaction.atomic():
                results["b"] = assign_number(prop, "invoice", on_date=today)[1]
            b_done_at["t"] = time.monotonic()
        finally:
            connection.close()

    ta, tb = threading.Thread(target=thread_a), threading.Thread(target=thread_b)
    ta.start()
    tb.start()
    a_assigned.wait(10)
    time.sleep(0.4)
    blocked_while_a_was_open = "t" not in b_done_at
    released_at = time.monotonic()
    release.set()
    ta.join(10)
    tb.join(10)

    assert blocked_while_a_was_open
    assert b_done_at["t"] >= released_at
    assert (results["a"], results["b"]) == (1, 2)
