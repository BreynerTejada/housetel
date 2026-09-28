"""Password recovery and change (P2).

- `request_password_reset(email)` emails a one-time link `${public_base_url}/reset-password/<uidb64>/<token>`
  built with Django's PasswordResetTokenGenerator: it stops working once the password changes or the user
  logs in, and after `settings.PASSWORD_RESET_TIMEOUT` (Django's default, 3 days). Unknown or inactive
  addresses get nothing and the API answers the same way (no user enumeration).
- `reset_password(uidb64, token, new_password)` applies Django's password validators. The new password
  changes the session hash, so every other session of the user ends; the view logs this browser in.
- `change_password(user, ...)` checks the current password; the view keeps its own session with
  `update_session_auth_hash` (the others end) and the user gets an email notice.
"""

import hashlib
from datetime import timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone, translation
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.accounts.emails import language_of, send_password_changed_email, send_password_reset_email
from apps.accounts.errors import InvalidToken
from apps.accounts.models import User
from apps.core import audit
from apps.core.errors import DomainError
from apps.core.runtime import public_base_url

RESET_EMAIL_COOLDOWN = 60  # seconds between two reset emails to the same address
RESET_EMAILS_PER_HOUR = 5  # per address, whatever the IP of the requests

INVALID_LINK = "El enlace no es válido o ya se usó. Pide uno nuevo."
WRONG_PASSWORD = "La contraseña actual no es correcta"
SAME_PASSWORD = "La contraseña nueva debe ser distinta de la actual"


def reset_link_lifetime() -> timedelta:
    return timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT)


def password_reset_url(user) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f"{public_base_url()}/reset-password/{uid}/{default_token_generator.make_token(user)}"


def forgot_password_url(email: str = "") -> str:
    return f"{public_base_url()}/forgot-password" + (f"?email={quote(email)}" if email else "")


def mask_email(email: str) -> str:
    """'valentina@casaaurora.co' → 'v•••@casaaurora.co' (enough to recognize the account on a shared link)."""
    local, _, domain = email.partition("@")
    return f"{local[:1] if len(local) > 1 else ''}•••@{domain}"


def message_language(user, language: str | None = None) -> str:
    """`language` (the one on screen: what LocaleMiddleware picked for the request) when it is supported,
    otherwise the user's profile language."""
    code = (language or "").split("-")[0].lower()
    return code if code in dict(settings.LANGUAGES) else language_of(user)


def validate_new_password(
    user, password: str, *, field: str = "new_password", language: str | None = None
) -> None:
    """Django's AUTH_PASSWORD_VALIDATORS, with their messages in `message_language(user, language)`."""
    with translation.override(message_language(user, language)):
        try:
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            messages = [str(message) for message in exc.messages]
        else:
            return
    raise DomainError(messages[0], code="validation_error", fields={field: messages})


def _may_email(email: str) -> bool:
    """At most one reset email a minute and RESET_EMAILS_PER_HOUR an hour per address, so the form cannot
    flood someone's inbox (not even from many IPs)."""
    digest = hashlib.sha256(email.encode()).hexdigest()[:32]
    if not cache.add(f"accounts:pwreset:cooldown:{digest}", 1, RESET_EMAIL_COOLDOWN):
        return False
    key = f"accounts:pwreset:hour:{digest}"
    cache.add(key, 0, 3600)
    try:
        sent = cache.incr(key)
    except ValueError:  # the counter expired between add and incr
        cache.set(key, 1, 3600)
        sent = 1
    return sent <= RESET_EMAILS_PER_HOUR


def request_password_reset(email: str) -> bool:
    """Email the reset link when `email` belongs to an active user. Returns whether an email went out; the API
    never tells the caller."""
    email = User.objects.normalize_email(email)
    user = User.objects.filter(email__iexact=email, is_active=True).first() if email else None
    if user is None or not _may_email(user.email):
        return False
    return send_password_reset_email(user, password_reset_url(user), valid_for=reset_link_lifetime())


def _user_from_uid(uidb64: str, *, lock: bool = False) -> User | None:
    try:
        pk = force_str(urlsafe_base64_decode(uidb64))
        queryset = User.objects.select_for_update() if lock else User.objects.all()
        return queryset.get(pk=pk)
    except (TypeError, ValueError, OverflowError, DjangoValidationError, User.DoesNotExist):
        return None


def _valid_reset_user(uidb64: str, token: str, *, lock: bool = False) -> User:
    user = _user_from_uid(uidb64, lock=lock)
    if user is None or not user.is_active or not default_token_generator.check_token(user, token):
        raise InvalidToken(INVALID_LINK)
    return user


def check_reset_link(uidb64: str, token: str) -> User:
    """The user of a reset link that still works (InvalidToken otherwise). Changes nothing."""
    return _valid_reset_user(uidb64, token)


def reset_password(uidb64: str, token: str, new_password: str, *, language: str | None = None) -> User:
    """Set the new password from an emailed link. Also marks the email as verified (the link reached it).
    `language`: of the validation messages (the page's; default, the user's)."""
    with transaction.atomic():
        user = _valid_reset_user(uidb64, token, lock=True)
        validate_new_password(user, new_password, language=language)
        user.set_password(new_password)
        fields = ["password", "updated_at"]
        if user.email_verified_at is None:
            user.email_verified_at = timezone.now()
            fields.append("email_verified_at")
        user.save(update_fields=fields)
        audit.record(
            action="accounts.password_reset",
            target=user,
            actor=user,
            summary=f"{user.email} restableció su contraseña con el enlace del correo",
        )
    return user


def change_password(user, *, current_password: str, new_password: str, language: str | None = None) -> User:
    """Change the password of a signed-in user (the view keeps its session) and email them a notice.
    `language`: of the validation messages (default, the user's)."""
    if not user.check_password(current_password or ""):
        raise DomainError(
            WRONG_PASSWORD, code="wrong_password", fields={"current_password": [WRONG_PASSWORD]}
        )
    if new_password == current_password:
        raise DomainError(SAME_PASSWORD, code="same_password", fields={"new_password": [SAME_PASSWORD]})
    validate_new_password(user, new_password, language=language)
    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password", "updated_at"])
        audit.record(
            action="accounts.password_changed",
            target=user,
            actor=user,
            summary=f"{user.email} cambió su contraseña",
        )
    send_password_changed_email(user, when=timezone.now(), reset_url=forgot_password_url(user.email))
    return user
