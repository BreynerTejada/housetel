"""Finance demo seed: payments for past stays, deposits for future ones, pending balances, cash shifts."""

import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from freezegun import freeze_time

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.seed import SeedContext
from apps.core.tests.factories import PropertyFactory
from apps.finance import seed as finance_seed
from apps.finance.models import CashShift, Charge, Folio, Payment, PaymentIntent
from apps.finance.services import get_or_create_folio, post_charge, reservation_balance

pytestmark = pytest.mark.django_db


def booking(prop, status, checkin, nights=2, total="600000"):
    reservation = ReservationFactory(
        property=prop, status=status, checkin_date=checkin, checkout_date=checkin + timedelta(days=nights)
    )
    StayFactory(reservation=reservation, status=status, total_amount=Decimal(total))
    return reservation


@pytest.fixture
def world(prop, make_member):
    today = prop.business_date
    front = make_member("front_desk", email="recepcion@hotel.test")
    past = [booking(prop, "checked_out", today - timedelta(days=d + 2)) for d in range(8)]
    in_house = [booking(prop, "checked_in", today - timedelta(days=1)) for _ in range(4)]
    leaving_today = booking(prop, "checked_in", today - timedelta(days=2))
    future = [booking(prop, "confirmed", today + timedelta(days=d + 3)) for d in range(10)]
    tentative = [booking(prop, "tentative", today + timedelta(days=20)) for _ in range(3)]
    cancelled = booking(prop, "cancelled", today + timedelta(days=5))
    folio = Folio.objects.create(property=prop, reservation=cancelled, guest=cancelled.booker)
    post_charge(folio, kind="cancellation_fee", amount=Decimal("300000"), description="Penalidad")
    other = PropertyFactory(organization=prop.organization)  # a hotel without front desk user nor bookings
    ctx = SeedContext(
        today=today,
        rng=random.Random(20260925),
        properties={"aurora": prop, "andino_bog": other},
        users={"aurora_front": front},
    )
    return {"ctx": ctx, "front": front, "past": past, "in_house": in_house, "leaving_today": leaving_today,
            "future": future, "tentative": tentative, "cancelled": cancelled}  # fmt: skip


def paid(reservation) -> Decimal:
    return sum(
        (p.amount for p in Payment.objects.filter(folio__reservation=reservation, status="approved")),
        Decimal("0"),
    )


def test_seed_builds_a_believable_ledger(world, prop):
    finance_seed.seed(world["ctx"])

    everything = [
        *world["past"],
        *world["in_house"],
        world["leaving_today"],
        *world["future"],
        *world["tentative"],
    ]
    assert all(reservation_balance(r) >= 0 for r in everything)  # nobody is overpaid
    settled = [r for r in world["past"] if reservation_balance(r) == 0]
    assert len(settled) >= 6
    assert all(Folio.objects.get(reservation=r).status == "closed" for r in settled)
    deposits = [r for r in world["future"] if paid(r) > 0]
    assert deposits and all(Decimal("0.3") <= paid(r) / Decimal("600000") <= Decimal("0.5") for r in deposits)
    assert any(reservation_balance(r) > 0 for r in [*world["in_house"], *world["future"]])  # pending balances
    assert all(paid(r) == 0 for r in world["tentative"])  # tentative ones only get pending links
    assert PaymentIntent.objects.filter(folio__reservation__in=world["tentative"], status="created").exists()
    methods = set(Payment.objects.values_list("method", flat=True))
    assert {"cash", "card_terminal"} <= methods and methods & {"wompi_card", "wompi_pse", "wompi_nequi"}


def test_every_tentative_booking_gets_its_pending_link(prop):
    """A tentative booking is a hold waiting for its payment, so each one gets a pending link. (A random 30 %
    used to get none: with the 3 tentative bookings of the ledger test above, that test failed in ~3 % of the
    runs, since each decision is seeded with the reservation's random id.)"""
    tentative = [booking(prop, "tentative", prop.business_date + timedelta(days=20 + i)) for i in range(20)]
    ctx = SeedContext(today=prop.business_date, rng=random.Random(1), properties={"aurora": prop})

    finance_seed.seed(ctx)

    for reservation in tentative:
        (link,) = PaymentIntent.objects.filter(folio__reservation=reservation)
        assert link.status == "created"
        assert paid(reservation) == 0


def fee_dates(reservation) -> set:
    charges = Charge.objects.filter(folio__reservation=reservation, kind="cancellation_fee")
    return set(charges.values_list("business_date", flat=True))


def test_penalties_are_dated_and_paid_on_the_day_they_were_posted(prop):
    """The booking services post cancellation and no-show penalties with the business date of the moment the
    demo is seeded. The finance seed dates each one when it happened (the day of the cancellation, or the
    night audit right after a no-show's arrival day), so revenue by business date does not pile up on the seed
    day, and a paid penalty is paid that same day (never before its charge)."""
    today = prop.business_date
    tz = ZoneInfo(prop.timezone)
    cancelled, no_shows = [], []
    for i in range(10):
        reservation = booking(prop, "cancelled", today - timedelta(days=20 + i))
        reservation.cancelled_at = datetime.combine(reservation.checkin_date, time(9, 30), tzinfo=tz)
        reservation.save(update_fields=["cancelled_at"])
        post_charge(get_or_create_folio(reservation), kind="cancellation_fee", amount=Decimal("300000"),
                    description="Penalidad")  # fmt: skip
        cancelled.append(reservation)
        no_show = booking(prop, "no_show", today - timedelta(days=10 + i))
        post_charge(get_or_create_folio(no_show), kind="cancellation_fee", amount=Decimal("300000"),
                    description="No show")  # fmt: skip
        no_shows.append(no_show)
    assert all(fee_dates(r) == {today} for r in [*cancelled, *no_shows])  # what the services leave
    ctx = SeedContext(today=today, rng=random.Random(1), properties={"aurora": prop})

    finance_seed.seed(ctx)

    for reservation in cancelled:
        assert fee_dates(reservation) == {reservation.checkin_date}, reservation.code
    for reservation in no_shows:
        assert fee_dates(reservation) == {reservation.checkin_date + timedelta(days=1)}, reservation.code
    payments = Payment.objects.filter(folio__reservation__in=[*cancelled, *no_shows], status="approved")
    assert payments.exists()
    for payment in payments.select_related("folio__reservation"):
        assert {payment.business_date} == fee_dates(payment.folio.reservation)


def test_seed_opens_the_front_desk_shift_and_keeps_a_history(world, prop):
    finance_seed.seed(world["ctx"])

    shifts = CashShift.objects.filter(property=prop, user=world["front"])
    (current,) = shifts.filter(closed_at__isnull=True)
    assert current.payments.filter(status="approved").exists()
    assert reservation_balance(world["leaving_today"]) == 0  # paid at the desk this morning
    history = shifts.exclude(closed_at=None)
    assert history.count() >= 3
    for shift in history:
        assert shift.difference == shift.counted_cash - shift.expected_cash
        assert shift.closed_at.date() <= prop.business_date


def test_todays_shift_opens_today_even_when_the_demo_is_seeded_right_after_midnight(prop, make_member):
    """Seeded at 00:10 the shift used to open "30 minutes ago", i.e. yesterday at 23:40."""
    front = make_member("front_desk")
    with freeze_time("2026-10-01 00:10:00-05:00"):
        prop.business_date = timezone.localdate()
        prop.save(update_fields=["business_date"])
        ctx = SeedContext(today=prop.business_date, rng=random.Random(1), properties={"aurora": prop},
                          users={"aurora_front": front})  # fmt: skip
        finance_seed.seed(ctx)
        (shift,) = CashShift.objects.filter(user=front, closed_at__isnull=True)
        assert timezone.localtime(shift.opened_at).date() == prop.business_date
        assert shift.opened_at <= timezone.now()


def test_seed_is_idempotent(world):
    finance_seed.seed(world["ctx"])
    counts = (Payment.objects.count(), PaymentIntent.objects.count(), CashShift.objects.count())
    finance_seed.seed(world["ctx"])
    assert (Payment.objects.count(), PaymentIntent.objects.count(), CashShift.objects.count()) == counts


def test_seed_works_without_bookings(prop, make_member):
    front = make_member("front_desk")
    ctx = SeedContext(today=prop.business_date, rng=random.Random(1), properties={"aurora": prop},
                      users={"aurora_front": front})  # fmt: skip
    finance_seed.seed(ctx)
    assert CashShift.objects.filter(user=front, closed_at__isnull=True).count() == 1
