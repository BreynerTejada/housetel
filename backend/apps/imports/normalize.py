"""Cell parsers of the importer: dates, numbers, money, countries, document types, statuses, names...

Every parser receives the cell text (already trimmed) and returns the normalized value or raises
`ValueError`; the validator turns that into a row issue. They never touch the database.
"""

import hashlib
import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.core.money import quantize
from apps.imports.catalog import fold

# ---- Dates --------------------------------------------------------------------------------------------

MONTHS = {
    # Spanish
    "ene": 1, "enero": 1, "feb": 2, "febrero": 2, "mar": 3, "marzo": 3, "abr": 4, "abril": 4, "may": 5,
    "mayo": 5, "jun": 6, "junio": 6, "jul": 7, "julio": 7, "ago": 8, "agosto": 8, "sep": 9, "sept": 9,
    "septiembre": 9, "setiembre": 9, "oct": 10, "octubre": 10, "nov": 11, "noviembre": 11, "dic": 12,
    "diciembre": 12,
    # English
    "jan": 1, "january": 1, "february": 2, "march": 3, "apr": 4, "april": 4, "june": 6, "july": 7,
    "aug": 8, "august": 8, "september": 9, "october": 10, "november": 11, "dec": 12, "december": 12,
}  # fmt: skip

_ISO = re.compile(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:[ T].*)?$")
_NUMERIC = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2}|\d{4})(?:[ T,].*)?$")
_EXCEL_SERIAL = re.compile(r"^\d{5}(?:\.\d+)?$")
EXCEL_EPOCH = date(1899, 12, 30)


def numeric_date_parts(text: str) -> tuple[int, int] | None:
    """(a, b) of an "a/b/yyyy" date, used to detect whether a column is day-first or month-first."""
    match = _NUMERIC.match((text or "").strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def detect_date_format(values: list[str]) -> tuple[str, bool]:
    """(`dmy` | `mdy`, ambiguous) for the numeric dates of a column: a first part above 12 means day-first, a
    second part above 12 means month-first; none of them → ambiguous (day-first, the Colombian default)."""
    day_first = month_first = False
    for value in values:
        parts = numeric_date_parts(value)
        if parts is None:
            continue
        first, second = parts
        if first > 12 >= second:
            day_first = True
        elif second > 12 >= first:
            month_first = True
    if month_first and not day_first:
        return "mdy", False
    if day_first:
        return "dmy", False
    return "dmy", True


def _year(value: str) -> int:
    year = int(value)
    return year + 2000 if year < 100 else year


def parse_date(text: str, fmt: str = "dmy") -> date:
    """ISO (2026-10-05, 2026/10/05, with or without time), numeric (05/10/2026 as `fmt` says: dmy or mdy;
    two-digit years are 20xx), with month names (5 oct 2026, 5 de octubre de 2026, Oct 5, 2026) or an Excel
    serial number (46300)."""
    value = (text or "").strip()
    if not value:
        raise ValueError("empty")
    match = _ISO.match(value)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = _NUMERIC.match(value)
    if match:
        first, second, year = int(match.group(1)), int(match.group(2)), _year(match.group(3))
        if fmt == "mdy":
            return date(year, first, second)
        if fmt == "ymd":  # "26/10/05" is not a sensible ymd: read it as dmy
            return date(year, second, first)
        return date(year, second, first)
    if _EXCEL_SERIAL.match(value):
        serial = int(float(value))
        if 20000 <= serial <= 80000:  # 1954 … 2119
            return EXCEL_EPOCH + timedelta(days=serial)
    words = re.findall(r"[a-záéíóúñ]+|\d+", value.lower())
    words = [word for word in words if word not in ("de", "del", "of", "the")]
    numbers = [int(word) for word in words if word.isdigit()]
    months = [MONTHS[fold(word)] for word in words if not word.isdigit() and fold(word) in MONTHS]
    if months and len(numbers) >= 2:
        year = next((n for n in numbers if n > 31), None)
        day = next((n for n in numbers if n <= 31), None)
        if year is not None and day is not None:
            return date(_year(str(year)), months[0], day)
    raise ValueError(value)


def parse_time(text: str) -> time:
    """ "21:30", "9:30 pm", "21h30", "2130" → time."""
    value = fold(text).replace(" ", "")
    match = re.match(r"^(\d{1,2})(?:[:h]?(\d{2}))?(?::\d{2})?(am|pm|a|p)?$", value.replace(".", ""))
    if not match:
        raise ValueError(text)
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    suffix = match.group(3)
    if suffix in ("pm", "p") and hour < 12:
        hour += 12
    if suffix in ("am", "a") and hour == 12:
        hour = 0
    return time(hour, minute)


# ---- Numbers and money --------------------------------------------------------------------------------


def _decimal_text(text: str) -> str:
    """Canonical number text from "1.160.500", "1,160,500.00", "$ 1.160.500,50", "(1.000)", "-45 000"."""
    value = (text or "").strip()
    negative = value.startswith("-") or (value.startswith("(") and value.endswith(")"))
    value = re.sub(r"[^0-9.,]", "", value)
    if not value or not re.search(r"\d", value):
        raise ValueError(text)
    dots, commas = value.count("."), value.count(",")
    if dots and commas:
        decimal_sep = "." if value.rfind(".") > value.rfind(",") else ","
        thousands = "," if decimal_sep == "." else "."
        value = value.replace(thousands, "").replace(decimal_sep, ".")
    elif dots or commas:
        sep = "." if dots else ","
        count = dots or commas
        tail = value.rsplit(sep, 1)[1]
        # "1.160.500" (several) or "1.500" (three digits after one separator) are thousands
        if count > 1 or len(tail) == 3:
            value = value.replace(sep, "")
        else:
            value = value.replace(sep, ".")
    return f"-{value}" if negative else value


def parse_decimal(text: str) -> Decimal:
    try:
        number = Decimal(_decimal_text(text))
    except (InvalidOperation, ValueError):
        raise ValueError(text) from None
    if not number.is_finite():
        raise ValueError(text)
    return number


def parse_money(text: str, currency: str = "COP") -> Decimal:
    return quantize(parse_decimal(text), currency)


def parse_int(text: str) -> int:
    number = parse_decimal(text)
    if number != number.to_integral_value():
        raise ValueError(text)
    return int(number)


# ---- People --------------------------------------------------------------------------------------------


def split_full_name(text: str) -> tuple[str, str]:
    """ "Pérez Gómez, Ana María" → ("Ana María", "Pérez Gómez"); "Ana Pérez" → ("Ana", "Pérez");
    "Ana Pérez Gómez" → ("Ana", "Pérez Gómez"); four or more words → two first names."""
    value = " ".join((text or "").split())
    if "," in value:
        last, first = (part.strip() for part in value.split(",", 1))
        return (first or last, last if first else "")
    words = value.split(" ")
    if len(words) <= 1:
        return value, ""
    if len(words) <= 3:
        return words[0], " ".join(words[1:])
    return " ".join(words[:2]), " ".join(words[2:])


def clean_email(text: str) -> str:
    value = (text or "").strip().lower()
    if value.startswith("mailto:"):
        value = value[7:]
    validate_email(value)  # ValidationError → caller
    return value


def is_valid_email(text: str) -> bool:
    try:
        clean_email(text)
    except ValidationError:
        return False
    return True


DOCUMENT_TYPES = {
    "CC": ("cc", "c c", "cedula", "cedula de ciudadania", "cedula ciudadania", "ciudadania",
           "cedula colombiana"),
    "CE": ("ce", "c e", "cedula de extranjeria", "cedula extranjeria", "extranjeria", "foreigner id"),
    "PA": ("pa", "pp", "pas", "pasaporte", "passport", "pasaporte extranjero"),
    "TI": ("ti", "t i", "tarjeta de identidad", "tarjeta identidad"),
    "PEP": ("pep", "permiso especial de permanencia"),
    "PPT": ("ppt", "permiso por proteccion temporal", "permiso de proteccion temporal"),
    "DNI": ("dni", "documento nacional de identidad", "national id", "id card", "national identity card",
            "ine",
            "cedula de identidad", "ci", "rut", "curp"),
    "NIT": ("nit",),
    "OTHER": ("otro", "other", "id", "identificacion", "identification", "licencia", "licencia de conduccion",
              "driver license", "drivers license", "driving licence"),
}  # fmt: skip
_DOCUMENT_LOOKUP = {alias: code for code, aliases in DOCUMENT_TYPES.items() for alias in aliases}


def parse_document_type(text: str) -> str:
    key = fold(text)
    if key.upper() in DOCUMENT_TYPES:
        return key.upper()
    if key in _DOCUMENT_LOOKUP:
        return _DOCUMENT_LOOKUP[key]
    raise ValueError(text)


GENDERS = {
    "F": ("f", "femenino", "female", "mujer", "woman", "fem", "femenina"),
    "M": ("m", "masculino", "male", "hombre", "man", "masc"),
    "X": ("x", "otro", "other", "no binario", "non binary", "nonbinary", "prefiero no decir", "n a"),
}
_GENDER_LOOKUP = {alias: code for code, aliases in GENDERS.items() for alias in aliases}


def parse_gender(text: str) -> str:
    key = fold(text)
    if key in _GENDER_LOOKUP:
        return _GENDER_LOOKUP[key]
    raise ValueError(text)


SPANISH_WORDS = ("es", "esp", "espanol", "spanish", "castellano", "es co", "es es", "es mx", "es_co")
OTHER_LANGUAGES = (
    "en",
    "eng",
    "ingles",
    "english",
    "en us",
    "en gb",
    "pt",
    "portugues",
    "portuguese",
    "fr",
    "frances",
    "french",
    "de",
    "aleman",
    "german",
    "it",
    "italiano",
    "italian",
    "nl",
    "holandes",
    "dutch",
)


def parse_language(text: str) -> str:
    """Housetel talks to guests in Spanish or English: Spanish variants → es, other known languages → en."""
    key = fold(text)
    if key in SPANISH_WORDS or key.startswith("es "):
        return "es"
    if key in OTHER_LANGUAGES or key[:3] in ("en ", "pt ", "fr ", "de ", "it "):
        return "en"
    raise ValueError(text)


SPANISH_SPEAKING = frozenset({
    "CO", "MX", "AR", "CL", "PE", "EC", "VE", "BO", "PY", "UY", "CR", "PA", "GT", "HN", "SV", "NI", "DO",
    "CU", "PR", "ES", "GQ",
})  # fmt: skip


def default_language(nationality: str, residence: str) -> str:
    country = nationality or residence
    return "en" if country and country not in SPANISH_SPEAKING else "es"


# ---- Countries -----------------------------------------------------------------------------------------

ISO3 = {
    "COL": "CO", "USA": "US", "MEX": "MX", "ARG": "AR", "BRA": "BR", "CHL": "CL", "PER": "PE", "ECU": "EC",
    "VEN": "VE", "ESP": "ES", "FRA": "FR", "DEU": "DE", "GBR": "GB", "ITA": "IT", "CAN": "CA", "PAN": "PA",
    "CRI": "CR", "URY": "UY", "PRY": "PY", "BOL": "BO", "DOM": "DO", "NLD": "NL", "CHE": "CH", "BEL": "BE",
    "PRT": "PT", "AUT": "AT", "SWE": "SE", "NOR": "NO", "DNK": "DK", "FIN": "FI", "IRL": "IE", "POL": "PL",
    "RUS": "RU", "ISR": "IL", "CHN": "CN", "JPN": "JP", "KOR": "KR", "IND": "IN", "AUS": "AU", "NZL": "NZ",
    "GTM": "GT", "HND": "HN", "SLV": "SV", "NIC": "NI", "CUB": "CU", "PRI": "PR", "TUR": "TR", "ZAF": "ZA",
}  # fmt: skip

COUNTRY_ALIASES = {
    "usa": "US", "u s a": "US", "u s": "US", "eeuu": "US", "ee uu": "US", "estados unidos de america": "US",
    "united states of america": "US", "america": "US", "uk": "GB", "u k": "GB", "england": "GB",
    "inglaterra": "GB", "scotland": "GB", "escocia": "GB", "wales": "GB", "gales": "GB",
    "great britain": "GB",
    "gran bretana": "GB", "britain": "GB", "holanda": "NL", "the netherlands": "NL", "netherlands": "NL",
    "paises bajos": "NL", "corea": "KR", "corea del sur": "KR", "south korea": "KR", "korea": "KR",
    "republica checa": "CZ", "czechia": "CZ", "czech republic": "CZ", "rusia": "RU", "russia": "RU",
    "republica dominicana": "DO", "dominican republic": "DO", "emiratos arabes unidos": "AE", "uae": "AE",
    "suiza": "CH", "switzerland": "CH", "vietnam": "VN", "viet nam": "VN",
}  # fmt: skip

# Nationalities written as demonyms ("Colombiana", "American"): the most frequent guests of a Colombian hotel.
DEMONYMS = {
    "CO": ("colombiano", "colombiana", "colombian"), "US": ("estadounidense", "americano", "americana",
    "norteamericano", "norteamericana", "american"), "MX": ("mexicano", "mexicana", "mexican"),
    "AR": ("argentino", "argentina", "argentinian", "argentine"), "BR": ("brasileno", "brasilena",
    "brasilero", "brasilera", "brazilian"), "CL": ("chileno", "chilena", "chilean"), "PE": ("peruano",
    "peruana", "peruvian"), "EC": ("ecuatoriano", "ecuatoriana", "ecuadorian"), "VE": ("venezolano",
    "venezolana", "venezuelan"), "ES": ("espanol", "espanola", "spanish", "spaniard"), "FR": ("frances",
    "francesa", "french"), "DE": ("aleman", "alemana", "german"), "GB": ("britanico", "britanica", "ingles",
    "inglesa", "british", "english"), "IT": ("italiano", "italiana", "italian"), "CA": ("canadiense",
    "canadian"), "PA": ("panameno", "panamena", "panamanian"), "CR": ("costarricense", "costa rican"),
    "UY": ("uruguayo", "uruguaya", "uruguayan"), "PY": ("paraguayo", "paraguaya", "paraguayan"),
    "BO": ("boliviano", "boliviana", "bolivian"), "DO": ("dominicano", "dominicana", "dominican"),
    "NL": ("holandes", "holandesa", "neerlandes", "neerlandesa", "dutch"), "CH": ("suizo", "suiza", "swiss"),
    "PT": ("portugues", "portuguesa", "portuguese"), "CN": ("chino", "china", "chinese"), "JP": ("japones",
    "japonesa", "japanese"), "KR": ("coreano", "coreana", "korean"), "AU": ("australiano", "australiana",
    "australian"), "IL": ("israeli", "israelita"), "CU": ("cubano", "cubana", "cuban"), "GT": ("guatemalteco",
    "guatemalteca", "guatemalan"), "SV": ("salvadoreno", "salvadorena", "salvadoran"), "HN": ("hondureno",
    "hondurena", "honduran"), "NI": ("nicaraguense", "nicaraguan"), "BE": ("belga", "belgian"),
    "SE": ("sueco", "sueca", "swedish"), "NO": ("noruego", "noruega", "norwegian"), "DK": ("danes", "danesa",
    "danish"), "IE": ("irlandes", "irlandesa", "irish"), "PL": ("polaco", "polaca", "polish"),
    "RU": ("ruso", "rusa", "russian"), "AT": ("austriaco", "austriaca", "austrian"), "IN": ("indio", "india",
    "hindu", "indian"),
}  # fmt: skip

_COUNTRY_LOOKUP: dict[str, str] | None = None


def _country_lookup() -> dict[str, str]:
    """Folded country name → ISO-2 from the phonenumbers locale data (names in es, en, pt, fr, de, it for
    every region) plus ISO-3 codes, aliases and demonyms."""
    global _COUNTRY_LOOKUP
    if _COUNTRY_LOOKUP is not None:
        return _COUNTRY_LOOKUP
    lookup: dict[str, str] = {}
    try:
        from phonenumbers.geodata.locale import LOCALE_DATA
    except ImportError:  # pragma: no cover - phonenumbers always ships it
        LOCALE_DATA = {}
    for code, names in LOCALE_DATA.items():
        if len(code) != 2 or not code.isalpha():
            continue
        for lang in ("es", "en", "pt", "fr", "de", "it", "aa"):
            name = names.get(lang, "")
            if name.startswith("*"):
                name = names.get(name[1:], "")
            if name:
                lookup.setdefault(fold(name), code)
    for iso3, code in ISO3.items():
        lookup[fold(iso3)] = code
    for alias, code in COUNTRY_ALIASES.items():
        lookup[fold(alias)] = code
    for code, words in DEMONYMS.items():
        for word in words:
            lookup.setdefault(fold(word), code)
    _COUNTRY_LOOKUP = lookup
    return lookup


def valid_country_codes() -> frozenset[str]:
    import phonenumbers

    return frozenset(phonenumbers.SUPPORTED_REGIONS) | {"XK"}


def parse_country(text: str) -> str:
    """ISO 3166-1 alpha-2 from a code ("co", "COL") or a name in es/en/pt/fr/de/it ("Estados Unidos",
    "Alemania", "Brasil", "Deutschland") or a demonym ("colombiana", "American")."""
    value = (text or "").strip()
    if len(value) == 2 and value.isalpha() and value.upper() in valid_country_codes():
        return value.upper()
    key = fold(value)
    code = _country_lookup().get(key)
    if code:
        return code
    raise ValueError(text)


# ---- Reservation statuses ------------------------------------------------------------------------------

STATUSES = {
    "confirmed": ("confirmed", "confirmada", "confirmado", "reservada", "reservado", "reserved", "booked",
                  "garantizada", "guaranteed", "activa", "active", "nueva", "new"),
    "tentative": ("not confirmed", "not_confirmed", "no confirmada", "no confirmado", "sin confirmar",
                  "unconfirmed", "tentativa", "tentativo", "tentative", "pendiente", "pending", "hold",
                  "en espera", "provisional", "option", "opcion"),
    "in_house": ("checked in", "checked_in", "check in", "checkin", "in house", "inhouse", "en casa",
                 "hospedado", "hospedada", "alojado", "alojada", "registrado", "registrada", "en curso",
                 "in progress", "ocupada", "arrived", "llego"),
    "checked_out": ("checked out", "checked_out", "check out", "checkout", "finalizada", "finalizado",
                    "completada", "completado", "completed", "departed", "salio", "cerrada", "closed"),
    "cancelled": ("cancelled", "canceled", "cancelada", "cancelado", "anulada", "anulado", "void", "voided",
                  "annulled"),
    "no_show": ("no show", "no_show", "noshow", "no se presento", "no llego", "ausente", "no presentado"),
}  # fmt: skip
_STATUS_LOOKUP = {fold(alias): code for code, aliases in STATUSES.items() for alias in aliases}


def parse_status(text: str) -> str:
    key = fold(text)
    if key in _STATUS_LOOKUP:
        return _STATUS_LOOKUP[key]
    raise ValueError(text)


ROOM_KINDS = {
    "private": ("private", "privada", "privado", "habitacion", "room", "habitacion privada", "suite",
                "standard", "estandar"),
    "dorm": ("dorm", "dormitorio", "dormitory", "compartida", "compartido", "shared", "cama", "bed",
             "hostel", "hostal", "venta por cama", "por cama", "mixto", "mixed dorm", "shared room"),
}  # fmt: skip
_KIND_LOOKUP = {fold(alias): code for code, aliases in ROOM_KINDS.items() for alias in aliases}


def parse_room_kind(text: str) -> str:
    key = fold(text)
    if key in _KIND_LOOKUP:
        return _KIND_LOOKUP[key]
    raise ValueError(text)


# ---- Misc ----------------------------------------------------------------------------------------------


def fingerprint(*parts) -> str:
    """Stable id for a row without an external id (same guest, dates and category → same id)."""
    text = "|".join(fold(part) for part in parts)
    return "fp-" + hashlib.sha1(text.encode()).hexdigest()[:16]  # noqa: S324 - not security related


def split_list(text: str) -> list[str]:
    """ "Doble, Twin" → ["Doble", "Twin"] (commas, semicolons and line breaks; a slash may be part of a
    name: "Doble/Twin")."""
    return [part.strip() for part in re.split(r"[,;\n]+", text or "") if part.strip()]


def to_iso(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)
