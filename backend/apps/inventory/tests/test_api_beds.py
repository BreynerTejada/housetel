"""`/api/v1/inventory/rooms/{id}/beds/`: sellable beds of dorm rooms."""

import pytest

from apps.bookings.tests.factories import StayFactory
from apps.core.signals import inventory_changed
from apps.inventory.models import Bed
from apps.inventory.tests.conftest import BASE
from apps.inventory.tests.factories import BedFactory, DormRoomTypeFactory, RoomFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def dorm(prop):
    return RoomFactory(room_type=DormRoomTypeFactory(property=prop), number="D1")


def beds_url(room, suffix=""):
    return f"{BASE}/rooms/{room.pk}/beds/{suffix}"


def test_lists_the_beds_of_a_dorm_room_in_natural_order(api, dorm):
    for label in ("C10", "C2", "C1"):
        BedFactory(room=dorm, label=label)
    response = api.get(beds_url(dorm))
    assert response.status_code == 200
    assert [bed["label"] for bed in response.json()] == ["C1", "C2", "C10"]
    assert set(response.json()[0]) >= {"id", "label", "bed_type", "is_active"}


def test_creates_a_bed_and_signals(api, prop, dorm, capture):
    responses = []
    received = capture(
        inventory_changed,
        lambda: responses.append(api.post(beds_url(dorm), {"label": "A1", "bed_type": "bunk_bottom"})),
    )
    assert responses[0].status_code == 201, responses[0].json()
    assert Bed.objects.get(room=dorm).label == "A1"
    assert received == [{"property": prop, "room_type_ids": [dorm.room_type_id], "start": None, "end": None}]


def test_labels_are_unique_per_room(api, dorm):
    BedFactory(room=dorm, label="C1")
    response = api.post(beds_url(dorm), {"label": "C1"})
    assert response.status_code == 400 and "label" in response.json()["fields"]


def test_private_rooms_have_no_beds(api, prop):
    room = RoomFactory(room_type__property=prop)
    response = api.post(beds_url(room), {"label": "C1"})
    assert (response.status_code, response.json()["code"]) == (400, "not_a_dorm")


def test_bulk_continues_the_numbering(api, dorm):
    BedFactory(room=dorm, label="C1")
    BedFactory(room=dorm, label="C2")
    response = api.post(beds_url(dorm, "bulk/"), {"count": 3, "prefix": "C"})
    assert response.status_code == 201, response.json()
    assert sorted(Bed.objects.filter(room=dorm).values_list("label", flat=True)) == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
    ]
    assert [bed["label"] for bed in response.json()] == ["C3", "C4", "C5"]


@pytest.mark.parametrize("count", [0, 51, "x"])
def test_bulk_validates_the_count(api, dorm, count):
    assert api.post(beds_url(dorm, "bulk/"), {"count": count}).status_code == 400


def test_deactivating_a_bed_signals(api, prop, dorm, capture):
    bed = BedFactory(room=dorm)
    received = capture(
        inventory_changed, lambda: api.patch(beds_url(dorm, f"{bed.pk}/"), {"is_active": False})
    )
    assert Bed.objects.get(pk=bed.pk).is_active is False
    assert len(received) == 1


def test_deletes_a_free_bed(api, dorm):
    bed = BedFactory(room=dorm)
    assert api.delete(beds_url(dorm, f"{bed.pk}/")).status_code == 204
    assert not Bed.objects.filter(pk=bed.pk).exists()


def test_a_bed_with_reservations_is_in_use(api, prop, dorm):
    bed = BedFactory(room=dorm)
    StayFactory(reservation__property=prop, room_type=dorm.room_type, room=dorm, bed=bed)
    response = api.delete(beds_url(dorm, f"{bed.pk}/"))
    assert (response.status_code, response.json()["code"]) == (409, "bed_in_use")
    response = api.patch(beds_url(dorm, f"{bed.pk}/"), {"is_active": False})
    assert (response.status_code, response.json()["code"]) == (409, "bed_in_use")


def test_beds_of_another_room_are_not_reachable(api, prop, dorm):
    other_dorm = RoomFactory(room_type=dorm.room_type, number="D2")
    bed = BedFactory(room=other_dorm)
    assert api.patch(beds_url(dorm, f"{bed.pk}/"), {"label": "X"}).status_code == 404
