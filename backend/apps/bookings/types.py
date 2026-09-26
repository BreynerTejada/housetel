"""Booking types and errors shared by producers and consumers (plan Step 5)."""

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from apps.core.errors import DomainError
from apps.guests.types import GuestInput
from apps.rates.types import Quote


@dataclass
class StayRequest:
    room_type_id: UUID
    rate_plan_id: UUID
    checkin: date
    checkout: date
    adults: int
    children: int = 0
    children_ages: list[int] = field(default_factory=list)
    room_id: UUID | None = None
    bed_id: UUID | None = None
    locked_room: bool = False
    occupants: list[GuestInput] = field(default_factory=list)
    nightly_rates: list[dict] | None = None  # prices imposed by a channel: [{"date", "amount"}]


@dataclass
class ReservationRequest:
    property: Any
    booker: Any  # GuestInput | Guest
    stays: list[StayRequest]
    source: str = "front_desk"
    channel_code: str = ""
    external_id: str = ""
    external_payload: dict = field(default_factory=dict)
    notes: str = ""
    special_requests: str = ""
    promo_code: str = ""
    language: str = "es"
    eta: time | None = None
    status: str = "confirmed"  # confirmed | tentative
    allow_overbooking: bool = False
    enforce_restrictions: bool = True
    hold_minutes: int = 20
    guarantee: str = "none"
    group_id: UUID | None = None
    custom_values: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Offer:
    room_type_id: UUID
    rate_plan_id: UUID
    available_units: int
    units_needed: int  # dorm: 1 per guest; private: 1
    quote: Quote  # per unit
    total: Decimal  # quote.total * units_needed


@dataclass
class AssignmentReport:
    assigned: list[tuple[str, str]] = field(default_factory=list)  # (stay_id, room_or_bed_id)
    unassigned: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


class BookingError(DomainError):
    code = "booking_error"


class AvailabilityError(BookingError):
    code = "no_availability"
    status_code = 409


class RestrictionError(BookingError):
    code = "restriction_violation"


class InvalidStateError(BookingError):
    code = "invalid_state"
    status_code = 409


class RoomNotReadyError(BookingError):
    code = "room_not_ready"
    status_code = 409


class BalanceDueError(BookingError):
    code = "balance_due"
    status_code = 409
