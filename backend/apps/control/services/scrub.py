"""Secrets never leave the backend (spec C12): every JSON blob the control center returns (audit changes,
alert data, automation run details, integration config) goes through `scrub()`.

A key is treated as secret when it looks like a credential (`password`, `*_secret`, `api_key`,
`private_key`, `access_token`, `verify_token`…) or when the caller names it explicitly (the `secret` fields
declared by the integration providers). Its value is replaced by `MASK` (empty values stay empty, so the UI
can still tell "not set" from "set").
"""

import re

MASK = "•••"
# Values that only say whether a secret is set (e.g. the audit of an integration update) are not secrets.
SAFE_MARKERS = frozenset({"", MASK, "configurado", "actualizado", "eliminado"})

_SECRET_KEY = re.compile(
    r"(pass(word|wd)?|secret|credential|api_?key|private_?key|access_?key|signing_?key|(^|_)token$)",
    re.IGNORECASE,
)


def is_secret_key(key) -> bool:
    return bool(_SECRET_KEY.search(str(key)))


def scrub(value, *, secret_names=frozenset()):
    """Deep copy of `value` with the values of secret-looking keys masked."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            if (key in secret_names or is_secret_key(key)) and not _harmless(item):
                cleaned[key] = MASK
            else:
                cleaned[key] = scrub(item, secret_names=secret_names)
        return cleaned
    if isinstance(value, list | tuple):
        return [scrub(item, secret_names=secret_names) for item in value]
    return value


def _marker(value) -> bool:
    return value is None or isinstance(value, bool) or (isinstance(value, str) and value in SAFE_MARKERS)


def _harmless(item) -> bool:
    if isinstance(item, list | tuple):
        return all(_marker(part) for part in item)
    if isinstance(item, dict):
        return not item
    return _marker(item)


def redact_text(text: str, secrets: dict) -> str:
    """Remove literal secret values from a free text (e.g. a provider error that echoes a key)."""
    if not text:
        return text
    for value in secrets.values():
        if isinstance(value, str) and len(value) >= 6 and value in text:
            text = text.replace(value, MASK)
    return text
