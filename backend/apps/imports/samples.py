# ruff: noqa: E501 - example rows and demo data are long literal lines (kept in `fmt: skip` blocks)
"""Downloadable templates (ES/EN, CSV or XLSX) and example files.

- Template: Housetel's column titles for the kind (recognized automatically by the mapping), one empty row.
- Example (`example=1`): the same columns with realistic rows built from the property's own categories,
  rooms and rate plans and dates around its business date, including a few rows that show warnings,
  skips and errors — handy to try the importer end to end. `preset=cloudbeds` writes the reservations or
  guests example with the titles and values of a Cloudbeds export (multi-room reservations in one row).
"""

import csv
import io
from datetime import timedelta

from django.http import HttpResponse

from apps.imports.models import ImportJob

TEMPLATES: dict[str, dict[str, list[tuple[str, str]]]] = {
    # kind → lang → [(field, title)]
    ImportJob.Kind.GUESTS: {
        "es": [
            ("external_id", "Id"), ("first_name", "Nombre"), ("last_name", "Apellidos"), ("email", "Email"),
            ("phone", "Teléfono"), ("document_type", "Tipo de documento"),
            ("document_number", "Número de documento"), ("nationality", "Nacionalidad"),
            ("country_of_residence", "País de residencia"), ("city_of_residence", "Ciudad"),
            ("birth_date", "Fecha de nacimiento"), ("gender", "Género"), ("language", "Idioma"),
            ("address", "Dirección"),
        ],
        "en": [
            ("external_id", "Id"), ("first_name", "First name"), ("last_name", "Last name"), ("email", "Email"),
            ("phone", "Phone"), ("document_type", "Document type"), ("document_number", "Document number"),
            ("nationality", "Nationality"), ("country_of_residence", "Country of residence"),
            ("city_of_residence", "City"), ("birth_date", "Birth date"), ("gender", "Gender"),
            ("language", "Language"), ("address", "Address"),
        ],
    },
    ImportJob.Kind.RESERVATIONS: {
        "es": [
            ("external_id", "Número de reserva"), ("status", "Estado"), ("checkin", "Llegada"),
            ("checkout", "Salida"), ("adults", "Adultos"), ("children", "Niños"), ("room_type", "Categoría"),
            ("room_number", "Habitación"), ("rate_plan", "Plan tarifario"), ("total_amount", "Total"),
            ("paid_amount", "Pagado"), ("first_name", "Nombre"), ("last_name", "Apellidos"), ("email", "Email"),
            ("phone", "Teléfono"), ("document_type", "Tipo de documento"),
            ("document_number", "Número de documento"), ("nationality", "Nacionalidad"),
            ("country_of_residence", "País de residencia"), ("source", "Origen"), ("eta", "Hora de llegada"),
            ("special_requests", "Solicitudes especiales"), ("notes", "Notas"),
        ],
        "en": [
            ("external_id", "Reservation number"), ("status", "Status"), ("checkin", "Check-in"),
            ("checkout", "Check-out"), ("adults", "Adults"), ("children", "Children"), ("room_type", "Room type"),
            ("room_number", "Room"), ("rate_plan", "Rate plan"), ("total_amount", "Total"),
            ("paid_amount", "Paid"), ("first_name", "First name"), ("last_name", "Last name"), ("email", "Email"),
            ("phone", "Phone"), ("document_type", "Document type"), ("document_number", "Document number"),
            ("nationality", "Nationality"), ("country_of_residence", "Country of residence"),
            ("source", "Source"), ("eta", "Arrival time"), ("special_requests", "Special requests"),
            ("notes", "Notes"),
        ],
    },
    ImportJob.Kind.ROOM_TYPES: {
        "es": [
            ("code", "Código"), ("name", "Nombre"), ("name_en", "Nombre en inglés"), ("kind", "Tipo"),
            ("base_occupancy", "Ocupación base"), ("max_adults", "Máx. adultos"), ("max_children", "Máx. niños"),
            ("max_occupancy", "Ocupación máxima"), ("beds_per_room", "Camas por habitación"),
            ("room_numbers", "Habitaciones"), ("base_price", "Precio base"), ("description", "Descripción"),
        ],
        "en": [
            ("code", "Code"), ("name", "Name"), ("name_en", "English name"), ("kind", "Type"),
            ("base_occupancy", "Base occupancy"), ("max_adults", "Max adults"), ("max_children", "Max children"),
            ("max_occupancy", "Max occupancy"), ("beds_per_room", "Beds per room"), ("room_numbers", "Rooms"),
            ("base_price", "Base price"), ("description", "Description"),
        ],
    },
    ImportJob.Kind.ROOMS: {
        "es": [
            ("number", "Número"), ("room_type", "Categoría"), ("floor", "Piso"), ("name", "Nombre"),
            ("beds", "Camas"), ("building", "Edificio"), ("notes", "Notas"),
        ],
        "en": [
            ("number", "Number"), ("room_type", "Room type"), ("floor", "Floor"), ("name", "Name"),
            ("beds", "Beds"), ("building", "Building"), ("notes", "Notes"),
        ],
    },
}  # fmt: skip

CLOUDBEDS_RESERVATIONS = [
    ("external_id", "Reservation Number"), ("third_party_id", "Third Party Confirmation Number"),
    ("full_name", "Name"), ("email", "Email"), ("phone", "Phone Number"), ("country_of_residence", "Country"),
    ("checkin", "Check in Date"), ("checkout", "Check out Date"), ("nights", "Nights"), ("adults", "Adults"),
    ("children", "Children"), ("room_type", "Room Type"), ("room_number", "Room Number"),
    ("rate_plan", "Rate Plan"), ("source", "Source"), ("status", "Status"), ("total_amount", "Grand Total"),
    ("balance_due", "Balance Due"), ("booked_at", "Reservation Date"), ("eta", "Estimated Arrival Time"),
]  # fmt: skip
CLOUDBEDS_GUESTS = [
    ("external_id", "Guest ID"), ("first_name", "First Name"), ("last_name", "Last Name"), ("email", "Email"),
    ("phone", "Phone"), ("gender", "Gender"), ("birth_date", "Date of Birth"), ("country_of_residence", "Country"),
    ("city_of_residence", "City"), ("address", "Address"), ("document_type", "Document Type"),
    ("document_number", "Document Number"), ("nationality", "Nationality"),
]  # fmt: skip


def columns(kind: str, lang: str, preset: str = "generic") -> list[tuple[str, str]]:
    if preset == ImportJob.Preset.CLOUDBEDS and kind == ImportJob.Kind.RESERVATIONS:
        return CLOUDBEDS_RESERVATIONS
    if preset == ImportJob.Preset.CLOUDBEDS and kind == ImportJob.Kind.GUESTS:
        return CLOUDBEDS_GUESTS
    return TEMPLATES[kind]["en" if lang == "en" else "es"]


# ---- Example rows -------------------------------------------------------------------------------------


def _fmt_date(day, lang: str, preset: str) -> str:
    if preset == ImportJob.Preset.CLOUDBEDS:
        return day.strftime("%m/%d/%Y")
    return day.isoformat() if lang == "en" else day.strftime("%d/%m/%Y")


def _catalog(prop) -> dict:
    from apps.inventory.models import Room, RoomType
    from apps.rates.models import RatePlan

    types = list(RoomType.objects.filter(property=prop, is_active=True).order_by("sort_order", "code"))
    private = [rt for rt in types if rt.kind == RoomType.Kind.PRIVATE] or types
    plans = list(RatePlan.objects.filter(property=prop, is_active=True).order_by("sort_order", "code"))
    base = next((plan for plan in plans if plan.kind == RatePlan.Kind.BASE), plans[0] if plans else None)
    rooms = {}
    for room_type in private:
        rooms[room_type.pk] = list(
            Room.objects.filter(room_type=room_type, is_active=True)
            .order_by("number")
            .values_list("number", flat=True)
        )
    numbers = set(Room.objects.filter(property=prop).values_list("number", flat=True))
    free = [str(n) for n in range(901, 1000) if str(n) not in numbers]
    return {"types": types, "private": private, "base": base, "rooms": rooms, "free_numbers": free}


def _name(obj, lang: str) -> str:
    name = obj.name or {}
    return name.get(lang) or name.get("es") or obj.code


def example_rows(kind: str, prop, lang: str, preset: str) -> list[dict]:
    today = prop.business_date
    cat = _catalog(prop)
    cloud = preset == ImportJob.Preset.CLOUDBEDS
    if kind == ImportJob.Kind.GUESTS:
        rows = [
            {"external_id": "G-1001", "first_name": "Camila", "last_name": "Restrepo Uribe",
             "email": "camila.restrepo@example.com", "phone": "+57 310 555 0142", "document_type": "CC",
             "document_number": "1.020.345.678", "nationality": "Colombia", "country_of_residence": "Colombia",
             "city_of_residence": "Medellín", "birth_date": _fmt_date(today.replace(year=1990, month=3, day=14), lang, preset),
             "gender": "F", "language": "Español"},
            {"external_id": "G-1002", "first_name": "Daniel", "last_name": "Walker",
             "email": "daniel.walker@example.com", "phone": "+1 415 555 0199",
             "document_type": "Passport" if lang == "en" or cloud else "Pasaporte", "document_number": "X1234567",
             "nationality": "United States" if lang == "en" or cloud else "Estados Unidos",
             "country_of_residence": "United States" if lang == "en" or cloud else "Estados Unidos",
             "city_of_residence": "San Francisco", "birth_date": _fmt_date(today.replace(year=1985, month=7, day=22), lang, preset),
             "gender": "M", "language": "English"},
            {"external_id": "G-1003", "first_name": "Sofía", "last_name": "Martínez", "email": "sofia.martinez@example",
             "phone": "310 555 0177", "document_number": "52.345.678", "nationality": "Colombiana",
             "city_of_residence": "Bogotá", "gender": "F", "address": "Cra 7 # 45-10"},
            {"external_id": "G-1004", "first_name": "Lukas", "last_name": "Becker", "email": "lukas.becker@example.de",
             "document_type": "Passport" if lang == "en" or cloud else "Pasaporte", "document_number": "C01X00T47",
             "nationality": "Germany" if lang == "en" or cloud else "Alemania",
             "country_of_residence": "Germany" if lang == "en" or cloud else "Alemania", "city_of_residence": "Berlín",
             "language": "Alemán" if lang == "es" and not cloud else "German"},
            {"external_id": "G-1005", "email": "sin.nombre@example.com", "phone": "+57 300 555 0100"},
        ]  # fmt: skip
        if cloud:
            for row in rows:
                row["gender"] = {"F": "Female", "M": "Male"}.get(row.get("gender", ""), row.get("gender", ""))
        return rows
    if kind == ImportJob.Kind.RESERVATIONS:
        types = cat["private"]
        if not types:
            return []
        first = next((rt for rt in types if rt.max_adults >= 2), types[0])
        second = next((rt for rt in types if rt.pk != first.pk and rt.max_children >= 1), None) or next(
            (rt for rt in types if rt.pk != first.pk), first
        )
        plan = cat["base"]
        plan_name = _name(plan, lang) if plan else ""
        rooms = cat["rooms"].get(first.pk) or []
        base = today + timedelta(days=95)

        def d(offset: int) -> str:
            return _fmt_date(base + timedelta(days=offset), lang, preset)

        def money(value: int) -> str:
            if cloud or lang == "en":
                return f"{value}.00"
            return f"{value:,}".replace(",", ".")

        def rel(offset: int) -> str:
            return _fmt_date(today + timedelta(days=offset), lang, preset)

        status = (
            {"confirmed": "Confirmed", "tentative": "Not Confirmed", "in_house": "Checked In", "cancelled": "Canceled",
             "checked_out": "Checked Out"}
            if cloud or lang == "en"
            else {"confirmed": "Confirmada", "tentative": "No confirmada", "in_house": "En casa",
                  "cancelled": "Cancelada", "checked_out": "Finalizada"}
        )  # fmt: skip
        rows = [
            {"external_id": "R-5001", "status": status["confirmed"], "checkin": d(0), "checkout": d(3),
             "adults": "2", "children": "0", "room_type": _name(first, lang), "room_number": rooms[0] if rooms else "",
             "rate_plan": plan_name, "total_amount": money(1285200), "paid_amount": money(385560),
             "first_name": "Camila", "last_name": "Restrepo Uribe", "email": "camila.restrepo@example.com",
             "phone": "+57 310 555 0142", "document_type": "CC", "document_number": "1020345678",
             "nationality": "CO", "country_of_residence": "CO", "source": "Booking.com", "eta": "15:30",
             "special_requests": "Cama extra para bebé" if lang == "es" else "Baby cot"},
            {"external_id": "R-5002", "status": status["confirmed"], "checkin": d(5), "checkout": d(9),
             "adults": "2", "children": "1", "room_type": _name(second, lang), "rate_plan": plan_name,
             "total_amount": money(1800000), "paid_amount": money(0), "first_name": "Daniel", "last_name": "Walker",
             "email": "daniel.walker@example.com", "phone": "+1 415 555 0199", "document_type": "PA",
             "document_number": "X1234567", "nationality": "US", "country_of_residence": "US", "source": "Expedia"},
            {"external_id": "R-5003", "status": status["in_house"], "checkin": rel(-2), "checkout": rel(2),
             "adults": "1", "children": "0", "room_type": _name(first, lang), "rate_plan": plan_name,
             "total_amount": money(1523200), "paid_amount": money(761600), "first_name": "Andrea", "last_name": "Gómez Salazar",
             "email": "andrea.gomez@example.com", "phone": "+57 315 555 0110", "nationality": "CO",
             "source": "Directo" if lang == "es" else "Direct"},
            {"external_id": "R-5004", "status": status["confirmed"], "checkin": d(12), "checkout": d(14),
             "adults": "2", "children": "0", "room_type": _name(first, lang), "rate_plan": plan_name,
             "total_amount": money(856800), "paid_amount": money(856800), "first_name": "Grupo", "last_name": "Andes Tours",
             "email": "reservas@andestours.example", "source": "Agencia" if lang == "es" else "Agency",
             "notes": "Grupo de 2 habitaciones" if lang == "es" else "Two-room group"},
            {"external_id": "R-5004", "status": status["confirmed"], "checkin": d(12), "checkout": d(14),
             "adults": "2", "children": "0", "room_type": _name(second, lang), "rate_plan": plan_name,
             "total_amount": money(952000), "paid_amount": money(0), "first_name": "Grupo", "last_name": "Andes Tours",
             "email": "reservas@andestours.example", "source": "Agencia" if lang == "es" else "Agency"},
            {"external_id": "R-5005", "status": status["tentative"], "checkin": d(20), "checkout": d(22),
             "adults": "2", "room_type": _name(first, lang), "rate_plan": plan_name, "total_amount": money(856800),
             "first_name": "Lukas", "last_name": "Becker", "email": "lukas.becker@example.de", "nationality": "DE",
             "country_of_residence": "DE", "source": "Airbnb"},
            {"external_id": "R-5006", "status": status["cancelled"], "checkin": d(25), "checkout": d(27),
             "adults": "2", "room_type": _name(first, lang), "rate_plan": plan_name, "total_amount": money(856800),
             "first_name": "Mariana", "last_name": "López", "email": "mariana.lopez@example.com"},
            {"external_id": "R-5007", "status": status["checked_out"], "checkin": rel(-9), "checkout": rel(-6),
             "adults": "2", "room_type": _name(first, lang), "rate_plan": plan_name, "total_amount": money(1142400),
             "first_name": "Jorge", "last_name": "Castaño", "email": "jorge.castano@example.com"},
            {"external_id": "R-5008", "status": status["confirmed"], "checkin": d(30), "checkout": d(33),
             "adults": "3", "room_type": "Suite Presidencial" if lang == "es" else "Presidential Suite",
             "rate_plan": plan_name, "total_amount": money(3600000), "first_name": "Valeria", "last_name": "Rincón",
             "email": "valeria.rincon@example.com", "nationality": "MX", "country_of_residence": "MX"},
        ]  # fmt: skip
        if cloud:
            for row in rows:
                row["full_name"] = f"{row.pop('first_name', '')} {row.pop('last_name', '')}".strip()
                row["balance_due"] = _balance(row.get("total_amount"), row.pop("paid_amount", "0"))
                row["balance_due"] = f"{row['balance_due']}.00"
                row["booked_at"] = rel(-30)
                row["nights"] = ""
            # Cloudbeds puts every room of a reservation in one row: "Standard, Superior"
            group = [row for row in rows if row["external_id"] == "R-5004"]
            if len(group) == 2:
                group[0]["room_type"] = f"{group[0]['room_type']}, {group[1]['room_type']}"
                group[0]["total_amount"] = money(1808800)
                group[0]["balance_due"] = money(952000)
                rows.remove(group[1])
        return rows
    if kind == ImportJob.Kind.ROOM_TYPES:
        free = cat["free_numbers"]
        suite = f"{free[0]}-{free[1]}" if len(free) >= 2 else ""
        dorm = free[2] if len(free) >= 3 else ""
        return [
            {"code": "SFAM", "name": "Suite Familiar", "name_en": "Family Suite", "kind": "Privada" if lang == "es" else "Private",
             "base_occupancy": "2", "max_adults": "4", "max_children": "2", "max_occupancy": "5",
             "room_numbers": suite, "base_price": "480.000",
             "description": "Dos ambientes, ideal para familias" if lang == "es" else "Two rooms, great for families"},
            {"code": "DMIX", "name": "Dormitorio Mixto", "name_en": "Mixed Dorm", "kind": "Dormitorio" if lang == "es" else "Dorm",
             "beds_per_room": "6", "room_numbers": dorm, "base_price": "65.000"},
        ]  # fmt: skip
    if kind == ImportJob.Kind.ROOMS:
        types = cat["private"]
        if not types:
            return []
        free = cat["free_numbers"]
        existing = (cat["rooms"].get(types[0].pk) or [""])[0]
        rows = [
            {"number": free[3] if len(free) > 3 else "", "room_type": _name(types[0], lang), "floor": "9",
             "name": "Mirador" if lang == "es" else "Lookout"},
            {"number": free[4] if len(free) > 4 else "", "room_type": types[-1].code, "floor": "9"},
            {"number": existing, "room_type": _name(types[0], lang), "notes": "Vista a la calle" if lang == "es" else "Street view"},
        ]  # fmt: skip
        return rows
    return []


def _balance(total: str | None, paid: str | None) -> int:
    def number(value) -> int:
        text = str(value or "0")
        text = text[:-3] if text.endswith(".00") else text
        return int(text.replace(".", "") or 0)

    return number(total) - number(paid)


# ---- Files --------------------------------------------------------------------------------------------


def build(kind: str, lang: str, fmt: str, *, prop=None, example: bool = False, preset: str = "generic"):
    """(content bytes, content type, filename)."""
    cols = columns(kind, lang, preset)
    rows = example_rows(kind, prop, lang, preset) if example and prop is not None else []
    matrix = [[title for _, title in cols]]
    for row in rows:
        matrix.append([row.get(field, "") for field, _ in cols])
    names = {
        "guests": ("huespedes", "guests"),
        "reservations": ("reservas", "reservations"),
        "room_types": ("categorias", "room-types"),
        "rooms": ("habitaciones", "rooms"),
    }[kind]
    stem = names[1] if lang == "en" else names[0]
    prefix = (
        ("ejemplo" if lang != "en" else "example")
        if example
        else ("plantilla" if lang != "en" else "template")
    )
    if preset == ImportJob.Preset.CLOUDBEDS and kind in (ImportJob.Kind.RESERVATIONS, ImportJob.Kind.GUESTS):
        stem = f"{stem}-cloudbeds"
    filename = f"housetel-{prefix}-{stem}.{fmt}"
    if fmt == "xlsx":
        return _xlsx(matrix), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename
    delimiter = "," if lang == "en" or preset == ImportJob.Preset.CLOUDBEDS else ";"
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=delimiter, lineterminator="\r\n")
    writer.writerows(matrix)
    return ("﻿" + buffer.getvalue()).encode("utf-8"), "text/csv; charset=utf-8", filename


def _xlsx(matrix: list[list[str]]) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Datos"
    for row in matrix:
        sheet.append(row)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="F3F0EB")
    for index, title in enumerate(matrix[0], start=1):
        width = max([len(str(title))] + [len(str(row[index - 1])) for row in matrix[1:]] + [8])
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = min(width + 2, 42)
    sheet.freeze_panes = "A2"
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def response(content: bytes, content_type: str, filename: str) -> HttpResponse:
    reply = HttpResponse(content, content_type=content_type)
    reply["Content-Disposition"] = f'attachment; filename="{filename}"'
    reply["Cache-Control"] = "no-store"
    return reply
