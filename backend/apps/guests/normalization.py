"""How guest data is stored (plan B3): names in title case, email lowercase, phone E.164 (Colombia by
default), document number without dots or spaces. Used by every write path (upsert, create, update) so that
matching and duplicate detection compare like with like."""

import re
import unicodedata
from difflib import SequenceMatcher

import phonenumbers

# Lowercase joining words inside Spanish/Portuguese/French/Dutch/German names ("María de los Ángeles").
NAME_PARTICLES = frozenset({
    "de", "del", "la", "las", "los", "y", "e", "da", "das", "do", "dos", "van", "von", "der", "den", "di",
    "du", "le",
})  # fmt: skip

DEFAULT_PHONE_REGION = "CO"


def _capitalize_word(word: str) -> str:
    """ "o'brien" → "O'Brien", "jean-luc" → "Jean-Luc"."""
    return re.sub(r"(^|['’\-])(\w)", lambda m: m.group(1) + m.group(2).upper(), word.lower())


def normalize_name(value: str | None) -> str:
    """Title case for names typed all in lower or upper case; deliberate mixed case ("McDonald") is kept.

    Particles (de, del, la, los, y…) stay lowercase unless they open the name ("De la Hoz")."""
    words = (value or "").split()
    result = []
    for index, word in enumerate(words):
        if not (word.islower() or word.isupper()):
            result.append(word)
        elif index > 0 and word.lower() in NAME_PARTICLES:
            result.append(word.lower())
        else:
            result.append(_capitalize_word(word))
    return " ".join(result)


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_country(value: str | None) -> str:
    return (value or "").strip().upper()


def normalize_document(value: str | None) -> str:
    """Document number without dots or whitespace, uppercased ("x 1.234" → "X1234"). Dashes are kept (NIT
    check digit: "900123456-7")."""
    return re.sub(r"[.\s]", "", value or "").upper()


def _e164(number) -> str:
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def _best_number(text: str, region: str | None):
    """The first valid reading (in `region`, then Colombia), else the first possible one, else None."""
    possible = None
    for candidate_region in dict.fromkeys(r for r in ((region or "").upper(), DEFAULT_PHONE_REGION) if r):
        try:
            number = phonenumbers.parse(text, candidate_region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(number):
            return number
        if possible is None and phonenumbers.is_possible_number(number):
            possible = number
    return possible


def normalize_phone(value: str | None, *, region: str | None = DEFAULT_PHONE_REGION) -> str:
    """E.164 (`+573001234567`). A number without country code is read in `region` (e.g. the guest's country
    of residence) and, if not valid there, as Colombian. Input that is not a usable phone is kept trimmed:
    a booking must never fail or lose data because of a phone format."""
    text = (value or "").strip()
    if not text:
        return ""
    number = _best_number(text, region)
    return _e164(number) if number is not None else text


def is_usable_phone(value: str | None, *, region: str | None = DEFAULT_PHONE_REGION) -> bool:
    """True when `value` reads as a possible phone number (validation of staff input)."""
    text = (value or "").strip()
    return bool(text) and _best_number(text, region) is not None


def fold(value: str | None) -> str:
    """Accent- and case-insensitive form used to compare names ("Pérez  Gómez" → "perez gomez")."""
    decomposed = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(stripped.lower().split())


def similar_last_names(a: str | None, b: str | None) -> bool:
    """Same surname ignoring accents, same first surname ("Pérez" ~ "Perez Gómez") or a likely typo."""
    a, b = fold(a), fold(b)
    if not a or not b:
        return False
    if a == b or a.split()[0] == b.split()[0]:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.8
