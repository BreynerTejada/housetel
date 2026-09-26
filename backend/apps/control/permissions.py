"""Permissions of `control` (plan §D). Registered by apps.core.permissions.autodiscover()."""

PERMISSIONS = [
    ("control.integrations", "Gestionar integraciones", "Manage integrations"),
    ("control.automations", "Gestionar automatizaciones", "Manage automations"),
    ("control.audit", "Ver auditoría", "View audit log"),
    ("control.audit_undo", "Deshacer acciones auditadas", "Undo audited actions"),
    ("control.alerts", "Ver y resolver alertas", "View and resolve alerts"),
]
