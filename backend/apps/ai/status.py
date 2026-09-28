"""What the settings page and the copilot panel show about the LLM provider and the AI usage of a hotel."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.ai.llm import PROVIDER_LABELS, PROVIDERS, provider_config, provider_status

COPILOT_SUGGESTIONS = [
    ("list_arrivals", "¿Cuántas llegadas hay hoy?", "How many arrivals are there today?"),
    ("get_occupancy", "¿Cómo va la ocupación esta semana?", "How is occupancy this week?"),
    (
        "check_availability",
        "¿Hay disponibilidad este fin de semana para 2 adultos?",
        "Is there availability this weekend for 2 adults?",
    ),
    ("list_departures", "¿Quién sale hoy?", "Who is checking out today?"),
    ("get_today_summary", "Dame el resumen del día", "Give me today's summary"),
    ("list_alerts", "¿Qué alertas hay abiertas?", "Which alerts are open?"),
]


def _platform_key(provider: str) -> bool:
    return bool(settings.GEMINI_API_KEY if provider == "gemini" else settings.ANTHROPIC_API_KEY)


def provider_info(prop) -> dict:
    """Configured provider and whether answers really come from it (`effective`: real | simulated). Secrets
    are never returned, only whether they exist."""
    from apps.core import integrations

    setting = integrations.get_setting(prop, "llm")
    provider, model, api_key = provider_config(setting)
    effective = "real" if setting.mode == "real" and setting.enabled and api_key else "simulated"
    return {
        "mode": setting.mode,
        "enabled": setting.enabled,
        "provider": provider,
        "label": PROVIDER_LABELS[provider],
        "model": model,  # the one in use: the hotel's own or, when empty, the platform's
        "custom_model": (setting.config or {}).get("model", ""),
        "platform_model": settings.GEMINI_MODEL if provider == "gemini" else settings.CLAUDE_MODEL,
        "effective": effective,
        "effective_label": PROVIDER_LABELS[provider] if effective == "real" else PROVIDER_LABELS["simulated"],
        "platform_key_configured": _platform_key(provider),
        "own_key_configured": bool(integrations.get_secrets(setting).get("api_key")),
        "status": provider_status(prop),
        "providers": [
            {"value": code, "label": PROVIDER_LABELS[code], "platform_key_configured": _platform_key(code)}
            for code in PROVIDERS
        ],
    }


def update_provider(prop, *, mode=None, provider=None, model=None) -> dict:
    """Change the llm integration of the hotel; returns the changes `{field: [before, after]}`."""
    from apps.core import integrations

    setting = integrations.get_setting(prop, "llm")
    config = dict(setting.config or {})
    changes = {}
    if mode is not None and mode != setting.mode:
        changes["mode"] = [setting.mode, mode]
        setting.mode = mode
    if provider is not None and provider != config.get("provider", "gemini"):
        changes["provider"] = [config.get("provider", "gemini"), provider]
        config["provider"] = provider
    if model is not None and model.strip() != config.get("model", ""):
        changes["model"] = [config.get("model", ""), model.strip()]
        if model.strip():
            config["model"] = model.strip()
        else:
            config.pop("model", None)
    if changes:
        setting.config = config
        setting.save(update_fields=["mode", "config", "updated_at"])
    return changes


def copilot_suggestions(user, prop, lang: str) -> list[str]:
    from apps.ai.copilot.tools import available_tools

    names = {tool.name for tool in available_tools(user, prop)}
    return [en if lang == "en" else es for tool, es, en in COPILOT_SUGGESTIONS if tool in names][:4]


def usage_report(prop, *, days: int = 30) -> dict:
    from apps.ai.models import AIUsage

    since = timezone.now() - timedelta(days=days)
    rows = AIUsage.objects.filter(property=prop, created_at__gte=since)
    totals = rows.aggregate(
        calls=Count("id"),
        errors=Count("id", filter=Q(success=False)),
        simulated=Count("id", filter=Q(provider="simulated")),
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
        avg_latency_ms=Avg("latency_ms", filter=~Q(provider="simulated")),
    )
    totals = {
        **totals,
        "input_tokens": totals["input_tokens"] or 0,
        "output_tokens": totals["output_tokens"] or 0,
        "avg_latency_ms": round(totals["avg_latency_ms"] or 0),
        "real": totals["calls"] - totals["simulated"],
    }

    def grouped(field):
        return [
            {
                field: item[field],
                "calls": item["calls"],
                "errors": item["errors"],
                "simulated": item["simulated"],
            }
            for item in rows.values(field)
            .annotate(
                calls=Count("id"),
                errors=Count("id", filter=Q(success=False)),
                simulated=Count("id", filter=Q(provider="simulated")),
            )
            .order_by("-calls", field)
        ]

    by_day = [
        {
            "date": item["day"].isoformat(),
            "calls": item["calls"],
            "errors": item["errors"],
            "simulated": item["simulated"],
        }
        for item in rows.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(
            calls=Count("id"),
            errors=Count("id", filter=Q(success=False)),
            simulated=Count("id", filter=Q(provider="simulated")),
        )
        .order_by("day")
    ]
    recent_errors = [
        {
            "at": item.created_at.isoformat(),
            "feature": item.feature,
            "provider": item.provider,
            "error": item.error,
        }
        for item in rows.filter(success=False).order_by("-created_at")[:5]
    ]
    return {
        "since": since.date().isoformat(),
        "days": days,
        "totals": totals,
        "by_feature": grouped("feature"),
        "by_provider": grouped("provider"),
        "by_day": by_day,
        "recent_errors": recent_errors,
    }
