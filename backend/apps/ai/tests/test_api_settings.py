"""AI settings API (permission ai.settings): provider and features, FAQ, usage and chatbot conversations; plus
the copilot status the panel reads (ai.copilot)."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.ai.models import AISettings, AIUsage, ChatbotConversation, PropertyFAQ
from apps.core.models import Alert, AuditEvent

pytestmark = pytest.mark.django_db

BASE = "/api/v1/ai"


def test_settings_show_the_features_and_the_provider(prop, api, llm_mode, settings):
    settings.GEMINI_API_KEY = "platform-key"
    llm_mode("real")

    body = api.get(f"{BASE}/settings/").json()

    assert (body["copilot_enabled"], body["chatbot_enabled"], body["draft_replies_enabled"]) == (
        True,
        True,
        True,
    )
    provider = body["provider"]
    assert (provider["mode"], provider["provider"], provider["effective"]) == ("real", "gemini", "real")
    assert provider["model"] == settings.GEMINI_MODEL
    assert (provider["platform_key_configured"], provider["own_key_configured"]) == (True, False)
    assert "api_key" not in str(body) and "platform-key" not in str(body)


def test_without_any_key_the_provider_is_effectively_simulated(prop, api, llm_mode, settings):
    settings.GEMINI_API_KEY = ""
    llm_mode("real")

    provider = api.get(f"{BASE}/settings/").json()["provider"]

    assert (provider["mode"], provider["effective"]) == ("real", "simulated")


def test_the_provider_and_the_features_can_be_changed(prop, api, llm_mode):
    from apps.core import integrations

    llm_mode("simulated")

    response = api.patch(
        f"{BASE}/settings/",
        {
            "provider": "claude",
            "mode": "real",
            "chatbot_enabled": False,
            "chatbot_greeting": {"es": "¡Bienvenido a casa!", "en": "Welcome home!"},
        },
        format="json",
    )

    assert response.status_code == 200, response.json()
    setting = integrations.get_setting(prop, "llm")
    assert (setting.mode, setting.config["provider"]) == ("real", "claude")
    row = AISettings.objects.get(property=prop)
    assert (row.chatbot_enabled, row.chatbot_greeting["en"]) == (False, "Welcome home!")
    assert response.json()["provider"]["provider"] == "claude"
    assert AuditEvent.objects.filter(action="ai.settings_updated", property=prop).exists()


def test_an_unknown_provider_is_rejected(prop, api):
    response = api.patch(f"{BASE}/settings/", {"provider": "gpt"}, format="json")

    assert response.status_code == 400 and "provider" in response.json()["fields"]


def test_the_settings_need_their_permission(prop, make_member, api_for):
    front = api_for(make_member("front_desk"), prop)

    assert front.get(f"{BASE}/settings/").status_code == 403
    assert front.get(f"{BASE}/faqs/").status_code == 403
    assert front.get(f"{BASE}/usage/").status_code == 403


# ---- FAQ ---------------------------------------------------------------------------------------------------


def test_faqs_are_managed_per_hotel_and_language(prop, api, organization):
    from apps.core.tests.factories import PropertyFactory

    other = PropertyFactory(organization=organization)
    foreign = PropertyFAQ.objects.create(property=other, question="¿Otra?", answer="Otra", language="es")

    created = api.post(
        f"{BASE}/faqs/",
        {"question": "¿Tienen parqueadero?", "answer": "Sí, cubierto.", "language": "es", "sort": 1},
        format="json",
    )
    api.post(f"{BASE}/faqs/", {"question": "Parking?", "answer": "Yes.", "language": "en"}, format="json")

    assert created.status_code == 201, created.json()
    assert [item["question"] for item in api.get(f"{BASE}/faqs/", {"language": "es"}).json()["results"]] == [
        "¿Tienen parqueadero?"
    ]
    faq_id = created.json()["id"]
    assert api.patch(f"{BASE}/faqs/{faq_id}/", {"answer": "Sí, gratis."}, format="json").json()["answer"] == (
        "Sí, gratis."
    )
    assert api.get(f"{BASE}/faqs/{foreign.pk}/").status_code == 404
    assert api.delete(f"{BASE}/faqs/{faq_id}/").status_code == 204
    assert (
        api.post(
            f"{BASE}/faqs/", {"question": "x", "answer": "y", "language": "fr"}, format="json"
        ).status_code
        == 400
    )


# ---- usage -------------------------------------------------------------------------------------------------


def test_usage_sums_the_calls_of_the_hotel(prop, api, organization):
    from apps.core.tests.factories import PropertyFactory

    AIUsage.objects.create(
        property=prop,
        feature="copilot",
        provider="gemini",
        model="gemini-3.5-flash",
        input_tokens=100,
        output_tokens=20,
        latency_ms=900,
    )
    AIUsage.objects.create(
        property=prop, feature="copilot", provider="gemini", success=False, error="Gemini 429"
    )
    AIUsage.objects.create(property=prop, feature="chatbot", provider="simulated", latency_ms=2)
    old = AIUsage.objects.create(property=prop, feature="chatbot", provider="simulated")
    AIUsage.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=40))
    AIUsage.objects.create(
        property=PropertyFactory(organization=organization), feature="copilot", provider="gemini"
    )

    body = api.get(f"{BASE}/usage/", {"days": 30}).json()

    assert body["totals"] == {
        **body["totals"],
        "calls": 3,
        "errors": 1,
        "simulated": 1,
        "input_tokens": 100,
        "output_tokens": 20,
    }
    by_feature = {item["feature"]: item for item in body["by_feature"]}
    assert (by_feature["copilot"]["calls"], by_feature["copilot"]["errors"]) == (2, 1)
    assert [item["error"] for item in body["recent_errors"]] == ["Gemini 429"]
    assert sum(day["calls"] for day in body["by_day"]) == 3


# ---- chatbot conversations ---------------------------------------------------------------------------------


def test_chatbot_conversations_can_be_read_and_the_handoff_resolved(prop, api):
    from apps.core.alerts import raise_alert

    handed = ChatbotConversation.objects.create(
        property=prop,
        session_id="s" * 20,
        handoff_requested=True,
        handoff_reason="requested",
        handoff_at=timezone.now(),
        contact={"name": "Marta", "email": "marta@example.com"},
        messages=[{"role": "user", "content": "Quiero hablar con alguien", "at": timezone.now().isoformat()}],
        last_message_at=timezone.now(),
    )
    ChatbotConversation.objects.create(
        property=prop, session_id="t" * 20, messages=[], last_message_at=timezone.now()
    )
    raise_alert(
        property=prop,
        kind="chatbot_handoff",
        severity="warning",
        title="x",
        message="y",
        dedupe_key=f"ai:chatbot_handoff:{handed.pk}",
    )

    listed = api.get(f"{BASE}/chatbot-conversations/", {"handoff": "1"}).json()
    detail = api.get(f"{BASE}/chatbot-conversations/{handed.pk}/").json()
    resolved = api.post(f"{BASE}/chatbot-conversations/{handed.pk}/resolve/", {}, format="json")

    assert [item["id"] for item in listed["results"]] == [str(handed.pk)]
    assert listed["results"][0]["last_message"] == "Quiero hablar con alguien"
    assert detail["messages"][0]["content"] == "Quiero hablar con alguien"
    assert resolved.status_code == 200 and resolved.json()["handoff_resolved_at"]
    assert Alert.objects.get(dedupe_key=f"ai:chatbot_handoff:{handed.pk}").resolved_at is not None


# ---- copilot status ----------------------------------------------------------------------------------------


def test_the_copilot_panel_knows_whether_it_is_simulated_and_what_to_suggest(
    prop, make_member, api_for, llm_mode
):
    llm_mode("simulated")
    front = api_for(make_member("front_desk"), prop)
    housekeeping = api_for(make_member("housekeeping"), prop)

    body = front.get(f"{BASE}/copilot/status/").json()

    assert (body["enabled"], body["effective"]) == (True, "simulated")
    assert body["suggestions"] and all(isinstance(item, str) for item in body["suggestions"])
    assert housekeeping.get(f"{BASE}/copilot/status/").status_code == 403
