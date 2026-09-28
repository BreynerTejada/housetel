"""`GET /api/v1/frontdesk/today/` (frontdesk.view): shape, permissions, tenancy and query budget."""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.bookings.tests.helpers import oct_
from apps.frontdesk.tests.helpers import arrived, new_stay

pytestmark = pytest.mark.django_db

URL = "/api/v1/frontdesk/today/"


class TestToday:
    def test_front_desk_reads_the_board_of_the_active_property(self, hotel, front_desk, api_for):
        stay = new_stay(hotel, oct_(1), oct_(3), room=hotel.rooms["101"])
        arrived(hotel, oct_(0), oct_(1), room=hotel.rooms["102"])

        response = api_for(front_desk, hotel.prop).get(URL)

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "business_date",
            "calendar_date",
            "currency",
            "kpis",
            "arrivals",
            "departures",
            "in_house",
            "rooms",
            "previous",
            "night_audit",
        }
        assert body["business_date"] == "2026-10-01"
        assert body["kpis"]["arrivals_total"] == 1
        assert body["kpis"]["departures_total"] == 1
        (arrival,) = body["arrivals"]
        assert (arrival["stay_id"], arrival["ready"], arrival["room"]) == (str(stay.pk), True, "101")

    def test_housekeeping_cannot_read_the_board(self, hotel, make_member, api_for):
        response = api_for(make_member("housekeeping"), hotel.prop).get(URL)

        assert response.status_code == 403
        assert response.json()["permission"] == "frontdesk.view"

    def test_another_organization_cannot_open_the_property(self, hotel, api_for):
        from apps.accounts.services import add_member, ensure_system_roles
        from apps.accounts.tests.factories import UserFactory
        from apps.core.tests.factories import OrganizationFactory

        other = OrganizationFactory(status="active")
        ensure_system_roles(other)
        stranger = UserFactory()
        add_member(other, stranger, "owner")

        assert api_for(stranger, hotel.prop).get(URL).status_code == 404

    def test_the_property_header_is_required(self, hotel, front_desk):
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=front_desk)

        response = client.get(URL)

        assert (response.status_code, response.json()["code"]) == (400, "property_required")

    def test_the_number_of_queries_does_not_grow_with_the_arrivals(self, hotel, front_desk, api_for):
        client = api_for(front_desk, hotel.prop)
        new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["101"])
        client.get(URL)  # warm-up: materializes InventoryDay rows
        with CaptureQueriesContext(connection) as few:
            client.get(URL)
        new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["102"])
        new_stay(hotel, oct_(1), oct_(2), room=hotel.rooms["201"])
        arrived(hotel, oct_(0), oct_(3), room_type=hotel.ste, room=hotel.rooms["301"])
        with CaptureQueriesContext(connection) as many:
            client.get(URL)

        assert len(many.captured_queries) == len(few.captured_queries)
