"""Permissions of `inventory` (plan §D). Registered by apps.core.permissions.autodiscover()."""

PERMISSIONS = [
    ("inventory.view", "Ver inventario", "View inventory"),
    (
        "inventory.manage",
        "Gestionar inventario y perfil de la propiedad",
        "Manage inventory and property profile",
    ),
]
