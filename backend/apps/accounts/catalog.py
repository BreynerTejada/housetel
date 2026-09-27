"""Permission catalog for the roles editor, and the anti-escalation rule.

Permissions are declared by each app in `apps/<app>/permissions.py` (plan §D) and registered by
apps.core.permissions. Roles store codes or fnmatch patterns (`bookings.*`, `*`).
"""

from importlib import import_module

from django.apps import apps as django_apps

from apps.core import permissions as registry
from apps.core.permissions import codes_match

# Module labels of the roles matrix (ES, EN), keyed by the code prefix.
MODULE_LABELS = {
    "accounts": ("Usuarios y roles", "Users & roles"),
    "inventory": ("Inventario", "Inventory"),
    "rates": ("Tarifas", "Rates"),
    "bookings": ("Reservas", "Reservations"),
    "guests": ("Huéspedes", "Guests"),
    "finance": ("Finanzas y caja", "Finance & cashier"),
    "frontdesk": ("Recepción", "Front desk"),
    "housekeeping": ("Limpieza y mantenimiento", "Housekeeping & maintenance"),
    "distribution": ("Canales", "Channels"),
    "marketplace": ("Marketplace y motor de reservas", "Marketplace & booking engine"),
    "guestportal": ("Portal del huésped", "Guest portal"),
    "messaging": ("Mensajería", "Messaging"),
    "compliance": ("Legal (DIAN, SIRE, TRA)", "Legal (DIAN, SIRE, TRA)"),
    "revenue": ("Revenue management", "Revenue management"),
    "ai": ("Inteligencia artificial", "Artificial intelligence"),
    "reports": ("Reportes", "Reports"),
    "saas": ("Plan y facturación de Housetel", "Housetel plan & billing"),
    "control": ("Centro de control", "Control center"),
}


def _declared_order() -> list[str]:
    """Codes in declaration order: apps in INSTALLED_APPS order, each app's PERMISSIONS as written."""
    ordered = []
    for config in django_apps.get_app_configs():
        if not config.name.startswith("apps."):
            continue
        try:
            module = import_module(f"{config.name}.permissions")
        except ModuleNotFoundError:
            continue
        ordered.extend(code for code, *_labels in getattr(module, "PERMISSIONS", []))
    return ordered


def permission_catalog() -> list[dict]:
    """`[{code, label_es, label_en, permissions: [{code, label_es, label_en}]}]`, one entry per module."""
    known = registry.catalog()
    ordered = list(dict.fromkeys([c for c in _declared_order() if c in known] + sorted(known)))
    modules: dict[str, dict] = {}
    for code in ordered:
        prefix = code.split(".", 1)[0]
        label_es, label_en = MODULE_LABELS.get(prefix, (prefix, prefix))
        module = modules.setdefault(
            prefix, {"code": prefix, "label_es": label_es, "label_en": label_en, "permissions": []}
        )
        es, en = known[code]
        module["permissions"].append({"code": code, "label_es": es, "label_en": en})
    return list(modules.values())


def codes_matched_by(granted: str) -> set[str]:
    """Catalog codes a stored code or pattern grants."""
    return {code for code in registry.catalog() if codes_match([granted], code)}


def unknown_permissions(requested: list[str]) -> list[str]:
    """Entries that grant nothing known (typos, removed codes), in the given order."""
    return [entry for entry in requested if not codes_matched_by(entry)]


def covers(granted: list[str] | None, requested: list[str]) -> bool:
    """True when `granted` includes every code that `requested` grants. `*` is only covered by `*`: it
    also grants permissions that do not exist yet."""
    granted = granted or []
    for entry in requested:
        if entry == "*" and "*" not in granted:
            return False
        if not all(codes_match(granted, code) for code in codes_matched_by(entry)):
            return False
    return True
