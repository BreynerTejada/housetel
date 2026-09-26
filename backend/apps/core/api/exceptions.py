"""API error format (spec §3.1): every error response is
`{"detail": str, "code": str, "fields"?: {...}, **extra}`.

- `DomainError` → its `status_code`, `code` and `extra` (Decimal/date/UUID extras rendered as strings).
- DRF `ValidationError` → 400 `validation_error` with `fields` (or its own `detail`/`code` when raised as
  `ValidationError({"detail": ..., "code": ...})`, e.g. `property_required`).
- Django `ValidationError`, `Http404`, `PermissionDenied` → same normalization.
- Exclusion / unique violations → 409 `conflict`; deleting a referenced row (PROTECT/RESTRICT) → 409 `in_use`.
- Anything else → `None` (Django renders a 500; bugs are never hidden behind a 4xx).
"""

from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError, RestrictedError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.serializers import as_serializer_error
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

from apps.core.errors import DomainError

CONFLICT_SQLSTATES = {"23P01": "exclusion", "23505": "unique"}  # exclusion_violation, unique_violation
GENERIC_VALIDATION_CODES = {"invalid", "validation_error"}


def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return _response({"detail": exc.message, "code": exc.code, **_jsonable(exc.extra)}, exc.status_code)
    if isinstance(exc, ProtectedError | RestrictedError):
        return _response(
            {"detail": "No se puede eliminar porque tiene registros asociados", "code": "in_use"},
            status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, IntegrityError):
        sqlstate = getattr(exc.__cause__, "sqlstate", None)
        if sqlstate not in CONFLICT_SQLSTATES:
            return None
        message = (
            "El recurso ya está ocupado en esas fechas"
            if CONFLICT_SQLSTATES[sqlstate] == "exclusion"
            else "Ya existe un registro con esos datos"
        )
        return _response({"detail": message, "code": "conflict"}, status.HTTP_409_CONFLICT)
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(detail=as_serializer_error(exc))
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound(*exc.args)
    elif isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied(*exc.args)

    response = drf_exception_handler(exc, context)
    if response is None:
        return None
    response.data = _normalize(exc)
    return response


def _response(data: dict, status_code: int) -> Response:
    set_rollback()
    return Response(data, status=status_code)


def _normalize(exc: exceptions.APIException) -> dict:
    detail = exc.detail
    if isinstance(detail, dict) and "detail" in detail:  # structured: {"detail", "code", **extra}
        data = _plain(detail)
        data["detail"] = _first_message(data["detail"])
        data.setdefault("code", exc.default_code)
        return data
    if isinstance(exc, exceptions.ValidationError):
        if isinstance(detail, dict):
            fields = _plain(detail)
            return {"detail": _first_message(fields), "code": "validation_error", "fields": fields}
        codes = exc.get_codes()
        code = _first_message(codes)
        return {
            "detail": _first_message(_plain(detail)),
            "code": "validation_error" if code in GENERIC_VALIDATION_CODES else code,
        }
    code = exc.get_codes()
    return {
        "detail": _first_message(_plain(detail)),
        "code": code if isinstance(code, str) else exc.default_code,
    }


def _plain(value):
    """ErrorDetail → str, recursively (keeps dict/list structure)."""
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return str(value)


def _first_message(value) -> str:
    if isinstance(value, dict):
        for item in value.values():
            message = _first_message(item)
            if message:
                return message
        return ""
    if isinstance(value, list | tuple):
        return next((message for message in map(_first_message, value) if message), "")
    return str(value)


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value
