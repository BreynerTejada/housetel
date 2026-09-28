"""Value objects of the channel manager: the ARI sent to a channel and the bookings received from one."""

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class AriRateDay:
    """One night of a channel rate. `price` = plan price × (1 + markup/100), rounded to the currency; None
    when the night has no price (then `stop_sell` is True)."""

    date: date
    price: Decimal | None
    min_los: int | None
    max_los: int | None
    closed_to_arrival: bool
    closed_to_departure: bool
    stop_sell: bool


@dataclass(frozen=True)
class AriRate:
    external_rate_id: str
    rate_plan_id: UUID | None
    markup_percent: Decimal
    days: list[AriRateDay]


@dataclass(frozen=True)
class AriBatch:
    """Everything a channel must know about one category over `[start, end)`. `kinds` says what changed
    (providers that pay per call, like Channex, only send those); the values are always complete."""

    connection_id: UUID
    room_type_id: UUID
    room_type_code: str
    external_room_id: str
    start: date
    end: date
    kinds: tuple[str, ...]
    availability: dict[date, int]  # never negative
    rates: list[AriRate]


@dataclass
class InboundRoom:
    """One room of a channel booking. `nightly_rates` = [{"date", "amount"}] per night (the price before the
    VAT not included, like a quoted price); None lets the PMS price it (iCal). `room_type_id`/`rate_plan_id`/
    `room_id` skip the mapping lookup (iCal calendars already know their category or room)."""

    external_room_id: str = ""
    external_rate_id: str = ""
    checkin: date | None = None
    checkout: date | None = None
    adults: int = 1
    children: int = 0
    nightly_rates: list[dict] | None = None
    room_type_id: UUID | None = None
    rate_plan_id: UUID | None = None
    room_id: UUID | None = None


@dataclass
class InboundBooking:
    """A booking as a channel reports it (normalized from BookSim/AirSim, Channex revisions or iCal
    events). `status`: new | modified | cancelled."""

    external_id: str
    status: str = "new"
    guest: dict = field(default_factory=dict)  # first_name, last_name, email, phone, country, language
    rooms: list[InboundRoom] = field(default_factory=list)
    currency: str = ""  # of the channel prices; "" = the property currency (a different one is refused)
    notes: str = ""
    special_requests: str = ""
    eta: time | None = None
    raw: dict = field(default_factory=dict)  # original payload (kept on the reservation)
    revision_id: str = ""  # Channex revision to acknowledge
    room_mapping_id: UUID | None = None  # iCal: the calendar the event came from


@dataclass
class ImportResult:
    """What `import_booking` did: created | modified | cancelled | unchanged | ignored | failed."""

    action: str
    reservation: object | None = None
    message: str = ""
    code: str = ""
    overbooked: bool = False
