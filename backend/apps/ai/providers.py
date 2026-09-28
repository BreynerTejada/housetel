"""Integration providers of kind `llm` (spec §1.2), listed by the control center (C12).

The runtime client comes from `apps.ai.llm.get_llm`; these classes describe the configuration form
(`CONFIG_FIELDS`) and implement `test_connection` for the integrations page.
"""

from django.conf import settings

from apps.core.integrations import BaseProvider, register_provider


class RealLLMProvider(BaseProvider):
    kind = "llm"
    mode = "real"
    label = "Gemini / Claude"
    CONFIG_FIELDS = [
        {
            "name": "provider",
            "label_es": "Proveedor",
            "label_en": "Provider",
            "type": "select",
            "secret": False,
            "required": True,
            "options": [
                {"value": "gemini", "label_es": "Google Gemini", "label_en": "Google Gemini"},
                {"value": "claude", "label_es": "Anthropic Claude", "label_en": "Anthropic Claude"},
            ],
            "help_es": "Gemini es el proveedor por defecto de la plataforma.",
            "help_en": "Gemini is the platform's default provider.",
        },
        {
            "name": "model",
            "label_es": "Modelo (opcional)",
            "label_en": "Model (optional)",
            "type": "text",
            "secret": False,
            "required": False,
            "help_es": "Vacío = el modelo de la plataforma (GEMINI_MODEL o CLAUDE_MODEL).",
            "help_en": "Empty = the platform model (GEMINI_MODEL or CLAUDE_MODEL).",
        },
        {
            "name": "api_key",
            "label_es": "Clave de API propia (opcional)",
            "label_en": "Own API key (optional)",
            "type": "password",
            "secret": True,
            "required": False,
            "help_es": "Vacío = se usa la clave de la plataforma.",
            "help_en": "Empty = the platform key is used.",
        },
    ]

    def test_connection(self) -> tuple[bool, str]:
        from apps.ai.llm import PROVIDER_LABELS, _live_calls_allowed, _real_client, provider_config

        provider, model, api_key = provider_config(self.setting)
        if not api_key:
            return False, f"Falta la clave de API de {PROVIDER_LABELS[provider]}"
        if not _live_calls_allowed():
            return False, "La prueba de conexión no contacta al proveedor durante los tests"
        return _real_client(provider, api_key=api_key, model=model).test_connection()


class SimulatedLLMProvider(BaseProvider):
    kind = "llm"
    mode = "simulated"
    label = "Asistente simulado"
    CONFIG_FIELDS: list[dict] = []

    def test_connection(self) -> tuple[bool, str]:
        return True, "El asistente simulado responde sin conexión"


register_provider("llm", "real", RealLLMProvider)
register_provider("llm", "simulated", SimulatedLLMProvider)

# The platform keys are read from the environment (never stored in the database).
PLATFORM_KEYS = {
    "gemini": lambda: bool(settings.GEMINI_API_KEY),
    "claude": lambda: bool(settings.ANTHROPIC_API_KEY),
}
