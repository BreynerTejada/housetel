"""The API exception handler renders every error as
{"detail": str, "code": str, "fields"?: {...}, **extra}."""

from decimal import Decimal

import psycopg.errors
import pytest
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import ProtectedError, RestrictedError
from django.http import Http404
from rest_framework import exceptions

from apps.core.api.exceptions import exception_handler
from apps.core.errors import ConfirmationRequired, DomainError, PaymentRequiredError


def handle(exc):
    return exception_handler(exc, {"view": None, "request": None})


def integrity_error(cause):
    error = IntegrityError(str(cause))
    error.__cause__ = cause
    return error


class InsufficientStock(DomainError):
    code = "insufficient_stock"
    status_code = 409


class TestDomainErrors:
    def test_status_code_and_extra_fields(self):
        response = handle(InsufficientStock("No hay disponibilidad", room_type="DBL", available=0))
        assert response.status_code == 409
        assert response.data == {
            "detail": "No hay disponibilidad",
            "code": "insufficient_stock",
            "room_type": "DBL",
            "available": 0,
        }

    def test_code_can_be_overridden_per_instance(self):
        response = handle(DomainError("Fechas inválidas", code="invalid_dates"))
        assert (response.status_code, response.data["code"]) == (400, "invalid_dates")

    def test_money_in_extra_is_rendered_as_string(self):
        response = handle(DomainError("Saldo pendiente", code="balance_due", amount=Decimal("150000.00")))
        assert response.data["amount"] == "150000.00"

    @pytest.mark.parametrize(
        ("exc", "status", "code"),
        [
            (ConfirmationRequired("Confirma la acción"), 400, "confirmation_required"),
            (PaymentRequiredError("Suspendida"), 402, "organization_suspended"),
        ],
    )
    def test_core_errors(self, exc, status, code):
        response = handle(exc)
        assert (response.status_code, response.data["code"]) == (status, code)


class TestValidationErrors:
    def test_field_errors_are_listed_under_fields(self):
        exc = exceptions.ValidationError(
            {"email": ["Este campo es obligatorio."], "adults": ["Debe ser ≥ 1."]}
        )
        response = handle(exc)
        assert response.status_code == 400
        assert response.data == {
            "detail": "Este campo es obligatorio.",
            "code": "validation_error",
            "fields": {"email": ["Este campo es obligatorio."], "adults": ["Debe ser ≥ 1."]},
        }

    def test_nested_field_errors_keep_their_structure_as_plain_strings(self):
        exc = exceptions.ValidationError({"stays": [{"checkin": ["Fecha inválida."]}]})
        response = handle(exc)
        assert response.data["fields"] == {"stays": [{"checkin": ["Fecha inválida."]}]}
        assert response.data["detail"] == "Fecha inválida."
        assert type(response.data["fields"]["stays"][0]["checkin"][0]) is str

    def test_non_field_error_keeps_a_specific_code(self):
        response = handle(
            exceptions.ValidationError("La salida debe ser posterior a la llegada", code="invalid_dates")
        )
        assert response.data == {
            "detail": "La salida debe ser posterior a la llegada",
            "code": "invalid_dates",
        }

    def test_non_field_error_with_the_generic_code_is_a_validation_error(self):
        response = handle(exceptions.ValidationError("Algo está mal"))
        assert response.data == {"detail": "Algo está mal", "code": "validation_error"}

    def test_structured_error_with_its_own_detail_and_code(self):
        exc = exceptions.ValidationError(
            {"detail": "Falta el encabezado X-Property-Id", "code": "property_required"}
        )
        response = handle(exc)
        assert (response.status_code, response.data) == (
            400,
            {"detail": "Falta el encabezado X-Property-Id", "code": "property_required"},
        )

    def test_django_validation_error_is_a_400(self):
        response = handle(DjangoValidationError({"overrides": ["Campo no sobrescribible: color"]}))
        assert response.status_code == 400
        assert response.data["code"] == "validation_error"
        assert response.data["fields"] == {"overrides": ["Campo no sobrescribible: color"]}


class TestHttpErrors:
    def test_permission_denied_with_extra_data(self):
        exc = exceptions.PermissionDenied(
            {
                "detail": "No tienes permiso para esta acción",
                "code": "permission_denied",
                "permission": "finance.refund",
            }
        )
        response = handle(exc)
        assert (response.status_code, response.data) == (
            403,
            {
                "detail": "No tienes permiso para esta acción",
                "code": "permission_denied",
                "permission": "finance.refund",
            },
        )

    @pytest.mark.parametrize(
        ("exc", "status", "code"),
        [
            (exceptions.NotFound("Propiedad no encontrada"), 404, "not_found"),
            (exceptions.NotAuthenticated(), 401, "not_authenticated"),
            (exceptions.MethodNotAllowed("DELETE"), 405, "method_not_allowed"),
            (exceptions.Throttled(wait=30), 429, "throttled"),
            (Http404(), 404, "not_found"),
            (DjangoPermissionDenied(), 403, "permission_denied"),
        ],
    )
    def test_standard_errors_get_a_detail_and_a_code(self, exc, status, code):
        response = handle(exc)
        assert response.status_code == status
        assert response.data["code"] == code
        assert isinstance(response.data["detail"], str) and response.data["detail"]

    def test_explicit_detail_message_is_kept(self):
        assert (
            handle(exceptions.NotFound("Propiedad no encontrada")).data["detail"] == "Propiedad no encontrada"
        )


class TestDatabaseErrors:
    def test_exclusion_violation_is_a_409_conflict(self):
        exc = integrity_error(
            psycopg.errors.ExclusionViolation("conflicting key value violates exclusion constraint")
        )
        response = handle(exc)
        assert (response.status_code, response.data["code"]) == (409, "conflict")

    def test_unique_violation_is_a_409_conflict(self):
        response = handle(integrity_error(psycopg.errors.UniqueViolation("duplicate key value")))
        assert (response.status_code, response.data["code"]) == (409, "conflict")

    @pytest.mark.parametrize("error_class", [ProtectedError, RestrictedError])
    def test_deleting_a_referenced_object_is_a_409_in_use(self, error_class):
        response = handle(error_class("referenced", set()))
        assert (response.status_code, response.data["code"]) == (409, "in_use")

    def test_other_integrity_errors_are_not_hidden(self):
        assert handle(integrity_error(psycopg.errors.NotNullViolation("null value"))) is None


def test_unexpected_exceptions_are_left_to_django():
    assert handle(RuntimeError("bug")) is None
