"""Room numbers for bulk creation: `"101-110,201,203"` → `["101", …, "110", "201", "203"]`.

A part is a range when both ends are `<letters><digits>` with the same letters ("A8-A10", "B1-3", "01-03":
zero padding follows the first end); anything else is a literal label ("Suite Mar", "PH-1"). Parts are
separated by commas, semicolons or new lines. Duplicates are kept so callers can report them
(`duplicates_in`).
"""

import re

from apps.core.errors import DomainError

MAX_ROOMS_PER_REQUEST = 500
MAX_NUMBER_LENGTH = 20  # Room.number max_length

_SEPARATORS = re.compile(r"[,;\n]")
_RANGE = re.compile(r"^([A-Za-z]*)(\d+)\s*-\s*([A-Za-z]*)(\d+)$")
_FLOOR = re.compile(r"^[A-Za-z]*(\d{3,})$")


def _invalid(message: str) -> DomainError:
    return DomainError(message, code="invalid_room_numbers", fields={"numbers": [message]})


def _expand(part: str) -> list[str]:
    match = _RANGE.match(part)
    if match is None:
        if len(part) > MAX_NUMBER_LENGTH:
            raise _invalid(f"«{part}» tiene más de {MAX_NUMBER_LENGTH} caracteres")
        return [part]
    prefix, first, end_prefix, last = match.groups()
    if end_prefix and end_prefix != prefix:
        raise _invalid(f"El rango «{part}» mezcla prefijos distintos")
    start, end = int(first), int(last)
    if end < start:
        raise _invalid(f"El rango «{part}» termina antes de empezar")
    if end - start + 1 > MAX_ROOMS_PER_REQUEST:
        raise _invalid(f"Máximo {MAX_ROOMS_PER_REQUEST} habitaciones por solicitud")
    width = len(first)
    numbers = [f"{prefix}{value:0{width}d}" for value in range(start, end + 1)]
    too_long = next((number for number in numbers if len(number) > MAX_NUMBER_LENGTH), None)
    if too_long:
        raise _invalid(f"«{too_long}» tiene más de {MAX_NUMBER_LENGTH} caracteres")
    return numbers


def parse_room_numbers(spec) -> list[str]:
    """Expand a spec (string, or list of numbers/ranges) into room numbers, in order, duplicates kept.

    Raises DomainError(code="invalid_room_numbers", fields={"numbers": [...]}) for an empty spec, reversed
    ranges, mixed prefixes, labels longer than 20 characters or more than MAX_ROOMS_PER_REQUEST numbers.
    """
    if isinstance(spec, str):
        parts = _SEPARATORS.split(spec)
    elif isinstance(spec, list | tuple):
        parts = [part for item in spec if item is not None for part in _SEPARATORS.split(str(item))]
    else:
        parts = []
    numbers: list[str] = []
    for raw in parts:
        part = raw.strip()
        if not part:
            continue
        numbers.extend(_expand(part))
        if len(numbers) > MAX_ROOMS_PER_REQUEST:
            raise _invalid(f"Máximo {MAX_ROOMS_PER_REQUEST} habitaciones por solicitud")
    if not numbers:
        raise _invalid("Indica al menos un número de habitación")
    return numbers


def duplicates_in(numbers: list[str]) -> list[str]:
    """Numbers that appear more than once, each listed once, in order of first repetition."""
    seen: set[str] = set()
    repeated: list[str] = []
    for number in numbers:
        if number in seen and number not in repeated:
            repeated.append(number)
        seen.add(number)
    return repeated


def infer_floor(number: str) -> str:
    """Hotel convention: the digits before the last two are the floor ("101" → "1", "1203" → "12").

    Numbers with fewer than three digits or with letters after the digits give "" (unknown).
    """
    match = _FLOOR.match(number.strip())
    if match is None:
        return ""
    return str(int(match.group(1)[:-2]))
