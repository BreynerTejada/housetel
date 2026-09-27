"""Guest contracts (plan §C): upsert_guest, update_guest, add_document, find_duplicates, merge_guests.

Every write path stores normalized data (apps.guests.normalization). Audit diffs never keep personal data
in clear (see `audited_changes`), so anonymizing a guest (Habeas Data) leaves no copy behind."""

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.core import audit
from apps.core.errors import ConflictError, DomainError
from apps.core.signals import send_on_commit
from apps.guests import signals
from apps.guests.models import Guest, GuestDocument
from apps.guests.normalization import (
    normalize_country,
    normalize_document,
    normalize_email,
    normalize_name,
    normalize_phone,
    similar_last_names,
)
from apps.guests.types import GuestInput

UPDATABLE_FIELDS = frozenset({
    "first_name", "last_name", "email", "phone", "document_type", "document_number", "nationality",
    "country_of_residence", "city_of_residence", "birth_date", "gender", "address", "language", "is_vip",
    "tags", "notes", "preferences", "marketing_consent", "data_processing_consent_at", "custom_values",
    "blacklisted",
})  # fmt: skip

# Values that identify a person (or may: free text, preferences with health data). Audit diffs record that
# they changed, never their values.
PERSONAL_FIELDS = frozenset({
    "first_name", "last_name", "email", "phone", "document_number", "birth_date", "address",
    "city_of_residence", "notes", "preferences", "custom_values",
})  # fmt: skip
MASK = "•••"


def audited_changes(changes: dict) -> dict:
    """`audit.diff` output with personal values replaced by a mask (empty values stay empty)."""
    return {
        field: [MASK if value not in ("", None, [], {}) else value for value in pair]
        if field in PERSONAL_FIELDS
        else pair
        for field, pair in changes.items()
    }


def phone_region(*candidates: str | None) -> str | None:
    """First known country among the candidates (residence first): the region a local phone is read in."""
    return next((normalize_country(c) for c in candidates if c), None)


def normalize_fields(data: dict, *, region: str | None = None) -> dict:
    """Normalized copy of the guest fields present in `data` (other keys pass through untouched)."""
    result = dict(data)
    for field in ("first_name", "last_name"):
        if isinstance(result.get(field), str):
            result[field] = normalize_name(result[field])
    for field in ("nationality", "country_of_residence", "document_type"):  # ISO-2 codes, CC/PA/…
        if isinstance(result.get(field), str):
            result[field] = result[field].strip().upper()
    if isinstance(result.get("email"), str):
        result["email"] = normalize_email(result["email"])
    if isinstance(result.get("document_number"), str):
        result["document_number"] = normalize_document(result["document_number"])
    if isinstance(result.get("phone"), str):
        result["phone"] = normalize_phone(result["phone"], region=region)
    for field in ("city_of_residence", "address"):
        if isinstance(result.get(field), str):
            result[field] = result[field].strip()
    return result


def _normalized(data: GuestInput) -> dict:
    values = normalize_fields(
        {
            "first_name": data.first_name or "",
            "last_name": data.last_name or "",
            "email": data.email or "",
            "phone": data.phone or "",
            "document_type": data.document_type or "",
            "document_number": data.document_number or "",
            "nationality": data.nationality or "",
            "country_of_residence": data.country_of_residence or "",
            "city_of_residence": data.city_of_residence or "",
        },
        region=phone_region(data.country_of_residence, data.nationality),
    )
    values["birth_date"] = data.birth_date
    values["language"] = (data.language or "").strip() or "es"
    return values


def surviving_guest(guest: Guest) -> Guest:
    """The guest a merged record now lives in (follows `merged_into`; merges keep chains one hop long)."""
    seen = set()
    while guest.merged_into_id and guest.pk not in seen:
        seen.add(guest.pk)
        guest = guest.merged_into
    return guest


def _find(organization, values):
    """Match by document — a merged guest's document leads to the guest it was merged into —, otherwise by
    email among active guests (only guests without a document, if a document was given)."""
    everyone = Guest.objects.select_for_update().filter(organization=organization)
    active = everyone.filter(merged_into__isnull=True)
    if values["document_number"]:
        guest = everyone.filter(
            document_type=values["document_type"], document_number=values["document_number"]
        ).first()
        if guest is not None:
            return surviving_guest(guest)
        if not values["email"]:
            return None
        return active.filter(email__iexact=values["email"], document_number="").order_by("created_at").first()
    if values["email"]:
        return active.filter(email__iexact=values["email"]).order_by("created_at").first()
    return None


def _apply(guest, values, data: GuestInput) -> Guest:
    keeps_document = bool(guest.document_number)  # an identity document is never replaced by a match
    for field, value in values.items():
        if keeps_document and field in ("document_type", "document_number"):
            continue
        if value not in ("", None):
            setattr(guest, field, value)
    if data.marketing_consent:
        guest.marketing_consent = True
    if data.data_processing_consent and guest.data_processing_consent_at is None:
        guest.data_processing_consent_at = timezone.now()
    guest.save()
    return guest


def upsert_guest(organization, data: GuestInput, *, actor=None) -> Guest:
    """Find the organization's guest by document, then email, and fill it with the non-empty input values;
    otherwise create it. Emails of merged guests are never matched; their documents resolve to the guest
    they were merged into. Consents are only ever granted, never revoked here."""
    values = _normalized(data)
    with transaction.atomic():
        guest = _find(organization, values)
        if guest is not None:
            return _apply(guest, values, data)
        try:
            with transaction.atomic():
                return _apply(Guest(organization=organization), values, data)
        except IntegrityError:  # same document created concurrently
            return _apply(_find(organization, values), values, data)


def update_guest(guest, data: dict, *, source: str = "user", actor=None) -> Guest:
    """Update editable guest fields and audit the diff (unknown/protected keys → DomainError
    `invalid_field`)."""
    invalid = sorted(set(data) - UPDATABLE_FIELDS)
    if invalid:
        raise DomainError(f"Campos no editables: {', '.join(invalid)}", code="invalid_field", fields=invalid)
    region = phone_region(
        data.get("country_of_residence") or guest.country_of_residence,
        data.get("nationality") or guest.nationality,
    )
    data = normalize_fields(data, region=region)
    before = {field: getattr(guest, field) for field in data}
    for field, value in data.items():
        setattr(guest, field, value)
    guest.save(update_fields=[*data, "updated_at"])
    changes = audit.diff(before, {field: getattr(guest, field) for field in data})
    if changes:
        audit.record(
            action="guests.guest_updated",
            target=guest,
            summary="Actualizó los datos de un huésped",
            actor=actor,
            source=source,
            changes=audited_changes(changes),
            organization=guest.organization,
        )
    return guest


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024

# Accepted identity-document formats, recognized by their first bytes (never by the client's file name or
# content type): extension stored, content type served.
DOCUMENT_TYPES = {
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".pdf": "application/pdf",
}
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}


def sniff_document_type(head: bytes) -> str | None:
    """Extension (a DOCUMENT_TYPES key) for the file starting with `head`, or None if not accepted."""
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head.startswith(b"\x89PNG"):
        return ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[4:8] == b"ftyp" and head[8:12] in HEIF_BRANDS:
        return ".heic"
    if head.startswith(b"%PDF-"):
        return ".pdf"
    return None


def check_document_file(file) -> str:
    """Validate an identity-document upload (≤ 10 MB, JPEG/PNG/WebP/HEIC image or PDF recognized by its
    content) and return the extension to store it with. DomainError `file_too_large` / `invalid_file_type`."""
    size = getattr(file, "size", None)
    if size is not None and size > MAX_DOCUMENT_BYTES:
        raise DomainError("El archivo supera el máximo de 10 MB", code="file_too_large")
    file.seek(0)
    extension = sniff_document_type(file.read(16))
    file.seek(0)
    if extension is None:
        raise DomainError(
            "Formato no admitido: sube una foto (JPG, PNG, WebP, HEIC) o un PDF", code="invalid_file_type"
        )
    return extension


def add_document(guest, *, kind: str, file, uploaded_via: str = "staff") -> GuestDocument:
    """Store an identity document (JPEG/PNG/WebP/HEIC image or PDF, ≤ 10 MB) in the private storage.

    The type comes from the file's content; the stored name is random (apps/guests/storage.py)."""
    if kind not in GuestDocument.Kind.values:
        raise DomainError(f"Tipo de documento inválido: {kind}", code="invalid_kind")
    if uploaded_via not in GuestDocument.UploadedVia.values:
        raise DomainError(f"Origen inválido: {uploaded_via}", code="invalid_uploaded_via")
    file.name = f"{kind}{check_document_file(file)}"
    return GuestDocument.objects.create(guest=guest, kind=kind, file=file, uploaded_via=uploaded_via)


def document_content_type(document: GuestDocument) -> str:
    return DOCUMENT_TYPES.get(Path(document.file.name).suffix.lower(), "application/octet-stream")


def find_duplicates(guest) -> list[Guest]:
    """Likely duplicates of `guest` (saved or not) in its organization: same document number (any type), same
    email, or same phone + similar last name. Merged guests never appear.

    Each returned guest carries `duplicate_reasons` (subset of "document", "email", "phone_name"); the ones
    with more reasons come first, then the oldest."""
    document = normalize_document(guest.document_number)
    email = normalize_email(guest.email)
    phone = normalize_phone(guest.phone, region=phone_region(guest.country_of_residence, guest.nationality))
    lookup = Q()
    if document:
        lookup |= Q(document_number=document)
    if email:
        lookup |= Q(email__iexact=email)
    if phone:
        lookup |= Q(phone=phone)
    if not lookup:
        return []
    candidates = Guest.objects.filter(lookup, organization_id=guest.organization_id, merged_into__isnull=True)
    if guest.pk:
        candidates = candidates.exclude(pk=guest.pk)
    result = []
    for candidate in candidates.order_by("created_at"):
        reasons = []
        if document and candidate.document_number == document:
            reasons.append("document")
        if email and candidate.email.lower() == email:
            reasons.append("email")
        if phone and candidate.phone == phone and similar_last_names(guest.last_name, candidate.last_name):
            reasons.append("phone_name")
        if reasons:
            candidate.duplicate_reasons = reasons
            result.append(candidate)
    result.sort(key=lambda g: -len(g.duplicate_reasons))  # stable: oldest first among equals
    return result


FILLABLE_FIELDS = (
    "last_name", "email", "phone", "nationality", "country_of_residence", "city_of_residence", "birth_date",
    "gender", "address",
)  # fmt: skip


def _is_empty(value) -> bool:
    return value in ("", None, [], {})


def _move_fk(rel, primary, duplicate) -> int:
    """Reverse FK / one-to-one: point the duplicate's rows at the primary. A unique constraint on the related
    model (e.g. one row per guest) leaves the conflicting rows on the duplicate instead of failing."""
    manager = rel.related_model._base_manager
    name = rel.field.name
    if rel.one_to_one and manager.filter(**{name: primary}).exists():
        return 0
    try:
        with transaction.atomic():
            return manager.filter(**{name: duplicate}).update(**{name: primary})
    except IntegrityError:
        moved = 0
        for pk in manager.filter(**{name: duplicate}).values_list("pk", flat=True):
            try:
                with transaction.atomic():
                    moved += manager.filter(pk=pk).update(**{name: primary})
            except IntegrityError:
                continue
        return moved


def _move_m2m(rel, primary, duplicate) -> int:
    """Reverse M2M (e.g. Stay.occupants): rows already linking the primary are dropped, the rest move."""
    through = rel.through
    owner = rel.field.m2m_field_name()  # FK to the model that declares the M2M (e.g. "stay")
    guest_field = rel.field.m2m_reverse_field_name()  # FK to Guest
    rows = through._base_manager.filter(**{guest_field: duplicate})
    linked = through._base_manager.filter(**{guest_field: primary}).values(f"{owner}_id")
    rows.filter(**{f"{owner}_id__in": linked}).delete()
    return rows.update(**{guest_field: primary})


def _move_relations(primary, duplicate) -> dict[str, int]:
    """Every relation to Guest, generically — later phases' models included without changes here."""
    moved = {}
    for rel in Guest._meta.related_objects:
        count = _move_m2m(rel, primary, duplicate) if rel.many_to_many else _move_fk(rel, primary, duplicate)
        if count:
            moved[f"{rel.related_model._meta.label}.{rel.field.name}"] = count
    return moved


def _fuse_fields(primary, duplicate) -> list[str]:
    """Fill what the primary lacks from the duplicate. Returns the names of the fields that changed."""
    filled = [
        f for f in FILLABLE_FIELDS if _is_empty(getattr(primary, f)) and not _is_empty(getattr(duplicate, f))
    ]
    for field in filled:
        setattr(primary, field, getattr(duplicate, field))
    if not primary.document_number and duplicate.document_number:
        # The (organization, type, number) pair is unique: the duplicate hands its document over.
        primary.document_type, primary.document_number = duplicate.document_type, duplicate.document_number
        duplicate.document_type, duplicate.document_number = "", ""
        filled.append("document")
    tags = list(dict.fromkeys([*(primary.tags or []), *(duplicate.tags or [])]))
    preferences = {**(duplicate.preferences or {}), **(primary.preferences or {})}
    custom_values = {**(duplicate.custom_values or {}), **(primary.custom_values or {})}
    notes = "\n\n".join(dict.fromkeys(n.strip() for n in (primary.notes, duplicate.notes) if n and n.strip()))
    consents = [c for c in (primary.data_processing_consent_at, duplicate.data_processing_consent_at) if c]
    updates = {
        "tags": tags,
        "preferences": preferences,
        "custom_values": custom_values,
        "notes": notes,
        "is_vip": primary.is_vip or duplicate.is_vip,
        "blacklisted": primary.blacklisted or duplicate.blacklisted,
        "marketing_consent": primary.marketing_consent or duplicate.marketing_consent,
        "data_processing_consent_at": min(consents) if consents else None,
    }
    for field, value in updates.items():
        if getattr(primary, field) != value:
            setattr(primary, field, value)
            filled.append(field)
    return filled


def merge_guests(primary, duplicate, *, actor) -> Guest:
    """Merge `duplicate` into `primary` (same organization): every relation of the duplicate moves to the
    primary (generic over Guest._meta.related_objects, FK and M2M), the primary's empty fields are filled,
    tags/preferences are combined, and the duplicate is kept as history with `merged_into=primary` (merged
    guests leave listings, searches and duplicate suggestions). Anonymized guests are refused (ConflictError
    `guest_anonymized`): filling an erased record would bring personal data back. Audited as
    `guests.merged`."""
    if primary.organization_id != duplicate.organization_id:
        raise DomainError("Los huéspedes son de organizaciones distintas", code="different_organization")
    if primary.pk == duplicate.pk:
        raise DomainError("No se puede fusionar un huésped consigo mismo", code="same_guest")
    with transaction.atomic():
        locked = {
            g.pk: g for g in Guest.objects.select_for_update().filter(pk__in=[primary.pk, duplicate.pk])
        }
        primary, duplicate = locked[primary.pk], locked[duplicate.pk]
        if primary.merged_into_id or duplicate.merged_into_id:
            raise ConflictError("Uno de los huéspedes ya fue fusionado", code="already_merged")
        if primary.anonymized_at or duplicate.anonymized_at:
            raise ConflictError("No se puede fusionar un huésped anonimizado", code="guest_anonymized")
        relations = _move_relations(primary, duplicate)
        filled = _fuse_fields(primary, duplicate)
        duplicate.merged_into = primary
        duplicate.save()  # first: it may be handing its document over to the primary
        primary.save()
        audit.record(
            action="guests.merged",
            target=primary,
            summary="Fusionó un huésped duplicado",
            actor=actor,
            organization=primary.organization,
            changes={"duplicate_id": str(duplicate.pk), "fields_filled": filled, "relations": relations},
        )
        send_on_commit(signals.guests_merged, primary=primary, duplicate=duplicate)
    return primary


# ---- Habeas Data (Ley 1581 de 2012) ---------------------------------------------------------------------

ANONYMIZED_NAME = ("Huésped", "anonimizado")
ERASED_VALUES = {
    "email": "", "phone": "", "document_type": "", "document_number": "", "birth_date": None, "gender": "",
    "address": "", "city_of_residence": "", "notes": "", "preferences": {}, "tags": [], "custom_values": {},
    "marketing_consent": False, "is_vip": False, "blacklisted": False,
}  # fmt: skip


def anonymize_guest(guest, *, actor) -> Guest:
    """Erase the guest's personal data on request (right of deletion) and delete their identity documents.

    The record stays ("Huésped anonimizado") so reservations, folios and legal reports keep their history;
    nationality, country of residence and language are kept (statistics, IVA history). Records merged into
    the guest are the same person and are erased too. A record already merged into another guest is refused
    (ConflictError `guest_merged` with the survivor's `guest_id`): the survivor holds its data as well, so the
    erasure goes through the survivor. The document files are deleted once the transaction commits. Audited
    as `guests.anonymized` (field names only)."""
    with transaction.atomic():
        guest = Guest.objects.select_for_update().get(pk=guest.pk)
        if guest.merged_into_id:
            raise ConflictError(
                "Este registro se fusionó con otro perfil; anonimiza el perfil principal",
                code="guest_merged",
                guest_id=str(surviving_guest(guest).pk),
            )
        if guest.anonymized_at:
            raise ConflictError("Los datos de este huésped ya fueron anonimizados", code="already_anonymized")
        records = [guest, *Guest.objects.select_for_update().filter(merged_into=guest)]
        documents = GuestDocument.objects.filter(guest__in=records)
        storage = GuestDocument._meta.get_field("file").storage
        files = [name for name in documents.values_list("file", flat=True) if name]
        documents_deleted = len(files)
        documents.delete()
        now = timezone.now()
        for record in records:
            record.first_name, record.last_name = ANONYMIZED_NAME
            for field, value in ERASED_VALUES.items():
                setattr(record, field, value)
            record.anonymized_at = now
            record.save()
        audit.record(
            action="guests.anonymized",
            target=guest,
            summary="Anonimizó los datos personales de un huésped (Habeas Data)",
            actor=actor,
            organization=guest.organization,
            changes={
                "fields": sorted(["first_name", "last_name", *ERASED_VALUES]),
                "documents_deleted": documents_deleted,
                "merged_records": len(records) - 1,
            },
        )
        transaction.on_commit(lambda: [storage.delete(name) for name in files])
        send_on_commit(
            signals.guest_anonymized, guest=guest, merged_ids=[record.pk for record in records[1:]]
        )
    return guest


EXPORT_FIELDS = (
    "first_name", "last_name", "email", "phone", "document_type", "document_number", "nationality",
    "country_of_residence", "city_of_residence", "birth_date", "gender", "address", "language", "is_vip",
    "tags", "notes", "preferences", "marketing_consent", "data_processing_consent_at", "custom_values",
    "blacklisted", "anonymized_at", "created_at", "updated_at",
)  # fmt: skip


def _jsonable(value):
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal | UUID):
        return str(value)
    return value


def _profile(guest) -> dict:
    return {"id": str(guest.pk), **{field: _jsonable(getattr(guest, field)) for field in EXPORT_FIELDS}}


def export_guest(guest) -> dict:
    """Everything the organization stores about the guest (right of access), JSON-safe: profile, consents,
    documents (metadata only), reservations as booker or occupant, and the records merged into it."""
    from apps.bookings.models import Reservation

    reservations = (
        Reservation.objects.filter(Q(booker=guest) | Q(stays__occupants=guest))
        .select_related("property")
        .distinct()
        .order_by("checkin_date", "code")
    )
    organization = guest.organization
    return {
        "exported_at": timezone.now().isoformat(),
        "organization": {
            "name": organization.name,
            "legal_name": organization.legal_name,
            "nit": organization.nit,
        },
        "guest": _profile(guest),
        "documents": [
            {"kind": d.kind, "uploaded_via": d.uploaded_via, "uploaded_at": d.created_at.isoformat()}
            for d in guest.documents.order_by("created_at")
        ],
        "reservations": [
            {
                "code": r.code,
                "property": r.property.name,
                "checkin": r.checkin_date.isoformat(),
                "checkout": r.checkout_date.isoformat(),
                "status": r.status,
                "role": "booker" if r.booker_id == guest.pk else "occupant",
            }
            for r in reservations
        ],
        "merged_records": [_profile(g) for g in guest.merged_guests.order_by("created_at")],
    }


# ---- Staff CRM operations (used by the API; not cross-app contracts) ------------------------------------


def document_owner(organization, document_type: str, document_number: str, *, exclude=None) -> Guest | None:
    """The (surviving) guest that holds this document in the organization, if any."""
    number = normalize_document(document_number)
    if not number:
        return None
    holders = Guest.objects.filter(
        organization=organization, document_type=(document_type or "").strip().upper(), document_number=number
    )
    if exclude is not None:
        holders = holders.exclude(pk=exclude.pk)
    holder = holders.first()
    return surviving_guest(holder) if holder else None


def create_guest(organization, data: dict, *, actor=None) -> Guest:
    """Create a guest from staff input (normalized). `data_processing_consent=True` records the Habeas Data
    consent time. A document already registered → ConflictError `guest_exists` with `guest_id`."""
    data = dict(data)
    consent = data.pop("data_processing_consent", False)
    data = normalize_fields(
        data, region=phone_region(data.get("country_of_residence"), data.get("nationality"))
    )
    holder = document_owner(organization, data.get("document_type", ""), data.get("document_number", ""))
    if holder is not None:
        raise ConflictError(
            "Ya existe un huésped con ese documento", code="guest_exists", guest_id=str(holder.pk)
        )
    guest = Guest(organization=organization, **data)
    if consent:
        guest.data_processing_consent_at = timezone.now()
    guest.save()
    audit.record(
        action="guests.guest_created",
        target=guest,
        summary="Creó un huésped",
        actor=actor,
        organization=organization,
    )
    return guest


def guest_relations(guest) -> dict[str, int]:
    """Rows of any app that reference the guest, by `app.Model.field` (documents excluded)."""
    counts = {}
    for rel in Guest._meta.related_objects:
        if rel.related_model is GuestDocument:
            continue
        if rel.many_to_many:
            count = rel.through._base_manager.filter(**{rel.field.m2m_reverse_field_name(): guest}).count()
        else:
            count = rel.related_model._base_manager.filter(**{rel.field.name: guest}).count()
        if count:
            counts[f"{rel.related_model._meta.label}.{rel.field.name}"] = count
    return counts


def _delete_files_on_commit(names: list[str]) -> None:
    storage = GuestDocument._meta.get_field("file").storage
    transaction.on_commit(lambda: [storage.delete(name) for name in names if name])


def delete_guest(guest, *, actor=None) -> None:
    """Delete a guest that nothing references (a typo, a test). Guests with history (reservations, stays,
    folios, merged records…) are kept: ConflictError `guest_in_use` — anonymize or merge them instead."""
    relations = guest_relations(guest)
    if relations:
        raise ConflictError(
            "El huésped tiene historial; anonimízalo o fusiónalo en lugar de eliminarlo",
            code="guest_in_use",
            relations=relations,
        )
    with transaction.atomic():
        _delete_files_on_commit(list(guest.documents.values_list("file", flat=True)))
        audit.record(
            action="guests.guest_deleted",
            target=guest,
            summary="Eliminó un huésped sin historial",
            actor=actor,
            organization=guest.organization,
        )
        guest.delete()


def delete_document(document, *, actor=None) -> None:
    with transaction.atomic():
        _delete_files_on_commit([document.file.name])
        audit.record(
            action="guests.document_deleted",
            target=document.guest,
            summary="Eliminó un documento de un huésped",
            actor=actor,
            organization=document.guest.organization,
            changes={"kind": document.kind},
        )
        document.delete()
