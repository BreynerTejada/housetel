"""NIT helpers (Colombian tax id). The check digit (dígito de verificación, DV) follows the DIAN modulo-11
algorithm with the weights 3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71 (right to left)."""

import re

_WEIGHTS = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
MAX_DIGITS = len(_WEIGHTS)


def normalize_nit(value: str) -> tuple[str, str]:
    """`"900.123.456-7"` → `("900123456", "7")`; `"900123456"` → `("900123456", "")`."""
    raw = (value or "").strip()
    base, _, dv = raw.partition("-")
    return re.sub(r"\D", "", base), re.sub(r"\D", "", dv)[:1]


def check_digit(nit: str) -> str:
    """DV of a NIT given without its check digit (non digits are ignored)."""
    digits = re.sub(r"\D", "", nit or "")
    total = sum(int(d) * _WEIGHTS[i] for i, d in enumerate(reversed(digits)))
    remainder = total % 11
    return str(11 - remainder if remainder > 1 else remainder)


def format_nit(nit: str, dv: str = "") -> str:
    """`"900123456", "7"` → `"900.123.456-7"`."""
    digits = re.sub(r"\D", "", nit or "")
    grouped = f"{int(digits):,}".replace(",", ".") if digits else ""
    return f"{grouped}-{dv}" if dv and grouped else grouped
