"""SIRE (Sistema de Información para el Reporte de Extranjeros, Migración Colombia): the bulk-upload flat
file of
the foreigners' entries (E, check-in) and exits (S, check-out) of a period.

File (assumptions and sources in docs/integration-notes/C7-compliance.md, "SIRE"): plain text, one movement
per
line, fields separated by TAB, CRLF line endings, no header, upper-case ASCII names, dates `dd/mm/aaaa`:

    establishment · city · document type · document number · nationality · surnames [· second surname] · names
    · movement (E|S) · movement date · origin · destination · birth date

The default layout has 12 columns (all surnames in one field); `ComplianceSettings.sire_second_surname_column`
switches to 13 (first and second surname apart). Codes come from `apps.compliance.codes` plus the hotel's
overrides. A movement with a missing field is kept as an incomplete `SireRecord` (listed in `report.missing`,
with
an alert) and stays out of the file until the data is fixed and the report is generated again.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.bookings.models import Stay
from apps.compliance.codes import divipola_code
from apps.compliance.models import SireRecord, SireReport
from apps.compliance.services.config import (
    get_settings,
    sire_city_code,
    sire_country_codes,
    sire_document_codes,
)
from apps.core import alerts, audit, integrations
from apps.core.errors import ConflictError, DomainError

MAX_PERIOD_DAYS = 93
LODGED_STATUSES = (Stay.Status.CHECKED_IN, Stay.Status.CHECKED_OUT)
COLUMNS = [
    "establishment", "city", "document_type", "document_number", "nationality", "surnames", "second_surname",
    "names", "movement", "movement_date", "origin", "destination", "birth_date",
]  # fmt: skip
REQUIRED = ["establishment", "city", "document_type", "document_number", "nationality", "surnames", "names",
            "movement_date", "origin", "destination", "birth_date"]  # fmt: skip
SURNAME_PARTICLES = {"DE", "DEL", "LA", "LAS", "LOS", "SAN", "SANTA", "VAN", "VON", "DER", "DEN", "DA",
"DI", "DO",
                     "DOS", "DAS", "DU", "LE", "DELLA", "DELLE"}  # fmt: skip
MISSING_ALERT = "compliance:sire:missing"
UNSUBMITTED_ALERT = "compliance:sire:unsubmitted"


def _count(count: int, singular: str, plural: str) -> str:
    """«1 movimiento», «2 movimientos» (never «1 movimientos» or «archivo(s)»)."""
    return f"{count} {singular if count == 1 else plural}"


# ------------------------------------------------------------------------------------------------- guests


def lodged_guests(stay) -> list:
    """Who slept in `stay`: its occupants, plus the booker in the first stay of the reservation unless the
    booker
    is registered as an occupant of another stay."""
    from apps.guests.models import Guest

    through = Stay.occupants.through
    occupant_ids = list(
        through.objects.filter(stay_id=stay.pk).order_by("id").values_list("guest_id", flat=True)
    )
    reservation = stay.reservation
    ids = []
    if reservation.booker_id not in occupant_ids:
        first = (
            Stay.objects.filter(reservation_id=reservation.pk)
            .order_by("created_at", "pk")
            .values("pk")
            .first()
        )
        elsewhere = (
            through.objects.filter(stay__reservation_id=reservation.pk, guest_id=reservation.booker_id)
            .exclude(stay_id=stay.pk)
            .exists()
        )
        if first and first["pk"] == stay.pk and not elsewhere:
            ids.append(reservation.booker_id)
    ids += occupant_ids
    guests = Guest.objects.in_bulk(ids)
    return [guests[pk] for pk in ids if pk in guests]


def travel_data(reservation) -> dict:
    """Travel data of the online check-in (apps.guestportal): {guest_id: {travel_reason, origin,
    destination}}."""
    try:
        from apps.guestportal.models import OnlineCheckin
    except ImportError:  # pragma: no cover - the portal app is optional for compliance
        return {}
    checkin = OnlineCheckin.objects.filter(reservation_id=reservation.pk).only("data").first()
    return ((checkin.data or {}).get("travel") or {}) if checkin else {}


def plain(value: str) -> str:
    """Upper-case ASCII without accents, tabs or double spaces (what the SIRE flat file accepts)."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c)).encode("ascii", "ignore").decode()
    return " ".join(text.upper().split())


def split_surnames(last_name: str) -> tuple[str, str]:
    """ "Smith Brown" → ("SMITH", "BROWN"); particles stay with the next word ("DE LA HOZ")."""
    groups, pending = [], []
    for word in plain(last_name).split():
        pending.append(word)
        if word not in SURNAME_PARTICLES:
            groups.append(" ".join(pending))
            pending = []
    if pending:
        groups.append(" ".join(pending))
    if not groups:
        return "", ""
    return groups[0], " ".join(groups[1:])


# --------------------------------------------------------------------------------------------------- rows


@dataclass
class Movement:
    movement: str  # "E" | "S"
    day: date
    stay: Stay
    guest: object


def _place_code(text: str, countries: dict) -> str:
    """A travel place typed in the online check-in → DIVIPOLA city or SIRE country code ("" if unknown)."""
    city = divipola_code(text)
    if city:
        return city
    iso = (text or "").strip().upper()
    return countries.get(iso, "") if len(iso) == 2 else ""


def build_row(settings, movement: Movement, *, travel: dict, documents: dict, countries: dict, city: str):
    guest = movement.guest
    surnames, second = split_surnames(guest.last_name)
    home = countries.get((guest.country_of_residence or guest.nationality or "").upper(), "")
    if movement.movement == SireRecord.Movement.ENTRY:
        origin = _place_code(travel.get("origin", ""), countries) or home
        destination = city
    else:
        origin = city
        typed = _place_code(travel.get("destination", ""), countries)
        destination = typed if typed and typed != city else home
    data = {
        "establishment": plain(settings.sire_establishment_code),
        "city": city,
        "document_type": documents.get((guest.document_type or "").upper(), ""),
        "document_number": plain(guest.document_number).replace(" ", ""),
        "nationality": countries.get((guest.nationality or "").upper(), ""),
        "surnames": plain(guest.last_name),
        "first_surname": surnames,
        "second_surname": second,
        "names": plain(guest.first_name),
        "movement": movement.movement,
        "movement_date": movement.day.strftime("%d/%m/%Y"),
        "origin": origin,
        "destination": destination,
        "birth_date": guest.birth_date.strftime("%d/%m/%Y") if guest.birth_date else "",
    }
    missing = [field for field in REQUIRED if not data[field]]
    return data, missing


def row_values(data: dict, *, second_surname_column: bool) -> list[str]:
    if second_surname_column:
        values = [data["first_surname"], data["second_surname"]]
    else:
        values = [data["surnames"]]
    head = [data[k] for k in ("establishment", "city", "document_type", "document_number", "nationality")]
    tail = [data[k] for k in ("names", "movement", "movement_date", "origin", "destination", "birth_date")]
    return head + values + tail


# --------------------------------------------------------------------------------------------- movements


def movements(property, start: date, end: date) -> tuple[list[Movement], list[dict]]:
    """Movements of foreign guests in `[start, end]` (inclusive) and guests whose nationality is unknown."""
    stays = (
        Stay.objects.filter(reservation__property=property, status__in=LODGED_STATUSES)
        .filter(
            Q(checkin_date__range=(start, end)) | Q(checkout_date__range=(start, end), status="checked_out")
        )
        .select_related("reservation")
        .order_by("checkin_date", "created_at")
    )
    found, unknown = [], []
    for stay in stays:
        guests = lodged_guests(stay)
        events = []
        if start <= stay.checkin_date <= end:
            events.append((SireRecord.Movement.ENTRY, stay.checkin_date))
        if stay.status == Stay.Status.CHECKED_OUT and start <= stay.checkout_date <= end:
            events.append((SireRecord.Movement.EXIT, stay.checkout_date))
        for guest in guests:
            nationality = (guest.nationality or "").upper()
            if nationality == "CO":
                continue
            for movement, day in events:
                if not nationality:
                    unknown.append(_missing_entry(guest, stay, movement, day, ["nationality"], record=False))
                else:
                    found.append(Movement(movement, day, stay, guest))
    found.sort(key=lambda m: (m.day, m.movement != "E", plain(m.guest.last_name), plain(m.guest.first_name)))
    return found, unknown


def _missing_entry(guest, stay, movement, day, fields, *, record=True) -> dict:
    return {
        "guest_id": str(guest.pk),
        "guest_name": guest.full_name,
        "reservation_id": str(stay.reservation_id),
        "reservation_code": stay.reservation.code,
        "stay_id": str(stay.pk),
        "movement": movement,
        "movement_date": day.isoformat(),
        "fields": fields,
        "record": record,
    }


# ------------------------------------------------------------------------------------------------ reports


def generate_sire(property, start: date, end: date, *, actor=None, source="user") -> SireReport:
    """Build the SIRE report of `[start, end]` (inclusive): records, file and missing data. A report of the
    same
    period that was not submitted yet is replaced."""
    if end < start:
        raise DomainError("La fecha final no puede ser anterior a la inicial", code="invalid_period")
    if (end - start).days + 1 > MAX_PERIOD_DAYS:
        raise DomainError(f"El periodo no puede superar {MAX_PERIOD_DAYS} días", code="invalid_period")
    settings = get_settings(property)
    documents, countries, city = (
        sire_document_codes(settings),
        sire_country_codes(settings),
        sire_city_code(settings),
    )
    found, unknown = movements(property, start, end)
    user = actor if actor is not None and getattr(actor, "is_authenticated", False) else None
    with transaction.atomic():
        superseded = SireReport.objects.filter(
            property=property, period_start=start, period_end=end, status=SireReport.Status.GENERATED
        )
        for old in superseded:
            old.file.delete(save=False)
        superseded.delete()
        report = SireReport.objects.create(
            property=property,
            period_start=start,
            period_end=end,
            mode=integrations.get_setting(property, "sire").mode,
            generated_by=user,
        )
        records, missing, travel_cache = [], list(unknown), {}
        for movement in found:
            reservation = movement.stay.reservation
            if reservation.pk not in travel_cache:
                travel_cache[reservation.pk] = travel_data(reservation)
            travel = travel_cache[reservation.pk].get(str(movement.guest.pk)) or {}
            data, fields = build_row(
                settings, movement, travel=travel, documents=documents, countries=countries, city=city
            )
            records.append(
                SireRecord(
                    report=report,
                    guest=movement.guest,
                    stay=movement.stay,
                    movement=movement.movement,
                    movement_date=movement.day,
                    complete=not fields,
                    missing_fields=fields,
                    data=data,
                )
            )
            if fields:
                missing.append(
                    _missing_entry(movement.guest, movement.stay, movement.movement, movement.day, fields)
                )
        SireRecord.objects.bulk_create(records)
        complete = [r for r in records if r.complete]
        report.records_count = len(complete)
        report.missing = missing
        content = render_sire_lines(complete, second_surname_column=settings.sire_second_surname_column)
        report.file.save(_file_name(settings, start, end), ContentFile(content.encode("utf-8")), save=False)
        report.save()
        audit.record(
            action="compliance.sire_generated",
            target=report,
            summary=f"Archivo SIRE {start:%d/%m/%Y}–{end:%d/%m/%Y}: "
            f"{_count(len(complete), 'movimiento', 'movimientos')}, {len(missing)} con datos faltantes",
            actor=actor,
            source=source,
            property=property,
            changes={"records": [None, len(complete)], "missing": [None, len(missing)]},
        )
    refresh_alerts(property)
    return report


def render_sire_lines(records, *, second_surname_column: bool) -> str:
    return "".join(
        "\t".join(row_values(record.data, second_surname_column=second_surname_column)) + "\r\n"
        for record in records
    )


def _file_name(settings, start: date, end: date) -> str:
    code = plain(settings.sire_establishment_code).replace(" ", "") or "SINCODIGO"
    return f"SIRE-{code}-{start:%Y%m%d}-{end:%Y%m%d}.txt"


def mark_submitted(report, *, actor=None, ack_code: str = "", source="user") -> SireReport:
    """Record that the file was uploaded to the SIRE portal. Simulated mode answers with an acknowledgement;
    in
    real mode the user may type the portal's receipt (now or later)."""
    ack_code = (ack_code or "").strip()
    with transaction.atomic():
        report = SireReport.objects.select_for_update().get(pk=report.pk)
        if report.status == SireReport.Status.ACKNOWLEDGED or (
            report.status == SireReport.Status.SUBMITTED and not ack_code
        ):
            raise ConflictError("Este archivo SIRE ya fue reportado", code="invalid_state")
        user = actor if actor is not None and getattr(actor, "is_authenticated", False) else None
        before = report.status
        if report.status == SireReport.Status.GENERATED:
            result = integrations.get_provider(report.property, "sire").submit(report)
            report.status = result["status"]
            report.ack_code = ack_code or result.get("ack_code", "")
            report.submitted_at = timezone.now()
            report.submitted_by = user
        if ack_code:
            report.ack_code = ack_code
            report.status = SireReport.Status.ACKNOWLEDGED
        report.save()
        audit.record(
            action="compliance.sire_submitted",
            target=report,
            summary=f"Archivo SIRE {report.period_start:%d/%m/%Y}–{report.period_end:%d/%m/%Y} reportado"
            + (f" (acuse {report.ack_code})" if report.ack_code else ""),
            actor=actor,
            source=source,
            property=report.property,
            changes={"status": [before, report.status]},
        )
    refresh_alerts(report.property)
    return report


def refresh_alerts(property) -> None:
    """Raise or resolve the SIRE alerts from the reports still waiting to be uploaded."""
    pending = list(SireReport.objects.filter(property=property, status=SireReport.Status.GENERATED))
    missing = sum(len(report.missing or []) for report in pending)
    if missing:
        latest = max(pending, key=lambda r: r.generated_at)
        alerts.raise_alert(
            property=property,
            kind="sire_missing_data",
            severity="warning",
            title="SIRE: "
            + _count(missing, "movimiento de extranjero", "movimientos de extranjeros")
            + " con datos faltantes",
            message="Completa los datos de los huéspedes (documento, nacionalidad, fecha de nacimiento…) y "
            "genera "
            "de nuevo el archivo: los movimientos incompletos no se incluyen.",
            link=f"/app/compliance?tab=sire&report={latest.pk}",
            dedupe_key=MISSING_ALERT,
            data={"count": missing, "report_id": str(latest.pk)},
            source="compliance",
        )
    else:
        alerts.resolve_alert(property, MISSING_ALERT)
    if pending:
        alerts.raise_alert(
            property=property,
            kind="sire_unsubmitted",
            severity="warning",
            title=_count(len(pending), "archivo SIRE", "archivos SIRE") + " por cargar en Migración Colombia",
            message=(
                "Descarga el archivo, súbelo en el portal SIRE y márcalo como reportado."
                if len(pending) == 1
                else "Descarga los archivos, súbelos en el portal SIRE y márcalos como reportados."
            ),
            link="/app/compliance?tab=sire",
            dedupe_key=UNSUBMITTED_ALERT,
            data={"count": len(pending)},
            source="compliance",
        )
    else:
        alerts.resolve_alert(property, UNSUBMITTED_ALERT)


def sire_daily_file(property) -> dict:
    """Automation `compliance.sire_daily_file`: yesterday's file (business date − 1), unless a report already
    covers that day."""
    day = property.business_date - timedelta(days=1)
    if SireReport.objects.filter(property=property, period_start__lte=day, period_end__gte=day).exists():
        return {"status": "skipped", "date": day.isoformat(), "reason": "already_generated"}
    found, unknown = movements(property, day, day)
    if not found and not unknown:
        return {"status": "skipped", "date": day.isoformat(), "reason": "no_movements"}
    report = generate_sire(property, day, day, source="automation")
    return {
        "status": "generated",
        "date": day.isoformat(),
        "report_id": str(report.pk),
        "records": report.records_count,
        "missing": len(report.missing),
    }
