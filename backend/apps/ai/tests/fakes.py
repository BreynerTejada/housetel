"""Test doubles for the LLM providers. Responses are built with the real SDK types (google-genai and
anthropic), so the adapters parse exactly the structures the providers return."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from google.genai import errors as genai_errors
from google.genai import types as genai_types

from apps.ai.types import LLMResult, ToolCall

# ---- Gemini ---------------------------------------------------------------------------------------------


def gemini_usage(prompt_tokens: int = 12, output_tokens: int = 5):
    return genai_types.GenerateContentResponseUsageMetadata(
        prompt_token_count=prompt_tokens,
        candidates_token_count=output_tokens,
        total_token_count=prompt_tokens + output_tokens,
    )


def gemini_text(text: str, *, prompt_tokens: int = 12, output_tokens: int = 5):
    return genai_types.GenerateContentResponse(
        candidates=[
            genai_types.Candidate(
                content=genai_types.Content(role="model", parts=[genai_types.Part(text=text)]),
                finish_reason=genai_types.FinishReason.STOP,
            )
        ],
        usage_metadata=gemini_usage(prompt_tokens, output_tokens),
        model_version="gemini-test",
    )


def gemini_calls(*calls: tuple[str, dict], signature: bytes | None = b"sig-1", text: str | None = None):
    """A model turn with function calls; only the first call carries the thought signature (like Gemini 3)."""
    parts = []
    if text:
        parts.append(genai_types.Part(text=text))
    for index, (name, args) in enumerate(calls):
        parts.append(
            genai_types.Part(
                function_call=genai_types.FunctionCall(name=name, args=args),
                thought_signature=signature if index == 0 else None,
            )
        )
    return genai_types.GenerateContentResponse(
        candidates=[
            genai_types.Candidate(
                content=genai_types.Content(role="model", parts=parts),
                finish_reason=genai_types.FinishReason.STOP,
            )
        ],
        usage_metadata=gemini_usage(),
        model_version="gemini-test",
    )


def gemini_error(code: int, status: str = "", message: str = "error"):
    body = {"error": {"code": code, "message": message, "status": status}}
    cls = genai_errors.ServerError if code >= 500 else genai_errors.ClientError
    return cls(code, body)


class FakeGeminiModels:
    def __init__(self):
        self.calls: list[dict] = []
        self.script: list[Any] = []

    def generate_content(self, *, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if not self.script:
            raise AssertionError("The fake Gemini client got an unexpected call")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    def get(self, *, model):
        self.calls.append({"get": model})
        if self.script and isinstance(self.script[0], BaseException):
            raise self.script.pop(0)
        return genai_types.Model(name=f"models/{model}")


class FakeGemini:
    """Stands in for `genai.Client`: `fake.respond(...)` queues responses (or exceptions)."""

    def __init__(self):
        self.models = FakeGeminiModels()
        self.created: list[dict] = []

    def respond(self, *items):
        self.models.script.extend(items)
        return self

    @property
    def calls(self) -> list[dict]:
        return [call for call in self.models.calls if "contents" in call]

    def factory(self, *, api_key, timeout_ms):
        self.created.append({"api_key": api_key, "timeout_ms": timeout_ms})
        return self


# ---- Claude ---------------------------------------------------------------------------------------------


def claude_message(*blocks: dict, input_tokens: int = 20, output_tokens: int = 7):
    from anthropic.types import Message

    stop = "tool_use" if any(block["type"] == "tool_use" for block in blocks) else "end_turn"
    return Message.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "claude-test",
            "content": list(blocks),
            "stop_reason": stop,
            "stop_sequence": None,
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
        }
    )


class FakeClaudeMessages:
    def __init__(self):
        self.calls: list[dict] = []
        self.script: list[Any] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("The fake Claude client got an unexpected call")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class FakeClaude:
    def __init__(self):
        self.messages = FakeClaudeMessages()
        self.created: list[dict] = []

    def respond(self, *items):
        self.messages.script.extend(items)
        return self

    @property
    def calls(self) -> list[dict]:
        return self.messages.calls

    def factory(self, *, api_key, timeout):
        self.created.append({"api_key": api_key, "timeout": timeout})
        return self


# ---- Scripted client (agent loops) ----------------------------------------------------------------------


@dataclass
class ScriptedLLM:
    """A fake `LLMClient` for the copilot/chatbot loops: returns queued `LLMResult`s and records what it was
    asked (messages, system prompt and the names of the tools it was offered)."""

    results: list[LLMResult] = field(default_factory=list)
    calls: list[dict] = field(default_factory=list)
    feature: str = "general"

    def generate(self, messages, *, system=None, tools=None, response_schema=None, temperature=0.2):
        self.calls.append(
            {
                "messages": [dict(message) for message in messages],
                "system": system,
                "tools": [tool["name"] for tool in tools or []],
                "response_schema": response_schema,
            }
        )
        if not self.results:
            raise AssertionError("The scripted LLM got an unexpected call")
        return self.results.pop(0)


def real_text(text: str) -> LLMResult:
    return LLMResult(text=text, provider="gemini", model="gemini-test", simulated=False)


def real_calls(*calls: tuple[str, dict]) -> LLMResult:
    return LLMResult(
        tool_calls=[
            ToolCall(name=name, arguments=args, id=f"call-{index}")
            for index, (name, args) in enumerate(calls, start=1)
        ],
        provider="gemini",
        model="gemini-test",
        simulated=False,
    )


def real_data(data) -> LLMResult:
    return LLMResult(data=data, text="", provider="gemini", model="gemini-test", simulated=False)
