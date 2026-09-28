"""Account emails (P2): reset the password, verify the email address and the notice of a changed password.

They come from Housetel itself (not from a hotel), in the user's language (`User.language`: es | en), as
HTML (template `accounts/email/account.html`) with a plain-text alternative. `send_*` return False when the
mail server fails (the error is logged) and never raise: callers decide whether that matters.
"""

import logging
from datetime import datetime, timedelta

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger("housetel.accounts")

ACCENT = "#B4583B"  # Housetel terracotta (design token --accent)

TEXT = {
    "es": {
        "greeting": "Hola, {name}:",
        "greeting_anonymous": "Hola:",
        "fallback": "Si el botón no funciona, copia y pega este enlace en tu navegador:",
        "footer": "Housetel · Software para hoteles en Colombia",
        "hour": "{n} hora",
        "hours": "{n} horas",
        "days": "{n} días",
        "when": "%d/%m/%Y a las %H:%M (hora de Colombia)",
        "reset_subject": "Restablece tu contraseña de Housetel",
        "reset_title": "Elige una contraseña nueva",
        "reset_body": (
            "Recibimos una solicitud para restablecer la contraseña de tu cuenta de Housetel ({email})."
        ),
        "reset_cta": "Elegir contraseña nueva",
        "reset_expiry": (
            "El enlace sirve una sola vez y vence en {duration}. Al guardar la contraseña nueva cerramos la "
            "sesión en tus otros dispositivos."
        ),
        "reset_ignore": "¿No lo pediste tú? Ignora este correo: tu contraseña actual sigue funcionando.",
        "verify_subject": "Confirma tu correo en Housetel",
        "verify_title": "Confirma tu correo",
        "verify_body": (
            "Confirma que {email} es tu correo. Así sabemos que los avisos de tu cuenta, como los enlaces "
            "para recuperar el acceso, le llegan a la persona correcta."
        ),
        "verify_cta": "Confirmar mi correo",
        "verify_expiry": (
            "El enlace vence en {duration}. Si venció, pide otro en Housetel desde Configuración › Mi cuenta "
            "y seguridad."
        ),
        "verify_ignore": "¿No creaste una cuenta en Housetel? Ignora este correo.",
        "changed_subject": "Tu contraseña de Housetel cambió",
        "changed_title": "Tu contraseña cambió",
        "changed_body": (
            "La contraseña de tu cuenta de Housetel ({email}) se cambió el {when}. Cerramos la sesión en tus "
            "otros dispositivos."
        ),
        "changed_cta": "No fui yo: restablecer la contraseña",
        "changed_note": "Si fuiste tú, no tienes que hacer nada.",
    },
    "en": {
        "greeting": "Hi {name},",
        "greeting_anonymous": "Hi,",
        "fallback": "If the button does not work, copy and paste this link into your browser:",
        "footer": "Housetel · Hotel software for Colombia",
        "hour": "{n} hour",
        "hours": "{n} hours",
        "days": "{n} days",
        "when": "%Y-%m-%d at %H:%M (Colombia time)",
        "reset_subject": "Reset your Housetel password",
        "reset_title": "Choose a new password",
        "reset_body": "We received a request to reset the password of your Housetel account ({email}).",
        "reset_cta": "Choose a new password",
        "reset_expiry": (
            "The link works once and expires in {duration}. Saving the new password signs you out on your "
            "other devices."
        ),
        "reset_ignore": "Didn't ask for this? Ignore this email: your current password still works.",
        "verify_subject": "Confirm your email on Housetel",
        "verify_title": "Confirm your email",
        "verify_body": (
            "Confirm that {email} is your email address, so we know your account notices, like password "
            "recovery links, reach the right person."
        ),
        "verify_cta": "Confirm my email",
        "verify_expiry": (
            "The link expires in {duration}. If it expired, ask for a new one in Housetel under Settings › "
            "My account and security."
        ),
        "verify_ignore": "Didn't create a Housetel account? Ignore this email.",
        "changed_subject": "Your Housetel password changed",
        "changed_title": "Your password changed",
        "changed_body": (
            "The password of your Housetel account ({email}) was changed on {when}. We signed you out on "
            "your other devices."
        ),
        "changed_cta": "It wasn't me: reset the password",
        "changed_note": "If it was you, there is nothing else to do.",
    },
}


def language_of(user) -> str:
    return user.language if getattr(user, "language", None) in TEXT else "es"


def _duration(valid_for: timedelta, lang: str) -> str:
    """'3 días' / '1 hour': whole hours under two days, whole days from there."""
    text = TEXT[lang]
    hours = max(1, round(valid_for.total_seconds() / 3600))
    if hours < 48:
        return (text["hour"] if hours == 1 else text["hours"]).format(n=hours)
    return text["days"].format(n=round(hours / 24))


def _greeting(user, lang: str) -> str:
    names = (user.full_name or "").split()
    if not names:
        return TEXT[lang]["greeting_anonymous"]
    return TEXT[lang]["greeting"].format(name=names[0])


def _send(user, *, kind: str, lang: str, paragraphs: list[str], cta_url: str, notes: list[str]) -> bool:
    text = TEXT[lang]
    subject = text[f"{kind}_subject"]
    title = text[f"{kind}_title"]
    cta_label = text[f"{kind}_cta"]
    body = [_greeting(user, lang), *paragraphs]
    html = render_to_string(
        "accounts/email/account.html",
        {
            "lang": lang,
            "subject": subject,
            "preheader": paragraphs[0] if paragraphs else "",
            "accent": ACCENT,
            "title": title,
            "paragraphs": body,
            "cta_label": cta_label,
            "cta_url": cta_url,
            "fallback_label": text["fallback"],
            "notes": notes,
            "footer": text["footer"],
        },
    )
    plain = "\n\n".join([title, *body, f"{cta_label}:\n{cta_url}", *notes, f"—\n{text['footer']}"])
    message = EmailMultiAlternatives(subject, plain, None, [user.email])
    message.attach_alternative(html, "text/html")
    try:
        message.send()
    except Exception:  # SMTP down, rejected address…: the caller decides what to tell the user
        logger.exception("Could not send the %s email to user %s", kind, user.pk)
        return False
    return True


def send_password_reset_email(user, url: str, *, valid_for: timedelta) -> bool:
    lang = language_of(user)
    text = TEXT[lang]
    return _send(
        user,
        kind="reset",
        lang=lang,
        paragraphs=[text["reset_body"].format(email=user.email)],
        cta_url=url,
        notes=[text["reset_expiry"].format(duration=_duration(valid_for, lang)), text["reset_ignore"]],
    )


def send_verification_email(user, url: str, *, valid_for: timedelta) -> bool:
    lang = language_of(user)
    text = TEXT[lang]
    return _send(
        user,
        kind="verify",
        lang=lang,
        paragraphs=[text["verify_body"].format(email=user.email)],
        cta_url=url,
        notes=[text["verify_expiry"].format(duration=_duration(valid_for, lang)), text["verify_ignore"]],
    )


def send_password_changed_email(user, *, when: datetime, reset_url: str) -> bool:
    lang = language_of(user)
    text = TEXT[lang]
    moment = timezone.localtime(when).strftime(text["when"])
    return _send(
        user,
        kind="changed",
        lang=lang,
        paragraphs=[text["changed_body"].format(email=user.email, when=moment)],
        cta_url=reset_url,
        notes=[text["changed_note"]],
    )
