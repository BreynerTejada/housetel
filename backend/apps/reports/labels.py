"""Spanish/English labels of the reports (column headers, KPIs, series, enum values, notes).

The JSON of every report and its CSV/XLSX/PDF exports are built in one language (`?lang=es|en`, default: the
user's language), so the labels live here, next to the definitions they describe. Page chrome (titles of the
hub, filters, buttons) lives in the frontend locales of the `reports` feature.
"""

from __future__ import annotations

LANGS = ("es", "en")

# --- Report titles (exports: PDF header, XLSX sheet, file names) ------------------------------------------

REPORT_TITLES: dict[str, tuple[str, str]] = {
    "performance": ("Rendimiento", "Performance"),
    "revenue-by-segment": ("Ingresos por segmento", "Revenue by segment"),
    "pickup": ("Pickup", "Pickup"),
    "forecast": ("Pronóstico (on the books)", "Forecast (on the books)"),
    "cancellations": ("Cancelaciones", "Cancellations"),
    "booking-window": ("Anticipación y duración", "Booking window and length of stay"),
    "guests-by-nationality": ("Huéspedes por nacionalidad", "Guests by nationality"),
    "occupancy-outlook": ("Ocupación prevista", "Occupancy outlook"),
    "arrivals": ("Llegadas", "Arrivals"),
    "departures": ("Salidas", "Departures"),
    "in-house": ("En casa", "In house"),
    "no-shows": ("No-shows", "No-shows"),
    "housekeeping-status": ("Estado de habitaciones", "Room status"),
    "daily-revenue": ("Ingresos diarios", "Daily revenue"),
    "payments-by-method": ("Pagos por medio", "Payments by method"),
    "cash-shifts": ("Turnos de caja", "Cash shifts"),
    "taxes": ("Impuestos (IVA)", "Taxes (VAT)"),
    "receivables": ("Saldos por cobrar", "Receivables"),
}

# --- Generic labels -----------------------------------------------------------------------------------------

LABELS: dict[str, tuple[str, str]] = {
    # dimensions
    "date": ("Fecha", "Date"),
    "week": ("Semana", "Week"),
    "month": ("Mes", "Month"),
    "segment": ("Segmento", "Segment"),
    "source": ("Fuente", "Source"),
    "channel": ("Canal", "Channel"),
    "room_type": ("Categoría", "Room type"),
    "rate_plan": ("Plan tarifario", "Rate plan"),
    "nationality": ("Nacionalidad", "Nationality"),
    "country": ("País", "Country"),
    "code": ("Reserva", "Booking"),
    "guest": ("Huésped", "Guest"),
    "vip": ("VIP", "VIP"),
    "status": ("Estado", "Status"),
    "room": ("Habitación", "Room"),
    "floor": ("Piso", "Floor"),
    "checkin": ("Llegada", "Arrival"),
    "checkout": ("Salida", "Departure"),
    "nights": ("Noches", "Nights"),
    "pax": ("Huéspedes", "Guests"),
    "eta": ("Hora de llegada", "ETA"),
    "created": ("Creada", "Booked"),
    "cancelled_on": ("Cancelada el", "Cancelled on"),
    "lead_days": ("Anticipación (días)", "Lead time (days)"),
    "reason": ("Motivo", "Reason"),
    "balance": ("Saldo", "Balance"),
    "total": ("Total", "Total"),
    "paid": ("Pagado", "Paid"),
    "method": ("Medio de pago", "Payment method"),
    "tax": ("Impuesto", "Tax"),
    "rate": ("Tarifa (%)", "Rate (%)"),
    "user": ("Usuario", "User"),
    "opened_at": ("Apertura", "Opened"),
    "closed_at": ("Cierre", "Closed"),
    "occupancy_state": ("Ocupación", "Occupancy"),
    "occupant": ("Huésped en casa", "Guest in house"),
    "arrival_today": ("Llega hoy", "Arriving today"),
    "departure_today": ("Sale hoy", "Departing today"),
    "days_since_checkout": ("Días desde la salida", "Days since departure"),
    "bucket": ("Rango", "Range"),
    "share": ("Participación", "Share"),
    # measures
    "available": ("Noches disponibles", "Available room nights"),
    "sold": ("Noches vendidas", "Room nights sold"),
    "occupancy": ("Ocupación", "Occupancy"),
    "adr": ("ADR", "ADR"),
    "revpar": ("RevPAR", "RevPAR"),
    "room_revenue": ("Ingresos de alojamiento", "Room revenue"),
    "room_revenue_short": ("Alojamiento", "Room"),
    "extras_revenue": ("Extras", "Extras"),
    "other_revenue": ("Otros ingresos", "Other revenue"),
    "fees_revenue": ("Cargos y ajustes", "Fees and adjustments"),
    "penalties": ("Penalidades", "Penalties"),
    "taxes": ("Impuestos", "Taxes"),
    "net_revenue": ("Total neto", "Net total"),
    "gross_revenue": ("Total con impuestos", "Total incl. taxes"),
    "forecast": ("Previsto", "Forecast"),
    "actual": ("Real", "Actual"),
    "previous": ("Periodo de comparación", "Comparison period"),
    "vs_previous_period": ("periodo anterior", "previous period"),
    "vs_previous_year": ("año anterior", "last year"),
    "reservations": ("Reservas", "Bookings"),
    "guests": ("Huéspedes únicos", "Unique guests"),
    "otb": ("On the books", "On the books"),
    "otb_before": ("On the books antes", "On the books before"),
    "pickup_nights": ("Pickup (noches)", "Pickup (room nights)"),
    "pickup_revenue": ("Pickup (ingresos)", "Pickup (revenue)"),
    "new_nights": ("Noches nuevas", "New room nights"),
    "lost_nights": ("Noches canceladas", "Cancelled room nights"),
    "new_reservations": ("Reservas nuevas", "New bookings"),
    "cancelled_reservations": ("Cancelaciones", "Cancellations"),
    "tentative_nights": ("Noches tentativas", "Tentative room nights"),
    "arrivals": ("Llegadas", "Arrivals"),
    "departures": ("Salidas", "Departures"),
    "cancellations": ("Cancelaciones", "Cancellations"),
    "cancellation_rate": ("Tasa de cancelación", "Cancellation rate"),
    "lost_revenue": ("Ingresos perdidos", "Lost revenue"),
    "fee": ("Penalidad", "Penalty"),
    "fees_charged": ("Penalidades cobradas", "Penalties charged"),
    "fees_pending": ("Penalidades por cobrar", "Penalties outstanding"),
    "avg_lead": ("Anticipación media", "Average lead time"),
    "median_lead": ("Anticipación mediana", "Median lead time"),
    "avg_los": ("Estadía media", "Average length of stay"),
    "same_day": ("Reservas del mismo día", "Same-day bookings"),
    "count": ("Cantidad", "Count"),
    "payments": ("Pagos", "Payments"),
    "payments_count": ("N.º de pagos", "No. of payments"),
    "refunds": ("Reembolsos", "Refunds"),
    "net_collected": ("Neto recaudado", "Net collected"),
    "online_share": ("Pagos en línea", "Online payments"),
    "shifts": ("Turnos", "Shifts"),
    "open_shifts": ("Turnos abiertos", "Open shifts"),
    "opening_float": ("Fondo inicial", "Opening float"),
    "cash_in": ("Efectivo recibido", "Cash received"),
    "cash_out": ("Efectivo devuelto", "Cash refunded"),
    "expected_cash": ("Esperado", "Expected"),
    "counted_cash": ("Contado", "Counted"),
    "difference": ("Diferencia", "Difference"),
    "differences": ("Turnos con diferencia", "Shifts with a difference"),
    "shift_open": ("Abierto", "Open"),
    "shift_closed": ("Cerrado", "Closed"),
    "taxable_base": ("Base gravada", "Taxable base"),
    "tax_amount": ("IVA", "VAT"),
    "exempt_base": ("Base exenta", "Exempt base"),
    "untaxed_base": ("No gravado", "Not taxed"),
    "exempt_charges": ("Cargos exentos", "Exempt charges"),
    "charges": ("Cargos", "Charges"),
    "no_tax": ("Sin impuesto", "No tax"),
    "receivable_total": ("Total por cobrar", "Total outstanding"),
    "receivable_departed": ("Salidas con saldo", "Departed with balance"),
    "receivable_in_house": ("En casa con saldo", "In house with balance"),
    "receivable_upcoming": ("Llegadas futuras", "Upcoming arrivals"),
    "receivable_penalties": ("Penalidades pendientes", "Unpaid penalties"),
    "countries": ("Países", "Countries"),
    "international_share": ("Noches de huéspedes extranjeros", "Room nights of foreign guests"),
    "top_country": ("Principal mercado", "Top market"),
    "rooms": ("Habitaciones", "Rooms"),
    "occupied": ("Ocupadas", "Occupied"),
    "vacant": ("Libres", "Vacant"),
    "blocked": ("Bloqueadas", "Blocked"),
    "vacant_dirty": ("Libres y sucias", "Vacant and dirty"),
    "arrivals_not_ready": ("Llegadas en habitación no lista", "Arrivals in a room not ready"),
    "arrivals_done": ("Ya llegaron", "Arrived"),
    "arrivals_pending": ("Por llegar", "Still to arrive"),
    "departures_done": ("Ya salieron", "Departed"),
    "departures_pending": ("Por salir", "Still to depart"),
    "unassigned": ("Sin habitación", "Unassigned"),
    "vip_count": ("VIP", "VIP"),
    "balance_due": ("Saldo pendiente", "Balance due"),
    "in_house_stays": ("Habitaciones ocupadas", "Occupied rooms"),
    "guests_in_house": ("Huéspedes en casa", "Guests in house"),
    "no_shows": ("No-shows", "No-shows"),
    "lost_nights_total": ("Noches perdidas", "Lost room nights"),
    "yes": ("Sí", "Yes"),
    "no": ("No", "No"),
    "none": ("Sin dato", "Unknown"),
    "other": ("Otros", "Other"),
    "unassigned_room": ("Sin asignar", "Unassigned"),
    "today": ("Hoy", "Today"),
    "total_row": ("Total", "Total"),
    # tables and charts
    "t_daily": ("Detalle por día", "Daily detail"),
    "t_weekly": ("Detalle por semana", "Weekly detail"),
    "t_monthly": ("Detalle por mes", "Monthly detail"),
    "t_segments": ("Segmentos", "Segments"),
    "t_pickup": ("Pickup por noche", "Pickup by night"),
    "t_forecast": ("Pronóstico por noche", "Forecast by night"),
    "t_cancellations": ("Reservas canceladas", "Cancelled bookings"),
    "t_cancellations_by_channel": ("Cancelaciones por canal", "Cancellations by channel"),
    "t_lead": ("Anticipación de la reserva", "Booking lead time"),
    "t_los": ("Duración de la estadía", "Length of stay"),
    "t_by_source": ("Promedios por fuente", "Averages by source"),
    "t_countries": ("Países", "Countries"),
    "t_arrivals": ("Llegadas", "Arrivals"),
    "t_departures": ("Salidas", "Departures"),
    "t_in_house": ("Estadías en casa", "In-house stays"),
    "t_no_shows": ("Reservas no-show", "No-show bookings"),
    "t_rooms": ("Habitaciones", "Rooms"),
    "t_methods": ("Por medio de pago", "By payment method"),
    "t_payments_daily": ("Recaudo por día", "Collections by day"),
    "t_shifts": ("Turnos", "Shifts"),
    "t_taxes": ("Por impuesto", "By tax"),
    "t_taxes_daily": ("Impuestos por día", "Taxes by day"),
    "t_receivables": ("Reservas con saldo", "Bookings with a balance"),
    "t_receivables_segments": ("Por tipo de saldo", "By balance type"),
    "t_receivables_aging": ("Antigüedad (salidas con saldo)", "Aging (departed guests)"),
    "t_outlook": ("Ocupación por noche", "Occupancy by night"),
    "c_occupancy": ("Ocupación por noche", "Occupancy by night"),
    "c_adr": ("ADR por noche", "ADR by night"),
    "c_revpar": ("RevPAR por noche", "RevPAR by night"),
    "c_room_revenue": ("Ingresos de alojamiento", "Room revenue"),
    "c_segments": ("Ingresos de alojamiento por segmento", "Room revenue by segment"),
    "c_pickup": ("Pickup por noche de estadía", "Pickup by stay night"),
    "c_forecast": ("Ocupación on the books", "Occupancy on the books"),
    "c_cancellations": ("Cancelaciones por día", "Cancellations by day"),
    "c_lead": ("Reservas por anticipación", "Bookings by lead time"),
    "c_los": ("Reservas por duración", "Bookings by length of stay"),
    "c_countries": ("Noches por país", "Room nights by country"),
    "c_rooms": ("Habitaciones por estado", "Rooms by status"),
    "c_daily_revenue": ("Ingresos por tipo", "Revenue by type"),
    "c_methods": ("Pagos por medio", "Payments by method"),
    "c_taxes": ("Base gravada y exenta por día", "Taxable and exempt base by day"),
    "c_receivables": ("Saldo por tipo", "Balance by type"),
    "c_outlook": ("Ocupación prevista", "Occupancy outlook"),
    "c_shift_differences": ("Diferencia por turno", "Difference by shift"),
}

# --- Enumerations -------------------------------------------------------------------------------------------

SOURCES: dict[str, tuple[str, str]] = {
    "walk_in": ("Walk-in", "Walk-in"),
    "phone": ("Teléfono", "Phone"),
    "email": ("Email", "Email"),
    "front_desk": ("Recepción", "Front desk"),
    "booking_engine": ("Motor de reservas", "Booking engine"),
    "marketplace": ("Marketplace Housetel", "Housetel marketplace"),
    "ota": ("OTA", "OTA"),
    "api": ("API", "API"),
}

CHANNELS: dict[str, tuple[str, str]] = {
    "direct": ("Directo", "Direct"),
    "marketplace": ("Marketplace Housetel", "Housetel marketplace"),
    "booking_engine": ("Motor de reservas", "Booking engine"),
    "booksim": ("BookSim", "BookSim"),
    "airsim": ("AirSim", "AirSim"),
    "channex": ("Channex", "Channex"),
    "ical": ("iCal", "iCal"),
}

RESERVATION_STATUSES: dict[str, tuple[str, str]] = {
    "tentative": ("Tentativa", "Tentative"),
    "confirmed": ("Confirmada", "Confirmed"),
    "checked_in": ("En casa", "In house"),
    "checked_out": ("Salió", "Checked out"),
    "cancelled": ("Cancelada", "Cancelled"),
    "no_show": ("No-show", "No-show"),
}

ROOM_STATUSES: dict[str, tuple[str, str]] = {
    "clean": ("Limpia", "Clean"),
    "inspected": ("Inspeccionada", "Inspected"),
    "dirty": ("Sucia", "Dirty"),
    "out_of_service": ("Fuera de servicio", "Out of service"),
}

OCCUPANCY_STATES: dict[str, tuple[str, str]] = {
    "occupied": ("Ocupada", "Occupied"),
    "vacant": ("Libre", "Vacant"),
    "blocked": ("Bloqueada", "Blocked"),
    "partial": ("Parcial", "Partly occupied"),
}

PAYMENT_METHODS: dict[str, tuple[str, str]] = {
    "cash": ("Efectivo", "Cash"),
    "card_terminal": ("Datáfono", "Card terminal"),
    "bank_transfer": ("Transferencia", "Bank transfer"),
    "wompi_card": ("Wompi · tarjeta", "Wompi · card"),
    "wompi_pse": ("Wompi · PSE", "Wompi · PSE"),
    "wompi_nequi": ("Wompi · Nequi", "Wompi · Nequi"),
    "wompi_other": ("Wompi · otro", "Wompi · other"),
    "ota_collect": ("Cobrado por la OTA", "Collected by the OTA"),
    "other": ("Otro", "Other"),
}

SHIFT_STATUSES: dict[str, tuple[str, str]] = {
    "open": ("Abierto", "Open"),
    "closed": ("Cerrado", "Closed"),
}

RECEIVABLE_SEGMENTS: dict[str, tuple[str, str]] = {
    "departed": LABELS["receivable_departed"],
    "in_house": LABELS["receivable_in_house"],
    "upcoming": LABELS["receivable_upcoming"],
    "penalties": LABELS["receivable_penalties"],
}

LEAD_BUCKETS: list[tuple[str, int, int | None, tuple[str, str]]] = [
    ("0", 0, 0, ("Mismo día", "Same day")),
    ("1-3", 1, 3, ("1 a 3 días", "1–3 days")),
    ("4-7", 4, 7, ("4 a 7 días", "4–7 days")),
    ("8-14", 8, 14, ("8 a 14 días", "8–14 days")),
    ("15-30", 15, 30, ("15 a 30 días", "15–30 days")),
    ("31-60", 31, 60, ("31 a 60 días", "31–60 days")),
    ("61-90", 61, 90, ("61 a 90 días", "61–90 days")),
    ("91+", 91, None, ("Más de 90 días", "Over 90 days")),
]

LOS_BUCKETS: list[tuple[str, int, int | None, tuple[str, str]]] = [
    ("1", 1, 1, ("1 noche", "1 night")),
    ("2", 2, 2, ("2 noches", "2 nights")),
    ("3", 3, 3, ("3 noches", "3 nights")),
    ("4", 4, 4, ("4 noches", "4 nights")),
    ("5", 5, 5, ("5 noches", "5 nights")),
    ("6", 6, 6, ("6 noches", "6 nights")),
    ("7", 7, 7, ("7 noches", "7 nights")),
    ("8-14", 8, 14, ("8 a 14 noches", "8–14 nights")),
    ("15+", 15, None, ("15 noches o más", "15 nights or more")),
]

AGING_BUCKETS: list[tuple[str, int, int | None, tuple[str, str]]] = [
    ("0-7", 0, 7, ("0 a 7 días", "0–7 days")),
    ("8-30", 8, 30, ("8 a 30 días", "8–30 days")),
    ("31-60", 31, 60, ("31 a 60 días", "31–60 days")),
    ("61+", 61, None, ("Más de 60 días", "Over 60 days")),
]

# ISO 3166-1 alpha-2 → (es, en) for the markets a Colombian hotel sees most. The UI shows every country with
# the browser's names (`Intl.DisplayNames`); exports fall back to the code for the rest.
COUNTRIES: dict[str, tuple[str, str]] = {
    "CO": ("Colombia", "Colombia"),
    "US": ("Estados Unidos", "United States"),
    "CA": ("Canadá", "Canada"),
    "MX": ("México", "Mexico"),
    "AR": ("Argentina", "Argentina"),
    "BR": ("Brasil", "Brazil"),
    "CL": ("Chile", "Chile"),
    "PE": ("Perú", "Peru"),
    "EC": ("Ecuador", "Ecuador"),
    "VE": ("Venezuela", "Venezuela"),
    "PA": ("Panamá", "Panama"),
    "CR": ("Costa Rica", "Costa Rica"),
    "UY": ("Uruguay", "Uruguay"),
    "PY": ("Paraguay", "Paraguay"),
    "BO": ("Bolivia", "Bolivia"),
    "DO": ("República Dominicana", "Dominican Republic"),
    "CU": ("Cuba", "Cuba"),
    "GT": ("Guatemala", "Guatemala"),
    "PR": ("Puerto Rico", "Puerto Rico"),
    "ES": ("España", "Spain"),
    "FR": ("Francia", "France"),
    "DE": ("Alemania", "Germany"),
    "GB": ("Reino Unido", "United Kingdom"),
    "IT": ("Italia", "Italy"),
    "PT": ("Portugal", "Portugal"),
    "NL": ("Países Bajos", "Netherlands"),
    "BE": ("Bélgica", "Belgium"),
    "CH": ("Suiza", "Switzerland"),
    "AT": ("Austria", "Austria"),
    "SE": ("Suecia", "Sweden"),
    "NO": ("Noruega", "Norway"),
    "DK": ("Dinamarca", "Denmark"),
    "FI": ("Finlandia", "Finland"),
    "IE": ("Irlanda", "Ireland"),
    "PL": ("Polonia", "Poland"),
    "RU": ("Rusia", "Russia"),
    "IL": ("Israel", "Israel"),
    "CN": ("China", "China"),
    "JP": ("Japón", "Japan"),
    "KR": ("Corea del Sur", "South Korea"),
    "IN": ("India", "India"),
    "AU": ("Australia", "Australia"),
    "NZ": ("Nueva Zelanda", "New Zealand"),
}


def pick(pair: tuple[str, str], lang: str) -> str:
    return pair[1] if lang == "en" else pair[0]


def tr(key: str, lang: str) -> str:
    """Label of `key` in `lang` (the key itself when unknown, so a typo is visible instead of empty)."""
    pair = LABELS.get(key)
    return pick(pair, lang) if pair else key


def enum_label(mapping: dict[str, tuple[str, str]], value: str | None, lang: str) -> str:
    if not value:
        return tr("none", lang)
    pair = mapping.get(value)
    return pick(pair, lang) if pair else str(value).replace("_", " ").capitalize()


def enum_labels(mapping: dict[str, tuple[str, str]], lang: str) -> dict[str, str]:
    return {code: pick(pair, lang) for code, pair in mapping.items()}


def country_label(code: str | None, lang: str) -> str:
    if not code:
        return tr("none", lang)
    pair = COUNTRIES.get(code.upper())
    return pick(pair, lang) if pair else code.upper()


def report_title(report_id: str, lang: str) -> str:
    pair = REPORT_TITLES.get(report_id)
    return pick(pair, lang) if pair else report_id
