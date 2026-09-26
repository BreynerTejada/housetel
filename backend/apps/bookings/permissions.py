"""Permissions of `bookings` (plan §D). Registered by apps.core.permissions.autodiscover()."""

PERMISSIONS = [
    ("bookings.view", "Ver reservas", "View reservations"),
    ("bookings.manage", "Crear y modificar reservas", "Create and modify reservations"),
    ("bookings.checkin", "Hacer check-in y check-out", "Check guests in and out"),
    ("bookings.cancel", "Cancelar reservas", "Cancel reservations"),
    ("bookings.waive_fee", "Exonerar penalidades", "Waive fees"),
    (
        "bookings.checkout_with_balance",
        "Hacer check-out con saldo pendiente",
        "Check out with an outstanding balance",
    ),
    ("bookings.overbook", "Sobrevender", "Overbook"),
]
