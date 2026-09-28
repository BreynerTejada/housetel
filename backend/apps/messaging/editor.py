"""Template editor (plan C6): the effective templates of a hotel, validation of the staff's text and previews.

A template is identified by (code, channel, language). The effective one is the hotel's override, else the
organization's, else the system default (`defaults.SYSTEM_TEMPLATES`). Custom codes (not in the system
catalog) exist only as rows.
"""

import re

from django.db.models import Q

from apps.messaging.defaults import CODE_LABELS, SYSTEM_CODES, SYSTEM_TEMPLATES
from apps.messaging.models import MessageTemplate
from apps.messaging.renderer import (
    missing_variables,
    render_markup,
    render_plain,
    render_whatsapp,
    unknown_variables,
)
from apps.messaging.services import (
    TemplateNotFound,
    _one_line,
    message_language,
    render_email_document,
    resolve_template,
)
from apps.messaging.variables import VARIABLES, build_variables, normalize_language, sample_variables

CATALOG = frozenset(item["key"] for item in VARIABLES)
CHANNELS = ("email", "whatsapp")
LANGUAGES = ("es", "en")
CODE_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
WA_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]{1,512}$")
MAX_BODY = {"email": 20000, "whatsapp": 4000}


def _sort_key(key: tuple[str, str, str]) -> tuple:
    code, channel, language = key
    system = code in SYSTEM_CODES
    return (
        0 if system else 1,
        SYSTEM_CODES.index(code) if system else 0,
        code,
        CHANNELS.index(channel) if channel in CHANNELS else 9,
        LANGUAGES.index(language) if language in LANGUAGES else 9,
    )


def code_label(code: str, name: str = "") -> dict:
    return dict(CODE_LABELS.get(code) or {"es": name or code, "en": name or code})


def effective_templates(prop) -> list[dict]:
    """Every (code, channel, language) the hotel can use, with the text that applies and where it comes
    from."""
    rows = MessageTemplate.objects.filter(organization_id=prop.organization_id).filter(
        Q(property=prop) | Q(property__isnull=True)
    )
    levels: dict[tuple, dict[str, MessageTemplate]] = {}
    names: dict[str, str] = {}
    for row in rows:
        levels.setdefault((row.code, row.channel, row.language), {})[row.scope] = row
        if row.name and (row.code not in names or row.scope == "property"):
            names[row.code] = row.name
    items = []
    for key in sorted(set(SYSTEM_TEMPLATES) | set(levels), key=_sort_key):
        code, channel, language = key
        found = levels.get(key, {})
        row = found.get("property") or found.get("organization")
        item = {
            "key": f"{code}:{channel}:{language}",
            "code": code,
            "label": code_label(code, names.get(code, "")),
            "is_system_code": code in SYSTEM_CODES,
            "channel": channel,
            "language": language,
            "organization_template_id": found["organization"].pk if "organization" in found else None,
            "property_template_id": found["property"].pk if "property" in found else None,
        }
        if row is not None:
            item.update(
                source=row.scope,
                id=row.pk,
                subject=row.subject,
                body=row.body,
                is_active=row.is_active,
                wa_template_name=row.wa_template_name,
                wa_template_params=list(row.wa_template_params or []),
                updated_at=row.updated_at,
            )
        else:
            default = SYSTEM_TEMPLATES[key]
            item.update(
                source="system",
                id=None,
                subject=default["subject"],
                body=default["body"],
                is_active=True,
                wa_template_name="",
                wa_template_params=[],
                updated_at=None,
            )
        items.append(item)
    return items


def template_codes(prop) -> list[str]:
    custom = (
        MessageTemplate.objects.filter(organization_id=prop.organization_id)
        .filter(Q(property=prop) | Q(property__isnull=True))
        .exclude(code__in=SYSTEM_CODES)
        .values_list("code", flat=True)
    )
    return [*SYSTEM_CODES, *sorted(set(custom))]


def unknown_message(names: list[str]) -> str:
    return f"Variables desconocidas: {', '.join(names)}"


def preview(
    prop,
    *,
    channel: str,
    language=None,
    template_code: str = "",
    subject=None,
    body=None,
    guest=None,
    reservation=None,
) -> dict:
    """Render a template (the effective one of `template_code`, or a draft `subject`/`body`) for the guest and
    reservation given (the guest defaults to the booker), or with believable sample values when there are
    none."""
    guest = guest if guest is not None else getattr(reservation, "booker", None)
    if body is not None:
        source = "draft"
        lang = normalize_language(language) if language else message_language(prop, guest, reservation)
        subject = subject or ""
    else:
        lang = message_language(prop, guest, reservation, language)
        template = resolve_template(prop, template_code, channel, lang)
        if template is None:
            raise TemplateNotFound(f"No existe la plantilla «{template_code}»", template_code=template_code)
        source, lang, subject, body = template.source, template.language, template.subject, template.body
    sample = guest is None and reservation is None
    if sample:
        variables = sample_variables(prop, lang)
    else:
        variables = build_variables(property=prop, guest=guest, reservation=reservation, language=lang)
    rendered_subject = _one_line(render_plain(subject, variables), 255) if channel == "email" else ""
    combined = f"{subject}\n{body}" if channel == "email" else body
    return {
        "channel": channel,
        "language": lang,
        "source": source,
        "sample": sample,
        "subject": rendered_subject,
        "text": render_plain(body, variables),
        "whatsapp": render_whatsapp(body, variables),
        "markup": render_markup(body, variables),
        "html": render_email_document(
            prop, subject=rendered_subject, body_template=body, variables=variables, language=lang
        )
        if channel == "email"
        else "",
        "missing": [name for name in missing_variables(combined, variables) if name in CATALOG],
        "unknown": unknown_variables(combined, CATALOG),
    }
