"""Errors of the account security flows (P2). Rendered as `{"detail", "code"}` by the API handler."""

from apps.core.errors import DomainError


class InvalidToken(DomainError):
    """A password-reset or verification link that is malformed, already used or no longer matches the user."""

    code = "invalid_token"
    status_code = 400


class TokenExpired(DomainError):
    """A verification link older than its lifetime (the user can ask for a new one)."""

    code = "token_expired"
    status_code = 400


class EmailUnavailable(DomainError):
    """The mail server did not take the message: nothing was sent, the user can try again later."""

    code = "email_unavailable"
    status_code = 503
