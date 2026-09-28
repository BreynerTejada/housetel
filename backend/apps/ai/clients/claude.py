"""Claude adapter (anthropic SDK, verified against v1.8).

- `client.messages.create(model, max_tokens, system, messages, tools=[{name, description, input_schema}])`;
  this SDK version has no `temperature` parameter.
- Tool calls are `tool_use` blocks; their results go back as `tool_result` blocks in a user turn.
- Structured output: `output_config={"format": {"type": "json_schema", "schema": ...}}`.
"""

from __future__ import annotations

import anthropic

from apps.ai.clients.base import (
    RETRYABLE_STATUSES,
    ProviderError,
    new_call_id,
    parse_json_text,
    to_json,
)
from apps.ai.types import LLMResult, ToolCall

TIMEOUT_SECONDS = 30.0
MAX_TOKENS = 2048


def make_client(*, api_key: str, timeout: float):
    return anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)


def to_messages(messages: list[dict]) -> list[dict]:
    """Our chat messages → Anthropic messages (consecutive tool results share one user turn)."""
    converted: list[dict] = []
    for message in messages:
        role = message.get("role")
        text = message.get("content") or ""
        if role == "user":
            converted.append({"role": "user", "content": text})
        elif role == "assistant":
            calls = message.get("tool_calls") or []
            if not calls:
                converted.append({"role": "assistant", "content": text})
                continue
            blocks = [{"type": "text", "text": text}] if text else []
            blocks += [
                {
                    "type": "tool_use",
                    "id": call.get("id") or new_call_id(),
                    "name": call["name"],
                    "input": call.get("arguments") or {},
                }
                for call in calls
            ]
            converted.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": message.get("tool_call_id") or "",
                "content": text if isinstance(text, str) else to_json(text),
            }
            previous = converted[-1] if converted else None
            if previous and previous["role"] == "user" and isinstance(previous["content"], list):
                previous["content"].append(block)
            else:
                converted.append({"role": "user", "content": [block]})
    return converted


class ClaudeClient:
    provider = "claude"

    def __init__(self, *, api_key: str, model: str, timeout: float = TIMEOUT_SECONDS):
        self.model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = make_client(api_key=self._api_key, timeout=self._timeout)
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
        kwargs = {"model": self.model, "max_tokens": MAX_TOKENS, "messages": to_messages(messages)}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "input_schema": tool.get("parameters") or {"type": "object", "properties": {}},
                }
                for tool in tools
            ]
        if response_schema:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": response_schema}}
        try:
            response = self.client.messages.create(**kwargs)
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                f"Claude {exc.status_code}: {exc.message}",
                status=exc.status_code,
                retryable=exc.status_code in RETRYABLE_STATUSES,
            ) from exc
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            raise ProviderError(f"Claude sin respuesta: {exc}", retryable=True) from exc
        texts, calls = [], []
        for block in response.content:
            if block.type == "text":
                texts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(name=block.name, arguments=dict(block.input or {}), id=block.id))
        text = "".join(texts).strip()
        return LLMResult(
            text=text,
            tool_calls=calls,
            data=parse_json_text(text) if response_schema else None,
            provider=self.provider,
            model=self.model,
            simulated=False,
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )

    def test_connection(self) -> tuple[bool, str]:
        try:
            self.client.models.retrieve(self.model)
        except anthropic.APIStatusError as exc:
            return False, f"Claude {exc.status_code}: {exc.message}"
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as exc:
            return False, f"Claude sin respuesta: {exc}"
        return True, f"Claude listo ({self.model})"
