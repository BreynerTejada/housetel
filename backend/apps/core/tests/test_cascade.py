"""Deleting an organization removes its whole graph (seed --reset relies on it), while deleting a row that
history depends on (room type with rooms, room or guest with stays, reservation with a folio) is refused."""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db.models import RestrictedError

from apps.accounts.models import User
from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.models import Organization
from apps.finance.models import Refund
from apps.finance.tests.factories import ChargeFactory, FolioFactory, PaymentFactory
from apps.inventory.models import RoomBlock
from apps.inventory.tests.factories import BedFactory, DormRoomTypeFactory, RoomFactory, RoomTypeFactory
from apps.rates.tests.factories import ExtraFactory, RoomTypeRateDefaultsFactory, TaxFactory

pytestmark = pytest.mark.django_db

DOMAIN_MODELS = [
    "core.Property", "inventory.RoomType", "inventory.Room", "inventory.Bed", "inventory.RoomBlock",
    "rates.Tax", "rates.RatePlan", "rates.RoomTypeRateDefaults", "rates.Extra", "bookings.Reservation",
    "bookings.Stay", "guests.Guest", "finance.Folio", "finance.Charge", "finance.Payment", "finance.Refund",
    "accounts.Role", "accounts.Membership",
]  # fmt: skip


@pytest.fixture
def graph(prop, owner):
    room_type = RoomTypeFactory(property=prop)
    room = RoomFactory(room_type=room_type, number="101")
    dorm = RoomFactory(room_type=DormRoomTypeFactory(property=prop), number="D1")
    bed = BedFactory(room=dorm)
    RoomBlock.objects.create(
        room=room, start_date="2026-12-01", end_date="2026-12-03", kind="maintenance", created_by=owner
    )
    tax = TaxFactory(property=prop)
    defaults = RoomTypeRateDefaultsFactory(room_type=room_type)
    reservation = ReservationFactory(property=prop)
    stay = StayFactory(
        reservation=reservation,
        room_type=room_type,
        rate_plan=defaults.rate_plan,
        room=room,
        occupants=[reservation.booker],
    )
    StayFactory(
        reservation=reservation, room_type=dorm.room_type, rate_plan=defaults.rate_plan, room=dorm, bed=bed
    )
    folio = FolioFactory(reservation=reservation, stay=stay)
    ChargeFactory(
        folio=folio,
        kind="extra",
        tax=tax,
        extra=ExtraFactory(property=prop, tax=tax),
        stay=stay,
        posted_by=owner,
    )
    payment = PaymentFactory(folio=folio, received_by=owner)
    Refund.objects.create(payment=payment, amount=Decimal("1000"), status="approved", approved_by=owner)
    return {"room_type": room_type, "room": room, "reservation": reservation}


def test_deleting_the_organization_removes_the_whole_graph_but_keeps_users(graph, prop, owner):
    before = {label: apps.get_model(label).objects.count() for label in DOMAIN_MODELS}
    assert all(count > 0 for count in before.values()), before

    Organization.objects.filter(pk=prop.organization_id).delete()

    after = {label: apps.get_model(label).objects.count() for label in DOMAIN_MODELS}
    assert after == dict.fromkeys(DOMAIN_MODELS, 0)
    assert User.objects.filter(pk=owner.pk).exists()


def test_a_room_type_with_rooms_cannot_be_deleted_directly(graph):
    with pytest.raises(RestrictedError):
        graph["room_type"].delete()


def test_a_room_with_stays_cannot_be_deleted_directly(graph):
    with pytest.raises(RestrictedError):
        graph["room"].delete()


def test_a_guest_who_booked_cannot_be_deleted_directly(graph):
    with pytest.raises(RestrictedError):
        graph["reservation"].booker.delete()


def test_a_reservation_with_a_folio_cannot_be_deleted_directly(graph):
    with pytest.raises(RestrictedError):
        graph["reservation"].delete()


def test_deleting_a_user_keeps_their_audit_trail_rows(graph, owner, prop):
    from apps.inventory.models import RoomBlock as Block

    assert Block.objects.filter(created_by=owner).exists()
    # CashShift.user is PROTECT (money history); other user references are SET_NULL.
    owner.memberships.all().delete()
    owner.delete()
    assert Block.objects.filter(created_by__isnull=True).count() == 1
