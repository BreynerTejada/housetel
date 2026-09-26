"""Permissions of `compliance` (plan §D). Registered by apps.core.permissions.autodiscover()."""

PERMISSIONS = [
    ("compliance.view", "Ver facturación electrónica, SIRE y TRA", "View e-invoicing, SIRE and TRA"),
    ("compliance.invoice", "Emitir facturas electrónicas", "Issue e-invoices"),
    ("compliance.void_invoice", "Anular facturas (notas crédito)", "Void invoices (credit notes)"),
    ("compliance.sire", "Gestionar reportes SIRE", "Manage SIRE reports"),
    ("compliance.tra", "Gestionar registros TRA", "Manage TRA registrations"),
    ("compliance.settings", "Configurar facturación y legal", "Configure invoicing and compliance"),
]
