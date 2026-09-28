"""Fixtures of the AI tests.

No test reaches a real LLM provider unless it is marked `live_llm`: the SDK client factories are replaced
by a guard that fails loudly, and tests that exercise the real adapters inject the fakes of `fakes.py`.
"""

import pytest

from apps.ai.tests.fakes import FakeClaude, FakeGemini


def _forbidden_factory(**kwargs):
    raise AssertionError("A test tried to build a real LLM SDK client (mark it live_llm or use a fake)")


@pytest.fixture(autouse=True)
def _no_real_llm(request, monkeypatch):
    monkeypatch.setattr("apps.ai.llm.RETRY_DELAY_SECONDS", 0)
    if request.node.get_closest_marker("live_llm"):
        return
    monkeypatch.setattr("apps.ai.clients.gemini.make_client", _forbidden_factory)
    monkeypatch.setattr("apps.ai.clients.claude.make_client", _forbidden_factory)


@pytest.fixture
def live_opt_in(settings):
    """Lets `get_llm` build real adapters inside the test run (with fake SDK clients injected)."""
    settings.AI_LIVE_LLM_IN_TESTS = True
    settings.GEMINI_API_KEY = "test-gemini-key"
    settings.GEMINI_MODEL = "gemini-3.5-flash"
    settings.ANTHROPIC_API_KEY = "test-claude-key"
    settings.CLAUDE_MODEL = "claude-test-model"
    return settings


@pytest.fixture
def fake_gemini(monkeypatch):
    fake = FakeGemini()
    monkeypatch.setattr("apps.ai.clients.gemini.make_client", fake.factory)
    return fake


@pytest.fixture
def fake_claude(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr("apps.ai.clients.claude.make_client", fake.factory)
    return fake


@pytest.fixture
def llm_mode(prop):
    """`llm_mode("real", provider="claude")` configures IntegrationSetting(kind="llm") of `prop`."""
    from apps.core import integrations

    def _set(mode, *, provider=None, enabled=True, target=None, **config):
        setting = integrations.get_setting(target or prop, "llm")
        setting.mode = mode
        setting.enabled = enabled
        setting.config = {**(setting.config or {}), **config, **({"provider": provider} if provider else {})}
        setting.save()
        return setting

    return _set
