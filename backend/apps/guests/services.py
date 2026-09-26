"""Guest contracts (plan §C). Phase A: simple upsert/update/add_document; B3 adds phone E.164 normalization,
duplicate detection and merging."""

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core import audit
from apps.core.errors import DomainError
from apps.guests.models import Guest, GuestDocument
from apps.guests.types import GuestInput

UPDATABLE_FIELDS = frozenset({
    "first_name", "last_name", "email", "phone", "document_type", "document_number", "nationality",
    "country_of_residence", "city_of_residence", "birth_date", "gender", "address", "language", "is_vip",
    "tags", "notes", "preferences", "marketing_consent", "data_processing_consent_at", "custom_values",
    "blacklisted",
})  # fmt: skip


def _normalized(data: GuestInput) -> dict:
    return {
        "first_name": (data.first_name or "").strip(),
        "last_name": (data.last_name or "").strip(),
        "email": (data.email or "").strip().lower(),
        "phone": (data.phone or "").strip(),
        "document_type": (data.document_type or "").strip().upper(),
        "document_number": (data.document_number or "").strip(),
        "nationality": (data.nationality or "").strip().upper(),
        "country_of_residence": (data.country_of_residence or "").strip().upper(),
        "city_of_residence": (data.city_of_residence or "").strip(),
        "birth_date": data.birth_date,
        "language": (data.language or "").strip() or "es",
    }


def _find(candidates, values):
    """Match by document; otherwise by email — only guests without a document, if a document was given."""
    if values["document_number"]:
        guest = candidates.filter(
            document_type=values["document_type"], document_number=values["document_number"]
        ).first()
        if guest is not None or not values["email"]:
            return guest
        return (
            candidates.filter(email__iexact=values["email"], document_number="")
            .order_by("created_at")
            .first()
        )
    if values["email"]:
        return candidates.filter(email__iexact=values["email"]).order_by("created_at").first()
    return None


def _apply(guest, values, data: GuestInput) -> Guest:
    for field, value in values.items():
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
    otherwise create it. Merged guests are never matched. Consents are only ever granted, never
    revoked here."""
    values = _normalized(data)
    candidates = Guest.objects.select_for_update().filter(organization=organization, merged_into__isnull=True)
    with transaction.atomic():
        guest = _find(candidates, values)
        if guest is not None:
            return _apply(guest, values, data)
        try:
            with transaction.atomic():
                return _apply(Guest(organization=organization), values, data)
        except IntegrityError:  # same document created concurrently
            return _apply(_find(candidates, values), values, data)


def update_guest(guest, data: dict, *, source: str = "user", actor=None) -> Guest:
    """Update editable guest fields and audit the diff (unknown/protected keys → DomainError
    `invalid_field`)."""
    invalid = sorted(set(data) - UPDATABLE_FIELDS)
    if invalid:
        raise DomainError(f"Campos no editables: {', '.join(invalid)}", code="invalid_field", fields=invalid)
    before = {field: getattr(guest, field) for field in data}
    for field, value in data.items():
        if field == "email" and isinstance(value, str):
            value = value.strip().lower()
        setattr(guest, field, value)
    guest.save(update_fields=[*data, "updated_at"])
    changes = audit.diff(before, {field: getattr(guest, field) for field in data})
    if changes:
        audit.record(
            action="guests.guest_updated",
            target=guest,
            summary=f"Actualizó el huésped {guest.full_name}",
            actor=actor,
            source=source,
            changes=changes,
            organization=guest.organization,
        )
    return guest


def add_document(guest, *, kind: str, file, uploaded_via: str = "staff") -> GuestDocument:
    if kind not in GuestDocument.Kind.values:
        raise DomainError(f"Tipo de documento inválido: {kind}", code="invalid_kind")
    if uploaded_via not in GuestDocument.UploadedVia.values:
        raise DomainError(f"Origen inválido: {uploaded_via}", code="invalid_uploaded_via")
    return GuestDocument.objects.create(guest=guest, kind=kind, file=file, uploaded_via=uploaded_via)


def find_duplicates(guest) -> list[Guest]:
    """Likely duplicates: same document, same email, or same phone + similar last name. Implemented by B3."""
    raise NotImplementedError("guests.find_duplicates: B3 implementa esta función")


def merge_guests(primary, duplicate, *, actor) -> Guest:
    """Re-point every relation of `duplicate` to `primary`, fill empty fields, mark `merged_into`. B3."""
    raise NotImplementedError("guests.merge_guests: B3 implementa esta función")
