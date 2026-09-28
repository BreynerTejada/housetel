"""Errors of the channel manager."""

from apps.core.errors import DomainError


class ChannelError(DomainError):
    """A channel (or its API) failed or refused a call. `retryable=False` for errors a retry cannot fix
    (missing credentials, invalid API key): the queue then fails at once instead of backing off."""

    code = "channel_error"
    status_code = 502

    def __init__(self, message: str = "", *, retryable: bool = True, code: str | None = None, **extra):
        super().__init__(message, code=code, **extra)
        self.retryable = retryable


class MappingError(DomainError):
    """A channel booking refers to a room or rate the connection does not map."""

    code = "unmapped"


class CalendarSkipped(DomainError):
    """The iCal provider of the configured mode does not read this calendar (simulated mode and an URL that
    is not a Housetel export): nothing is imported and nothing is cancelled."""

    code = "calendar_skipped"
