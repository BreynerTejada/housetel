"""Gemini adapter (google-genai SDK, verified against v2.25).

- `client.models.generate_content(model, contents, config=GenerateContentConfig(...))`.
- Tools: one `types.Tool(function_declarations=[FunctionDeclaration(name, description,
  parameters_json_schema)])`; automatic function calling is disabled, so function calls come back to us.
- Structured output: `response_mime_type="application/json"` + `response_json_schema`.
- Gemini 3 attaches a `thought_signature` to function-call parts that must be sent back with the call in the
  same turn; it travels in `ProviderToolCall.meta`. Calls without one (from another provider or the simulated
  fallback) use the documented "skip validation" signature.
"""

from __future__ import annotations

import base64
import logging

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from apps.ai.clients.base import (
    RETRYABLE_STATUSES,
    ProviderError,
    ProviderToolCall,
    new_call_id,
    parse_json_text,
    parse_tool_content,
)
from apps.ai.types import LLMResult

try:  # the SDK also accepts httpx2 transports
    import httpx2

    NETWORK_ERRORS: tuple = (httpx.RequestError, httpx2.RequestError)
except ImportError:  # pragma: no cover
    NETWORK_ERRORS = (httpx.RequestError,)

logger = logging.getLogger("housetel.ai")

TIMEOUT_MS = 30_000
# Sent as URL-safe base64 by the SDK: "skip_thought_signature_validator".
SKIP_SIGNATURE = base64.urlsafe_b64decode("skip_thought_signature_validator")


def make_client(*, api_key: str, timeout_ms: int):
    """The SDK client (retries are ours: one short retry, then the simulated fallback)."""
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=timeout_ms, retry_options=types.HttpRetryOptions(attempts=1)),
    )


def _stored_signature(call: dict) -> bytes | None:
    raw = (call.get("meta") or {}).get("thought_signature")
    if not raw:
        return None
    try:
        return base64.b64decode(raw)
    except ValueError:
        return None


def _signatures(calls: list[dict]) -> list[bytes | None]:
    """Gemini signs the first function call of a turn. A turn that came from Gemini goes back exactly as
    received; one that did not (another provider, the simulated fallback) gets the documented bypass
    signature on its first call."""
    stored = [_stored_signature(call) for call in calls]
    if any(stored):
        return stored
    return [SKIP_SIGNATURE if index == 0 else None for index in range(len(calls))]


def to_contents(messages: list[dict]) -> list[types.Content]:
    """Our chat messages → Gemini contents (consecutive tool results share one `tool` turn)."""
    contents: list[types.Content] = []
    for message in messages:
        role = message.get("role")
        text = message.get("content") or ""
        if role == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))
        elif role == "assistant":
            parts = [types.Part.from_text(text=text)] if text else []
            calls = message.get("tool_calls") or []
            for call, signature in zip(calls, _signatures(calls), strict=True):
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(name=call["name"], args=call.get("arguments") or {}),
                        thought_signature=signature,
                    )
                )
            if parts:
                contents.append(types.Content(role="model", parts=parts))
        elif role == "tool":
            part = types.Part.from_function_response(
                name=message.get("name") or "tool", response={"result": parse_tool_content(text)}
            )
            if contents and contents[-1].role == "tool":
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role="tool", parts=[part]))
    return contents


def to_tool(tools: list[dict]) -> types.Tool:
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool.get("description", ""),
                parameters_json_schema=tool.get("parameters") or {"type": "object", "properties": {}},
            )
            for tool in tools
        ]
    )


class GeminiClient:
    provider = "gemini"

    def __init__(self, *, api_key: str, model: str, timeout_ms: int = TIMEOUT_MS, thinking: str = "low"):
        self.model = model
        self.thinking = thinking  # "minimal" (chat: fastest answers) | "low"
        self._api_key = api_key
        self._timeout_ms = timeout_ms
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = make_client(api_key=self._api_key, timeout_ms=self._timeout_ms)
        return self._client

    def generate(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> LLMResult:
        config = types.GenerateContentConfig(
            system_instruction=system or None,
            temperature=temperature,
            tools=[to_tool(tools)] if tools else None,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            response_mime_type="application/json" if response_schema else None,
            response_json_schema=response_schema or None,
            thinking_config=self._thinking(),
        )
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=to_contents(messages), config=config
            )
        except genai_errors.APIError as exc:
            status = exc.code if isinstance(exc.code, int) else None
            raise ProviderError(
                f"Gemini {exc.code} {exc.status or ''}: {exc.message or exc}".strip(),
                status=status,
                retryable=status in RETRYABLE_STATUSES,
            ) from exc
        except NETWORK_ERRORS as exc:
            raise ProviderError(f"Gemini sin respuesta: {type(exc).__name__}: {exc}", retryable=True) from exc
        return self._result(response, structured=bool(response_schema))

    def _thinking(self):
        """Gemini 3 models accept a thinking level: `minimal` for the chats (copilot, chatbot, drafts: most of
        their latency is thinking), `low` for bigger generations (onboarding, daily brief); both spend less
        quota than the default. Older models (thinking budget) keep their default."""
        if self.model.startswith("gemini-3"):
            level = types.ThinkingLevel.MINIMAL if self.thinking == "minimal" else types.ThinkingLevel.LOW
            return types.ThinkingConfig(thinking_level=level)
        return None

    def _result(self, response, *, structured: bool) -> LLMResult:
        parts = []
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            parts = response.candidates[0].content.parts
        texts, calls = [], []
        for part in parts:
            if part.function_call is not None:
                signature = part.thought_signature
                calls.append(
                    ProviderToolCall(
                        name=part.function_call.name or "",
                        arguments=dict(part.function_call.args or {}),
                        id=part.function_call.id or new_call_id(),
                        meta={"thought_signature": base64.b64encode(signature).decode()} if signature else {},
                    )
                )
            elif part.text and not part.thought:
                texts.append(part.text)
        text = "".join(texts).strip()
        usage = response.usage_metadata
        return LLMResult(
            text=text,
            tool_calls=calls,
            data=parse_json_text(text) if structured else None,
            provider=self.provider,
            model=self.model,
            simulated=False,
            usage={
                "input_tokens": (usage.prompt_token_count or 0) if usage else 0,
                "output_tokens": ((usage.candidates_token_count or 0) + (usage.thoughts_token_count or 0))
                if usage
                else 0,
            },
        )

    def test_connection(self) -> tuple[bool, str]:
        """Cheap check (model metadata, no generation quota)."""
        try:
            self.client.models.get(model=self.model)
        except genai_errors.APIError as exc:
            return False, f"Gemini {exc.code}: {exc.message or exc}"
        except NETWORK_ERRORS as exc:
            return False, f"Gemini sin respuesta: {exc}"
        return True, f"Gemini listo ({self.model})"
