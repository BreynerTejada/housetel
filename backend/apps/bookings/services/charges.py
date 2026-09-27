"""Room-night charges (plan §C) — signature fixed in Phase A, implemented by B2b."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import transaction

from apps.bookings.models import Reservation, Stay
from apps.bookings.services.pricing import entries_total, lodging_tax, make_entry, split_amount, tax_exempt
from apps.bookings.services.totals import refresh_reservation
from apps.core.money import D, quantize

if TYPE_CHECKING:  # finance.models imports bookings.models; keep the runtime import graph one-way
    from apps.finance.models import Charge

NOT_BILLABLE = ("cancelled", "no_show")


def post_room_charges(stay, *, until_date, actor=None, source="automation") -> list[Charge]:
    """Post (idempotently) one `room` charge per night < `until_date` not yet posted:
    `post_charge(kind="room", amount=net, tax=lodging IVA, tax_exempt=booker.is_foreign_non_resident,
    night_date=night, stay=stay, business_date=night)`. Net = night amount without tax
    (amount/(1+rate) when the tax is included in the price).

    - "Not yet posted" = no non-voided `room` charge of this stay for that night (a voided night is posted
      again). Cancelled / no-show stays get nothing. Charges go to the reservation's guest folio.
    - The net comes from the night entry (`Stay.nightly_rates[i].net`); an entry without it (or a stay without
      breakdown, whose total is split evenly) is treated as tax-inclusive: `net = amount / (1 + rate)`.
    - The lodging tax is the first active room tax by code; exempt when it exempts foreign non-residents and
      the booker currently is one.
    - If a posted charge total differs from the night's amount (the guest's IVA exemption changed, rounding of
      an included tax), the night entry, the stay total and the reservation total follow the posted charge, so
      Σ room charges always equals the stay total.
    """
    from apps.finance import services as finance
    from apps.finance.models import Charge as ChargeModel

    with transaction.atomic():
        Reservation.objects.select_for_update().filter(pk=stay.reservation_id).values_list(
            "pk", flat=True
        ).first()
        stay = (
            Stay.objects.select_for_update(of=("self",))
            .select_related("reservation__property", "reservation__booker", "room", "room_type")
            .get(pk=stay.pk)
        )
        if stay.status in NOT_BILLABLE:
            return []
        done = set(
            ChargeModel.objects.filter(stay=stay, kind="room", voided_at__isnull=True).values_list(
                "night_date", flat=True
            )
        )
        pending = [night for night in stay.nights if night < until_date and night not in done]
        if not pending:
            return []
        reservation = stay.reservation
        prop = reservation.property
        currency = prop.currency or "COP"
        folio = finance.get_or_create_folio(reservation)
        tax = lodging_tax(prop)
        exempt = tax_exempt(tax, reservation.booker.is_foreign_non_resident)
        entries = {item["date"]: dict(item) for item in stay.nightly_rates or []}
        split = (
            dict(zip(stay.nights, split_amount(stay.total_amount, len(stay.nights), currency), strict=True))
            if not entries
            else {}
        )
        label = stay.room.number if stay.room_id else stay.room_type.code
        charges, corrected = [], False
        for night in pending:
            item = entries.get(night.isoformat())
            if item is not None and "net" in item:
                net = D(item["net"])
            else:
                amount = D(item["amount"]) if item is not None else split.get(night, D(0))
                net = _net_of(amount, tax, exempt, currency)
            charge = finance.post_charge(
                folio,
                kind="room",
                amount=net,
                description=f"Alojamiento · {label} · noche del {night.isoformat()}",
                tax=tax,
                tax_exempt=exempt,
                stay=stay,
                night_date=night,
                actor=actor,
                source=source,
                business_date=night,
            )
            charges.append(charge)
            if item is not None:
                posted = make_entry(
                    night, charge.amount + charge.tax_amount, charge.amount, charge.tax_amount
                )
                if posted != item:
                    entries[night.isoformat()] = posted
                    corrected = True
        if corrected:
            stay.nightly_rates = [entries[item["date"]] for item in stay.nightly_rates]
            stay.total_amount = entries_total(stay.nightly_rates)
            stay.save(update_fields=["nightly_rates", "total_amount", "updated_at"])
            refresh_reservation(reservation)
    return charges


def _net_of(amount, tax, exempt, currency):
    if tax is None or exempt:
        return quantize(amount, currency)
    return quantize(D(amount) / (1 + D(tax.rate) / 100), currency)
