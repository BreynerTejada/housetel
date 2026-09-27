"""`check_in` / `check_out` (spec §4.2, plan B2b).

check_in: confirmed (tentative only with force), arrival due (`checkin_date <= business_date`; earlier arrival
dates and stays already over need force), a room (auto-assigned when missing, clean first) that is clean or
inspected (else RoomNotReadyError unless force).
check_out: in-house only; an early departure moves `checkout_date` to the business date and frees the future
nights; posts the room charges; balance must be 0 (else BalanceDueError unless force); room → dirty.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from apps.bookings.models import InventoryDay, Reservation, Stay
from apps.bookings.services.reservations import assign_room, check_in, check_out, create_reservation
from apps.bookings.tests.helpers import book, entry, oct_, reservation_request, stay_request
from apps.bookings.types import BalanceDueError, InvalidStateError, RoomNotReadyError
from apps.core.models import AuditEvent
from apps.finance.models import Charge
from apps.finance.services import get_or_create_folio, record_payment
from apps.inventory.models import Room

pytestmark = pytest.mark.django_db


def new_stay(hotel, checkin=None, checkout=None, room=None, **kwargs):
    stay = book(hotel, checkin or oct_(1), checkout or oct_(3), **kwargs).stays.get()
    if room is not None:
        assign_room(stay, room)
    return Stay.objects.get(pk=stay.pk)


def fresh(stay):
    return Stay.objects.select_related("reservation", "room").get(pk=stay.pk)


def set_business_date(hotel, day):
    hotel.prop.business_date = day
    hotel.prop.save()


def set_status(room, status):
    Room.objects.filter(pk=room.pk).update(housekeeping_status=status)


def pay(stay, amount):
    folio = get_or_create_folio(stay.reservation)
    return record_payment(folio, amount=Decimal(amount), method="bank_transfer", reference="TRX-1")


def sold(room_type, day):
    row = InventoryDay.objects.filter(room_type=room_type, date=day).first()
    return row.sold_units if row else 0


class TestCheckIn:
    def test_checks_in_an_arrival_in_a_clean_room(
        self, hotel, owner, django_capture_on_commit_callbacks, signal_log
    ):
        stay = new_stay(hotel, room=hotel.rooms["101"])

        with django_capture_on_commit_callbacks(execute=True):
            result = check_in(stay, actor=owner)

        stay = fresh(stay)
        assert isinstance(result, Stay)
        assert (stay.status, stay.reservation.status) == ("checked_in", "checked_in")
        assert stay.checked_in_at is not None
        assert [kw["stay"].pk for kw in signal_log.of("stay_checked_in")] == [stay.pk]
        event = AuditEvent.objects.get(action="bookings.stay_checked_in")
        assert (event.actor, event.target_id) == (owner, str(stay.pk))

    def test_an_inspected_room_is_ready(self, hotel):
        set_status(hotel.rooms["101"], "inspected")
        check_in(new_stay(hotel, room=hotel.rooms["101"]))

    @pytest.mark.parametrize("status", ["dirty", "out_of_service"])
    def test_a_room_that_is_not_ready_needs_force(self, hotel, status):
        set_status(hotel.rooms["101"], status)
        stay = new_stay(hotel, room=hotel.rooms["101"])
        with pytest.raises(RoomNotReadyError) as error:
            check_in(stay)
        assert error.value.status_code == 409
        assert fresh(stay).status == "confirmed"
        check_in(stay, force=True)
        assert fresh(stay).status == "checked_in"

    def test_without_room_the_first_clean_room_is_assigned(self, hotel):
        set_status(hotel.rooms["101"], "dirty")
        stay = new_stay(hotel)
        check_in(stay)
        assert (fresh(stay).room, fresh(stay).status) == (hotel.rooms["102"], "checked_in")

    def test_without_any_free_room_it_fails(self, hotel):
        for number in ("101", "102", "201"):
            new_stay(hotel, room=hotel.rooms[number])
        stay = new_stay(hotel, allow_overbooking=True)
        with pytest.raises(InvalidStateError):
            check_in(stay)

    def test_the_arrival_date_must_have_come(self, hotel):
        stay = new_stay(hotel, oct_(2), oct_(4), room=hotel.rooms["101"])
        with pytest.raises(InvalidStateError):
            check_in(stay, force=True)

    def test_a_late_arrival_needs_force(self, hotel):
        stay = new_stay(hotel, oct_(1), oct_(4), room=hotel.rooms["101"])
        set_business_date(hotel, oct_(2))
        with pytest.raises(InvalidStateError):
            check_in(stay)
        check_in(stay, force=True)
        assert fresh(stay).status == "checked_in"

    def test_a_stay_that_already_ended_needs_force(self, hotel):
        """Registering a past stay after the fact (e.g. loading history) is a forced, late check-in."""
        stay = new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["101"])
        set_business_date(hotel, oct_(3))
        with pytest.raises(InvalidStateError):
            check_in(stay)
        check_in(stay, force=True)
        assert fresh(stay).status == "checked_in"

    def test_a_tentative_reservation_needs_force_and_loses_its_hold(self, hotel):
        stay = new_stay(hotel, room=hotel.rooms["101"], status="tentative")
        with pytest.raises(InvalidStateError):
            check_in(stay)
        check_in(stay, force=True)
        reservation = Reservation.objects.get(pk=stay.reservation_id)
        assert (reservation.status, reservation.hold_expires_at) == ("checked_in", None)

    def test_the_other_rooms_of_a_tentative_reservation_are_confirmed_when_the_guest_arrives(self, hotel):
        req = reservation_request(
            hotel,
            [stay_request(hotel, oct_(1), oct_(3)), stay_request(hotel, oct_(1), oct_(3))],
            status="tentative",
        )
        first, second = create_reservation(req).stays.order_by("created_at")

        check_in(first, force=True)

        assert (fresh(first).status, fresh(second).status) == ("checked_in", "confirmed")

    @pytest.mark.parametrize("status", ["checked_in", "checked_out", "cancelled", "no_show"])
    def test_only_expected_stays_check_in(self, hotel, status):
        stay = new_stay(hotel, room=hotel.rooms["101"])
        Stay.objects.filter(pk=stay.pk).update(status=status)
        with pytest.raises(InvalidStateError):
            check_in(stay, force=True)

    def test_the_iva_exemption_is_refreshed_with_the_guest_data(self, hotel):
        stay = new_stay(hotel, room=hotel.rooms["101"])  # booked as a resident: 761.600
        booker = stay.reservation.booker
        booker.nationality, booker.country_of_residence = "FR", "FR"
        booker.save()

        check_in(stay)

        stay = fresh(stay)
        assert stay.nightly_rates == [entry(oct_(1), 320000, 320000, 0), entry(oct_(2), 320000, 320000, 0)]
        assert (stay.total_amount, stay.reservation.total_amount) == (Decimal("640000"), Decimal("640000"))


class TestCheckOut:
    @pytest.fixture
    def in_house(self, hotel):
        stay = new_stay(hotel, oct_(1), oct_(3), room=hotel.rooms["101"])
        check_in(stay)
        set_business_date(hotel, oct_(3))
        return fresh(stay)

    def test_requires_the_balance_to_be_settled(self, hotel, in_house):
        with pytest.raises(BalanceDueError) as error:
            check_out(in_house)
        assert (error.value.status_code, error.value.extra["amount"]) == (409, Decimal("761600"))
        assert fresh(in_house).status == "checked_in"
        assert not Charge.objects.filter(stay=in_house).exists()  # rolled back

    def test_posts_the_nights_and_leaves_the_room_dirty(
        self, hotel, in_house, owner, django_capture_on_commit_callbacks, signal_log
    ):
        pay(in_house, "761600")

        with django_capture_on_commit_callbacks(execute=True):
            result = check_out(in_house, actor=owner)

        stay = fresh(in_house)
        assert isinstance(result, Stay)
        assert (stay.status, stay.reservation.status) == ("checked_out", "checked_out")
        assert stay.checked_out_at is not None
        assert sorted(Charge.objects.filter(stay=stay, kind="room").values_list("night_date", flat=True)) == [
            oct_(1),
            oct_(2),
        ]
        assert Room.objects.get(pk=hotel.rooms["101"].pk).housekeeping_status == "dirty"
        assert [kw["stay"].pk for kw in signal_log.of("stay_checked_out")] == [stay.pk]
        assert [(kw["old"], kw["new"]) for kw in signal_log.of("room_status_changed")] == [("clean", "dirty")]
        assert AuditEvent.objects.filter(action="bookings.stay_checked_out", actor=owner).exists()

    def test_the_checkout_is_announced_before_the_room_turns_dirty(
        self, hotel, in_house, django_capture_on_commit_callbacks, signal_log
    ):
        """Housekeeping (C2) creates the departure cleaning from `stay_checked_out` (it knows the arrival of
        today) before the generic `room_status_changed` → dirty arrives."""
        with django_capture_on_commit_callbacks(execute=True):
            check_out(in_house, force=True)
        names = [name for name, _kwargs in signal_log if name in ("stay_checked_out", "room_status_changed")]
        assert names == ["stay_checked_out", "room_status_changed"]

    def test_force_checks_out_with_an_open_balance(self, hotel, in_house):
        check_out(in_house, force=True)
        assert fresh(in_house).status == "checked_out"
        assert AuditEvent.objects.get(action="bookings.stay_checked_out").changes["balance_due"] == [
            None,
            "761600.00",
        ]

    def test_an_early_departure_frees_the_future_nights(self, hotel):
        stay = new_stay(hotel, oct_(1), oct_(4), room=hotel.rooms["101"])
        check_in(stay)
        set_business_date(hotel, oct_(2))
        pay(stay, "380800")

        check_out(stay)

        stay = fresh(stay)
        assert (stay.checkout_date, stay.total_amount, stay.nightly_rates) == (
            oct_(2),
            Decimal("380800"),
            [entry(oct_(1), 380800, 320000, 60800)],
        )
        assert (stay.reservation.checkout_date, stay.reservation.total_amount) == (oct_(2), Decimal("380800"))
        assert list(Charge.objects.filter(stay=stay).values_list("night_date", flat=True)) == [oct_(1)]
        assert (sold(hotel.dbl, oct_(2)), sold(hotel.dbl, oct_(3))) == (0, 0)

    def test_leaving_on_the_arrival_day_still_counts_one_night(self, hotel):
        stay = new_stay(hotel, oct_(1), oct_(4), room=hotel.rooms["101"])
        check_in(stay)
        check_out(stay, force=True)
        assert fresh(stay).checkout_date == oct_(1) + timedelta(days=1)

    def test_the_nights_a_check_out_frees_from_today_on_are_announced(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        """The guest leaves on the arrival day: tonight is sellable again (channels must hear about it)."""
        stay = new_stay(hotel, oct_(1), oct_(4), room=hotel.rooms["101"])
        check_in(stay)

        with django_capture_on_commit_callbacks(execute=True):
            check_out(stay, force=True)

        freed = {
            night
            for kwargs in signal_log.of("inventory_changed")
            for night in (
                kwargs["start"] + timedelta(days=n) for n in range((kwargs["end"] - kwargs["start"]).days)
            )
        }
        assert freed == {oct_(1), oct_(2), oct_(3)}
        assert sold(hotel.dbl, oct_(1)) == 0

    def test_a_regular_check_out_announces_nothing_about_past_nights(
        self, hotel, in_house, django_capture_on_commit_callbacks, signal_log
    ):
        with django_capture_on_commit_callbacks(execute=True):
            check_out(in_house, force=True)
        assert signal_log.of("inventory_changed") == []

    def test_the_reservation_checks_out_with_its_last_stay(self, hotel):
        req = reservation_request(
            hotel, [stay_request(hotel, oct_(1), oct_(2)), stay_request(hotel, oct_(1), oct_(2))]
        )
        reservation = create_reservation(req)
        first, second = reservation.stays.all()
        for stay in (first, second):
            check_in(stay)
        set_business_date(hotel, oct_(2))

        check_out(first, force=True)
        assert Reservation.objects.get(pk=reservation.pk).status == "checked_in"
        check_out(second, force=True)
        assert Reservation.objects.get(pk=reservation.pk).status == "checked_out"

    @pytest.mark.parametrize("status", ["confirmed", "checked_out", "cancelled"])
    def test_only_in_house_stays_check_out(self, hotel, status):
        stay = new_stay(hotel, room=hotel.rooms["101"])
        Stay.objects.filter(pk=stay.pk).update(status=status)
        with pytest.raises(InvalidStateError):
            check_out(stay, force=True)
