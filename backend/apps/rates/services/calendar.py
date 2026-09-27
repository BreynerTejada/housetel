"""Colombian public holidays (library `holidays`, country CO) for the grid, the calendar and revenue."""

from datetime import date

import holidays

LANGUAGES = {"es": "es", "en": "en_US"}


def holiday_list(start: date, end: date, lang: str = "es") -> list[dict]:
    """`[{"date": "YYYY-MM-DD", "name": str}]` of the holidays in `[start, end)`, by date."""
    if end <= start:
        return []
    last = date.fromordinal(end.toordinal() - 1)
    calendar = holidays.country_holidays(
        "CO", years=range(start.year, last.year + 1), language=LANGUAGES.get(lang, "es")
    )
    return [
        {"date": day.isoformat(), "name": name}
        for day, name in sorted(calendar.items())
        if start <= day < end
    ]
