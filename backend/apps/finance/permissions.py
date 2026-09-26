"""Permissions of `finance` (plan §D). Registered by apps.core.permissions.autodiscover()."""

PERMISSIONS = [
    ("finance.view", "Ver folios y pagos", "View folios and payments"),
    ("finance.collect", "Registrar cargos y pagos", "Post charges and payments"),
    ("finance.void", "Anular cargos", "Void charges"),
    ("finance.refund", "Reembolsar pagos", "Refund payments"),
    ("finance.cashier", "Gestionar caja", "Manage cash shifts"),
]
