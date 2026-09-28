"""Staff API `/api/v1/distribution/` (distribution.view to read, distribution.manage to change anything):
connections with nested mappings and their actions, options for the wizard, sync log, ARI queue and the OTA
simulator."""

import copy

import pytest

from apps.bookings.models import Reservation
from apps.bookings.tests.helpers import oct_
from apps.core import integrations
from apps.core.models import AuditEvent, IntegrationSetting
from apps.distribution.models import (
    AriUpdate,
    ChannelConnection,
    RoomMapping,
    SimOtaBooking,
    SimOtaInventory,
    SyncLog,
)
from apps.distribution.services.queue import full_sync
from apps.distribution.tests.factories import connect

pytestmark = pytest.mark.django_db

BASE = "/api/v1/distribution"


def booksim_payload(hotel, **overrides):
    payload = {
        "channel_code": "booksim",
        "name": "BookSim",
        "room_mappings": [
            {"room_type": str(hotel.dbl.pk), "external_room_id": "BS-DBL"},
            {"room_type": str(hotel.ste.pk), "external_room_id": "BS-STE"},
        ],
        "rate_mappings": [
            {"rate_plan": str(hotel.plan.pk), "external_rate_id": "BS-BAR", "markup_percent": "15"}
        ],
    }
    payload.update(overrides)
    return payload


# --- connections --------------------------------------------------------------------------------------------


def test_a_connection_is_created_with_its_mappings_and_synced(hotel, api):
    response = api.post(f"{BASE}/connections/", booksim_payload(hotel, full_sync=True), format="json")

    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["channel_code"], body["status"], body["mode"], body["delivery"], body["simulated"]) == (
        "booksim",
        "active",
        "simulated",
        "push",
        True,
    )
    assert [m["external_room_id"] for m in body["room_mappings"]] == ["BS-DBL", "BS-STE"]
    assert body["room_mappings"][0]["room_type_code"] == "DBL"
    assert body["rate_mappings"][0] | {"id": None} == {
        "id": None,
        "rate_plan": str(hotel.plan.pk),
        "rate_plan_code": "BAR",
        "rate_plan_name": hotel.plan.name,
        "room_type": None,
        "room_type_code": None,
        "external_rate_id": "BS-BAR",
        "markup_percent": "15.00",
    }
    connection = ChannelConnection.objects.get(pk=body["id"])
    assert SimOtaInventory.objects.filter(connection=connection).count() == 2 * 365
    assert connection.last_sync_at is not None
    assert AuditEvent.objects.filter(
        action="distribution.connection_created", target_id=str(connection.pk)
    ).exists()


def test_without_full_sync_the_mapped_categories_are_queued(hotel, api):
    response = api.post(f"{BASE}/connections/", booksim_payload(hotel), format="json")

    assert response.status_code == 201
    assert AriUpdate.objects.filter(connection_id=response.json()["id"], status="pending").count() == 2
    assert response.json()["stats"]["pending_updates"] == 2


def test_one_connection_per_channel_except_ical(hotel, api):
    assert api.post(f"{BASE}/connections/", booksim_payload(hotel), format="json").status_code == 201

    again = api.post(f"{BASE}/connections/", booksim_payload(hotel), format="json")
    assert (again.status_code, again.json()["code"]) == (409, "channel_already_connected")

    for name in ("Airbnb", "VRBO"):
        ical = {"channel_code": "ical", "name": name, "room_mappings": [{"room_type": str(hotel.ste.pk)}]}
        assert api.post(f"{BASE}/connections/", ical, format="json").status_code == 201


@pytest.mark.parametrize(
    ("change", "field"),
    [
        (
            {
                "room_mappings": [
                    {"room_type": "00000000-0000-0000-0000-000000000000", "external_room_id": "X"}
                ]
            },
            "room_mappings",
        ),
        ({"room_mappings": [{"room_type": "DBL"}]}, "room_mappings"),
        ({"room_mappings": [{"room_type": "DBL", "external_room_id": ""}]}, "room_mappings"),
        (
            {
                "room_mappings": [
                    {"room_type": "DBL", "external_room_id": "A"},
                    {"room_type": "STE", "external_room_id": "A"},
                ]
            },
            "room_mappings",
        ),
        (
            {
                "room_mappings": [
                    {"room_type": "DBL", "external_room_id": "A"},
                    {"room_type": "DBL", "external_room_id": "B"},
                ]
            },
            "room_mappings",
        ),
        ({"room_mappings": [{"room_type": "DBL", "room": "101", "external_room_id": "A"}]}, "room_mappings"),
        (
            {"rate_mappings": [{"rate_plan": "BAR", "external_rate_id": "R", "markup_percent": "-95"}]},
            "rate_mappings",
        ),
        ({"rate_mappings": [{"rate_plan": "BAR", "external_rate_id": ""}]}, "rate_mappings"),
        ({"channel_code": "tripadvisor"}, "channel_code"),
    ],
)
def test_invalid_mappings_are_refused(hotel, api, change, field):
    change = copy.deepcopy(change)
    ids = {
        "DBL": str(hotel.dbl.pk),
        "STE": str(hotel.ste.pk),
        "BAR": str(hotel.plan.pk),
        "101": str(hotel.rooms["101"].pk),
    }
    for key in ("room_mappings", "rate_mappings"):
        for item in change.get(key, []):
            for ref in ("room_type", "rate_plan", "room"):
                if item.get(ref) in ids:
                    item[ref] = ids[item[ref]]

    response = api.post(f"{BASE}/connections/", booksim_payload(hotel, **change), format="json")

    assert response.status_code == 400, response.json()
    assert field in response.json()["fields"]
    assert not ChannelConnection.objects.exists()


def test_categories_of_another_property_cannot_be_mapped(hotel, api, organization):
    from apps.bookings.tests.helpers import build_hotel
    from apps.core.tests.factories import PropertyFactory

    other = build_hotel(PropertyFactory(organization=organization))
    payload = booksim_payload(
        hotel, room_mappings=[{"room_type": str(other.dbl.pk), "external_room_id": "BS-X"}]
    )

    response = api.post(f"{BASE}/connections/", payload, format="json")

    assert response.status_code == 400
    assert "room_mappings" in response.json()["fields"]


def test_ical_calendars_map_categories_or_rooms_and_expose_their_export_url(hotel, api):
    payload = {
        "channel_code": "ical",
        "name": "Airbnb",
        "settings": {"import_all_events": True},
        "room_mappings": [
            {
                "room_type": str(hotel.dbl.pk),
                "room": str(hotel.rooms["101"].pk),
                "ical_import_url": "webcal://www.airbnb.com/calendar/ical/1.ics?s=abc",
            },
            {"room_type": str(hotel.ste.pk)},
        ],
    }

    response = api.post(f"{BASE}/connections/", payload, format="json")

    assert response.status_code == 201, response.json()
    body = response.json()
    assert (body["delivery"], body["settings"]) == ("ical", {"import_all_events": True})
    room_calendar, category_calendar = body["room_mappings"]
    assert room_calendar["room_number"] == "101"
    assert room_calendar["ical_import_url"] == "https://www.airbnb.com/calendar/ical/1.ics?s=abc"
    token = RoomMapping.objects.get(pk=category_calendar["id"]).ical_export_token
    assert category_calendar["ical_export_url"].endswith(f"/api/v1/public/distribution/ical/{token}.ics")
    assert not AriUpdate.objects.exists()  # iCal is pull-based


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1/cal.ics", "http://intranet/cal.ics", "ftp://example.com/a.ics"]
)
def test_calendar_urls_on_internal_networks_are_refused(hotel, api, url):
    payload = {
        "channel_code": "ical",
        "name": "Airbnb",
        "room_mappings": [{"room_type": str(hotel.ste.pk), "ical_import_url": url}],
    }

    response = api.post(f"{BASE}/connections/", payload, format="json")

    assert response.status_code == 400
    assert "room_mappings" in response.json()["fields"]


def test_ical_connections_have_no_rates_and_unknown_settings_are_refused(hotel, api):
    base = {"channel_code": "ical", "name": "Airbnb", "room_mappings": [{"room_type": str(hotel.ste.pk)}]}
    with_rates = {**base, "rate_mappings": [{"rate_plan": str(hotel.plan.pk), "external_rate_id": "X"}]}
    assert api.post(f"{BASE}/connections/", with_rates, format="json").status_code == 400
    odd = {**base, "settings": {"surprise": 1}}
    assert api.post(f"{BASE}/connections/", odd, format="json").status_code == 400


def test_the_list_shows_mode_stats_and_integration_without_secrets(hotel, api):
    booksim = connect(hotel, "booksim")
    full_sync(booksim)
    setting = integrations.get_setting(hotel.prop, "channel_channex")
    setting.mode, setting.config = "real", {"environment": "staging", "property_id": "prop-1"}
    setting.save(update_fields=["mode", "config"])
    integrations.set_secrets(setting, {"api_key": "super-secret-key"})
    connect(hotel, "channex", room_types=[hotel.dbl], plans=[])

    response = api.get(f"{BASE}/connections/")

    assert response.status_code == 200
    body = {item["channel_code"]: item for item in response.json()}
    stats = body["booksim"]["stats"]
    assert {
        key: stats[key] for key in ("pending_updates", "failed_updates", "reservations", "errors_24h")
    } == {
        "pending_updates": 0,
        "failed_updates": 0,
        "reservations": 0,
        "errors_24h": 0,
    }
    assert stats["last_out_at"] is not None and stats["last_in_at"] is None  # the full sync went out
    assert stats["in_errors_24h"] == 0
    assert body["booksim"]["integration"] is None
    assert body["channex"]["mode"] == "real" and body["channex"]["simulated"] is False
    assert body["channex"]["integration"] == {
        "kind": "channel_channex",
        "mode": "real",
        "enabled": True,
        "config": {"environment": "staging", "property_id": "prop-1"},
        "secrets": ["api_key"],
    }
    assert "super-secret-key" not in response.content.decode()


def test_the_stats_split_what_went_out_from_what_came_in(hotel, api):
    connection = connect(hotel, "booksim")
    SyncLog.objects.create(connection=connection, direction="out", kind="ari", status="success")
    SyncLog.objects.create(connection=connection, direction="in", kind="booking_new", status="error")
    SyncLog.objects.create(connection=connection, direction="in", kind="booking_new", status="success")

    stats = api.get(f"{BASE}/connections/{connection.pk}/").json()["stats"]

    assert (stats["errors_24h"], stats["in_errors_24h"]) == (1, 1)
    assert stats["last_in_at"] >= stats["last_out_at"]


def test_the_wizard_can_switch_channex_to_real_and_store_its_credentials(hotel, api):
    payload = {
        "channel_code": "channex",
        "name": "Channex",
        "mode": "real",
        "integration": {
            "config": {"environment": "staging", "property_id": "716305c4"},
            "secrets": {"api_key": "k-123"},
        },
        "room_mappings": [{"room_type": str(hotel.dbl.pk), "external_room_id": "994d1375"}],
        "rate_mappings": [
            {"rate_plan": str(hotel.plan.pk), "room_type": str(hotel.dbl.pk), "external_rate_id": "445835fb"}
        ],
    }

    response = api.post(f"{BASE}/connections/", payload, format="json")

    assert response.status_code == 201, response.json()
    setting = IntegrationSetting.objects.get(property=hotel.prop, kind="channel_channex")
    assert (setting.mode, setting.config["property_id"]) == ("real", "716305c4")
    assert integrations.get_secrets(setting) == {"api_key": "k-123"}
    assert "k-123" not in response.content.decode() and "k-123" not in setting.secrets_encrypted
    event = AuditEvent.objects.get(action="distribution.integration_configured")
    assert "k-123" not in str(event.changes)


def test_resending_the_same_integration_config_changes_nothing(hotel, api):
    setting = integrations.get_setting(hotel.prop, "channel_channex")
    setting.config = {"environment": "staging"}
    setting.save(update_fields=["config"])
    connection = connect(hotel, "channex", room_types=[hotel.dbl], plans=[])

    response = api.patch(
        f"{BASE}/connections/{connection.pk}/",
        {"integration": {"config": {"environment": "staging"}}},
        format="json",
    )

    assert response.status_code == 200
    assert not AuditEvent.objects.filter(action="distribution.integration_configured").exists()


def test_unknown_integration_fields_are_refused(hotel, api):
    payload = {
        "channel_code": "channex",
        "name": "Channex",
        "mode": "real",
        "integration": {"secrets": {"password": "x"}},
        "room_mappings": [{"room_type": str(hotel.dbl.pk), "external_room_id": "a"}],
    }

    response = api.post(f"{BASE}/connections/", payload, format="json")

    assert response.status_code == 400
    assert "integration" in response.json()["fields"]


def test_mappings_are_replaced_and_the_channel_is_queued_again(hotel, api):
    connection = connect(hotel, "booksim")
    full_sync(connection)
    AriUpdate.objects.all().delete()
    dbl_mapping = connection.room_mappings.get(room_type=hotel.dbl)

    response = api.patch(
        f"{BASE}/connections/{connection.pk}/",
        {
            "name": "BookSim Colombia",
            "room_mappings": [
                {"id": str(dbl_mapping.pk), "room_type": str(hotel.dbl.pk), "external_room_id": "BS-DOUBLE"},
                {"room_type": str(hotel.dorm_type.pk), "external_room_id": "BS-DORM"},
            ],
        },
        format="json",
    )

    assert response.status_code == 200, response.json()
    assert [m["external_room_id"] for m in response.json()["room_mappings"]] == ["BS-DOUBLE", "BS-DORM"]
    assert (
        connection.room_mappings.get(external_room_id="BS-DOUBLE").pk == dbl_mapping.pk
    )  # kept, not recreated
    assert not connection.room_mappings.filter(room_type=hotel.ste).exists()
    assert sorted(AriUpdate.objects.values_list("room_type__code", flat=True)) == ["DBL", "DORM"]
    # the OTA forgets rooms it no longer has
    assert not SimOtaInventory.objects.filter(
        connection=connection, external_room_id__in=["BS-DBL", "BS-STE"]
    ).exists()
    connection.refresh_from_db()
    assert connection.name == "BookSim Colombia"


def test_pause_keeps_the_queue_and_resume_syncs_everything(hotel, api):
    connection = connect(hotel, "booksim")

    paused = api.post(f"{BASE}/connections/{connection.pk}/pause/")
    assert (paused.status_code, paused.json()["status"]) == (200, "paused")
    assert api.post(f"{BASE}/connections/{connection.pk}/full-sync/").status_code == 409

    resumed = api.post(f"{BASE}/connections/{connection.pk}/resume/")
    assert (resumed.status_code, resumed.json()["connection"]["status"]) == (200, "active")
    assert resumed.json()["sync"]["sent"] == 2
    assert SimOtaInventory.objects.filter(connection=connection).count() == 2 * 365
    actions = set(AuditEvent.objects.values_list("action", flat=True))
    assert {"distribution.connection_paused", "distribution.connection_resumed"} <= actions


def test_full_sync_and_test_actions(hotel, api):
    connection = connect(hotel, "airsim")

    synced = api.post(f"{BASE}/connections/{connection.pk}/full-sync/")
    tested = api.post(f"{BASE}/connections/{connection.pk}/test/")

    assert (synced.status_code, synced.json()["sent"], synced.json()["failed"]) == (200, 2, 0)
    assert tested.status_code == 200 and tested.json()["ok"] is True and tested.json()["message"]
    assert SyncLog.objects.filter(connection=connection, kind="test", status="success").exists()


def test_ical_connections_do_not_full_sync(hotel, api):
    connection = connect(hotel, "ical", plans=[])

    response = api.post(f"{BASE}/connections/{connection.pk}/full-sync/")

    assert (response.status_code, response.json()["code"]) == (400, "not_supported")


def test_pull_downloads_the_bookings_of_pull_channels(hotel, api):
    from apps.distribution.services import simulator

    channex = connect(hotel, "channex")
    full_sync(channex)
    simulator.create_booking(
        channex,
        external_room_id="CH-DBL",
        external_rate_id="CH-BAR",
        checkin=oct_(10),
        checkout=oct_(12),
        adults=2,
    )

    pulled = api.post(f"{BASE}/connections/{channex.pk}/pull/")
    booksim = connect(hotel, "booksim")
    refused = api.post(f"{BASE}/connections/{booksim.pk}/pull/")

    assert (pulled.status_code, pulled.json()["created"]) == (200, 1)
    assert (refused.status_code, refused.json()["code"]) == (400, "not_supported")


def test_deleting_a_connection_keeps_its_reservations(hotel, api):
    from apps.distribution.services import simulator

    connection = connect(hotel, "booksim")
    full_sync(connection)
    booking = simulator.create_booking(
        connection,
        external_room_id="BS-DBL",
        external_rate_id="BS-BAR",
        checkin=oct_(10),
        checkout=oct_(11),
        adults=1,
    )

    response = api.delete(f"{BASE}/connections/{connection.pk}/")

    assert response.status_code == 204
    assert not ChannelConnection.objects.exists()
    assert Reservation.objects.filter(external_id=booking.external_id, status="confirmed").exists()
    assert AuditEvent.objects.filter(action="distribution.connection_deleted").exists()


# --- options, logs, queue -----------------------------------------------------------------------------------


def test_options_describe_channels_categories_plans_and_integrations(hotel, api):
    response = api.get(f"{BASE}/options/")

    assert response.status_code == 200
    body = response.json()
    channels = {item["code"]: item for item in body["channels"]}
    assert set(channels) == {"booksim", "airsim", "ical", "channex"}
    assert (channels["booksim"]["delivery"], channels["booksim"]["modes"]) == ("push", ["simulated"])
    assert channels["channex"]["modes"] == ["real", "simulated"]
    assert channels["channex"]["connected"] is False
    assert [item["code"] for item in body["room_types"]] == ["DBL", "STE", "DORM"]
    assert body["rate_plans"][0] | {"id": None, "sample": None} == {
        "id": None,
        "code": "BAR",
        "name": hotel.plan.name,
        "kind": "base",
        "room_types": [str(hotel.dbl.pk), str(hotel.ste.pk), str(hotel.dorm_type.pk)],
        "is_public": True,
        "is_active": True,
        "channels": [],
        "sample": None,
    }
    # a real price per plan so the wizard can show what the channel will charge after the markup
    assert body["rate_plans"][0]["sample"] == {
        "room_type": str(hotel.dbl.pk),
        "date": "2026-10-01",
        "price": "320000.00",
    }
    assert body["integrations"]["channel_channex"]["mode"] == "simulated"
    fields = {field["name"]: field for field in body["integrations"]["channel_channex"]["fields"]}
    assert fields["api_key"]["secret"] is True and "environment" in fields


def test_the_catalog_suggests_ids_for_simulated_channels(hotel, api):
    response = api.get(f"{BASE}/options/catalog/", {"channel": "airsim"})

    assert response.status_code == 200
    assert response.json()["rooms"][0] == {"id": "AS-DBL", "title": hotel.dbl.name["es"]}
    assert response.json()["rates"][0]["id"] == "AS-BAR"


def test_the_catalog_of_a_misconfigured_real_channex_explains_what_is_missing(hotel, api):
    setting = integrations.get_setting(hotel.prop, "channel_channex")
    setting.mode = "real"
    setting.save(update_fields=["mode"])

    response = api.get(f"{BASE}/options/catalog/", {"channel": "channex"})

    assert (response.status_code, response.json()["code"]) == (400, "integration_misconfigured")


def test_the_sync_log_is_filterable(hotel, api):
    booksim = connect(hotel, "booksim")
    airsim = connect(hotel, "airsim")
    SyncLog.objects.create(
        connection=booksim, direction="out", kind="ari", status="success", message="ARI enviado"
    )
    SyncLog.objects.create(
        connection=booksim,
        direction="in",
        kind="booking_new",
        status="error",
        message="Sin mapear",
        external_id="BS-77",
    )
    SyncLog.objects.create(
        connection=airsim, direction="out", kind="ari", status="success", message="ARI enviado"
    )

    everything = api.get(f"{BASE}/logs/").json()
    errors = api.get(f"{BASE}/logs/", {"status": "error"}).json()
    of_booksim = api.get(f"{BASE}/logs/", {"connection": str(booksim.pk), "direction": "out"}).json()
    searched = api.get(f"{BASE}/logs/", {"q": "BS-77"}).json()

    assert everything["count"] == 3
    assert [row["external_id"] for row in errors["results"]] == ["BS-77"]
    assert of_booksim["count"] == 1 and of_booksim["results"][0]["connection"]["channel_code"] == "booksim"
    assert searched["count"] == 1


def test_the_queue_lists_updates_and_failed_ones_can_be_retried(hotel, api):
    connection = connect(hotel, "booksim")
    from apps.distribution.services.queue import enqueue_ari

    enqueue_ari(hotel.prop, room_type_ids=[hotel.dbl.pk], start=oct_(5), end=oct_(6))
    AriUpdate.objects.update(status="failed", attempts=5, last_error="La OTA no responde")

    listed = api.get(f"{BASE}/queue/", {"status": "failed"})
    assert listed.status_code == 200
    (row,) = listed.json()["results"]
    assert (row["room_type"]["code"], row["kinds"], row["attempts"], row["last_error"]) == (
        "DBL",
        ["availability", "rates", "restrictions"],
        5,
        "La OTA no responde",
    )

    retried = api.post(f"{BASE}/queue/retry/", {"connection": str(connection.pk)}, format="json")

    assert (retried.status_code, retried.json()["retried"], retried.json()["sent"]) == (200, 1, 1)
    assert AriUpdate.objects.get().status == "sent"


# --- simulator ----------------------------------------------------------------------------------------------


def test_the_simulator_flow_through_the_api(hotel, api):
    connection = connect(hotel, "booksim", markup="10")
    full_sync(connection)
    base = f"{BASE}/simulator/{connection.pk}"

    grid = api.get(f"{base}/inventory/", {"start": "2026-10-10", "end": "2026-10-12"})
    assert grid.status_code == 200
    assert grid.json()["rooms"][0]["rates"][0]["cells"][0]["price"] == "352000.00"

    created = api.post(
        f"{base}/bookings/",
        {
            "external_room_id": "BS-DBL",
            "external_rate_id": "BS-BAR",
            "checkin": "2026-10-10",
            "checkout": "2026-10-12",
            "adults": 2,
            "guest": {"first_name": "Ana", "last_name": "Ruiz", "country": "CO"},
        },
        format="json",
    )
    assert created.status_code == 201, created.json()
    booking = created.json()
    assert (booking["status"], booking["pms_status"], booking["revision"]) == ("new", "imported", 1)
    reservation = Reservation.objects.get(external_id=booking["external_id"])
    assert booking["reservation"] == {
        "id": str(reservation.pk),
        "code": reservation.code,
        "status": "confirmed",
    }

    modified = api.post(
        f"{base}/bookings/{booking['external_id']}/modify/", {"checkout": "2026-10-13"}, format="json"
    )
    assert (modified.status_code, modified.json()["revision"]) == (200, 2)
    listed = api.get(f"{base}/bookings/")
    assert listed.json()["count"] == 1 and listed.json()["results"][0]["status"] == "modified"

    cancelled = api.post(f"{base}/bookings/{booking['external_id']}/cancel/")
    assert (cancelled.status_code, cancelled.json()["reservation"]["status"]) == (200, "cancelled")
    delivered = api.post(f"{base}/bookings/{booking['external_id']}/deliver/")
    assert (delivered.status_code, delivered.json()["pms_status"]) == (200, "imported")


def test_simulator_errors_are_explained(hotel, api):
    connection = connect(hotel, "booksim")  # never synced: the OTA has nothing to sell
    base = f"{BASE}/simulator/{connection.pk}"
    payload = {
        "external_room_id": "BS-DBL",
        "external_rate_id": "BS-BAR",
        "checkin": "2026-10-10",
        "checkout": "2026-10-12",
        "adults": 2,
    }

    refused = api.post(f"{base}/bookings/", payload, format="json")
    forced = api.post(f"{base}/bookings/", {**payload, "force": True}, format="json")
    unknown = api.post(f"{base}/bookings/NOPE/cancel/")
    inverted = api.post(f"{base}/bookings/", {**payload, "checkout": "2026-10-09"}, format="json")
    ical = connect(hotel, "ical", plans=[])
    not_simulated = api.get(f"{BASE}/simulator/{ical.pk}/inventory/")

    assert (refused.status_code, refused.json()["code"]) == (409, "ota_not_sellable")
    assert refused.json()["reasons"]
    assert forced.status_code == 201 and forced.json()["payload"]["forced"] is True
    assert unknown.status_code == 404
    assert inverted.status_code == 400
    assert (not_simulated.status_code, not_simulated.json()["code"]) == (400, "not_simulated")
    assert SimOtaBooking.objects.count() == 1


def test_the_inventory_range_is_bounded(hotel, api):
    connection = connect(hotel, "booksim")

    too_long = api.get(
        f"{BASE}/simulator/{connection.pk}/inventory/", {"start": "2026-10-01", "end": "2027-01-01"}
    )
    default = api.get(f"{BASE}/simulator/{connection.pk}/inventory/")

    assert too_long.status_code == 400
    assert default.status_code == 200 and len(default.json()["dates"]) == 14
    assert default.json()["dates"][0] == "2026-10-01"  # from the business date


# --- permissions and isolation ------------------------------------------------------------------------------


def test_front_desk_reads_channels_but_cannot_change_them(hotel, api_for, make_member):
    connection = connect(hotel, "booksim")
    client = api_for(make_member("front_desk"), hotel.prop)

    assert client.get(f"{BASE}/connections/").status_code == 200
    assert client.get(f"{BASE}/logs/").status_code == 200
    assert client.get(f"{BASE}/simulator/{connection.pk}/inventory/").status_code == 200
    for method, path in (
        ("post", f"{BASE}/connections/"),
        ("patch", f"{BASE}/connections/{connection.pk}/"),
        ("delete", f"{BASE}/connections/{connection.pk}/"),
        ("post", f"{BASE}/connections/{connection.pk}/full-sync/"),
        ("post", f"{BASE}/connections/{connection.pk}/pause/"),
        ("post", f"{BASE}/queue/retry/"),
        ("post", f"{BASE}/simulator/{connection.pk}/bookings/"),
    ):
        response = getattr(client, method)(path, {}, format="json")
        assert (response.status_code, response.json().get("permission")) == (403, "distribution.manage"), path


def test_housekeeping_cannot_see_channels(hotel, api_for, make_member):
    client = api_for(make_member("housekeeping"), hotel.prop)

    response = client.get(f"{BASE}/connections/")

    assert (response.status_code, response.json()["permission"]) == (403, "distribution.view")


def test_connections_of_other_organizations_are_invisible(hotel, api, api_for):
    from apps.accounts.services import add_member, ensure_system_roles
    from apps.accounts.tests.factories import UserFactory
    from apps.bookings.tests.helpers import build_hotel
    from apps.core.tests.factories import OrganizationFactory, PropertyFactory

    other_org = OrganizationFactory()
    ensure_system_roles(other_org)
    other = build_hotel(PropertyFactory(organization=other_org))
    foreign = connect(other, "booksim")
    SyncLog.objects.create(connection=foreign, direction="out", kind="ari", status="success")
    stranger = UserFactory()
    add_member(other_org, stranger, "owner")
    mine = connect(hotel, "booksim")

    assert [item["id"] for item in api.get(f"{BASE}/connections/").json()] == [str(mine.pk)]
    for path in (f"{BASE}/connections/{foreign.pk}/", f"{BASE}/simulator/{foreign.pk}/inventory/"):
        assert api.get(path).status_code == 404
    assert api.post(f"{BASE}/connections/{foreign.pk}/full-sync/").status_code == 404
    assert api.get(f"{BASE}/logs/").json()["count"] == 0
    assert api_for(stranger, hotel.prop).get(f"{BASE}/connections/").status_code == 404  # not their property


def test_anonymous_requests_are_rejected(hotel, public_api):
    response = public_api.get(f"{BASE}/connections/", HTTP_X_PROPERTY_ID=str(hotel.prop.pk))

    assert response.status_code == 401
