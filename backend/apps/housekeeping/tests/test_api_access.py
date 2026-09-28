"""Every housekeeping endpoint: anonymous → 401, another organization or property → 404, a role without the
permission → 403 naming the permission (plan §B.11)."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.housekeeping.services import tickets as ticket_svc
from apps.housekeeping.tests.conftest import JPEG
from apps.housekeeping.tests.factories import HousekeepingTaskFactory

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("private_media")]
BASE = "/api/v1/housekeeping/"

# (method, path, body, permission a role without any housekeeping permission is asked for)
ENDPOINTS = [
    ("get", "tasks/", None, "housekeeping.view"),
    ("post", "tasks/", {"room_id": "{room}", "kind": "deep_clean"}, "housekeeping.supervise"),
    ("get", "tasks/{task}/", None, "housekeeping.view"),
    ("patch", "tasks/{task}/", {"priority": "high"}, "housekeeping.supervise"),
    ("post", "tasks/{task}/start/", {}, "housekeeping.work"),
    ("post", "tasks/{task}/finish/", {}, "housekeeping.work"),
    ("post", "tasks/{task}/inspect/", {}, "housekeeping.supervise"),
    ("post", "tasks/{task}/assign/", {"user_id": None}, "housekeeping.supervise"),
    ("post", "tasks/{task}/cancel/", {}, "housekeeping.supervise"),
    ("post", "tasks/auto-assign/", {}, "housekeeping.supervise"),
    ("post", "tasks/generate/", {}, "housekeeping.supervise"),
    ("get", "board/", None, "housekeeping.view"),
    ("get", "summary/", None, "housekeeping.view"),
    ("get", "staff/", None, "housekeeping.view"),
    ("get", "settings/", None, "housekeeping.view"),
    ("patch", "settings/", {"auto_assign": False}, "housekeeping.supervise"),
    ("post", "rooms/{room}/status/", {"housekeeping_status": "dirty"}, "housekeeping.work"),
    ("get", "tickets/", None, "housekeeping.view"),
    ("post", "tickets/", {"title": "Fuga"}, "housekeeping.work"),
    ("get", "tickets/{ticket}/", None, "housekeeping.view"),
    ("patch", "tickets/{ticket}/", {"title": "Otra"}, "housekeeping.maintenance"),
    ("delete", "tickets/{ticket}/", None, "housekeeping.supervise"),
    ("post", "tickets/{ticket}/start/", {}, "housekeeping.maintenance"),
    ("post", "tickets/{ticket}/resolve/", {}, "housekeeping.maintenance"),
    ("post", "tickets/{ticket}/cancel/", {}, "housekeeping.maintenance"),
    ("post", "tickets/{ticket}/photos/", "photo", "housekeeping.work"),
    ("delete", "tickets/{ticket}/photos/{photo}/", None, "housekeeping.work"),
    ("get", "ticket-photos/{photo}/file/", None, "housekeeping.view"),
]
IDS = [f"{method} {path}" for method, path, _body, _permission in ENDPOINTS]


@pytest.fixture
def objects(hotel):
    task = HousekeepingTaskFactory(room=hotel.rooms["101"])
    ticket = ticket_svc.create_ticket(hotel.prop, room=hotel.rooms["102"], title="Espejo")
    photo = ticket_svc.add_photo(ticket, file=SimpleUploadedFile("p.jpg", JPEG))
    return {"task": task.pk, "ticket": ticket.pk, "photo": photo.pk, "room": hotel.rooms["201"].pk}


def call(client, method, path, body, objects):
    url = BASE + path.format(**objects)
    if body == "photo":
        return client.post(url, {"image": SimpleUploadedFile("p.jpg", JPEG)}, format="multipart")
    if isinstance(body, dict):
        body = {
            key: value.format(**objects) if isinstance(value, str) else value for key, value in body.items()
        }
    return getattr(client, method)(url, body) if body is not None else getattr(client, method)(url)


@pytest.mark.parametrize(("method", "path", "body", "permission"), ENDPOINTS, ids=IDS)
def test_anonymous_requests_are_refused(hotel, objects, public_api, method, path, body, permission):
    public_api.credentials(HTTP_X_PROPERTY_ID=str(hotel.prop.pk))
    assert call(public_api, method, path, body, objects).status_code == 401


@pytest.mark.parametrize(("method", "path", "body", "permission"), ENDPOINTS, ids=IDS)
def test_another_organization_never_reaches_the_hotel(
    hotel, objects, api_for, method, path, body, permission
):
    from apps.accounts.services import add_member, ensure_system_roles
    from apps.accounts.tests.factories import UserFactory

    other_org = OrganizationFactory(status="active")
    ensure_system_roles(other_org)
    stranger = UserFactory()
    add_member(other_org, stranger, "owner", all_properties=True)

    response = call(api_for(stranger, hotel.prop), method, path, body, objects)

    assert response.status_code == 404


OBJECT_ENDPOINTS = [endpoint for endpoint in ENDPOINTS if "{" in endpoint[1]]  # paths with an object id


@pytest.mark.parametrize(
    ("method", "path", "body", "permission"),
    OBJECT_ENDPOINTS,
    ids=[f"{e[0]} {e[1]}" for e in OBJECT_ENDPOINTS],
)
def test_objects_of_another_hotel_of_the_chain_are_not_found(
    hotel, objects, api_for, make_member, method, path, body, permission
):
    """An owner working in another hotel of the same organization (header = that hotel)."""
    sibling = PropertyFactory(organization=hotel.prop.organization)
    response = call(api_for(make_member("owner"), sibling), method, path, body, objects)
    assert response.status_code == 404


@pytest.mark.parametrize(("method", "path", "body", "permission"), ENDPOINTS, ids=IDS)
def test_a_role_without_housekeeping_permissions_is_told_which_one_it_lacks(
    hotel, objects, api_for, make_member, method, path, body, permission
):
    accountant = make_member("accountant")

    response = call(api_for(accountant, hotel.prop), method, path, body, objects)

    assert (response.status_code, response.json()["code"], response.json()["permission"]) == (
        403,
        "permission_denied",
        permission,
    )
