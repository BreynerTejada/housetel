"""Run summaries: the figures of a run, a deterministic summary (Spanish and English) and an AI summary
through the LLM contract `apps.ai.llm.get_llm(property).generate(...)`.

The AI summary is asked for as JSON `{"es", "en"}` (`response_schema`). It falls back to the deterministic
one (provider "") when the client is the simulated one, answers nothing usable or fails (quota, network...):
a run never fails because of the LLM.
"""

import json
import logging
from collections import Counter
from decimal import Decimal

from apps.ai.llm import get_llm
from apps.core.i18n import t
from apps.revenue.services.explain import money, percent

logger = logging.getLogger("housetel.revenue")

ZERO = Decimal("0")
CENTS = Decimal("0.01")
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
AI_SCHEMA = {
    "type": "object",
    "properties": {
        "es": {"type": "string", "description": "Resumen en español"},
        "en": {"type": "string", "description": "Summary in English"},
    },
    "required": ["es", "en"],
}
NUMBER_STYLE = (
    "Escribe el dinero en pesos sin decimales (español: $ 1.234.567; inglés: $1,234,567), los porcentajes "
    "sin decimales innecesarios (español: 12 %; inglés: 12%) y las fechas en palabras (español: 12 de "
    "octubre; inglés: October 12). "
)
JSON_ANSWER = (
    'Responde en JSON con las claves "es" (español) y "en" (inglés), el mismo contenido en cada idioma.'
)
SYSTEM_PROMPT = (
    "Eres el asistente de revenue management de un hotel en Colombia. Con los datos de una corrida de "
    "reglas de precio, escribe para el gerente un resumen breve (2 a 4 frases, sin viñetas ni markdown): "
    "qué precios conviene subir o bajar, por qué y qué revisar primero. Usa solo los datos entregados: no "
    "inventes cifras ni fechas. El impacto estimado compara vender las unidades libres al precio recomendado "
    "contra el actual: una bajada en noches vacías lo hace negativo a propósito (busca llenar esas noches). "
    + NUMBER_STYLE
    + JSON_ANSWER
)


def _money(value) -> str:
    return format(Decimal(value).quantize(CENTS), "f")


def impact_figures(recommendations) -> dict:
    """Estimated impact if the free units sell at the recommended prices: Σ (recommended − current) × free
    units, in total and split between raises and drops (a drop on an empty night never hides the raises)."""
    up = down = ZERO
    for rec in recommendations:
        impact = (rec.recommended_price - rec.current_price) * (rec.available_units or 0)
        if rec.change_percent > 0:
            up += impact
        elif rec.change_percent < 0:
            down += impact
    return {"estimated_impact": _money(up + down), "impact_up": _money(up), "impact_down": _money(down)}


def run_stats(property, stored, *, start, end, auto_applied: int, expired: int) -> dict:
    """JSON-safe figures of a run (stored in `RevenueRun.details`, sent to the LLM)."""
    recs = list(stored.recommendations)
    changes = [rec.change_percent for rec in recs]
    rules = Counter(
        reason["name"]
        for rec in recs
        for reason in rec.reasons
        if reason.get("type") == "rule" and reason.get("applied")
    )
    by_type: dict[str, list] = {}
    for rec in recs:
        by_type.setdefault(rec.room_type.code, []).append(rec)
    top = sorted(recs, key=lambda rec: (-abs(rec.change_percent), rec.date, rec.room_type.code))[:5]
    last_night = end.fromordinal(end.toordinal() - 1)
    return {
        "property": property.name,
        "city": property.city,
        "currency": property.currency or "COP",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "last_night": last_night.isoformat(),
        "count": len(recs),
        "up": sum(1 for change in changes if change > 0),
        "down": sum(1 for change in changes if change < 0),
        "avg_change_percent": _money(sum(changes, ZERO) / len(changes)) if changes else "0.00",
        **impact_figures(recs),
        "created": stored.created,
        "refreshed": stored.refreshed,
        "superseded": stored.superseded,
        "kept_rejected": stored.kept_rejected,
        "expired": expired,
        "auto_applied": auto_applied,
        "rules": [
            {"name": name, "count": count}
            for name, count in sorted(rules.items(), key=lambda i: (-i[1], i[0]))
        ],
        "room_types": [
            {
                "code": code,
                "name": t(items[0].room_type.name, "es"),
                "count": len(items),
                "avg_change_percent": _money(sum((rec.change_percent for rec in items), ZERO) / len(items)),
            }
            for code, items in by_type.items()
        ],
        "top": [
            {
                "date": rec.date.isoformat(),
                "room_type": rec.room_type.code,
                "change_percent": _money(rec.change_percent),
                "current_price": _money(rec.current_price),
                "recommended_price": _money(rec.recommended_price),
                "reasons": [r["name"] for r in rec.reasons if r.get("type") == "rule" and r.get("applied")],
            }
            for rec in top
        ],
    }


def _date(value: str, lang: str) -> str:
    year, month, day = (int(part) for part in value.split("-"))
    return f"{day:02d}/{month:02d}/{year}" if lang == "es" else f"{MONTHS_EN[month - 1]} {day}, {year}"


def _split(stats: dict, lang: str) -> str:
    """Both sides of the impact, e.g. ` (subidas +$ 300.000; bajadas −$ 150.000)`, when a run has both."""
    if not (stats["up"] and stats["down"]):
        return ""
    currency = stats["currency"]
    up = "+" + money(stats["impact_up"], lang, currency)
    down = money(stats["impact_down"], lang, currency)
    if lang == "es":
        return f" (subidas {up}; bajadas {down})"
    return f" (raises {up}; drops {down})"


def template_summary(stats: dict) -> dict:
    """Deterministic `{"es", "en"}` summary of a run."""
    currency, count = stats["currency"], stats["count"]
    result = {}
    for lang in ("es", "en"):
        start, last = _date(stats["start"], lang), _date(stats["last_night"], lang)
        if lang == "es":
            text = f"Se revisaron las noches del {start} al {last}: "
            if not count:
                result[lang] = text + "no hay cambios de precio que recomendar."
                continue
            noun = "recomendación" if count == 1 else "recomendaciones"
            text += (
                f"{count} {noun} ({stats['up']} de subida y {stats['down']} de bajada), cambio medio "
                f"{percent(stats['avg_change_percent'], lang, signed=True)}."
            )
            if stats["rules"]:
                text += (
                    " Motivos principales: "
                    + ", ".join(f"{item['name']} ({item['count']})" for item in stats["rules"][:3])
                    + "."
                )
            impact = money(stats["estimated_impact"], lang, currency)
            text += f" Impacto estimado si se venden las unidades libres: {impact}{_split(stats, lang)}."
            if stats["auto_applied"]:
                text += f" Se aplicaron automáticamente {stats['auto_applied']}."
        else:
            text = f"Nights from {start} to {last} reviewed: "
            if not count:
                result[lang] = text + "no price changes to recommend."
                continue
            noun = "recommendation" if count == 1 else "recommendations"
            text += (
                f"{count} {noun} ({stats['up']} up, {stats['down']} down), average change "
                f"{percent(stats['avg_change_percent'], lang, signed=True)}."
            )
            if stats["rules"]:
                text += (
                    " Main reasons: "
                    + ", ".join(f"{item['name']} ({item['count']})" for item in stats["rules"][:3])
                    + "."
                )
            impact = money(stats["estimated_impact"], lang, currency)
            text += f" Estimated impact if the free units sell: {impact}{_split(stats, lang)}."
            if stats["auto_applied"]:
                text += f" {stats['auto_applied']} applied automatically."
        result[lang] = text
    return result


def ai_summary(property, stats: dict) -> tuple[dict, str]:
    """`({"es", "en"}, provider)` written by the LLM, or `({}, "")` when it is not available."""
    return ask_llm(
        property,
        system=SYSTEM_PROMPT,
        content="Datos de la corrida (JSON):\n" + json.dumps(stats, ensure_ascii=False),
        purpose="summary",
    )


def ask_llm(property, *, system: str, content: str, purpose: str) -> tuple[dict, str]:
    """One bilingual answer `({"es", "en"}, provider)` from `get_llm(property)`, asked as JSON; `({}, "")`
    when the client is the simulated one, answers nothing usable or fails (quota, network, provider bugs)."""
    try:
        client = get_llm(property)
        if hasattr(client, "feature"):  # C9's client tags its usage records by feature
            client.feature = "revenue"
        result = client.generate(
            [{"role": "user", "content": content}],
            system=system,
            response_schema=AI_SCHEMA,
            temperature=0.3,
        )
    except Exception:  # noqa: BLE001 - quota, network, provider bugs: the template is the fallback
        logger.warning("Revenue AI %s unavailable (property=%s)", purpose, property.pk, exc_info=True)
        return {}, ""
    if result is None or getattr(result, "simulated", True):
        return {}, ""
    data = result.data
    if data is None and (result.text or "").strip().startswith("{"):
        try:
            data = json.loads(result.text)
        except ValueError:
            data = None
    if isinstance(data, dict) and all(
        isinstance(data.get(lang), str) and data[lang].strip() for lang in ("es", "en")
    ):
        return {lang: data[lang].strip()[:3000] for lang in ("es", "en")}, result.provider or "llm"
    text = (result.text or "").strip()
    if text:
        return {"es": text[:3000], "en": text[:3000]}, result.provider or "llm"
    return {}, ""


EXPLAIN_PROMPT = (
    "Eres el asistente de revenue management de un hotel en Colombia. Explica al equipo del hotel, en 2 o 3 "
    "frases claras y sin jerga (sin viñetas ni markdown), por qué conviene cambiar el precio de esta noche "
    "y qué gana o arriesga el hotel si lo aprueba. Usa solo los datos entregados (reglas que aplicaron, "
    "ocupación, anticipación, límites): no inventes cifras, fechas ni eventos. " + NUMBER_STYLE + JSON_ANSWER
)
WEEKDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def explanation_facts(rec) -> dict:
    """JSON-safe facts of one recommendation for the LLM (what its deterministic explanation says)."""
    prop = rec.property
    return {
        "hotel": prop.name,
        "city": prop.city,
        "currency": prop.currency or "COP",
        "category": t(rec.room_type.name, "es"),
        "rate_plan": t(rec.rate_plan.name, "es"),
        "night": rec.date.isoformat(),
        "weekday": WEEKDAYS_ES[rec.date.weekday()],
        "days_ahead": (rec.date - prop.business_date).days,
        "current_price": _money(rec.current_price),
        "recommended_price": _money(rec.recommended_price),
        "change_percent": _money(rec.change_percent),
        "reference_price": _money(rec.anchor_price),
        "reference_source": rec.anchor_source,
        "rules_adjustment_percent": _money(rec.adjustment_percent),
        "occupancy_percent": None if rec.occupancy is None else _money(rec.occupancy),
        "free_units": rec.available_units,
        "reasons": rec.reasons,
        "status": rec.status,
        "deterministic_explanation": rec.explanation.get("es", ""),
    }


def ai_explanation(rec) -> tuple[dict, str]:
    """`({"es", "en"}, provider)`: the LLM's plain-language explanation of one recommendation, or `({}, "")`
    when the LLM is not available (the caller shows the deterministic explanation)."""
    return ask_llm(
        rec.property,
        system=EXPLAIN_PROMPT,
        content="Recomendación de precio (JSON):\n" + json.dumps(explanation_facts(rec), ensure_ascii=False),
        purpose="explanation",
    )
