"""Permission registry. Each app declares `PERMISSIONS = [(code, label_es, label_en), ...]` in
`apps/<app>/permissions.py`; roles store codes or fnmatch patterns (`bookings.*`, `*`)."""

from fnmatch import fnmatchcase
from importlib import import_module

from django.apps import apps as django_apps

PERMISSIONS: list[tuple[str, str, str]] = []  # core declares no permissions of its own

_REGISTRY: dict[str, tuple[str, str]] = {}


def register(code: str, label_es: str, label_en: str) -> None:
    _REGISTRY[code] = (label_es, label_en)


def catalog() -> dict[str, tuple[str, str]]:
    return dict(sorted(_REGISTRY.items()))


def codes_match(granted: list[str] | None, code: str) -> bool:
    return any(g == "*" or g == code or fnmatchcase(code, g) for g in granted or [])


def has_perm(user, prop, code: str) -> bool:
    from apps.accounts.models import Membership

    membership = (
        Membership.objects.select_related("role")
        .filter(user=user, organization=prop.organization, is_active=True)
        .first()
    )
    if not membership or not (membership.all_properties or membership.properties.filter(pk=prop.pk).exists()):
        return False
    return codes_match(membership.role.permissions, code)


def autodiscover() -> None:
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        try:
            module = import_module(f"{cfg.name}.permissions")
        except ModuleNotFoundError as exc:
            if exc.name != f"{cfg.name}.permissions":
                raise
            continue
        for code, label_es, label_en in getattr(module, "PERMISSIONS", []):
            register(code, label_es, label_en)
