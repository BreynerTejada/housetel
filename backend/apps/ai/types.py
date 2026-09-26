from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = ""


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    data: dict | list | None = None
    provider: str = "simulated"
    model: str = ""
    simulated: bool = True
    usage: dict = field(default_factory=dict)


class LLMClient(Protocol):
    def generate(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> LLMResult: ...


# messages: [{"role": "user"|"assistant"|"tool", "content": str, "tool_call_id"?: str, "name"?: str}]
# tools: [{"name": str, "description": str, "parameters": <JSON Schema>}]
