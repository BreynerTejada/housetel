"""Permissions of `guests` (plan §D). Registered by apps.core.permissions.autodiscover()."""

PERMISSIONS = [
    ("guests.view", "Ver huéspedes", "View guests"),
    ("guests.manage", "Gestionar huéspedes", "Manage guests"),
    ("guests.merge", "Fusionar huéspedes duplicados", "Merge duplicate guests"),
    ("guests.export", "Exportar datos de huéspedes", "Export guest data"),
]
