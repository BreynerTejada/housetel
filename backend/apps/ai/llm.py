"""LLM contract (spec §4.2). Phase A: always the simulated client; C9 adds Gemini/Claude selection by
IntegrationSetting(kind="llm") with fallback to simulated on quota/errors."""

from apps.ai.types import LLMClient, LLMResult


class SimulatedLLMClient:
    """Deterministic offline client with the same contract as the real providers."""

    provider = "simulated"

    def generate(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
        response_schema: dict | None = None,
        temperature: float = 0.2,
    ) -> LLMResult:
        last_user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        text = (
            f"(modo simulado) Recibí tu mensaje: «{last_user[:200]}». La IA real aún no está conectada."
            if last_user
            else "(modo simulado) ¿En qué puedo ayudarte?"
        )
        return LLMResult(text=text, provider=self.provider, model="simulated", simulated=True)


def get_llm(property=None) -> LLMClient:
    return SimulatedLLMClient()
