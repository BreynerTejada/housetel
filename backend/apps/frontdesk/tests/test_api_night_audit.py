"""Night audit API: `GET night-audit/preview/`, `POST night-audit/run/` (frontdesk.night_audit) and
`GET night-audit/reports/` (frontdesk.view)."""

import pytest
from freezegun import freeze_time

from apps.bookings.tests.helpers import oct_
from apps.core.models import AutomationRun
from apps.frontdesk.models import NightAuditReport
from apps.frontdesk.tests.helpers import new_stay

pytestmark = pytest.mark.django_db

PREVIEW = "/api/v1/frontdesk/night-audit/preview/"
RUN = "/api/v1/frontdesk/night-audit/run/"
REPORTS = "/api/v1/frontdesk/night-audit/reports/"
AFTER_OCT_1 = "2026-10-02 02:00:00-05:00"


@freeze_time(AFTER_OCT_1)
class TestPreviewAndRun:
    def test_the_manager_previews_the_audit(self, hotel, manager, api_for):
        missing = new_stay(hotel, oct_(1), oct_(2))

        response = api_for(manager, hotel.prop).get(PREVIEW)

        assert response.status_code == 200
        body = response.json()
        assert (body["business_date"], body["can_run"], body["due"]) == ("2026-10-01", True, True)
        assert [item["code"] for item in body["summary"]["no_shows"]] == [missing.reservation.code]
        assert body["last_report"] is None

    def test_the_front_desk_cannot_preview_nor_run_it(self, hotel, front_desk, api_for):
        client = api_for(front_desk, hotel.prop)

        preview = client.get(PREVIEW)
        run = client.post(RUN, {"business_date": "2026-10-01"}, format="json")

        assert (preview.status_code, preview.json()["permission"]) == (403, "frontdesk.night_audit")
        assert (run.status_code, run.json()["permission"]) == (403, "frontdesk.night_audit")

    def test_running_it_closes_the_day_once(self, hotel, manager, api_for):
        client = api_for(manager, hotel.prop)

        first = client.post(RUN, {"business_date": "2026-10-01"}, format="json")
        again = client.post(RUN, {"business_date": "2026-10-01"}, format="json")

        assert first.status_code == 201
        report = first.json()
        assert (report["business_date"], report["status"]) == ("2026-10-01", "completed")
        assert report["triggered_by"]["email"] == manager.email
        assert report["summary"]["next_business_date"] == "2026-10-02"
        assert (again.status_code, again.json()["id"]) == (200, report["id"])
        hotel.prop.refresh_from_db()
        assert hotel.prop.business_date == oct_(2)
        run = AutomationRun.objects.get(code="frontdesk.night_audit")
        assert (run.triggered_by, run.status) == (manager, "success")

    def test_a_stale_business_date_is_refused(self, hotel, manager, api_for):
        response = api_for(manager, hotel.prop).post(RUN, {"business_date": "2026-09-28"}, format="json")

        assert response.status_code == 409
        assert (response.json()["code"], response.json()["business_date"]) == (
            "business_date_changed",
            "2026-10-01",
        )

    def test_a_day_that_has_not_started_cannot_be_closed(self, hotel, manager, api_for):
        with freeze_time("2026-09-30 12:00:00-05:00"):
            response = api_for(manager, hotel.prop).post(RUN, {"business_date": "2026-10-01"}, format="json")

        assert (response.status_code, response.json()["code"]) == (409, "audit_ahead")
        assert not NightAuditReport.objects.exists()

    def test_the_date_being_closed_is_required(self, hotel, manager, api_for):
        response = api_for(manager, hotel.prop).post(RUN, {}, format="json")

        assert response.status_code == 400
        assert "business_date" in response.json()["fields"]


@freeze_time(AFTER_OCT_1)
class TestReports:
    def test_the_front_desk_reads_the_closing_reports_of_its_property(
        self, hotel, manager, front_desk, api_for
    ):
        api_for(manager, hotel.prop).post(RUN, {"business_date": "2026-10-01"}, format="json")
        client = api_for(front_desk, hotel.prop)

        listing = client.get(REPORTS)

        assert listing.status_code == 200
        (row,) = listing.json()["results"]
        assert row["business_date"] == "2026-10-01"
        detail = client.get(f"{REPORTS}{row['id']}/")
        assert detail.status_code == 200
        assert detail.json()["summary"]["figures"]["rooms_available"] == 8

    def test_reports_of_another_property_are_invisible(self, hotel, organization, owner, api_for):
        from apps.bookings.tests.helpers import build_hotel
        from apps.core.tests.factories import PropertyFactory

        other = build_hotel(PropertyFactory(organization=organization))
        api_for(owner, other.prop).post(RUN, {"business_date": "2026-10-01"}, format="json")
        report = NightAuditReport.objects.get(property=other.prop)
        client = api_for(owner, hotel.prop)

        assert client.get(REPORTS).json()["results"] == []
        assert client.get(f"{REPORTS}{report.pk}/").status_code == 404

    def test_housekeeping_cannot_read_reports(self, hotel, make_member, api_for):
        response = api_for(make_member("housekeeping"), hotel.prop).get(REPORTS)

        assert (response.status_code, response.json()["permission"]) == (403, "frontdesk.view")
