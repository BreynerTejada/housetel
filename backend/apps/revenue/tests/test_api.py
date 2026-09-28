"""Staff API of revenue (`/api/v1/revenue/`): settings, rules, bounds, recommendations (list, calendar,
summary, approve/reject/apply), runs, run-now and simulate. `revenue.view` reads, `revenue.manage` writes."""

from decimal import Decimal

import pytest

from apps.core.models import AuditEvent, AutomationRun
from apps.inventory.tests.factories import RoomTypeFactory
from apps.rates.models import DailyRate
from apps.revenue.models import PriceBounds, PricingRule, RateRecommendation, RevenueRun
from apps.revenue.services.runs import run_revenue
from apps.revenue.tests.conftest import make_rule, oct_

pytestmark = pytest.mark.django_db

URL = "/api/v1/revenue/"
D = Decimal
OCCUPANCY_RULE = {
    "name": "Ocupación",
    "kind": "occupancy",
    "params": {"tiers": [{"min": 85, "max": 100, "adjust": 15}, {"min": 0, "max": 40, "adjust": "-8"}]},
    "combine": "stack",
    "priority": 20,
}


@pytest.fixture
def client(api, hotel):
    return api


@pytest.fixture
def pending(hotel):
    """Pending recommendations for the 15 holiday/long-weekend nights of the horizon (336.000 each)."""
    make_rule(hotel.prop, "holiday", {"adjust": 12}, name="Festivos")
    run_revenue(hotel.prop)
    return {rec.date: rec for rec in RateRecommendation.objects.filter(status="pending")}


class TestSettings:
    def test_defaults_are_created_on_first_read(self, client, hotel):
        hotel.settings.delete()
        response = client.get(URL + "settings/")
        assert response.status_code == 200
        assert response.json() == {
            "enabled": True,
            "auto_apply": False,
            "horizon_days": 120,
            "max_daily_change_percent": "20.00",
            "min_change_percent": "2.00",
            "price_rounding": "1000.00",
            "updated_at": response.json()["updated_at"],
        }

    def test_patch_validates_and_audits(self, client, hotel):
        response = client.patch(URL + "settings/", {"auto_apply": True, "horizon_days": 90}, format="json")
        assert response.status_code == 200
        assert (response.json()["auto_apply"], response.json()["horizon_days"]) == (True, 90)
        event = AuditEvent.objects.get(action="revenue.settings_updated")
        assert event.changes == {"auto_apply": [False, True], "horizon_days": [120, 90]}
        bad = client.patch(
            URL + "settings/", {"horizon_days": 400, "max_daily_change_percent": 0}, format="json"
        )
        assert bad.status_code == 400
        assert set(bad.json()["fields"]) == {"horizon_days", "max_daily_change_percent"}


class TestRules:
    def test_create_normalizes_the_params(self, client, hotel):
        response = client.post(
            URL + "rules/", {**OCCUPANCY_RULE, "room_types": [str(hotel.room_type.pk)]}, format="json"
        )
        assert response.status_code == 201, response.json()
        body = response.json()
        assert body["params"] == {
            "tiers": [{"min": 0, "max": 40, "adjust": -8}, {"min": 85, "max": 100, "adjust": 15}]
        }
        assert body["room_types"] == [str(hotel.room_type.pk)]
        assert (body["combine"], body["priority"], body["is_active"]) == ("stack", 20, True)
        assert AuditEvent.objects.filter(action="revenue.rule_created").exists()

    def test_invalid_params_are_a_field_error(self, client):
        rule = {**OCCUPANCY_RULE, "params": {"tiers": [{"min": 50, "max": 20, "adjust": 5}]}}
        response = client.post(URL + "rules/", rule, format="json")
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_rule_params"
        assert "params" in response.json()["fields"]

    def test_changing_the_kind_revalidates_the_params(self, client, hotel):
        rule = make_rule(hotel.prop, "holiday", {"adjust": 12})
        response = client.patch(URL + f"rules/{rule.pk}/", {"kind": "event"}, format="json")
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_rule_params"

    def test_categories_of_another_property_are_rejected(self, client, hotel):
        foreign = RoomTypeFactory()
        response = client.post(
            URL + "rules/", {**OCCUPANCY_RULE, "room_types": [str(foreign.pk)]}, format="json"
        )
        assert response.status_code == 400
        assert "room_types" in response.json()["fields"]

    def test_update_and_delete(self, client, hotel):
        rule = make_rule(hotel.prop, "holiday", {"adjust": 12})
        response = client.patch(
            URL + f"rules/{rule.pk}/", {"params": {"adjust": 15}, "is_active": False}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["params"] == {"adjust": 15, "include_bridges": True}
        assert client.delete(URL + f"rules/{rule.pk}/").status_code == 204
        assert not PricingRule.objects.exists()
        assert {e.action for e in AuditEvent.objects.all()} >= {
            "revenue.rule_updated",
            "revenue.rule_deleted",
        }


class TestBounds:
    def test_post_creates_then_updates_the_bounds_of_a_category_and_plan(self, client, hotel):
        payload = {
            "room_type": str(hotel.room_type.pk),
            "rate_plan": str(hotel.plan.pk),
            "min_price": "250000",
        }
        created = client.post(URL + "bounds/", payload, format="json")
        assert created.status_code == 201, created.json()
        assert (created.json()["min_price"], created.json()["max_price"]) == ("250000.00", None)
        updated = client.post(URL + "bounds/", {**payload, "max_price": "500000"}, format="json")
        assert updated.status_code == 200
        assert PriceBounds.objects.get().max_price == D("500000")

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"min_price": None, "max_price": None}, "min_price"),
            ({"min_price": "600000", "max_price": "500000"}, "max_price"),
            ({"min_price": "0"}, "min_price"),
            ({"rate_plan": "derived"}, "rate_plan"),
            ({"room_type": "other"}, "room_type"),
        ],
    )
    def test_validation(self, client, hotel, change, field):
        payload = {
            "room_type": str(hotel.room_type.pk),
            "rate_plan": str(hotel.plan.pk),
            "min_price": "250000",
        }
        payload.update(change)
        if payload["rate_plan"] == "derived":
            payload["rate_plan"] = str(hotel.derived.pk)
        if payload["room_type"] == "other":  # a category of the hotel that the plan does not sell
            payload["room_type"] = str(RoomTypeFactory(property=hotel.prop).pk)
        response = client.post(URL + "bounds/", payload, format="json")
        assert response.status_code == 400
        assert field in response.json()["fields"]


class TestRecommendations:
    def test_list_filters_and_shape(self, client, hotel, pending):
        response = client.get(URL + "recommendations/", {"start": "2026-10-10", "end": "2026-10-13"})
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 3
        item = body["results"][0]
        assert item["date"] == "2026-10-10"
        assert item["room_type"] == {
            "id": str(hotel.room_type.pk),
            "code": "DBL",
            "name": hotel.room_type.name,
            "color": hotel.room_type.color,
        }
        assert item["rate_plan"]["code"] == "FLEX"
        assert (item["current_price"], item["recommended_price"], item["change_percent"]) == (
            "300000.00",
            "336000.00",
            "12.00",
        )
        assert item["status"] == "pending"
        assert item["explanation"]["es"].startswith("Sube 12 %")
        assert item["reasons"][0]["kind"] == "holiday"
        assert client.get(URL + "recommendations/", {"status": "applied"}).json()["count"] == 0

    def test_calendar_has_one_row_per_category_and_plan(self, client, hotel, pending):
        response = client.get(URL + "recommendations/calendar/", {"start": "2026-10-09", "end": "2026-10-14"})
        assert response.status_code == 200
        body = response.json()
        assert body["dates"] == ["2026-10-09", "2026-10-10", "2026-10-11", "2026-10-12", "2026-10-13"]
        assert body["holidays"] == [{"date": "2026-10-12", "name": "Día de la Raza"}]
        assert len(body["rows"]) == 1
        row = body["rows"][0]
        assert (row["room_type"]["code"], row["rate_plan"]["code"]) == ("DBL", "FLEX")
        assert sorted(row["cells"]) == ["2026-10-10", "2026-10-11", "2026-10-12"]
        cell = row["cells"]["2026-10-12"]
        assert cell == {
            "id": str(pending[oct_(12)].pk),
            "status": "pending",
            "change_percent": "12.00",
            "current_price": "300000.00",
            "recommended_price": "336000.00",
            "occupancy": "0.00",
        }

    def test_calendar_range_is_validated(self, client):
        assert client.get(URL + "recommendations/calendar/", {"start": "2026-10-09"}).status_code == 400
        too_long = client.get(URL + "recommendations/calendar/", {"start": "2026-10-01", "end": "2027-10-01"})
        assert too_long.status_code == 400

    def test_summary(self, client, hotel, pending):
        body = client.get(URL + "recommendations/summary/").json()
        assert (body["pending"], body["up"], body["down"]) == (15, 15, 0)
        assert (body["avg_change_percent"], body["estimated_impact"]) == ("12.00", "5400000.00")
        assert body["first_date"] == "2026-10-10"
        assert body["last_run"]["recommendations_count"] == 15
        assert (body["enabled"], body["auto_apply"], body["currency"]) == (True, False, "COP")

    def test_summary_splits_the_impact_of_raises_and_drops(self, client, hotel):
        """A drop on a night with many free rooms must not hide the raises: both sides are reported."""
        make_rule(hotel.prop, "event", {"start": "2026-10-20", "end": "2026-10-20", "adjust": 10})
        make_rule(hotel.prop, "event", {"start": "2026-10-21", "end": "2026-10-21", "adjust": -5})
        run_revenue(hotel.prop)
        body = client.get(URL + "recommendations/summary/").json()
        # 20 Oct: 300.000 → 330.000 on 10 free rooms; 21 Oct: 300.000 → 285.000 on 10 free rooms
        assert (body["up"], body["down"]) == (1, 1)
        assert (body["impact_up"], body["impact_down"], body["estimated_impact"]) == (
            "300000.00",
            "-150000.00",
            "150000.00",
        )

    def test_approve_applies_and_reports(self, client, hotel, pending, django_capture_on_commit_callbacks):
        ids = [str(pending[oct_(day)].pk) for day in (10, 11, 12)]
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(URL + "recommendations/approve/", {"ids": ids}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert (body["updated"], body["skipped"], body["errors"]) == (3, [], [])
        assert {item["status"] for item in body["recommendations"]} == {"applied"}
        assert sorted(DailyRate.objects.values_list("date", "price", "source")) == [
            (oct_(10), D("336000"), "revenue"),
            (oct_(11), D("336000"), "revenue"),
            (oct_(12), D("336000"), "revenue"),
        ]

    def test_reject_and_apply(self, client, hotel, pending):
        rejected = client.post(
            URL + "recommendations/reject/", {"ids": [str(pending[oct_(10)].pk)]}, format="json"
        )
        assert rejected.json()["recommendations"][0]["status"] == "rejected"
        applied = client.post(
            URL + "recommendations/apply/", {"ids": [str(pending[oct_(11)].pk)]}, format="json"
        )
        assert applied.json()["recommendations"][0]["status"] == "applied"

    def test_decisions_need_ids(self, client):
        response = client.post(URL + "recommendations/approve/", {"ids": []}, format="json")
        assert response.status_code == 400
        assert "ids" in response.json()["fields"]


class TestRuns:
    def test_run_now_goes_through_the_automation(self, client, hotel, owner):
        make_rule(hotel.prop, "holiday", {"adjust": 12})
        response = client.post(URL + "run-now/", {}, format="json")
        assert response.status_code == 201, response.json()
        body = response.json()
        assert (body["trigger"], body["status"], body["recommendations_count"]) == ("manual", "success", 15)
        assert body["triggered_by"]["email"] == owner.email
        assert body["summary"]["es"].startswith("Se revisaron")
        automation = AutomationRun.objects.get(code="revenue.run_rules")
        assert (automation.status, automation.triggered_by) == ("success", owner)
        assert client.get(URL + "runs/").json()["results"][0]["id"] == body["id"]
        assert client.get(URL + f"runs/{body['id']}/").status_code == 200

    def test_run_now_is_refused_while_revenue_is_disabled(self, client, hotel):
        hotel.settings.enabled = False
        hotel.settings.save()
        response = client.post(URL + "run-now/", {}, format="json")
        assert (response.status_code, response.json()["code"]) == (409, "revenue_disabled")
        assert not RevenueRun.objects.exists()


class TestSimulate:
    def test_simulate_never_persists(self, client, hotel):
        make_rule(hotel.prop, "holiday", {"adjust": 12})
        response = client.post(URL + "simulate/", {"start": "2026-10-01", "end": "2026-11-01"}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["count"] == 4  # 10–12 Oct and 31 Oct (Saturday of the 2 Nov long weekend)
        assert (body["summary"]["impact_up"], body["summary"]["impact_down"]) == ("1440000.00", "0.00")
        assert [item["date"] for item in body["recommendations"]][:3] == [
            "2026-10-10",
            "2026-10-11",
            "2026-10-12",
        ]
        assert body["recommendations"][0]["id"] is None
        assert not RateRecommendation.objects.exists() and not RevenueRun.objects.exists()

    def test_simulate_a_draft_rule(self, client, hotel):
        stored = make_rule(hotel.prop, "holiday", {"adjust": 12})
        draft = {"id": str(stored.pk), "name": "Festivos", "kind": "holiday", "params": {"adjust": 20}}
        response = client.post(
            URL + "simulate/", {"start": "2026-10-12", "end": "2026-10-13", "rule": draft}, format="json"
        )
        assert response.status_code == 200
        assert [item["recommended_price"] for item in response.json()["recommendations"]] == ["360000.00"]
        stored.refresh_from_db()
        assert stored.params == {"adjust": 12, "include_bridges": True}

    def test_an_invalid_draft_is_a_400(self, client):
        response = client.post(
            URL + "simulate/", {"rule": {"name": "x", "kind": "holiday", "params": {}}}, format="json"
        )
        assert response.status_code == 400


def test_options_list_the_categories_and_base_plans(client, hotel):
    body = client.get(URL + "options/").json()
    assert [rt["code"] for rt in body["room_types"]] == ["DBL"]
    assert [(plan["code"], plan["room_types"]) for plan in body["rate_plans"]] == [
        ("FLEX", [str(hotel.room_type.pk)])
    ]
    assert (body["currency"], body["business_date"]) == ("COP", "2026-10-01")


def test_options_carry_the_default_price_of_each_category_in_each_base_plan(client, hotel):
    unpriced = RoomTypeFactory(property=hotel.prop, code="STE", sort_order=2)
    hotel.plan.room_types.add(unpriced)
    plan = client.get(URL + "options/").json()["rate_plans"][0]
    assert plan["default_prices"] == {str(hotel.room_type.pk): "300000.00", str(unpriced.pk): None}


class TestAccess:
    READS = [
        "settings/",
        "rules/",
        "bounds/",
        "recommendations/",
        "recommendations/summary/",
        "runs/",
        "options/",
    ]

    @pytest.mark.parametrize("path", READS)
    def test_front_desk_reads(self, api_for, make_member, hotel, path):
        response = api_for(make_member("front_desk"), hotel.prop).get(URL + path)
        assert response.status_code == 200

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("patch", "settings/"),
            ("post", "rules/"),
            ("post", "bounds/"),
            ("post", "recommendations/approve/"),
            ("post", "recommendations/reject/"),
            ("post", "recommendations/apply/"),
            ("post", "run-now/"),
            ("post", "simulate/"),
        ],
    )
    def test_front_desk_cannot_decide_or_configure(self, api_for, make_member, hotel, method, path):
        response = getattr(api_for(make_member("front_desk"), hotel.prop), method)(
            URL + path, {}, format="json"
        )
        assert response.status_code == 403
        assert response.json()["permission"] == "revenue.manage"

    @pytest.mark.parametrize("path", READS)
    def test_housekeeping_sees_nothing(self, api_for, make_member, hotel, path):
        response = api_for(make_member("housekeeping"), hotel.prop).get(URL + path)
        assert (response.status_code, response.json()["permission"]) == (403, "revenue.view")

    def test_another_organization_never_sees_the_property(self, api_for, hotel):
        from apps.accounts.services import add_member, ensure_system_roles
        from apps.accounts.tests.factories import UserFactory
        from apps.core.tests.factories import OrganizationFactory

        org = OrganizationFactory()
        ensure_system_roles(org)
        stranger = UserFactory()
        add_member(org, stranger, "owner")
        assert api_for(stranger, hotel.prop).get(URL + "rules/").status_code == 404

    def test_rows_of_another_property_are_not_found(self, api, hotel):
        from apps.core.tests.factories import PropertyFactory

        other = PropertyFactory(organization=hotel.prop.organization)
        rule = make_rule(other, "holiday", {"adjust": 12})
        foreign_type = RoomTypeFactory(property=other)
        run = RevenueRun.objects.create(property=other)
        rec = RateRecommendation.objects.create(
            property=other,
            room_type=foreign_type,
            rate_plan=hotel.plan,
            date=oct_(20),
            current_price=D("1"),
            anchor_price=D("1"),
            recommended_price=D("2"),
            change_percent=D("100"),
        )
        assert api.get(URL + f"rules/{rule.pk}/").status_code == 404
        assert api.get(URL + f"runs/{run.pk}/").status_code == 404
        assert api.get(URL + f"recommendations/{rec.pk}/").status_code == 404
        assert api.get(URL + "recommendations/").json()["count"] == 0
        response = api.post(URL + "recommendations/approve/", {"ids": [str(rec.pk)]}, format="json")
        assert response.json()["skipped"] == [{"id": str(rec.pk), "reason": "not_found"}]
