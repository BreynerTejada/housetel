"""Guests API (`/api/v1/guests/`, organization-scoped): CRUD with search and filters, profile stats, stays,
private documents, duplicates and merge, Habeas Data export and anonymization; permissions and isolation."""

import json
from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.bookings.tests.factories import ReservationFactory, StayFactory
from apps.core.models import AuditEvent
from apps.core.tests.factories import OrganizationFactory, PropertyFactory
from apps.guests.models import Guest, GuestDocument
from apps.guests.tests.factories import ForeignGuestFactory, GuestFactory
from apps.inventory.models import CustomFieldDefinition

pytestmark = pytest.mark.django_db

BASE = "/api/v1/guests/guests/"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture(autouse=True)
def private_media(settings, tmp_path):
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"


def detail(guest):
    return f"{BASE}{guest.pk}/"


def names(response):
    return sorted(row["full_name"] for row in response.json()["results"])


class TestList:
    def test_lists_the_organization_guests_without_merged_ones(self, api, organization):
        ana = GuestFactory(organization=organization, first_name="Ana", last_name="Pérez")
        GuestFactory(organization=organization, first_name="Old", last_name="Copy", merged_into=ana)
        GuestFactory(organization=OrganizationFactory(), first_name="Otra", last_name="Org")

        response = api.get(BASE)

        assert response.status_code == 200
        assert names(response) == ["Ana Pérez"]
        row = response.json()["results"][0]
        assert {"id", "full_name", "email", "phone", "document_type", "document_number", "nationality",
                "is_vip", "tags", "stays_count", "last_stay_date"} <= set(row)  # fmt: skip

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("perez", ["Ana Pérez"]),  # accents ignored
            ("ANA PÉR", ["Ana Pérez"]),  # every word must match
            ("gomez", ["Luis Gómez"]),
            ("luis@example", ["Luis Gómez"]),
            ("1.020.304.050", ["Ana Pérez"]),  # formatted document
            ("300 111 2233", ["Ana Pérez"]),  # formatted phone
            ("nadie", []),
        ],
    )
    def test_search_by_name_email_phone_or_document(self, api, organization, query, expected):
        GuestFactory(organization=organization, first_name="Ana", last_name="Pérez",
                     document_number="1020304050", phone="+573001112233")  # fmt: skip
        GuestFactory(
            organization=organization, first_name="Luis", last_name="Gómez", email="luis@example.com"
        )
        assert names(api.get(BASE, {"q": query})) == expected

    def test_filters(self, api, organization, prop):
        vip = GuestFactory(organization=organization, first_name="Vip", last_name="Uno", is_vip=True,
                           tags=["frecuente"])  # fmt: skip
        foreign = ForeignGuestFactory(organization=organization, first_name="John", last_name="Smith")
        ReservationFactory(property=prop, booker=foreign, status="checked_out")
        ReservationFactory(property=prop, booker=vip, status="cancelled")

        assert names(api.get(BASE, {"is_vip": "true"})) == ["Vip Uno"]
        assert names(api.get(BASE, {"nationality": "us"})) == ["John Smith"]
        assert names(api.get(BASE, {"tag": "frecuente"})) == ["Vip Uno"]
        assert names(api.get(BASE, {"has_stays": "true"})) == ["John Smith"]
        assert names(api.get(BASE, {"has_stays": "false"})) == ["Vip Uno"]

    def test_rows_carry_stay_count_and_last_stay(self, api, organization, prop):
        guest = GuestFactory(organization=organization)
        ReservationFactory(property=prop, booker=guest, status="checked_out",
                           checkin_date=date(2025, 1, 1), checkout_date=date(2025, 1, 3))  # fmt: skip
        StayFactory(
            reservation=ReservationFactory(property=prop, status="checked_out", checkin_date=date(2025, 6, 1),
                                           checkout_date=date(2025, 6, 4)),
            occupants=[guest],
        )  # fmt: skip
        row = api.get(BASE).json()["results"]
        mine = next(r for r in row if r["id"] == str(guest.pk))
        assert (mine["stays_count"], mine["last_stay_date"]) == (2, "2025-06-01")

    def test_needs_guests_view(self, api_for, make_member, prop):
        response = api_for(make_member("housekeeping"), prop).get(BASE)
        assert (response.status_code, response.json()["permission"]) == (403, "guests.view")

    @pytest.mark.parametrize("ordering", [None, "stays_count", "-last_stay_date", "last_name"])
    def test_pages_follow_a_total_order(self, api, organization, ordering):
        # Many guests share a sort value (0 stays, the same surname): without a tie-breaker the database may
        # return them in a different order on each page, repeating some guests and skipping others.
        GuestFactory.create_batch(3, organization=organization, first_name="Ana", last_name="Pérez")
        with CaptureQueriesContext(connection) as queries:
            response = api.get(BASE, {"ordering": ordering} if ordering else {})
        assert response.status_code == 200
        listing = next(q["sql"] for q in queries if 'FROM "guests_guest"' in q["sql"] and "LIMIT" in q["sql"])
        outer_order_by = listing.rsplit("ORDER BY", 1)[1].split("LIMIT")[0].strip()
        assert outer_order_by.endswith('"guests_guest"."id" ASC'), outer_order_by


class TestDetail:
    def test_includes_profile_stats(self, api, organization, prop):
        guest = GuestFactory(organization=organization)
        ReservationFactory(property=prop, booker=guest, status="checked_out")

        body = api.get(detail(guest)).json()

        assert body["stats"]["stays_count"] == 1
        assert body["stats"]["total_spent"] == "0.00"
        assert body["merged_into"] is None

    def test_list_counters_are_filled_in_every_detail_response(self, api, organization, prop):
        guest = GuestFactory(organization=organization)
        ReservationFactory(property=prop, booker=guest, status="checked_out",
                           checkin_date=date(2025, 1, 1), checkout_date=date(2025, 1, 3))  # fmt: skip
        ReservationFactory(property=prop, booker=guest, status="cancelled")

        for body in (api.get(detail(guest)).json(), api.patch(detail(guest), {"notes": "x"}).json()):
            assert (body["stays_count"], body["reservations_count"], body["last_stay_date"]) == (
                1,
                2,
                "2025-01-01",
            )

    def test_merged_guest_points_to_the_survivor(self, api, organization):
        primary = GuestFactory(organization=organization)
        old = GuestFactory(organization=organization, merged_into=primary)
        assert api.get(detail(old)).json()["merged_into"] == str(primary.pk)

    def test_guests_of_another_organization_are_not_found(self, api):
        stranger = GuestFactory(organization=OrganizationFactory())
        for method in ("get", "patch", "delete"):
            assert getattr(api, method)(detail(stranger)).status_code == 404
        assert api.get(f"{detail(stranger)}stays/").status_code == 404

    def test_chain_members_restricted_to_another_hotel_share_the_guests(
        self, api_for, make_member, organization
    ):
        other_hotel = PropertyFactory(organization=organization)
        clerk = make_member("front_desk", properties=[other_hotel])
        guest = GuestFactory(organization=organization)
        assert api_for(clerk, other_hotel).get(detail(guest)).status_code == 200


class TestCreate:
    def test_creates_a_normalized_guest_with_consent(self, api, organization):
        response = api.post(
            BASE,
            {
                "first_name": "camila", "last_name": "ROJAS", "email": "Camila@Example.com",
                "phone": "310 555 0101", "document_type": "CC", "document_number": "52.123.456",
                "nationality": "co", "country_of_residence": "CO", "data_processing_consent": True,
                "tags": ["corporativo", " corporativo ", "vip empresa"],
            },
        )  # fmt: skip
        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["full_name"], body["email"], body["phone"]) == (
            "Camila Rojas",
            "camila@example.com",
            "+573105550101",
        )
        assert body["document_number"] == "52123456" and body["data_processing_consent_at"]
        assert body["tags"] == ["corporativo", "vip empresa"]
        assert Guest.objects.get(pk=body["id"]).organization == organization
        assert AuditEvent.objects.filter(action="guests.guest_created", target_id=body["id"]).exists()

    def test_existing_document_is_a_409_pointing_to_the_guest(self, api, organization):
        existing = GuestFactory(organization=organization, document_type="CC", document_number="52123456")
        response = api.post(
            BASE, {"first_name": "Otra", "document_type": "CC", "document_number": "52.123.456"}
        )
        assert response.status_code == 409
        assert (response.json()["code"], response.json()["guest_id"]) == ("guest_exists", str(existing.pk))

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"first_name": ""}, "first_name"),
            ({"first_name": "A", "phone": "12"}, "phone"),
            ({"first_name": "A", "email": "no-es-correo"}, "email"),
            ({"first_name": "A", "nationality": "Colombia"}, "nationality"),
            ({"first_name": "A", "document_number": "123"}, "document_type"),
            ({"first_name": "A", "birth_date": "2999-01-01"}, "birth_date"),
            ({"first_name": "A", "language": "fr"}, "language"),
        ],
    )
    def test_validation(self, api, payload, field):
        response = api.post(BASE, payload)
        assert response.status_code == 400
        assert field in response.json()["fields"]

    def test_custom_values_follow_the_organization_guest_fields(self, api, organization):
        CustomFieldDefinition.objects.create(
            organization=organization, applies_to="guest", key="empresa", label={"es": "Empresa"},
            field_type="text",
        )  # fmt: skip
        ok = api.post(BASE, {"first_name": "A", "custom_values": {"empresa": "Ecopetrol"}})
        assert ok.status_code == 201 and ok.json()["custom_values"] == {"empresa": "Ecopetrol"}
        bad = api.post(BASE, {"first_name": "B", "custom_values": {"talla": "M"}})
        assert (bad.status_code, bad.json()["code"]) == (400, "invalid_custom_values")

    def test_front_desk_can_create_but_accountant_only_reads(self, api_for, make_member, prop):
        assert api_for(make_member("front_desk"), prop).post(BASE, {"first_name": "A"}).status_code == 201
        accountant = api_for(make_member("accountant"), prop)
        assert accountant.get(BASE).status_code == 200
        assert accountant.post(BASE, {"first_name": "A"}).status_code == 403


class TestUpdate:
    def test_patch_normalizes_and_audits(self, api, organization):
        guest = GuestFactory(organization=organization, is_vip=False)
        response = api.patch(
            detail(guest), {"is_vip": True, "last_name": "de la torre", "notes": "Piso alto"}
        )
        assert response.status_code == 200
        guest.refresh_from_db()
        assert (guest.is_vip, guest.last_name, guest.notes) == (True, "De la Torre", "Piso alto")
        assert AuditEvent.objects.filter(action="guests.guest_updated", target_id=str(guest.pk)).exists()

    def test_consent_can_be_given_and_revoked(self, api, organization):
        guest = GuestFactory(organization=organization, data_processing_consent_at=None)
        given = api.patch(detail(guest), {"data_processing_consent": True}).json()[
            "data_processing_consent_at"
        ]
        assert given
        again = api.patch(detail(guest), {"data_processing_consent": True}).json()[
            "data_processing_consent_at"
        ]
        assert again == given  # the original date is kept
        assert (
            api.patch(detail(guest), {"data_processing_consent": False}).json()["data_processing_consent_at"]
            is None
        )

    def test_taking_another_guest_document_is_a_409(self, api, organization):
        other = GuestFactory(organization=organization, document_type="CC", document_number="777")
        guest = GuestFactory(organization=organization)
        response = api.patch(detail(guest), {"document_type": "CC", "document_number": "777"})
        assert (response.status_code, response.json()["guest_id"]) == (409, str(other.pk))

    def test_merged_and_anonymized_guests_are_read_only(self, api, organization):
        primary = GuestFactory(organization=organization)
        old = GuestFactory(organization=organization, merged_into=primary)
        assert api.patch(detail(old), {"notes": "x"}).json()["code"] == "guest_merged"
        erased = GuestFactory(organization=organization)
        api.post(f"{detail(erased)}anonymize/", {"confirm": True})
        assert api.patch(detail(erased), {"notes": "x"}).json()["code"] == "guest_anonymized"


class TestDelete:
    def test_guest_without_history_is_deleted(self, api, organization):
        guest = GuestFactory(organization=organization)
        assert api.delete(detail(guest)).status_code == 204
        assert not Guest.objects.filter(pk=guest.pk).exists()

    def test_guest_with_history_is_kept(self, api, organization, prop):
        guest = GuestFactory(organization=organization)
        StayFactory(reservation=ReservationFactory(property=prop), occupants=[guest])
        response = api.delete(detail(guest))
        assert (response.status_code, response.json()["code"]) == (409, "guest_in_use")
        assert Guest.objects.filter(pk=guest.pk).exists()


class TestStays:
    def test_lists_reservations_as_booker_or_occupant(self, api, organization, prop):
        guest = GuestFactory(organization=organization)
        other_hotel = PropertyFactory(organization=organization, name="Andino Medellín")
        booked = ReservationFactory(
            property=prop, booker=guest, code="HT-BOOK01", checkin_date=date(2026, 1, 10),
            checkout_date=date(2026, 1, 12),
        )  # fmt: skip
        shared_reservation = ReservationFactory(
            property=other_hotel,
            code="HT-SHAR01",
            checkin_date=date(2026, 3, 1),
            checkout_date=date(2026, 3, 4),
        )
        shared = StayFactory(reservation=shared_reservation, occupants=[guest])

        rows = api.get(f"{detail(guest)}stays/").json()["results"]

        assert [(r["code"], r["role"], r["nights"], r["property"]["name"]) for r in rows] == [
            ("HT-SHAR01", "occupant", 3, "Andino Medellín"),
            ("HT-BOOK01", "booker", 2, prop.name),
        ]
        assert rows[1]["id"] == str(booked.pk) and rows[0]["id"] == str(shared.reservation_id)


class TestDocuments:
    def test_upload_list_and_delete(self, api, organization):
        guest = GuestFactory(organization=organization)

        created = api.post(
            f"{detail(guest)}documents/",
            {"kind": "passport", "file": SimpleUploadedFile("pasaporte john.png", PNG)},
            format="multipart",
        )

        assert created.status_code == 201, created.json()
        body = created.json()
        assert body["file_url"] == f"/api/v1/guests/documents/{body['id']}/file/"
        assert "/media/" not in json.dumps(body)
        assert (body["kind"], body["uploaded_via"], body["content_type"]) == (
            "passport",
            "staff",
            "image/png",
        )
        listed = api.get(f"{detail(guest)}documents/").json()
        assert [d["id"] for d in listed] == [body["id"]]
        assert api.delete(f"/api/v1/guests/documents/{body['id']}/").status_code == 204
        assert not GuestDocument.objects.filter(pk=body["id"]).exists()

    def test_rejected_file_type_is_a_400(self, api, organization):
        guest = GuestFactory(organization=organization)
        response = api.post(
            f"{detail(guest)}documents/",
            {"kind": "other", "file": SimpleUploadedFile("x.png", b"<html></html>")},
            format="multipart",
        )
        assert (response.status_code, response.json()["code"]) == (400, "invalid_file_type")

    def test_accountant_cannot_upload(self, api_for, make_member, prop, organization):
        guest = GuestFactory(organization=organization)
        response = api_for(make_member("accountant"), prop).post(
            f"{detail(guest)}documents/",
            {"kind": "other", "file": SimpleUploadedFile("x.png", PNG)},
            format="multipart",
        )
        assert response.status_code == 403


class TestDuplicatesAndMerge:
    def test_duplicates_come_with_their_reasons(self, api, organization):
        guest = GuestFactory(organization=organization, email="ana@example.com")
        twin = GuestFactory(organization=organization, email="ANA@example.com")
        rows = api.get(f"{detail(guest)}duplicates/").json()
        assert [(r["id"], r["reasons"]) for r in rows] == [(str(twin.pk), ["email"])]

    def test_lookup_checks_unsaved_data(self, api, organization):
        existing = GuestFactory(organization=organization, document_type="PA", document_number="X123")
        rows = api.get(f"{BASE}lookup/", {"document_type": "PA", "document_number": "x 123"}).json()
        assert [(r["id"], r["reasons"]) for r in rows] == [(str(existing.pk), ["document"])]
        assert api.get(f"{BASE}lookup/").json() == []

    def test_merge_needs_permission_and_confirmation(self, api, api_for, make_member, prop, organization):
        primary = GuestFactory(organization=organization)
        duplicate = GuestFactory(organization=organization)
        payload = {"primary_id": str(primary.pk), "duplicate_id": str(duplicate.pk)}

        clerk = api_for(make_member("front_desk"), prop)
        assert clerk.post(f"{BASE}merge/", {**payload, "confirm": True}).status_code == 403
        unconfirmed = api.post(f"{BASE}merge/", payload)
        assert (unconfirmed.status_code, unconfirmed.json()["code"]) == (400, "confirmation_required")

        merged = api.post(f"{BASE}merge/", {**payload, "confirm": True})

        assert merged.status_code == 200 and merged.json()["id"] == str(primary.pk)
        duplicate.refresh_from_db()
        assert duplicate.merged_into_id == primary.pk
        assert str(duplicate.pk) not in {r["id"] for r in api.get(BASE).json()["results"]}

    def test_merging_an_anonymized_guest_is_a_409(self, api, organization):
        erased = GuestFactory(organization=organization)
        api.post(f"{detail(erased)}anonymize/", {"confirm": True})
        other = GuestFactory(organization=organization)
        response = api.post(
            f"{BASE}merge/", {"primary_id": str(erased.pk), "duplicate_id": str(other.pk), "confirm": True}
        )
        assert (response.status_code, response.json()["code"]) == (409, "guest_anonymized")

    def test_merge_with_a_guest_of_another_organization_is_404(self, api, organization):
        primary = GuestFactory(organization=organization)
        stranger = GuestFactory(organization=OrganizationFactory())
        response = api.post(
            f"{BASE}merge/",
            {"primary_id": str(primary.pk), "duplicate_id": str(stranger.pk), "confirm": True},
        )
        assert response.status_code == 404


class TestHabeasData:
    def test_export_is_a_json_download_and_is_audited(self, api, organization):
        guest = GuestFactory(organization=organization, email="ana@example.com")
        response = api.get(f"{detail(guest)}export/")
        assert response.status_code == 200
        assert response["Content-Disposition"] == f'attachment; filename="huesped-{guest.pk}.json"'
        assert json.loads(response.content)["guest"]["email"] == "ana@example.com"
        assert AuditEvent.objects.filter(action="guests.exported", target_id=str(guest.pk)).exists()

    def test_anonymize_needs_confirmation(self, api, organization):
        guest = GuestFactory(organization=organization, email="ana@example.com")
        assert api.post(f"{detail(guest)}anonymize/", {}).json()["code"] == "confirmation_required"
        body = api.post(f"{detail(guest)}anonymize/", {"confirm": True}).json()
        assert (body["full_name"], body["email"]) == ("Huésped anonimizado", "")
        assert body["anonymized_at"]

    def test_anonymizing_a_merged_record_points_to_the_main_profile(self, api, organization):
        primary = GuestFactory(organization=organization)
        old = GuestFactory(organization=organization, merged_into=primary)
        response = api.post(f"{detail(old)}anonymize/", {"confirm": True})
        assert response.status_code == 409
        assert (response.json()["code"], response.json()["guest_id"]) == ("guest_merged", str(primary.pk))

    def test_front_desk_can_neither_export_nor_anonymize(self, api_for, make_member, prop, organization):
        guest = GuestFactory(organization=organization)
        clerk = api_for(make_member("front_desk"), prop)
        assert clerk.get(f"{detail(guest)}export/").status_code == 403
        assert clerk.post(f"{detail(guest)}anonymize/", {"confirm": True}).status_code == 403


def test_tags_lists_the_organization_tags(api, organization):
    GuestFactory(organization=organization, tags=["frecuente", "luna de miel"])
    GuestFactory(organization=organization, tags=["corporativo", "frecuente"])
    GuestFactory(organization=OrganizationFactory(), tags=["secreto"])
    assert api.get(f"{BASE}tags/").json() == ["corporativo", "frecuente", "luna de miel"]
