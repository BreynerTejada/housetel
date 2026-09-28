"""`get_llm(property)`: provider selection (IntegrationSetting kind="llm"), request shape of the Gemini and
Claude adapters, retries, fallback to the simulated client, the `llm_degraded` alert and usage records."""

import base64
import os

import pytest
from django.utils import timezone

from apps.ai.llm import assistant_message, get_llm, tool_message
from apps.ai.models import AIUsage
from apps.ai.tests.fakes import claude_message, gemini_calls, gemini_error, gemini_text
from apps.ai.types import LLMResult, ToolCall
from apps.core.models import Alert

pytestmark = pytest.mark.django_db

ARRIVALS_TOOL = {
    "name": "list_arrivals",
    "description": "Llegadas de una fecha",
    "parameters": {"type": "object", "properties": {"date": {"type": "string"}}, "required": []},
}
USER = [{"role": "user", "content": "¿Cuántas llegadas hay hoy?"}]


def degraded_alerts(prop):
    return Alert.objects.filter(property=prop, kind="llm_degraded")


# ---- selection ----------------------------------------------------------------------------------------


def test_simulated_mode_answers_offline_and_records_the_usage(prop, llm_mode):
    llm_mode("simulated")

    result = get_llm(prop).generate([{"role": "user", "content": "Hola"}])

    assert isinstance(result, LLMResult)
    assert (result.simulated, result.provider) == (True, "simulated")
    assert result.text
    usage = AIUsage.objects.get(property=prop)
    assert (usage.provider, usage.success, usage.feature) == ("simulated", True, "general")


def test_a_disabled_integration_uses_the_simulated_client(prop, llm_mode, live_opt_in, fake_gemini):
    llm_mode("real", enabled=False)

    result = get_llm(prop).generate(USER)

    assert result.simulated
    assert fake_gemini.created == []


def test_the_test_run_never_reaches_a_real_provider_without_opting_in(prop, llm_mode, settings, fake_gemini):
    settings.GEMINI_API_KEY = "a-key"
    llm_mode("real")

    result = get_llm(prop).generate(USER)

    assert result.simulated
    assert fake_gemini.created == []


def test_without_a_property_the_platform_setting_decides(db, live_opt_in, fake_gemini):
    fake_gemini.respond(gemini_text("ok"))

    result = get_llm().generate(USER)  # the platform default is real when GEMINI_API_KEY exists

    assert (result.provider, result.simulated) == ("gemini", False)
    assert AIUsage.objects.get().property is None


def test_real_mode_without_any_api_key_degrades_to_simulated(prop, llm_mode, live_opt_in, fake_gemini):
    live_opt_in.GEMINI_API_KEY = ""
    llm_mode("real")

    result = get_llm(prop).generate(USER)

    assert result.simulated
    assert fake_gemini.created == []
    assert degraded_alerts(prop).count() == 1


def test_a_property_api_key_wins_over_the_platform_key(prop, llm_mode, live_opt_in, fake_gemini):
    from apps.core import integrations

    setting = llm_mode("real")
    integrations.set_secrets(setting, {"api_key": "hotel-own-key"})
    fake_gemini.respond(gemini_text("ok"))

    get_llm(prop).generate(USER)

    assert fake_gemini.created[0]["api_key"] == "hotel-own-key"


# ---- Gemini adapter -----------------------------------------------------------------------------------


def test_gemini_request_has_the_model_system_prompt_tools_and_temperature(
    prop, llm_mode, live_opt_in, fake_gemini
):
    llm_mode("real")
    fake_gemini.respond(gemini_text("Hoy hay 3 llegadas.", prompt_tokens=40, output_tokens=9))

    result = get_llm(prop).generate(USER, system="Eres el copiloto", tools=[ARRIVALS_TOOL], temperature=0.1)

    (call,) = fake_gemini.calls
    assert call["model"] == "gemini-3.5-flash"
    config = call["config"]
    assert config.system_instruction == "Eres el copiloto"
    assert config.temperature == 0.1
    assert config.automatic_function_calling.disable is True
    (declaration,) = config.tools[0].function_declarations
    assert (declaration.name, declaration.description) == ("list_arrivals", "Llegadas de una fecha")
    assert declaration.parameters_json_schema == ARRIVALS_TOOL["parameters"]
    assert config.response_mime_type is None
    ((content),) = call["contents"]
    assert (content.role, content.parts[0].text) == ("user", "¿Cuántas llegadas hay hoy?")
    assert (result.text, result.provider, result.model, result.simulated) == (
        "Hoy hay 3 llegadas.",
        "gemini",
        "gemini-3.5-flash",
        False,
    )
    assert result.usage == {"input_tokens": 40, "output_tokens": 9}
    usage = AIUsage.objects.get(property=prop)
    assert (usage.provider, usage.model, usage.input_tokens, usage.output_tokens, usage.success) == (
        "gemini",
        "gemini-3.5-flash",
        40,
        9,
        True,
    )


@pytest.mark.parametrize(
    ("model", "thinking"),
    [("gemini-3.5-flash", "LOW"), ("gemini-2.5-flash", None)],
)
def test_gemini_3_models_think_briefly_and_never_run_tools_on_their_own(
    prop, llm_mode, live_opt_in, fake_gemini, model, thinking
):
    llm_mode("real", model=model)
    fake_gemini.respond(gemini_text("ok"))

    get_llm(prop).generate(USER)

    config = fake_gemini.calls[0]["config"]
    level = config.thinking_config.thinking_level if config.thinking_config else None
    assert (level.value if level else None) == thinking
    assert config.automatic_function_calling.disable is True


def test_gemini_function_calls_become_tool_calls_and_go_back_with_their_signature(
    prop, llm_mode, live_opt_in, fake_gemini
):
    llm_mode("real")
    fake_gemini.respond(
        gemini_calls(("list_arrivals", {"date": "2026-10-01"}), ("get_today_summary", {})),
        gemini_text("Hay 2 llegadas."),
    )
    llm = get_llm(prop)

    first = llm.generate(USER, tools=[ARRIVALS_TOOL])

    assert [(call.name, call.arguments) for call in first.tool_calls] == [
        ("list_arrivals", {"date": "2026-10-01"}),
        ("get_today_summary", {}),
    ]
    assert all(isinstance(call, ToolCall) and call.id for call in first.tool_calls)
    arrivals, summary = first.tool_calls
    history = [
        *USER,
        assistant_message(first),
        tool_message(arrivals, {"count": 2}),
        tool_message(summary, {"occupancy": 70}),
    ]

    second = llm.generate(history, tools=[ARRIVALS_TOOL])

    assert second.text == "Hay 2 llegadas."
    user, model, tool = fake_gemini.calls[1]["contents"]
    assert (user.role, model.role, tool.role) == ("user", "model", "tool")
    assert [part.function_call.name for part in model.parts] == ["list_arrivals", "get_today_summary"]
    # Only the first call of a parallel turn carries Gemini's signature; the rest go back as received.
    assert [part.thought_signature for part in model.parts] == [b"sig-1", None]
    assert [(part.function_response.name, part.function_response.response) for part in tool.parts] == [
        ("list_arrivals", {"result": {"count": 2}}),
        ("get_today_summary", {"result": {"occupancy": 70}}),
    ]


def test_a_function_call_without_its_signature_is_sent_with_the_validator_bypass(
    prop, llm_mode, live_opt_in, fake_gemini
):
    """Tool calls that did not come from Gemini (e.g. the simulated fallback) have no thought signature."""
    llm_mode("real")
    fake_gemini.respond(gemini_text("Listo"))
    call = ToolCall(name="list_arrivals", arguments={}, id="call-x")
    history = [*USER, assistant_message(LLMResult(tool_calls=[call])), tool_message(call, [])]

    get_llm(prop).generate(history, tools=[ARRIVALS_TOOL])

    model = fake_gemini.calls[0]["contents"][1]
    # The SDK sends bytes as URL-safe base64: this is the documented "skip validation" signature.
    assert base64.urlsafe_b64encode(model.parts[0].thought_signature) == b"skip_thought_signature_validator"


def test_structured_output_asks_gemini_for_json_and_parses_it(prop, llm_mode, live_opt_in, fake_gemini):
    llm_mode("real")
    schema = {"type": "object", "properties": {"rooms": {"type": "integer"}}, "required": ["rooms"]}
    fake_gemini.respond(gemini_text('{"rooms": 12}'))

    result = get_llm(prop).generate(USER, response_schema=schema)

    config = fake_gemini.calls[0]["config"]
    assert (config.response_mime_type, config.response_json_schema) == ("application/json", schema)
    assert result.data == {"rooms": 12}


# ---- retries and fallback -----------------------------------------------------------------------------


def test_a_quota_error_is_retried_once_then_falls_back_with_an_alert(
    prop, llm_mode, live_opt_in, fake_gemini
):
    llm_mode("real")
    fake_gemini.respond(gemini_error(429, "RESOURCE_EXHAUSTED"), gemini_error(429, "RESOURCE_EXHAUSTED"))

    result = get_llm(prop).generate(USER, tools=[ARRIVALS_TOOL])

    assert len(fake_gemini.calls) == 2
    assert (result.simulated, result.provider) == (True, "simulated")
    alert = degraded_alerts(prop).get()
    assert (alert.severity, alert.link) == ("warning", "/app/settings/ai")
    assert alert.dedupe_key == f"ai:llm_degraded:{timezone.localdate().isoformat()}"
    attempts = AIUsage.objects.filter(property=prop, provider="gemini")
    assert [(row.success, "429" in row.error) for row in attempts] == [(False, True), (False, True)]
    assert AIUsage.objects.filter(property=prop, provider="simulated", success=True).count() == 1


def test_after_a_quota_error_the_provider_rests_and_the_alert_is_not_repeated(
    prop, llm_mode, live_opt_in, fake_gemini
):
    llm_mode("real")
    fake_gemini.respond(gemini_error(429, "RESOURCE_EXHAUSTED"), gemini_error(429, "RESOURCE_EXHAUSTED"))
    get_llm(prop).generate(USER)
    degraded_alerts(prop).update(resolved_at=timezone.now())  # someone resolves it the same day

    result = get_llm(prop).generate(USER)

    assert result.simulated
    assert len(fake_gemini.calls) == 2  # cooling down: no new request to Gemini
    assert degraded_alerts(prop).count() == 1  # one alert per day


def test_a_server_error_is_retried_and_the_retry_can_answer(prop, llm_mode, live_opt_in, fake_gemini):
    llm_mode("real")
    fake_gemini.respond(gemini_error(503, "UNAVAILABLE"), gemini_text("Todo bien"))

    result = get_llm(prop).generate(USER)

    assert (result.text, result.simulated) == ("Todo bien", False)
    assert not degraded_alerts(prop).exists()


def test_a_timeout_is_retried(prop, llm_mode, live_opt_in, fake_gemini):
    import httpx

    llm_mode("real")
    fake_gemini.respond(httpx.ReadTimeout("slow"), gemini_text("Por fin"))

    assert get_llm(prop).generate(USER).text == "Por fin"


def test_an_invalid_request_is_not_retried_but_still_falls_back(prop, llm_mode, live_opt_in, fake_gemini):
    llm_mode("real")
    fake_gemini.respond(gemini_error(400, "INVALID_ARGUMENT", "bad schema"))

    result = get_llm(prop).generate(USER)

    assert len(fake_gemini.calls) == 1
    assert result.simulated
    assert "400" in degraded_alerts(prop).get().message


# ---- Claude adapter -----------------------------------------------------------------------------------


def test_claude_is_used_when_configured_and_its_tool_use_becomes_tool_calls(
    prop, llm_mode, live_opt_in, fake_claude
):
    llm_mode("real", provider="claude")
    fake_claude.respond(
        claude_message(
            {"type": "text", "text": "Reviso las llegadas."},
            {"type": "tool_use", "id": "toolu_1", "name": "list_arrivals", "input": {"date": "2026-10-01"}},
        ),
        claude_message({"type": "text", "text": "Hay 2 llegadas."}),
    )
    llm = get_llm(prop)

    first = llm.generate(USER, system="Eres el copiloto", tools=[ARRIVALS_TOOL])
    (call,) = first.tool_calls
    second = llm.generate(
        [*USER, assistant_message(first), tool_message(call, {"count": 2})], tools=[ARRIVALS_TOOL]
    )

    request = fake_claude.calls[0]
    assert (request["model"], request["system"]) == ("claude-test-model", "Eres el copiloto")
    assert request["tools"] == [
        {
            "name": "list_arrivals",
            "description": "Llegadas de una fecha",
            "input_schema": ARRIVALS_TOOL["parameters"],
        }
    ]
    assert request["messages"] == [{"role": "user", "content": "¿Cuántas llegadas hay hoy?"}]
    assert (first.provider, first.text, call.id, call.arguments) == (
        "claude",
        "Reviso las llegadas.",
        "toolu_1",
        {"date": "2026-10-01"},
    )
    assert fake_claude.calls[1]["messages"][1:] == [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Reviso las llegadas."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "list_arrivals",
                    "input": {"date": "2026-10-01"},
                },
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"count": 2}'}],
        },
    ]
    assert second.text == "Hay 2 llegadas."
    assert (
        AIUsage.objects.filter(property=prop, provider="claude", input_tokens=20, output_tokens=7).count()
        == 2
    )


def test_claude_structured_output_uses_a_json_schema_format(prop, llm_mode, live_opt_in, fake_claude):
    llm_mode("real", provider="claude")
    schema = {"type": "object", "properties": {"rooms": {"type": "integer"}}}
    fake_claude.respond(claude_message({"type": "text", "text": '{"rooms": 4}'}))

    result = get_llm(prop).generate(USER, response_schema=schema)

    assert fake_claude.calls[0]["output_config"] == {"format": {"type": "json_schema", "schema": schema}}
    assert result.data == {"rooms": 4}


def test_a_claude_rate_limit_falls_back_to_simulated(prop, llm_mode, live_opt_in, fake_claude):
    import anthropic
    import httpx

    llm_mode("real", provider="claude")
    response = httpx.Response(429, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    error = anthropic.RateLimitError("rate limited", response=response, body=None)
    fake_claude.respond(error, error)

    result = get_llm(prop).generate(USER)

    assert result.simulated
    assert len(fake_claude.calls) == 2
    assert degraded_alerts(prop).count() == 1


# ---- live ---------------------------------------------------------------------------------------------


@pytest.mark.live_llm
@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="GEMINI_API_KEY is not set")
def test_live_gemini_answers_a_short_prompt(prop, llm_mode, settings):
    settings.AI_LIVE_LLM_IN_TESTS = True
    settings.GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
    llm_mode("real")

    result = get_llm(prop).generate(
        [{"role": "user", "content": "Responde únicamente con la palabra: listo"}], temperature=0
    )

    assert (result.provider, result.simulated) == ("gemini", False), result.text
    assert "listo" in result.text.lower()


def test_interactive_calls_wait_less_than_big_generations(prop, llm_mode, live_opt_in, fake_gemini):
    from apps.ai.llm import llm_for

    llm_mode("real")
    fake_gemini.respond(gemini_text("a"), gemini_text("b"))

    get_llm(prop).generate(USER)
    onboarding = llm_for(prop, "onboarding", timeout=60)
    onboarding.generate(USER)

    assert [created["timeout_ms"] for created in fake_gemini.created] == [20_000, 60_000]
    assert AIUsage.objects.filter(property=prop, feature="onboarding").count() == 1
