"""Hotel-defined custom fields (spec §4 `CustomFieldDefinition`): which definitions apply and the central
validation of `custom_values`. `validate_custom_values` is re-exported by apps.inventory.services (contract).
"""

from datetime import date

from django.db.models import Q

from apps.core.errors import DomainError
from apps.inventory.models import CustomFieldDefinition


def custom_field_definitions(*, organization, applies_to: str, property=None) -> list[CustomFieldDefinition]:
    """Definitions of `applies_to` ("room_type" | "room" | "guest" | "reservation") for the organization:
    the organization-wide ones plus, when `property` is given, the ones of that property."""
    scope = Q(property__isnull=True)
    if property is not None:
        scope |= Q(property=property)
    return list(
        CustomFieldDefinition.objects.filter(
            scope, organization=organization, applies_to=applies_to
        ).order_by("sort_order", "key")
    )


def validate_custom_values(defs, values) -> dict:
    """Validate `values` against CustomFieldDefinitions (spec §4 central validation) and return them cleaned.

    Applies `default_value` for missing keys; rejects unknown keys, missing required ones and wrong types
    (text: str · number: int/float · boolean: bool · select: one option value · multiselect: list of option
    values · date: "YYYY-MM-DD"). Raises DomainError(code="invalid_custom_values", fields={key: [msg]}).
    """
    return clean_custom_values(defs, values)


def clean_custom_values(defs, values, *, partial: bool = False) -> dict:
    """`validate_custom_values`, or with `partial=True` only the given keys (no defaults, nothing required):
    used for values that override inherited ones (a room overriding its category's fields)."""
    if values is None:
        values = {}
    if not isinstance(values, dict):
        raise DomainError(
            "Los campos personalizados deben ser un objeto {clave: valor}",
            code="invalid_custom_values",
            fields={"custom_values": ["Debe ser un objeto {clave: valor}"]},
        )
    values = dict(values)
    definitions = {definition.key: definition for definition in defs}
    errors: dict[str, list[str]] = {
        key: ["Campo personalizado desconocido"] for key in values if key not in definitions
    }
    cleaned = {}
    for key, definition in definitions.items():
        if partial and key not in values:
            continue
        value = values.get(key)
        if value is None or value == "" or value == []:
            if partial:
                continue
            if definition.default_value is not None:
                cleaned[key] = definition.default_value
            elif definition.required:
                errors[key] = ["Este campo es obligatorio"]
            continue
        try:
            cleaned[key] = clean_custom_value(definition, value)
        except ValueError as exc:
            errors[key] = [str(exc)]
    if errors:
        raise DomainError("Hay campos personalizados inválidos", code="invalid_custom_values", fields=errors)
    return cleaned


def option_values(definition) -> set:
    return {option["value"] if isinstance(option, dict) else option for option in definition.options or []}


def clean_custom_value(definition, value):
    """One value against its definition's `field_type`; raises ValueError with a Spanish message."""
    field_type = definition.field_type
    options = option_values(definition)
    if field_type == "text":
        if not isinstance(value, str):
            raise ValueError("Debe ser un texto")
        return value
    if field_type == "number":
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("Debe ser un número")
        return value
    if field_type == "boolean":
        if not isinstance(value, bool):
            raise ValueError("Debe ser sí o no")
        return value
    if field_type == "select":
        if value not in options:
            raise ValueError(f"Opción inválida: {value}")
        return value
    if field_type == "multiselect":
        if not isinstance(value, list) or any(item not in options for item in value):
            raise ValueError("Opciones inválidas")
        return value
    if field_type == "date":
        if isinstance(value, date):
            return value.isoformat()
        try:
            return date.fromisoformat(value).isoformat()
        except (TypeError, ValueError):
            raise ValueError("Debe ser una fecha AAAA-MM-DD") from None
    raise ValueError(f"Tipo de campo desconocido: {field_type}")
