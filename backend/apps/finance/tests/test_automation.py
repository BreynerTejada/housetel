"""finance.sync_pending_intents: verifies open payment links every 5 minutes and expires stale ones."""

from datetime import timedelta
from decimal import Decimal

import pytest
from celery.schedules import crontab
from django.utils import timezone

from apps.bookings.tests.factories import ReservationFactory
from apps.core import automation
from apps.core.tests.factories import PropertyFactory
from apps.finance.models import Payment, PaymentIntent
from apps.finance.services import create_payment_intent, get_or_create_folio

pytestmark = pytest.mark.django_db


def link(prop, **fields):
    folio = get_or_create_folio(ReservationFactory(property=prop))
    intent = create_payment_intent(folio, amount=Decimal("100000"), return_url="")
    if fields:
        PaymentIntent.objects.filter(pk=intent.pk).update(**fields)
        intent.refresh_from_db()
    return intent


def test_is_registered_every_five_minutes():
    item = automation.get("finance.sync_pending_intents")
    assert (item.app, item.scope, item.default_enabled) == ("finance", "property", True)
    assert item.schedule == crontab(minute="*/5")


def test_verifies_open_links_and_expires_stale_ones(prop):
    waiting = link(prop)
    paid_but_unsynced = link(
        prop,
        payload={"simulation": {"outcome": "approved", "method": "wompi_pse", "transaction_id": "SIM-9"}},
    )
    stale = link(prop, expires_at=timezone.now() - timedelta(minutes=1))
    stale_pending = link(prop, status="pending", expires_at=timezone.now() - timedelta(hours=1))
    already_paid = link(prop, status="approved")
    other_hotel = link(
        PropertyFactory(organization=prop.organization), expires_at=timezone.now() - timedelta(days=1)
    )

    run = automation.run("finance.sync_pending_intents", prop)

    assert run.status == "success"
    assert run.details == {"checked": 4, "approved": 1, "expired": 2}
    statuses = {i.pk: i.status for i in PaymentIntent.objects.all()}
    assert statuses[waiting.pk] == "created"
    assert statuses[paid_but_unsynced.pk] == "approved"
    assert statuses[stale.pk] == statuses[stale_pending.pk] == "expired"
    assert statuses[already_paid.pk] == "approved"
    assert statuses[other_hotel.pk] == "created"
    assert Payment.objects.get().intent_id == paid_but_unsynced.pk
