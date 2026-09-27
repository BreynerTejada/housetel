"""stay_checked_out → folios close (folio_closed is emitted) only when everyone left and nothing is owed."""

from decimal import Decimal

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.models import AuditEvent
from apps.core.signals import folio_closed, send_on_commit, stay_checked_out
from apps.finance.services import get_or_create_folio, post_charge, record_payment, refund_payment

pytestmark = pytest.mark.django_db


@pytest.fixture
def closed_folios():
    folios = []

    def receiver(sender, **kwargs):
        folios.append(kwargs["folio"])

    folio_closed.connect(receiver, weak=False, dispatch_uid="test-folio-closed")
    yield folios
    folio_closed.disconnect(dispatch_uid="test-folio-closed")


def reservation_with(prop, *statuses, total=Decimal("400000")):
    reservation = ReservationFactory(property=prop, status="checked_out")
    stays = [StayFactory(reservation=reservation, status=status, total_amount=total) for status in statuses]
    return reservation, stays


def check_out(stay, capture):
    with capture(execute=True):
        send_on_commit(stay_checked_out, stay=stay)


def test_settled_reservation_closes_its_folios(prop, closed_folios, django_capture_on_commit_callbacks):
    reservation, (stay,) = reservation_with(prop, "checked_out")
    folio = get_or_create_folio(reservation)
    post_charge(folio, kind="extra", amount=Decimal("50000"), description="Minibar")
    record_payment(folio, amount=Decimal("450000"), method="card_terminal")

    check_out(stay, django_capture_on_commit_callbacks)

    folio.refresh_from_db()
    assert folio.status == "closed" and folio.closed_at is not None
    assert closed_folios == [folio]
    assert AuditEvent.objects.filter(action="finance.folio_closed", target_id=str(folio.pk)).exists()


def test_a_balance_due_keeps_the_folio_open(prop, closed_folios, django_capture_on_commit_callbacks):
    reservation, (stay,) = reservation_with(prop, "checked_out")
    folio = get_or_create_folio(reservation)
    record_payment(folio, amount=Decimal("100000"), method="card_terminal")

    check_out(stay, django_capture_on_commit_callbacks)

    folio.refresh_from_db()
    assert folio.status == "open" and closed_folios == []


def test_an_overpaid_reservation_waits_for_its_refund(
    prop, closed_folios, django_capture_on_commit_callbacks
):
    reservation, (stay,) = reservation_with(prop, "checked_out")
    folio = get_or_create_folio(reservation)
    record_payment(folio, amount=Decimal("500000"), method="card_terminal")

    check_out(stay, django_capture_on_commit_callbacks)

    folio.refresh_from_db()
    assert folio.status == "open" and closed_folios == []


def test_a_refund_still_in_progress_keeps_the_folio_open(
    prop, owner, closed_folios, django_capture_on_commit_callbacks
):
    """Money on its way back to the guest (pending refund): the account is not settled yet."""
    reservation, (stay,) = reservation_with(prop, "checked_out")
    folio = get_or_create_folio(reservation)
    payment = record_payment(folio, amount=Decimal("400000"), method="ota_collect")
    refund = refund_payment(payment, amount=Decimal("50000"), reason="Cortesía", actor=owner, confirm=True)
    assert refund.status == "pending"  # OTA money: refunded by hand in the channel's extranet

    check_out(stay, django_capture_on_commit_callbacks)

    folio.refresh_from_db()
    assert folio.status == "open" and closed_folios == []


def test_waits_until_every_stay_left(prop, closed_folios, django_capture_on_commit_callbacks):
    reservation, (leaving, staying) = reservation_with(prop, "checked_out", "checked_in")
    folio = get_or_create_folio(reservation)
    record_payment(folio, amount=Decimal("800000"), method="bank_transfer")

    check_out(leaving, django_capture_on_commit_callbacks)

    folio.refresh_from_db()
    assert folio.status == "open" and closed_folios == []


def test_cancelled_stays_do_not_block_the_close(prop, closed_folios, django_capture_on_commit_callbacks):
    reservation, (stay, _cancelled) = reservation_with(prop, "checked_out", "cancelled")
    folio = get_or_create_folio(reservation)
    stay_folio = get_or_create_folio(reservation, stay=stay)
    record_payment(folio, amount=Decimal("400000"), method="bank_transfer")

    check_out(stay, django_capture_on_commit_callbacks)

    assert {f.pk for f in closed_folios} == {folio.pk, stay_folio.pk}
