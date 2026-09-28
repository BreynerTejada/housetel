"""Readable schedules of the registered automations: the celery `crontab` (or interval) of each one becomes
`{"cron", "every_seconds", "text": {"es", "en"}}`, plus an estimate of the next run.

Beat runs in `CELERY_TIMEZONE` (America/Bogota, the zone of every property today), so the times shown are the
hotel's local times.
"""

import logging
from datetime import datetime, timedelta

from django.utils import timezone

logger = logging.getLogger("housetel.control")

DAYS = {
    "es": ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"],
    "en": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"],
}
DAY_ALIASES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}


def _field(schedule, name: str) -> str:
    value = getattr(schedule, f"_orig_{name}", "*")
    return str(value).strip() if value is not None else "*"


def _is_int(value: str) -> bool:
    return value.isdigit()


def _ints(value: str) -> list[int] | None:
    parts = [part.strip() for part in value.split(",")]
    return [int(part) for part in parts] if parts and all(_is_int(part) for part in parts) else None


def _join(items: list[str], lang: str) -> str:
    if len(items) <= 1:
        return "".join(items)
    last = " y " if lang == "es" else " and "
    return ", ".join(items[:-1]) + last + items[-1]


def _days(value: str) -> list[int] | None:
    days = []
    for part in value.split(","):
        part = part.strip().lower()
        if _is_int(part):
            days.append(int(part) % 7)
        elif part[:3] in DAY_ALIASES:
            days.append(DAY_ALIASES[part[:3]])
        else:
            return None
    return days


def _cron_text(minute: str, hour: str, dom: str, month: str, dow: str) -> dict:
    cron = f"{minute} {hour} {dom} {month} {dow}"
    fallback = {"es": f"Programación «{cron}»", "en": f"Schedule “{cron}”"}
    if month != "*":
        return fallback
    every_day = dom == "*" and dow == "*"

    if every_day and hour == "*":
        if minute == "*":
            return {"es": "Cada minuto", "en": "Every minute"}
        if minute.startswith("*/") and _is_int(minute[2:]):
            n = int(minute[2:])
            return {"es": f"Cada {n} minutos", "en": f"Every {n} minutes"}
        if _is_int(minute):
            m = int(minute)
            if m == 0:
                return {"es": "Cada hora", "en": "Every hour"}
            return {"es": f"Cada hora, al minuto {m:02d}", "en": f"Every hour at :{m:02d}"}
        return fallback

    if not _is_int(minute):
        return fallback
    m = int(minute)
    if hour.startswith("*/") and _is_int(hour[2:]) and every_day:
        n = int(hour[2:])
        return {"es": f"Cada {n} horas", "en": f"Every {n} hours"}
    hours = _ints(hour)
    if hours is None:
        return fallback
    times = [f"{h:02d}:{m:02d}" for h in hours]
    at_es, at_en = _join(times, "es"), _join(times, "en")
    plural_es = "a las" if len(times) > 1 or hours[0] != 1 else "a la"

    if every_day:
        return {"es": f"Todos los días {plural_es} {at_es}", "en": f"Daily at {at_en}"}
    if dow == "*" and _ints(dom):
        days = _ints(dom) or []
        es_days = _join([str(d) for d in days], "es")
        en_days = _join([str(d) for d in days], "en")
        return {
            "es": f"El día {es_days} de cada mes {plural_es} {at_es}",
            "en": f"Monthly on day {en_days} at {at_en}",
        }
    if dom == "*":
        days = _days(dow)
        if days:
            es_names = _join([DAYS["es"][d] for d in days], "es")
            en_names = _join([DAYS["en"][d] for d in days], "en")
            return {"es": f"Los {es_names} {plural_es} {at_es}", "en": f"{en_names} at {at_en}"}
    return fallback


def describe(schedule) -> dict:
    """`{"cron": "0 2 * * *" | None, "every_seconds": int | None, "text": {"es", "en"}}`."""
    if isinstance(schedule, int | float):
        return _interval(float(schedule))
    run_every = getattr(schedule, "run_every", None)
    if isinstance(run_every, timedelta) and not hasattr(schedule, "_orig_minute"):
        return _interval(run_every.total_seconds())
    if hasattr(schedule, "_orig_minute"):
        fields = [_field(schedule, name) for name in ("minute", "hour", "day_of_month", "month_of_year")]
        dow = _field(schedule, "day_of_week")
        minute, hour, dom, month = fields
        return {
            "cron": f"{minute} {hour} {dom} {month} {dow}",
            "every_seconds": None,
            "text": _cron_text(minute, hour, dom, month, dow),
        }
    return {"cron": None, "every_seconds": None, "text": {"es": str(schedule), "en": str(schedule)}}


def _interval(seconds: float) -> dict:
    seconds = int(seconds)
    if seconds % 3600 == 0 and seconds >= 3600:
        n = seconds // 3600
        text = {
            "es": f"Cada {n} horas" if n > 1 else "Cada hora",
            "en": f"Every {n} hours" if n > 1 else "Every hour",
        }
    elif seconds % 60 == 0 and seconds >= 60:
        n = seconds // 60
        text = {
            "es": f"Cada {n} minutos" if n > 1 else "Cada minuto",
            "en": f"Every {n} minutes" if n > 1 else "Every minute",
        }
    else:
        text = {"es": f"Cada {seconds} segundos", "en": f"Every {seconds} seconds"}
    return {"cron": None, "every_seconds": seconds, "text": text}


def next_run_at(schedule, now: datetime | None = None) -> datetime | None:
    """Estimated next time beat fires this schedule (None if it cannot be computed)."""
    now = now or timezone.now()
    try:
        if isinstance(schedule, int | float):
            return now + timedelta(seconds=float(schedule))
        # celery reads the crontab fields in the zone of the datetime it receives (beat passes local times):
        # hand it "now" in the schedule's zone (CELERY_TIMEZONE), or 02:00 would be read as 02:00 UTC.
        zone = getattr(schedule, "tz", None)
        if zone is not None:
            now = timezone.localtime(now, zone)
        remaining = schedule.remaining_estimate(now)
        if not isinstance(remaining, timedelta):
            return None
        # celery lands a few milliseconds before the minute (21:59:59.97): round to the nearest minute
        return (now + remaining + timedelta(seconds=30)).replace(second=0, microsecond=0)
    except Exception:  # noqa: BLE001 - an exotic schedule must not break the automations page
        logger.debug("Could not estimate the next run of %r", schedule, exc_info=True)
        return None
