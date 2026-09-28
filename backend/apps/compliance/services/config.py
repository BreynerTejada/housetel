"""Per-property legal configuration and the facts about the hotel that every legal document repeats."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.compliance.codes import (
    SIRE_COUNTRY_CODES,
    SIRE_DOCUMENT_TYPES,
    TRA_ACCOMMODATION_TYPES,
    divipola_code,
)
from apps.compliance.models import ComplianceSettings
from apps.compliance.services.builder import check_digit
from apps.compliance.services.cufe import nit_without_dv


def get_settings(property) -> ComplianceSettings:
    """The hotel's `ComplianceSettings`, created with the defaults on first use."""
    settings, _ = ComplianceSettings.objects.get_or_create(property=property)
    return settings


def local_now(property) -> datetime:
    return timezone.localtime(timezone.now(), ZoneInfo(property.timezone or "America/Bogota"))


def local_date(property, moment: datetime | None = None) -> date:
    """Calendar date in the hotel's time zone (legal documents carry the real date, not the business date)."""
    moment = moment or timezone.now()
    return timezone.localtime(moment, ZoneInfo(property.timezone or "America/Bogota")).date()


def format_nit(nit: str, dv: str = "") -> str:
    """ "901234567", "7" → "901.234.567-7"."""
    digits = nit_without_dv(nit)
    grouped = f"{int(digits):,}".replace(",", ".") if digits else ""
    return f"{grouped}-{dv}" if grouped and dv else grouped


def supplier_info(property) -> dict:
    """Issuer block (the hotel): legal name, NIT (without check digit) and its DV, address and contact."""
    raw = (property.nit or "").strip()
    nit = nit_without_dv(raw)
    dv = raw.split("-", 1)[1].strip() if "-" in raw else (check_digit(nit) if nit else "")
    return {
        "legal_name": property.legal_name or property.name,
        "trade_name": property.name,
        "nit": nit,
        "dv": dv,
        "nit_display": format_nit(nit, dv),
        "address": property.address,
        "city": property.city,
        "department": property.department,
        "country": property.country or "CO",
        "municipality_code": divipola_code(property.city),
        "phone": property.phone,
        "email": property.email,
        "rnt": rnt_digits(property.rnt_number),
    }


def rnt_digits(value: str) -> str:
    """The RNT without a leading "RNT" label ("RNT 98765" → "98765")."""
    text = (value or "").strip()
    return text[3:].strip(" :.-#") if text.upper().startswith("RNT") else text


def sire_city_code(settings: ComplianceSettings) -> str:
    return settings.sire_city_code or divipola_code(settings.property.city)


def sire_document_codes(settings: ComplianceSettings) -> dict:
    return {**SIRE_DOCUMENT_TYPES, **(settings.sire_document_codes or {})}


def sire_country_codes(settings: ComplianceSettings) -> dict:
    return {**SIRE_COUNTRY_CODES, **{k.upper(): v for k, v in (settings.sire_country_codes or {}).items()}}


def tra_establishment_id(settings: ComplianceSettings) -> str:
    return rnt_digits(settings.tra_establishment_id or settings.property.rnt_number)


def tra_accommodation_type(settings: ComplianceSettings) -> str:
    prop = settings.property
    return settings.tra_accommodation_type or TRA_ACCOMMODATION_TYPES.get(prop.property_type, "Hotel")
