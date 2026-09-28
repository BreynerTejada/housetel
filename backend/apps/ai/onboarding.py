"""AI-assisted onboarding (plan C9).

`propose(property, description, website_url)`: reads the hotel's website (httpx, 8 s, public addresses only,
no scripts, at most 20 000 characters), asks the model for a structured proposal (`response_schema`
"onboarding_proposal"; offline, the heuristics below read numbers and keywords from the description) and
normalizes it into something the review screen can edit and `apply` can create:

    {"property": {name, description{es,en}, city, address, phone, email, star_rating, check_in_time,
                  check_out_time, amenities[codes]},
     "room_types": [{code, name{es,en}, kind, base_occupancy, max_adults, max_children, max_occupancy,
                     beds[{type,count}], beds_per_room, size_m2, amenities[codes], units, room_numbers[],
                     base_price, weekend_adjust_percent, extra_adult_price, extra_child_price}],
     "policies": {non_refundable_discount_percent, breakfast_price, pets_allowed, smoking_allowed,
                  children_allowed},
     "extras": [{code, name{es,en}, price, charge_type}]}

`apply_proposal(property, proposal, actor)`: validates it again and creates everything in one transaction
with the contract services (`inventory.provision_room_type`, `rates.provision_rates`), the profile through
inventory's profile service and the extras through the rates API serializer. Any error rolls back all of it.
"""

from __future__ import annotations

import html
import ipaddress
import logging
import re
import socket
import unicodedata
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from types import SimpleNamespace
from urllib.parse import urljoin, urlsplit

import httpx
from django.db import transaction

from apps.ai import nlp
from apps.ai.llm import llm_for
from apps.ai.simulated import register_structured
from apps.core.errors import DomainError

logger = logging.getLogger("housetel.ai")

WEBSITE_TIMEOUT_SECONDS = 8
WEBSITE_MAX_CHARS = 20_000
WEBSITE_MAX_BYTES = 2_000_000
WEBSITE_MAX_REDIRECTS = 3
ONBOARDING_LLM_TIMEOUT = 60

MAX_ROOM_TYPES = 20
MAX_UNITS = 200
BED_TYPES = ("single", "twin", "double", "queen", "king", "bunk", "sofa_bed", "crib")
BED_SYNONYMS = {
    "sencilla": "single",
    "individual": "single",
    "doble": "double",
    "matrimonial": "double",
    "camarote": "bunk",
    "litera": "bunk",
    "sofa cama": "sofa_bed",
    "sofa-cama": "sofa_bed",
    "sofacama": "sofa_bed",
    "cuna": "crib",
    "reina": "queen",
    "rey": "king",
}
BED_CAPACITY = {
    "single": 1,
    "twin": 1,
    "double": 2,
    "queen": 2,
    "king": 2,
    "bunk": 2,
    "sofa_bed": 1,
    "crib": 0,
}
CHARGE_TYPES = ("per_stay", "per_night", "per_person", "per_person_night")
DEFAULT_PRICE = {"private": Decimal("250000"), "dorm": Decimal("60000")}
DEFAULT_NR_DISCOUNT = 12
STOPWORDS = {"DE", "DEL", "LA", "EL", "LAS", "LOS", "AL", "CON", "Y", "EN", "THE", "OF", "WITH", "AND"}
TIME = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(a\.?\s?m\.?|p\.?\s?m\.?)?\s*$", re.I)


# ---- website -----------------------------------------------------------------------------------------------


def resolve_host(host: str) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})


def _public_host(host: str) -> bool:
    try:
        addresses = resolve_host(host)
    except (OSError, UnicodeError):
        return False
    try:
        return bool(addresses) and all(ipaddress.ip_address(address).is_global for address in addresses)
    except ValueError:
        return False


HIDDEN_BLOCKS = re.compile(r"<(script|style|noscript|svg|template|iframe|head)\b.*?</\1\s*>", re.I | re.S)
TITLE = re.compile(r"<title[^>]*>(.*?)</title\s*>", re.I | re.S)
META_DESCRIPTION = re.compile(
    r"<meta[^>]+name=[\"'](?:description|og:description)[\"'][^>]*content=[\"']([^\"']*)[\"']", re.I
)
TAG = re.compile(r"<[^>]+>")
COMMENT = re.compile(r"<!--.*?-->", re.S)


def html_to_text(markup: str) -> str:
    title = TITLE.search(markup)
    meta = META_DESCRIPTION.search(markup)
    body = HIDDEN_BLOCKS.sub(" ", COMMENT.sub(" ", markup))
    body = re.sub(r"<(br|p|div|li|h[1-6]|tr|section|article)\b[^>]*>", "\n", body, flags=re.I)
    text = html.unescape(TAG.sub(" ", body)).replace("\xa0", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    parts = [html.unescape(title[1]).strip() if title else "", html.unescape(meta[1]).strip() if meta else ""]
    return "\n".join(part for part in [*parts, *lines] if part)


def fetch_website_text(url: str) -> dict:
    """`{"url", "fetched", "text", "chars", "error"}`; never raises (the proposal works without the site)."""
    result = {"url": url, "fetched": False, "text": "", "chars": 0, "error": ""}
    current = (url or "").strip()
    try:
        with httpx.Client(
            timeout=WEBSITE_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"User-Agent": "HousetelOnboarding/1.0 (+https://housetel.co)"},
        ) as client:
            for _ in range(WEBSITE_MAX_REDIRECTS + 1):
                parts = urlsplit(current)
                if parts.scheme not in ("http", "https") or not parts.hostname:
                    result["error"] = "La dirección debe empezar por http:// o https://"
                    return result
                if not _public_host(parts.hostname):
                    result["error"] = "No se puede leer esa dirección (no es un sitio público)"
                    return result
                with client.stream("GET", current) as response:
                    if response.is_redirect and response.headers.get("location"):
                        current = urljoin(current, response.headers["location"])
                        continue
                    if response.status_code >= 400:
                        result["error"] = f"El sitio respondió {response.status_code}"
                        return result
                    kind = response.headers.get("content-type", "text/html")
                    if "html" not in kind and "text" not in kind:
                        result["error"] = "La dirección no es una página web"
                        return result
                    raw = b""
                    for chunk in response.iter_bytes():
                        raw += chunk
                        if len(raw) >= WEBSITE_MAX_BYTES:
                            break
                    encoding = response.encoding or "utf-8"
                text = html_to_text(raw.decode(encoding, errors="replace"))[:WEBSITE_MAX_CHARS]
                result.update(fetched=True, text=text, chars=len(text), url=current)
                return result
            result["error"] = "Demasiadas redirecciones"
    except httpx.HTTPError as exc:
        result["error"] = f"No se pudo leer el sitio ({type(exc).__name__})"
    return result


# ---- the model's answer ------------------------------------------------------------------------------------

_BED_ITEM = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"type": {"type": "string", "enum": list(BED_TYPES)}, "count": {"type": "integer"}},
    "required": ["type", "count"],
}
PROPOSAL_SCHEMA = {
    "title": "onboarding_proposal",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "property": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "name": {"type": "string"},
                "description_es": {"type": "string"},
                "description_en": {"type": "string"},
                "city": {"type": "string"},
                "address": {"type": "string"},
                "phone": {"type": "string"},
                "email": {"type": "string"},
                "star_rating": {"type": "integer"},
                "check_in_time": {"type": "string", "description": "HH:MM"},
                "check_out_time": {"type": "string", "description": "HH:MM"},
                "amenities": {"type": "array", "items": {"type": "string"}},
            },
        },
        "room_types": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "code": {"type": "string"},
                    "name_es": {"type": "string"},
                    "name_en": {"type": "string"},
                    "kind": {"type": "string", "enum": ["private", "dorm"]},
                    "units": {
                        "type": "integer",
                        "description": "Habitaciones (o dormitorios) de esta categoría",
                    },
                    "max_adults": {"type": "integer"},
                    "max_children": {"type": "integer"},
                    "max_occupancy": {"type": "integer"},
                    "beds": {"type": "array", "items": _BED_ITEM},
                    "size_m2": {"type": "number"},
                    "amenities": {"type": "array", "items": {"type": "string"}},
                    "base_price": {
                        "type": "number",
                        "description": "Precio por noche en COP (dorm: por cama)",
                    },
                    "weekend_adjust_percent": {"type": "number"},
                    "extra_adult_price": {"type": "number"},
                    "extra_child_price": {"type": "number"},
                },
                "required": ["name_es", "kind", "units", "base_price"],
            },
        },
        "policies": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "non_refundable_discount_percent": {"type": "number"},
                "breakfast_price": {"type": "number"},
                "pets_allowed": {"type": "boolean"},
                "smoking_allowed": {"type": "boolean"},
                "children_allowed": {"type": "boolean"},
            },
        },
        "extras": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "code": {"type": "string"},
                    "name_es": {"type": "string"},
                    "name_en": {"type": "string"},
                    "price": {"type": "number"},
                    "charge_type": {"type": "string", "enum": list(CHARGE_TYPES)},
                },
                "required": ["name_es", "price", "charge_type"],
            },
        },
    },
    "required": ["property", "room_types", "policies", "extras"],
}


def _catalog(prop) -> dict[str, str]:
    """Valid amenity codes → Spanish name (global catalog + the organization's own)."""
    from django.db.models import Q

    from apps.core.i18n import t
    from apps.inventory.models import Amenity

    amenities = Amenity.objects.filter(Q(organization__isnull=True) | Q(organization=prop.organization))
    return {amenity.code: t(amenity.name, "es") for amenity in amenities.order_by("code")}


def _system_prompt(catalog: dict[str, str]) -> str:
    codes = ", ".join(f"{code} ({name})" for code, name in catalog.items())
    return "\n".join(
        [
            "Eres el asistente de configuración de Housetel, un software para hoteles en Colombia.",
            "Con la descripción del hotel (y el texto de su sitio web, si viene) propone su configuración "
            "inicial.",
            "",
            "## Reglas",
            "- Categorías (room_types): una por tipo de habitación que se vende distinto (Estándar, Doble, "
            "Suite…). "
            'Para hostales, los dormitorios compartidos son kind "dorm" y se venden por cama (base_price por '
            "cama).",
            "- units = cuántas habitaciones (o dormitorios) de esa categoría tiene el hotel.",
            "- Precios en pesos colombianos (COP) por noche, sin decimales. Si no aparecen, estima precios "
            "razonables para la ciudad y el tipo de hotel.",
            f"- Tipos de cama válidos: {', '.join(BED_TYPES)}.",
            f"- Amenidades: usa solo estos códigos: {codes}.",
            "- check_in_time y check_out_time en formato HH:MM de 24 horas.",
            "- No inventes teléfonos, correos ni direcciones: déjalos vacíos si no aparecen.",
            "- Extras: servicios que se cobran aparte (desayuno, parqueadero, traslados…).",
        ]
    )


def _prompt(description: str, website_text: str) -> str:
    parts = ["## Descripción del hotel", description.strip() or "(sin descripción)"]
    if website_text:
        parts += ["", "## Texto del sitio web", website_text]
    return "\n".join(parts)


def propose(prop, *, description: str = "", website_url: str = "", llm=None) -> dict:
    """`{"proposal", "warnings", "simulated", "provider", "website"}`."""
    description = (description or "").strip()[:5000]
    website_url = (website_url or "").strip()
    if not description and not website_url:
        raise DomainError(
            "Describe tu hotel o escribe la dirección de su sitio web",
            code="validation_error",
            fields={"description": ["Describe tu hotel o escribe la dirección de su sitio web"]},
        )
    website = fetch_website_text(website_url) if website_url else None
    catalog = _catalog(prop)
    llm = llm or llm_for(prop, "onboarding", timeout=ONBOARDING_LLM_TIMEOUT)
    result = llm.generate(
        [{"role": "user", "content": _prompt(description, (website or {}).get("text", ""))}],
        system=_system_prompt(catalog),
        response_schema=PROPOSAL_SCHEMA,
        temperature=0.2,
    )
    raw = result.data if isinstance(result.data, dict) else None
    warnings = []
    if raw is None:
        raw = heuristic_proposal(description + "\n" + (website or {}).get("text", ""))
        warnings.append(
            "No obtuve una propuesta estructurada del modelo: armé una con lo que entendí del texto."
        )
    proposal, normalization_warnings = normalize_proposal(prop, raw, catalog=catalog)
    if website and not website["fetched"]:
        warnings.append(f"No pude leer el sitio web: {website['error']}")
    return {
        "proposal": proposal,
        "warnings": warnings + normalization_warnings,
        "simulated": bool(result.simulated),
        "provider": result.provider,
        "website": {key: value for key, value in (website or {}).items() if key != "text"} or None,
    }


# ---- normalization -----------------------------------------------------------------------------------------


def _ascii_upper(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    return "".join(char for char in normalized if not unicodedata.combining(char)).upper()


def _code_from_name(name: str) -> str:
    words = [word for word in re.findall(r"[A-Z0-9]+", _ascii_upper(name)) if word not in STOPWORDS]
    if not words:
        return "RT"
    if len(words) == 1:
        return words[0][:3]
    return "".join(word if word.isdigit() else word[0] for word in words)[:20]


def _sanitize_code(value) -> str:
    code = re.sub(r"[^A-Z0-9_-]+", "-", _ascii_upper(str(value or "").strip()))
    return code.strip("-_")[:20].rstrip("-_")


def _unique(base: str, taken: set[str]) -> str:
    base = base or "RT"
    if base not in taken:
        taken.add(base)
        return base
    for suffix in range(2, 1000):
        candidate = f"{base[: 20 - len(str(suffix))]}{suffix}"
        if candidate not in taken:
            taken.add(candidate)
            return candidate
    raise DomainError("No se pudo generar un código único", code="validation_error")


def _int(value, default=None, *, low=None, high=None):
    try:
        number = int(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return default
    if (low is not None and number < low) or (high is not None and number > high):
        return default
    return number


def _money(value) -> Decimal | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).replace("$", "").replace(" ", ""))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite():
        return None
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _bool(value, default):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("si", "sí", "yes", "true", "1"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("no", "false", "0"):
        return False
    return default


def normalize_time(value) -> str | None:
    if value in (None, ""):
        return None
    match = TIME.match(str(value))
    if not match:
        return None
    hour, minute, meridiem = int(match[1]), int(match[2] or 0), (match[3] or "").lower().replace(".", "")
    if meridiem.startswith("p") and hour < 12:
        hour += 12
    if meridiem.startswith("a") and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _i18n(item: dict, key: str) -> dict:
    """`{"es", "en"}` from `key` (dict) or from the flat `key_es`/`key_en` of the model's answer."""
    value = item.get(key)
    if isinstance(value, dict):
        es, en = str(value.get("es") or "").strip(), str(value.get("en") or "").strip()
    else:
        es = str(item.get(f"{key}_es") or (value if isinstance(value, str) else "") or "").strip()
        en = str(item.get(f"{key}_en") or "").strip()
    return {
        "es": es[:100] if key == "name" else es[:4000],
        "en": (en or es)[:100] if key == "name" else en[:4000],
    }


def _beds(raw) -> list[dict]:
    beds = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        kind = nlp.norm(str(item.get("type") or "")).replace("_", " ")
        kind = BED_SYNONYMS.get(kind, kind.replace(" ", "_"))
        if kind not in BED_TYPES:
            kind = "double"
        count = _int(item.get("count"), 1, low=1, high=20)
        existing = next((bed for bed in beds if bed["type"] == kind), None)
        if existing:
            existing["count"] = min(existing["count"] + count, 20)
        else:
            beds.append({"type": kind, "count": count})
    return beds[:10]


def _bed_capacity(beds) -> int:
    return sum(BED_CAPACITY[bed["type"]] * bed["count"] for bed in beds)


def _amenities(raw, catalog: dict, unknown: set) -> list[str]:
    codes = []
    for value in raw if isinstance(raw, list) else []:
        code = str(value or "").strip()
        if code in catalog:
            if code not in codes:
                codes.append(code)
        elif code:
            unknown.add(code)
    return codes


def _room_type(raw: dict, *, index: int, catalog: dict, unknown: set, warnings: list) -> dict:
    kind = "dorm" if str(raw.get("kind") or "").lower() in ("dorm", "dormitorio", "shared") else "private"
    name = _i18n(raw, "name")
    if not name["es"]:
        name = {"es": f"Categoría {index + 1}", "en": f"Room type {index + 1}"}
    beds = _beds(raw.get("beds"))
    if not beds:
        beds = [{"type": "bunk", "count": 3}] if kind == "dorm" else [{"type": "queen", "count": 1}]
    units = _int(raw.get("units"), 1, low=1, high=MAX_UNITS) or 1
    price = _money(raw.get("base_price"))
    if price is None or price <= 0:
        price = DEFAULT_PRICE[kind]
        warnings.append(
            f"«{name['es']}»: sin precio válido, usé {nlp.format_money(price)} por noche (ajústalo)."
        )
    item = {
        "code": raw.get("code") or "",
        "name": name,
        "kind": kind,
        "beds": beds,
        "size_m2": None,
        "amenities": _amenities(raw.get("amenities"), catalog, unknown),
        "units": units,
        "room_numbers": [
            str(number).strip()[:20] for number in raw.get("room_numbers") or [] if str(number).strip()
        ],
        "base_price": str(price),
        "weekend_adjust_percent": _int(raw.get("weekend_adjust_percent"), 0, low=-100, high=1000),
        "extra_adult_price": str(_money(raw.get("extra_adult_price")) or 0) if kind == "private" else "0",
        "extra_child_price": str(_money(raw.get("extra_child_price")) or 0) if kind == "private" else "0",
    }
    size = _money(raw.get("size_m2"))
    if size is not None and 1 <= size <= 1000:
        item["size_m2"] = int(size)
    if kind == "dorm":
        item.update(
            base_occupancy=1,
            max_adults=1,
            max_children=0,
            max_occupancy=1,
            beds_per_room=max(1, _bed_capacity(beds)),
        )
    else:
        capacity = max(1, _bed_capacity(beds))
        maximum = _int(raw.get("max_occupancy"), capacity, low=1, high=20)
        adults = _int(raw.get("max_adults"), min(maximum, max(capacity, 1)), low=1, high=maximum)
        children = _int(raw.get("max_children"), max(0, maximum - 1), low=0, high=max(0, maximum - 1))
        base = _int(raw.get("base_occupancy"), min(2, adults), low=1, high=adults)
        item.update(
            base_occupancy=base,
            max_adults=adults,
            max_children=children,
            max_occupancy=maximum,
            beds_per_room=None,
        )
    return item


def _generate_numbers(index: int, item: dict, used: set[str]) -> list[str]:
    numbers = []
    if item["kind"] == "dorm":
        counter = 1
        while len(numbers) < item["units"]:
            candidate = f"D{counter}"
            if candidate not in used:
                numbers.append(candidate)
                used.add(candidate)
            counter += 1
        return numbers
    floor, counter = index + 1, 1
    while len(numbers) < item["units"]:
        if counter > 99:
            floor, counter = floor + 10, 1
        candidate = f"{floor}{counter:02d}"
        if candidate not in used:
            numbers.append(candidate)
            used.add(candidate)
        counter += 1
    return numbers


def normalize_proposal(prop, raw, *, catalog: dict | None = None) -> tuple[dict, list[str]]:
    """A proposal the review screen and `apply_proposal` can trust: types and ranges fixed, codes and room
    numbers unique in the hotel, unknown amenities dropped. Returns `(proposal, warnings)`."""
    from apps.inventory.models import Room, RoomType

    raw = raw if isinstance(raw, dict) else {}
    catalog = catalog if catalog is not None else _catalog(prop)
    warnings: list[str] = []
    unknown: set[str] = set()

    source = raw.get("property") if isinstance(raw.get("property"), dict) else {}
    description = _i18n(source, "description")
    stars = _int(source.get("star_rating"), None, low=1, high=5)
    hotel = {
        "name": str(source.get("name") or "").strip()[:200] or prop.name,
        "description": description,
        "city": str(source.get("city") or "").strip()[:100],
        "address": str(source.get("address") or "").strip()[:255],
        "phone": str(source.get("phone") or "").strip()[:32],
        "email": str(source.get("email") or "").strip()[:254],
        "star_rating": stars,
        "check_in_time": normalize_time(source.get("check_in_time")),
        "check_out_time": normalize_time(source.get("check_out_time")),
        "amenities": _amenities(source.get("amenities"), catalog, unknown),
    }

    items = [item for item in raw.get("room_types") or [] if isinstance(item, dict)][:MAX_ROOM_TYPES]
    room_types = [
        _room_type(item, index=index, catalog=catalog, unknown=unknown, warnings=warnings)
        for index, item in enumerate(items)
    ]
    taken = set(RoomType.objects.filter(property=prop).values_list("code", flat=True))
    for item in room_types:
        base = _sanitize_code(item["code"]) or _code_from_name(item["name"]["es"])
        item["code"] = _unique(base, taken)
    used = set(Room.objects.filter(property=prop).values_list("number", flat=True))
    for item in room_types:  # numbers written by hand are kept (apply reports a clash) …
        if len(item["room_numbers"]) == item["units"] and len(set(item["room_numbers"])) == item["units"]:
            used.update(item["room_numbers"])
        else:
            item["room_numbers"] = []
    for index, item in enumerate(room_types):  # … the rest are generated around them
        if not item["room_numbers"]:
            item["room_numbers"] = _generate_numbers(index, item, used)

    policies_raw = raw.get("policies") if isinstance(raw.get("policies"), dict) else {}
    discount = _int(policies_raw.get("non_refundable_discount_percent"), DEFAULT_NR_DISCOUNT, low=0, high=90)
    breakfast = _money(policies_raw.get("breakfast_price"))
    policies = {
        "non_refundable_discount_percent": discount,
        "breakfast_price": str(breakfast) if breakfast and breakfast > 0 else None,
        "pets_allowed": _bool(policies_raw.get("pets_allowed"), False),
        "smoking_allowed": _bool(policies_raw.get("smoking_allowed"), False),
        "children_allowed": _bool(policies_raw.get("children_allowed"), True),
    }

    extras, extra_codes = [], set()
    for item in raw.get("extras") or []:
        if not isinstance(item, dict):
            continue
        name = _i18n(item, "name")
        price = _money(item.get("price"))
        if not name["es"] or price is None or price <= 0:
            continue
        charge_type = item.get("charge_type") if item.get("charge_type") in CHARGE_TYPES else "per_stay"
        code = _unique(_sanitize_code(item.get("code")) or _code_from_name(name["es"]), extra_codes)
        extras.append({"code": code, "name": name, "price": str(price), "charge_type": charge_type})
    if policies["breakfast_price"] and not any(extra["code"] == "BRK" for extra in extras):
        extras.insert(
            0,
            {
                "code": _unique("BRK", extra_codes),
                "name": {"es": "Desayuno", "en": "Breakfast"},
                "price": policies["breakfast_price"],
                "charge_type": "per_person_night",
            },
        )

    if unknown:
        warnings.append(f"Omití amenidades que no están en el catálogo: {', '.join(sorted(unknown))}.")
    if not room_types:
        warnings.append("No encontré categorías de habitación: agrega al menos una antes de crear todo.")
    proposal = {"property": hotel, "room_types": room_types, "policies": policies, "extras": extras[:15]}
    return proposal, warnings


# ---- apply -------------------------------------------------------------------------------------------------


def _plans(policies: dict) -> list[dict]:
    plans = [
        {
            "code": "FLEX",
            "name": {"es": "Tarifa flexible", "en": "Flexible rate"},
            "kind": "base",
            "cancellation_policy": "flexible",
            "sort_order": 10,
        }
    ]
    discount = policies.get("non_refundable_discount_percent") or 0
    if discount > 0:
        plans.append(
            {
                "code": "NR",
                "name": {"es": "No reembolsable", "en": "Non-refundable"},
                "kind": "derived",
                "parent": "FLEX",
                "derivation_type": "percent",
                "derivation_value": str(-discount),
                "cancellation_policy": "non_refundable",
                "sort_order": 20,
            }
        )
    if policies.get("breakfast_price"):
        plans.append(
            {
                "code": "BB",
                "name": {"es": "Con desayuno", "en": "Breakfast included"},
                "kind": "derived",
                "parent": "FLEX",
                "derivation_type": "amount",
                "derivation_value": policies["breakfast_price"],
                "meal_plan": "breakfast",
                "cancellation_policy": "flexible",
                "sort_order": 30,
            }
        )
    return plans


def _profile_data(hotel: dict, policies: dict) -> dict:
    data = {key: hotel[key] for key in ("name", "city", "address", "phone", "email") if hotel.get(key)}
    description = {lang: text for lang, text in (hotel.get("description") or {}).items() if text}
    if description:
        data["description"] = description
    for key in ("check_in_time", "check_out_time", "star_rating"):
        if hotel.get(key):
            data[key] = hotel[key]
    if hotel.get("amenities"):
        data["amenities"] = hotel["amenities"]
    data["policies"] = {key: policies[key] for key in ("pets_allowed", "smoking_allowed", "children_allowed")}
    return data


def _raise_serializer_errors(errors, *, prefix: str) -> None:
    fields = {
        f"{prefix}.{key}": value if isinstance(value, list) else [str(value)] for key, value in errors.items()
    }
    first = next(iter(fields.values()), ["Datos inválidos"])
    message = first[0] if isinstance(first, list) and first else "Datos inválidos"
    raise DomainError(str(message), code="validation_error", fields=fields)


def apply_proposal(prop, proposal: dict, *, actor=None) -> dict:
    """Create the proposal (edited by the user) in one transaction and return a summary."""
    from apps.core import audit
    from apps.inventory.serializers import PropertyProfileSerializer
    from apps.inventory.services import provision_room_type, update_property_profile
    from apps.rates.api.serializers import ExtraSerializer
    from apps.rates.models import Tax
    from apps.rates.services.provision import provision_rates

    clean, _ = normalize_proposal(prop, proposal)
    if not clean["room_types"]:
        raise DomainError(
            "Agrega al menos una categoría de habitación",
            code="validation_error",
            fields={"room_types": ["Agrega al menos una categoría"]},
        )
    summary = {"room_types": [], "rooms_created": 0, "rate_plans": [], "extras": [], "profile_updated": []}
    with transaction.atomic():
        profile = PropertyProfileSerializer(
            prop, data=_profile_data(clean["property"], clean["policies"]), partial=True
        )
        if not profile.is_valid():
            _raise_serializer_errors(profile.errors, prefix="property")
        update_property_profile(prop, profile, actor=actor)
        summary["profile_updated"] = sorted(profile.validated_data)

        for item in clean["room_types"]:
            data = {
                key: item[key]
                for key in (
                    "code",
                    "name",
                    "kind",
                    "beds",
                    "amenities",
                    "base_occupancy",
                    "max_adults",
                    "max_children",
                    "max_occupancy",
                )
            }
            if item.get("size_m2"):
                data["size_m2"] = item["size_m2"]
            room_type = provision_room_type(
                prop,
                data=data,
                room_numbers=item["room_numbers"],
                floor=None,
                beds_per_room=item.get("beds_per_room") if item["kind"] == "dorm" else None,
                actor=actor,
            )
            numbers = sorted(room_type.rooms.values_list("number", flat=True))
            summary["room_types"].append(
                {
                    "id": str(room_type.pk),
                    "code": room_type.code,
                    "name": room_type.name,
                    "kind": room_type.kind,
                    "rooms": numbers,
                }
            )
            summary["rooms_created"] += len(numbers)

        plans = _plans(clean["policies"])
        provision_rates(
            prop,
            room_type_prices={
                item["code"]: {
                    "price": item["base_price"],
                    "weekend_adjust_percent": item["weekend_adjust_percent"],
                    "extra_adult_price": item["extra_adult_price"],
                    "extra_child_price": item["extra_child_price"],
                }
                for item in clean["room_types"]
            },
            plans=plans,
            actor=actor,
        )
        summary["rate_plans"] = [plan["code"] for plan in plans]

        extras_tax = Tax.objects.filter(property=prop, code="IVA-EXTRAS").first()
        context = {"request": SimpleNamespace(property=prop, user=actor)}
        for extra in clean["extras"]:
            serializer = ExtraSerializer(
                data={
                    **extra,
                    "tax": str(extras_tax.pk) if extras_tax else None,
                    "sellable_online": True,
                    "is_active": True,
                },
                context=context,
            )
            if not serializer.is_valid():
                if "code" in serializer.errors:  # the hotel already sells it: keep theirs
                    continue
                _raise_serializer_errors(serializer.errors, prefix=f"extras.{extra['code']}")
            serializer.save(property=prop)
            summary["extras"].append(extra["code"])

        audit.record(
            action="ai.onboarding_applied",
            target=prop,
            property=prop,
            actor=actor,
            source="ai",
            summary=f"Configuración asistida: {len(summary['room_types'])} categorías y "
            f"{summary['rooms_created']} habitaciones",
            changes={
                "room_types": [item["code"] for item in summary["room_types"]],
                "plans": summary["rate_plans"],
                "extras": summary["extras"],
            },
        )
    summary["links"] = {
        "room_types": "/app/settings/room-types",
        "rooms": "/app/settings/rooms",
        "rates": "/app/rates",
        "plans": "/app/rates/plans",
        "property": "/app/settings/property",
        "extras": "/app/settings/extras",
    }
    return summary


# ---- offline heuristics ------------------------------------------------------------------------------------

_NUM = (
    rf"(\d+|{'|'.join(sorted(nlp.NUMBER_WORDS, key=len, reverse=True))}|nueve|diez|once|doce|quince|veinte)"
)
_EXTRA_NUMBERS = {"nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20}
PRICE = re.compile(r"\$?\s*(\d{1,3}(?:[.,]\d{3})+|\d{4,7}|\d{2,3}\s*(?:mil|k)\b)")
ROOM_KINDS = [
    # (pattern after the number, code, name es, name en, kind, beds, default price)
    (
        r"dormitorios?(?:\s+(?:compartidos?|mixtos?|femeninos?))?(?:\s+de\s+(\d+)\s+camas)?|dorms?",
        "D",
        "Dormitorio compartido",
        "Shared dorm",
        "dorm",
        None,
        60000,
    ),
    (r"suites?", "STE", "Suite", "Suite", "private", [{"type": "king", "count": 1}], 450000),
    (
        r"(?:habitaciones?\s+)?dobles?|doubles?",
        "DBL",
        "Doble",
        "Double",
        "private",
        [{"type": "queen", "count": 1}],
        250000,
    ),
    (
        r"(?:habitaciones?\s+)?(?:sencillas?|individuales?)|singles?",
        "SGL",
        "Sencilla",
        "Single",
        "private",
        [{"type": "single", "count": 1}],
        180000,
    ),
    (
        r"(?:habitaciones?\s+)?triples?",
        "TPL",
        "Triple",
        "Triple",
        "private",
        [{"type": "queen", "count": 1}, {"type": "single", "count": 1}],
        320000,
    ),
    (
        r"(?:habitaciones?\s+)?familiares?|family rooms?",
        "FAM",
        "Familiar",
        "Family",
        "private",
        [{"type": "queen", "count": 1}, {"type": "bunk", "count": 1}],
        380000,
    ),
    (
        r"(?:habitaciones?\s+)?superiores?",
        "SUP",
        "Superior",
        "Superior",
        "private",
        [{"type": "king", "count": 1}],
        320000,
    ),
    (
        r"(?:habitaciones?\s+)?privadas?|private rooms?",
        "PRV",
        "Privada",
        "Private room",
        "private",
        [{"type": "double", "count": 1}],
        150000,
    ),
    (
        r"(?:habitaciones?\s+)?est[aá]ndar|standard rooms?",
        "STD",
        "Estándar",
        "Standard",
        "private",
        [{"type": "queen", "count": 1}],
        250000,
    ),
]
GENERIC_ROOMS = re.compile(rf"\b{_NUM}\s+(?:habitaciones|cuartos|rooms)\b")
# The next "<number> <word>" mention (another room type) ends the price window; numbers inside prices and
# "2 noches", "30 mil"… do not.
NEXT_MENTION = re.compile(
    r"(?<![\d.,])\b\d+\s+(?!mil\b|k\b|noches?\b|personas?\b|camas?\b|pesos\b|cop\b)[a-z]"
)
SENTENCE = r"(?:[^.]|\.(?=\d)){0,60}"  # up to the end of the sentence ("30.000" does not end it)
CITIES = [
    "Cartagena",
    "Medellín",
    "Bogotá",
    "Cali",
    "Santa Marta",
    "Barranquilla",
    "San Andrés",
    "Pereira",
    "Manizales",
    "Armenia",
    "Bucaramanga",
    "Villa de Leyva",
    "Salento",
    "Guatapé",
    "Popayán",
    "Pasto",
    "Leticia",
    "Cúcuta",
    "Ibagué",
    "Neiva",
    "Villavicencio",
    "Palomino",
    "Minca",
    "Mompox",
    "Barichara",
    "San Gil",
    "Santa Fe de Antioquia",
    "Jardín",
    "Tolú",
    "Capurganá",
    "Nuquí",
    "Providencia",
]
AMENITY_WORDS = [
    (r"wi-?fi|internet", "wifi"),
    (r"piscina|pool", "pool"),
    (r"aire acondicionado|a/c\b", "air_conditioning"),
    (r"parqueadero|parking|estacionamiento", "parking"),
    (r"restaurante|restaurant", "restaurant"),
    (r"\bbar\b", "bar"),
    (r"terraza|rooftop", "terrace"),
    (r"gimnasio|\bgym\b", "gym"),
    (r"\bspa\b", "spa"),
    (r"vista al mar|sea view|frente al mar", "sea_view"),
    (r"balc[oó]n", "balcony"),
    (r"\btv\b|televisi[oó]n", "tv"),
    (r"minibar", "minibar"),
    (r"caja fuerte", "safe"),
    (r"desayuno|breakfast", "breakfast"),
    (r"recepci[oó]n 24|24 horas", "reception_24h"),
    (r"lockers|casilleros", "lockers"),
    (r"cocina compartida|shared kitchen", "shared_kitchen"),
    (r"lavander[ií]a|laundry", "laundry"),
    (r"traslados?|shuttle", "airport_shuttle"),
    (r"ba[nñ]era|jacuzzi|tina", "bathtub"),
    (r"ascensor", "elevator"),
    (r"ba[nñ]o privado", "private_bathroom"),
    (r"ba[nñ]o compartido", "shared_bathroom"),
]
ROOM_LEVEL = {
    "wifi",
    "air_conditioning",
    "tv",
    "minibar",
    "safe",
    "private_bathroom",
    "shared_bathroom",
    "balcony",
    "bathtub",
}


def _to_int(token: str) -> int | None:
    token = token.strip().lower()
    return nlp.to_int(token) or _EXTRA_NUMBERS.get(token)


def _price(text: str) -> Decimal | None:
    match = PRICE.search(text)
    if not match:
        return None
    token = match[1].lower().replace(" ", "")
    if token.endswith(("mil", "k")):
        value = Decimal(re.sub(r"\D", "", token)) * 1000
    else:
        value = Decimal(re.sub(r"\D", "", token))
    return value if value >= 10000 else None


def _time_after(text: str, label: str) -> str | None:
    match = re.search(
        rf"{label}[^0-9]{{0,20}}(\d{{1,2}}(?::\d{{2}})?\s*(?:a\.?\s?m\.?|p\.?\s?m\.?)?)", text, re.I
    )
    return normalize_time(match[1]) if match else None


def heuristic_proposal(text: str) -> dict:
    """What a model would propose, read from the text with rules (offline assistant)."""
    plain = nlp.strip_accents(text.lower())
    room_types, spans = [], []
    for pattern, code, es, en, kind, beds, default_price in ROOM_KINDS:
        regex = re.compile(rf"\b{_NUM}\s+(?:{nlp.strip_accents(pattern)})\b")
        for match in regex.finditer(plain):
            if any(start <= match.start() < end for start, end in spans):
                continue
            units = _to_int(match[1]) or 1
            window = plain[match.end() : match.end() + 70]
            window = window.split(" y ", 1)[0] if kind == "dorm" else NEXT_MENTION.split(window)[0]
            price = _price(window)
            item = {
                "code": code,
                "name_es": es,
                "name_en": en,
                "kind": kind,
                "units": units,
                "base_price": float(price) if price else default_price,
                "amenities": [],
            }
            if kind == "dorm":
                beds_per_room = (
                    int(match.group(match.lastindex)) if match.lastindex and match.lastindex > 1 else 6
                )
                item["beds"] = [{"type": "bunk", "count": max(1, beds_per_room // 2)}] + (
                    [{"type": "single", "count": 1}] if beds_per_room % 2 else []
                )
                item["code"] = f"D{beds_per_room}"
                item["name_es"], item["name_en"] = (
                    f"Dormitorio de {beds_per_room} camas",
                    f"{beds_per_room}-bed dorm",
                )
            else:
                item["beds"] = beds
            if re.search(r"vista al mar|frente al mar|sea view", plain[match.end() : match.end() + 40]):
                item["amenities"].append("sea_view")
            item["_position"] = match.start()
            room_types.append(item)
            spans.append((match.start(), match.end()))
    room_types.sort(key=lambda item: item.pop("_position"))  # in the order the text mentions them
    if not room_types:
        generic = GENERIC_ROOMS.search(plain)
        units = _to_int(generic[1]) if generic else None
        price = _price(plain[generic.end() : generic.end() + 80]) if generic else None
        room_types.append(
            {
                "code": "STD",
                "name_es": "Estándar",
                "name_en": "Standard",
                "kind": "private",
                "units": units or 10,
                "beds": [{"type": "queen", "count": 1}],
                "base_price": float(price) if price else 250000,
                "amenities": [],
            }
        )

    amenities = [code for pattern, code in AMENITY_WORDS if re.search(pattern, plain)]
    for item in room_types:
        item["amenities"] = list(
            dict.fromkeys([*item["amenities"], *[code for code in amenities if code in ROOM_LEVEL]])
        )
    city = next((name for name in CITIES if nlp.strip_accents(name.lower()) in plain), "")
    stars = re.search(r"(\d)\s*estrellas|(\d)[\s-]*stars?", plain)
    breakfast = None
    if found := re.search(rf"desayuno{SENTENCE}", plain):
        if not re.search(r"desayuno\s+incluido", found[0]):
            breakfast = _price(found[0])
    extras = []
    for pattern, code, es, en, charge in [
        (rf"parqueadero{SENTENCE}", "PARK", "Parqueadero", "Parking", "per_night"),
        (rf"traslados?{SENTENCE}", "TRF", "Traslado aeropuerto", "Airport transfer", "per_stay"),
    ]:
        if found := re.search(pattern, plain):
            if price := _price(found[0]):
                extras.append(
                    {"code": code, "name_es": es, "name_en": en, "price": float(price), "charge_type": charge}
                )
    pets = None
    if re.search(
        r"no\s+(?:se\s+)?(?:aceptan|admiten|permiten|aceptamos)\s+mascotas|sin\s+mascotas|no pets", plain
    ):
        pets = False
    elif re.search(
        r"pet[\s-]?friendly|aceptamos mascotas|se aceptan mascotas|mascotas (?:bienvenidas|permitidas)|"
        r"admitimos mascotas",
        plain,
    ):
        pets = True
    return {
        "property": {
            "city": city,
            "star_rating": int(stars[1] or stars[2]) if stars else None,
            "check_in_time": _time_after(plain, r"check[\s-]?in"),
            "check_out_time": _time_after(plain, r"check[\s-]?out"),
            "amenities": amenities,
            "description_es": " ".join(text.split())[:600],
        },
        "room_types": room_types,
        "policies": {
            "breakfast_price": float(breakfast) if breakfast else None,
            "pets_allowed": pets,
            "smoking_allowed": False,
            "children_allowed": True,
        },
        "extras": extras,
    }


@register_structured("onboarding_proposal")
def _simulated_proposal(prompt: str, system: str | None) -> dict:
    return heuristic_proposal(
        prompt.replace("## Descripción del hotel", "").replace("## Texto del sitio web", "")
    )
