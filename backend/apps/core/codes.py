"""Human-readable codes (reservations `HT-7K2M9Q`, etc.) without ambiguous characters (0/O, 1/I/L)."""

import secrets

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_code(prefix: str = "HT", length: int = 6) -> str:
    body = "".join(secrets.choice(ALPHABET) for _ in range(length))
    return f"{prefix}-{body}" if prefix else body
