"""CSV export of the reservations list (`;`-separated UTF-8 with BOM, so Excel opens it correctly)."""

import csv
import io

from django.http import HttpResponse
from django.utils import timezone

from apps.frontdesk.services.figures import money

MAX_ROWS = 10_000

HEADERS = {
    "es": "Código;Estado;Fuente;Canal;Llegada;Salida;Noches;Adultos;Niños;Huésped;Email;Teléfono;"
    "Habitaciones;Categorías;Total;Saldo;Moneda;Creada;Grupo".split(";"),
    "en": "Code;Status;Source;Channel;Arrival;Departure;Nights;Adults;Children;Guest;Email;Phone;"
    "Rooms;Room types;Total;Balance;Currency;Created;Group".split(";"),
}
STATUS_LABELS = {
    "es": {"tentative": "Tentativa", "confirmed": "Confirmada", "checked_in": "En casa",
           "checked_out": "Finalizada", "cancelled": "Cancelada", "no_show": "No show"},
    "en": {"tentative": "Tentative", "confirmed": "Confirmed", "checked_in": "In house",
           "checked_out": "Checked out", "cancelled": "Cancelled", "no_show": "No-show"},
}  # fmt: skip
SOURCE_LABELS = {
    "es": {"walk_in": "Walk-in", "phone": "Teléfono", "email": "Email", "front_desk": "Recepción",
           "booking_engine": "Motor de reservas", "marketplace": "Marketplace", "ota": "OTA", "api": "API",
           "import": "Importación"},
    "en": {"walk_in": "Walk-in", "phone": "Phone", "email": "Email", "front_desk": "Front desk",
           "booking_engine": "Booking engine", "marketplace": "Marketplace", "ota": "OTA", "api": "API",
           "import": "Import"},
}  # fmt: skip


def reservations_csv(reservations, *, lang: str, business_date) -> HttpResponse:
    """`reservations` must be annotated with `balance` (bookings `with_balance`) and prefetch `stays` with
    their room, bed and room type. At most `MAX_ROWS` rows."""
    lang = lang if lang in HEADERS else "es"
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(HEADERS[lang])
    for reservation in reservations[:MAX_ROWS]:
        stays = list(reservation.stays.all())
        writer.writerow(
            [
                reservation.code,
                STATUS_LABELS[lang].get(reservation.status, reservation.status),
                SOURCE_LABELS[lang].get(reservation.source, reservation.source),
                reservation.channel_code,
                reservation.checkin_date.isoformat(),
                reservation.checkout_date.isoformat(),
                (reservation.checkout_date - reservation.checkin_date).days,
                reservation.adults,
                reservation.children,
                reservation.booker.full_name,
                reservation.booker.email,
                reservation.booker.phone,
                ", ".join(_unit(stay) for stay in stays if stay.room_id),
                ", ".join(dict.fromkeys(stay.room_type.code for stay in stays)),
                money(reservation.total_amount),
                money(reservation.balance),
                reservation.currency,
                timezone.localtime(reservation.created_at).strftime("%Y-%m-%d %H:%M"),
                reservation.group.name if reservation.group_id else "",
            ]
        )
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    name = "reservas" if lang == "es" else "reservations"
    response["Content-Disposition"] = f'attachment; filename="{name}-{business_date.isoformat()}.csv"'
    return response


def _unit(stay) -> str:
    return f"{stay.room.number}/{stay.bed.label}" if stay.bed_id else stay.room.number


ROOMING_HEADERS = {
    "es": "Reserva;Titular;Estado;Categoría;Habitación;Llegada;Salida;Noches;Adultos;Niños;"
    "Huésped en la habitación;Del cupo".split(";"),
    "en": "Reservation;Booker;Status;Room type;Room;Arrival;Departure;Nights;Adults;Children;"
    "Guest in the room;From the allotment".split(";"),
}
YES_NO = {"es": ("Sí", "No"), "en": ("Yes", "No")}


def rooming_csv(group, rows, *, lang: str) -> HttpResponse:
    """The group's rooming list (`bookings.services.groups.rooming_list` rows) as a CSV the hotel can send to
    the organizer and get back with the names."""
    lang = lang if lang in ROOMING_HEADERS else "es"
    yes, no = YES_NO[lang]
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\n")
    writer.writerow(ROOMING_HEADERS[lang])
    for row in rows:
        name = row["room_type"]["name"]
        room = row["room"]["number"] if row["room"] else ""
        if row["bed"]:
            room = f"{room}/{row['bed']['label']}"
        writer.writerow(
            [
                row["code"],
                row["booker_name"],
                STATUS_LABELS[lang].get(row["status"], row["status"]),
                (name.get(lang) or name.get("es") or row["room_type"]["code"])
                if isinstance(name, dict)
                else name,
                room,
                row["checkin"],
                row["checkout"],
                row["nights"],
                row["adults"],
                row["children"],
                row["guest"]["full_name"] if row["guest"] else "",
                yes if row["group_block_id"] else no,
            ]
        )
    response = HttpResponse(buffer.getvalue(), content_type="text/csv; charset=utf-8")
    slug = "".join(ch if ch.isalnum() else "-" for ch in group.name.lower()).strip("-")[:40] or "grupo"
    response["Content-Disposition"] = f'attachment; filename="rooming-{slug}.csv"'
    return response
