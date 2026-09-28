"""Billing rules of a reservation (who pays which charges). Pure reads: finance imports it lazily from
`post_charge` and the balances, so it must stay light and never write.

Categories of `ReservationBilling.routing` by charge kind:
- `lodging`: room nights (`room`, each night with its IVA: the DIAN requires invoicing the tax to the same
  buyer as the service) and cancellation / no-show fees (`cancellation_fee`);
- `lodging_taxes`: lodging taxes and levies posted as their own charge (`tax`, e.g. seguro hotelero or a
  municipal tourism fee);
- `extras`: extras, fees and other charges (`extra`, `fee`, `other`);
- `all`: everything, adjustments (discounts) included.
"""

from apps.corporate.models import ReservationBilling

Route = ReservationBilling.Route
ROUTE_VALUES = [route.value for route in Route]
KIND_CATEGORY = {
    "room": Route.LODGING,
    "cancellation_fee": Route.LODGING,
    "tax": Route.LODGING_TAXES,
    "extra": Route.EXTRAS,
    "fee": Route.EXTRAS,
    "other": Route.EXTRAS,
}


def category_of(kind: str) -> str | None:
    """Routing category of a charge kind (adjustments only follow `all`)."""
    return KIND_CATEGORY.get(kind)


def routes_kind(billing, kind: str) -> bool:
    """True when `billing` sends charges of `kind` to its company folio."""
    if billing is None or billing.bill_to != ReservationBilling.BillTo.COMPANY or billing.company_id is None:
        return False
    routing = set(billing.routing or [])
    return Route.ALL in routing or category_of(kind) in routing


def billing_of(reservation) -> ReservationBilling | None:
    return ReservationBilling.objects.filter(reservation_id=reservation.pk).select_related("company").first()


def lodging_company(reservation):
    """The company the reservation's lodging is billed to, or None (guest)."""
    billing = billing_of(reservation)
    return billing.company if routes_kind(billing, "room") else None
