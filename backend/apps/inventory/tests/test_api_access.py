"""Every inventory endpoint: tenant isolation and permissions (`inventory.view` reads, `inventory.manage`
writes; housekeeping and front desk only read)."""

import pytest
from rest_framework.test import APIClient

from apps.inventory.services import block_room
from apps.inventory.tests.conftest import BASE
from apps.inventory.tests.factories import BedFactory, DormRoomTypeFactory, RoomFactory, RoomTypeFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def objects(prop):
    room_type = RoomTypeFactory(property=prop)
    room = RoomFactory(room_type=room_type)
    dorm = RoomFactory(room_type=DormRoomTypeFactory(property=prop), number="D1")
    bed = BedFactory(room=dorm)
    block = block_room(room, start=prop.business_date, end=prop.business_date.replace(year=2099),
                       kind="maintenance", reason="")  # fmt: skip
    return {"room_type": room_type, "room": room, "dorm": dorm, "bed": bed, "block": block}


def reads(o):
    return [
        "/property/",
        "/amenities/",
        "/room-types/",
        f"/room-types/{o['room_type'].pk}/",
        f"/room-types/{o['room_type'].pk}/photos/",
        "/property/photos/",
        "/rooms/",
        f"/rooms/{o['room'].pk}/",
        f"/rooms/{o['room'].pk}/effective/",
        f"/rooms/{o['dorm'].pk}/beds/",
        "/custom-fields/",
        "/blocks/",
        "/summary/",
    ]


def writes(o):
    return [
        ("patch", "/property/", {"name": "X"}),
        ("post", "/amenities/", {"code": "x", "name": "X"}),
        ("post", "/room-types/", {"name": "X"}),
        ("patch", f"/room-types/{o['room_type'].pk}/", {"color": "#000000"}),
        ("delete", f"/room-types/{o['room_type'].pk}/", None),
        ("post", f"/room-types/{o['room_type'].pk}/duplicate/", {}),
        ("post", f"/room-types/{o['room_type'].pk}/photos/reorder/", {"ids": []}),
        ("post", "/rooms/", {"room_type": str(o["room_type"].pk), "number": "999"}),
        ("patch", f"/rooms/{o['room'].pk}/", {"floor": "9"}),
        ("delete", f"/rooms/{o['room'].pk}/", None),
        ("post", "/rooms/bulk-create/", {"room_type": str(o["room_type"].pk), "numbers": "900"}),
        ("post", "/rooms/bulk-update/", {"ids": [str(o["room"].pk)], "set": {"floor": "9"}}),
        ("post", f"/rooms/{o['room'].pk}/reset-override/", {"field": "view"}),
        ("post", f"/rooms/{o['room'].pk}/status/", {"housekeeping_status": "dirty"}),
        ("post", f"/rooms/{o['dorm'].pk}/beds/", {"label": "Z1"}),
        ("post", f"/rooms/{o['dorm'].pk}/beds/bulk/", {"count": 1}),
        ("patch", f"/rooms/{o['dorm'].pk}/beds/{o['bed'].pk}/", {"label": "Z2"}),
        ("post", "/custom-fields/", {"applies_to": "room", "key": "x", "label": "X"}),
        (
            "post",
            "/blocks/",
            {
                "room": str(o["room"].pk),
                "start_date": "2030-01-01",
                "end_date": "2030-01-02",
                "kind": "maintenance",
            },
        ),  # fmt: skip
        ("post", f"/blocks/{o['block'].pk}/release/", {}),
    ]


def call(client, method, path, data=None):
    return getattr(client, method)(f"{BASE}{path}", data)


def test_anonymous_requests_are_rejected(objects, prop):
    client = APIClient()
    client.credentials(HTTP_X_PROPERTY_ID=str(prop.pk))
    for path in reads(objects):
        assert client.get(f"{BASE}{path}").status_code == 401, path


def test_another_organization_never_reaches_our_property(stranger_api, objects):
    for path in reads(objects):
        assert stranger_api.get(f"{BASE}{path}").status_code == 404, path
    for method, path, data in writes(objects):
        assert call(stranger_api, method, path, data).status_code == 404, path


@pytest.mark.parametrize("client_fixture", ["hk_api", "front_api"])
def test_read_only_roles_read_but_never_write(request, objects, client_fixture):
    client = request.getfixturevalue(client_fixture)
    for path in reads(objects):
        assert client.get(f"{BASE}{path}").status_code == 200, path
    for method, path, data in writes(objects):
        response = call(client, method, path, data)
        assert (response.status_code, response.json()["permission"]) == (403, "inventory.manage"), path


def test_objects_of_another_property_of_the_same_organization_are_hidden(api, organization):
    from apps.core.tests.factories import PropertyFactory

    sister = PropertyFactory(organization=organization)
    room_type = RoomTypeFactory(property=sister)
    room = RoomFactory(room_type=room_type)
    assert api.get(f"{BASE}/room-types/{room_type.pk}/").status_code == 404
    assert api.get(f"{BASE}/rooms/{room.pk}/").status_code == 404
    assert api.get(f"{BASE}/room-types/").json() == []
