"""Cash shifts (caja). One open shift per user and property (enforced in the database).

Every manual payment a user takes while their shift is open is linked to it (`Payment.cash_shift`), and so
is every refund they give (`Refund.cash_shift`). Expected cash = opening float + approved cash payments −
approved refunds of cash payments. At close the user counts the drawer (optionally by denomination) and
the difference (counted − expected) is stored.
"""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

from apps.core import audit
from apps.core.errors import DomainError
from apps.core.money import D, quantize
from apps.finance.errors import CashShiftAlreadyOpen, CashShiftClosed
from apps.finance.models import CashShift, Payment, Refund

ZERO = Decimal("0")
CENTS = Decimal("0.01")


def _user(actor):
    return actor if getattr(actor, "is_authenticated", False) else None


def money_str(value) -> str:
    """API/audit money format: `"350000.00"`."""
    return f"{D(value).quantize(CENTS):f}"


def current_cash_shift(property, user) -> CashShift | None:
    """The user's open shift at the property, if any."""
    if _user(user) is None:
        return None
    return CashShift.objects.filter(property=property, user=user, closed_at__isnull=True).first()


def open_cash_shift(property, user, *, opening_float, notes="") -> CashShift:
    opening = quantize(opening_float, property.currency)
    if opening < 0:
        raise DomainError("El fondo inicial no puede ser negativo", code="invalid_amount")
    if current_cash_shift(property, user) is not None:
        raise CashShiftAlreadyOpen("Ya tienes un turno de caja abierto")
    try:
        with transaction.atomic():
            shift = CashShift.objects.create(
                property=property, user=user, opening_float=opening, notes=(notes or "").strip()
            )
    except IntegrityError:  # opened concurrently
        raise CashShiftAlreadyOpen("Ya tienes un turno de caja abierto") from None
    audit.record(
        action="finance.cash_shift_opened",
        target=shift,
        summary=f"Abrió turno de caja con fondo de {money_str(opening)}",
        actor=user,
        property=property,
        changes={"opening_float": money_str(opening)},
    )
    return shift


def cash_shift_totals(shift) -> dict:
    """Live totals of a shift: payments by method, cash in/out and the expected cash in the drawer."""
    payments = Payment.objects.filter(cash_shift=shift, status=Payment.Status.APPROVED)
    methods = list(
        payments.values("method").annotate(count=Count("id"), total=Sum("amount")).order_by("method")
    )
    by_method = {row["method"]: row["total"] for row in methods}
    cash_refunds = (
        Refund.objects.filter(
            cash_shift=shift, status=Refund.Status.APPROVED, payment__method=Payment.Method.CASH
        ).aggregate(total=Sum("amount"))["total"]
        or ZERO
    )
    cash_payments = by_method.get(Payment.Method.CASH, ZERO)
    return {
        "opening_float": shift.opening_float,
        "cash_payments": cash_payments,
        "cash_refunds": cash_refunds,
        "expected_cash": shift.opening_float + cash_payments - cash_refunds,
        "by_method": by_method,
        "methods": methods,  # [{"method", "count", "total"}] ordered by method
        "payments_count": sum(row["count"] for row in methods),
        "refunds_count": Refund.objects.filter(cash_shift=shift, status=Refund.Status.APPROVED).count(),
    }


def _count_denominations(denominations: dict) -> tuple[dict, Decimal]:
    cleaned: dict[str, int] = {}
    total = ZERO
    for raw_value, raw_count in denominations.items():
        try:
            value, count = int(str(raw_value)), int(raw_count)
        except (TypeError, ValueError):
            raise DomainError("Conteo por denominación inválido", code="invalid_denominations") from None
        if value <= 0 or count < 0:
            raise DomainError("Conteo por denominación inválido", code="invalid_denominations")
        if count:
            cleaned[str(value)] = count
            total += Decimal(value) * count
    return cleaned, total


def close_cash_shift(shift, *, actor, counted_cash=None, notes="", denominations=None) -> CashShift:
    """Close the shift with the counted cash (or a count by denomination, which must agree with it)."""
    with transaction.atomic():
        shift = CashShift.objects.select_for_update().select_related("property").get(pk=shift.pk)
        if shift.closed_at is not None:
            raise CashShiftClosed("Este turno de caja ya está cerrado")
        currency = shift.property.currency
        cleaned: dict = {}
        if denominations:
            cleaned, counted = _count_denominations(denominations)
            if counted_cash is not None and quantize(counted_cash, currency) != counted:
                raise DomainError(
                    "El total contado no coincide con el conteo por denominación",
                    code="denominations_mismatch",
                    counted=counted,
                )
        elif counted_cash is not None:
            counted = quantize(counted_cash, currency)
        else:
            raise DomainError("Indica el efectivo contado", code="counted_cash_required")
        if counted < 0:
            raise DomainError("El efectivo contado no puede ser negativo", code="invalid_amount")
        expected = cash_shift_totals(shift)["expected_cash"]
        shift.expected_cash = expected
        shift.counted_cash = counted
        shift.difference = counted - expected
        shift.closed_at = timezone.now()
        shift.closed_by = _user(actor)
        shift.denominations = cleaned
        shift.notes = "\n".join(part for part in (shift.notes, (notes or "").strip()) if part)
        shift.save()
        audit.record(
            action="finance.cash_shift_closed",
            target=shift,
            summary=(
                f"Cerró turno de caja: esperado {money_str(expected)}, contado {money_str(counted)}, "
                f"diferencia {money_str(shift.difference)}"
            ),
            actor=actor,
            property=shift.property,
            changes={
                "expected_cash": money_str(expected),
                "counted_cash": money_str(counted),
                "difference": money_str(shift.difference),
            },
        )
    return shift
