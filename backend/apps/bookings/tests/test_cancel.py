"""`cancel_reservation` and `mark_no_show` (spec §4.2, plan B2b): penalties from the policy snapshot, waiver,
inventory release, fee charge, signals.

Timing: the free window ends `free_until_hours_before` hours before `checkin_date + property.check_in_time` in
the property's timezone. Check-in 2026-10-10 at 15:00 Bogotá (UTC−5) with 48 h free → free until
2026-10-08 15:00 COT = 20:00 UTC. Two DBL nights = 761.600 (first night 380.800).
"""

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from apps.bookings.models import InventoryDay, Reservation, Stay
from apps.bookings.services.availability import availability
from apps.bookings.services.policies import cancellation_fee
from apps.bookings.services.reservations import (
    assign_room,
    cancel_reservation,
    create_reservation,
    mark_no_show,
)
from apps.bookings.tests.helpers import book, oct_, reservation_request, stay_request
from apps.bookings.types import InvalidStateError
from apps.core.models import AuditEvent
from apps.finance.models import Charge
from apps.finance.services import reservation_balance
from apps.rates.tests.factories import CancellationPolicyFactory

pytestmark = pytest.mark.django_db

BEFORE_DEADLINE = "2026-10-08 19:59:00+00:00"
AFTER_DEADLINE = "2026-10-08 20:01:00+00:00"


def with_policy(hotel, **values):
    policy = CancellationPolicyFactory(property=hotel.prop, **values)
    hotel.plan.cancellation_policy = policy
    hotel.plan.save()
    return policy


def booking(hotel, **kwargs):
    return book(hotel, oct_(10), oct_(12), **kwargs)


def fees(reservation):
    return list(
        Charge.objects.filter(folio__reservation=reservation, kind="cancellation_fee").values_list(
            "amount", "tax_amount"
        )
    )


class TestCancellationFee:
    @freeze_time(BEFORE_DEADLINE)
    def test_inside_the_free_window_it_is_free(self, hotel):
        with_policy(hotel, free_until_hours_before=48, penalty_type="first_night")
        reservation = booking(hotel)

        cancel_reservation(reservation, reason="Cambio de planes")

        reservation.refresh_from_db()
        assert (reservation.status, reservation.cancellation_fee) == ("cancelled", Decimal("0"))
        assert reservation.cancellation_reason == "Cambio de planes"
        assert reservation.cancelled_at is not None
        assert fees(reservation) == []

    @freeze_time(AFTER_DEADLINE)
    def test_after_the_window_the_first_night_is_charged(self, hotel):
        with_policy(hotel, free_until_hours_before=48, penalty_type="first_night")
        reservation = booking(hotel)

        cancel_reservation(reservation, reason="No viaja")

        reservation.refresh_from_db()
        assert reservation.cancellation_fee == Decimal("380800")
        assert fees(reservation) == [(Decimal("380800"), Decimal("0"))]
        assert reservation_balance(reservation) == Decimal("380800")

    @freeze_time(AFTER_DEADLINE)
    @pytest.mark.parametrize(
        "policy,fee",
        [
            ({"penalty_type": "percent", "penalty_value": Decimal("50")}, "380800"),
            ({"penalty_type": "full"}, "761600"),
        ],
        ids=["percent", "full"],
    )
    def test_percent_and_full_penalties(self, hotel, policy, fee):
        with_policy(hotel, free_until_hours_before=48, **policy)
        reservation = booking(hotel)
        assert cancel_reservation(reservation, reason="-").cancellation_fee == Decimal(fee)

    @freeze_time("2026-09-01 12:00:00+00:00")
    def test_non_refundable_charges_everything_even_early(self, hotel):
        with_policy(hotel, non_refundable=True)
        assert cancel_reservation(booking(hotel), reason="-").cancellation_fee == Decimal("761600")

    @freeze_time(AFTER_DEADLINE)
    def test_the_first_night_of_every_stay_counts(self, hotel):
        with_policy(hotel, free_until_hours_before=48, penalty_type="first_night")
        req = reservation_request(
            hotel,
            [
                stay_request(hotel, oct_(10), oct_(12)),
                stay_request(hotel, oct_(10), oct_(11), room_type=hotel.ste),
            ],
        )
        reservation = create_reservation(req)
        assert cancel_reservation(reservation, reason="-").cancellation_fee == Decimal("380800") + Decimal(
            "773500"
        )

    @freeze_time(AFTER_DEADLINE)
    def test_without_policy_it_is_free(self, hotel):
        assert cancel_reservation(booking(hotel), reason="-").cancellation_fee == Decimal("0")

    @freeze_time(AFTER_DEADLINE)
    def test_a_tentative_reservation_is_cancelled_without_fee(self, hotel):
        with_policy(hotel, non_refundable=True)
        assert cancel_reservation(booking(hotel, status="tentative"), reason="-").cancellation_fee == Decimal(
            0
        )

    @freeze_time(AFTER_DEADLINE)
    def test_waiving_the_fee(self, hotel, owner):
        with_policy(hotel, non_refundable=True)
        reservation = booking(hotel)

        cancel_reservation(reservation, reason="Cortesía", waive_fee=True, actor=owner)

        assert Reservation.objects.get(pk=reservation.pk).cancellation_fee == Decimal("0")
        assert fees(reservation) == []
        event = AuditEvent.objects.get(action="bookings.reservation_cancelled")
        assert event.changes["fee_waived"] == [None, "761600.00"]

    @freeze_time(BEFORE_DEADLINE)
    def test_preview_tells_the_fee_and_the_deadline_without_cancelling(self, hotel):
        with_policy(hotel, free_until_hours_before=48, penalty_type="first_night")
        reservation = booking(hotel)

        preview = cancellation_fee(reservation)

        assert (preview.amount, preview.reason) == (Decimal("0"), "free_window")
        assert preview.free_until == datetime(2026, 10, 8, 15, 0, tzinfo=ZoneInfo("America/Bogota"))
        assert Reservation.objects.get(pk=reservation.pk).status == "confirmed"
        with freeze_time(AFTER_DEADLINE):
            late = cancellation_fee(reservation)
        assert (late.amount, late.reason) == (Decimal("380800"), "first_night")


class TestCancellation:
    def test_releases_the_units_and_the_room(self, hotel):
        reservation = booking(hotel)
        assign_room(reservation.stays.get(), hotel.rooms["101"])

        cancel_reservation(reservation, reason="-")

        assert availability(property=hotel.prop, checkin=oct_(10), checkout=oct_(12))[hotel.dbl.pk] == 3
        assert set(
            InventoryDay.objects.filter(date__in=[oct_(10), oct_(11)]).values_list("sold_units", flat=True)
        ) == {0}
        assert set(Stay.objects.filter(reservation=reservation).values_list("status", flat=True)) == {
            "cancelled"
        }
        other = booking(hotel).stays.get()
        assign_room(other, hotel.rooms["101"])  # the room is free again

    def test_emits_reservation_cancelled_and_inventory_changed(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        reservation = booking(hotel)
        with django_capture_on_commit_callbacks(execute=True):
            cancel_reservation(reservation, reason="-")
        assert [kw["reservation"] for kw in signal_log.of("reservation_cancelled")] == [reservation]
        (changed,) = signal_log.of("inventory_changed")
        assert (changed["room_type_ids"], changed["start"], changed["end"]) == (
            [hotel.dbl.pk],
            oct_(10),
            oct_(12),
        )

    @freeze_time(AFTER_DEADLINE)
    def test_is_audited_with_its_source(self, hotel):
        with_policy(hotel, non_refundable=True)
        reservation = booking(hotel)
        cancel_reservation(reservation, reason="Cancelada en la OTA", source="channel")
        event = AuditEvent.objects.get(action="bookings.reservation_cancelled")
        assert (event.source, event.target_id) == ("channel", str(reservation.pk))
        assert Charge.objects.get(kind="cancellation_fee").source == "channel"

    @pytest.mark.parametrize("status", ["checked_in", "checked_out", "cancelled", "no_show"])
    def test_only_tentative_or_confirmed_reservations_can_be_cancelled(self, hotel, status):
        reservation = booking(hotel)
        Reservation.objects.filter(pk=reservation.pk).update(status=status)
        with pytest.raises(InvalidStateError):
            cancel_reservation(reservation, reason="-")


class TestNoShow:
    @pytest.fixture
    def late(self, hotel):
        """Arrived on 2026-10-01 for three nights; the business date is already the 2nd."""
        reservation = book(hotel, oct_(1), oct_(4))
        assign_room(reservation.stays.get(), hotel.rooms["101"])
        hotel.prop.business_date = oct_(2)
        hotel.prop.save()
        return Reservation.objects.get(pk=reservation.pk)

    def test_frees_every_night_and_charges_the_first_one_by_default(self, hotel, late):
        result = mark_no_show(late)

        assert result.status == "no_show"
        assert set(Stay.objects.filter(reservation=late).values_list("status", flat=True)) == {"no_show"}
        assert [
            InventoryDay.objects.get(room_type=hotel.dbl, date=oct_(day)).sold_units for day in (1, 2, 3)
        ] == [0, 0, 0]
        assert Reservation.objects.get(pk=late.pk).cancellation_fee == Decimal("380800")
        assert fees(late) == [(Decimal("380800"), Decimal("0"))]
        assert AuditEvent.objects.get(action="bookings.reservation_no_show").source == "automation"
        assign_room(book(hotel, oct_(2), oct_(3)).stays.get(), hotel.rooms["101"])  # room free again

    def test_follows_the_policy(self, hotel):
        with_policy(hotel, non_refundable=True)
        reservation = book(hotel, oct_(1), oct_(3))
        hotel.prop.business_date = oct_(2)
        hotel.prop.save()
        assert mark_no_show(reservation, source="user").cancellation_fee == Decimal("761600")

    def test_emits_reservation_no_show(self, hotel, late, django_capture_on_commit_callbacks, signal_log):
        with django_capture_on_commit_callbacks(execute=True):
            mark_no_show(late)
        assert [kw["reservation"].pk for kw in signal_log.of("reservation_no_show")] == [late.pk]
        assert signal_log.of("inventory_changed")[0]["room_type_ids"] == [hotel.dbl.pk]

    def test_an_arrival_that_is_not_due_yet_cannot_be_a_no_show(self, hotel):
        reservation = book(hotel, oct_(1), oct_(3))  # business date is the 1st: still expected today
        with pytest.raises(InvalidStateError):
            mark_no_show(reservation)

    @pytest.mark.parametrize("status", ["tentative", "checked_in", "cancelled"])
    def test_only_confirmed_reservations(self, hotel, late, status):
        Reservation.objects.filter(pk=late.pk).update(status=status)
        with pytest.raises(InvalidStateError):
            mark_no_show(late)
