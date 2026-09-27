"""InventoryDay: `rebuild_inventory` (materialization from source tables), `availability` read from it,
and the `inventory_changed` receiver (plan B2b › Inventario).

Units = active rooms (private) or active beds of active rooms (dorm). Per night: sold = active stays
covering the night (counted in the category of their assigned room, else of the stay); blocked = distinct
units under an active block (a dorm room block blocks all its active beds).
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.bookings.models import InventoryDay
from apps.bookings.services.availability import availability, availability_by_date
from apps.bookings.services.inventory import inventory_horizon, rebuild_inventory
from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.bookings.tests.helpers import oct_
from apps.core import signals
from apps.inventory.models import RoomBlock
from apps.inventory.services import block_room, release_block
from apps.inventory.tests.factories import BedFactory, RoomFactory

pytestmark = pytest.mark.django_db


def put_stay(hotel, room_type, checkin, checkout, *, status="confirmed", room=None, bed=None):
    reservation = ReservationFactory(
        property=hotel.prop, checkin_date=checkin, checkout_date=checkout, status=status
    )
    return StayFactory(
        reservation=reservation, room_type=room_type, rate_plan=hotel.plan, room=room, bed=bed, status=status
    )


def rows(hotel, room_type):
    """{date: (total, sold, blocked)} of a category."""
    return {
        day.date: (day.total_units, day.sold_units, day.blocked_units)
        for day in InventoryDay.objects.filter(room_type=room_type)
    }


class TestRebuild:
    def test_creates_one_row_per_category_and_night_with_the_active_units(self, hotel):
        RoomFactory(room_type=hotel.dbl, number="199", is_active=False)
        BedFactory(room=hotel.dorm, label="X", is_active=False)
        closed_dorm = RoomFactory(room_type=hotel.dorm_type, number="D2", is_active=False)
        BedFactory(room=closed_dorm, label="A")

        result = rebuild_inventory(hotel.prop, oct_(1), oct_(4))

        assert result.created == 9 and result.updated == 0
        assert rows(hotel, hotel.dbl) == {oct_(d): (3, 0, 0) for d in (1, 2, 3)}
        assert rows(hotel, hotel.ste) == {oct_(d): (1, 0, 0) for d in (1, 2, 3)}
        assert rows(hotel, hotel.dorm_type) == {oct_(d): (4, 0, 0) for d in (1, 2, 3)}
        assert set(InventoryDay.objects.values_list("property_id", flat=True)) == {hotel.prop.pk}

    def test_sold_units_are_the_active_stays_covering_each_night(self, hotel):
        put_stay(hotel, hotel.dbl, oct_(1), oct_(4))  # unassigned
        put_stay(hotel, hotel.dbl, oct_(2), oct_(3), status="tentative", room=hotel.rooms["101"])
        put_stay(hotel, hotel.dbl, oct_(3), oct_(5), status="checked_in", room=hotel.rooms["102"])
        for status in ("cancelled", "no_show", "checked_out"):
            put_stay(hotel, hotel.dbl, oct_(1), oct_(4), status=status)

        rebuild_inventory(hotel.prop, oct_(1), oct_(5))

        assert {day: sold for day, (_, sold, _) in rows(hotel, hotel.dbl).items()} == {
            oct_(1): 1,
            oct_(2): 2,
            oct_(3): 2,
            oct_(4): 1,
        }

    def test_each_dorm_stay_is_one_bed(self, hotel):
        put_stay(hotel, hotel.dorm_type, oct_(1), oct_(3), room=hotel.dorm, bed=hotel.beds["A"])
        put_stay(hotel, hotel.dorm_type, oct_(1), oct_(2), room=hotel.dorm, bed=hotel.beds["B"])
        put_stay(hotel, hotel.dorm_type, oct_(1), oct_(2))  # no bed yet

        rebuild_inventory(hotel.prop, oct_(1), oct_(3))

        assert rows(hotel, hotel.dorm_type) == {oct_(1): (4, 3, 0), oct_(2): (4, 1, 0)}

    def test_an_upgraded_stay_uses_a_unit_of_its_assigned_room_category(self, hotel):
        put_stay(hotel, hotel.dbl, oct_(1), oct_(2), room=hotel.rooms["301"])  # DBL booked, sleeps in STE

        rebuild_inventory(hotel.prop, oct_(1), oct_(2))

        assert rows(hotel, hotel.dbl) == {oct_(1): (3, 0, 0)}
        assert rows(hotel, hotel.ste) == {oct_(1): (1, 1, 0)}

    def test_blocked_units_are_distinct_units_under_active_blocks(self, hotel):
        room = hotel.rooms["101"]
        RoomBlock.objects.create(room=room, start_date=oct_(1), end_date=oct_(3), kind="maintenance")
        RoomBlock.objects.create(
            room=room, start_date=oct_(2), end_date=oct_(4), kind="owner_hold"
        )  # overlaps
        RoomBlock.objects.create(
            room=hotel.rooms["102"], start_date=oct_(1), end_date=oct_(4), released_at=timezone.now()
        )
        closed = RoomFactory(room_type=hotel.dbl, number="199", is_active=False)
        RoomBlock.objects.create(room=closed, start_date=oct_(1), end_date=oct_(4))
        RoomBlock.objects.create(room=hotel.dorm, bed=hotel.beds["A"], start_date=oct_(1), end_date=oct_(4))
        RoomBlock.objects.create(room=hotel.dorm, start_date=oct_(3), end_date=oct_(4))  # the whole dorm

        rebuild_inventory(hotel.prop, oct_(1), oct_(4))

        assert {day: blocked for day, (_, _, blocked) in rows(hotel, hotel.dbl).items()} == {
            oct_(1): 1,
            oct_(2): 1,
            oct_(3): 1,
        }
        assert {day: blocked for day, (_, _, blocked) in rows(hotel, hotel.dorm_type).items()} == {
            oct_(1): 1,
            oct_(2): 1,
            oct_(3): 4,
        }

    def test_is_idempotent_and_reports_the_drift_it_repairs(self, hotel):
        put_stay(hotel, hotel.dbl, oct_(1), oct_(3))
        rebuild_inventory(hotel.prop, oct_(1), oct_(3))

        again = rebuild_inventory(hotel.prop, oct_(1), oct_(3))
        assert (again.created, again.updated, again.drift) == (0, 0, [])

        InventoryDay.objects.filter(room_type=hotel.dbl, date=oct_(2)).update(sold_units=5, blocked_units=2)
        repaired = rebuild_inventory(hotel.prop, oct_(1), oct_(3))

        assert (repaired.created, repaired.updated) == (0, 1)
        assert repaired.drift == [
            {
                "room_type_id": str(hotel.dbl.pk),
                "date": "2026-10-02",
                "sold_units": [5, 1],
                "blocked_units": [2, 0],
            }
        ]
        assert rows(hotel, hotel.dbl)[oct_(2)] == (3, 1, 0)

    def test_missing_rows_are_inserted_in_the_global_lock_order(self, hotel, monkeypatch):
        """Two processes materializing overlapping ranges insert the same keys; both must insert them in one
        order — (room type, date), the order rows are locked everywhere — or their INSERTs can deadlock (a
        Python set iterates in a different order in every process)."""
        inserted = []
        real_bulk_create = InventoryDay.objects.bulk_create

        def recording_bulk_create(objs, *args, **kwargs):
            objs = list(objs)
            inserted.extend((str(obj.room_type_id), obj.date) for obj in objs)
            return real_bulk_create(objs, *args, **kwargs)

        monkeypatch.setattr(InventoryDay.objects, "bulk_create", recording_bulk_create)

        rebuild_inventory(hotel.prop, oct_(1), oct_(31))

        assert len(inserted) == 3 * 30
        assert inserted == sorted(inserted)

    def test_can_be_limited_to_some_categories(self, hotel):
        rebuild_inventory(hotel.prop, oct_(1), oct_(2), room_type_ids=[hotel.ste.pk])
        assert set(InventoryDay.objects.values_list("room_type_id", flat=True)) == {hotel.ste.pk}

    def test_without_a_range_it_covers_the_default_horizon(self, hotel):
        start, end = inventory_horizon(hotel.prop)
        assert (start, end) == (oct_(1) - timedelta(days=7), oct_(1) + timedelta(days=541))

        rebuild_inventory(hotel.prop, room_type_ids=[hotel.dbl.pk])

        dates = InventoryDay.objects.filter(room_type=hotel.dbl).values_list("date", flat=True)
        assert (min(dates), max(dates), len(dates)) == (start, end - timedelta(days=1), 548)


class TestAvailability:
    def test_reads_the_materialized_rows(self, hotel):
        rebuild_inventory(hotel.prop, oct_(1), oct_(4))
        InventoryDay.objects.filter(room_type=hotel.dbl, date=oct_(2)).update(sold_units=2)

        assert availability(property=hotel.prop, checkin=oct_(1), checkout=oct_(4)) == {
            hotel.dbl.pk: 1,  # the minimum over the nights
            hotel.ste.pk: 1,
            hotel.dorm_type.pk: 4,
        }

    def test_builds_the_rows_it_is_missing(self, hotel):
        put_stay(hotel, hotel.dbl, oct_(2), oct_(3))

        assert availability(property=hotel.prop, checkin=oct_(1), checkout=oct_(4))[hotel.dbl.pk] == 2
        assert InventoryDay.objects.filter(room_type=hotel.dbl).count() == 3

    def test_can_be_negative_when_a_category_is_overbooked(self, hotel):
        rebuild_inventory(hotel.prop, oct_(1), oct_(2))
        InventoryDay.objects.filter(room_type=hotel.ste).update(sold_units=2)
        assert availability(property=hotel.prop, checkin=oct_(1), checkout=oct_(2))[hotel.ste.pk] == -1

    def test_only_active_categories_are_listed_and_can_be_filtered(self, hotel):
        hotel.ste.is_active = False
        hotel.ste.save()
        assert set(availability(property=hotel.prop, checkin=oct_(1), checkout=oct_(2))) == {
            hotel.dbl.pk,
            hotel.dorm_type.pk,
        }
        only_dorm = availability(
            property=hotel.prop, checkin=oct_(1), checkout=oct_(2), room_type_ids=[hotel.dorm_type.pk]
        )
        assert only_dorm == {hotel.dorm_type.pk: 4}

    def test_an_empty_range_has_nothing_available(self, hotel):
        result = availability(property=hotel.prop, checkin=oct_(3), checkout=oct_(3))
        assert result == {hotel.dbl.pk: 0, hotel.ste.pk: 0, hotel.dorm_type.pk: 0}


class TestAvailabilityByDate:
    """`availability_by_date` (range contract asked by B2a for the rate grid): every night of `[start, end)`
    per active category in one call, from InventoryDay."""

    def test_gives_every_night_of_every_active_category(self, hotel):
        rebuild_inventory(hotel.prop, oct_(1), oct_(4))
        InventoryDay.objects.filter(room_type=hotel.dbl, date=oct_(2)).update(sold_units=2)
        InventoryDay.objects.filter(room_type=hotel.dorm_type, date=oct_(3)).update(sold_units=5)
        hotel.ste.is_active = False
        hotel.ste.save()

        result = availability_by_date(property=hotel.prop, start=oct_(1), end=oct_(4))

        assert result == {
            hotel.dbl.pk: {oct_(1): 3, oct_(2): 1, oct_(3): 3},
            hotel.dorm_type.pk: {oct_(1): 4, oct_(2): 4, oct_(3): -1},
        }

    def test_builds_missing_rows_and_filters_categories(self, hotel):
        put_stay(hotel, hotel.dbl, oct_(2), oct_(3))
        result = availability_by_date(
            property=hotel.prop, start=oct_(1), end=oct_(3), room_type_ids=[hotel.dbl.pk]
        )
        assert result == {hotel.dbl.pk: {oct_(1): 3, oct_(2): 2}}

    def test_an_empty_range_has_no_nights(self, hotel):
        result = availability_by_date(property=hotel.prop, start=oct_(3), end=oct_(3))
        assert result == {hotel.dbl.pk: {}, hotel.ste.pk: {}, hotel.dorm_type.pk: {}}
        assert not InventoryDay.objects.exists()


class TestInventoryChangedReceiver:
    def test_blocking_and_releasing_a_room_update_availability(
        self, hotel, django_capture_on_commit_callbacks
    ):
        rebuild_inventory(hotel.prop, oct_(1), oct_(4))

        with django_capture_on_commit_callbacks(execute=True):
            block = block_room(
                hotel.rooms["101"], start=oct_(2), end=oct_(3), kind="maintenance", reason="Pintura"
            )
        assert availability(property=hotel.prop, checkin=oct_(1), checkout=oct_(4))[hotel.dbl.pk] == 2
        assert rows(hotel, hotel.dbl)[oct_(2)] == (3, 0, 1)

        with django_capture_on_commit_callbacks(execute=True):
            release_block(block)
        assert availability(property=hotel.prop, checkin=oct_(1), checkout=oct_(4))[hotel.dbl.pk] == 3

    def test_an_event_without_range_rebuilds_the_whole_horizon(
        self, hotel, django_capture_on_commit_callbacks
    ):
        rebuild_inventory(hotel.prop, oct_(1), oct_(2))
        room = hotel.rooms["201"]
        room.is_active = False
        room.save()

        with django_capture_on_commit_callbacks(execute=True):
            signals.send_on_commit(
                signals.inventory_changed,
                property=hotel.prop,
                room_type_ids=[hotel.dbl.pk],
                start=None,
                end=None,
            )

        totals = set(InventoryDay.objects.filter(room_type=hotel.dbl).values_list("total_units", flat=True))
        assert totals == {2}
        assert InventoryDay.objects.filter(room_type=hotel.dbl).count() == 548

    def test_events_emitted_by_bookings_itself_are_not_rebuilt_again(
        self, hotel, django_capture_on_commit_callbacks
    ):
        rebuild_inventory(hotel.prop, oct_(1), oct_(2))
        InventoryDay.objects.filter(room_type=hotel.dbl).update(sold_units=2)
        event = {"property": hotel.prop, "room_type_ids": [hotel.dbl.pk], "start": oct_(1), "end": oct_(2)}

        with django_capture_on_commit_callbacks(execute=True):
            signals.send_on_commit(signals.inventory_changed, origin="bookings", **event)
        assert rows(hotel, hotel.dbl)[oct_(1)] == (3, 2, 0)  # already maintained incrementally

        with django_capture_on_commit_callbacks(execute=True):
            signals.send_on_commit(signals.inventory_changed, **event)
        assert rows(hotel, hotel.dbl)[oct_(1)] == (3, 0, 0)
