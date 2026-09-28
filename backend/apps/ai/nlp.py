"""Small deterministic language helpers (Spanish and English) for the offline assistant.

`stay_dates` understands ranges ("del 12 al 14 de octubre", "October 12-14"), single dates with nights ("on
Oct 5 for 2 nights"), numeric and ISO dates, weekdays ("el viernes") and relative words ("mañana", "este fin
de semana"). `best_answer` picks the knowledge line that best matches a question (keywords + synonyms).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

MONTHS = {
    "enero": 1,
    "ene": 1,
    "january": 1,
    "jan": 1,
    "febrero": 2,
    "feb": 2,
    "february": 2,
    "marzo": 3,
    "march": 3,
    "abril": 4,
    "abr": 4,
    "april": 4,
    "apr": 4,
    "mayo": 5,
    "may": 5,
    "junio": 6,
    "jun": 6,
    "june": 6,
    "julio": 7,
    "jul": 7,
    "july": 7,
    "agosto": 8,
    "ago": 8,
    "august": 8,
    "aug": 8,
    "septiembre": 9,
    "setiembre": 9,
    "sept": 9,
    "sep": 9,
    "september": 9,
    "octubre": 10,
    "oct": 10,
    "october": 10,
    "noviembre": 11,
    "nov": 11,
    "november": 11,
    "diciembre": 12,
    "dic": 12,
    "december": 12,
    "dec": 12,
}
WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
NUMBER_WORDS = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "one": 1,
    "dos": 2,
    "two": 2,
    "tres": 3,
    "three": 3,
    "cuatro": 4,
    "four": 4,
    "cinco": 5,
    "five": 5,
    "seis": 6,
    "six": 6,
    "siete": 7,
    "seven": 7,
    "ocho": 8,
    "eight": 8,
}

_MONTH = "|".join(sorted(MONTHS, key=len, reverse=True))
_NUM = r"\d+|" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True))
_ORD = r"(?:st|nd|rd|th)?"

ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
NUMERIC_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b")
RANGE_DAY_FIRST = re.compile(
    rf"\b(\d{{1,2}}){_ORD}\s*(?:al|a|-|y\s+el|y|hasta\s+el|hasta|to|through|until)\s*(?:el\s+)?(\d{{1,2}}){_ORD}\s+(?:de\s+)?({_MONTH})\b"
)
RANGE_MONTH_FIRST = re.compile(
    rf"\b({_MONTH})\.?\s+(\d{{1,2}}){_ORD}\s*(?:-|to|through|until|al)\s*(\d{{1,2}}){_ORD}\b(?!\s*(?:/|:|{_MONTH}))"
)
DAY_MONTH = re.compile(rf"\b(\d{{1,2}}){_ORD}\s+(?:de\s+)?({_MONTH})\b")
MONTH_DAY = re.compile(rf"\b({_MONTH})\.?\s+(\d{{1,2}}){_ORD}\b")
NIGHTS = re.compile(rf"\b({_NUM})\s*(?:noches?|nights?)\b")
WEEKEND = re.compile(r"\b(?:fin\s+de\s+semana|weekend)\b")
RELATIVE = [
    (re.compile(r"\b(?:pasado\s+manana|day\s+after\s+tomorrow)\b"), 2),
    (re.compile(r"\b(?:manana|tomorrow)\b"), 1),
    (re.compile(r"\b(?:hoy|today|esta\s+noche|tonight)\b"), 0),
]
WEEKDAY = re.compile(r"\b(" + "|".join(WEEKDAYS) + r")\b")

ADULT_WORDS = r"adultos?|adults?|personas?|people|persons?|guests?|huespedes?|pax"
CHILD_WORDS = r"ninos?|ninas?|children|child|kids?|menores?"
ADULTS = re.compile(rf"\b({_NUM})\s*(?:{ADULT_WORDS})\b")
WE_ARE = re.compile(rf"\b(?:somos|we\s+are)\s+({_NUM})\b")
CHILDREN = re.compile(rf"\b({_NUM})\s*(?:{CHILD_WORDS})\b")
RESERVATION_CODE = re.compile(r"\bHT-[0-9A-Z]{6}\b", re.IGNORECASE)
ROOM = re.compile(
    r"\b(?:habitacion|hab\.?|room|cuarto|la)\s*(?:numero\s*|no\.?\s*|#\s*)?([a-z]?\d{1,4}[a-z]?)\b"
)


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def norm(text: str) -> str:
    """Lowercase, no accents, single spaces; "check in"/"check-in" → "checkin"."""
    value = strip_accents((text or "").lower())
    value = re.sub(r"\bcheck[\s-]?in\b", "checkin", value)
    value = re.sub(r"\bcheck[\s-]?out\b", "checkout", value)
    return re.sub(r"\s+", " ", value).strip()


def to_int(token: str) -> int | None:
    token = token.strip()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


# ---- dates ------------------------------------------------------------------------------------------------


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _future(month: int, day: int, today: date) -> date | None:
    """Month/day without a year: this year, or next year if it already passed."""
    found = _safe_date(today.year, month, day)
    if found is not None and found < today:
        found = _safe_date(today.year + 1, month, day)
    return found


def _mask(text: str, match: re.Match) -> str:
    return text[: match.start()] + " " * (match.end() - match.start()) + text[match.end() :]


def _mentions(text: str, today: date) -> tuple[list[tuple[int, date]], bool]:
    """Dates mentioned in `text` with their positions; the flag says a range was inverted (invalid)."""
    found: list[tuple[int, date]] = []
    invalid = False

    def scan(pattern, build):
        nonlocal text, invalid
        for match in list(pattern.finditer(text)):
            dates = build(match)
            if dates is None:
                invalid = True
            else:
                found.extend((match.start() + offset, value) for offset, value in enumerate(dates) if value)
            text = _mask(text, match)

    def iso(m):
        return [_safe_date(int(m[1]), int(m[2]), int(m[3]))]

    def numeric(m):
        year = int(m[3]) if m[3] else None
        if year is not None and year < 100:
            year += 2000
        day, month = int(m[1]), int(m[2])
        return [_safe_date(year, month, day) if year else _future(month, day, today)]

    def day_range(m, first_day, second_day, month):
        if first_day > second_day:
            if first_day >= 25 and second_day <= 7:  # "del 30 al 2 de noviembre"
                start_month = month - 1 or 12
                start = _future(start_month, first_day, today)
                end = _future(month, second_day, today)
                return [start, end]
            return None
        return [_future(month, first_day, today), _future(month, second_day, today)]

    scan(ISO_DATE, iso)
    scan(NUMERIC_DATE, numeric)
    scan(RANGE_DAY_FIRST, lambda m: day_range(m, int(m[1]), int(m[2]), MONTHS[m[3]]))
    scan(RANGE_MONTH_FIRST, lambda m: day_range(m, int(m[2]), int(m[3]), MONTHS[m[1]]))
    scan(DAY_MONTH, lambda m: [_future(MONTHS[m[2]], int(m[1]), today)])
    scan(MONTH_DAY, lambda m: [_future(MONTHS[m[1]], int(m[2]), today)])
    for pattern, days in RELATIVE:
        scan(pattern, lambda m, days=days: [today + timedelta(days=days)])
    scan(WEEKDAY, lambda m: [today + timedelta(days=(WEEKDAYS[m[1]] - today.weekday()) % 7)])
    found.sort(key=lambda item: item[0])
    return found, invalid


def _weekend(today: date) -> tuple[date, date]:
    if today.weekday() == 5:  # Saturday: tonight
        return today, today + timedelta(days=1)
    friday = today + timedelta(days=(4 - today.weekday()) % 7)
    return friday, friday + timedelta(days=2)


def stay_dates(text: str, today: date) -> tuple[date, date] | None:
    """(checkin, checkout) mentioned in `text`, or None (nothing found, or an inverted range)."""
    value = norm(text)
    weekend = WEEKEND.search(value)
    if weekend:
        value = _mask(value, weekend)
    nights_match = NIGHTS.search(value)
    nights = to_int(nights_match[1]) if nights_match else None
    if nights_match:
        value = _mask(value, nights_match)
    mentions, invalid = _mentions(value, today)
    if invalid:
        return None
    dates = []
    for _, found in mentions:
        if found not in dates:
            dates.append(found)
    if not dates:
        return _weekend(today) if weekend else None
    checkin = dates[0]
    if len(dates) >= 2:
        checkout = dates[1]
        if checkout <= checkin:
            later = _safe_date(checkout.year + 1, checkout.month, checkout.day)
            checkout = later if later and later > checkin and (later - checkin).days <= 60 else checkout
        return (checkin, checkout) if checkout > checkin else None
    return checkin, checkin + timedelta(days=max(1, nights or 1))


# ---- party, codes, rooms ------------------------------------------------------------------------------


def party(text: str) -> tuple[int | None, int]:
    """(adults or None, children) mentioned in `text`."""
    value = norm(text)
    adults_match = ADULTS.search(value) or WE_ARE.search(value)
    children_match = CHILDREN.search(value)
    adults = to_int(adults_match[1]) if adults_match else None
    children = to_int(children_match[1]) if children_match else 0
    return adults, children or 0


def reservation_codes(text: str) -> list[str]:
    codes = []
    for match in RESERVATION_CODE.finditer(text or ""):
        code = match.group(0).upper()
        if code not in codes:
            codes.append(code)
    return codes


def room_number(text: str) -> str | None:
    match = ROOM.search(norm(text))
    return match[1].upper() if match else None


# ---- language -----------------------------------------------------------------------------------------

SPANISH_WORDS = set(
    "el la los las de del que hay para por con una un tienen tiene habitacion habitaciones reserva hola "
    "cuantas cuantos llegadas salidas gracias buenos buenas dias noches quiero necesito puedo donde cuando "
    "como mi mis es son esta estan hoy manana semana precio saldo y disponibilidad huespedes ocupacion "
    "mueve bloquea haz crea".split()
)
ENGLISH_WORDS = set(
    "the a an is are do does you your have has room rooms hello hi how what when where which can could would "
    "please thanks thank available availability for from to on and night nights today tomorrow weekend price "
    "balance arrivals departures guests i my me we any there occupancy move block create book".split()
)


def language(text: str, default: str = "es") -> str:
    if not text:
        return default
    words = re.findall(r"[a-z]+", norm(text))
    spanish = sum(word in SPANISH_WORDS for word in words) + 2 * len(re.findall(r"[¿¡ñáéíóú]", text.lower()))
    english = sum(word in ENGLISH_WORDS for word in words)
    if spanish == english:
        return default
    return "es" if spanish > english else "en"


# ---- extractive answers ------------------------------------------------------------------------------

STOPWORDS = set(
    "a al algo algun alguna ante con como cual cuales cuando de del desde donde el ella en entre es esta "
    "estan este esto hay la las le lo los me mi mis muy no nos o para pero por puedo puede pueden que quiero "
    "se si sin sobre son su sus tambien te tengo tiene tienen tu un una uno unos y ya hola gracias favor "
    "usted ustedes the an and are can could do does for from have has how i in is it my of on or please to "
    "we what when where which will with would you your hello hi thanks there be get hotel hostal habitacion "
    "habitaciones room rooms".split()
)
SYNONYMS = {
    "parking": "parqueadero parqueaderos parqueo estacionamiento garaje carro carros vehiculo vehiculos "
    "parking car",
    "pets": "mascota mascotas perro perros gato gatos animal animales pet pets dog dogs cat cats",
    "breakfast": "desayuno desayunos breakfast",
    "wifi": "wifi internet wi-fi",
    "pool": "piscina piscinas pool",
    "location": "llegar llego llegamos ubicacion ubicados ubicado ubicada direccion address located location "
    "directions mapa",
    "hours": "hora horas horario horarios schedule time",
    "airport": "aeropuerto traslado traslados transfer transfers airport shuttle",
    "checkin": "checkin entrada",
    "checkout": "checkout salida",
    "price": "precio precios tarifa tarifas costo cuesta vale price prices rate rates cost",
    "cancel": "cancelar cancelacion cancellation cancel reembolso refund",
    "children": "nino ninos ninas menores children child kids",
}
_CONCEPT = {word: concept for concept, words in SYNONYMS.items() for word in words.split()}


def _keys(text: str) -> set[str]:
    keys = set()
    for word in re.findall(r"[a-z0-9-]+", norm(text)):
        if word in STOPWORDS or len(word) < 3:
            continue
        if word in _CONCEPT:
            keys.add(_CONCEPT[word])
            continue
        stem = (
            word[:-2]
            if word.endswith("es") and len(word) > 5
            else word[:-1]
            if word.endswith("s") and len(word) > 4
            else word
        )
        keys.add(_CONCEPT.get(stem, stem))
    return keys


def best_answer(question: str, lines: list[str]) -> str | None:
    """The answer of the knowledge line that best matches `question` ("question → answer" lines give the
    answer; other lines are returned whole), or None when nothing matches. A match in the question of a FAQ
    counts double: "¿Tienen parqueadero?" answers with the parking FAQ, not with the list of extras that
    also mentions parking."""
    wanted = _keys(question)
    if not wanted:
        return None
    best, best_score = None, 0
    for line in lines:
        head, arrow, answer = line.partition("→")
        if arrow:
            score = 2 * len(wanted & _keys(head)) + len(wanted & _keys(answer))
        else:
            score = len(wanted & _keys(line))
        if score > best_score:
            best, best_score = (answer.strip() if arrow else line.strip()), score
    return best


# ---- formatting ---------------------------------------------------------------------------------------

MONTH_NAMES = {
    "es": [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ],
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
}


def format_date(value, lang: str = "es") -> str:
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return value
    names = MONTH_NAMES["en" if lang == "en" else "es"]
    if lang == "en":
        return f"{names[value.month - 1]} {value.day}"
    return f"{value.day} de {names[value.month - 1]}"


def format_money(value, currency: str = "COP") -> str:
    """`$ 761.600` (COP without decimals, dots as thousands separators, like the frontend)."""
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if currency == "COP":
        return "$\u00a0" + f"{amount:,.0f}".replace(",", ".")
    return f"{currency} {amount:,.2f}"
