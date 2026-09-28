"""Email verification (P2).

A new user gets the link `${public_base_url}/verify-email/<token>` (receiver in apps/accounts/receivers.py).
Users created from an invitation are verified when they accept it, demo users and superusers are born
verified, and a password reset through the emailed link verifies the address too.

The token is signed with Django's signing (salt `accounts.verify-email`) and lasts VERIFICATION_LIFETIME. It
carries the user id and a digest of the address — not the address itself, since signed payloads are only
base64 — so it stops matching if the email changes.
"""

import hashlib
from datetime import timedelta

from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.emails import send_verification_email
from apps.accounts.errors import InvalidToken, TokenExpired
from apps.accounts.models import User
from apps.core import audit
from apps.core.runtime import public_base_url

SALT = "accounts.verify-email"
VERIFICATION_LIFETIME = timedelta(days=7)

INVALID_LINK = "El enlace de verificación no es válido."
EXPIRED_LINK = "El enlace de verificación venció. Pide uno nuevo desde Mi cuenta y seguridad."


def _email_digest(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def make_verification_token(user) -> str:
    return signing.dumps({"u": str(user.pk), "e": _email_digest(user.email)}, salt=SALT)


def verification_url(user) -> str:
    return f"{public_base_url()}/verify-email/{make_verification_token(user)}"


def send_verification(user) -> bool:
    """Email a fresh verification link. False if the mail server failed (logged)."""
    return send_verification_email(user, verification_url(user), valid_for=VERIFICATION_LIFETIME)


def send_verification_on_commit(user) -> None:
    """Email the link once the current transaction commits (nothing goes out if it rolls back), unless by then
    the user is verified or inactive. Used for new users (receivers.py) and for a new address set in the
    Django admin."""
    user_id = user.pk

    def send_if_still_pending() -> None:
        pending = User.objects.filter(pk=user_id, is_active=True, email_verified_at__isnull=True).first()
        if pending is not None:
            send_verification(pending)

    transaction.on_commit(send_if_still_pending, robust=True)


def verify_email(token: str) -> tuple[User, bool]:
    """Mark the address of the token as verified. Returns (user, verified_now): opening a valid link again
    answers (user, False) instead of an error."""
    try:
        data = signing.loads(token, salt=SALT, max_age=VERIFICATION_LIFETIME)
    except signing.SignatureExpired as exc:
        raise TokenExpired(EXPIRED_LINK) from exc
    except signing.BadSignature as exc:
        raise InvalidToken(INVALID_LINK) from exc
    if not isinstance(data, dict):
        raise InvalidToken(INVALID_LINK)
    with transaction.atomic():
        try:
            user = User.objects.select_for_update().filter(pk=data.get("u")).first()
        except (DjangoValidationError, ValueError, TypeError):
            user = None
        if user is None or not user.is_active or data.get("e") != _email_digest(user.email):
            raise InvalidToken(INVALID_LINK)
        if user.email_verified_at is not None:
            return user, False
        user.email_verified_at = timezone.now()
        user.save(update_fields=["email_verified_at", "updated_at"])
        audit.record(
            action="accounts.email_verified",
            target=user,
            actor=user,
            summary=f"{user.email} verificó su correo",
        )
    return user, True
