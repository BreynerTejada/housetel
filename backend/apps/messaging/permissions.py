"""Permissions of `messaging` (plan §D). Registered by apps.core.permissions.autodiscover()."""

PERMISSIONS = [
    ("messaging.view", "Ver bandeja de mensajes", "View inbox"),
    ("messaging.send", "Enviar mensajes", "Send messages"),
    (
        "messaging.templates",
        "Gestionar plantillas y mensajes automáticos",
        "Manage templates and automated messages",
    ),
]
