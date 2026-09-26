"""Room-night charges (plan §C) — signature fixed in Phase A, implemented by B2b."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # finance.models imports bookings.models; keep the runtime import graph one-way
    from apps.finance.models import Charge


def post_room_charges(stay, *, until_date, actor=None, source="automation") -> list[Charge]:
    """Post (idempotently) one `room` charge per night < `until_date` not yet posted:
    `post_charge(kind="room", amount=net, tax=lodging IVA, tax_exempt=booker.is_foreign_non_resident,
    night_date=night, stay=stay, business_date=night)`. Net = night amount without tax
    (amount/(1+rate) when the tax is included in the price)."""
    raise NotImplementedError("bookings.post_room_charges: B2b implementa esta función")
