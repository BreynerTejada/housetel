"""`modify_stay` (spec §4.2, plan B2b): new dates / category / plan / occupancy, moving inventory atomically,
repricing (or keeping the agreed prices), releasing the room when it no longer fits, `reservation_updated`.

Conftest hotel: DBL 380.800 per night (320.000 + IVA), STE 773.500. Business date 2026-10-01.
"""

from decimal import Decimal

import pytest

from apps.bookings.models import InventoryDay, Stay
from apps.bookings.services import reservations
from apps.bookings.services.reservations import (
    assign_room,
    create_reservation,
    modify_stay,
    preview_modify_stay,
)
from apps.bookings.tests.helpers import book, entry, oct_, reservation_request, stay_request
from apps.bookings.types import AvailabilityError, BookingError, InvalidStateError
from apps.core.models import AuditEvent
from apps.rates.models import DailyRate
from apps.rates.tests.factories import CancellationPolicyFactory, RatePlanFactory

pytestmark = pytest.mark.django_db


def new_stay(hotel, checkin=None, checkout=None, room=None, **kwargs):
    stay = book(hotel, checkin or oct_(1), checkout or oct_(3), **kwargs).stays.get()
    if room is not None:
        assign_room(stay, room)
    return Stay.objects.get(pk=stay.pk)


def fresh(stay):
    return Stay.objects.select_related("reservation").get(pk=stay.pk)


def sold(room_type, day):
    row = InventoryDay.objects.filter(room_type=room_type, date=day).first()
    return row.sold_units if row else 0


class TestDates:
    def test_extending_takes_the_new_night_and_prices_it(self, hotel):
        stay = new_stay(hotel)

        result = modify_stay(stay, checkout=oct_(4))

        assert isinstance(result, Stay)
        stay = fresh(stay)
        assert (stay.checkin_date, stay.checkout_date, stay.total_amount) == (
            oct_(1),
            oct_(4),
            Decimal("1142400"),
        )
        assert [item["date"] for item in stay.nightly_rates] == ["2026-10-01", "2026-10-02", "2026-10-03"]
        assert (stay.reservation.checkout_date, stay.reservation.total_amount) == (
            oct_(4),
            Decimal("1142400"),
        )
        assert sold(hotel.dbl, oct_(3)) == 1

    def test_moving_the_dates_releases_the_old_nights(self, hotel):
        stay = new_stay(hotel)
        modify_stay(stay, checkin=oct_(5), checkout=oct_(7))
        assert [sold(hotel.dbl, oct_(day)) for day in (1, 2, 5, 6)] == [0, 0, 1, 1]
        assert fresh(stay).reservation.checkin_date == oct_(5)

    def test_without_units_on_the_new_nights_it_is_a_409_and_nothing_changes(self, hotel):
        for _ in range(3):
            book(hotel, oct_(3), oct_(4))
        stay = new_stay(hotel)
        with pytest.raises(AvailabilityError):
            modify_stay(stay, checkout=oct_(4))
        assert (fresh(stay).checkout_date, sold(hotel.dbl, oct_(3)), sold(hotel.dbl, oct_(1))) == (
            oct_(3),
            3,
            1,
        )

    def test_reprices_with_the_current_rates(self, hotel):
        stay = new_stay(hotel)
        DailyRate.objects.create(
            room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(1), price=Decimal("400000")
        )
        modify_stay(stay, checkout=oct_(4))
        assert fresh(stay).nightly_rates[0] == entry(oct_(1), 476000, 400000, 76000)

    def test_reprice_false_keeps_the_agreed_prices_and_prices_only_new_nights(self, hotel):
        stay = new_stay(hotel)
        DailyRate.objects.create(
            room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(1), price=Decimal("400000")
        )
        DailyRate.objects.create(
            room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(3), price=Decimal("300000")
        )
        modify_stay(stay, checkout=oct_(4), reprice=False)
        assert fresh(stay).nightly_rates == [
            entry(oct_(1), 380800, 320000, 60800),
            entry(oct_(2), 380800, 320000, 60800),
            entry(oct_(3), 357000, 300000, 57000),
        ]
        assert fresh(stay).total_amount == Decimal("1118600")

    def test_dates_must_be_valid(self, hotel):
        with pytest.raises(BookingError) as error:
            modify_stay(new_stay(hotel), checkout=oct_(1))
        assert error.value.code == "invalid_dates"


class TestRoom:
    def test_is_kept_when_it_is_still_free(self, hotel):
        stay = new_stay(hotel, room=hotel.rooms["101"])
        modify_stay(stay, checkout=oct_(4))
        assert fresh(stay).room == hotel.rooms["101"]

    def test_is_released_when_someone_else_has_it_on_the_new_nights(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        stay = new_stay(hotel, room=hotel.rooms["101"])
        new_stay(hotel, oct_(3), oct_(5), room=hotel.rooms["101"])
        with django_capture_on_commit_callbacks(execute=True):
            modify_stay(stay, checkout=oct_(4))
        assert (fresh(stay).room, fresh(stay).checkout_date) == (None, oct_(4))
        assert [(kw["stay"].pk, kw["old_room"]) for kw in signal_log.of("room_assigned")] == [
            (stay.pk, hotel.rooms["101"])
        ]

    def test_changing_the_category_releases_the_room_and_moves_the_units(self, hotel):
        stay = new_stay(hotel, room=hotel.rooms["101"])
        modify_stay(stay, room_type=hotel.ste)
        stay = fresh(stay)
        assert (stay.room, stay.room_type, stay.total_amount) == (None, hotel.ste, Decimal("1547000"))
        assert (sold(hotel.dbl, oct_(1)), sold(hotel.ste, oct_(1)), sold(hotel.ste, oct_(2))) == (0, 1, 1)

    def test_changing_the_category_to_the_one_of_its_upgraded_room_keeps_the_room(self, hotel):
        stay = new_stay(hotel)
        assign_room(stay, hotel.rooms["301"], force=True)  # a DBL booking upgraded to the suite

        modify_stay(stay, room_type=hotel.ste)

        stay = fresh(stay)
        assert (stay.room, stay.room_type, stay.total_amount) == (
            hotel.rooms["301"],
            hotel.ste,
            Decimal("1547000"),
        )
        assert (sold(hotel.dbl, oct_(1)), sold(hotel.ste, oct_(1)), sold(hotel.ste, oct_(2))) == (0, 1, 1)

    def test_the_database_constraint_guards_the_kept_room(self, hotel, monkeypatch):
        """If the application check misses the next guest of the room, the exclusion constraint refuses the
        extension: 409 and nothing changes (dates, room, inventory)."""
        stay = new_stay(hotel, room=hotel.rooms["101"])
        new_stay(hotel, oct_(3), oct_(5), room=hotel.rooms["101"])
        monkeypatch.setattr(reservations, "is_occupied", lambda *args, **kwargs: False)

        with pytest.raises(AvailabilityError) as error:
            modify_stay(stay, checkout=oct_(4))

        assert error.value.code == "no_availability"
        assert (fresh(stay).checkout_date, fresh(stay).room, sold(hotel.dbl, oct_(3))) == (
            oct_(3),
            hotel.rooms["101"],
            1,
        )

    def test_a_dorm_bed_is_kept_when_free(self, hotel):
        stay = new_stay(hotel, room_type=hotel.dorm_type, adults=1)
        assign_room(stay, hotel.dorm, bed=hotel.beds["B"])
        modify_stay(stay, checkout=oct_(5))
        assert (fresh(stay).bed, sold(hotel.dorm_type, oct_(4))) == (hotel.beds["B"], 1)


class TestInHouse:
    @pytest.fixture
    def in_house(self, hotel):
        stay = new_stay(hotel, room=hotel.rooms["101"])
        Stay.objects.filter(pk=stay.pk).update(status="checked_in")
        return fresh(stay)

    def test_can_extend_in_the_same_room(self, hotel, in_house):
        modify_stay(in_house, checkout=oct_(5))
        assert (fresh(in_house).checkout_date, fresh(in_house).room) == (oct_(5), hotel.rooms["101"])

    def test_cannot_extend_when_the_room_is_taken_next(self, hotel, in_house):
        new_stay(hotel, oct_(3), oct_(5), room=hotel.rooms["101"])
        with pytest.raises(AvailabilityError):
            modify_stay(in_house, checkout=oct_(4))

    def test_the_arrival_cannot_change(self, hotel, in_house):
        with pytest.raises(InvalidStateError):
            modify_stay(in_house, checkin=oct_(2))

    def test_the_category_cannot_change(self, hotel, in_house):
        with pytest.raises(InvalidStateError):
            modify_stay(in_house, room_type=hotel.ste)
        assert fresh(in_house).room_type == hotel.dbl

    def test_an_upgraded_guest_can_take_the_category_of_the_room(self, hotel, in_house):
        assign_room(in_house, hotel.rooms["301"], force=True)
        modify_stay(in_house, room_type=hotel.ste)
        stay = fresh(in_house)
        assert (stay.room, stay.room_type, stay.status) == (hotel.rooms["301"], hotel.ste, "checked_in")

    def test_the_departure_cannot_move_before_the_business_date(self, hotel, in_house):
        hotel.prop.business_date = oct_(3)
        hotel.prop.save()
        with pytest.raises(InvalidStateError):
            modify_stay(in_house, checkout=oct_(2))
        assert fresh(in_house).checkout_date == oct_(3)

    def test_can_shorten_to_the_business_date_plus_one(self, hotel, in_house):
        modify_stay(in_house, checkout=oct_(2))
        assert (fresh(in_house).checkout_date, sold(hotel.dbl, oct_(2))) == (oct_(2), 0)


class TestOther:
    @pytest.mark.parametrize("status", ["cancelled", "no_show", "checked_out"])
    def test_inactive_stays_cannot_change(self, hotel, status):
        stay = new_stay(hotel)
        Stay.objects.filter(pk=stay.pk).update(status=status)
        with pytest.raises(InvalidStateError):
            modify_stay(stay, checkout=oct_(4))

    def test_capacity_and_plan_are_validated(self, hotel):
        stay = new_stay(hotel)
        with pytest.raises(BookingError) as error:
            modify_stay(stay, adults=3)
        assert error.value.code == "capacity_exceeded"
        only_ste = RatePlanFactory(property=hotel.prop, code="STEONLY", room_types=[hotel.ste])
        with pytest.raises(BookingError) as error:
            modify_stay(stay, rate_plan=only_ste)
        assert error.value.code == "invalid_rate_plan"

    def test_changing_the_plan_takes_its_cancellation_policy(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        flexible = CancellationPolicyFactory(property=hotel.prop)
        hotel.plan.cancellation_policy = flexible
        hotel.plan.save()
        strict = CancellationPolicyFactory(property=hotel.prop, non_refundable=True)
        nonref = RatePlanFactory(
            property=hotel.prop,
            code="NR",
            kind="derived",
            parent=hotel.plan,
            derivation_value=Decimal("-12"),
            room_types=[hotel.dbl],
            cancellation_policy=strict,
        )
        stay = new_stay(hotel)

        with django_capture_on_commit_callbacks(execute=True):
            modify_stay(stay, rate_plan=nonref)

        snapshot = fresh(stay).reservation.cancellation_policy_snapshot
        assert (snapshot["id"], snapshot["non_refundable"], snapshot["rate_plan_id"]) == (
            str(strict.pk),
            True,
            str(nonref.pk),
        )
        change = [str(flexible.pk), str(strict.pk)]
        assert (
            AuditEvent.objects.get(action="bookings.stay_modified").changes["cancellation_policy"] == change
        )
        (updated,) = signal_log.of("reservation_updated")
        assert updated["changes"]["cancellation_policy"] == tuple(change)

    def test_only_the_first_stay_decides_the_cancellation_policy(self, hotel):
        hotel.plan.cancellation_policy = CancellationPolicyFactory(property=hotel.prop)
        hotel.plan.save()
        nonref = RatePlanFactory(
            property=hotel.prop,
            code="NR",
            room_types=[hotel.dbl],
            cancellation_policy=CancellationPolicyFactory(property=hotel.prop, non_refundable=True),
        )
        req = reservation_request(
            hotel, [stay_request(hotel, oct_(1), oct_(3)), stay_request(hotel, oct_(1), oct_(3))]
        )
        reservation = create_reservation(req)
        before = reservation.cancellation_policy_snapshot
        second = reservation.stays.order_by("created_at").last()

        modify_stay(second, rate_plan=nonref)

        assert fresh(second).reservation.cancellation_policy_snapshot == before

    def test_changing_the_plan_reprices(self, hotel):
        nonref = RatePlanFactory(
            property=hotel.prop,
            code="NR",
            kind="derived",
            parent=hotel.plan,
            derivation_value=Decimal("-12"),
            room_types=[hotel.dbl],
        )
        stay = new_stay(hotel)
        modify_stay(stay, rate_plan=nonref, adults=1)
        stay = fresh(stay)
        assert (stay.rate_plan, stay.adults, stay.reservation.adults) == (nonref, 1, 1)
        assert stay.total_amount == Decimal("670208")  # (281.600 + 53.504) × 2

    def test_emits_reservation_updated_and_inventory_changed(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        stay = new_stay(hotel)
        with django_capture_on_commit_callbacks(execute=True):
            modify_stay(stay, checkin=oct_(2), checkout=oct_(5))
        (updated,) = signal_log.of("reservation_updated")
        assert (updated["reservation"], updated["stay"]) == (stay.reservation, stay)
        changes = updated["changes"]
        assert changes["checkin_date"] == ("2026-10-01", "2026-10-02")
        assert changes["checkout_date"] == ("2026-10-03", "2026-10-05")
        assert changes["total_amount"] == ("761600.00", "1142400.00")
        assert changes["stay.checkout_date"] == ("2026-10-03", "2026-10-05")
        (changed,) = signal_log.of("inventory_changed")
        assert (changed["room_type_ids"], changed["start"], changed["end"]) == (
            [hotel.dbl.pk],
            oct_(1),
            oct_(5),
        )

    def test_is_audited(self, hotel, owner):
        stay = new_stay(hotel)
        modify_stay(stay, checkout=oct_(4), actor=owner)
        event = AuditEvent.objects.get(action="bookings.stay_modified")
        assert (event.target_id, event.actor) == (str(stay.pk), owner)
        assert event.changes["stay.checkout_date"] == ["2026-10-03", "2026-10-04"]

    def test_nothing_to_change_is_a_no_op(self, hotel):
        stay = new_stay(hotel)
        modify_stay(stay, checkout=oct_(3))
        assert not AuditEvent.objects.filter(action="bookings.stay_modified").exists()


def test_nights_already_charged_keep_their_amount_when_repricing(hotel):
    from apps.bookings.services.charges import post_room_charges

    stay = new_stay(hotel, room=hotel.rooms["101"])
    Stay.objects.filter(pk=stay.pk).update(status="checked_in")
    post_room_charges(stay, until_date=oct_(2))  # night of the 1st charged at 320.000 + IVA
    for day in (1, 2):
        DailyRate.objects.create(
            room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(day), price=Decimal("400000")
        )

    modify_stay(stay, checkout=oct_(4))

    assert fresh(stay).nightly_rates == [
        entry(oct_(1), 380800, 320000, 60800),
        entry(oct_(2), 476000, 400000, 76000),
        entry(oct_(3), 380800, 320000, 60800),
    ]


class TestPreview:
    def test_tells_the_new_price_without_changing_anything(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        stay = new_stay(hotel, room=hotel.rooms["101"])

        with django_capture_on_commit_callbacks(execute=True):
            preview = preview_modify_stay(stay, checkout=oct_(4))

        assert preview["stay"]["checkout_date"] == "2026-10-04"
        assert preview["stay"]["nights"] == 3
        assert preview["stay"]["room_id"] == str(hotel.rooms["101"].pk)
        assert preview["stay"]["nightly_rates"][-1] == entry(oct_(3), 380800, 320000, 60800)
        assert (preview["stay"]["total_amount"], preview["current_total"], preview["difference"]) == (
            "1142400.00",
            "761600.00",
            "380800.00",
        )
        assert (preview["reservation_total"], preview["balance"], preview["room_kept"]) == (
            "1142400.00",
            "1142400.00",
            True,
        )
        stay = fresh(stay)  # nothing was saved, audited, sent or taken
        assert (stay.checkout_date, stay.total_amount, sold(hotel.dbl, oct_(3))) == (
            oct_(3),
            Decimal("761600"),
            0,
        )
        assert not AuditEvent.objects.filter(action="bookings.stay_modified").exists()
        assert signal_log == []

    def test_says_when_the_room_would_be_released(self, hotel):
        stay = new_stay(hotel, room=hotel.rooms["101"])
        preview = preview_modify_stay(stay, room_type=hotel.ste)
        assert (preview["room_kept"], preview["stay"]["room_id"], preview["stay"]["room_type_id"]) == (
            False,
            None,
            str(hotel.ste.pk),
        )

    def test_raises_what_the_change_would_raise(self, hotel):
        for _ in range(3):
            book(hotel, oct_(3), oct_(4))
        stay = new_stay(hotel)
        with pytest.raises(AvailabilityError):
            preview_modify_stay(stay, checkout=oct_(4))

    def test_room_kept_is_null_for_a_stay_without_room(self, hotel):
        assert preview_modify_stay(new_stay(hotel), checkout=oct_(4))["room_kept"] is None
