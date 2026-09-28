"""Finance domain errors (API: `{"detail", "code"}` with the class status).

Messages in Spanish, codes stable in English."""

from apps.core.errors import ConflictError, DomainError


class FolioClosedError(ConflictError):
    code = "folio_closed"


class AlreadyVoidedError(ConflictError):
    code = "already_voided"


class CashShiftRequired(ConflictError):
    code = "cash_shift_required"


class CashShiftAlreadyOpen(ConflictError):
    code = "cash_shift_open"


class CashShiftClosed(ConflictError):
    code = "cash_shift_closed"


class PaymentNotRefundable(ConflictError):
    code = "payment_not_refundable"


class PaymentNotVoidable(ConflictError):
    code = "payment_not_voidable"


class RefundExceedsPayment(DomainError):
    code = "refund_exceeds_payment"


class RefundNotPending(ConflictError):
    code = "refund_not_pending"


class OnlinePaymentsDisabled(ConflictError):
    code = "online_payments_disabled"


class IntegrationMisconfigured(DomainError):
    code = "integration_misconfigured"


class IntentClosed(ConflictError):
    """The payment link can no longer change (already paid or expired)."""

    code = "intent_closed"


class SimulationDisabled(ConflictError):
    """The hotel takes real payments now: its old simulated links can no longer be "paid"."""

    code = "simulation_disabled"


class ChargeInvoicedError(ConflictError):
    """P4: the charge is covered by an electronic invoice; annul it with a credit note before moving it."""

    code = "charge_invoiced"


class FolioMismatchError(DomainError):
    """P4: charges and payments move only between open folios of the same reservation."""

    code = "folio_mismatch"


class ProviderError(Exception):
    """A payment provider call failed (network, HTTP error, unexpected answer). Never shown raw to guests."""

    def __init__(self, message: str, *, status: int | None = None, payload: dict | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}
