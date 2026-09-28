"""Deterministic explanation of one recommendation, in Spanish and English: the change, the rules that moved
the price (with their adjustments), the limits that held it back, the commercial rounding (the recommended
price is always the final, rounded one) and, when it differs from the current price, the reference (anchor)
price it was computed from."""

from decimal import Decimal

from apps.rates.services.resolution import WEEKDAYS

WEEKDAY_NAMES = {
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
SOURCE_NAMES = {
    "es": {
        "default": "precio por defecto",
        "season": "temporada",
        "manual": "precio manual",
        "bulk": "edición masiva",
        "channel": "canal",
        "revenue": "revenue",
    },
    "en": {
        "default": "default price",
        "season": "season",
        "manual": "manual price",
        "bulk": "bulk edit",
        "channel": "channel",
        "revenue": "revenue",
    },
}
MINUS = "−"


def number(value, lang: str) -> str:
    """12 → "12", 13.04 → "13,04" (es) / "13.04" (en); trailing zeros dropped."""
    text = format(Decimal(str(value)).quantize(Decimal("0.01")).normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",") if lang == "es" else text


def percent(value, lang: str, *, signed: bool = False) -> str:
    value = Decimal(str(value))
    sign = ("+" if value > 0 else MINUS if value < 0 else "") if signed else ""
    body = number(abs(value) if signed else value, lang)
    return f"{sign}{body} %" if lang == "es" else f"{sign}{body}%"


def money(value, lang: str, currency: str = "COP") -> str:
    """$ 300.000 (es) / $300,000 (en); COP without decimals; negatives as −$ 4.767.200."""
    amount = Decimal(str(value))
    decimals = 0 if currency == "COP" else 2
    sign = MINUS if amount < 0 else ""
    text = f"{abs(amount):,.{decimals}f}"
    if lang == "es":
        text = text.replace(",", "·").replace(".", ",").replace("·", ".")
        return f"{sign}$ {text}"
    return f"{sign}${text}"


def _rule_label(reason: dict, lang: str) -> str:
    kind, detail = reason["kind"], reason.get("detail") or {}
    if kind == "occupancy":
        occupancy = number(detail.get("occupancy", 0), lang)
        return f"ocupación del {occupancy} %" if lang == "es" else f"{occupancy}% occupancy"
    if kind == "lead_time":
        days = int(detail.get("lead_days", 0))
        if detail.get("window") == "early_bird":
            return (
                f"anticipación ({days} días antes)" if lang == "es" else f"booked early ({days} days ahead)"
            )
        if lang == "es":
            when = "es hoy" if days == 0 else "falta 1 día" if days == 1 else f"faltan {days} días"
            return f"última hora ({when})"
        when = "today" if days == 0 else "1 day to go" if days == 1 else f"{days} days to go"
        return f"last minute ({when})"
    if kind == "day_of_week":
        return WEEKDAY_NAMES[lang][WEEKDAYS.index(detail.get("weekday", "mon"))]
    if kind == "holiday":
        name = detail.get(f"name_{lang}") or detail.get("name_es", "")
        if detail.get("bridge"):
            return f"puente de {name}" if lang == "es" else f"long weekend: {name}"
        return f"festivo {name}" if lang == "es" else f"holiday: {name}"
    if kind == "event":
        name = detail.get("name") or reason.get("name", "")
        return f"evento {name}" if lang == "es" else f"event: {name}"
    return reason.get("name", kind)


def _limit_label(reason: dict, lang: str, currency: str) -> str:
    kind = reason["kind"]
    if kind == "rounding":
        step = money(reason.get("step") or 0, lang, currency)
        return f"redondeado a múltiplos de {step}" if lang == "es" else f"rounded to multiples of {step}"
    if kind == "max_daily_change":
        limit = percent(reason["percent"], lang)
        return (
            f"limitado al cambio máximo de {limit}"
            if lang == "es"
            else f"capped at the {limit} maximum change"
        )
    price = money(reason["price"], lang, currency)
    if kind == "min_price":
        return f"sube al mínimo de {price}" if lang == "es" else f"raised to the {price} floor"
    return f"baja al máximo de {price}" if lang == "es" else f"lowered to the {price} ceiling"


def _sentence(*, current, recommended, change, anchor, anchor_source, reasons, currency, lang) -> str:
    change = Decimal(str(change))
    amount = percent(abs(change), lang)
    if lang == "es":
        head = f"{'Sube' if change > 0 else 'Baja'} {amount} (de {money(current, lang, currency)} a "
        head += f"{money(recommended, lang, currency)})"
    else:
        head = f"{'Up' if change > 0 else 'Down'} {amount} (from {money(current, lang, currency)} to "
        head += f"{money(recommended, lang, currency)})"
    parts = [
        f"{_rule_label(reason, lang)} ({percent(reason['adjust'], lang, signed=True)})"
        for reason in reasons
        if reason.get("type") == "rule" and reason.get("applied")
    ]
    if not parts:
        parts.append("vuelve al precio de referencia" if lang == "es" else "back to the reference price")
    parts += [_limit_label(reason, lang, currency) for reason in reasons if reason.get("type") == "limit"]
    text = f"{head}: {'; '.join(parts)}."
    if Decimal(str(anchor)) != Decimal(str(current)):
        source = SOURCE_NAMES[lang].get(anchor_source, anchor_source)
        label = "Referencia" if lang == "es" else "Reference"
        text += f" {label}: {money(anchor, lang, currency)} ({source})."
    return text


def explain(*, current, recommended, change, anchor, anchor_source, reasons, currency="COP") -> dict:
    """`{"es": str, "en": str}` explaining why the price should move from `current` to `recommended`."""
    values = {
        "current": current,
        "recommended": recommended,
        "change": change,
        "anchor": anchor,
        "anchor_source": anchor_source,
        "reasons": reasons,
        "currency": currency,
    }
    return {lang: _sentence(**values, lang=lang) for lang in ("es", "en")}
