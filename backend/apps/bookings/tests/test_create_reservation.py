"""`create_reservation` (spec §4.2, plan B2b): atomic creation with inventory locking, capacity, availability,
restrictions, pricing (quote or channel prices) and folio.

Stay.nightly_rates stores per night `amount` (what the guest pays for the night: net + the lodging tax when it
is not included), `net` and `tax`; the stay total is their sum. With the conftest hotel:
DBL 320.000 + IVA 19 % = 380.800 per night.
"""

import re
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from apps.bookings.models import InventoryDay, Reservation
from apps.bookings.services.availability import availability
from apps.bookings.services.reservations import create_reservation
from apps.bookings.tests.factories import ReservationFactory, ReservationGroupFactory
from apps.bookings.tests.helpers import (
    book,
    entry,
    foreign_input,
    guest_input,
    oct_,
    reservation_request,
    stay_request,
)
from apps.bookings.types import AvailabilityError, BookingError, RestrictionError
from apps.core.models import Alert, AuditEvent
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.finance.models import Folio
from apps.guests.models import Guest
from apps.guests.tests.factories import GuestFactory
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import DailyRate
from apps.rates.tests.factories import CancellationPolicyFactory, RatePlanFactory

pytestmark = pytest.mark.django_db


def sold(room_type, day):
    """Sold units of a night (a night nobody touched has no row yet: nothing sold)."""
    row = InventoryDay.objects.filter(room_type=room_type, date=day).first()
    return row.sold_units if row else 0


class TestCreation:
    def test_creates_the_reservation_its_priced_stays_and_the_folio(self, hotel, owner):
        booker = guest_input(first_name="Laura", last_name="Gómez", document_number="52123456")

        reservation = book(hotel, oct_(1), oct_(3), booker=booker, actor=owner, notes="Aniversario")

        assert re.fullmatch(r"HT-[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}", reservation.code)
        assert (reservation.status, reservation.source, reservation.currency) == (
            "confirmed",
            "front_desk",
            "COP",
        )
        assert (reservation.checkin_date, reservation.checkout_date) == (oct_(1), oct_(3))
        assert (reservation.adults, reservation.children) == (2, 0)
        assert reservation.total_amount == Decimal("761600")
        assert (reservation.notes, reservation.created_by) == ("Aniversario", owner)
        assert reservation.booker.document_number == "52123456"
        assert reservation.booker.organization == hotel.prop.organization

        (stay,) = reservation.stays.all()
        assert (stay.room_type, stay.rate_plan, stay.status, stay.room) == (
            hotel.dbl,
            hotel.plan,
            "confirmed",
            None,
        )
        assert (stay.checkin_date, stay.checkout_date, stay.adults, stay.children) == (oct_(1), oct_(3), 2, 0)
        assert stay.nightly_rates == [
            entry(oct_(1), 380800, 320000, 60800),
            entry(oct_(2), 380800, 320000, 60800),
        ]
        assert stay.total_amount == Decimal("761600")
        assert Folio.objects.filter(reservation=reservation, folio_type="guest").count() == 1

    def test_takes_one_unit_per_night_and_checkout_night_stays_free(self, hotel):
        book(hotel, oct_(1), oct_(3))

        assert (sold(hotel.dbl, oct_(1)), sold(hotel.dbl, oct_(2)), sold(hotel.dbl, oct_(3))) == (1, 1, 0)
        assert availability(property=hotel.prop, checkin=oct_(1), checkout=oct_(3))[hotel.dbl.pk] == 2
        assert availability(property=hotel.prop, checkin=oct_(3), checkout=oct_(4))[hotel.dbl.pk] == 3

    def test_emits_reservation_created_and_inventory_changed_after_commit(
        self, hotel, django_capture_on_commit_callbacks, signal_log
    ):
        with django_capture_on_commit_callbacks(execute=True):
            reservation = book(hotel, oct_(1), oct_(3))
            assert signal_log == []

        assert [kwargs["reservation"] for kwargs in signal_log.of("reservation_created")] == [reservation]
        (changed,) = signal_log.of("inventory_changed")
        assert changed == {
            "property": hotel.prop,
            "room_type_ids": [hotel.dbl.pk],
            "start": oct_(1),
            "end": oct_(3),
            "origin": "bookings",
        }

    def test_audits_the_creation(self, hotel, owner):
        reservation = book(hotel, oct_(1), oct_(3), actor=owner)
        event = AuditEvent.objects.get(action="bookings.reservation_created")
        assert (event.target_id, event.actor, event.source) == (str(reservation.pk), owner, "user")
        assert event.property == hotel.prop and reservation.code in event.summary

    def test_channel_reservations_are_audited_as_channel(self, hotel):
        book(hotel, oct_(1), oct_(3), source="ota", channel_code="booksim", enforce_restrictions=False)
        assert AuditEvent.objects.get(action="bookings.reservation_created").source == "channel"

    def test_source_label_overrides_the_audit_source(self, hotel):
        req = reservation_request(hotel, [stay_request(hotel, oct_(1), oct_(2))])
        create_reservation(req, source_label="ai")
        assert AuditEvent.objects.get(action="bookings.reservation_created").source == "ai"

    def test_an_existing_guest_can_be_the_booker(self, hotel):
        guest = GuestFactory(organization=hotel.prop.organization)
        reservation = book(hotel, oct_(1), oct_(2), booker=guest)
        assert reservation.booker == guest

    def test_a_guest_of_another_organization_cannot_be_the_booker(self, hotel):
        stranger = GuestFactory(organization=OrganizationFactory())
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), booker=stranger)
        assert error.value.code == "invalid_guest"

    def test_occupants_are_upserted_and_attached(self, hotel):
        occupant = guest_input(first_name="Mateo", document_number="1001001")
        reservation = book(hotel, oct_(1), oct_(2), stay_kwargs={"occupants": [occupant]})
        (stay,) = reservation.stays.all()
        assert [guest.document_number for guest in stay.occupants.all()] == ["1001001"]
        assert Guest.objects.get(document_number="1001001").organization == hotel.prop.organization

    def test_a_multi_stay_reservation_spans_its_stays(self, hotel):
        req = reservation_request(
            hotel,
            [
                stay_request(hotel, oct_(1), oct_(3)),
                stay_request(hotel, oct_(2), oct_(5), room_type=hotel.ste, adults=1),
            ],
        )
        reservation = create_reservation(req)
        assert (reservation.checkin_date, reservation.checkout_date) == (oct_(1), oct_(5))
        assert (reservation.adults, reservation.children) == (3, 0)
        # STE 650.000 + 19 % = 773.500 × 3 nights
        assert reservation.total_amount == Decimal("761600") + Decimal("2320500")
        assert reservation.stays.count() == 2

    def test_the_cancellation_policy_is_snapshotted(self, hotel):
        policy = CancellationPolicyFactory(
            property=hotel.prop,
            free_until_hours_before=72,
            penalty_type="percent",
            penalty_value=Decimal("50"),
        )
        hotel.plan.cancellation_policy = policy
        hotel.plan.save()

        reservation = book(hotel, oct_(1), oct_(3))
        policy.free_until_hours_before = 1
        policy.save()

        snapshot = Reservation.objects.get(pk=reservation.pk).cancellation_policy_snapshot
        assert snapshot["id"] == str(policy.pk)
        assert (snapshot["non_refundable"], snapshot["free_until_hours_before"]) == (False, 72)
        assert (snapshot["penalty_type"], snapshot["penalty_value"]) == ("percent", "50.00")
        assert snapshot["name"] == policy.name

    def test_without_policy_the_snapshot_is_empty(self, hotel):
        assert book(hotel, oct_(1), oct_(2)).cancellation_policy_snapshot == {}

    def test_a_derived_plan_without_policy_inherits_its_parents(self, hotel):
        policy = CancellationPolicyFactory(property=hotel.prop, non_refundable=True)
        hotel.plan.cancellation_policy = policy
        hotel.plan.save()
        derived = RatePlanFactory(
            property=hotel.prop,
            code="NR",
            kind="derived",
            parent=hotel.plan,
            derivation_value=Decimal("-10"),
            room_types=[hotel.dbl],
        )
        reservation = book(hotel, oct_(1), oct_(2), plan=derived)
        assert reservation.cancellation_policy_snapshot["non_refundable"] is True
        # 320.000 − 10 % = 288.000 + 19 % = 342.720
        assert reservation.total_amount == Decimal("342720")

    def test_links_the_group(self, hotel):
        group = ReservationGroupFactory(property=hotel.prop, name="Boda Pérez")
        assert book(hotel, oct_(1), oct_(2), group_id=group.pk).group == group

    def test_a_group_of_another_property_is_rejected(self, hotel):
        group = ReservationGroupFactory(property=PropertyFactory(organization=hotel.prop.organization))
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), group_id=group.pk)
        assert error.value.code == "invalid_group"

    def test_retries_when_the_generated_code_collides(self, hotel, monkeypatch):
        ReservationFactory(property=hotel.prop, code="HT-AAAAAA")
        codes = iter(["HT-AAAAAA", "HT-BBBBBB"])
        monkeypatch.setattr("apps.bookings.models.generate_code", lambda prefix="HT", length=6: next(codes))
        assert book(hotel, oct_(1), oct_(2)).code == "HT-BBBBBB"


class TestPricing:
    def test_foreign_non_residents_do_not_pay_iva(self, hotel):
        reservation = book(hotel, oct_(1), oct_(3), booker=foreign_input())
        (stay,) = reservation.stays.all()
        assert stay.nightly_rates == [entry(oct_(1), 320000, 320000, 0), entry(oct_(2), 320000, 320000, 0)]
        assert reservation.total_amount == Decimal("640000")

    def test_an_included_tax_splits_the_night_price_into_net_and_tax(self, hotel):
        hotel.iva.included_in_price = True
        hotel.iva.save()
        hotel.dbl.rate_defaults.update(price=Decimal("380800"))
        (stay,) = book(hotel, oct_(1), oct_(2)).stays.all()
        assert stay.nightly_rates == [entry(oct_(1), 380800, 320000, 60800)]
        assert stay.total_amount == Decimal("380800")

    def test_the_tax_of_each_night_is_rounded_like_its_room_charge(self, hotel):
        DailyRate.objects.create(
            room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(1), price=Decimal("323840")
        )
        (stay,) = book(hotel, oct_(1), oct_(2)).stays.all()
        # 323.840 × 19 % = 61.529,6 → 61.530 (COP, half up)
        assert stay.nightly_rates == [entry(oct_(1), 385370, 323840, 61530)]

    def test_channel_nightly_rates_replace_the_quoted_prices(self, hotel):
        rates = [{"date": oct_(1), "amount": "300000"}, {"date": "2026-10-02", "amount": Decimal("310000")}]
        reservation = book(
            hotel,
            oct_(1),
            oct_(3),
            source="ota",
            channel_code="booksim",
            enforce_restrictions=False,
            stay_kwargs={"nightly_rates": rates},
        )
        (stay,) = reservation.stays.all()
        assert stay.nightly_rates == [
            entry(oct_(1), 357000, 300000, 57000),
            entry(oct_(2), 368900, 310000, 58900),
        ]
        assert reservation.total_amount == Decimal("725900")

    def test_channel_nightly_rates_must_cover_exactly_the_nights(self, hotel):
        with pytest.raises(BookingError) as error:
            book(
                hotel,
                oct_(1),
                oct_(3),
                stay_kwargs={"nightly_rates": [{"date": oct_(1), "amount": "300000"}]},
            )
        assert error.value.code == "invalid_nightly_rates"

    def test_a_category_without_price_cannot_be_sold_directly(self, hotel):
        hotel.ste.rate_defaults.all().delete()
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), room_type=hotel.ste)
        assert error.value.code == "no_rate"


class TestValidation:
    @pytest.mark.parametrize(
        "adults,children,ages",
        [(3, 0, []), (2, 2, [5, 7]), (0, 1, [5])],
        ids=["too-many-adults", "too-many-children", "no-adult"],
    )
    def test_capacity(self, hotel, adults, children, ages):
        with pytest.raises(BookingError) as error:
            book(
                hotel,
                oct_(1),
                oct_(2),
                adults=adults,
                stay_kwargs={"children": children, "children_ages": ages},
            )
        assert error.value.code == "capacity_exceeded"
        assert not Reservation.objects.exists()

    def test_the_occupancy_limit_applies_to_adults_and_children_together(self, hotel):
        hotel.dbl.max_occupancy = 2
        hotel.dbl.save()
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), adults=2, stay_kwargs={"children": 1, "children_ages": [4]})
        assert error.value.code == "capacity_exceeded"

    def test_children_ages_must_match_the_children(self, hotel):
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), adults=1, stay_kwargs={"children": 1, "children_ages": [4, 9]})
        assert error.value.code == "invalid_children_ages"

    def test_dates(self, hotel):
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(3), oct_(3))
        assert error.value.code == "invalid_dates"

    def test_a_reservation_needs_stays(self, hotel):
        with pytest.raises(BookingError) as error:
            create_reservation(reservation_request(hotel, []))
        assert error.value.code == "no_stays"

    def test_the_category_must_belong_to_the_property_and_be_active(self, hotel):
        foreign_type = RoomTypeFactory(property=PropertyFactory(organization=hotel.prop.organization))
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), room_type=foreign_type)
        assert error.value.code == "invalid_room_type"
        hotel.ste.is_active = False
        hotel.ste.save()
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), room_type=hotel.ste)
        assert error.value.code == "invalid_room_type"

    def test_the_plan_must_be_active_belong_to_the_property_and_include_the_category(self, hotel):
        only_ste = RatePlanFactory(property=hotel.prop, code="STEONLY", room_types=[hotel.ste])
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), plan=only_ste)
        assert error.value.code == "invalid_rate_plan"
        hotel.plan.is_active = False
        hotel.plan.save()
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2))
        assert error.value.code == "invalid_rate_plan"

    @pytest.mark.parametrize(
        "field,value,code",
        [
            ("status", "checked_in", "invalid_status"),
            ("source", "carrier_pigeon", "invalid_source"),
            ("guarantee", "gold", "invalid_guarantee"),
        ],
    )
    def test_status_source_and_guarantee_must_be_known(self, hotel, field, value, code):
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), **{field: value})
        assert error.value.code == code


class TestAvailability:
    def test_without_units_left_it_raises_409_and_takes_nothing(self, hotel):
        for _ in range(3):
            book(hotel, oct_(1), oct_(3))

        with pytest.raises(AvailabilityError) as error:
            book(hotel, oct_(2), oct_(4))

        assert (error.value.code, error.value.status_code) == ("no_availability", 409)
        assert error.value.extra["shortfalls"][0] == {
            "room_type_id": str(hotel.dbl.pk),
            "date": "2026-10-02",
            "available": 0,
            "requested": 1,
        }
        assert Reservation.objects.count() == 3
        assert (sold(hotel.dbl, oct_(2)), sold(hotel.dbl, oct_(3))) == (3, 0)

    def test_overbooking_is_allowed_on_request_and_raises_an_alert(self, hotel):
        for _ in range(3):
            book(hotel, oct_(1), oct_(3))

        reservation = book(hotel, oct_(2), oct_(4), allow_overbooking=True)

        assert sold(hotel.dbl, oct_(2)) == 4
        assert availability(property=hotel.prop, checkin=oct_(2), checkout=oct_(3))[hotel.dbl.pk] == -1
        alert = Alert.objects.get(kind="overbooking", resolved_at__isnull=True)
        assert (alert.property, alert.severity) == (hotel.prop, "critical")
        assert alert.data["reservation_id"] == str(reservation.pk)
        assert reservation.code in alert.title + alert.message

    def test_requested_room_is_assigned(self, hotel):
        reservation = book(
            hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["102"].pk, "locked_room": True}
        )
        (stay,) = reservation.stays.all()
        assert (stay.room, stay.locked_room) == (hotel.rooms["102"], True)

    def test_an_occupied_requested_room_rolls_everything_back(self, hotel):
        book(hotel, oct_(1), oct_(3), stay_kwargs={"room_id": hotel.rooms["102"].pk})
        with pytest.raises(AvailabilityError):
            book(hotel, oct_(2), oct_(4), stay_kwargs={"room_id": hotel.rooms["102"].pk})
        assert Reservation.objects.count() == 1
        assert sold(hotel.dbl, oct_(2)) == 1

    def test_a_requested_room_of_another_category_is_rejected(self, hotel):
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), stay_kwargs={"room_id": hotel.rooms["301"].pk})
        assert error.value.code == "category_mismatch"


class TestRestrictions:
    def test_stop_sell_blocks_direct_bookings(self, hotel):
        DailyRate.objects.create(
            room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(2), price=Decimal("320000"), stop_sell=True
        )
        with pytest.raises(RestrictionError) as error:
            book(hotel, oct_(1), oct_(3))
        assert (error.value.code, error.value.status_code) == ("restriction_violation", 400)
        assert error.value.extra["violations"] == ["stop_sell"]
        assert not Reservation.objects.exists()

    def test_min_los_blocks_a_too_short_stay(self, hotel):
        DailyRate.objects.create(
            room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(1), price=Decimal("320000"), min_los=3
        )
        with pytest.raises(RestrictionError) as error:
            book(hotel, oct_(1), oct_(3))
        assert "min_los" in error.value.extra["violations"]
        assert book(hotel, oct_(1), oct_(4)).stays.get().nights == [oct_(1), oct_(2), oct_(3)]

    def test_channel_bookings_skip_restrictions_but_not_availability(self, hotel):
        DailyRate.objects.create(
            room_type=hotel.dbl,
            rate_plan=hotel.plan,
            date=oct_(1),
            price=Decimal("320000"),
            min_los=5,
            stop_sell=True,
        )
        ota = {"source": "ota", "channel_code": "booksim", "enforce_restrictions": False}
        for _ in range(3):
            book(hotel, oct_(1), oct_(2), **ota)
        with pytest.raises(AvailabilityError):
            book(hotel, oct_(1), oct_(2), **ota)

    def test_an_invalid_promo_code_is_rejected(self, hotel):
        with pytest.raises(BookingError) as error:
            book(hotel, oct_(1), oct_(2), promo_code="NOEXISTE")
        assert error.value.code == "promo_invalid"


class TestTentative:
    @freeze_time("2026-10-01 13:00:00+00:00")
    def test_a_tentative_reservation_holds_inventory_for_hold_minutes(self, hotel):
        reservation = book(hotel, oct_(1), oct_(2), status="tentative", hold_minutes=30)
        assert reservation.status == "tentative"
        assert set(reservation.stays.values_list("status", flat=True)) == {"tentative"}
        assert reservation.hold_expires_at == datetime(2026, 10, 1, 13, 30, tzinfo=ZoneInfo("UTC"))
        assert sold(hotel.dbl, oct_(1)) == 1

    def test_a_confirmed_reservation_has_no_hold(self, hotel):
        assert book(hotel, oct_(1), oct_(2)).hold_expires_at is None


class TestDorms:
    def test_a_dorm_request_becomes_one_stay_per_bed(self, hotel):
        reservation = book(hotel, oct_(1), oct_(3), room_type=hotel.dorm_type, adults=3)

        stays = list(reservation.stays.all())
        assert len(stays) == 3
        assert {(stay.adults, stay.children, stay.total_amount) for stay in stays} == {
            (1, 0, Decimal("154700"))
        }
        # 65.000 + 19 % = 77.350 per bed-night
        assert stays[0].nightly_rates == [
            entry(oct_(1), 77350, 65000, 12350),
            entry(oct_(2), 77350, 65000, 12350),
        ]
        assert (reservation.adults, reservation.total_amount) == (3, Decimal("464100"))
        assert sold(hotel.dorm_type, oct_(1)) == 3

    def test_channel_prices_of_a_dorm_line_are_split_between_its_beds(self, hotel):
        reservation = book(
            hotel,
            oct_(1),
            oct_(2),
            room_type=hotel.dorm_type,
            adults=2,
            source="ota",
            channel_code="airsim",
            enforce_restrictions=False,
            stay_kwargs={"nightly_rates": [{"date": oct_(1), "amount": "130001"}]},
        )
        nets = sorted(Decimal(stay.nightly_rates[0]["net"]) for stay in reservation.stays.all())
        assert nets == [Decimal("65000"), Decimal("65001")]

    def test_a_dorm_room_request_gets_distinct_free_beds(self, hotel):
        book(
            hotel,
            oct_(1),
            oct_(2),
            room_type=hotel.dorm_type,
            adults=1,
            stay_kwargs={"room_id": hotel.dorm.pk, "bed_id": hotel.beds["A"].pk},
        )

        reservation = book(
            hotel,
            oct_(1),
            oct_(2),
            room_type=hotel.dorm_type,
            adults=2,
            stay_kwargs={"room_id": hotel.dorm.pk},
        )

        beds = {stay.bed.label for stay in reservation.stays.all()}
        assert len(beds) == 2 and "A" not in beds
        assert {stay.room for stay in reservation.stays.all()} == {hotel.dorm}

    def test_one_bed_cannot_hold_several_guests(self, hotel):
        with pytest.raises(BookingError) as error:
            book(
                hotel,
                oct_(1),
                oct_(2),
                room_type=hotel.dorm_type,
                adults=2,
                stay_kwargs={"room_id": hotel.dorm.pk, "bed_id": hotel.beds["A"].pk},
            )
        assert error.value.code == "capacity_exceeded"

    def test_children_are_not_accepted_in_a_dorm_that_does_not_allow_them(self, hotel):
        with pytest.raises(BookingError) as error:
            book(
                hotel,
                oct_(1),
                oct_(2),
                room_type=hotel.dorm_type,
                adults=1,
                stay_kwargs={"children": 1, "children_ages": [8]},
            )
        assert error.value.code == "capacity_exceeded"

    def test_no_beds_left_means_409(self, hotel):
        book(hotel, oct_(1), oct_(2), room_type=hotel.dorm_type, adults=3)
        with pytest.raises(AvailabilityError):
            book(hotel, oct_(1), oct_(2), room_type=hotel.dorm_type, adults=2)
