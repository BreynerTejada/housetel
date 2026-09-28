"""Online check-in (plan C5): guests (TRA/SIRE data) → documents → arrival → signature and terms → complete.

- Guest slots: one per expected guest of each active stay (adults + children, at least one). The booker is the
  first guest of the first stay; companions are `Stay.occupants` (added with `bookings.add_occupant`).
- Identity data is written to `guests.Guest` through `update_guest` (booker, known companions) and
  `upsert_guest` (new companions). Travel data (motivo de viaje, procedencia, destino) belongs to the stay and
  lives in `OnlineCheckin.data["travel"][<guest_id>]`; companions inherit the booker's when left empty.
- Identity documents are `GuestDocument` rows created with `guests.add_document(uploaded_via="portal")`
  (private storage). The signature is a PNG in the same private storage.
- Completion validates everything (`missing_items`), marks the check-in `completed` and emits
  `guest_checked_in_online(reservation)` after commit, once.
"""

import base64
import binascii
import io
import re
from dataclasses import dataclass
from datetime import date, time
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from apps.bookings.models import ACTIVE_STAY_STATUSES, Stay
from apps.bookings.services.reservations import add_occupant, update_reservation
from apps.core import alerts, audit
from apps.core.errors import ConflictError, DomainError
from apps.core.signals import guest_checked_in_online, send_on_commit
from apps.guestportal.models import OnlineCheckin
from apps.guestportal.services.access import (
    checkin_window,
    ensure_checkin,
    portal_settings,
    terms_of,
)
from apps.guestportal.services.summary import (
    balance_of,
    property_payload,
    reservation_payload,
    stay_payload,
    stays_of,
)
from apps.guests.models import Guest, GuestDocument
from apps.guests.normalization import fold, is_usable_phone, normalize_document, similar_last_names
from apps.guests.services import add_document, document_owner, phone_region, update_guest, upsert_guest
from apps.guests.types import GuestInput

STEPS = [choice for choice, _ in OnlineCheckin.Step.choices]
IDENTITY_FIELDS = (
    "first_name",
    "last_name",
    "document_type",
    "document_number",
    "nationality",
    "country_of_residence",
    "birth_date",
)
CONTACT_FIELDS = ("city_of_residence", "email", "phone")
TRAVEL_FIELDS = ("travel_reason", "origin", "destination")
# Motivo de viaje (Tarjeta de Registro Alojamiento / DANE); the portal shows them translated.
TRAVEL_REASONS = ["leisure", "business", "family", "education", "health", "religion", "shopping", "transit",
                  "other"]  # fmt: skip
DOCUMENT_KINDS = ["id_front", "id_back", "passport", "other"]
ADULT_AGE = 18
COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
MAX_SIGNATURE_BYTES = 1_500_000
MAX_SIGNATURE_SIDE = 4000
REQUIRED = "Este dato es obligatorio"


class CheckinClosed(ConflictError):
    code = "checkin_closed"


class DocumentInUse(ConflictError):
    code = "document_in_use"


# --- slots ------------------------------------------------------------------------------------------------


@dataclass
class Slot:
    index: int
    stay: Stay
    role: str  # booker | companion
    guest: Guest | None
    child: bool = False  # an empty slot beyond the stay's adults: a child is expected there


def active_stays(reservation) -> list[Stay]:
    return [stay for stay in stays_of(reservation) if stay.status in ACTIVE_STAY_STATUSES]


def ordered_occupants(stay) -> list[Guest]:
    """Occupants in the order they were added (the M2M rows keep it)."""
    through = Stay.occupants.through
    rows = through.objects.filter(stay_id=stay.pk).select_related("guest").order_by("id")
    return [row.guest for row in rows]


def guest_slots(reservation, stays=None) -> list[Slot]:
    stays = active_stays(reservation) if stays is None else stays
    booker = reservation.booker
    slots: list[Slot] = []
    for position, stay in enumerate(stays):
        registered = [("booker", booker)] if position == 0 else []
        registered += [("companion", guest) for guest in ordered_occupants(stay) if guest.pk != booker.pk]
        expected = max(stay.adults + stay.children, 1)
        for role, guest in registered:
            slots.append(Slot(len(slots), stay, role, guest))
        for seat in range(len(registered), expected):
            slots.append(Slot(len(slots), stay, "companion", None, child=seat >= max(stay.adults, 1)))
    return slots


def is_adult(guest, on: date) -> bool:
    """Unknown birth date counts as adult (the document is asked for)."""
    born = guest.birth_date
    if born is None:
        return True
    years = on.year - born.year - ((on.month, on.day) < (born.month, born.day))
    return years >= ADULT_AGE


def identity_complete(guest) -> bool:
    return all(getattr(guest, field) for field in IDENTITY_FIELDS)


def travel_of(checkin, guest) -> dict:
    if checkin is None or guest is None:
        return {}
    return dict((checkin.data or {}).get("travel", {}).get(str(guest.pk), {}))


def travel_complete(checkin, guest) -> bool:
    travel = travel_of(checkin, guest)
    return all(travel.get(field) for field in TRAVEL_FIELDS)


def slot_complete(slot, checkin) -> bool:
    if slot.guest is None or not identity_complete(slot.guest):
        return False
    return slot.role != "booker" or travel_complete(checkin, slot.guest)


def guests_with_documents(guest_ids) -> set:
    return set(
        GuestDocument.objects.filter(guest_id__in=list(guest_ids))
        .exclude(kind=GuestDocument.Kind.SIGNATURE)
        .values_list("guest_id", flat=True)
    )


def guests_needing_documents(reservation, slots) -> list[Guest]:
    guests = [slot.guest for slot in slots if slot.guest is not None]
    with_documents = guests_with_documents(guest.pk for guest in guests)
    return [
        guest
        for guest in guests
        if guest.pk not in with_documents and is_adult(guest, reservation.checkin_date)
    ]


def missing_items(reservation, checkin, settings, slots=None) -> list[dict]:
    """What still blocks completion: `guest_data` (per slot), `document` (per adult without one, when the
    hotel requires it), `signature` / `terms`."""
    slots = guest_slots(reservation) if slots is None else slots
    missing = [
        {
            "code": "guest_data",
            "slot": slot.index,
            "stay_id": str(slot.stay.pk),
            "guest_id": str(slot.guest.pk) if slot.guest else None,
        }
        for slot in slots
        if not slot_complete(slot, checkin)
    ]
    if settings.require_document_photo:
        missing += [
            {"code": "document", "guest_id": str(guest.pk)}
            for guest in guests_needing_documents(reservation, slots)
        ]
    signed = bool(checkin and checkin.signature)
    accepted = bool(checkin and checkin.accepted_terms_at)
    if settings.require_signature and not (signed and accepted):
        missing.append({"code": "signature"})
    elif not accepted:
        missing.append({"code": "terms"})
    return missing


# --- reading --------------------------------------------------------------------------------------------


def document_hint(number: str) -> str:
    return "••••" + (number[-4:] if len(number) > 4 else "")


def _guest_data(slot) -> dict:
    guest = slot.guest
    if guest is None:
        return {}
    if slot.role == "booker":  # the link holder's own profile
        return {
            "first_name": guest.first_name,
            "last_name": guest.last_name,
            "document_type": guest.document_type,
            "document_number": guest.document_number,
            "nationality": guest.nationality,
            "country_of_residence": guest.country_of_residence,
            "city_of_residence": guest.city_of_residence,
            "birth_date": guest.birth_date.isoformat() if guest.birth_date else None,
            "email": guest.email,
            "phone": guest.phone,
        }
    # companions: the portal never reveals what the hotel already knows about them
    return {
        "first_name": guest.first_name,
        "last_name": guest.last_name,
        "nationality": guest.nationality,
        "document_type": guest.document_type,
        "document_hint": document_hint(guest.document_number) if guest.document_number else "",
    }


def _expected(slot, reservation) -> str:
    """`child` for a registered minor or an empty slot the booking holds for a child; else `adult`."""
    if slot.guest is not None:
        return "adult" if is_adult(slot.guest, reservation.checkin_date) else "child"
    return "child" if slot.child else "adult"


def checkin_payload(reservation) -> dict:
    prop = reservation.property
    settings = portal_settings(prop)
    checkin = OnlineCheckin.objects.filter(reservation=reservation).first()
    stays = stays_of(reservation)
    slots = guest_slots(reservation, [stay for stay in stays if stay.status in ACTIVE_STAY_STATUSES])
    guest_ids = [slot.guest.pk for slot in slots if slot.guest]
    documents: dict = {}
    for document in GuestDocument.objects.filter(guest_id__in=guest_ids).exclude(kind="signature"):
        documents.setdefault(document.guest_id, []).append(
            {
                "id": str(document.pk),
                "kind": document.kind,
                "uploaded_via": document.uploaded_via,
                "created_at": document.created_at.isoformat(),
            }
        )
    return {
        "status": checkin.status if checkin else OnlineCheckin.Status.NOT_STARTED,
        "current_step": checkin.current_step if checkin else OnlineCheckin.Step.GUESTS,
        "completed_at": checkin.completed_at.isoformat() if checkin and checkin.completed_at else None,
        "window": checkin_window(reservation, settings).as_dict(),
        "settings": {
            "require_document_photo": settings.require_document_photo,
            "require_signature": settings.require_signature,
        },
        "terms": terms_of(settings),
        "travel_reasons": TRAVEL_REASONS,
        "property": property_payload(prop),
        "reservation": reservation_payload(reservation),
        "stays": [stay_payload(stay) for stay in stays],
        "guests": [
            {
                "slot": slot.index,
                "stay_id": str(slot.stay.pk),
                "role": slot.role,
                "guest_id": str(slot.guest.pk) if slot.guest else None,
                "complete": slot_complete(slot, checkin),
                "is_adult": is_adult(slot.guest, reservation.checkin_date) if slot.guest else not slot.child,
                "expected": _expected(slot, reservation),
                "data": _guest_data(slot),
                "travel": travel_of(checkin, slot.guest),
                "documents": documents.get(slot.guest.pk, []) if slot.guest else [],
            }
            for slot in slots
        ],
        "eta": checkin.eta.strftime("%H:%M") if checkin and checkin.eta else None,
        "signature": {
            "signed": bool(checkin and checkin.signature),
            "accepted_terms_at": checkin.accepted_terms_at.isoformat()
            if checkin and checkin.accepted_terms_at
            else None,
        },
        "missing": missing_items(reservation, checkin, settings, slots),
        "balance": balance_of(reservation),
    }


# --- writing: helpers -------------------------------------------------------------------------------------


def require_open(reservation):
    """The portal settings of the reservation's property; CheckinClosed (409) outside the window."""
    settings = portal_settings(reservation.property)
    window = checkin_window(reservation, settings)
    if not window.is_open:
        raise CheckinClosed(
            "El check-in online no está disponible para esta reserva",
            reason=window.reason,
            opens_on=window.opens_on,
        )
    return settings


def _open_checkin(reservation):
    """Lock (creating it the first time) the reservation's check-in; CheckinClosed outside the window."""
    settings = require_open(reservation)
    ensure_checkin(reservation)
    checkin = OnlineCheckin.objects.select_for_update().get(reservation=reservation)
    return checkin, settings


def _advance(checkin, step: str) -> None:
    if STEPS.index(step) > STEPS.index(checkin.current_step):
        checkin.current_step = step
    if checkin.status == OnlineCheckin.Status.NOT_STARTED:
        checkin.status = OnlineCheckin.Status.IN_PROGRESS


def _save(checkin, meta) -> None:
    checkin.ip = (meta or {}).get("ip") or checkin.ip
    checkin.user_agent = (meta or {}).get("user_agent") or checkin.user_agent
    checkin.save()


def _text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _date(value, errors, key):
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        errors[key] = ["Usa el formato AAAA-MM-DD"]
        return None
    if parsed > timezone.localdate() or parsed.year < 1900:
        errors[key] = ["Fecha de nacimiento inválida"]
        return None
    return parsed


def clean_entry(raw, index: int, errors: dict) -> dict | None:
    """Validate one guest entry of the `guests` step; errors go to `errors["guests.<index>.<field>"]`."""
    prefix = f"guests.{index}."
    if not isinstance(raw, dict):
        errors[f"guests.{index}"] = ["Datos inválidos"]
        return None
    entry = {
        "stay_id": _text(raw.get("stay_id"), 64),
        "role": _text(raw.get("role"), 20) or "companion",
        "guest_id": _text(raw.get("guest_id"), 64) or None,
        "keep": bool(raw.get("keep")),
    }
    if entry["role"] not in ("booker", "companion"):
        errors[prefix + "role"] = ["Rol inválido"]
    if not entry["stay_id"]:
        errors[prefix + "stay_id"] = [REQUIRED]
    if entry["keep"]:
        if not entry["guest_id"] or entry["role"] == "booker":
            errors[prefix + "keep"] = ["Solo se conservan acompañantes ya registrados"]
        return entry
    values = {
        "first_name": _text(raw.get("first_name"), 100),
        "last_name": _text(raw.get("last_name"), 100),
        "document_type": _text(raw.get("document_type"), 10).upper(),
        "document_number": normalize_document(_text(raw.get("document_number"), 40)),
        "nationality": _text(raw.get("nationality"), 2).upper(),
        "country_of_residence": _text(raw.get("country_of_residence"), 2).upper(),
        "city_of_residence": _text(raw.get("city_of_residence"), 100),
        "email": _text(raw.get("email"), 254).lower(),
        "phone": _text(raw.get("phone"), 32),
        "birth_date": _date(raw.get("birth_date"), errors, prefix + "birth_date"),
    }
    for field in IDENTITY_FIELDS:
        if not values[field] and prefix + field not in errors:
            errors[prefix + field] = [REQUIRED]
    if values["document_type"] and values["document_type"] not in Guest.DocumentType.values:
        errors[prefix + "document_type"] = ["Tipo de documento inválido"]
    for field in ("nationality", "country_of_residence"):
        if values[field] and not COUNTRY_CODE.match(values[field]):
            errors[prefix + field] = ["Usa el código ISO de dos letras del país (CO, US, ES…)"]
    if values["email"] and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", values["email"]):
        errors[prefix + "email"] = ["Escribe un correo válido"]
    region = phone_region(values["country_of_residence"], values["nationality"])
    if values["phone"] and not is_usable_phone(values["phone"], region=region):
        errors[prefix + "phone"] = ["Escribe un teléfono válido (con el indicativo si no es de Colombia)"]
    travel = {
        "travel_reason": _text(raw.get("travel_reason"), 20),
        "origin": _text(raw.get("origin"), 120),
        "destination": _text(raw.get("destination"), 120),
    }
    if travel["travel_reason"] and travel["travel_reason"] not in TRAVEL_REASONS:
        errors[prefix + "travel_reason"] = ["Motivo de viaje inválido"]
    if entry["role"] == "booker":
        for field in TRAVEL_FIELDS:
            if not travel[field] and prefix + field not in errors:
                errors[prefix + field] = [REQUIRED]
    return {**entry, "values": values, "travel": travel}


def _identity_update(values) -> dict:
    """Fields written on an existing guest: identity always, contact data only when given (the portal never
    erases how the hotel reaches the guest)."""
    data = {field: values[field] for field in IDENTITY_FIELDS}
    data.update({field: values[field] for field in CONTACT_FIELDS if values[field]})
    return data


def _flag_duplicate(reservation, owner, guest=None) -> None:
    """Tell the hotel that a document typed on the portal belongs to another profile (`guest` = the profile
    being edited; None for a new companion, whose typed data is not saved)."""
    if guest is not None:
        message = (
            "En el check-in online se escribió un documento que ya pertenece a otro perfil. Revisa los dos "
            "perfiles y fusiónalos para que el huésped pueda completar su registro."
        )
    else:
        message = (
            f"En el check-in online se escribió para un acompañante un documento que ya pertenece a "
            f"{owner.full_name}, con otro nombre. Verifica los datos con el huésped a su llegada."
        )
    subject = guest or owner
    alerts.raise_alert(
        property=reservation.property,
        kind="guestportal_duplicate_guest",
        severity="warning",
        title=f"Posible huésped duplicado en {reservation.code}",
        message=message,
        link=f"/app/guests/{subject.pk}",
        dedupe_key=f"guestportal:duplicate:{reservation.pk}:{subject.pk}",
        data={
            "reservation_id": str(reservation.pk),
            "reservation_code": reservation.code,
            "guest_ids": sorted({str(subject.pk), str(owner.pk)}),
        },
        source="guest",
    )


def same_person(guest, values) -> bool:
    """A typed companion is the profile that holds the document when the first given name matches and the
    surname is the same or close (accents, case, second surname: "ana maria PEREZ" ~ "Ana María Pérez
    Gómez")."""
    typed, known = fold(values["first_name"]).split(), fold(guest.first_name).split()
    return (
        bool(typed and known)
        and typed[0] == known[0]
        and similar_last_names(guest.last_name, values["last_name"])
    )


def _fill_empty(guest, values) -> Guest:
    """A returning guest keeps the profile the hotel knows; the portal only completes what is missing."""
    empty = {
        field: values[field]
        for field in (*IDENTITY_FIELDS, *CONTACT_FIELDS)
        if values[field] not in ("", None) and getattr(guest, field) in ("", None)
    }
    return update_guest(guest, empty, source="guest") if empty else guest


# --- writing: steps -------------------------------------------------------------------------------------


def save_guests(reservation, entries, *, meta=None) -> OnlineCheckin:
    """The `guests` step: validates every entry, then writes the booker (`update_guest`), known companions
    (`update_guest`) and new companions (`upsert_guest` + `add_occupant`) and the travel data, atomically."""
    require_open(reservation)
    if not isinstance(entries, list) or not entries:
        raise DomainError("Incluye los datos de los huéspedes", code="validation_error",
                          fields={"guests": [REQUIRED]})  # fmt: skip
    errors: dict = {}
    cleaned = [clean_entry(raw, index, errors) for index, raw in enumerate(entries)]
    if sum(1 for entry in cleaned if entry and entry["role"] == "booker") != 1:
        errors.setdefault("guests", ["Incluye una vez los datos del titular de la reserva"])
    if errors:
        raise DomainError("Revisa los datos de los huéspedes", code="validation_error", fields=errors)

    stays = {str(stay.pk): stay for stay in active_stays(reservation)}
    booker = reservation.booker
    organization = reservation.property.organization
    keys = set()
    for index, entry in enumerate(cleaned):
        if entry["stay_id"] not in stays:
            errors[f"guests.{index}.stay_id"] = ["La habitación no pertenece a esta reserva"]
        if entry["keep"]:
            continue
        key = (entry["values"]["document_type"], entry["values"]["document_number"])
        if key in keys:
            raise DomainError("Registraste dos veces a la misma persona", code="duplicate_guest", index=index)
        keys.add(key)
    if errors:
        raise DomainError("Revisa los datos de los huéspedes", code="validation_error", fields=errors)
    _check_capacity(cleaned, stays, booker)

    # A document that already belongs to another profile is never taken over from a public link. A new
    # companion who holds it under the same name is a returning guest: linked as the hotel knows them.
    for entry in cleaned:
        if entry["keep"]:
            continue
        target = booker if entry["role"] == "booker" else _known_companion(entry, stays)
        values = entry["values"]
        owner = document_owner(
            organization, values["document_type"], values["document_number"], exclude=target
        )
        if owner is None or (target is not None and owner.pk == target.pk):
            continue
        if (
            target is None
            and entry["role"] == "companion"
            and not entry["guest_id"]
            and same_person(owner, values)
        ):
            entry["returning"] = owner
            continue
        _flag_duplicate(reservation, owner, target)
        raise DocumentInUse(
            "Ese documento ya está registrado en otro perfil del hotel. Le avisamos al equipo para "
            "unificar tus datos; puedes intentarlo más tarde o terminar el registro en recepción."
        )

    with transaction.atomic():
        checkin, _settings = _open_checkin(reservation)
        data = dict(checkin.data or {})
        travel_by_guest = dict(data.get("travel", {}))
        booker_travel = next(entry["travel"] for entry in cleaned if entry["role"] == "booker")
        resolved = set()
        for index, entry in enumerate(cleaned):
            stay = stays[entry["stay_id"]]
            guest = _write_entry(reservation, entry, stay, booker, organization)
            if guest.pk in resolved or (entry["role"] != "booker" and guest.pk == booker.pk):
                raise DomainError(
                    "Registraste dos veces a la misma persona", code="duplicate_guest", index=index
                )
            resolved.add(guest.pk)
            if not entry["keep"]:
                travel = {field: entry["travel"][field] or booker_travel[field] for field in TRAVEL_FIELDS}
                travel_by_guest[str(guest.pk)] = travel
        data["travel"] = travel_by_guest
        data["steps"] = sorted(set(data.get("steps", [])) | {"guests"})
        checkin.data = data
        _advance(checkin, OnlineCheckin.Step.DOCUMENTS)
        _save(checkin, meta)
    return checkin


def _check_capacity(cleaned, stays, booker) -> None:
    """A public link never adds more people to a room than the booking holds: new companions fit in the free
    slots of their stay (expected guests minus the booker on the first stay and the registered occupants)."""
    first_stay_id = next(iter(stays), None)
    new_by_stay: dict[str, int] = {}
    for entry in cleaned:
        if entry["role"] == "companion" and not entry["guest_id"] and not entry["keep"]:
            new_by_stay[entry["stay_id"]] = new_by_stay.get(entry["stay_id"], 0) + 1
    for stay_id, count in new_by_stay.items():
        stay = stays[stay_id]
        registered = stay.occupants.exclude(pk=booker.pk).count() + (1 if stay_id == first_stay_id else 0)
        expected = max(stay.adults + stay.children, 1)
        if registered + count > expected:
            raise DomainError(
                f"La habitación es para {expected} huésped(es): quita a quien sobra o pídele el cambio al "
                "hotel",
                code="too_many_guests",
                stay_id=stay_id,
                expected=expected,
            )


def _known_companion(entry, stays):
    if not entry["guest_id"] or entry["stay_id"] not in stays:
        return None
    stay = stays[entry["stay_id"]]
    return stay.occupants.filter(pk=entry["guest_id"]).first()


def _write_entry(reservation, entry, stay, booker, organization) -> Guest:
    if entry["role"] == "booker":
        return update_guest(booker, _identity_update(entry["values"]), source="guest")
    if entry["guest_id"]:
        guest = stay.occupants.filter(pk=entry["guest_id"]).first()
        if guest is None:
            raise DomainError("Ese huésped no está registrado en esta habitación", code="invalid_guest")
        if entry["keep"]:
            return guest
        return update_guest(guest, _identity_update(entry["values"]), source="guest")
    values = entry["values"]
    if entry.get("returning") is not None:
        guest = _fill_empty(entry["returning"], values)
    else:
        # nobody holds the document (checked above); the email is written afterwards so a public link
        # never lands on another profile that happens to share it
        guest = upsert_guest(
            organization,
            GuestInput(
                first_name=values["first_name"],
                last_name=values["last_name"],
                phone=values["phone"],
                document_type=values["document_type"],
                document_number=values["document_number"],
                nationality=values["nationality"],
                country_of_residence=values["country_of_residence"],
                city_of_residence=values["city_of_residence"],
                birth_date=values["birth_date"],
                language=reservation.language or "es",
            ),
        )
        if values["email"] and guest.email != values["email"]:
            guest = update_guest(guest, {"email": values["email"]}, source="guest")
    if guest.pk != booker.pk:
        add_occupant(stay, guest)
    return guest


def reservation_guest(reservation, guest_id) -> Guest:
    """The booker or an occupant of an active stay of the reservation (else `invalid_guest`)."""
    if str(reservation.booker_id) == str(guest_id):
        return reservation.booker
    guest = (
        Guest.objects.filter(
            pk=guest_id, stays__reservation=reservation, stays__status__in=ACTIVE_STAY_STATUSES
        )
        .distinct()
        .first()
        if _is_uuid(guest_id)
        else None
    )
    if guest is None:
        raise DomainError("Ese huésped no pertenece a esta reserva", code="invalid_guest")
    return guest


def _is_uuid(value) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F-]{32,36}", str(value or "")))


def save_document(reservation, *, guest_id, kind, file, meta=None) -> GuestDocument:
    """One identity document (photo or PDF) of a guest of the booking → private `GuestDocument`."""
    if kind not in DOCUMENT_KINDS:
        raise DomainError("Tipo de documento inválido", code="validation_error",
                          fields={"kind": ["Elige frente, reverso, pasaporte u otro"]})  # fmt: skip
    if file is None:
        raise DomainError(
            "Adjunta la foto del documento", code="validation_error", fields={"file": [REQUIRED]}
        )
    with transaction.atomic():
        checkin, _settings = _open_checkin(reservation)
        guest = reservation_guest(reservation, guest_id)
        document = add_document(guest, kind=kind, file=file, uploaded_via="portal")
        data = dict(checkin.data or {})
        data["documents"] = [
            *data.get("documents", []),
            {
                "guest_id": str(guest.pk),
                "document_id": str(document.pk),
                "kind": kind,
                "uploaded_at": document.created_at.isoformat(),
            },
        ]
        checkin.data = data
        _advance(checkin, OnlineCheckin.Step.DOCUMENTS)
        _save(checkin, meta)
    return document


def confirm_documents(reservation, *, meta=None) -> OnlineCheckin:
    """Leave the documents step: every adult guest needs a document when the hotel requires it."""
    with transaction.atomic():
        checkin, settings = _open_checkin(reservation)
        if settings.require_document_photo:
            pending = guests_needing_documents(reservation, guest_slots(reservation))
            if pending:
                raise DomainError(
                    "Falta la foto del documento de: " + ", ".join(guest.full_name for guest in pending),
                    code="documents_missing",
                    guest_ids=[str(guest.pk) for guest in pending],
                )
        data = dict(checkin.data or {})
        data["steps"] = sorted(set(data.get("steps", [])) | {"documents"})
        checkin.data = data
        _advance(checkin, OnlineCheckin.Step.ARRIVAL)
        _save(checkin, meta)
    return checkin


def save_arrival(reservation, *, eta: time | None, meta=None) -> OnlineCheckin:
    """Estimated time of arrival: kept on the check-in and on the reservation (front desk sees it)."""
    with transaction.atomic():
        checkin, _settings = _open_checkin(reservation)
        if eta is not None and reservation.eta != eta:
            update_reservation(reservation, {"eta": eta}, source="guest")
        checkin.eta = eta
        data = dict(checkin.data or {})
        data["steps"] = sorted(set(data.get("steps", [])) | {"arrival"})
        checkin.data = data
        _advance(checkin, OnlineCheckin.Step.SIGNATURE)
        _save(checkin, meta)
    return checkin


def decode_signature(value: str) -> bytes:
    """PNG bytes of a `data:image/png;base64,…` (or bare base64) value; `invalid_signature` /
    `signature_empty` when it is not a PNG with a visible stroke."""
    text = (value or "").strip()
    if text.startswith("data:"):
        header, _, text = text.partition(",")
        if not header.startswith("data:image/png"):
            raise DomainError("La firma debe ser una imagen PNG", code="invalid_signature")
    try:
        raw = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise DomainError("La firma no es una imagen válida", code="invalid_signature") from None
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise DomainError("La imagen de la firma es demasiado grande", code="invalid_signature")
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DomainError("La firma debe ser una imagen PNG", code="invalid_signature")
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise DomainError("La firma no es una imagen válida", code="invalid_signature") from None
    if max(image.size) > MAX_SIGNATURE_SIDE:
        raise DomainError("La imagen de la firma es demasiado grande", code="invalid_signature")
    visible = image.convert("RGBA").getchannel("A").getbbox()
    if visible is None:
        raise DomainError("Firma en el recuadro antes de continuar", code="signature_empty")
    return raw


def save_signature(reservation, *, signature: str, accept_terms: bool, marketing_consent: bool = False,
                   meta=None) -> OnlineCheckin:  # fmt: skip
    """Signature (PNG, private storage) + acceptance of the terms and of the data processing (Habeas Data,
    recorded on the booker)."""
    if not accept_terms:
        raise DomainError(
            "Acepta los términos y el tratamiento de datos para continuar", code="terms_required"
        )
    with transaction.atomic():
        checkin, settings = _open_checkin(reservation)
        if signature:
            png = decode_signature(signature)
            old = checkin.signature.name if checkin.signature else ""
            checkin.signature.save("signature.png", ContentFile(png), save=False)
            if old:
                storage = checkin.signature.storage
                transaction.on_commit(lambda: storage.delete(old))
        elif settings.require_signature and not checkin.signature:  # coming back keeps the one given
            raise DomainError("Firma en el recuadro antes de continuar", code="signature_required")
        now = timezone.now()
        checkin.accepted_terms_at = now
        booker = reservation.booker
        consent = {}
        if booker.data_processing_consent_at is None:
            consent["data_processing_consent_at"] = now
        if marketing_consent and not booker.marketing_consent:
            consent["marketing_consent"] = True
        if consent:
            update_guest(booker, consent, source="guest")
        data = dict(checkin.data or {})
        data["steps"] = sorted(set(data.get("steps", [])) | {"signature"})
        checkin.data = data
        _advance(checkin, OnlineCheckin.Step.PAYMENT)
        _save(checkin, meta)
    return checkin


def complete_checkin(reservation, *, meta=None) -> OnlineCheckin:
    """Validate every requirement and mark the check-in completed; `guest_checked_in_online` once."""
    existing = OnlineCheckin.objects.filter(reservation=reservation).first()
    if existing is not None and existing.status == OnlineCheckin.Status.COMPLETED:
        return existing
    with transaction.atomic():
        checkin, settings = _open_checkin(reservation)
        if checkin.status == OnlineCheckin.Status.COMPLETED:
            return checkin
        missing = missing_items(reservation, checkin, settings)
        if missing:
            raise DomainError("Aún faltan datos para completar el check-in", code="checkin_incomplete",
                              missing=missing)  # fmt: skip
        checkin.status = OnlineCheckin.Status.COMPLETED
        checkin.completed_at = timezone.now()
        due = Decimal(balance_of(reservation)["due"])
        checkin.current_step = OnlineCheckin.Step.PAYMENT if due > 0 else OnlineCheckin.Step.DONE
        _save(checkin, meta)
        audit.record(
            action="guestportal.checkin_completed",
            target=reservation,
            summary=f"Check-in online completado de {reservation.code}",
            source="guest",
            property=reservation.property,
        )
        send_on_commit(guest_checked_in_online, reservation=reservation)
    return checkin
