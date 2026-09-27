"""`search_offers` (spec §4.2, plan B2b): active categories with room for the party × applicable active
plans → quote → kept when the restrictions are met and there are enough units; cheapest first.

Offer.quote is per unit; Offer.total = quote.total × units_needed (private: 1 room; dorm: 1 bed per guest).
Conftest prices for one night (IVA 19 % on the subtotal): DBL 380.800 · STE 773.500 · DORM bed 77.350.
"""

from decimal import Decimal

import pytest

from apps.bookings.services.availability import search_offers
from apps.bookings.tests.helpers import book, oct_
from apps.rates.models import DailyRate, PromoCode
from apps.rates.tests.factories import RatePlanFactory

pytestmark = pytest.mark.django_db


def offers(hotel, **kwargs):
    params = {"property": hotel.prop, "checkin": oct_(1), "checkout": oct_(2), "adults": 2}
    params.update(kwargs)
    return search_offers(**params)


def summary(result):
    return [(offer.room_type_id, offer.rate_plan_id, offer.units_needed, offer.total) for offer in result]


def derived(hotel, code, value="-12", room_types=None, **kwargs):
    return RatePlanFactory(
        property=hotel.prop,
        code=code,
        kind="derived",
        parent=hotel.plan,
        derivation_value=Decimal(value),
        room_types=room_types or [hotel.dbl],
        **kwargs,
    )


def test_every_category_with_room_times_every_applicable_plan_cheapest_first(hotel):
    nonref = derived(hotel, "NR")  # DBL 320.000 − 12 % = 281.600 + 19 % = 335.104

    result = offers(hotel)

    assert summary(result) == [
        (hotel.dorm_type.pk, hotel.plan.pk, 2, Decimal("154700")),
        (hotel.dbl.pk, nonref.pk, 1, Decimal("335104")),
        (hotel.dbl.pk, hotel.plan.pk, 1, Decimal("380800")),
        (hotel.ste.pk, hotel.plan.pk, 1, Decimal("773500")),
    ]
    dorm = result[0]
    assert (dorm.available_units, dorm.quote.total, dorm.quote.adults) == (4, Decimal("77350"), 1)
    assert (result[2].available_units, result[2].quote.checkin, result[2].quote.checkout) == (
        3,
        oct_(1),
        oct_(2),
    )


def test_the_party_must_fit_the_category(hotel):
    assert {offer.room_type_id for offer in offers(hotel, adults=3)} == {hotel.dorm_type.pk}
    with_child = offers(hotel, adults=2, children=1, children_ages=[6])
    assert {offer.room_type_id for offer in with_child} == {hotel.dbl.pk, hotel.ste.pk}  # dorm takes no kids


def test_channels_decide_which_plans_apply(hotel):
    corporate = derived(hotel, "CORP", "-5", is_public=False)
    marketplace = derived(hotel, "MKT", "0", channels=["marketplace"])
    ota = derived(hotel, "OTA", "0", channels=["booksim"])

    def plans(channel):
        return {
            offer.rate_plan_id
            for offer in offers(hotel, channel=channel)
            if offer.room_type_id == hotel.dbl.pk
        }

    assert plans("direct") == {hotel.plan.pk, corporate.pk}
    assert plans("marketplace") == {hotel.plan.pk, marketplace.pk}
    assert plans("booking_engine") == {hotel.plan.pk}
    assert plans("booksim") == {hotel.plan.pk, ota.pk}


def test_categories_without_enough_units_are_left_out(hotel):
    for _ in range(3):
        book(hotel, oct_(1), oct_(2))
    book(hotel, oct_(1), oct_(2), room_type=hotel.dorm_type, adults=3)

    assert {offer.room_type_id for offer in offers(hotel, adults=2)} == {hotel.ste.pk}
    (dorm,) = [offer for offer in offers(hotel, adults=1) if offer.room_type_id == hotel.dorm_type.pk]
    assert (dorm.available_units, dorm.units_needed) == (1, 1)


def test_plans_whose_restrictions_fail_are_left_out(hotel):
    nonref = derived(hotel, "NR")
    DailyRate.objects.create(
        room_type=hotel.dbl, rate_plan=hotel.plan, date=oct_(1), price=Decimal("320000"), stop_sell=True
    )
    remaining = {(offer.room_type_id, offer.rate_plan_id) for offer in offers(hotel)}
    assert (hotel.dbl.pk, hotel.plan.pk) not in remaining
    assert (hotel.dbl.pk, nonref.pk) not in remaining  # derived plans use their base plan's restrictions
    assert (hotel.ste.pk, hotel.plan.pk) in remaining


def test_categories_without_a_price_are_left_out(hotel):
    hotel.ste.rate_defaults.all().delete()
    assert hotel.ste.pk not in {offer.room_type_id for offer in offers(hotel)}


def test_inactive_plans_and_categories_are_left_out(hotel):
    derived(hotel, "OLD", is_active=False)
    hotel.ste.is_active = False
    hotel.ste.save()
    assert summary(offers(hotel)) == [
        (hotel.dorm_type.pk, hotel.plan.pk, 2, Decimal("154700")),
        (hotel.dbl.pk, hotel.plan.pk, 1, Decimal("380800")),
    ]


def test_a_plan_applies_only_to_its_categories(hotel):
    only_ste = derived(hotel, "STEX", "0", room_types=[hotel.ste])
    assert {offer.room_type_id for offer in offers(hotel) if offer.rate_plan_id == only_ste.pk} == {
        hotel.ste.pk
    }


def test_foreign_non_residents_are_quoted_without_iva(hotel):
    (dbl,) = [
        offer
        for offer in offers(hotel, guest_is_foreign_non_resident=True)
        if offer.room_type_id == hotel.dbl.pk
    ]
    assert dbl.total == Decimal("320000")
    assert dbl.quote.taxes[0].exempt is True


def test_the_promo_code_is_passed_to_the_quote(hotel):
    PromoCode.objects.create(
        property=hotel.prop, code="BIENVENIDA10", discount_type="percent", value=Decimal("10")
    )
    (dbl,) = [
        offer for offer in offers(hotel, promo_code="BIENVENIDA10") if offer.room_type_id == hotel.dbl.pk
    ]
    assert dbl.quote.promo_applied == "BIENVENIDA10"
    assert dbl.total < Decimal("380800")


def test_several_nights_and_an_empty_range(hotel):
    (dbl,) = [offer for offer in offers(hotel, checkout=oct_(4)) if offer.room_type_id == hotel.dbl.pk]
    assert (len(dbl.quote.nights), dbl.total) == (3, Decimal("1142400"))
    assert offers(hotel, checkout=oct_(1)) == []
