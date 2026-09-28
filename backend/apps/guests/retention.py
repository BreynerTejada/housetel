"""Habeas Data retention (Ley 1581 de 2012, plan P6): identity documents and signatures are kept only while
the hotel needs them.

`purge_identity_documents(prop, retention_days=N)` (automation `guests.purge_identity_documents`, daily)
deletes, N days after the departure:

- the photos of identity documents (`GuestDocument`: front/back, passport, other) of the guests whose
  **last** reservation in the organization ended at this property on or before `business_date - N`, and
  who have nothing active (tentative, confirmed or in house) anywhere in the organization. Documents
  belong to the guest, not to a reservation, so a guest is handled by the property of their last stay
  (each property has its own N);
- the signature of the online check-in of this property's reservations that ended on or before that
  date (`OnlineCheckin.signature`). The acceptance evidence (date, IP, user agent) stays: it proves the
  consent.

"Ended" = departure date of a checked-out, cancelled or no-show reservation. Files go on commit (a failed
run deletes nothing), every deletion is audited without personal data (kinds, dates and ids only), and the
online check-in keeps a `retention_purged_at` mark so the staff sees why the documents are gone.
`retention_days = 0` means never.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core import audit
from apps.guests.models import Guest, GuestDocument

DEFAULT_RETENTION_DAYS = 180
ENDED_STATUSES = ("checked_out", "cancelled", "no_show")
ACTIVE_STATUSES = ("tentative", "confirmed", "checked_in")
ACTOR_LABEL = "Retención de datos (Habeas Data)"


@dataclass
class PurgeResult:
    cutoff: date
    guests: int = 0
    documents: int = 0
    signatures: int = 0
    reservations: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "cutoff": self.cutoff.isoformat(),
            "guests": self.guests,
            "documents": self.documents,
            "signatures": self.signatures,
            "reservations": self.reservations[:50],
        }


def _delete_on_commit(storage, names: list[str]) -> None:
    names = [name for name in names if name]
    if names:
        transaction.on_commit(lambda: [storage.delete(name) for name in names])


def _last_reservations(prop, guest_ids) -> dict:
    """guest_id → (latest departure, property of that reservation, any active reservation) in the org."""
    from apps.bookings.models import Reservation

    facts: dict = {}
    rows = (
        Reservation.objects.filter(property__organization_id=prop.organization_id)
        .filter(Q(booker_id__in=guest_ids) | Q(stays__occupants__in=guest_ids))
        .values_list("booker_id", "stays__occupants", "status", "checkout_date", "property_id")
        .distinct()
    )
    for booker_id, occupant_id, status, checkout, property_id in rows:
        for guest_id in {booker_id, occupant_id} & guest_ids:
            last, last_property, active = facts.get(guest_id, (None, None, False))
            if status in ACTIVE_STATUSES:
                active = True
            elif status in ENDED_STATUSES and (last is None or checkout > last):
                last, last_property = checkout, property_id
            facts[guest_id] = (last, last_property, active)
    return facts


def purge_identity_documents(prop, *, retention_days: int, today: date | None = None) -> PurgeResult:
    from apps.guestportal.models import OnlineCheckin

    today = today or prop.business_date
    cutoff = today - timedelta(days=retention_days)
    result = PurgeResult(cutoff=cutoff)
    if retention_days <= 0:
        return result
    now = timezone.now()
    document_storage = GuestDocument._meta.get_field("file").storage
    signature_storage = OnlineCheckin._meta.get_field("signature").storage

    with transaction.atomic():
        # 1) identity documents of the guests whose last stay (at this property) ended before the cutoff
        guest_ids = set(
            GuestDocument.objects.filter(guest__organization_id=prop.organization_id)
            .values_list("guest_id", flat=True)
            .distinct()
        )
        facts = _last_reservations(prop, guest_ids) if guest_ids else {}
        due = [
            guest_id
            for guest_id, (last, property_id, active) in facts.items()
            if not active and last is not None and last <= cutoff and property_id == prop.pk
        ]
        purged_documents: set[str] = set()
        for guest in Guest.objects.filter(pk__in=due).prefetch_related("documents"):
            documents = list(guest.documents.all())
            if not documents:
                continue
            last = facts[guest.pk][0]
            _delete_on_commit(document_storage, [document.file.name for document in documents])
            audit.record(
                action="guests.documents_purged",
                target=guest,
                summary=(
                    f"Borró {len(documents)} "
                    + ("documento de identidad" if len(documents) == 1 else "documentos de identidad")
                    + f" por la política de retención ({retention_days} días después de la salida)"
                ),
                source="automation",
                actor_label=ACTOR_LABEL,
                property=prop,
                changes={
                    "retention_days": retention_days,
                    "last_departure": last.isoformat(),
                    "deleted": [
                        {
                            "id": str(document.pk),
                            "kind": document.kind,
                            "uploaded_via": document.uploaded_via,
                            "uploaded_at": document.created_at.isoformat(),
                        }
                        for document in documents
                    ],
                },
            )
            purged_documents.update(str(document.pk) for document in documents)
            GuestDocument.objects.filter(pk__in=[document.pk for document in documents]).delete()
            result.guests += 1
            result.documents += len(documents)

        # 2) signatures (and the mark on the check-ins that lost documents) of the reservations that ended
        checkins = OnlineCheckin.objects.filter(
            reservation__property=prop,
            reservation__status__in=ENDED_STATUSES,
            reservation__checkout_date__lte=cutoff,
        ).select_related("reservation")
        for checkin in checkins:
            data = dict(checkin.data or {})
            referenced = {str(item.get("document_id")) for item in data.get("documents") or []}
            lost_documents = sorted(referenced & purged_documents)
            had_signature = bool(checkin.signature)
            if not had_signature and not lost_documents:
                continue
            fields = ["data", "updated_at"]
            if had_signature:
                _delete_on_commit(signature_storage, [checkin.signature.name])
                checkin.signature = ""
                fields.append("signature")
                result.signatures += 1
            data["retention_purged_at"] = now.isoformat()
            data["retention_days"] = retention_days
            checkin.data = data
            checkin.save(update_fields=fields)
            reservation = checkin.reservation
            result.reservations.append(reservation.code)
            audit.record(
                action="guests.signature_purged" if had_signature else "guests.checkin_documents_purged",
                target=checkin,
                summary=(
                    f"Borró la firma del check-in online de {reservation.code} por la política de retención"
                    if had_signature
                    else f"Borró los documentos del check-in online de {reservation.code} por la política "
                    "de retención"
                ),
                source="automation",
                actor_label=ACTOR_LABEL,
                property=prop,
                changes={
                    "retention_days": retention_days,
                    "departure": reservation.checkout_date.isoformat(),
                    "signature": had_signature,
                    "documents": lost_documents,
                },
            )
    return result
