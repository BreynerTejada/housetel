from dataclasses import dataclass
from datetime import date


@dataclass
class GuestInput:
    """Guest data coming from a booking flow, the portal or a channel (consumed by `upsert_guest`)."""

    first_name: str
    last_name: str
    email: str = ""
    phone: str = ""
    document_type: str = ""  # Guest.DocumentType value
    document_number: str = ""
    nationality: str = ""  # ISO 3166-1 alpha-2
    country_of_residence: str = ""  # ISO 3166-1 alpha-2
    city_of_residence: str = ""
    birth_date: date | None = None
    language: str = "es"
    marketing_consent: bool = False
    data_processing_consent: bool = False  # Habeas Data (Ley 1581): sets Guest.data_processing_consent_at
