"""Lifecycle rules API: `/api/v1/messaging/lifecycle-rules/`."""

import pytest

from apps.core.models import AuditEvent
from apps.core.tests.factories import PropertyFactory
from apps.messaging.models import LifecycleRule
from apps.messaging.tests.factories import LifecycleRuleFactory, MessageTemplateFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/messaging/lifecycle-rules/"


def test_the_six_rules_exist_with_their_defaults(api, prop):
    rows = api.get(URL).json()
    assert [row["event"] for row in rows] == [
        "confirmation",
        "pre_arrival",
        "arrival_day",
        "post_stay",
        "payment_reminder",
        "cancellation",
    ]
    pre_arrival = rows[1]
    assert {
        k: pre_arrival[k]
        for k in (
            "enabled",
            "days_offset",
            "channels",
            "template_code",
            "send_after",
            "scheduled",
            "uses_offset",
        )
    } == {
        "enabled": True,
        "days_offset": 3,
        "channels": ["email", "whatsapp"],
        "template_code": "pre_arrival",
        "send_after": "09:00",
        "scheduled": True,
        "uses_offset": True,
    }
    assert pre_arrival["label"] == {
        "es": "Antes de la llegada (check-in en línea)",
        "en": "Before arrival (online check-in)",
    }
    assert (rows[0]["scheduled"], rows[0]["uses_offset"]) == (False, False)
    assert LifecycleRule.objects.filter(property=prop).count() == 6


def test_rules_are_per_hotel(api, prop):
    LifecycleRuleFactory(
        property=PropertyFactory(organization=prop.organization), event="confirmation", enabled=False
    )
    assert api.get(URL).json()[0]["enabled"] is True


def test_update_a_rule(api, prop):
    rule = api.get(URL).json()[3]  # post_stay
    response = api.patch(
        f"{URL}{rule['id']}/",
        {"enabled": False, "days_offset": 2, "channels": ["whatsapp", "email"], "send_after": "10:30"},
        format="json",
    )
    assert response.status_code == 200
    row = LifecycleRule.objects.get(pk=rule["id"])
    assert (row.enabled, row.days_offset, row.channels, row.send_after.strftime("%H:%M")) == (
        False,
        2,
        ["email", "whatsapp"],
        "10:30",
    )


def test_a_custom_template_can_be_chosen(api, prop):
    MessageTemplateFactory(property=prop, code="welcome_drink", name="Cóctel", body="Salud")
    rule = api.get(URL).json()[2]
    response = api.patch(f"{URL}{rule['id']}/", {"template_code": "welcome_drink"}, format="json")
    assert response.status_code == 200 and response.json()["template_code"] == "welcome_drink"


def test_validation(api):
    rule = api.get(URL).json()[1]

    def patch(**body):
        return api.patch(f"{URL}{rule['id']}/", body, format="json")

    assert "channels" in patch(channels=["sms"]).json()["fields"]
    assert "days_offset" in patch(days_offset=61).json()["fields"]
    assert "template_code" in patch(template_code="does_not_exist").json()["fields"]
    assert (
        "template_code" in patch(template_code="custom_message").json()["fields"]
    )  # free text, not a template
    assert "send_after" in patch(send_after="25:00").json()["fields"]


def test_the_offset_of_immediate_events_stays_at_zero(api):
    rule = api.get(URL).json()[0]  # confirmation
    response = api.patch(f"{URL}{rule['id']}/", {"days_offset": 5}, format="json")
    assert response.status_code == 200 and response.json()["days_offset"] == 0


def test_another_hotels_rule_is_not_found(api):
    other = LifecycleRuleFactory(property=PropertyFactory())
    assert api.patch(f"{URL}{other.pk}/", {"enabled": False}, format="json").status_code == 404


def test_front_desk_reads_but_does_not_change_rules(api_for, prop, make_member):
    client = api_for(make_member("front_desk"), prop)
    rule = client.get(URL).json()[0]
    response = client.patch(f"{URL}{rule['id']}/", {"enabled": False}, format="json")
    assert response.status_code == 403 and response.json()["permission"] == "messaging.templates"


def test_rule_changes_are_audited(api, prop, owner):
    rule = api.get(URL).json()[3]  # post_stay
    api.patch(f"{URL}{rule['id']}/", {"enabled": False, "days_offset": 2}, format="json")
    event = AuditEvent.objects.get(action="messaging.lifecycle_rule_updated")
    assert (event.target_id, event.actor, event.property) == (rule["id"], owner, prop)
    assert event.changes == {"enabled": [True, False], "days_offset": [1, 2]}
