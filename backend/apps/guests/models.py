"""Guests (spec §4): shared by every property of an organization (a chain sees one CRM)."""

from django.db import models
from django.db.models import Q

from apps.core.fields import json_field
from apps.core.models import BaseModel, Organization


class Guest(BaseModel):
    class DocumentType(models.TextChoices):
        CC = "CC", "Cédula de ciudadanía"
        CE = "CE", "Cédula de extranjería"
        PA = "PA", "Pasaporte"
        TI = "TI", "Tarjeta de identidad"
        PEP = "PEP", "Permiso especial de permanencia"
        PPT = "PPT", "Permiso por protección temporal"
        DNI = "DNI", "Documento nacional de identidad"
        NIT = "NIT", "NIT"
        OTHER = "OTHER", "Otro"

    class Gender(models.TextChoices):
        FEMALE = "F", "Femenino"
        MALE = "M", "Masculino"
        OTHER = "X", "Otro"

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="guests")
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=32, blank=True)  # E.164, e.g. +573001234567
    document_type = models.CharField(max_length=10, choices=DocumentType.choices, blank=True)
    document_number = models.CharField(max_length=40, blank=True)
    nationality = models.CharField(max_length=2, blank=True)  # ISO 3166-1 alpha-2
    country_of_residence = models.CharField(max_length=2, blank=True)  # ISO 3166-1 alpha-2
    city_of_residence = models.CharField(max_length=100, blank=True)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=Gender.choices, blank=True)
    address = models.CharField(max_length=255, blank=True)
    language = models.CharField(max_length=5, default="es")
    is_vip = models.BooleanField(default=False)
    tags = json_field(default=list)
    notes = models.TextField(blank=True)
    preferences = json_field()
    marketing_consent = models.BooleanField(default=False)
    data_processing_consent_at = models.DateTimeField(null=True, blank=True)  # Ley 1581 de 2012 (Habeas Data)
    custom_values = json_field()
    blacklisted = models.BooleanField(default=False)
    merged_into = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="merged_guests"
    )

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "document_type", "document_number"],
                condition=~Q(document_number=""),
                name="guest_document_unique",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "email"], name="guest_org_email_idx"),
            models.Index(fields=["organization", "phone"], name="guest_org_phone_idx"),
            models.Index(fields=["organization", "last_name"], name="guest_org_last_name_idx"),
        ]

    def __str__(self) -> str:
        return self.full_name

    @property
    def full_name(self) -> str:
        return " ".join(part for part in (self.first_name, self.last_name) if part)

    @property
    def is_foreign_non_resident(self) -> bool:
        """Foreign nationality and residence outside Colombia (IVA exemption, ET art. 481 lit. d; SIRE).

        Without a nationality we never exempt; a foreigner with unknown residence counts as non-resident.
        """
        nationality = (self.nationality or "").upper()
        residence = (self.country_of_residence or "").upper()
        return bool(nationality) and nationality != "CO" and residence != "CO"


class GuestDocument(BaseModel):
    class Kind(models.TextChoices):
        ID_FRONT = "id_front", "Documento (frente)"
        ID_BACK = "id_back", "Documento (reverso)"
        PASSPORT = "passport", "Pasaporte"
        SIGNATURE = "signature", "Firma"
        OTHER = "other", "Otro"

    class UploadedVia(models.TextChoices):
        STAFF = "staff", "Recepción"
        PORTAL = "portal", "Portal del huésped"

    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    file = models.FileField(upload_to="guest-documents/%Y/%m/")
    uploaded_via = models.CharField(max_length=10, choices=UploadedVia.choices, default=UploadedVia.STAFF)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.guest} · {self.kind}"
