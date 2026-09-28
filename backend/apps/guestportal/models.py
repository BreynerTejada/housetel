"""Guest portal (plan C5): per-property settings, the online check-in of a reservation and the guest's
service requests.

Personal data of the guests lives in `guests.Guest` (written through `guests.services`); identity documents
are `guests.GuestDocument` rows in private storage. The online check-in keeps only what belongs to the stay:
travel data per guest (motivo de viaje, procedencia, destino), the ETA, the signature and the evidence of the
acceptance (time, IP, user agent). The signature is stored in the same private storage as identity documents
(never under MEDIA_ROOT, never behind a public URL).
"""

import uuid
from pathlib import Path

from django.conf import settings
from django.db import models

from apps.bookings.models import Reservation
from apps.core.fields import i18n_field, json_field, money_field
from apps.core.models import BaseModel, Property
from apps.guests.storage import PrivateDocumentStorage
from apps.rates.models import Extra


class GuestPortalSettings(BaseModel):
    property = models.OneToOneField(Property, on_delete=models.CASCADE, related_name="guest_portal_settings")
    checkin_opens_days_before = models.PositiveSmallIntegerField(default=7)
    require_document_photo = models.BooleanField(default=True)
    require_signature = models.BooleanField(default=True)
    auto_approve_extras = models.BooleanField(default=True)
    # C5: the hotel decides whether guests may change or cancel on their own (always within the policy).
    allow_guest_cancellation = models.BooleanField(default=True)
    allow_guest_modification = models.BooleanField(default=True)
    terms = i18n_field()

    class Meta:
        verbose_name = "guest portal settings"
        verbose_name_plural = "guest portal settings"

    def __str__(self) -> str:
        return f"Portal · {self.property}"


def signature_upload_to(instance, filename: str) -> str:
    """Random name per organization, next to the identity documents (private storage)."""
    organization_id = instance.reservation.property.organization_id
    return f"guest-portal/signatures/{organization_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class OnlineCheckin(BaseModel):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started", "Sin empezar"
        IN_PROGRESS = "in_progress", "En progreso"
        COMPLETED = "completed", "Completado"

    class Step(models.TextChoices):
        GUESTS = "guests", "Huéspedes"
        DOCUMENTS = "documents", "Documentos"
        ARRIVAL = "arrival", "Llegada"
        SIGNATURE = "signature", "Firma y términos"
        PAYMENT = "payment", "Pago"
        DONE = "done", "Listo"

    reservation = models.OneToOneField(Reservation, on_delete=models.CASCADE, related_name="online_checkin")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NOT_STARTED)
    current_step = models.CharField(max_length=20, choices=Step.choices, default=Step.GUESTS)
    # {"travel": {"<guest_id>": {"travel_reason", "origin", "destination"}},
    #  "documents": [{"guest_id", "document_id", "kind", "uploaded_at"}], "steps": ["guests", ...]}
    data = json_field()
    signature = models.FileField(
        upload_to=signature_upload_to, storage=PrivateDocumentStorage(), max_length=255, blank=True
    )
    accepted_terms_at = models.DateTimeField(null=True, blank=True)
    eta = models.TimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["status"], name="online_checkin_status_idx")]

    def __str__(self) -> str:
        return f"Check-in online · {self.reservation_id} · {self.status}"


class ServiceRequest(BaseModel):
    class Kind(models.TextChoices):
        LATE_CHECKOUT = "late_checkout", "Late check-out"
        EARLY_CHECKIN = "early_checkin", "Early check-in"
        TRANSFER = "transfer", "Traslado"
        EXTRA = "extra", "Extra"
        OTHER = "other", "Otra solicitud"

    class Status(models.TextChoices):
        REQUESTED = "requested", "Solicitada"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"
        DONE = "done", "Realizada"

    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE, related_name="service_requests")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    extra = models.ForeignKey(Extra, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    quantity = models.PositiveSmallIntegerField(default=1)
    requested_time = models.TimeField(null=True, blank=True)  # late check-out until / early check-in from
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
    price = money_field(null=True, blank=True)  # what the guest pays (net + tax): charged, or estimated
    charge = models.ForeignKey(
        "finance.Charge", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["reservation", "status"], name="service_request_res_status_idx")]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} · {self.reservation_id} · {self.status}"
