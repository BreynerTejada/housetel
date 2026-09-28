"""System role templates (plan §D). Patterns use fnmatch (`bookings.*`, `*`)."""

ROLE_TEMPLATES = {
    "owner": {"name": "Dueño", "permissions": ["*"]},
    "manager": {"name": "Gerente", "permissions": [
        "accounts.*", "inventory.*", "rates.*", "bookings.*", "guests.*", "finance.*", "frontdesk.*",
        "housekeeping.*", "distribution.*", "marketplace.*", "guestportal.*", "messaging.*",
        "compliance.*", "revenue.*", "ai.*", "reports.*", "control.*", "saas.billing_view",
        "corporate.*", "imports.*"]},
    "front_desk": {"name": "Recepción", "permissions": [
        "frontdesk.view", "bookings.view", "bookings.manage", "bookings.checkin", "bookings.cancel",
        "guests.view", "guests.manage", "finance.view", "finance.collect", "finance.cashier",
        "messaging.view", "messaging.send", "guestportal.view", "guestportal.manage",
        "housekeeping.view", "compliance.view", "compliance.invoice", "compliance.sire", "compliance.tra",
        "reports.operational", "ai.copilot", "control.alerts", "inventory.view", "rates.view",
        "distribution.view", "revenue.view", "corporate.view"]},
    "housekeeping_supervisor": {"name": "Supervisor de limpieza", "permissions": [
        "housekeeping.*", "inventory.view", "control.alerts"]},
    "housekeeping": {"name": "Housekeeping", "permissions": [
        "housekeeping.view", "housekeeping.work", "inventory.view"]},
    "maintenance": {"name": "Mantenimiento", "permissions": [
        "housekeeping.view", "housekeeping.maintenance", "inventory.view"]},
    "accountant": {"name": "Contabilidad", "permissions": [
        "finance.*", "reports.*", "compliance.*", "bookings.view", "guests.view", "control.audit",
        "control.alerts", "saas.billing_view", "inventory.view", "rates.view", "corporate.*"]},
}  # fmt: skip

ROLE_DESCRIPTIONS = {
    "owner": "Acceso total a la organización.",
    "manager": "Gestiona toda la operación, excepto el plan y la facturación de Housetel.",
    "front_desk": "Reservas, check-in/out, huéspedes, cobros y caja.",
    "housekeeping_supervisor": "Supervisa y asigna la limpieza y el mantenimiento.",
    "housekeeping": "Realiza las tareas de limpieza asignadas.",
    "maintenance": "Atiende los tickets de mantenimiento.",
    "accountant": "Finanzas, reportes y cumplimiento legal.",
}
