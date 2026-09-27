"""Availability, offers, calendar, auto-assign, groups and inventory rebuild endpoints (plan B2b › API)."""

import pytest

from apps.bookings.models import InventoryDay, ReservationGroup
from apps.bookings.services.reservations import assign_room
from apps.bookings.tests.factories import ReservationGroupFactory
from apps.bookings.tests.helpers import book, guest_input, oct_
from apps.guests.models import Guest
from apps.inventory.services import block_room

pytestmark = pytest.mark.django_db

BASE = "/api/v1/bookings/"


class TestAvailability:
    def test_units_per_category(self, hotel, api):
        book(hotel, oct_(1), oct_(3))
        response = api.get(f"{BASE}availability/", {"checkin": "2026-10-01", "checkout": "2026-10-03"})
        assert response.status_code == 200
        assert response.json() == {str(hotel.dbl.pk): 2, str(hotel.ste.pk): 1, str(hotel.dorm_type.pk): 4}

    def test_dates_are_required_and_valid(self, hotel, api):
        response = api.get(f"{BASE}availability/", {"checkin": "2026-10-01"})
        assert (response.status_code, response.json()["code"]) == (400, "validation_error")
        response = api.get(f"{BASE}availability/", {"checkin": "2026-10-03", "checkout": "2026-10-01"})
        assert response.status_code == 400


class TestOffers:
    def test_lists_the_offers(self, hotel, api):
        response = api.get(
            f"{BASE}offers/",
            {"checkin": "2026-10-01", "checkout": "2026-10-03", "adults": 2, "channel": "direct"},
        )
        assert response.status_code == 200
        offers = response.json()
        assert [offer["room_type"]["code"] for offer in offers] == ["DORM", "DBL", "STE"]
        dbl = offers[1]
        assert set(dbl) == {
            "room_type_id",
            "rate_plan_id",
            "room_type",
            "rate_plan",
            "available_units",
            "units_needed",
            "quote",
            "total",
        }
        assert (dbl["total"], dbl["available_units"], dbl["units_needed"]) == ("761600.00", 3, 1)
        assert set(dbl["room_type"]) == {
            "id",
            "code",
            "name",
            "kind",
            "color",
            "max_adults",
            "max_children",
            "max_occupancy",
        }
        assert set(dbl["rate_plan"]) == {
            "id",
            "code",
            "name",
            "meal_plan",
            "is_public",
            "deposit_percent",
            "cancellation_policy",
        }
        assert dbl["quote"]["total"] == "761600.00" and len(dbl["quote"]["nights"]) == 2

    def test_foreign_guests_and_children(self, hotel, api):
        response = api.get(
            f"{BASE}offers/",
            {
                "checkin": "2026-10-01",
                "checkout": "2026-10-02",
                "adults": 2,
                "children": 1,
                "children_ages": "6",
                "foreign": "1",
            },
        )
        codes = {offer["room_type"]["code"]: offer for offer in response.json()}
        assert set(codes) == {"DBL", "STE"}
        assert codes["DBL"]["quote"]["taxes"][0]["exempt"] is True

    def test_adults_are_validated(self, hotel, api):
        response = api.get(f"{BASE}offers/", {"checkin": "2026-10-01", "checkout": "2026-10-02", "adults": 0})
        assert response.status_code == 400


class TestCalendar:
    def test_has_the_exact_shape(self, hotel, api, django_capture_on_commit_callbacks):
        vip = Guest.objects.create(
            organization=hotel.prop.organization, first_name="Sofía", last_name="Rey", is_vip=True
        )
        in_101 = book(hotel, oct_(1), oct_(3), booker=vip, stay_kwargs={"room_id": hotel.rooms["101"].pk})
        waiting = book(hotel, oct_(2), oct_(4), booker=guest_input(first_name="Pedro", last_name="Paz"))
        dorm = book(
            hotel,
            oct_(1),
            oct_(2),
            room_type=hotel.dorm_type,
            adults=1,
            stay_kwargs={"room_id": hotel.dorm.pk, "bed_id": hotel.beds["B"].pk},
        )
        book(hotel, oct_(9), oct_(10))  # outside the range
        with django_capture_on_commit_callbacks(execute=True):  # the receiver puts the block in InventoryDay
            block = block_room(
                hotel.rooms["201"], start=oct_(2), end=oct_(5), kind="maintenance", reason="Pintura"
            )

        response = api.get(f"{BASE}calendar/", {"start": "2026-10-01", "end": "2026-10-04"})

        assert response.status_code == 200
        body = response.json()
        assert set(body) == {"room_types", "stays", "blocks", "availability"}

        assert [room_type["code"] for room_type in body["room_types"]] == ["DBL", "STE", "DORM"]
        dbl = body["room_types"][0]
        assert set(dbl) == {"id", "code", "name", "color", "kind", "rooms"}
        assert (dbl["id"], dbl["kind"], dbl["name"]) == (str(hotel.dbl.pk), "private", hotel.dbl.name)
        assert [room["number"] for room in dbl["rooms"]] == ["101", "102", "201"]
        assert dbl["rooms"][0] == {
            "id": str(hotel.rooms["101"].pk),
            "number": "101",
            "floor": "1",
            "housekeeping_status": "clean",
            "beds": [],
        }
        assert [bed["label"] for bed in body["room_types"][2]["rooms"][0]["beds"]] == ["A", "B", "C", "D"]

        stays = {item["code"]: item for item in body["stays"]}
        assert set(stays) == {in_101.code, waiting.code, dorm.code}
        first = stays[in_101.code]
        assert set(first) == {
            "id",
            "reservation_id",
            "code",
            "status",
            "source",
            "channel_code",
            "guest_name",
            "room_id",
            "bed_id",
            "room_type_id",
            "checkin",
            "checkout",
            "adults",
            "children",
            "balance_due",
            "is_vip",
        }
        assert (
            first["room_id"],
            first["checkin"],
            first["checkout"],
            first["guest_name"],
            first["is_vip"],
        ) == (
            str(hotel.rooms["101"].pk),
            "2026-10-01",
            "2026-10-03",
            "Sofía Rey",
            True,
        )
        assert (first["balance_due"], first["reservation_id"], first["status"]) == (
            True,
            str(in_101.pk),
            "confirmed",
        )
        assert (stays[waiting.code]["room_id"], stays[waiting.code]["room_type_id"]) == (
            None,
            str(hotel.dbl.pk),
        )
        assert stays[dorm.code]["bed_id"] == str(hotel.beds["B"].pk)

        assert body["blocks"] == [
            {
                "id": str(block.pk),
                "room_id": str(hotel.rooms["201"].pk),
                "bed_id": None,
                "start": "2026-10-02",
                "end": "2026-10-05",
                "kind": "maintenance",
                "reason": "Pintura",
            }
        ]
        # DBL: 3 rooms − stays − the blocked 201
        assert body["availability"][str(hotel.dbl.pk)] == {"2026-10-01": 2, "2026-10-02": 0, "2026-10-03": 1}
        assert body["availability"][str(hotel.dorm_type.pk)]["2026-10-01"] == 3

    def test_the_range_is_required_and_limited(self, hotel, api):
        assert api.get(f"{BASE}calendar/", {"start": "2026-10-01"}).status_code == 400
        response = api.get(f"{BASE}calendar/", {"start": "2026-10-01", "end": "2027-03-01"})
        assert (response.status_code, response.json()["code"]) == (400, "range_too_long")


class TestAutoAssign:
    def test_returns_the_report(self, hotel, api):
        stay = book(hotel, oct_(1), oct_(2)).stays.get()
        for number in ("101", "102", "201"):
            assign_room(book(hotel, oct_(2), oct_(3)).stays.get(), hotel.rooms[number])
        waiting = book(hotel, oct_(2), oct_(3), allow_overbooking=True)

        response = api.post(
            f"{BASE}auto-assign/", {"date_from": "2026-10-01", "date_to": "2026-10-02"}, format="json"
        )

        assert response.status_code == 200
        body = response.json()
        assert body["assigned"] == [
            {
                "stay_id": str(stay.pk),
                "reservation_id": str(stay.reservation_id),
                "code": stay.reservation.code,
                "room_id": body["assigned"][0]["room_id"],
                "room_number": body["assigned"][0]["room_number"],
                "bed_id": None,
                "bed_label": None,
            }
        ]
        assert body["unassigned"] == [
            {"stay_id": str(waiting.stays.get().pk), "reservation_id": str(waiting.pk), "code": waiting.code}
        ]
        assert len(body["messages"]) == 1

    def test_needs_manage(self, hotel, api_for, make_member):
        response = api_for(make_member("accountant"), hotel.prop).post(
            f"{BASE}auto-assign/", {"date_from": "2026-10-01", "date_to": "2026-10-01"}, format="json"
        )
        assert response.status_code == 403


class TestGroups:
    def test_crud(self, hotel, api):
        response = api.post(f"{BASE}groups/", {"name": "Boda Pérez", "notes": "Bloque de 5"}, format="json")
        assert (response.status_code, response.json()["reservations_count"]) == (201, 0)
        group_id = response.json()["id"]
        book(hotel, oct_(1), oct_(2), group_id=group_id)
        body = api.get(f"{BASE}groups/{group_id}/").json()
        assert (body["name"], body["reservations_count"], body["contact_guest"]) == ("Boda Pérez", 1, None)
        patched = api.patch(f"{BASE}groups/{group_id}/", {"name": "Boda P."}, format="json").json()
        assert (patched["name"], patched["reservations_count"]) == ("Boda P.", 1)
        assert api.get(f"{BASE}groups/").json()["count"] == 1
        assert api.delete(f"{BASE}groups/{group_id}/").status_code == 204
        assert not ReservationGroup.objects.exists()

    def test_the_contact_must_be_a_guest_of_the_organization(self, hotel, api):
        stranger = Guest.objects.create(
            organization=ReservationGroupFactory().property.organization, first_name="X"
        )
        response = api.post(
            f"{BASE}groups/", {"name": "G", "contact_guest_id": str(stranger.pk)}, format="json"
        )
        assert response.status_code == 400

    def test_accountant_reads_but_does_not_write(self, hotel, api_for, make_member):
        client = api_for(make_member("accountant"), hotel.prop)
        assert client.get(f"{BASE}groups/").status_code == 200
        assert client.post(f"{BASE}groups/", {"name": "X"}, format="json").status_code == 403

    def test_groups_of_other_properties_are_hidden(self, hotel, api):
        other = ReservationGroupFactory()
        assert api.get(f"{BASE}groups/{other.pk}/").status_code == 404


class TestInventoryRebuild:
    def test_rebuilds_a_range(self, hotel, api):
        book(hotel, oct_(1), oct_(2))
        InventoryDay.objects.filter(room_type=hotel.dbl, date=oct_(1)).update(sold_units=3)
        response = api.post(
            f"{BASE}inventory/rebuild/", {"start": "2026-10-01", "end": "2026-10-03"}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["updated"] == 1
        assert InventoryDay.objects.get(room_type=hotel.dbl, date=oct_(1)).sold_units == 1

    def test_needs_manage(self, hotel, api_for, make_member):
        client = api_for(make_member("accountant"), hotel.prop)
        assert client.post(f"{BASE}inventory/rebuild/", {}, format="json").status_code == 403

    @pytest.mark.parametrize(
        "body",
        [
            {"start": "2026-10-05", "end": "2026-10-01"},  # inverted
            {"start": "2026-10-05", "end": "2026-10-05"},  # empty
            {"start": "2026-01-01", "end": "2030-01-01"},  # four years of rows at once
            {"start": "2028-06-01"},  # after the end of the default horizon
        ],
        ids=["inverted", "empty", "too-long", "start-after-horizon"],
    )
    def test_the_range_must_be_valid_and_bounded(self, hotel, api, body):
        response = api.post(f"{BASE}inventory/rebuild/", body, format="json")
        assert (response.status_code, response.json()["code"]) == (400, "validation_error")
        assert not InventoryDay.objects.exists()

    def test_one_bound_completes_with_the_default_horizon(self, hotel, api):
        response = api.post(f"{BASE}inventory/rebuild/", {"end": "2026-10-03"}, format="json")
        assert (response.status_code, response.json()["created"]) == (200, 3 * 9)  # Sep 24 → Oct 2

    def test_the_rebuild_and_its_audit_are_one_transaction(self, hotel, api, monkeypatch):
        """If the audit cannot be written, the recalculation is not kept either (all or nothing)."""
        from apps.core import audit

        def broken_record(**kwargs):
            raise RuntimeError("audit down")

        monkeypatch.setattr(audit, "record", broken_record)
        api.raise_request_exception = False

        response = api.post(
            f"{BASE}inventory/rebuild/", {"start": "2026-10-01", "end": "2026-10-03"}, format="json"
        )

        assert response.status_code == 500
        assert not InventoryDay.objects.exists()


def test_the_endpoints_are_in_the_openapi_schema(public_api):
    paths = public_api.get("/api/schema/?format=json").json()["paths"]
    for path in (
        "/api/v1/bookings/reservations/",
        "/api/v1/bookings/reservations/{id}/cancel/",
        "/api/v1/bookings/stays/{id}/check-in/",
        "/api/v1/bookings/stays/{id}/modify-preview/",
        "/api/v1/bookings/calendar/",
        "/api/v1/bookings/offers/",
    ):
        assert path in paths
