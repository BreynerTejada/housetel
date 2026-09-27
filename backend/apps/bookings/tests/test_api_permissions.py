"""Every bookings endpoint (plan §B.11): the permission it needs and tenant isolation.

- A housekeeper (no `bookings.*`) gets 403 with the missing code on every endpoint.
- The accountant (`bookings.view` only) reads but gets 403 `bookings.manage` / `bookings.checkin` /
  `bookings.cancel` on writes.
- Another organization's member can neither use this property (404) nor reach its objects from theirs (404).
"""

import pytest

from apps.accounts.services import ensure_system_roles
from apps.bookings.tests.factories import ReservationGroupFactory
from apps.bookings.tests.helpers import book, oct_
from apps.core.tests.factories import OrganizationFactory, PropertyFactory

pytestmark = pytest.mark.django_db

BASE = "/api/v1/bookings/"
DATES = {"checkin": "2026-10-01", "checkout": "2026-10-03"}


@pytest.fixture
def objects(hotel):
    reservation = book(hotel, oct_(1), oct_(3))
    return {
        "reservation": reservation.pk,
        "stay": reservation.stays.get().pk,
        "group": ReservationGroupFactory(property=hotel.prop).pk,
    }


def endpoints(ids):
    """(method, path, body/query, permission)."""
    r, s, g = ids["reservation"], ids["stay"], ids["group"]
    return [
        ("get", "reservations/", {}, "bookings.view"),
        ("post", "reservations/", {}, "bookings.manage"),
        ("get", f"reservations/{r}/", {}, "bookings.view"),
        ("patch", f"reservations/{r}/", {"notes": "x"}, "bookings.manage"),
        ("post", f"reservations/{r}/cancel/", {"confirm": True}, "bookings.cancel"),
        ("get", f"reservations/{r}/cancel-preview/", {}, "bookings.view"),
        ("post", f"reservations/{r}/confirm/", {}, "bookings.manage"),
        ("post", f"reservations/{r}/no-show/", {}, "bookings.manage"),
        ("get", f"stays/{s}/", {}, "bookings.view"),
        ("post", f"stays/{s}/modify/", {"checkout": "2026-10-04"}, "bookings.manage"),
        ("post", f"stays/{s}/modify-preview/", {"checkout": "2026-10-04"}, "bookings.manage"),
        ("get", f"stays/{s}/room-options/", {}, "bookings.view"),
        ("post", f"stays/{s}/assign/", {}, "bookings.manage"),
        ("post", f"stays/{s}/unassign/", {}, "bookings.manage"),
        ("post", f"stays/{s}/check-in/", {}, "bookings.checkin"),
        ("post", f"stays/{s}/check-out/", {}, "bookings.checkin"),
        ("post", f"stays/{s}/occupants/", {}, "bookings.manage"),
        ("delete", f"stays/{s}/occupants/", {}, "bookings.manage"),
        ("get", "availability/", DATES, "bookings.view"),
        ("get", "offers/", DATES, "bookings.view"),
        ("get", "calendar/", {"start": "2026-10-01", "end": "2026-10-03"}, "bookings.view"),
        ("post", "auto-assign/", {"date_from": "2026-10-01", "date_to": "2026-10-01"}, "bookings.manage"),
        ("get", "groups/", {}, "bookings.view"),
        ("post", "groups/", {"name": "G"}, "bookings.manage"),
        ("get", f"groups/{g}/", {}, "bookings.view"),
        ("patch", f"groups/{g}/", {"name": "H"}, "bookings.manage"),
        ("put", f"groups/{g}/", {"name": "H"}, "bookings.manage"),
        ("delete", f"groups/{g}/", {}, "bookings.manage"),
        ("post", "inventory/rebuild/", {}, "bookings.manage"),
    ]


def call(client, method, path, data):
    if method == "get":
        return client.get(f"{BASE}{path}", data)
    return getattr(client, method)(f"{BASE}{path}", data, format="json")


def test_a_housekeeper_is_refused_everywhere_with_the_missing_permission(
    hotel, objects, api_for, make_member
):
    client = api_for(make_member("housekeeping"), hotel.prop)
    for method, path, data, permission in endpoints(objects):
        response = call(client, method, path, data)
        assert (response.status_code, response.json().get("permission")) == (403, permission), (method, path)


def test_the_accountant_reads_but_does_not_write(hotel, objects, api_for, make_member):
    client = api_for(make_member("accountant"), hotel.prop)
    for method, path, data, permission in endpoints(objects):
        response = call(client, method, path, data)
        if permission == "bookings.view":
            assert response.status_code == 200, (method, path, response.json())
        else:
            assert (response.status_code, response.json().get("permission")) == (403, permission), (
                method,
                path,
            )


def test_another_organization_reaches_nothing(hotel, objects, api_for, make_member):
    stranger_org = OrganizationFactory()
    ensure_system_roles(stranger_org)
    stranger = make_member("owner", org=stranger_org)
    on_our_property = api_for(stranger, hotel.prop)
    on_theirs = api_for(stranger, PropertyFactory(organization=stranger_org))
    our_ids = [str(pk) for pk in objects.values()]
    for method, path, data, _permission in endpoints(objects):
        assert call(on_our_property, method, path, data).status_code == 404, (method, path)
        if any(pk in path for pk in our_ids):  # our objects do not exist on their property
            assert call(on_theirs, method, path, data).status_code == 404, (method, path)
