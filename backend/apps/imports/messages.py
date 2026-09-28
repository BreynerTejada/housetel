"""Bilingual messages of the importer (row issues and outcomes).

Each message has a stable `code` and a Spanish/English template; rows store `{"code", "es", "en"}` (and the
issues add `level` and `field`), so the UI shows the viewer's language and the error report (CSV) can be
downloaded in either. Messages of other apps' services (a `DomainError` detail) come only in Spanish: known
codes get the English template here, unknown ones repeat the Spanish text.
"""

from apps.core.errors import DomainError

MESSAGES: dict[str, tuple[str, str]] = {
    # --- validation: files and columns
    "required": ("Falta el dato obligatorio «{field}»", "The required value “{field}” is missing"),
    "invalid_date": ("Fecha inválida en «{field}»: «{value}»", "Invalid date in “{field}”: “{value}”"),
    "invalid_time": ("Hora inválida en «{field}»: «{value}»", "Invalid time in “{field}”: “{value}”"),
    "invalid_number": ("Número inválido en «{field}»: «{value}»", "Invalid number in “{field}”: “{value}”"),
    "invalid_money": ("Monto inválido en «{field}»: «{value}»", "Invalid amount in “{field}”: “{value}”"),
    "negative_amount": ("El monto de «{field}» no puede ser negativo", "“{field}” cannot be negative"),
    "invalid_email": (
        "Email inválido «{value}»: se importa sin email",
        "Invalid email “{value}”: imported without an email",
    ),
    "unknown_country": (
        "País no reconocido en «{field}»: «{value}» (se deja vacío)",
        "Unknown country in “{field}”: “{value}” (left empty)",
    ),
    "unknown_document_type": (
        "Tipo de documento no reconocido «{value}»: se usa «Otro»",
        "Unknown document type “{value}”: “Other” is used",
    ),
    "document_type_inferred": (
        "Sin tipo de documento: se asume {value}",
        "No document type: {value} is assumed",
    ),
    "unknown_gender": (
        "Género no reconocido «{value}» (se deja vacío)",
        "Unknown gender “{value}” (left empty)",
    ),
    "unknown_language": (
        "Idioma no reconocido «{value}»: se usa el del país",
        "Unknown language “{value}”: the country's language is used",
    ),
    "birth_date_future": ("La fecha de nacimiento está en el futuro", "The birth date is in the future"),
    "missing_name": ("Falta el nombre del huésped", "The guest's name is missing"),
    "dates_order": ("La salida debe ser posterior a la llegada", "The check-out must be after the check-in"),
    "nights_mismatch": (
        "Las noches ({value}) no coinciden con las fechas: se usan las fechas",
        "The nights ({value}) do not match the dates: the dates are used",
    ),
    "unknown_status": (
        "Estado no reconocido «{value}»: se deduce de las fechas",
        "Unknown status “{value}”: deduced from the dates",
    ),
    "skip_cancelled": (
        "Cancelada en el sistema anterior: no se importa",
        "Cancelled in the previous system: not imported",
    ),
    "skip_no_show": (
        "No-show en el sistema anterior: no se importa",
        "No-show in the previous system: not imported",
    ),
    "skip_checked_out": (
        "Estadía finalizada: solo se importan reservas futuras y en casa",
        "Finished stay: only future and in-house reservations are imported",
    ),
    "skip_past": (
        "La estadía ya terminó ({date}): no se importa",
        "The stay already ended ({date}): not imported",
    ),
    "skip_arrival_passed": (
        "La llegada ({date}) ya pasó y la reserva no figura en casa: no se importa",
        "The arrival ({date}) has passed and the reservation is not in house: not imported",
    ),
    "in_house_future": (
        "Figura en casa pero la llegada es futura ({date})",
        "It is in house but the arrival is in the future ({date})",
    ),
    "in_house_ended": (
        "Figura en casa pero la salida ya pasó ({date}): haz el check-out en el sistema anterior",
        "It is in house but the check-out has passed ({date}): check it out in the previous system",
    ),
    "assumed_in_house": (
        "Sin estado: por las fechas se importa como en casa",
        "No status: imported as in house because of its dates",
    ),
    "tentative_no_expiry": (
        "No confirmada: se importa como tentativa sin vencimiento",
        "Not confirmed: imported as tentative with no expiry",
    ),
    "adults_default": ("Sin adultos: se asume 1", "No adults: 1 is assumed"),
    "unmapped_room_type": ("Categoría sin asignar: «{value}»", "Unassigned category: “{value}”"),
    "unmapped_rate_plan": ("Plan tarifario sin asignar: «{value}»", "Unassigned rate plan: “{value}”"),
    "no_default_plan": (
        "No hay un plan tarifario activo para usar por defecto",
        "There is no active rate plan to use by default",
    ),
    "plan_not_for_type": (
        "El plan {plan} no incluye la categoría {room_type}: agrégala en Tarifas o elige otro plan",
        "The {plan} plan does not include the {room_type} category: add it in Rates or choose another plan",
    ),
    "room_type_inactive": ("La categoría {room_type} está inactiva", "The {room_type} category is inactive"),
    "capacity": (
        "La categoría {room_type} admite máximo {max_adults} adultos, {max_children} niños y {max_occupancy} "
        "huéspedes",
        "The {room_type} category allows at most {max_adults} adults, {max_children} children and "
        "{max_occupancy} guests",
    ),
    "dorm_children": (
        "El dormitorio {room_type} no admite niños",
        "The {room_type} dorm does not allow children",
    ),
    "room_not_found": (
        "La habitación «{value}» no existe: se importa sin asignar",
        "Room “{value}” does not exist: imported unassigned",
    ),
    "room_not_found_in_house": (
        "La habitación «{value}» no existe en Housetel",
        "Room “{value}” does not exist in Housetel",
    ),
    "room_other_type": (
        "La habitación {room} es de la categoría {room_type}: se importa sin asignar",
        "Room {room} belongs to the {room_type} category: imported unassigned",
    ),
    "room_other_type_in_house": (
        "La habitación {room} es de la categoría {room_type}, no de {expected}",
        "Room {room} belongs to the {room_type} category, not {expected}",
    ),
    "room_auto": (
        "Sin habitación: al registrar la llegada se asigna una libre de la categoría",
        "No room: a free room of the category is assigned when checking in",
    ),
    "bed_not_found": (
        "La cama «{value}» no existe en la habitación {room}: se asigna una libre",
        "Bed “{value}” does not exist in room {room}: a free one is assigned",
    ),
    "paid_exceeds_total": (
        "Lo pagado ({paid}) supera el total ({total}): quedará saldo a favor",
        "The amount paid ({paid}) exceeds the total ({total}): the guest will have a credit",
    ),
    "balance_mismatch": (
        "Lo pagado ({paid}) no cuadra con total − saldo ({expected}): se usa lo pagado",
        "The amount paid ({paid}) does not match total − balance ({expected}): the amount paid is used",
    ),
    "no_total": (
        "Sin total: se cotiza con las tarifas de Housetel",
        "No total: priced with Housetel's rates",
    ),
    "external_id_missing": (
        "Sin número de reserva: se identifica por huésped, fechas y categoría",
        "No reservation number: identified by guest, dates and category",
    ),
    "exists_update": ("Ya se importó antes: se actualizará", "Imported before: it will be updated"),
    "exists_skip": ("Ya se importó antes: se omite", "Imported before: skipped"),
    "duplicate_row": ("Repite los datos de la fila {row}", "Repeats the data of row {row}"),
    "multi_room_split": (
        "Varias habitaciones en una fila: huéspedes y monto se repartieron entre ellas",
        "Several rooms in one row: guests and amount were split among them",
    ),
    "group_rows": (
        "Reserva de {count} habitaciones (filas {rows})",
        "Reservation with {count} rooms (rows {rows})",
    ),
    "group_has_errors": (
        "Otra fila de la misma reserva tiene errores (fila {row})",
        "Another row of the same reservation has errors (row {row})",
    ),
    "group_guest_differs": (
        "El titular difiere de la primera fila de la reserva: se usa el de la fila {row}",
        "The booker differs from the reservation's first row: the one of row {row} is used",
    ),
    "invalid_kind": (
        "Tipo de categoría no reconocido «{value}»: usa «privada» o «dormitorio»",
        "Unknown category type “{value}”: use “private” or “dorm”",
    ),
    "invalid_room_numbers": ("Números de habitación inválidos: «{value}»", "Invalid room numbers: “{value}”"),
    "room_numbers_taken": (
        "Estas habitaciones ya existen: {value}",
        "These rooms already exist: {value}",
    ),
    "dorm_beds_required": (
        "Un dormitorio necesita «camas por habitación»",
        "A dorm needs “beds per room”",
    ),
    "room_type_exists_update": (
        "La categoría {value} ya existe: se actualizará",
        "Category {value} already exists: it will be updated",
    ),
    "room_type_exists_skip": (
        "La categoría {value} ya existe: se omite",
        "Category {value} already exists: skipped",
    ),
    "room_exists_update": (
        "La habitación {value} ya existe: se actualizará",
        "Room {value} already exists: it will be updated",
    ),
    "room_exists_skip": ("La habitación {value} ya existe: se omite", "Room {value} already exists: skipped"),
    "code_repeated": ("El código {value} se repite en la fila {row}", "Code {value} repeats in row {row}"),
    "number_repeated": (
        "La habitación {value} se repite en la fila {row}",
        "Room {value} repeats in row {row}",
    ),
    "rates_added": (
        "Se agrega a tus planes tarifarios con precio base {value}",
        "Added to your rate plans with a base price of {value}",
    ),
    # --- outcomes
    "created": ("Creado", "Created"),
    "created_reservation": ("Reserva {code} creada", "Reservation {code} created"),
    "created_in_house": (
        "Reserva {code} creada y en casa ({room})",
        "Reservation {code} created, in house ({room})",
    ),
    "created_guest": ("Huésped creado", "Guest created"),
    "matched_guest": (
        "Ya existía en Housetel (mismo documento o email): se completaron sus datos",
        "Already in Housetel (same document or email): their data was completed",
    ),
    "updated": ("Actualizado", "Updated"),
    "updated_fields": ("Actualizado: {value}", "Updated: {value}"),
    "unchanged": ("Sin cambios", "No changes"),
    "skipped_existing": ("Ya importado antes: omitido", "Imported before: skipped"),
    "skipped_inactive": (
        "La reserva ya no está activa en Housetel ({status}): omitida",
        "The reservation is no longer active in Housetel ({status}): skipped",
    ),
    "cancelled_from_source": (
        "Cancelada: el sistema anterior la marca como {value}",
        "Cancelled: the previous system marks it as {value}",
    ),
    "checked_in_from_source": ("Registrada en casa ({room})", "Checked in ({room})"),
    "payment_added": ("Pago importado de {value}", "Imported payment of {value}"),
    "cancel_in_house": (
        "Figura cancelada en el sistema anterior pero en Housetel está en casa: revísala",
        "Cancelled in the previous system but in house in Housetel: check it",
    ),
    "exists_cancel": (
        "Ya se importó antes y ahora figura cancelada: se cancelará en Housetel (sin penalidad)",
        "Imported before and now cancelled: it will be cancelled in Housetel (no fee)",
    ),
    "multi_stay_not_updated": (
        "Cambios de habitaciones en reservas de varias habitaciones: no se aplican",
        "Room changes in multi-room reservations are not applied",
    ),
    "payment_lower": (
        "Lo pagado en el archivo ({value}) es menor que lo ya importado: revisa el folio",
        "The amount paid in the file ({value}) is lower than what was imported: check the folio",
    ),
    "total_differs": (
        "El total quedó en {value} (el archivo dice {expected})",
        "The total is {value} (the file says {expected})",
    ),
    "would_create": ("Se crearía", "Would be created"),
    "would_update": ("Se actualizaría", "Would be updated"),
    "reverted": ("Reserva cancelada por la reversión", "Reservation cancelled by the rollback"),
    "revert_in_house": ("Está en casa: no se revierte", "It is in house: not rolled back"),
    "revert_not_active": (
        "Ya no está activa ({status}): no se revierte",
        "No longer active ({status}): not rolled back",
    ),
    "revert_activity": (
        "Tiene actividad posterior a la importación ({value}): no se revierte",
        "It has activity after the import ({value}): not rolled back",
    ),
    "revert_missing": ("La reserva ya no existe", "The reservation no longer exists"),
    "conflict_in_file": (
        "Sin disponibilidad en {room_type} el {date}: las filas anteriores del archivo ocupan la "
        "última unidad",
        "No availability in {room_type} on {date}: earlier rows of the file take the last unit",
    ),
    "room_conflict_in_file": (
        "La habitación {room} ya está ocupada por la fila {row} del archivo en esas fechas",
        "Room {room} is already taken by row {row} of the file on those dates",
    ),
    "internal_error": ("Error inesperado: {value}", "Unexpected error: {value}"),
    # --- other apps' service errors (codes of their DomainError)
    "no_availability": (
        "Sin disponibilidad para esas fechas en la categoría (no se sobrevende)",
        "No availability for those dates in the category (no overbooking)",
    ),
    "room_blocked": ("La habitación está bloqueada en esas fechas", "The room is blocked on those dates"),
    "capacity_exceeded": ("Supera la capacidad de la categoría", "Exceeds the category's capacity"),
    "invalid_rate_plan": (
        "El plan tarifario no aplica a esta categoría",
        "The rate plan does not apply to this category",
    ),
    "invalid_room_type": (
        "La categoría no existe o está inactiva",
        "The category does not exist or is inactive",
    ),
    "category_mismatch": ("La habitación es de otra categoría", "The room belongs to another category"),
    "invalid_state": (
        "La reserva no permite esa acción en su estado actual",
        "The reservation's status does not allow it",
    ),
    "room_not_ready": ("La habitación no está lista", "The room is not ready"),
    "guest_exists": ("Ese documento pertenece a otro huésped", "That document belongs to another guest"),
    "room_in_use": ("La habitación tiene reservas activas", "The room has active reservations"),
    "room_type_in_use": ("La categoría tiene reservas activas", "The category has active reservations"),
    "duplicate_room_numbers": ("Esos números de habitación ya existen", "Those room numbers already exist"),
    "unknown_room_type": ("Categoría inexistente", "Unknown category"),
    "invalid_price": ("Precio inválido", "Invalid price"),
    "folio_closed": ("El folio está cerrado", "The folio is closed"),
}


# Field codes shown inside messages ("Falta el dato obligatorio «Llegada»").
FIELD_LABELS: dict[str, tuple[str, str]] = {
    "external_id": ("Id / número", "Id / number"),
    "full_name": ("Nombre completo", "Full name"),
    "first_name": ("Nombre", "First name"),
    "last_name": ("Apellidos", "Last name"),
    "email": ("Email", "Email"),
    "phone": ("Teléfono", "Phone"),
    "document_type": ("Tipo de documento", "Document type"),
    "document_number": ("Número de documento", "Document number"),
    "nationality": ("Nacionalidad", "Nationality"),
    "country_of_residence": ("País de residencia", "Country of residence"),
    "city_of_residence": ("Ciudad", "City"),
    "birth_date": ("Fecha de nacimiento", "Birth date"),
    "gender": ("Género", "Gender"),
    "language": ("Idioma", "Language"),
    "address": ("Dirección", "Address"),
    "status": ("Estado", "Status"),
    "checkin": ("Llegada", "Check-in"),
    "checkout": ("Salida", "Check-out"),
    "nights": ("Noches", "Nights"),
    "adults": ("Adultos", "Adults"),
    "children": ("Niños", "Children"),
    "room_type": ("Categoría", "Category"),
    "room_number": ("Habitación", "Room"),
    "bed": ("Cama", "Bed"),
    "rate_plan": ("Plan tarifario", "Rate plan"),
    "total_amount": ("Total", "Total"),
    "paid_amount": ("Pagado", "Paid"),
    "balance_due": ("Saldo", "Balance due"),
    "source": ("Origen", "Source"),
    "third_party_id": ("Número del canal", "Channel number"),
    "booked_at": ("Fecha de reserva", "Booking date"),
    "eta": ("Hora de llegada", "Arrival time"),
    "special_requests": ("Solicitudes especiales", "Special requests"),
    "notes": ("Notas", "Notes"),
    "code": ("Código", "Code"),
    "name": ("Nombre", "Name"),
    "name_en": ("Nombre en inglés", "English name"),
    "kind": ("Tipo", "Type"),
    "base_occupancy": ("Ocupación base", "Base occupancy"),
    "max_adults": ("Máx. adultos", "Max adults"),
    "max_children": ("Máx. niños", "Max children"),
    "max_occupancy": ("Ocupación máxima", "Max occupancy"),
    "beds_per_room": ("Camas por habitación", "Beds per room"),
    "room_numbers": ("Habitaciones", "Rooms"),
    "base_price": ("Precio base", "Base price"),
    "description": ("Descripción", "Description"),
    "number": ("Número", "Number"),
    "floor": ("Piso", "Floor"),
    "beds": ("Camas", "Beds"),
    "building": ("Edificio", "Building"),
}


def field_label(code: str, lang: str = "es") -> str:
    pair = FIELD_LABELS.get(code)
    return (pair[1] if lang == "en" else pair[0]) if pair else code


def render(msg_code: str, lang: str = "es", /, **params) -> str:
    templates = MESSAGES.get(msg_code)
    if templates is None:
        return str(params.get("detail") or params.get("value") or msg_code)
    template = templates[1] if lang == "en" else templates[0]
    values = {key: _text(value) for key, value in params.items()}
    if "field" in params:
        values["field"] = field_label(str(params["field"]), lang)
    try:
        return template.format(**values)
    except (KeyError, IndexError):
        return template


def _text(value) -> str:
    if value is None:
        return ""
    return str(value)


def message(msg_code: str, /, **params) -> dict:
    """{"code", "es", "en"} ready to store in a row (templates may use `{code}`, `{field}`…)."""
    return {"code": msg_code, "es": render(msg_code, "es", **params), "en": render(msg_code, "en", **params)}


def issue(level: str, msg_code: str, field: str = "", /, **params) -> dict:
    """A validation issue: level `error` (the row is not imported), `warning` (imported with a caveat), `skip`
    (nothing to import) or `info`."""
    return {"level": level, "code": msg_code, "field": field, **message(msg_code, **params)}


def from_domain_error(exc: DomainError) -> dict:
    """{"code", "es", "en"} of another app's DomainError: its Spanish detail (plus field messages) and, when
    the code is known, the English template."""
    detail = exc.message
    fields = exc.extra.get("fields") if isinstance(exc.extra, dict) else None
    if isinstance(fields, dict):
        extras = [
            f"{name}: {' '.join(str(item) for item in (value if isinstance(value, list) else [value]))}"
            for name, value in fields.items()
        ]
        if extras:
            detail = f"{detail} ({'; '.join(extras)})"
    code = exc.code or "domain_error"
    english = MESSAGES[code][1] if code in MESSAGES and "{" not in MESSAGES[code][1] else detail
    return {"code": code, "es": detail, "en": english}


def text(stored: dict | None, lang: str = "es") -> str:
    if not stored:
        return ""
    return str(stored.get("en" if lang == "en" else "es") or stored.get("es") or "")
