"""Values of the template placeholders (plan C6): a flat `{"dotted.name": "text"}` dict built from the guest,
the reservation, the hotel and the caller's `context` (which adds or overrides keys, e.g. the payment link of
`finance`: `payment_url`, `amount`, `reference`, `expires_at`). Everything is already formatted for the
guest's language, so the renderer only substitutes strings.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from apps.core.i18n import t
from apps.core.money import quantize
from apps.core.tokens import portal_url as signed_portal_url

LANGUAGES = ("es", "en")

_MONTHS = {
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
_WEEKDAYS = {
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}


def _v(key, group, es, en, example_es, example_en=None):
    return {
        "key": key,
        "group": group,
        "label": {"es": es, "en": en},
        "example": {"es": example_es, "en": example_en if example_en is not None else example_es},
    }


# Catalog for the template editor (`GET /api/v1/messaging/variables/`), in display order.
VARIABLES = [
    _v("guest.first_name", "guest", "Nombre del huésped", "Guest first name", "Ana"),
    _v("guest.last_name", "guest", "Apellidos del huésped", "Guest last name", "Pérez"),
    _v("guest.full_name", "guest", "Nombre completo", "Full name", "Ana Pérez"),
    _v("guest.email", "guest", "Correo del huésped", "Guest email", "ana.perez@example.com"),
    _v("guest.phone", "guest", "Teléfono del huésped", "Guest phone", "+573001234567"),
    _v("reservation.code", "reservation", "Código de la reserva", "Booking code", "HT-7K2M9Q"),
    _v(
        "reservation.checkin",
        "reservation",
        "Fecha de llegada",
        "Arrival date",
        "viernes 9 de octubre de 2026",
        "Friday, October 9, 2026",
    ),
    _v(
        "reservation.checkout",
        "reservation",
        "Fecha de salida",
        "Departure date",
        "domingo 11 de octubre de 2026",
        "Sunday, October 11, 2026",
    ),
    _v("nights", "reservation", "Noches", "Nights", "2"),
    _v("reservation.adults", "reservation", "Adultos", "Adults", "2"),
    _v("reservation.children", "reservation", "Niños", "Children", "0"),
    _v("reservation.guests", "reservation", "Total de huéspedes", "Total guests", "2"),
    _v(
        "reservation.room_type",
        "reservation",
        "Habitación reservada",
        "Room type",
        "Suite Vista al Mar",
        "Sea View Suite",
    ),
    _v("reservation.total", "reservation", "Total de la reserva", "Booking total", "$ 761.600"),
    _v("reservation.cancellation_fee", "reservation", "Penalidad de cancelación", "Cancellation fee", "$ 0"),
    _v("balance", "reservation", "Saldo pendiente", "Balance due", "$ 380.800"),
    _v("property.name", "property", "Nombre del hotel", "Hotel name", "Hotel Casa Aurora"),
    _v("property.phone", "property", "Teléfono del hotel", "Hotel phone", "+57 605 660 1234"),
    _v("property.email", "property", "Correo del hotel", "Hotel email", "reservas@casaaurora.co"),
    _v("property.address", "property", "Dirección del hotel", "Hotel address", "Calle del Cuartel #36-77"),
    _v("property.city", "property", "Ciudad", "City", "Cartagena"),
    _v("property.website", "property", "Sitio web", "Website", "https://casaaurora.co"),
    _v("property.check_in_time", "property", "Hora de check-in", "Check-in time", "15:00"),
    _v("property.check_out_time", "property", "Hora de check-out", "Check-out time", "12:00"),
    _v("portal_url", "links", "Portal del huésped", "Guest portal link", "https://…/g/…"),
    _v("checkin_url", "links", "Check-in en línea", "Online check-in link", "https://…/g/…/checkin"),
    _v("payment_url", "links", "Link de pago", "Payment link", "https://…/g/…"),
    _v("review_url", "links", "Link para opinar", "Review link", "https://…/g/…"),
    _v("amount", "payment", "Monto del link de pago", "Payment link amount", "$ 200.000"),
    _v("reference", "payment", "Referencia del pago", "Payment reference", "HT-7K2M9Q-2D3J6D"),
    _v(
        "expires_at",
        "payment",
        "Vencimiento del link de pago",
        "Payment link expiry",
        "27 de septiembre de 2026, 18:44",
        "September 27, 2026, 18:44",
    ),
]


def normalize_language(language) -> str:
    code = str(language or "").strip().lower()[:2]
    return code if code in LANGUAGES else "es"


def format_money(amount, currency: str = "COP") -> str:
    """`$ 350.000` (COP without decimals, dot thousands), same style as finance messages."""
    value = quantize(amount or 0, currency)
    digits = f"{abs(value):,.0f}" if currency == "COP" else f"{abs(value):,.2f}"
    digits = digits.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if value < 0 else ''}$ {digits}"


def format_date(value: date, language: str) -> str:
    lang = normalize_language(language)
    weekday, month = _WEEKDAYS[lang][value.weekday()], _MONTHS[lang][value.month - 1]
    if lang == "en":
        return f"{weekday}, {month} {value.day}, {value.year}"
    return f"{weekday} {value.day} de {month} de {value.year}"


def format_datetime(value: datetime, language: str, timezone: str) -> str:
    lang = normalize_language(language)
    local = value.astimezone(ZoneInfo(timezone or "America/Bogota"))
    month, clock = _MONTHS[lang][local.month - 1], local.strftime("%H:%M")
    if lang == "en":
        return f"{month} {local.day}, {local.year}, {clock}"
    return f"{local.day} de {month} de {local.year}, {clock}"


def _clock(value) -> str:
    return value.strftime("%H:%M") if value else ""


def _property_values(prop) -> dict:
    return {
        "property.name": prop.name,
        "property.phone": prop.phone,
        "property.email": prop.email,
        "property.address": prop.address,
        "property.city": prop.city,
        "property.website": prop.website,
        "property.check_in_time": _clock(prop.check_in_time),
        "property.check_out_time": _clock(prop.check_out_time),
    }


def _guest_values(guest) -> dict:
    return {
        "guest.first_name": guest.first_name,
        "guest.last_name": guest.last_name,
        "guest.full_name": guest.full_name,
        "guest.email": guest.email,
        "guest.phone": guest.phone,
    }


def _room_types(reservation, lang: str) -> str:
    stays = list(reservation.stays.select_related("room_type").order_by("checkin_date", "created_at"))
    active = [s for s in stays if s.status not in ("cancelled", "no_show")] or stays
    return ", ".join(dict.fromkeys(t(stay.room_type.name, lang) for stay in active))


def _reservation_values(reservation, lang: str) -> dict:
    from apps.finance.services import reservation_balance

    prop = reservation.property
    portal = signed_portal_url(reservation)
    return {
        "reservation.code": reservation.code,
        "reservation.checkin": format_date(reservation.checkin_date, lang),
        "reservation.checkout": format_date(reservation.checkout_date, lang),
        "nights": str((reservation.checkout_date - reservation.checkin_date).days),
        "reservation.adults": str(reservation.adults),
        "reservation.children": str(reservation.children),
        "reservation.guests": str(reservation.adults + reservation.children),
        "reservation.room_type": _room_types(reservation, lang),
        "reservation.total": format_money(reservation.total_amount, reservation.currency),
        "reservation.cancellation_fee": format_money(reservation.cancellation_fee, reservation.currency),
        "balance": format_money(reservation_balance(reservation), reservation.currency),
        "portal_url": portal,
        "checkin_url": f"{portal}/checkin",
        "payment_url": portal,
        "review_url": str((prop.settings or {}).get("review_url") or portal),
    }


def _flatten(data: dict, prefix: str = "") -> dict:
    flat = {}
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(_flatten(value, f"{name}."))
        else:
            flat[name] = value
    return flat


def _context_value(key: str, value, prop, lang: str) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return format_datetime(value, lang, prop.timezone)
    if isinstance(value, date):
        return format_date(value, lang)
    if isinstance(value, Decimal):
        return format_money(value, prop.currency)
    if isinstance(value, str) and key.endswith("_at") and "T" in value:
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return value
        if moment.tzinfo is not None:
            return format_datetime(moment, lang, prop.timezone)
    return str(value)


def build_variables(*, property, guest=None, reservation=None, language="es", context=None) -> dict[str, str]:
    """All placeholder values for one message. `guest` defaults to the reservation's booker."""
    lang = normalize_language(language)
    guest = guest if guest is not None else getattr(reservation, "booker", None)
    values = _property_values(property)
    if guest is not None:
        values.update(_guest_values(guest))
    if reservation is not None:
        values.update(_reservation_values(reservation, lang))
    for key, value in _flatten(context or {}).items():
        values[key] = _context_value(key, value, property, lang)
    return values


def sample_variables(property, language="es") -> dict[str, str]:
    """Believable values for the template preview when no reservation is chosen (catalog examples + the
    hotel's real data and dates a week ahead)."""
    lang = normalize_language(language)
    values = {item["key"]: item["example"][lang] for item in VARIABLES}
    values.update({key: value for key, value in _property_values(property).items() if value})
    checkin = property.business_date + timedelta(days=7)
    values["reservation.checkin"] = format_date(checkin, lang)
    values["reservation.checkout"] = format_date(checkin + timedelta(days=2), lang)
    return values
