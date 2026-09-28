"""Front desk helpers over the reservations of the active property (bookings.view):
`GET reservations/export/` (CSV with the filters of `GET /api/v1/bookings/reservations/`) and
`GET reservations/{id}/online-checkin/` (state of the guest portal check-in, C5)."""

import csv
import io

import pytest

from apps.bookings.tests.helpers import oct_
from apps.frontdesk.tests.helpers import arrived, new_stay

pytestmark = pytest.mark.django_db

EXPORT = "/api/v1/frontdesk/reservations/export/"


def read_csv(response) -> list[list[str]]:
    text = response.content.decode("utf-8")
    assert text.startswith("﻿")  # BOM: Excel opens it as UTF-8
    return list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))


class TestExport:
    def test_exports_the_filtered_reservations_as_csv(self, hotel, front_desk, api_for):
        in_house = arrived(hotel, oct_(0), oct_(3), room=hotel.rooms["101"])
        new_stay(hotel, oct_(2), oct_(4))

        response = api_for(front_desk, hotel.prop).get(EXPORT, {"status": "checked_in"})

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert 'filename="reservas-2026-10-01.csv"' in response["Content-Disposition"]
        header, *rows = read_csv(response)
        assert header[:6] == ["Código", "Estado", "Fuente", "Canal", "Llegada", "Salida"]
        assert len(rows) == 1
        row = dict(zip(header, rows[0], strict=True))
        reservation = in_house.reservation
        assert row["Código"] == reservation.code
        assert row["Estado"] == "En casa"
        assert (row["Llegada"], row["Salida"], row["Noches"]) == ("2026-09-30", "2026-10-03", "3")
        assert row["Huésped"] == reservation.booker.full_name
        assert row["Habitaciones"] == "101"
        assert (row["Total"], row["Saldo"]) == ("1142400.00", "1142400.00")

    def test_english_headers_on_request(self, hotel, front_desk, api_for):
        new_stay(hotel, oct_(2), oct_(4))

        response = api_for(front_desk, hotel.prop).get(EXPORT, {"lang": "en"})

        header, row = read_csv(response)
        assert header[:2] == ["Code", "Status"]
        assert row[1] == "Confirmed"

    def test_only_the_active_property_is_exported(self, hotel, organization, front_desk, api_for):
        from apps.bookings.tests.helpers import build_hotel
        from apps.core.tests.factories import PropertyFactory

        other = build_hotel(PropertyFactory(organization=organization))
        new_stay(other, oct_(2), oct_(4))

        _header, *rows = read_csv(api_for(front_desk, hotel.prop).get(EXPORT))

        assert rows == []

    def test_housekeeping_cannot_export(self, hotel, make_member, api_for):
        response = api_for(make_member("housekeeping"), hotel.prop).get(EXPORT)

        assert (response.status_code, response.json()["permission"]) == (403, "bookings.view")


class TestOnlineCheckin:
    def test_reports_the_state_of_the_guest_portal_check_in(self, hotel, front_desk, api_for):
        from django.apps import apps as django_apps

        stay = new_stay(hotel, oct_(1), oct_(2))
        url = f"/api/v1/frontdesk/reservations/{stay.reservation_id}/online-checkin/"
        client = api_for(front_desk, hotel.prop)

        assert client.get(url).json() == {
            "reservation_id": str(stay.reservation_id),
            "status": None,
            "completed_at": None,
        }
        try:
            online_checkin = django_apps.get_model("guestportal", "OnlineCheckin")
        except LookupError:
            pytest.skip("guestportal.OnlineCheckin no existe todavía (C5)")
        online_checkin.objects.create(reservation=stay.reservation, status="completed")
        assert client.get(url).json()["status"] == "completed"

    def test_a_reservation_of_another_property_is_not_found(self, hotel, organization, owner, api_for):
        from apps.bookings.tests.helpers import build_hotel
        from apps.core.tests.factories import PropertyFactory

        other = build_hotel(PropertyFactory(organization=organization))
        stay = new_stay(other, oct_(1), oct_(2))

        response = api_for(owner, hotel.prop).get(
            f"/api/v1/frontdesk/reservations/{stay.reservation_id}/online-checkin/"
        )

        assert response.status_code == 404
