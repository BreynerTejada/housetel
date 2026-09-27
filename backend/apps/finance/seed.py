"""Finance demo seed (plan B4): runs after bookings.

- Past stays (checked out) are paid — cash, card terminal or the simulated online gateway (Wompi-like) — and
  their folios closed; a few stay as receivables.
- In-house stays: some paid in full, most with a 50 % deposit, some still owing everything.
- Future confirmed stays: deposits of 30–50 % (online link or bank transfer), a pending link or nothing.
- Tentative stays: each one gets a pending payment link and nothing else (paying it confirms the booking).
- Cancellation and no-show penalties (posted by the booking services while seeding) are dated on the business
  date they belong to — the day of the cancellation, the night audit after a no-show — and about half of them
  are paid that day.
- The front desk user of each hotel (`aurora_front`, `andino_front`) gets a closed cash-shift history for
  the last days and an open shift today with this morning's payments.

Idempotent: reservations that already have payments or links are left alone, every decision about a
reservation comes from a random generator seeded with its id (a rerun decides the same, including "leave it
unpaid"), and the shifts are created only when the user has none at the property.
"""

import random
from datetime import datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.bookings.models import Reservation
from apps.core.money import quantize
from apps.core.tokens import portal_url
from apps.finance.cash import cash_shift_totals, close_cash_shift, open_cash_shift
from apps.finance.models import CashShift, Charge, Folio, Payment, PaymentIntent
from apps.finance.services import (
    close_settled_folios,
    create_payment_intent,
    decide_simulated_intent,
    get_or_create_folio,
    record_payment,
    reservation_balance,
)

FRONT_DESK_USERS = {"aurora": "aurora_front", "andino_mde": "andino_front"}
SHIFT_HISTORY_DAYS = 5
PAST_METHODS = [("card_terminal", 40), ("cash", 30), ("online", 30)]
ONLINE_METHODS = [("card", 70), ("pse", 20), ("nequi", 10)]


def seed(ctx) -> None:
    for key, prop in ctx.properties.items():
        front = ctx.users.get(FRONT_DESK_USERS.get(key, ""))
        stats = _seed_property(ctx, prop, front)
        ctx.log(
            f"  finanzas {prop.name}: {stats['payments']} pagos, {stats['links']} links, "
            f"{stats['shifts']} turnos de caja"
        )


def _seed_property(ctx, prop, front) -> dict:
    before = _counts(prop)
    taken = set(Payment.objects.filter(folio__property=prop).values_list("folio__reservation_id", flat=True))
    taken |= set(PaymentIntent.objects.filter(property=prop).values_list("folio__reservation_id", flat=True))
    todo = [
        r
        for r in Reservation.objects.filter(property=prop)
        .select_related("booker")
        .order_by("checkin_date", "created_at")
        if r.pk not in taken
    ]
    for reservation in todo:
        _date_penalty(ctx, prop, reservation)
    done: set = set()
    if front is not None and not CashShift.objects.filter(property=prop, user=front).exists():
        _shift_history(ctx, prop, front, todo, done)
        _todays_shift(ctx, prop, front, todo, done)
    declined_shown = PaymentIntent.objects.filter(property=prop, status="declined").exists()
    for reservation in todo:
        if reservation.pk not in done:
            declined_shown = _seed_reservation(ctx, reservation, declined_shown) or declined_shown
    after = _counts(prop)
    return {key: after[key] - before[key] for key in after}


def _counts(prop) -> dict:
    return {
        "payments": Payment.objects.filter(folio__property=prop).count(),
        "links": PaymentIntent.objects.filter(property=prop).count(),
        "shifts": CashShift.objects.filter(property=prop).count(),
    }


# --- Reservations -------------------------------------------------------------------------------------


def _seed_reservation(ctx, reservation, declined_shown: bool) -> bool:
    """Returns True when it created the demo declined link."""
    rng = random.Random(f"housetel-finance-{reservation.pk}")
    balance = reservation_balance(reservation)
    if balance <= 0:
        return False
    folio = get_or_create_folio(reservation)
    if folio.status == Folio.Status.CLOSED:
        return False
    roll = rng.random()
    status = reservation.status
    if status == "checked_out":
        amount = balance if roll >= 0.08 else _round(balance * Decimal("0.6"))  # a few receivables
        _pay(ctx, rng, folio, amount, _weighted(rng, PAST_METHODS), reservation.checkout_date)
        close_settled_folios(reservation)
    elif status == "checked_in":
        if roll < 0.3:
            _pay(ctx, rng, folio, balance, _weighted(rng, PAST_METHODS), reservation.checkin_date)
        elif roll < 0.85:
            method = rng.choice(["online", "card_terminal"])
            _pay(ctx, rng, folio, _round(balance / 2), method, reservation.checkin_date)
    elif status == "confirmed":
        deposit = _round(balance * Decimal(rng.randint(30, 50)) / 100, floor=True)
        paid_on = max(ctx.today - timedelta(days=rng.randint(1, 20)), ctx.today - timedelta(days=60))
        if roll < 0.45:
            _pay(ctx, rng, folio, deposit, "online", paid_on)
        elif roll < 0.6:
            _pay(ctx, rng, folio, deposit, "bank_transfer", paid_on)
        elif roll < 0.72:
            _link(folio, deposit)
        elif not declined_shown:
            decide_simulated_intent(_link(folio, deposit), outcome="declined", method="card")
            return True
    elif status == "tentative":  # a hold waiting for its payment: always a pending link
        _link(folio, _round(balance * Decimal("0.3"), floor=True))
    elif status in ("cancelled", "no_show") and roll < 0.5:
        _pay(ctx, rng, folio, balance, "card_terminal", _penalty_day(ctx, folio.property, reservation))
    return False


def _penalty_day(ctx, prop, reservation):
    """Business date on which the penalty belongs: the day of the cancellation, or the night audit right after
    a no-show's arrival day (`mark_no_show` needs the business date past the arrival)."""
    if reservation.status == "no_show":
        day = reservation.checkin_date + timedelta(days=1)
    elif reservation.cancelled_at:
        day = timezone.localtime(reservation.cancelled_at, ZoneInfo(prop.timezone or "America/Bogota")).date()
    else:
        day = reservation.checkin_date
    return min(day, ctx.today)


def _date_penalty(ctx, prop, reservation) -> None:
    """The booking services post a cancellation or no-show penalty with the business date of the moment the
    demo is seeded: date it when it happened, so revenue by business date does not pile up on the seed day.
    Only moves charges back in time (a penalty posted live, on its own day, is left alone)."""
    if reservation.status not in ("cancelled", "no_show"):
        return
    day = _penalty_day(ctx, prop, reservation)
    moment = reservation.cancelled_at if reservation.status == "cancelled" else None
    Charge.objects.filter(
        folio__reservation=reservation, kind=Charge.Kind.CANCELLATION_FEE, business_date__gt=day
    ).update(business_date=day, created_at=moment or _moment(prop, day, 2))


def _pay(ctx, rng, folio, amount, method, day, *, actor=None) -> Payment:
    amount = quantize(amount, folio.currency)
    if method == "online":
        intent = _link(folio, amount)
        intent = decide_simulated_intent(intent, outcome="approved", method=_weighted(rng, ONLINE_METHODS))
        payment = Payment.objects.get(intent=intent)
        moment = _moment(folio.property, day, rng.randint(8, 22))
        PaymentIntent.objects.filter(pk=intent.pk).update(
            created_at=moment, expires_at=moment + timedelta(hours=24)
        )
    else:
        reference = {"card_terminal": f"VOUCHER-{rng.randint(100000, 999999)}",
                     "bank_transfer": f"TRF-{rng.randint(1000000, 9999999)}"}.get(method, "")  # fmt: skip
        payment = record_payment(folio, amount=amount, method=method, reference=reference, actor=actor)
    moment = _moment(folio.property, day, rng.randint(8, 20), rng.randint(0, 59))
    Payment.objects.filter(pk=payment.pk).update(business_date=min(day, ctx.today), created_at=moment)
    return payment


def _link(folio, amount) -> PaymentIntent:
    reservation = folio.reservation
    return create_payment_intent(folio, amount=amount, return_url=f"{portal_url(reservation)}?paid=1")


# --- Cash shifts --------------------------------------------------------------------------------------


def _shift_history(ctx, prop, user, todo, done) -> None:
    rng = ctx.rng
    for days_ago in range(SHIFT_HISTORY_DAYS, 0, -1):
        day = ctx.today - timedelta(days=days_ago)
        shift = open_cash_shift(prop, user, opening_float=Decimal("200000"), notes="Turno de la mañana")
        departures = [
            r for r in todo if r.status == "checked_out" and r.checkout_date == day and r.pk not in done
        ]
        for reservation in departures[:3]:
            amount = reservation_balance(reservation)
            if amount <= 0:
                continue
            method = "cash" if rng.random() < 0.6 else "card_terminal"
            _pay(ctx, rng, get_or_create_folio(reservation), amount, method, day, actor=user)
            close_settled_folios(reservation)
            done.add(reservation.pk)
        difference = Decimal(rng.choice([0, 0, 0, -2000, 5000, -10000]))
        expected = cash_shift_totals(shift)["expected_cash"]
        close_cash_shift(shift, actor=user, counted_cash=expected + difference,
                         notes="Faltante por revisar" if difference < 0 else "")  # fmt: skip
        CashShift.objects.filter(pk=shift.pk).update(
            opened_at=_moment(prop, day, 7), closed_at=_moment(prop, day, 15, 5)
        )


def _todays_shift(ctx, prop, user, todo, done) -> None:
    rng = ctx.rng
    shift = open_cash_shift(prop, user, opening_float=Decimal("300000"), notes="Turno de la mañana")
    # 07:00, or half an hour ago if the demo is seeded earlier, but never before today's midnight
    opened = max(
        _moment(prop, ctx.today, 0), min(_moment(prop, ctx.today, 7), timezone.now() - timedelta(minutes=30))
    )
    CashShift.objects.filter(pk=shift.pk).update(opened_at=opened)
    leaving = [
        r for r in todo if r.status == "checked_in" and r.checkout_date == ctx.today and r.pk not in done
    ]
    arriving = [
        r for r in todo if r.status == "confirmed" and r.checkin_date == ctx.today and r.pk not in done
    ]
    for reservation in leaving[:2]:
        amount = reservation_balance(reservation)
        if amount > 0:
            method = "cash" if rng.random() < 0.7 else "card_terminal"
            _pay(ctx, rng, get_or_create_folio(reservation), amount, method, ctx.today, actor=user)
            done.add(reservation.pk)
    for reservation in arriving[:1]:
        amount = _round(reservation_balance(reservation) / 2)
        if amount > 0:
            _pay(ctx, rng, get_or_create_folio(reservation), amount, "cash", ctx.today, actor=user)
            done.add(reservation.pk)


# --- Helpers ------------------------------------------------------------------------------------------


def _weighted(rng, options):
    return rng.choices([value for value, _ in options], weights=[weight for _, weight in options])[0]


def _round(amount, *, floor=False) -> Decimal:
    """Round to thousands of pesos (deposits and partial payments look like what people really pay)."""
    thousands = (Decimal(amount) / 1000).to_integral_value(
        rounding="ROUND_FLOOR" if floor else "ROUND_HALF_UP"
    )
    return max(Decimal(1000), thousands * 1000)


def _moment(prop, day, hour, minute=0):
    local = datetime.combine(day, time(hour, minute))
    moment = timezone.make_aware(local, ZoneInfo(prop.timezone or "America/Bogota"))
    return min(moment, timezone.now())
