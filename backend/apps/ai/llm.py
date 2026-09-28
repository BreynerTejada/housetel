"""LLM contract (spec §4.2): `get_llm(property) -> LLMClient`.

The provider comes from IntegrationSetting(kind="llm") of the property (or the platform when `property` is
None): mode `real` → `config.provider` "gemini" (default) or "claude", with the platform keys of the
environment (`GEMINI_API_KEY` / `ANTHROPIC_API_KEY`) unless the setting stores its own `api_key` secret;
mode `simulated` (or a disabled integration) → the deterministic offline client.

Failures of the real provider (429, 5xx, timeouts, network) get one short retry when they failed fast (a
timeout is not retried: the person would wait twice); then the call is answered by the simulated client and
a `llm_degraded` alert is raised (at most one per property and day). After a failure the provider rests (2
minutes after a quota error, 30 s otherwise: calls go straight to the simulated client); the next successful
call clears the degradation and resolves the day's alert. Chats (copilot, chatbot, drafts) ask Gemini for
minimal thinking to answer fast. Every call is recorded in `AIUsage` (a failed attempt and its fallback are
two rows).

Safety net: while the test suite runs (`settings.TESTING`), real providers are never contacted unless the
test opts in with `settings.AI_LIVE_LLM_IN_TESTS = True` (the `live_llm` test and the adapter tests, which
inject fake SDK clients).
"""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.ai.clients.base import ProviderError, to_json
from apps.ai.simulated import SimulatedLLMClient
from apps.ai.types import LLMClient, LLMResult, ToolCall

logger = logging.getLogger("housetel.ai")

__all__ = ["SimulatedLLMClient", "get_llm", "llm_for", "assistant_message", "tool_message", "LLMService"]

PROVIDERS = ("gemini", "claude")
PROVIDER_LABELS = {"gemini": "Google Gemini", "claude": "Anthropic Claude", "simulated": "Simulado"}
RETRY_DELAY_SECONDS = 0.8
QUICK_FAILURE_SECONDS = 8
QUOTA_COOLDOWN_SECONDS = 120
ERROR_COOLDOWN_SECONDS = 30
STATUS_TTL_SECONDS = 60 * 60 * 24


def _property_today(property):
    if property is None:
        return timezone.localdate()
    from apps.core.dates import property_now

    return property_now(property).date()


def _status_key(property) -> str:
    return f"ai:llm:status:{property.pk if property is not None else 'platform'}"


def provider_status(property) -> dict:
    """Last degradation seen for the property: `{error, at, cooling_down_until}` or `{}`."""
    return cache.get(_status_key(property)) or {}


class LLMService:
    """The client `get_llm` returns: `generate()` with retry, fallback, alert and usage records."""

    def __init__(
        self,
        *,
        property,
        primary=None,
        fallback: SimulatedLLMClient,
        feature: str = "general",
        degraded_reason: str = "",
        cooldown_key: str = "",
    ):
        self.property = property
        self.primary = primary
        self.fallback = fallback
        self.feature = feature
        self.degraded_reason = degraded_reason
        self.cooldown_key = cooldown_key

    @property
    def simulated(self) -> bool:
        return self.primary is None

    @property
    def provider(self) -> str:
        return self.primary.provider if self.primary is not None else "simulated"

    @property
    def model(self) -> str:
        return self.primary.model if self.primary is not None else "simulated"

    def generate(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> LLMResult:
        kwargs = {
            "system": system,
            "tools": tools,
            "response_schema": response_schema,
            "temperature": temperature,
        }
        if self.degraded_reason:
            self._degrade(self.degraded_reason)
        if self.primary is not None and not self._cooling_down():
            for attempt in (1, 2):
                started = time.monotonic()
                try:
                    result = self.primary.generate(messages, **kwargs)
                except ProviderError as exc:
                    self._record(self.primary.provider, self.primary.model, started, error=str(exc))
                    # A short retry only after a quick failure (429, 503…): retrying a request that just
                    # timed out would double the wait of the person in front of the screen.
                    quick = time.monotonic() - started < QUICK_FAILURE_SECONDS
                    if exc.retryable and attempt == 1 and quick:
                        time.sleep(RETRY_DELAY_SECONDS)
                        continue
                    self._cool_down(QUOTA_COOLDOWN_SECONDS if exc.quota else ERROR_COOLDOWN_SECONDS)
                    self._degrade(str(exc))
                except Exception as exc:  # an SDK surprise must not take the feature down
                    logger.exception("LLM provider %s failed unexpectedly", self.primary.provider)
                    self._record(
                        self.primary.provider,
                        self.primary.model,
                        started,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    self._cool_down(ERROR_COOLDOWN_SECONDS)
                    self._degrade(f"{type(exc).__name__}: {exc}")
                else:
                    self._record(self.primary.provider, self.primary.model, started, usage=result.usage)
                    self._recovered()
                    return result
                break
        started = time.monotonic()
        result = self.fallback.generate(messages, **kwargs)
        self._record("simulated", "simulated", started)
        return result

    # ---- internals -------------------------------------------------------------------------------------

    def _record(self, provider: str, model: str, started: float, *, usage=None, error: str = "") -> None:
        from apps.ai.models import AIUsage

        usage = usage or {}
        try:
            AIUsage.objects.create(
                property=self.property,
                feature=self.feature[:40],
                provider=provider,
                model=(model or "")[:100],
                input_tokens=int(usage.get("input_tokens") or 0),
                output_tokens=int(usage.get("output_tokens") or 0),
                latency_ms=int((time.monotonic() - started) * 1000),
                success=not error,
                error=error[:500],
            )
        except Exception:  # usage is bookkeeping: never break the answer for it
            logger.exception("Could not record AI usage")

    def _recovered(self) -> None:
        """The provider answered: forget the last degradation and close today's `llm_degraded` alert (the
        settings page and the alert center stop saying the AI is simulated). Cheap when nothing failed."""
        status = provider_status(self.property)
        if not status.get("error"):
            return
        cache.set(
            _status_key(self.property),
            {"last_success_at": timezone.now().isoformat()},
            STATUS_TTL_SECONDS,
        )
        if self.property is None:
            return
        from apps.core.alerts import resolve_alert

        try:
            day = _property_today(self.property).isoformat()
            resolve_alert(self.property, f"ai:llm_degraded:{day}")
        except Exception:  # bookkeeping: never break the answer for it
            logger.exception("Could not resolve the llm_degraded alert")

    def _cooling_down(self) -> bool:
        return bool(self.cooldown_key and cache.get(self.cooldown_key))

    def _cool_down(self, seconds: int) -> None:
        if self.cooldown_key:
            cache.set(self.cooldown_key, True, seconds)
        status = provider_status(self.property)
        status["cooling_down_until"] = (timezone.now() + timedelta(seconds=seconds)).isoformat()
        cache.set(_status_key(self.property), status, STATUS_TTL_SECONDS)

    def _degrade(self, reason: str) -> None:
        from apps.core.alerts import raise_alert
        from apps.core.models import Alert

        status = provider_status(self.property)
        status.update({"error": reason[:500], "at": timezone.now().isoformat()})
        cache.set(_status_key(self.property), status, STATUS_TTL_SECONDS)
        day = _property_today(self.property).isoformat()
        dedupe_key = f"ai:llm_degraded:{day}"
        if Alert.objects.filter(property=self.property, dedupe_key=dedupe_key).exists():
            return  # one alert per day, even if someone resolved it
        label = PROVIDER_LABELS.get(self.provider, self.provider)
        raise_alert(
            property=self.property,
            kind="llm_degraded",
            severity="warning",
            title="La IA está respondiendo en modo simulado",
            message=(
                f"{label} no respondió: {reason[:300]}. Housetel sigue funcionando con el asistente simulado "
                "hasta que el proveedor vuelva a estar disponible."
            ),
            link="/app/settings/ai",
            dedupe_key=dedupe_key,
            data={"provider": self.provider, "provider_label": label, "error": reason[:500]},
            source="ai",
        )


INTERACTIVE_TIMEOUT_SECONDS = 30
# Chats answer a person who is waiting: the model thinks as little as possible (see GeminiClient._thinking).
INTERACTIVE_FEATURES = frozenset({"copilot", "chatbot", "draft_reply"})


def _real_client(
    provider: str,
    *,
    api_key: str,
    model: str,
    timeout: float = INTERACTIVE_TIMEOUT_SECONDS,
    thinking: str = "low",
):
    if provider == "claude":
        from apps.ai.clients.claude import ClaudeClient

        return ClaudeClient(api_key=api_key, model=model, timeout=timeout)
    from apps.ai.clients.gemini import GeminiClient

    return GeminiClient(api_key=api_key, model=model, timeout_ms=int(timeout * 1000), thinking=thinking)


def _live_calls_allowed() -> bool:
    return not getattr(settings, "TESTING", False) or getattr(settings, "AI_LIVE_LLM_IN_TESTS", False)


def provider_config(setting) -> tuple[str, str, str]:
    """(provider, model, api_key) of a real-mode llm setting (the key may be empty)."""
    from apps.core import integrations

    config = setting.config or {}
    provider = config.get("provider") if config.get("provider") in PROVIDERS else "gemini"
    platform_key = settings.GEMINI_API_KEY if provider == "gemini" else settings.ANTHROPIC_API_KEY
    platform_model = settings.GEMINI_MODEL if provider == "gemini" else settings.CLAUDE_MODEL
    api_key = integrations.get_secrets(setting).get("api_key") or platform_key or ""
    return provider, (config.get("model") or platform_model or ""), api_key


def get_llm(property=None) -> LLMClient:
    return _build(property)


def _build(property, *, timeout: float = INTERACTIVE_TIMEOUT_SECONDS, feature: str = "general") -> LLMService:
    from apps.core import integrations

    fallback = SimulatedLLMClient(today=_property_today(property))
    setting = integrations.get_setting(property, "llm")
    if setting.mode != "real" or not setting.enabled or not _live_calls_allowed():
        return LLMService(property=property, fallback=fallback, feature=feature)
    provider, model, api_key = provider_config(setting)
    if not api_key:
        return LLMService(
            property=property,
            fallback=fallback,
            feature=feature,
            degraded_reason=f"falta la clave de API de {PROVIDER_LABELS[provider]}",
        )
    fingerprint = hashlib.sha256(api_key.encode()).hexdigest()[:12]
    thinking = "minimal" if feature in INTERACTIVE_FEATURES else "low"
    return LLMService(
        property=property,
        primary=_real_client(provider, api_key=api_key, model=model, timeout=timeout, thinking=thinking),
        fallback=fallback,
        feature=feature,
        cooldown_key=f"ai:llm:cooldown:{provider}:{fingerprint}",
    )


def llm_for(property, feature: str, *, timeout: float = INTERACTIVE_TIMEOUT_SECONDS) -> LLMService:
    """`get_llm` tagged with the feature that uses it (copilot, chatbot, onboarding…) for the usage report;
    `timeout` (seconds per attempt) is longer for big generations such as the onboarding proposal."""
    return _build(property, timeout=timeout, feature=feature)


# ---- conversation helpers ------------------------------------------------------------------------------


def assistant_message(result: LLMResult) -> dict:
    """The assistant turn of `result` for the next call (keeps tool calls and their provider metadata)."""
    message: dict = {"role": "assistant", "content": result.text or ""}
    if result.tool_calls:
        message["tool_calls"] = [serialize_tool_call(call) for call in result.tool_calls]
    return message


def serialize_tool_call(call: ToolCall) -> dict:
    data = {"id": call.id, "name": call.name, "arguments": call.arguments}
    meta = getattr(call, "meta", None)
    if meta:
        data["meta"] = meta
    return data


def tool_message(call: ToolCall, data) -> dict:
    return {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": to_json(data)}
