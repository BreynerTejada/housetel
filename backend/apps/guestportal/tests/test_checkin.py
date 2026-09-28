"""Online check-in through the portal: guests (TRA/SIRE data), documents, arrival, signature and
completion."""

from datetime import date, time
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.bookings.tests.helpers import book, foreign_input, oct_
from apps.core.models import Alert
from apps.core.signals import guest_checked_in_online
from apps.core.tokens import make_reservation_token
from apps.guestportal.models import GuestPortalSettings, OnlineCheckin
from apps.guestportal.tests.conftest import jpeg_bytes, signature_data_url
from apps.guests.models import Guest, GuestDocument
from apps.guests.tests.factories import GuestFactory

pytestmark = pytest.mark.django_db


def booker_entry(reservation, **overrides) -> dict:
    stay = reservation.stays.get()
    entry = {
        "stay_id": str(stay.pk),
        "role": "booker",
        "first_name": "Laura",
        "last_name": "Gómez",
        "document_type": "CC",
        "document_number": reservation.booker.document_number,
        "nationality": "CO",
        "country_of_residence": "CO",
        "city_of_residence": "Bogotá",
        "birth_date": "1990-04-02",
        "email": "laura.gomez@example.com",
        "phone": "3001112233",
        "travel_reason": "leisure",
        "origin": "Bogotá",
        "destination": "Bogotá",
    }
    entry.update(overrides)
    return entry


def companion_entry(reservation, **overrides) -> dict:
    stay = reservation.stays.get()
    entry = {
        "stay_id": str(stay.pk),
        "role": "companion",
        "first_name": "ana maría",
        "last_name": "PÉREZ",
        "document_type": "CC",
        "document_number": "1.020.304.050",
        "nationality": "CO",
        "country_of_residence": "CO",
        "birth_date": "1992-06-15",
    }
    entry.update(overrides)
    return entry


def post_step(public_api, portal_url, payload):
    return public_api.post(portal_url("checkin/"), payload, format="json")


def upload(public_api, portal_url, guest_id, *, kind="id_front", content=None, name="cedula.jpg"):
    file = SimpleUploadedFile(name, content or jpeg_bytes(), content_type="image/jpeg")
    return public_api.post(
        portal_url("checkin/"),
        {"step": "documents", "guest_id": str(guest_id), "kind": kind, "file": file},
        format="multipart",
    )


def fill_everything(public_api, portal_url, reservation):
    """Guests (booker + companion), a document each, ETA and signature: ready to complete."""
    response = post_step(
        public_api,
        portal_url,
        {"step": "guests", "guests": [booker_entry(reservation), companion_entry(reservation)]},
    )
    assert response.status_code == 200, response.json()
    companion = reservation.stays.get().occupants.get()
    for guest_id in (reservation.booker_id, companion.pk):
        assert upload(public_api, portal_url, guest_id).status_code == 201
    assert post_step(public_api, portal_url, {"step": "documents"}).status_code == 200
    assert post_step(public_api, portal_url, {"step": "arrival", "eta": "16:30"}).status_code == 200
    response = post_step(
        public_api, portal_url, {"step": "signature", "signature": signature_data_url(), "accept_terms": True}
    )
    assert response.status_code == 200, response.json()
    return companion


class TestReadingTheCheckin:
    def test_a_fresh_checkin_lists_one_slot_per_guest_with_the_booker_prefilled(
        self, public_api, portal_url, reservation
    ):
        body = public_api.get(portal_url("checkin/")).json()

        assert body["status"] == "not_started"
        assert body["current_step"] == "guests"
        assert [(slot["role"], slot["complete"]) for slot in body["guests"]] == [
            ("booker", False),  # no birth date yet
            ("companion", False),
        ]
        booker = body["guests"][0]
        assert booker["guest_id"] == str(reservation.booker_id)
        assert booker["data"]["document_number"] == reservation.booker.document_number
        assert body["guests"][1]["guest_id"] is None
        assert {item["code"] for item in body["missing"]} == {"guest_data", "document", "signature"}
        assert body["terms"]["es"]

    def test_companions_already_registered_show_only_their_name_and_a_masked_document(
        self, public_api, portal_url, reservation
    ):
        companion = GuestFactory(organization=reservation.property.organization, document_number="99887766")
        reservation.stays.get().occupants.add(companion)

        body = public_api.get(portal_url("checkin/")).json()

        slot = body["guests"][1]
        assert slot["guest_id"] == str(companion.pk)
        assert slot["data"] == {
            "first_name": companion.first_name,
            "last_name": companion.last_name,
            "nationality": companion.nationality,
            "document_type": companion.document_type,
            "document_hint": "••••7766",
        }
        assert companion.email not in str(body)


class TestGuestsStep:
    def test_the_step_saves_the_booker_and_creates_the_companion_as_an_occupant(
        self, public_api, portal_url, reservation
    ):
        response = post_step(
            public_api,
            portal_url,
            {"step": "guests", "guests": [booker_entry(reservation), companion_entry(reservation)]},
        )

        assert response.status_code == 200, response.json()
        booker = Guest.objects.get(pk=reservation.booker_id)
        assert (booker.birth_date.isoformat(), booker.city_of_residence, booker.phone) == (
            "1990-04-02",
            "Bogotá",
            "+573001112233",
        )
        companion = Guest.objects.get(
            organization=reservation.property.organization, document_number="1020304050"
        )
        assert (companion.first_name, companion.last_name, companion.birth_date.isoformat()) == (
            "Ana María",
            "Pérez",
            "1992-06-15",
        )
        assert list(reservation.stays.get().occupants.all()) == [companion]
        checkin = OnlineCheckin.objects.get(reservation=reservation)
        assert (checkin.status, checkin.current_step) == ("in_progress", "documents")
        # travel data belongs to the stay: the companion inherits the booker's
        assert checkin.data["travel"][str(companion.pk)] == {
            "travel_reason": "leisure",
            "origin": "Bogotá",
            "destination": "Bogotá",
        }

    def test_missing_identity_data_is_reported_per_guest(self, public_api, portal_url, reservation):
        response = post_step(
            public_api,
            portal_url,
            {
                "step": "guests",
                "guests": [booker_entry(reservation), companion_entry(reservation, document_number="")],
            },
        )

        assert response.status_code == 400
        assert response.json()["code"] == "validation_error"
        assert "guests.1.document_number" in response.json()["fields"]
        assert not reservation.stays.get().occupants.exists()

    def test_the_booker_travel_data_is_required(self, public_api, portal_url, reservation):
        response = post_step(
            public_api,
            portal_url,
            {"step": "guests", "guests": [booker_entry(reservation, travel_reason="")]},
        )

        assert response.status_code == 400
        assert "guests.0.travel_reason" in response.json()["fields"]

    def test_the_same_person_cannot_be_registered_twice(self, public_api, portal_url, reservation):
        twin = companion_entry(reservation, document_number=reservation.booker.document_number)

        response = post_step(
            public_api, portal_url, {"step": "guests", "guests": [booker_entry(reservation), twin]}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "duplicate_guest"

    def test_a_document_that_belongs_to_another_profile_is_flagged_to_the_hotel(
        self, public_api, portal_url, reservation
    ):
        other = GuestFactory(organization=reservation.property.organization, document_type="CC")

        response = post_step(
            public_api,
            portal_url,
            {"step": "guests", "guests": [booker_entry(reservation, document_number=other.document_number)]},
        )

        assert response.status_code == 409
        assert response.json()["code"] == "document_in_use"
        alert = Alert.objects.get(property=reservation.property, kind="guestportal_duplicate_guest")
        assert alert.data["guest_ids"] == sorted([str(reservation.booker_id), str(other.pk)])
        assert Guest.objects.get(pk=reservation.booker_id).document_number != other.document_number

    def test_a_new_companion_never_takes_over_the_profile_that_holds_that_document(
        self, public_api, portal_url, reservation
    ):
        stranger = GuestFactory(
            organization=reservation.property.organization,
            first_name="Pedro",
            last_name="Ramírez",
            document_number="99887766",
            birth_date=date(1970, 1, 1),
        )
        typed = companion_entry(
            reservation, first_name="Otra", last_name="Persona", document_number="99.887.766"
        )

        response = post_step(
            public_api, portal_url, {"step": "guests", "guests": [booker_entry(reservation), typed]}
        )

        assert response.status_code == 409
        assert response.json()["code"] == "document_in_use"
        stranger.refresh_from_db()
        assert (stranger.first_name, stranger.last_name, stranger.birth_date) == (
            "Pedro",
            "Ramírez",
            date(1970, 1, 1),
        )
        assert not reservation.stays.get().occupants.exists()
        assert Alert.objects.filter(
            property=reservation.property, kind="guestportal_duplicate_guest"
        ).exists()

    def test_a_returning_companion_is_linked_to_the_stay_without_rewriting_the_profile(
        self, public_api, portal_url, reservation
    ):
        known = GuestFactory(
            organization=reservation.property.organization,
            first_name="Ana María",
            last_name="Pérez Gómez",
            document_number="1020304050",
            birth_date=date(1992, 6, 15),
            email="ana@example.com",
        )
        typed = companion_entry(
            reservation, first_name="ana maria", last_name="PEREZ", birth_date="1990-01-01"
        )

        response = post_step(
            public_api, portal_url, {"step": "guests", "guests": [booker_entry(reservation), typed]}
        )

        assert response.status_code == 200, response.json()
        assert list(reservation.stays.get().occupants.all()) == [known]
        known.refresh_from_db()
        assert (known.first_name, known.last_name, known.birth_date, known.email) == (
            "Ana María",
            "Pérez Gómez",
            date(1992, 6, 15),
            "ana@example.com",
        )

    def test_a_new_companion_is_never_matched_to_another_profile_by_email(
        self, public_api, portal_url, reservation
    ):
        contact = GuestFactory(
            organization=reservation.property.organization,
            first_name="Contacto",
            last_name="WhatsApp",
            document_type="",
            document_number="",
            email="ana.perez@example.com",
        )
        typed = companion_entry(reservation, email="ana.perez@example.com")

        response = post_step(
            public_api, portal_url, {"step": "guests", "guests": [booker_entry(reservation), typed]}
        )

        assert response.status_code == 200, response.json()
        companion = reservation.stays.get().occupants.get()
        assert companion.pk != contact.pk
        assert (companion.document_number, companion.email) == ("1020304050", "ana.perez@example.com")
        contact.refresh_from_db()
        assert (contact.first_name, contact.document_number) == ("Contacto", "")

    def test_the_step_is_closed_before_the_window_opens(self, public_api, hotel):
        later = book(hotel, oct_(20), oct_(22))

        response = public_api.post(
            f"/api/v1/public/guestportal/{make_reservation_token(later)}/checkin/",
            {"step": "guests", "guests": [booker_entry(later)]},
            format="json",
        )

        assert response.status_code == 409
        assert response.json()["code"] == "checkin_closed"
        assert response.json()["reason"] == "not_open_yet"


class TestDocuments:
    def test_an_upload_becomes_a_private_guest_document(self, public_api, portal_url, reservation):
        response = upload(public_api, portal_url, reservation.booker_id)

        assert response.status_code == 201, response.json()
        document = GuestDocument.objects.get(guest=reservation.booker)
        assert (document.kind, document.uploaded_via) == ("id_front", "portal")
        assert "/media/" not in response.content.decode()
        assert not Path(document.file.path).is_relative_to(Path(settings.MEDIA_ROOT))
        assert response.json()["document"] == {
            "id": str(document.pk),
            "kind": "id_front",
            "guest_id": str(reservation.booker_id),
        }

    def test_only_guests_of_the_booking_can_receive_documents(self, public_api, portal_url, reservation):
        stranger = GuestFactory(organization=reservation.property.organization)

        response = upload(public_api, portal_url, stranger.pk)

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_guest"
        assert not GuestDocument.objects.filter(guest=stranger).exists()

    def test_files_that_are_not_photos_or_pdfs_are_rejected(self, public_api, portal_url, reservation):
        response = upload(public_api, portal_url, reservation.booker_id, content=b"MZ\x90\x00 not an image")

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_file_type"

    def test_the_step_needs_a_document_per_adult_when_the_hotel_requires_it(
        self, public_api, portal_url, reservation
    ):
        post_step(
            public_api,
            portal_url,
            {"step": "guests", "guests": [booker_entry(reservation), companion_entry(reservation)]},
        )
        upload(public_api, portal_url, reservation.booker_id)

        response = post_step(public_api, portal_url, {"step": "documents"})

        assert response.status_code == 400
        assert response.json()["code"] == "documents_missing"
        companion = reservation.stays.get().occupants.get()
        assert response.json()["guest_ids"] == [str(companion.pk)]

    def test_without_the_requirement_the_step_just_moves_on(self, public_api, portal_url, reservation):
        GuestPortalSettings.objects.create(property=reservation.property, require_document_photo=False)

        response = post_step(public_api, portal_url, {"step": "documents"})

        assert response.status_code == 200
        assert OnlineCheckin.objects.get(reservation=reservation).current_step == "arrival"


class TestArrivalAndSignature:
    def test_the_eta_reaches_the_reservation(self, public_api, portal_url, reservation):
        response = post_step(public_api, portal_url, {"step": "arrival", "eta": "16:30"})

        assert response.status_code == 200
        reservation.refresh_from_db()
        assert reservation.eta == time(16, 30)
        assert OnlineCheckin.objects.get(reservation=reservation).eta == time(16, 30)

    def test_the_signature_is_kept_privately_with_the_acceptance(self, public_api, portal_url, reservation):
        response = post_step(
            public_api,
            portal_url,
            {
                "step": "signature",
                "signature": signature_data_url(),
                "accept_terms": True,
                "marketing_consent": True,
            },
        )

        assert response.status_code == 200, response.json()
        checkin = OnlineCheckin.objects.get(reservation=reservation)
        assert checkin.accepted_terms_at is not None
        assert checkin.signature.name.endswith(".png")
        assert not Path(checkin.signature.path).is_relative_to(Path(settings.MEDIA_ROOT))
        assert checkin.ip == "127.0.0.1"
        booker = Guest.objects.get(pk=reservation.booker_id)
        assert booker.data_processing_consent_at is not None
        assert booker.marketing_consent is True

    def test_coming_back_to_the_step_keeps_the_signature_already_given(
        self, public_api, portal_url, reservation
    ):
        post_step(
            public_api,
            portal_url,
            {"step": "signature", "signature": signature_data_url(), "accept_terms": True},
        )
        first = OnlineCheckin.objects.get(reservation=reservation).signature.name

        response = post_step(
            public_api, portal_url, {"step": "signature", "signature": "", "accept_terms": True}
        )

        assert response.status_code == 200, response.json()
        assert OnlineCheckin.objects.get(reservation=reservation).signature.name == first

    def test_without_any_signature_the_step_asks_for_one(self, public_api, portal_url, reservation):
        response = post_step(
            public_api, portal_url, {"step": "signature", "signature": "", "accept_terms": True}
        )

        assert response.status_code == 400
        assert response.json()["code"] == "signature_required"

    def test_a_blank_signature_is_rejected(self, public_api, portal_url, reservation):
        response = post_step(
            public_api,
            portal_url,
            {"step": "signature", "signature": signature_data_url(blank=True), "accept_terms": True},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "signature_empty"

    def test_something_that_is_not_a_png_is_not_a_signature(self, public_api, portal_url, reservation):
        response = post_step(
            public_api,
            portal_url,
            {"step": "signature", "signature": "data:image/png;base64,aGVsbG8=", "accept_terms": True},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "invalid_signature"

    def test_the_terms_must_be_accepted(self, public_api, portal_url, reservation):
        response = post_step(
            public_api,
            portal_url,
            {"step": "signature", "signature": signature_data_url(), "accept_terms": False},
        )

        assert response.status_code == 400
        assert response.json()["code"] == "terms_required"


class TestCompletion:
    def test_an_incomplete_checkin_says_what_is_missing(self, public_api, portal_url, reservation):
        response = public_api.post(portal_url("checkin/complete/"), {}, format="json")

        assert response.status_code == 400
        assert response.json()["code"] == "checkin_incomplete"
        assert {item["code"] for item in response.json()["missing"]} == {
            "guest_data",
            "document",
            "signature",
        }
        assert not OnlineCheckin.objects.filter(reservation=reservation, status="completed").exists()

    def test_completing_marks_the_booking_ready_and_emits_the_signal_once(
        self, public_api, portal_url, reservation, django_capture_on_commit_callbacks
    ):
        fill_everything(public_api, portal_url, reservation)
        received = []

        def listener(sender, reservation, **kwargs):
            received.append(reservation.pk)

        guest_checked_in_online.connect(listener, weak=False, dispatch_uid="test-c5-online")
        try:
            with django_capture_on_commit_callbacks(execute=True):
                first = public_api.post(portal_url("checkin/complete/"), {}, format="json")
            with django_capture_on_commit_callbacks(execute=True):
                again = public_api.post(portal_url("checkin/complete/"), {}, format="json")
        finally:
            guest_checked_in_online.disconnect(dispatch_uid="test-c5-online")

        assert first.status_code == 200, first.json()
        assert again.status_code == 200
        checkin = OnlineCheckin.objects.get(reservation=reservation)
        assert checkin.status == "completed"
        assert checkin.completed_at is not None
        assert first.json()["status"] == "completed"
        assert received == [reservation.pk]

    def test_a_foreign_guest_passport_can_be_the_document(self, public_api, hotel):
        foreign = book(hotel, oct_(5), oct_(7), adults=1, booker=foreign_input())
        url = f"/api/v1/public/guestportal/{make_reservation_token(foreign)}/"
        entry = booker_entry(
            foreign,
            document_type="PA",
            nationality="US",
            country_of_residence="US",
            first_name="John",
            last_name="Smith",
            city_of_residence="Austin",
            phone="",
        )
        public_api.post(url + "checkin/", {"step": "guests", "guests": [entry]}, format="json")
        file = SimpleUploadedFile("passport.jpg", jpeg_bytes(), content_type="image/jpeg")
        public_api.post(
            url + "checkin/",
            {"step": "documents", "guest_id": str(foreign.booker_id), "kind": "passport", "file": file},
            format="multipart",
        )
        public_api.post(
            url + "checkin/",
            {"step": "signature", "signature": signature_data_url(), "accept_terms": True},
            format="json",
        )

        response = public_api.post(url + "checkin/complete/", {}, format="json")

        assert response.status_code == 200, response.json()
        assert Guest.objects.get(pk=foreign.booker_id).is_foreign_non_resident
