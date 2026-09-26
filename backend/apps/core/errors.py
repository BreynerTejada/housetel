"""Domain errors. The API exception handler renders them as `{"detail", "code", **extra}` with
`status_code`."""


class DomainError(Exception):
    code = "domain_error"
    status_code = 400

    def __init__(self, message: str = "", *, code: str | None = None, **extra):
        super().__init__(message or self.__class__.__name__)
        self.message = message or str(self)
        if code:
            self.code = code
        self.extra = extra


class ConfirmationRequired(DomainError):
    code = "confirmation_required"
    status_code = 400


class PaymentRequiredError(DomainError):
    code = "organization_suspended"
    status_code = 402


class NotFoundError(DomainError):
    code = "not_found"
    status_code = 404


class ConflictError(DomainError):
    code = "conflict"
    status_code = 409
