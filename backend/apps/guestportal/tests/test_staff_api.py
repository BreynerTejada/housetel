"""Staff side of the guest portal (`/api/v1/guestportal/`): check-in data, link + QR, sending the link,
service requests and settings. Permissions and tenant isolation."""

from datetime import time

import pytest
from django.core.files.base import ContentFile

from apps.bookings.tests.helpers import book, oct_
from apps.core.models import Alert
from apps.finance.models import Charge
from apps.guestportal.models import GuestPortalSettings, OnlineCheckin, ServiceRequest
from apps.guestportal.tests.conftest import jpeg_bytes, png_bytes
from apps.guests.services import add_document
from apps.rates.tests.factories import ExtraFactory

pytestmark = pytest.mark.django_db

BASE = "/api/v1/guestportal/"


@pytest.fixture
def front_desk(make_member):
    return make_member("front_desk")


@pytest.fixture
def desk(api_for, front_desk, prop):
    return api_for(front_desk, prop)


@pytest.fixture
def completed(reservation):
    """A completed online check-in with the booker's document and signature."""
    document = add_document(
        reservation.booker,
        kind="passport",
        file=ContentFile(jpeg_bytes(), name="p.jpg"),
        uploaded_via="portal",
    )
    checkin = OnlineCheckin.objects.create(
        reservation=reservation,
        status="completed",
        current_step="done",
        eta=time(15, 30),
        data={
            "travel": {
                str(reservation.booker_id): {
                    "travel_reason": "business",
                    "origin": "Medellín",
                    "destination": "Bogotá",
                }
            }
        },  # fmt: skip
        ip="181.1.2.3",
        user_agent="Mozilla/5.0 (iPhone)",
    )
    checkin.signature.save("signature.png", ContentFile(png_bytes()), save=True)
    return checkin, document


class TestCheckinData:
    def test_the_front_desk_sees_the_online_checkin_of_a_reservation(self, desk, reservation, completed):
        checkin, document = completed

        response = desk.get(f"{BASE}reservations/{reservation.pk}/checkin/")

        assert response.status_code == 200, response.json()
        body = response.json()
        assert (body["status"], body["eta"], body["ip"]) == ("completed", "15:30", "181.1.2.3")
        booker = body["guests"][0]
        assert booker["role"] == "booker"
        assert booker["data"]["document_number"] == reservation.booker.document_number
        assert booker["travel"] == {
            "travel_reason": "business",
            "origin": "Medellín",
            "destination": "Bogotá",
        }
        assert booker["documents"] == [
            {
                "id": str(document.pk),
                "kind": "passport",
                "uploaded_via": "portal",
                "created_at": document.created_at.isoformat(),
                "file_url": f"/api/v1/guests/documents/{document.pk}/file/",
            }
        ]
        assert (
            body["signature_url"] == f"/api/v1/guestportal/reservations/{reservation.pk}/checkin/signature/"
        )
        assert "/media/" not in response.content.decode()

    def test_a_reservation_without_online_checkin_is_not_started(self, desk, reservation):
        body = desk.get(f"{BASE}reservations/{reservation.pk}/checkin/").json()

        assert body["status"] == "not_started"
        assert body["signature_url"] is None

    def test_the_signature_is_served_only_to_staff_and_never_cached(
        self, desk, public_api, reservation, completed
    ):
        response = desk.get(f"{BASE}reservations/{reservation.pk}/checkin/signature/")

        assert response.status_code == 200
        assert response["Content-Type"] == "image/png"
        assert "no-store" in response["Cache-Control"]
        assert b"".join(response.streaming_content).startswith(b"\x89PNG")
        assert public_api.get(f"{BASE}reservations/{reservation.pk}/checkin/signature/").status_code == 401

    def test_arrivals_of_a_day_with_their_checkin_status(self, desk, hotel, reservation, completed):
        other = book(hotel, oct_(5), oct_(6))
        book(hotel, oct_(6), oct_(8))  # another day

        rows = desk.get(f"{BASE}checkins/", {"date": "2026-10-05"}).json()

        assert {(row["code"], row["checkin_status"]) for row in rows} == {
            (reservation.code, "completed"),
            (other.code, "not_started"),
        }
        done = next(row for row in rows if row["code"] == reservation.code)
        assert (done["eta"], done["guest_name"], done["reservation_id"]) == (
            "15:30",
            reservation.booker.full_name,
            str(reservation.pk),
        )


class TestLink:
    def test_the_link_comes_with_a_qr_code(self, desk, reservation):
        body = desk.get(f"{BASE}reservations/{reservation.pk}/link/").json()

        assert "/g/" in body["url"]
        assert body["checkin_url"] == body["url"] + "/checkin"
        assert body["qr_png"].startswith("data:image/png;base64,")

    def test_sending_the_link_uses_the_checkin_invitation_template(self, desk, reservation, monkeypatch):
        calls = []

        def fake_send_message(**kwargs):
            calls.append(kwargs)
            return []

        monkeypatch.setattr("apps.guestportal.services.staff.send_message", fake_send_message)

        # same payload as finance's payment link: {send_via: [...]}
        response = desk.post(f"{BASE}reservations/{reservation.pk}/send-link/", {"send_via": ["whatsapp"]},
                             format="json")  # fmt: skip

        assert response.status_code == 200, response.json()
        assert len(calls) == 1
        call = calls[0]
        assert (call["template_code"], call["reservation"], call["guest"], call["channels"]) == (
            "checkin_invitation",
            reservation,
            reservation.booker,
            ("whatsapp",),
        )
        assert call["context"]["checkin_url"].endswith("/checkin")
        assert response.json()["messages"] == []


class TestServiceRequests:
    @pytest.fixture
    def late(self, reservation):
        from apps.guestportal.services.requests import create_request

        return create_request(
            reservation, kind="late_checkout", requested_time=time(14, 0), notes="Vuelo tarde"
        )

    def test_the_staff_lists_pending_requests(self, desk, late):
        rows = desk.get(f"{BASE}service-requests/", {"status": "requested"}).json()["results"]

        assert [(row["id"], row["kind"], row["reservation"]["code"]) for row in rows] == [
            (str(late.pk), "late_checkout", late.reservation.code)
        ]

    def test_approving_can_charge_a_catalog_extra_and_resolves_the_alert(self, desk, hotel, late):
        extra = ExtraFactory(property=hotel.prop, code="LATE", price="80000", charge_type="per_stay")

        response = desk.post(f"{BASE}service-requests/{late.pk}/approve/", {"extra_id": str(extra.pk)},
                             format="json")  # fmt: skip

        assert response.status_code == 200, response.json()
        late.refresh_from_db()
        assert late.status == "approved"
        charge = Charge.objects.get(pk=late.charge_id)
        assert (charge.extra_id, charge.amount) == (extra.pk, 80000)
        assert not Alert.objects.filter(kind="guestportal_request", resolved_at__isnull=True).exists()

    def test_rejecting_keeps_the_reason(self, desk, late):
        response = desk.post(
            f"{BASE}service-requests/{late.pk}/reject/", {"reason": "Hotel lleno"}, format="json"
        )

        assert response.status_code == 200
        late.refresh_from_db()
        assert (late.status, late.decision_note) == ("rejected", "Hotel lleno")

    def test_a_decided_request_cannot_be_decided_again(self, desk, late):
        desk.post(f"{BASE}service-requests/{late.pk}/reject/", {}, format="json")

        response = desk.post(f"{BASE}service-requests/{late.pk}/approve/", {}, format="json")

        assert response.status_code == 409
        assert response.json()["code"] == "invalid_state"


class TestSettings:
    def test_defaults_are_created_on_first_read(self, api, prop):
        body = api.get(f"{BASE}settings/").json()

        assert body["checkin_opens_days_before"] == 7
        assert body["require_document_photo"] is True
        assert body["terms"]["es"]  # the default text when the hotel wrote none
        assert GuestPortalSettings.objects.filter(property=prop).exists()

    def test_the_manager_edits_them(self, api, prop):
        response = api.patch(
            f"{BASE}settings/",
            {
                "checkin_opens_days_before": 3,
                "auto_approve_extras": False,
                "terms": {"es": "Reglas", "en": "Rules"},
            },
            format="json",
        )

        assert response.status_code == 200, response.json()
        settings = GuestPortalSettings.objects.get(property=prop)
        assert (settings.checkin_opens_days_before, settings.auto_approve_extras, settings.terms["es"]) == (
            3,
            False,
            "Reglas",
        )

    def test_the_window_is_bounded(self, api):
        response = api.patch(f"{BASE}settings/", {"checkin_opens_days_before": 400}, format="json")

        assert response.status_code == 400
        assert "checkin_opens_days_before" in response.json()["fields"]


class TestAccess:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "checkins/"),
            ("get", "reservations/{id}/checkin/"),
            ("get", "reservations/{id}/link/"),
            ("post", "reservations/{id}/send-link/"),
            ("get", "service-requests/"),
            ("get", "settings/"),
            ("patch", "settings/"),
        ],
    )
    def test_housekeeping_has_no_access(self, api_for, make_member, prop, reservation, method, path):
        client = api_for(make_member("housekeeping"), prop)

        response = getattr(client, method)(BASE + path.format(id=reservation.pk), {}, format="json")

        assert response.status_code == 403
        assert response.json()["permission"].startswith("guestportal.")

    def test_reservations_of_another_hotel_are_not_found(self, api, organization, make_member):
        from apps.bookings.tests.helpers import build_hotel
        from apps.core.tests.factories import OrganizationFactory, PropertyFactory

        other_hotel = build_hotel(PropertyFactory(organization=OrganizationFactory()))
        foreign = book(other_hotel, oct_(5), oct_(7))

        for path in ("checkin/", "checkin/signature/", "link/"):
            assert api.get(f"{BASE}reservations/{foreign.pk}/{path}").status_code == 404
        assert api.post(f"{BASE}reservations/{foreign.pk}/send-link/", {}, format="json").status_code == 404

    def test_requests_of_another_hotel_are_invisible(self, api, prop):
        from apps.bookings.tests.helpers import build_hotel
        from apps.core.tests.factories import OrganizationFactory, PropertyFactory
        from apps.guestportal.services.requests import create_request

        other_hotel = build_hotel(PropertyFactory(organization=OrganizationFactory()))
        foreign = create_request(book(other_hotel, oct_(5), oct_(7)), kind="late_checkout")

        assert api.get(f"{BASE}service-requests/").json()["count"] == 0
        assert api.post(f"{BASE}service-requests/{foreign.pk}/approve/", {}, format="json").status_code == 404
        assert ServiceRequest.objects.get(pk=foreign.pk).status == "requested"
