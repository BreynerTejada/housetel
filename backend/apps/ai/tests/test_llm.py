"""Phase A stub (plan Step 5): get_llm returns a simulated client; C9 adds Gemini/Claude and the fallback."""

import pytest

from apps.ai.llm import SimulatedLLMClient, get_llm
from apps.ai.types import LLMResult


def test_without_property_returns_the_simulated_client():
    assert isinstance(get_llm(), SimulatedLLMClient)


@pytest.mark.django_db
def test_simulated_client_answers_offline(prop):
    result = get_llm(prop).generate(
        [{"role": "user", "content": "¿Cuántas llegadas hay hoy?"}],
        system="Eres el copiloto",
        tools=[{"name": "list_arrivals", "description": "", "parameters": {}}],
    )
    assert isinstance(result, LLMResult)
    assert (result.simulated, result.provider, result.tool_calls) == (True, "simulated", [])
    assert result.text.startswith("(modo simulado)")
