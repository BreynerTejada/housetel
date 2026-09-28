"""ARI values sent to a channel: availability per night, and per mapped rate the plan price (derived plans
resolved) × (1 + markup/100) with the base plan restrictions."""

from decimal import Decimal

import pytest

from apps.bookings.services.reservations import create_reservation
from apps.bookings.tests.helpers import guest_input, oct_, stay_request
from apps.bookings.types import ReservationRequest
from apps.distribution.services.ari import build_batch
from apps.distribution.services.queue import ARI_KINDS
from apps.distribution.tests.factories import connect
from apps.rates.tests.factories import DailyRateFactory, DerivedRatePlanFactory, RatePlanFactory

pytestmark = pytest.mark.django_db


def prices(batch) -> dict:
    return {rate.external_rate_id: [day.price for day in rate.days] for rate in batch.rates}


def test_prices_resolve_derived_plans_and_add_the_markup(hotel):
    non_refundable = DerivedRatePlanFactory(
        property=hotel.prop,
        parent=hotel.plan,
        code="NR",
        derivation_type="percent",
        derivation_value=Decimal("-12"),
        room_types=[hotel.dbl],
    )
    breakfast = DerivedRatePlanFactory(
        property=hotel.prop,
        parent=hotel.plan,
        code="BB",
        derivation_type="amount",
        derivation_value=Decimal("35000"),
        room_types=[hotel.dbl],
    )
    connection = connect(
        hotel, room_types=[hotel.dbl], plans=[hotel.plan, non_refundable, breakfast], markup="15"
    )

    batch = build_batch(connection, hotel.dbl, oct_(5), oct_(7), ARI_KINDS)

    # 320.000 × 1,15 · 320.000 × 0,88 × 1,15 · (320.000 + 35.000) × 1,15
    assert prices(batch) == {
        "BS-BAR": [Decimal("368000"), Decimal("368000")],
        "BS-NR": [Decimal("323840"), Decimal("323840")],
        "BS-BB": [Decimal("408250"), Decimal("408250")],
    }
    assert batch.external_room_id == "BS-DBL"
    assert [day.date for day in batch.rates[0].days] == [oct_(5), oct_(6)]


def test_each_mapping_applies_its_own_markup_and_rounds_to_whole_pesos(hotel):
    connection = connect(hotel, room_types=[hotel.ste], plans=[], markup="0")
    connection.rate_mappings.create(rate_plan=hotel.plan, external_rate_id="BS-BAR", markup_percent="12.5")

    batch = build_batch(connection, hotel.ste, oct_(5), oct_(6), ARI_KINDS)

    assert prices(batch) == {"BS-BAR": [Decimal("731250")]}  # 650.000 × 1,125


def test_restrictions_come_from_the_base_plan_rows(hotel):
    derived = DerivedRatePlanFactory(
        property=hotel.prop, parent=hotel.plan, code="NR", room_types=[hotel.dbl]
    )
    derived.min_los_default = 3
    derived.save(update_fields=["min_los_default"])
    DailyRateFactory(
        room_type=hotel.dbl,
        rate_plan=hotel.plan,
        date=oct_(5),
        price=Decimal("300000"),
        min_los=2,
        max_los=7,
        closed_to_arrival=True,
    )
    DailyRateFactory(
        room_type=hotel.dbl,
        rate_plan=hotel.plan,
        date=oct_(6),
        price=Decimal("300000"),
        closed_to_departure=True,
        stop_sell=True,
    )
    connection = connect(hotel, room_types=[hotel.dbl], plans=[hotel.plan, derived])

    batch = build_batch(connection, hotel.dbl, oct_(5), oct_(8), ARI_KINDS)
    by_rate = {rate.external_rate_id: rate.days for rate in batch.rates}

    base = [
        (d.min_los, d.max_los, d.closed_to_arrival, d.closed_to_departure, d.stop_sell)
        for d in by_rate["BS-BAR"]
    ]
    assert base == [
        (2, 7, True, False, False),
        (None, None, False, True, True),
        (None, None, False, False, False),
    ]
    # the derived plan shares the rows; nights without their own minimum take the plan default
    assert [d.min_los for d in by_rate["BS-NR"]] == [2, 3, 3]
    assert [d.stop_sell for d in by_rate["BS-NR"]] == [False, True, False]


def test_availability_counts_reservations_and_never_goes_below_zero(hotel):
    connection = connect(hotel, room_types=[hotel.ste])
    booking = ReservationRequest(
        property=hotel.prop,
        booker=guest_input(),
        stays=[stay_request(hotel, oct_(5), oct_(7), room_type=hotel.ste)],
        source="phone",
    )
    create_reservation(booking)
    overbooked = ReservationRequest(
        property=hotel.prop,
        booker=guest_input(),
        stays=[stay_request(hotel, oct_(6), oct_(7), room_type=hotel.ste)],
        source="ota",
        allow_overbooking=True,
        enforce_restrictions=False,
    )
    create_reservation(overbooked)

    batch = build_batch(connection, hotel.ste, oct_(4), oct_(8), ARI_KINDS)

    assert batch.availability == {oct_(4): 1, oct_(5): 0, oct_(6): 0, oct_(7): 1}


def test_rates_that_cannot_be_sold_on_the_channel_are_closed(hotel):
    private = RatePlanFactory(property=hotel.prop, code="CORP", is_public=False, room_types=[hotel.dbl])
    direct_only = RatePlanFactory(property=hotel.prop, code="WEB", room_types=[hotel.dbl])
    direct_only.channels = ["direct", "marketplace"]
    direct_only.save(update_fields=["channels"])
    inactive = RatePlanFactory(property=hotel.prop, code="OLD", is_active=False, room_types=[hotel.dbl])
    other_category = RatePlanFactory(property=hotel.prop, code="STEONLY", room_types=[hotel.ste])
    connection = connect(
        hotel, room_types=[hotel.dbl], plans=[hotel.plan, private, direct_only, inactive, other_category]
    )

    batch = build_batch(connection, hotel.dbl, oct_(5), oct_(6), ARI_KINDS)
    closed = {rate.external_rate_id: rate.days[0].stop_sell for rate in batch.rates}

    assert closed == {
        "BS-BAR": False,
        "BS-CORP": True,
        "BS-WEB": True,
        "BS-OLD": True,
        "BS-STEONLY": True,
    }


def test_a_rate_whose_plan_was_deleted_or_has_no_price_is_closed(hotel):
    unpriced = RatePlanFactory(property=hotel.prop, code="NOPRICE", room_types=[hotel.dbl])
    connection = connect(hotel, room_types=[hotel.dbl], plans=[hotel.plan, unpriced])
    connection.rate_mappings.create(rate_plan=None, external_rate_id="BS-GONE")

    batch = build_batch(connection, hotel.dbl, oct_(5), oct_(6), ARI_KINDS)
    days = {rate.external_rate_id: rate.days[0] for rate in batch.rates}

    assert (days["BS-NOPRICE"].price, days["BS-NOPRICE"].stop_sell) == (None, True)
    assert (days["BS-GONE"].price, days["BS-GONE"].stop_sell) == (None, True)
    assert (days["BS-BAR"].price, days["BS-BAR"].stop_sell) == (Decimal("320000"), False)


def test_a_rate_mapped_to_one_category_only_applies_there(hotel):
    connection = connect(hotel, "channex", room_types=[hotel.dbl, hotel.ste], plans=[])
    connection.rate_mappings.create(rate_plan=hotel.plan, room_type=hotel.dbl, external_rate_id="ch-rp-dbl")
    connection.rate_mappings.create(rate_plan=hotel.plan, room_type=hotel.ste, external_rate_id="ch-rp-ste")

    dbl = build_batch(connection, hotel.dbl, oct_(5), oct_(6), ARI_KINDS)
    ste = build_batch(connection, hotel.ste, oct_(5), oct_(6), ARI_KINDS)

    assert prices(dbl) == {"ch-rp-dbl": [Decimal("320000")]}
    assert prices(ste) == {"ch-rp-ste": [Decimal("650000")]}
