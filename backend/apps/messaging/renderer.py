"""Safe template renderer (plan C6). Templates are plain text typed by the hotel staff:

- `{{dotted.name}}` placeholders are looked up in a flat dict of strings (see `variables.py`). Nothing is
  evaluated: an unknown name renders empty (and `missing_variables` reports it for the preview).
- A tiny markup: `**bold**`, `[label](url)` and blank lines between paragraphs. A link alone in its
  paragraph becomes a button in the email.
- Markup is parsed on the template *before* the values go in, so a value (a guest name typed in a booking
  form) can never add links, bold or HTML; in HTML every value is escaped.
"""

import html
import re

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\}\}")
_SENTINEL_RE = re.compile("\x00(\\d+)\x00")
_TOKEN_RE = re.compile(r"\[(?P<label>[^\]\n]+)\]\((?P<target>[^)\s]+)\)|\*\*(?P<bold>[^\n]+?)\*\*")
_LINK_ONLY_RE = re.compile(r"^\[(?P<label>[^\]\n]+)\]\((?P<target>[^)\s]+)\)$")
_PARAGRAPH_RE = re.compile(r"\n[ \t]*\n+")
_SAFE_URL_RE = re.compile(r"^(https?://|mailto:)", re.IGNORECASE)
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

BRAND_ACCENT = "#B4583B"  # Housetel terracotta (design tokens --accent)


def placeholders(template: str) -> list[str]:
    """Variable names used by `template`, once each, in order of appearance."""
    return list(dict.fromkeys(PLACEHOLDER_RE.findall(template or "")))


def missing_variables(template: str, variables: dict) -> list[str]:
    """Placeholders without a (non-empty) value: they would render empty."""
    return [name for name in placeholders(template) if not str(variables.get(name) or "")]


def unknown_variables(template: str, catalog) -> list[str]:
    """Placeholders that are not in the variables catalog (typos: they would always render empty)."""
    return [name for name in placeholders(template) if name not in catalog]


class _Prepared:
    """The template with each placeholder replaced by a sentinel, and the value of each sentinel."""

    def __init__(self, template: str, variables: dict):
        self.values: list[str] = []

        def _sentinel(match):
            value = variables.get(match.group(1))
            self.values.append("" if value is None else str(value))
            return f"\x00{len(self.values) - 1}\x00"

        text = (template or "").replace("\x00", "").replace("\r\n", "\n")
        self.text = PLACEHOLDER_RE.sub(_sentinel, text)

    def raw(self, text: str) -> str:
        return _SENTINEL_RE.sub(lambda m: self.values[int(m.group(1))], text)

    def escaped(self, text: str) -> str:
        """HTML of a text fragment: template text and values escaped, newlines as <br>."""
        escaped = html.escape(text, quote=True).replace("\n", "<br>")
        return _SENTINEL_RE.sub(lambda m: html.escape(self.values[int(m.group(1))], quote=True), escaped)


def _text_link(prepared: _Prepared, label: str, target: str) -> str:
    label_text, url = prepared.raw(label).strip(), prepared.raw(target).strip()
    if not url:
        return label_text
    return url if label_text in ("", url) else f"{label_text}: {url}"


def _render_text(template: str, variables: dict, bold: str) -> str:
    prepared = _Prepared(template, variables)

    def _token(match):
        if match.group("label") is not None:
            return _text_link(prepared, match.group("label"), match.group("target"))
        return f"{bold}{prepared.raw(match.group('bold'))}{bold}"

    parts, position = [], 0
    for match in _TOKEN_RE.finditer(prepared.text):
        parts.append(prepared.raw(prepared.text[position : match.start()]))
        parts.append(_token(match))
        position = match.end()
    parts.append(prepared.raw(prepared.text[position:]))
    return "".join(parts)


def render_plain(template: str, variables: dict) -> str:
    """Plain text (email alternative part, subjects, previews): bold markers dropped, links as
    `label: url`."""
    return _render_text(template, variables, bold="")


def render_whatsapp(template: str, variables: dict) -> str:
    """WhatsApp text: `**x**` → `*x*` (WhatsApp bold), links as `label: url`."""
    return _render_text(template, variables, bold="*")


def render_markup(template: str, variables: dict) -> str:
    """Values filled in, markup kept: what the inbox composer shows when a template is inserted (the reply is
    rendered for its channel when it is sent)."""
    prepared = _Prepared(template, variables)
    return prepared.raw(prepared.text)


def _safe_url(prepared: _Prepared, target: str) -> str | None:
    url = prepared.raw(target).strip()
    return url if _SAFE_URL_RE.match(url) else None


def _text_on(accent: str) -> str:
    """Dark or white text for a button of color `accent` (WCAG relative luminance)."""
    channels = [int(accent[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    return "#1F1C19" if luminance > 0.45 else "#FFFFFF"


def _inline_html(prepared: _Prepared, text: str, accent: str) -> str:
    parts, position = [], 0
    for match in _TOKEN_RE.finditer(text):
        parts.append(prepared.escaped(text[position : match.start()]))
        if match.group("label") is not None:
            url = _safe_url(prepared, match.group("target"))
            if url is None:
                parts.append(html.escape(_text_link(prepared, match.group("label"), match.group("target"))))
            else:
                parts.append(
                    f'<a href="{html.escape(url, quote=True)}" '
                    f'style="color:{accent};text-decoration:underline">'
                    f"{prepared.escaped(match.group('label'))}</a>"
                )
        else:
            parts.append(f"<strong>{prepared.escaped(match.group('bold'))}</strong>")
        position = match.end()
    parts.append(prepared.escaped(text[position:]))
    return "".join(parts)


def _button_html(prepared: _Prepared, label: str, url: str, accent: str) -> str:
    return (
        '<p style="margin:28px 0">'
        f'<a href="{html.escape(url, quote=True)}" style="display:inline-block;background:{accent};'
        f"color:{_text_on(accent)};text-decoration:none;font-weight:600;padding:12px 22px;"
        f'border-radius:10px">{prepared.escaped(label)}</a></p>'
    )


def render_html(template: str, variables: dict, *, accent: str = BRAND_ACCENT) -> str:
    """Email body HTML (the layout wraps it): escaped paragraphs, <br> line breaks, bold, links and
    buttons."""
    accent = accent if isinstance(accent, str) and _HEX_COLOR_RE.match(accent) else BRAND_ACCENT
    prepared = _Prepared(template, variables)
    blocks = []
    for paragraph in _PARAGRAPH_RE.split(prepared.text.strip()):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        link = _LINK_ONLY_RE.match(paragraph)
        url = _safe_url(prepared, link.group("target")) if link else None
        if link and url:
            blocks.append(_button_html(prepared, link.group("label"), url, accent))
        else:
            blocks.append(f"<p>{_inline_html(prepared, paragraph, accent)}</p>")
    return "\n".join(blocks)
