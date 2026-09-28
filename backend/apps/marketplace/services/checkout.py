"""Online checkout: validate a selection, price it exactly (`quote_selection`) and book it (`create_booking`).

Both go through `plan_booking`, so the quote the guest sees is the reservation the booking creates:
- rooms priced with the same per-night entries as `create_reservation` (`offers.unit_price`);
- extras priced like `finance.post_charge` (net × quantity, tax rounded on the line, IVA of extras never
  exempt unless the tax says so);
- the IVA exemption of lodging follows nationality + residence exactly like `Guest.is_foreign_non_resident`.

Payment: `pay_now` pays the whole booking; `pay_at_hotel` pays nothing now, unless a plan asks for a deposit
(`deposit_percent`), then the deposit of each stay is paid now. Anything paid now makes the booking
`tentative` with a hold of `PAYMENT_HOLD_MINUTES` (the payment link expires with it, and PSE needs time); the
approved payment confirms it (bookings' `payment_received` receiver). Nothing to pay → `confirmed`.
"""

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction

from apps.bookings.services.availability import availability
from apps.bookings.services.pricing import QUOTE_WARNINGS, lodging_tax, tax_exempt
from apps.bookings.services.reservations import create_reservation
from apps.bookings.types import (
    AvailabilityError,
    BookingError,
    ReservationRequest,
    RestrictionError,
    StayRequest,
)
from apps.core.dates import nights as stay_nights
from apps.core.money import D, quantize
from apps.core.runtime import public_base_url
from apps.core.tokens import portal_url
from apps.finance import services as finance
from apps.finance.errors import OnlinePaymentsDisabled
from apps.guests.models import Guest
from apps.guests.types import GuestInput
from apps.inventory.models import RoomType
from apps.marketplace.services.catalog import channel_plans, effective_policy, policy_payload
from apps.marketplace.services.engine import (
    BOOKING_ENGINE,
    channel_property,
    check_stay_dates,
    engine_settings,
    online_payments_enabled,
)
from apps.marketplace.services.offers import UnitPrice, money, unit_price
from apps.rates.models import Extra
from apps.rates.services.quote import quote as rate_quote

PAYMENT_HOLD_MINUTES = 45  # ≥ 30: a PSE payment (bank redirect) must fit inside the hold
PAY_NOW = "pay_now"
ZERO = Decimal("0")


@dataclass
class PlannedItem:
    room_type: RoomType
    plan: object
    quantity: int
    adults: int
    children: int
    children_ages: list
    quote: object  # rates Quote per unit (dorm: per bed, one adult)
    unit: UnitPrice
    units_per_item: int  # dorm: one bed per guest; private: one room

    @property
    def units(self) -> int:
        return self.quantity * self.units_per_item

    @property
    def is_dorm(self) -> bool:
        return self.room_type.kind == RoomType.Kind.DORM

    @property
    def persons(self) -> int:
        return (self.adults + self.children) * self.quantity

    @property
    def deposit_per_unit(self) -> Decimal:
        percent = D(self.plan.deposit_percent)
        return quantize(self.unit.total * percent / 100, self.currency) if percent > 0 else ZERO

    currency: str = "COP"


@dataclass
class PlannedExtra:
    extra: Extra
    quantity: int
    unit_net: Decimal
    net: Decimal
    tax_amount: Decimal
    exempt: bool

    @property
    def total(self) -> Decimal:
        return self.net + self.tax_amount


@dataclass
class BookingPlan:
    prop: object
    via: str
    checkin: object
    checkout: object
    foreign: bool
    promo_code: str
    items: list[PlannedItem] = field(default_factory=list)
    extras: list[PlannedExtra] = field(default_factory=list)

    @property
    def currency(self) -> str:
        return self.prop.currency or "COP"

    @property
    def nights(self) -> int:
        return len(stay_nights(self.checkin, self.checkout))

    @property
    def lodging_total(self) -> Decimal:
        return sum((item.unit.total * item.units for item in self.items), ZERO)

    @property
    def extras_total(self) -> Decimal:
        return sum((extra.total for extra in self.extras), ZERO)

    @property
    def tax_total(self) -> Decimal:
        lodging = sum((item.unit.tax * item.units for item in self.items), ZERO)
        return lodging + sum((extra.tax_amount for extra in self.extras), ZERO)

    @property
    def discount_total(self) -> Decimal:
        return sum((D(item.quote.discount_total) * item.units for item in self.items), ZERO)

    @property
    def total(self) -> Decimal:
        return self.lodging_total + self.extras_total

    @property
    def deposit_total(self) -> Decimal:
        return sum((item.deposit_per_unit * item.units for item in self.items), ZERO)

    @property
    def requires_payment(self) -> bool:
        return any(D(item.plan.deposit_percent) > 0 for item in self.items)

    def due_now(self, payment_option: str) -> Decimal:
        return self.total if payment_option == PAY_NOW else self.deposit_total


def is_foreign_non_resident(nationality: str, residence: str) -> bool:
    """The rule of `Guest.is_foreign_non_resident` (ET art. 481 lit. d)."""
    return Guest(nationality=nationality or "", country_of_residence=residence or "").is_foreign_non_resident


def plan_booking(data: dict) -> BookingPlan:
    """Validate and price a selection (the validated body of `CheckoutSerializer`/`BookingSerializer`)."""
    prop = channel_property(data["property_slug"], data["via"])
    settings = engine_settings(prop)
    checkin, checkout = data["checkin"], data["checkout"]
    check_stay_dates(prop, checkin, checkout, settings)
    guest = data.get("guest") or {}
    foreign = is_foreign_non_resident(guest.get("nationality", ""), guest.get("country_of_residence", ""))
    promo_code = (data.get("promo_code") or "").strip()
    plan = BookingPlan(
        prop=prop, via=data["via"], checkin=checkin, checkout=checkout, foreign=foreign, promo_code=promo_code
    )
    sellable = {sold.pk: sold for sold in channel_plans(prop, data["via"], settings)}
    payments = online_payments_enabled(prop)
    tax = lodging_tax(prop)
    for raw in data["items"]:
        plan.items.append(_plan_item(prop, raw, plan, sellable, payments, tax))
    _check_availability(prop, plan)
    plan.extras = [_plan_extra(prop, raw, plan) for raw in data.get("extras") or []]
    return plan


def _plan_item(prop, raw, plan: BookingPlan, sellable, payments, tax) -> PlannedItem:
    room_type = RoomType.objects.filter(pk=raw["room_type_id"], property=prop, is_active=True).first()
    if room_type is None:
        raise BookingError("La categoría no existe en este hotel", code="invalid_room_type")
    rate_plan = sellable.get(raw["rate_plan_id"])
    if rate_plan is None or room_type.pk not in {rt.pk for rt in rate_plan.room_types.all()}:
        raise BookingError("Esta tarifa no se vende en línea para esta habitación", code="invalid_rate_plan")
    if D(rate_plan.deposit_percent) > 0 and not payments:
        raise OnlinePaymentsDisabled("Los pagos en línea están desactivados para este hotel")
    adults, children = int(raw["adults"]), int(raw.get("children") or 0)
    ages = list(raw.get("children_ages") or [])
    dorm = room_type.kind == RoomType.Kind.DORM
    _check_capacity(room_type, adults, children)
    unit_quote = rate_quote(
        property=prop,
        room_type=room_type,
        rate_plan=rate_plan,
        checkin=plan.checkin,
        checkout=plan.checkout,
        adults=1 if dorm else adults,
        children=0 if dorm else children,
        children_ages=None if dorm else (ages or None),
        promo_code=plan.promo_code or None,
        guest_is_foreign_non_resident=plan.foreign,
    )
    blocking = [violation for violation in unit_quote.violations if violation not in QUOTE_WARNINGS]
    if not unit_quote.restrictions_ok:
        raise RestrictionError("La estadía no cumple las restricciones de la tarifa", violations=blocking)
    if "no_rate" in unit_quote.violations:
        raise BookingError("Esta habitación no tiene precio para esas noches", code="no_rate")
    if plan.promo_code and not unit_quote.promo_applied:
        raise BookingError("El código promocional no es válido para esta reserva", code="promo_invalid")
    return PlannedItem(
        room_type=room_type,
        plan=rate_plan,
        quantity=int(raw.get("quantity") or 1),
        adults=adults,
        children=children,
        children_ages=ages,
        quote=unit_quote,
        unit=unit_price(prop, unit_quote, foreign=plan.foreign, tax=tax),
        units_per_item=adults + children if dorm else 1,
        currency=prop.currency or "COP",
    )


def _check_capacity(room_type, adults, children) -> None:
    if room_type.kind == RoomType.Kind.DORM:
        if children and not room_type.max_children:
            raise BookingError("Este dormitorio no admite niños", code="capacity_exceeded")
        return
    if (
        adults > room_type.max_adults
        or children > room_type.max_children
        or adults + children > room_type.max_occupancy
    ):
        raise BookingError(
            f"La habitación admite máximo {room_type.max_occupancy} huéspedes", code="capacity_exceeded"
        )


def _check_availability(prop, plan: BookingPlan) -> None:
    needed: Counter = Counter()
    for item in plan.items:
        needed[item.room_type.pk] += item.units
    free = availability(
        property=prop, checkin=plan.checkin, checkout=plan.checkout, room_type_ids=list(needed)
    )
    shortfalls = [
        {"room_type_id": str(type_id), "available": max(0, free.get(type_id, 0)), "requested": units}
        for type_id, units in needed.items()
        if free.get(type_id, 0) < units
    ]
    if shortfalls:
        raise AvailabilityError("Ya no hay disponibilidad para tu selección", shortfalls=shortfalls)


def default_extra_quantity(charge_type: str, *, persons: int, nights: int) -> int:
    """Per stay 1, per night N, per person P, per person-night P × N (as `finance.extra_default_quantity`)."""
    persons, nights = max(1, persons), max(1, nights)
    return {"per_night": nights, "per_person": persons, "per_person_night": persons * nights}.get(
        charge_type, 1
    )


def _plan_extra(prop, raw, plan: BookingPlan) -> PlannedExtra:
    extra = (
        Extra.objects.select_related("tax")
        .filter(pk=raw["extra_id"], property=prop, is_active=True, sellable_online=True)
        .first()
    )
    if extra is None:
        raise BookingError("Este extra no se vende en línea", code="invalid_extra")
    quantity = raw.get("quantity") or default_extra_quantity(
        extra.charge_type, persons=sum(item.persons for item in plan.items), nights=plan.nights
    )
    tax = extra.tax if extra.tax_id and extra.tax.is_active else None
    exempt = tax_exempt(tax, plan.foreign)
    unit_net = finance.extra_unit_net(extra, tax)
    net = quantize(unit_net * int(quantity), plan.currency)
    tax_amount = quantize(net * D(tax.rate) / 100, plan.currency) if tax is not None and not exempt else ZERO
    return PlannedExtra(
        extra=extra, quantity=int(quantity), unit_net=unit_net, net=net, tax_amount=tax_amount, exempt=exempt
    )


# ---- Quote -----------------------------------------------------------------------------------------------


def quote_payload(plan: BookingPlan, payment_option: str) -> dict:
    return {
        "property_slug": plan.prop.slug,
        "via": plan.via,
        "checkin": plan.checkin.isoformat(),
        "checkout": plan.checkout.isoformat(),
        "nights": plan.nights,
        "currency": plan.currency,
        "tax_exempt": plan.foreign and tax_exempt(lodging_tax(plan.prop), True),
        "items": [
            {
                "room_type_id": str(item.room_type.pk),
                "rate_plan_id": str(item.plan.pk),
                "room_type_name": item.room_type.name or {},
                "room_type_kind": item.room_type.kind,
                "rate_plan_name": item.plan.name or {},
                "meal_plan": item.plan.meal_plan,
                "quantity": item.quantity,
                "adults": item.adults,
                "children": item.children,
                "units": item.units,
                "net": money(item.unit.net * item.units),
                "tax": money(item.unit.tax * item.units),
                "total": money(item.unit.total * item.units),
                "discount": money(D(item.quote.discount_total) * item.units),
                "deposit": money(item.deposit_per_unit * item.units),
                "deposit_percent": money(item.plan.deposit_percent),
                "cancellation_policy": policy_payload(effective_policy(item.plan)),
            }
            for item in plan.items
        ],
        "extras": [
            {
                "extra_id": str(extra.extra.pk),
                "code": extra.extra.code,
                "name": extra.extra.name or {},
                "charge_type": extra.extra.charge_type,
                "quantity": extra.quantity,
                "unit_price": money(extra.unit_net),
                "net": money(extra.net),
                "tax": money(extra.tax_amount),
                "total": money(extra.total),
                "tax_exempt": extra.exempt,
            }
            for extra in plan.extras
        ],
        "lodging_total": money(plan.lodging_total),
        "extras_total": money(plan.extras_total),
        "tax_total": money(plan.tax_total),
        "discount_total": money(plan.discount_total),
        "total": money(plan.total),
        "deposit_total": money(plan.deposit_total),
        "requires_payment": plan.requires_payment,
        "due_now": {"pay_now": money(plan.total), "pay_at_hotel": money(plan.deposit_total)},
        "payment_option": payment_option,
        "amount_due_now": money(plan.due_now(payment_option)),
        "promo": {"code": plan.promo_code.upper(), "applied": True} if plan.promo_code else None,
        "online_payments": online_payments_enabled(plan.prop),
    }


def quote_selection(data: dict) -> dict:
    return quote_payload(plan_booking(data), data.get("payment_option") or "pay_at_hotel")


# ---- Booking ---------------------------------------------------------------------------------------------


def confirmation_path(prop, via: str, code: str) -> str:
    """Where the guest lands after booking (and where the payment gateway sends them back)."""
    if via == BOOKING_ENGINE:
        return f"/h/{prop.slug}/booking/{code}"
    return f"/booking/{code}/confirmed"


def _guest_input(guest: dict, language: str) -> GuestInput:
    return GuestInput(
        first_name=guest["first_name"],
        last_name=guest["last_name"],
        email=guest["email"],
        phone=guest.get("phone", ""),
        document_type=guest.get("document_type", ""),
        document_number=guest.get("document_number", ""),
        nationality=guest.get("nationality", ""),
        country_of_residence=guest.get("country_of_residence", ""),
        city_of_residence=guest.get("city_of_residence", ""),
        language=language,
        marketing_consent=bool(guest.get("marketing_consent")),
        data_processing_consent=bool(guest.get("data_processing_consent")),
    )


def _stay_requests(plan: BookingPlan) -> list[StayRequest]:
    stays = []
    for item in plan.items:
        for _ in range(item.quantity):
            stays.append(
                StayRequest(
                    room_type_id=item.room_type.pk,
                    rate_plan_id=item.plan.pk,
                    checkin=plan.checkin,
                    checkout=plan.checkout,
                    adults=item.adults,
                    children=item.children,
                    children_ages=list(item.children_ages),
                )
            )
    return stays


def reservation_deposit(reservation) -> Decimal:
    """Σ over stays of the plan's deposit (each stay rounded to the currency, as in the quote)."""
    currency = reservation.currency or "COP"
    total = ZERO
    for stay in reservation.stays.select_related("rate_plan"):
        percent = D(stay.rate_plan.deposit_percent)
        if percent > 0:
            total += quantize(D(stay.total_amount) * percent / 100, currency)
    return total


def create_booking(data: dict) -> dict:
    """Create the online reservation, post its extras and, when something is paid now, the payment link."""
    plan = plan_booking(data)
    prop, via = plan.prop, plan.via
    payment_option = data["payment_option"]
    due_now = plan.due_now(payment_option)
    if due_now > 0 and not online_payments_enabled(prop):
        raise OnlinePaymentsDisabled("Los pagos en línea están desactivados para este hotel")
    tentative = due_now > 0
    with transaction.atomic():
        reservation = create_reservation(
            ReservationRequest(
                property=prop,
                booker=_guest_input(data["guest"], data["language"]),
                stays=_stay_requests(plan),
                source=via,
                special_requests=data.get("special_requests") or "",
                promo_code=plan.promo_code,
                language=data["language"],
                eta=data.get("eta"),
                status="tentative" if tentative else "confirmed",
                hold_minutes=PAYMENT_HOLD_MINUTES if tentative else 0,
                guarantee="deposit" if tentative else "none",
            )
        )
        folio = finance.get_or_create_folio(reservation)
        for extra in plan.extras:
            finance.post_extra_charge(folio, extra.extra, quantity=extra.quantity, source="guest")
        total = finance.reservation_balance(reservation)
        payment = None
        if tentative:
            amount = total if payment_option == PAY_NOW else reservation_deposit(reservation)
            intent = finance.create_payment_intent(
                folio,
                amount=amount,
                return_url=f"{public_base_url()}{confirmation_path(prop, via, reservation.code)}",
            )
            payment = {
                "checkout_url": intent.checkout_url,
                "reference": intent.reference,
                "amount": money(intent.amount),
                "expires_at": intent.expires_at.isoformat() if intent.expires_at else None,
            }
    return {
        "reservation_code": reservation.code,
        "status": reservation.status,
        "via": via,
        "currency": reservation.currency,
        "total": money(total),
        "amount_due_now": payment["amount"] if payment else money(ZERO),
        "payment": payment,
        "hold_expires_at": reservation.hold_expires_at.isoformat() if reservation.hold_expires_at else None,
        "portal_url": portal_url(reservation),
        "confirmation_path": confirmation_path(prop, via, reservation.code),
    }


__all__ = ["PAYMENT_HOLD_MINUTES", "create_booking", "plan_booking", "quote_selection"]
