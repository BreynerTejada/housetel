"""Pricing rule kinds: params (validation + normalization) and the evaluation of one rule for one night.

Params by kind (adjustments are percentages over the anchor price, from −90 to +300):

- occupancy    `{"tiers": [{"min": 0, "max": 40, "adjust": -8}, …]}` — on-the-books occupancy of the night
               (0–100 %). `min` inclusive, `max` exclusive, except that a tier ending at 100 includes 100.
               Tiers may leave gaps but never overlap.
- lead_time    `{"last_minute": [{"max_days": 3, "adjust": -5}],
                "early_bird": [{"min_days": 60, "adjust": 4}]}`
               — days from the business date to the night. The tightest last-minute window (smallest
               `max_days` ≥ lead) or the widest early-bird window (largest `min_days` ≤ lead) applies; every
               early-bird window starts after every last-minute one.
- day_of_week  `{"fri": 5, "sat": 10}` — keys mon…sun.
- holiday      `{"adjust": 12, "include_bridges": true}` — Colombian holidays (library `holidays`) and, with
               `include_bridges`, the Saturday and Sunday nights of a long weekend ("puente") that ends on a
               Monday holiday.
- event        `{"name": "Festival", "start": "2027-01-08", "end": "2027-01-12", "adjust": 20}` — manual
               event; `end` is inclusive (like seasons), at most 366 nights.

Numbers are stored as JSON numbers (ints when integral).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

import holidays as holidays_lib

from apps.core.errors import DomainError
from apps.rates.services.resolution import WEEKDAYS

KINDS = ("occupancy", "lead_time", "day_of_week", "holiday", "event")
MIN_ADJUST = Decimal("-90")
MAX_ADJUST = Decimal("300")
MAX_LEAD_DAYS = 730
MAX_EVENT_NIGHTS = 366
HOLIDAY_LANGUAGES = {"es": "es", "en": "en_US"}


@dataclass(frozen=True)
class NightFacts:
    """What the rules look at for one night of one category."""

    date: date
    lead_days: int
    occupancy: Decimal | None  # on-the-books %, None when the category has nothing to sell that night
    holiday: dict | None = None  # {"name_es", "name_en"} when the night is a holiday
    bridge: dict | None = None  # {"name_es", "name_en"} of the Monday holiday of its long weekend


@dataclass(frozen=True)
class RuleHit:
    adjust: Decimal
    detail: dict


@dataclass(frozen=True)
class HolidayFacts:
    holidays: dict  # date → {"name_es", "name_en"}
    bridges: dict  # Saturday/Sunday date → names of the Monday holiday


def params_error(message: str) -> DomainError:
    return DomainError(message, code="invalid_rule_params", fields={"params": [message]})


# ---- validation -----------------------------------------------------------------------------------------


def clean_params(kind: str, params) -> dict:
    """Validated and normalized params of a rule of `kind` (DomainError `invalid_rule_params` otherwise)."""
    cleaner = _CLEANERS.get(kind)
    if cleaner is None:
        raise params_error(f"Tipo de regla desconocido: {kind}")
    if not isinstance(params, dict):
        raise params_error("Los parámetros deben ser un objeto")
    return cleaner(params)


def _number(value, label: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise params_error(f"{label} debe ser un número")
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise params_error(f"{label} debe ser un número") from None
    if not number.is_finite():
        raise params_error(f"{label} debe ser un número")
    return number.quantize(Decimal("0.01"))


def _adjust(value) -> Decimal:
    adjust = _number(value, "El ajuste")
    if not MIN_ADJUST <= adjust <= MAX_ADJUST:
        raise params_error("El ajuste va de −90 % a +300 %")
    return adjust


def _days(value, label: str, *, minimum: int) -> int:
    number = _number(value, label)
    if number != number.to_integral_value() or not minimum <= number <= MAX_LEAD_DAYS:
        raise params_error(f"{label} debe ser un número entero de días entre {minimum} y {MAX_LEAD_DAYS}")
    return int(number)


def _json_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _items(params, key: str, *, required=True) -> list:
    items = params.get(key)
    if items is None and not required:
        return []
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise params_error(f"«{key}» debe ser una lista de tramos")
    return items


def _clean_occupancy(params: dict) -> dict:
    tiers = []
    for item in _items(params, "tiers"):
        low, high = _number(item.get("min"), "El mínimo"), _number(item.get("max"), "El máximo")
        if not (0 <= low < high <= 100):
            raise params_error("Cada tramo va de 0 % a 100 % y su mínimo es menor que su máximo")
        tiers.append((low, high, _adjust(item.get("adjust"))))
    if not tiers:
        raise params_error("Agrega al menos un tramo de ocupación")
    tiers.sort()
    for (_, previous_high, _), (low, _, _) in zip(tiers, tiers[1:], strict=False):
        if low < previous_high:
            raise params_error("Los tramos de ocupación no pueden solaparse")
    return {
        "tiers": [
            {"min": _json_number(low), "max": _json_number(high), "adjust": _json_number(adjust)}
            for low, high, adjust in tiers
        ]
    }


def _clean_lead_time(params: dict) -> dict:
    last_minute = sorted(
        (_days(item.get("max_days"), "«Faltan como máximo»", minimum=0), _adjust(item.get("adjust")))
        for item in _items(params, "last_minute", required=False)
    )
    early_bird = sorted(
        (_days(item.get("min_days"), "«Faltan al menos»", minimum=1), _adjust(item.get("adjust")))
        for item in _items(params, "early_bird", required=False)
    )
    if not last_minute and not early_bird:
        raise params_error("Agrega al menos una ventana de última hora o de anticipación")
    for windows in (last_minute, early_bird):
        days = [value for value, _ in windows]
        if len(set(days)) != len(days):
            raise params_error("Hay ventanas repetidas con los mismos días")
    if last_minute and early_bird and early_bird[0][0] <= last_minute[-1][0]:
        raise params_error("Las ventanas de anticipación deben empezar después de las de última hora")
    return {
        "last_minute": [{"max_days": days, "adjust": _json_number(adjust)} for days, adjust in last_minute],
        "early_bird": [{"min_days": days, "adjust": _json_number(adjust)} for days, adjust in early_bird],
    }


def _clean_day_of_week(params: dict) -> dict:
    unknown = set(params) - set(WEEKDAYS)
    if unknown:
        raise params_error(f"Días desconocidos: {', '.join(sorted(unknown))} (usa mon…sun)")
    if not params:
        raise params_error("Indica el ajuste de al menos un día")
    return {day: _json_number(_adjust(params[day])) for day in WEEKDAYS if day in params}


def _clean_holiday(params: dict) -> dict:
    include_bridges = params.get("include_bridges", True)
    if not isinstance(include_bridges, bool):
        raise params_error("«Incluir puentes» es sí o no")
    return {"adjust": _json_number(_adjust(params.get("adjust"))), "include_bridges": include_bridges}


def _date(value, label: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise params_error(f"{label} debe ser una fecha AAAA-MM-DD") from None


def _clean_event(params: dict) -> dict:
    start, end = _date(params.get("start"), "El inicio"), _date(params.get("end"), "El fin")
    if end < start:
        raise params_error("El evento termina antes de empezar")
    if (end - start).days + 1 > MAX_EVENT_NIGHTS:
        raise params_error("Un evento dura como máximo un año")
    name = params.get("name") or ""
    if not isinstance(name, str) or len(name) > 120:
        raise params_error("El nombre del evento es un texto de hasta 120 caracteres")
    return {
        "name": name.strip(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        "adjust": _json_number(_adjust(params.get("adjust"))),
    }


_CLEANERS = {
    "occupancy": _clean_occupancy,
    "lead_time": _clean_lead_time,
    "day_of_week": _clean_day_of_week,
    "holiday": _clean_holiday,
    "event": _clean_event,
}


# ---- evaluation -----------------------------------------------------------------------------------------


def evaluate(kind: str, params: dict, facts: NightFacts) -> RuleHit | None:
    """The adjustment of one rule for one night, or None when it does not apply (params already clean)."""
    return _EVALUATORS[kind](params, facts)


def _eval_occupancy(params: dict, facts: NightFacts) -> RuleHit | None:
    occupancy = facts.occupancy
    if occupancy is None:
        return None
    for tier in params["tiers"]:
        low, high = Decimal(str(tier["min"])), Decimal(str(tier["max"]))
        if low <= occupancy < high or occupancy == high == 100:
            return RuleHit(Decimal(str(tier["adjust"])), {"occupancy": format(occupancy, "f")})
    return None


def _eval_lead_time(params: dict, facts: NightFacts) -> RuleHit | None:
    lead = facts.lead_days
    last_minute = [tier for tier in params.get("last_minute", []) if lead <= tier["max_days"]]
    if last_minute:
        tier = min(last_minute, key=lambda item: item["max_days"])
        detail = {"lead_days": lead, "window": "last_minute", "days": tier["max_days"]}
        return RuleHit(Decimal(str(tier["adjust"])), detail)
    early_bird = [tier for tier in params.get("early_bird", []) if lead >= tier["min_days"]]
    if early_bird:
        tier = max(early_bird, key=lambda item: item["min_days"])
        detail = {"lead_days": lead, "window": "early_bird", "days": tier["min_days"]}
        return RuleHit(Decimal(str(tier["adjust"])), detail)
    return None


def _eval_day_of_week(params: dict, facts: NightFacts) -> RuleHit | None:
    weekday = WEEKDAYS[facts.date.weekday()]
    adjust = Decimal(str(params.get(weekday) or 0))
    return RuleHit(adjust, {"weekday": weekday}) if adjust else None


def _eval_holiday(params: dict, facts: NightFacts) -> RuleHit | None:
    adjust = Decimal(str(params["adjust"]))
    if facts.holiday:
        return RuleHit(adjust, {**facts.holiday, "bridge": False})
    if facts.bridge and params.get("include_bridges", True):
        return RuleHit(adjust, {**facts.bridge, "bridge": True})
    return None


def _eval_event(params: dict, facts: NightFacts) -> RuleHit | None:
    start, end = date.fromisoformat(params["start"]), date.fromisoformat(params["end"])
    if start <= facts.date <= end:
        return RuleHit(Decimal(str(params["adjust"])), {"name": params.get("name", "")})
    return None


_EVALUATORS = {
    "occupancy": _eval_occupancy,
    "lead_time": _eval_lead_time,
    "day_of_week": _eval_day_of_week,
    "holiday": _eval_holiday,
    "event": _eval_event,
}


# ---- Colombian holidays -------------------------------------------------------------------------------


def holiday_facts(start: date, end: date) -> HolidayFacts:
    """Holidays of `[start, end)` and the long-weekend nights (Saturday and Sunday before a Monday holiday)
    of that range, with the names in Spanish and English."""
    if end <= start:
        return HolidayFacts({}, {})
    years = range(start.year, (end + timedelta(days=2)).year + 1)
    calendars = {
        lang: holidays_lib.country_holidays("CO", years=years, language=code)
        for lang, code in HOLIDAY_LANGUAGES.items()
    }
    names = {
        day: {"name_es": name, "name_en": calendars["en"].get(day, name)}
        for day, name in calendars["es"].items()
    }
    found, bridges = {}, {}
    day = start
    while day < end:
        if day in names:
            found[day] = names[day]
        if day.weekday() in (5, 6):  # Saturday, Sunday
            monday = day + timedelta(days=7 - day.weekday())
            if monday in names:
                bridges[day] = names[monday]
        day += timedelta(days=1)
    return HolidayFacts(found, bridges)
