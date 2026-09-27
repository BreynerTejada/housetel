"""`/api/v1/inventory/blocks/`: out-of-order rooms or beds for date ranges (`end_date` exclusive)."""

from datetime import date, timedelta

import pytest

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.signals import inventory_changed
from apps.inventory.models import RoomBlock
from apps.inventory.services import block_room
from apps.inventory.tests.conftest import BASE
from apps.inventory.tests.factories import BedFactory, DormRoomTypeFactory, RoomFactory, RoomTypeFactory

pytestmark = pytest.mark.django_db
URL = f"{BASE}/blocks/"
OCT = lambda day: date(2026, 10, day)  # noqa: E731


@pytest.fixture
def room(prop):
    return RoomFactory(room_type=RoomTypeFactory(property=prop), number="101")


def payload(room, **extra):
    return {"room": str(room.pk), "start_date": "2026-10-01", "end_date": "2026-10-04", "kind": "maintenance",
            "reason": "Pintura", **extra}  # fmt: skip


class TestCreate:
    def test_blocks_through_the_service_and_signals(self, api, prop, owner, room, capture):
        responses = []
        received = capture(inventory_changed, lambda: responses.append(api.post(URL, payload(room))))
        assert responses[0].status_code == 201, responses[0].json()
        body = responses[0].json()
        fields = ("room_number", "start_date", "end_date", "kind", "is_active")
        assert [body[field] for field in fields] == ["101", "2026-10-01", "2026-10-04", "maintenance", True]
        assert RoomBlock.objects.get(pk=body["id"]).created_by == owner
        assert received == [
            {"property": prop, "room_type_ids": [room.room_type_id], "start": OCT(1), "end": OCT(4)}
        ]

    def test_overlapping_blocks_answer_409(self, api, room):
        api.post(URL, payload(room))
        response = api.post(URL, payload(room, start_date="2026-10-03", end_date="2026-10-06"))
        assert (response.status_code, response.json()["code"]) == (409, "block_overlap")

    def test_rooms_with_reservations_in_the_period_need_force(self, api, prop, room):
        reservation = ReservationFactory(property=prop, checkin_date=OCT(2), checkout_date=OCT(5))
        StayFactory(reservation=reservation, room_type=room.room_type, room=room)
        response = api.post(URL, payload(room))
        assert (response.status_code, response.json()["code"]) == (409, "room_has_reservations")
        assert response.json()["reservations"] == [reservation.code]
        assert api.post(URL, payload(room, force=True)).status_code == 201

    @pytest.mark.parametrize(
        ("extra", "field"),
        [
            ({"end_date": "2026-10-01"}, "end_date"),
            ({"kind": "party"}, "kind"),
            ({"start_date": "tomorrow"}, "start_date"),
        ],
    )
    def test_validation(self, api, room, extra, field):
        response = api.post(URL, payload(room, **extra))
        assert response.status_code == 400 and field in response.json()["fields"], response.json()

    def test_a_bed_must_belong_to_the_room(self, api, prop):
        dorm = RoomFactory(room_type=DormRoomTypeFactory(property=prop))
        other_bed = BedFactory(room=RoomFactory(room_type=dorm.room_type))
        response = api.post(URL, payload(dorm, bed=str(other_bed.pk)))
        assert response.status_code == 400 and "bed" in response.json()["fields"]

    def test_a_room_of_another_property_is_rejected(self, api):
        foreign = RoomFactory()
        response = api.post(URL, payload(foreign))
        assert response.status_code == 400 and "room" in response.json()["fields"]


class TestListAndRelease:
    def test_lists_blocks_with_filters(self, api, prop, room):
        other = RoomFactory(room_type=room.room_type, number="102")
        active = block_room(room, start=OCT(1), end=OCT(3), kind="maintenance", reason="")
        released = block_room(other, start=OCT(1), end=OCT(3), kind="owner_hold", reason="")
        released.released_at = released.created_at
        released.save()

        body = api.get(URL).json()
        assert body["count"] == 2  # paginated
        assert [row["id"] for row in api.get(f"{URL}?active=true").json()["results"]] == [str(active.pk)]
        assert [row["id"] for row in api.get(f"{URL}?room={other.pk}").json()["results"]] == [
            str(released.pk)
        ]

    def test_filters_by_overlap_with_a_range(self, api, room):
        early = block_room(room, start=OCT(1), end=OCT(3), kind="maintenance", reason="")
        block_room(room, start=OCT(10), end=OCT(12), kind="maintenance", reason="")
        rows = api.get(f"{URL}?start=2026-10-02&end=2026-10-05").json()["results"]
        assert [row["id"] for row in rows] == [str(early.pk)]

    def test_release(self, api, prop, room, capture):
        block = block_room(room, start=OCT(1), end=OCT(3), kind="maintenance", reason="")
        responses = []
        received = capture(inventory_changed, lambda: responses.append(api.post(f"{URL}{block.pk}/release/")))
        assert responses[0].status_code == 200
        assert (responses[0].json()["is_active"], responses[0].json()["released_at"] is not None) == (
            False,
            True,
        )
        assert len(received) == 1

    def test_blocks_of_another_property_are_not_reachable(self, api):
        foreign = block_room(RoomFactory(), start=OCT(1), end=OCT(3), kind="maintenance", reason="")
        assert api.post(f"{URL}{foreign.pk}/release/").status_code == 404
        assert api.get(URL).json()["count"] == 0

    def test_today_is_the_default_business_date_for_active_blocks(self, api, prop, room):
        start = prop.business_date - timedelta(days=5)
        block_room(room, start=start, end=start + timedelta(days=2), kind="maintenance", reason="")  # past
        assert api.get(f"{URL}?current=true").json()["count"] == 0
