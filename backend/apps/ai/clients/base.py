"""Pieces shared by the provider adapters."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field

from django.core.serializers.json import DjangoJSONEncoder

from apps.ai.types import ToolCall


@dataclass
class ProviderToolCall(ToolCall):
    """A `ToolCall` with provider metadata that must travel back with it (e.g. Gemini's thought signature).
    `apps.ai.llm.assistant_message` keeps `meta` in the conversation history."""

    meta: dict = field(default_factory=dict)


class ProviderError(Exception):
    """A failed provider call. `retryable`: worth one short retry (429, 5xx, timeouts, network)."""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable

    @property
    def quota(self) -> bool:
        return self.status == 429


RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


def new_call_id() -> str:
    return f"call_{secrets.token_hex(6)}"


def to_json(value) -> str:
    return json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False)


def parse_tool_content(content):
    """A `tool` message carries JSON text; give the provider the decoded value (or the raw text)."""
    if isinstance(content, str):
        try:
            return json.loads(content)
        except ValueError:
            return content
    return content


def parse_json_text(text: str):
    """Structured output: the JSON object in `text` (tolerates a ```json fence), or None."""
    if not text:
        return None
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`")
        body = body[4:] if body.lower().startswith("json") else body
    try:
        return json.loads(body)
    except ValueError:
        start, end = body.find("{"), body.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(body[start : end + 1])
            except ValueError:
                return None
        return None
