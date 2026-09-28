"""What can be imported: kinds, presets, the fields of each kind (with the ES/EN column titles recognized
automatically) and the job options.

Header matching compares folded titles (lower case, no accents, no punctuation): "Número de reserva",
"numero de reserva" and "NUMERO_DE_RESERVA" are the same. Presets add their own titles first:

- **generic**: Housetel's templates (ES/EN) and the usual titles of spreadsheets and other PMSs.
- **cloudbeds**: the Cloudbeds export. Its reservations export (Reservations → Export, .xlsx) lets the user
  pick the columns, so the preset recognizes every title of the export wizard it may contain (English and
  Spanish UI): "Reservation Number", "Third Party Confirmation Number", "Name"/"Guest Name", "Email", "Phone
  Number", "Check in Date"/"Check-In", "Check out Date"/"Check-Out", "Nights", "Adults", "Children", "Room
  Type", "Room Number", "Rate Plan", "Source", "Status" (confirmed, not_confirmed, canceled, checked_in,
  checked_out, no_show — also their UI labels), "Grand Total", "Deposit", "Balance Due", "Reservation Date",
  "Estimated Arrival Time", "Country". Its guest export uses "First Name", "Last Name", "Email", "Phone",
  "Date
  of Birth", "Gender", "Country", "Document Type", "Document Number"... A multi-room reservation may come in
  one row with the room types (and numbers) separated by commas: the preset splits them.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from apps.imports.models import ImportJob

Kind = ImportJob.Kind

MAX_FILE_BYTES = 15 * 1024 * 1024
MAX_ROWS = 10_000
MAX_COLUMNS = 120
SAMPLE_VALUES = 4  # sample cells shown per column in the mapping step
MAX_DISTINCT_VALUES = 200  # distinct categories / plans offered in the value mapping

DATE_FORMATS = ("auto", "dmy", "mdy", "ymd")
ON_EXISTING = ("update", "skip")

DEFAULT_OPTIONS = {
    "date_format": "auto",  # auto | dmy | mdy | ymd
    "amounts_include_tax": True,  # the file's totals are what the guest pays (IVA included)
    "on_existing": "update",  # update | skip (records imported before from the same system)
    "default_rate_plan": "",  # uuid of the plan for rows without one ("" → the first active base plan)
}

PRESET_LABELS = {"generic": "Otro sistema", "cloudbeds": "Cloudbeds"}


def fold(value) -> str:
    """ "Número de Reserva #" → "numero de reserva": no accents, lower case, words only."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


@dataclass(frozen=True)
class Field:
    code: str
    type: str = "text"  # text | date | int | money | choice | email | phone | country | time
    required: bool = False
    aliases: tuple[str, ...] = ()
    cloudbeds: tuple[str, ...] = ()
    group: str = "main"  # main | guest | stay | money | extra (UI grouping)
    value_mapping: str = ""  # room_type | rate_plan: distinct values mapped to Housetel objects

    def titles(self, preset: str) -> list[str]:
        own = list(self.cloudbeds) if preset == ImportJob.Preset.CLOUDBEDS else []
        return [fold(title) for title in (*own, *self.aliases)]


@dataclass(frozen=True)
class KindSpec:
    code: str
    fields: tuple[Field, ...]
    # at least one of these groups must be mapped (e.g. a guest needs a full name or a first name)
    one_of: tuple[tuple[str, ...], ...] = field(default_factory=tuple)

    def get(self, code: str) -> Field | None:
        return next((item for item in self.fields if item.code == code), None)


# ---- Guest fields (also the booker of a reservation) ---------------------------------------------------

GUEST_FIELDS = (
    Field(
        "full_name",
        group="guest",
        aliases=(
            "nombre completo",
            "nombre y apellido",
            "nombres y apellidos",
            "huesped",
            "nombre del huesped",
            "titular",
            "nombre del titular",
            "cliente",
            "nombre cliente",
            "full name",
            "guest name",
            "guest",
            "customer name",
            "customer",
        ),
        cloudbeds=("name", "guest name", "nombre", "nombre del huesped"),
    ),
    Field(
        "first_name",
        group="guest",
        aliases=("nombre", "nombres", "primer nombre", "first name", "firstname", "given name", "forename"),
        cloudbeds=("first name", "guest first name", "nombre"),
    ),
    Field(
        "last_name",
        group="guest",
        aliases=("apellido", "apellidos", "last name", "lastname", "surname", "family name"),
        cloudbeds=("last name", "guest last name", "apellido", "apellidos"),
    ),
    Field(
        "email",
        type="email",
        group="guest",
        aliases=(
            "email",
            "e mail",
            "correo",
            "correo electronico",
            "mail",
            "email address",
            "guest email",
            "correo del huesped",
        ),
        cloudbeds=("email", "guest email"),
    ),
    Field(
        "phone",
        type="phone",
        group="guest",
        aliases=(
            "telefono",
            "celular",
            "movil",
            "telefono movil",
            "whatsapp",
            "phone",
            "phone number",
            "mobile",
            "mobile phone",
            "cell phone",
            "cellphone",
            "guest phone",
            "telefono del huesped",
        ),
        cloudbeds=("phone number", "phone", "cell phone", "mobile"),
    ),
    Field(
        "document_type",
        type="choice",
        group="guest",
        aliases=(
            "tipo de documento",
            "tipo documento",
            "tipo doc",
            "tipo de identificacion",
            "tipo id",
            "document type",
            "id type",
            "identification type",
        ),
        cloudbeds=("document type", "tipo de documento"),
    ),
    Field(
        "document_number",
        group="guest",
        aliases=(
            "numero de documento",
            "numero documento",
            "documento",
            "no documento",
            "nro documento",
            "documento de identidad",
            "cedula",
            "identificacion",
            "numero de identificacion",
            "document number",
            "document",
            "id number",
            "identification number",
            "passport number",
            "pasaporte",
            "passport",
        ),
        cloudbeds=("document number", "numero de documento", "id number"),
    ),
    Field(
        "nationality",
        type="country",
        group="guest",
        aliases=("nacionalidad", "pais de nacionalidad", "nationality", "citizenship"),
        cloudbeds=("nationality", "nacionalidad"),
    ),
    Field(
        "country_of_residence",
        type="country",
        group="guest",
        aliases=(
            "pais",
            "pais de residencia",
            "residencia",
            "pais residencia",
            "country",
            "country of residence",
            "residence country",
            "residence",
        ),
        cloudbeds=("country", "pais"),
    ),
    Field(
        "city_of_residence",
        group="guest",
        aliases=("ciudad", "ciudad de residencia", "municipio", "city", "city of residence", "town"),
        cloudbeds=("city", "ciudad"),
    ),
    Field(
        "birth_date",
        type="date",
        group="guest",
        aliases=(
            "fecha de nacimiento",
            "nacimiento",
            "fecha nacimiento",
            "cumpleanos",
            "birth date",
            "date of birth",
            "dob",
            "birthday",
            "birthdate",
        ),
        cloudbeds=("date of birth", "birthday", "birth date", "fecha de nacimiento"),
    ),
    Field(
        "gender",
        type="choice",
        group="guest",
        aliases=("genero", "sexo", "gender", "sex"),
        cloudbeds=("gender", "genero"),
    ),
    Field(
        "language",
        type="choice",
        group="guest",
        aliases=("idioma", "lengua", "language", "lang", "preferred language"),
        cloudbeds=("language", "idioma"),
    ),
    Field(
        "address",
        group="guest",
        aliases=("direccion", "direccion de residencia", "address", "street address", "street"),
        cloudbeds=("address", "street address", "direccion"),
    ),
)

GUESTS = KindSpec(
    code=Kind.GUESTS,
    fields=(
        Field(
            "external_id",
            group="main",
            aliases=(
                "id",
                "id huesped",
                "id del huesped",
                "codigo huesped",
                "codigo cliente",
                "id cliente",
                "guest id",
                "customer id",
                "profile id",
            ),
            cloudbeds=("guest id", "id del huesped", "customer id"),
        ),
        *GUEST_FIELDS,
    ),
    one_of=(("full_name", "first_name"),),
)

# ---- Reservations -------------------------------------------------------------------------------------

RESERVATION_FIELDS = (
    Field(
        "external_id",
        group="main",
        aliases=(
            "numero de reserva",
            "no reserva",
            "nro reserva",
            "reserva",
            "codigo de reserva",
            "codigo reserva",
            "id reserva",
            "id de reserva",
            "localizador",
            "confirmacion",
            "numero de confirmacion",
            "reservation number",
            "reservation id",
            "reservation",
            "reservation code",
            "confirmation number",
            "confirmation code",
            "booking id",
            "booking number",
            "booking reference",
            "res id",
        ),
        cloudbeds=("reservation number", "reservation id", "numero de reserva", "reservation"),
    ),
    Field(
        "status",
        type="choice",
        group="main",
        aliases=("estado", "estado de la reserva", "estado reserva", "status", "reservation status"),
        cloudbeds=("status", "reservation status", "estado"),
    ),
    Field(
        "checkin",
        type="date",
        required=True,
        group="stay",
        aliases=(
            "llegada",
            "fecha de llegada",
            "fecha llegada",
            "fecha de entrada",
            "entrada",
            "check in",
            "checkin",
            "fecha check in",
            "check in date",
            "arrival",
            "arrival date",
            "start date",
            "desde",
        ),
        cloudbeds=("check in date", "check in", "checkin", "fecha de llegada", "llegada"),
    ),
    Field(
        "checkout",
        type="date",
        group="stay",
        aliases=(
            "salida",
            "fecha de salida",
            "fecha salida",
            "check out",
            "checkout",
            "fecha check out",
            "check out date",
            "departure",
            "departure date",
            "end date",
            "hasta",
        ),
        cloudbeds=("check out date", "check out", "checkout", "fecha de salida", "salida"),
    ),
    Field(
        "nights",
        type="int",
        group="stay",
        aliases=("noches", "numero de noches", "nights", "number of nights", "los"),
        cloudbeds=("nights", "noches"),
    ),
    Field(
        "adults",
        type="int",
        group="stay",
        aliases=("adultos", "numero de adultos", "adults", "adult", "pax", "huespedes", "guests"),
        cloudbeds=("adults", "adultos"),
    ),
    Field(
        "children",
        type="int",
        group="stay",
        aliases=("ninos", "numero de ninos", "menores", "children", "kids", "child", "infants"),
        cloudbeds=("children", "ninos"),
    ),
    Field(
        "room_type",
        type="choice",
        required=True,
        group="stay",
        value_mapping="room_type",
        aliases=(
            "categoria",
            "tipo de habitacion",
            "tipo habitacion",
            "tipo de alojamiento",
            "acomodacion",
            "room type",
            "room category",
            "accommodation type",
            "accommodation",
            "unit type",
        ),
        cloudbeds=("room type", "room types", "accommodation type", "tipo de habitacion"),
    ),
    Field(
        "room_number",
        group="stay",
        aliases=(
            "habitacion",
            "numero de habitacion",
            "no habitacion",
            "hab",
            "cuarto",
            "room",
            "room number",
            "room name",
            "room no",
            "unit",
        ),
        cloudbeds=("room number", "room", "room name", "numero de habitacion", "habitacion"),
    ),
    Field(
        "bed",
        group="stay",
        aliases=("cama", "numero de cama", "bed", "bed number", "bed name"),
        cloudbeds=("bed", "cama"),
    ),
    Field(
        "rate_plan",
        type="choice",
        group="stay",
        value_mapping="rate_plan",
        aliases=("plan", "tarifa", "plan tarifario", "plan de tarifa", "rate plan", "rate", "rate name"),
        cloudbeds=("rate plan", "rate name", "rate", "plan de tarifa"),
    ),
    Field(
        "total_amount",
        type="money",
        group="money",
        aliases=(
            "total",
            "total reserva",
            "valor total",
            "valor",
            "monto total",
            "precio total",
            "importe total",
            "total amount",
            "reservation total",
            "total price",
            "amount",
        ),
        cloudbeds=("grand total", "total", "reservation total", "total general"),
    ),
    Field(
        "paid_amount",
        type="money",
        group="money",
        aliases=(
            "pagado",
            "total pagado",
            "monto pagado",
            "abonado",
            "abono",
            "anticipo",
            "paid",
            "amount paid",
            "total paid",
            "payments",
            "deposito",
            "deposit",
        ),
        cloudbeds=("paid", "amount paid", "deposit", "pagado"),
    ),
    Field(
        "balance_due",
        type="money",
        group="money",
        aliases=(
            "saldo",
            "saldo pendiente",
            "por pagar",
            "pendiente",
            "balance",
            "balance due",
            "amount due",
        ),
        cloudbeds=("balance due", "balance", "saldo"),
    ),
    *GUEST_FIELDS,
    Field(
        "source",
        group="extra",
        aliases=("origen", "fuente", "canal", "canal de venta", "source", "channel", "booking source"),
        cloudbeds=("source", "origen"),
    ),
    Field(
        "third_party_id",
        group="extra",
        aliases=(
            "id del canal",
            "reserva del canal",
            "confirmacion del canal",
            "ota id",
            "channel reservation id",
            "external reference",
        ),
        cloudbeds=(
            "third party confirmation number",
            "numero de confirmacion de terceros",
            "source reservation id",
        ),
    ),
    Field(
        "booked_at",
        type="date",
        group="extra",
        aliases=(
            "fecha de reserva",
            "fecha de creacion",
            "creada",
            "fecha reserva",
            "reservation date",
            "booking date",
            "date booked",
            "booked on",
            "created",
            "created at",
        ),
        cloudbeds=("reservation date", "booking date", "date booked", "fecha de reserva"),
    ),
    Field(
        "eta",
        type="time",
        group="extra",
        aliases=("hora de llegada", "hora estimada de llegada", "hora llegada", "eta", "arrival time"),
        cloudbeds=("estimated arrival time", "arrival time", "hora estimada de llegada"),
    ),
    Field(
        "special_requests",
        group="extra",
        aliases=("solicitudes especiales", "solicitudes", "peticiones", "special requests", "requests"),
        cloudbeds=("special requests", "guest requests"),
    ),
    Field(
        "notes",
        group="extra",
        aliases=("notas", "observaciones", "comentarios", "nota", "notes", "comments", "remarks"),
        cloudbeds=("notes", "reservation notes", "comments"),
    ),
)

RESERVATIONS = KindSpec(
    code=Kind.RESERVATIONS,
    fields=RESERVATION_FIELDS,
    one_of=(("full_name", "first_name"), ("checkout", "nights")),
)

# ---- Room types and rooms -----------------------------------------------------------------------------

ROOM_TYPES = KindSpec(
    code=Kind.ROOM_TYPES,
    fields=(
        Field(
            "code",
            aliases=(
                "codigo",
                "codigo categoria",
                "abreviatura",
                "sigla",
                "code",
                "short name",
                "short code",
            ),
            cloudbeds=("short name", "room type short name", "abbreviation"),
        ),
        Field(
            "name",
            required=True,
            aliases=(
                "nombre",
                "categoria",
                "nombre de la categoria",
                "nombre es",
                "tipo de habitacion",
                "name",
                "room type",
                "room type name",
                "name es",
            ),
            cloudbeds=("room type name", "room type", "name"),
        ),
        Field("name_en", aliases=("nombre en ingles", "nombre en", "name en", "english name")),
        Field(
            "kind",
            type="choice",
            aliases=("tipo", "clase", "venta", "privada o dormitorio", "kind", "type", "private or dorm"),
            cloudbeds=("type", "room type category"),
        ),
        Field(
            "base_occupancy",
            type="int",
            aliases=("ocupacion base", "ocupacion estandar", "base occupancy", "standard occupancy"),
        ),
        Field(
            "max_adults",
            type="int",
            aliases=("max adultos", "maximo de adultos", "adultos maximo", "max adults", "maximum adults"),
            cloudbeds=("max adults", "adults"),
        ),
        Field(
            "max_children",
            type="int",
            aliases=("max ninos", "maximo de ninos", "ninos maximo", "max children", "maximum children"),
            cloudbeds=("max children", "children"),
        ),
        Field(
            "max_occupancy",
            type="int",
            aliases=(
                "ocupacion maxima",
                "capacidad",
                "capacidad maxima",
                "max huespedes",
                "max occupancy",
                "maximum occupancy",
                "max guests",
                "capacity",
            ),
            cloudbeds=("max occupancy", "max guests", "occupancy"),
        ),
        Field(
            "beds_per_room",
            type="int",
            aliases=("camas por habitacion", "camas", "numero de camas", "beds per room", "beds"),
        ),
        Field(
            "room_numbers",
            aliases=(
                "habitaciones",
                "numeros de habitacion",
                "numeros",
                "rooms",
                "room numbers",
                "units",
            ),
            cloudbeds=("rooms", "room names"),
        ),
        Field(
            "base_price",
            type="money",
            aliases=(
                "precio",
                "precio base",
                "tarifa",
                "tarifa base",
                "precio por noche",
                "base price",
                "price",
                "rate",
                "base rate",
                "nightly rate",
            ),
            cloudbeds=("base rate", "rate", "price"),
        ),
        Field(
            "description",
            aliases=("descripcion", "description", "detalle"),
            cloudbeds=("description", "room type description"),
        ),
    ),
)

ROOMS = KindSpec(
    code=Kind.ROOMS,
    fields=(
        Field(
            "number",
            required=True,
            aliases=(
                "numero",
                "numero de habitacion",
                "habitacion",
                "no habitacion",
                "hab",
                "number",
                "room",
                "room number",
                "room name",
                "unit",
            ),
            cloudbeds=("room name", "room number", "room"),
        ),
        Field(
            "room_type",
            type="choice",
            required=True,
            value_mapping="room_type",
            aliases=("categoria", "tipo de habitacion", "tipo", "room type", "category", "type"),
            cloudbeds=("room type", "room type name"),
        ),
        Field("floor", aliases=("piso", "planta", "nivel", "floor", "level")),
        Field("name", aliases=("nombre", "alias", "nombre de la habitacion", "name", "display name")),
        Field(
            "beds", type="int", aliases=("camas", "numero de camas", "beds", "number of beds", "bed count")
        ),
        Field("building", aliases=("edificio", "torre", "bloque", "building", "block", "tower")),
        Field("notes", aliases=("notas", "observaciones", "notes", "comments")),
    ),
)

KINDS: dict[str, KindSpec] = {
    Kind.GUESTS: GUESTS,
    Kind.RESERVATIONS: RESERVATIONS,
    Kind.ROOM_TYPES: ROOM_TYPES,
    Kind.ROOMS: ROOMS,
}


def spec(kind: str) -> KindSpec:
    return KINDS[kind]


def default_options(preset: str) -> dict:
    options = dict(DEFAULT_OPTIONS)
    # Cloudbeds' "Grand Total" includes taxes and fees (like most PMS exports): both presets start there.
    options["amounts_include_tax"] = True
    return options


def catalog() -> dict:
    """JSON description of the kinds and their fields for the UI (labels live in the frontend i18n)."""
    return {
        "kinds": [
            {
                "code": kind,
                "fields": [
                    {
                        "code": item.code,
                        "type": item.type,
                        "required": item.required,
                        "group": item.group,
                        "value_mapping": item.value_mapping,
                    }
                    for item in kind_spec.fields
                ],
                "one_of": [list(group) for group in kind_spec.one_of],
            }
            for kind, kind_spec in KINDS.items()
        ],
        "presets": [{"code": code, "label": label} for code, label in PRESET_LABELS.items()],
        "options": {
            "date_format": list(DATE_FORMATS),
            "on_existing": list(ON_EXISTING),
            "defaults": DEFAULT_OPTIONS,
        },
        "limits": {"max_file_bytes": MAX_FILE_BYTES, "max_rows": MAX_ROWS, "formats": ["csv", "xlsx"]},
    }
