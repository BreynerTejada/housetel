"""Rate types shared by every consumer of the quote engine (plan Step 5). Money is Decimal, rounded to the
currency unit by `apps.core.money.quantize`; `Quote.to_dict()` renders money as two-decimal strings."""

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

_CENTS = Decimal("0.01")


@dataclass(frozen=True)
class NightPrice:
    date: date
    base: Decimal
    extra_adults: Decimal
    extra_children: Decimal
    discount: Decimal
    total: Decimal


@dataclass(frozen=True)
class TaxLine:
    code: str
    name: str
    rate: Decimal
    amount: Decimal
    included: bool
    exempt: bool = False


@dataclass(frozen=True)
class DayRate:
    date: date
    price: Decimal
    extra_adult_price: Decimal
    extra_child_price: Decimal
    min_los: int | None
    max_los: int | None
    closed_to_arrival: bool
    closed_to_departure: bool
    stop_sell: bool
    source: str  # DailyRate.Source value, "default" (RoomTypeRateDefaults) or "none" (no price configured)


@dataclass(frozen=True)
class Quote:
    room_type_id: UUID
    rate_plan_id: UUID
    checkin: date
    checkout: date
    adults: int
    children: int
    nights: list[NightPrice]
    subtotal: Decimal  # Σ nights.total (discount already applied)
    discount_total: Decimal
    taxes: list[TaxLine]
    tax_total: Decimal  # Σ taxes that are NOT included and NOT exempt
    total: Decimal  # subtotal + tax_total
    currency: str
    restrictions_ok: bool
    violations: list[str] = field(default_factory=list)
    promo_applied: str | None = None

    def to_dict(self) -> dict:
        """JSON-safe: Decimal → "0.00" string, date → ISO, UUID → str."""
        return _jsonable(asdict(self))


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return format(value.quantize(_CENTS), "f")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
