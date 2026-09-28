"""Channel providers (plan C3 › Proveedores). Auto-discovered by `apps.core.integrations.autodiscover`.

Every provider speaks the same interface, with the connection as first argument:

- `push_ari(connection, batches: list[AriBatch]) -> dict` — send availability, rates and restrictions.
- `fetch_bookings(connection) -> list[InboundBooking]` and `acknowledge(connection, booking)` — pull-based
  channels (Channex booking revisions feed; the simulated Channex keeps its bookings until they are pulled).
- `fetch_calendar(connection, mapping) -> str` — iCal calendars to import.
- `remote_catalog(connection=None) -> {"rooms": [...], "rates": [...]}` — the channel's rooms and rates, for
  the mapping step of the wizard.
- `test_connection(connection=None) -> (ok, message)`.

BookSim and AirSim are simulated OTAs with no integration kind of their own: `SimulatedOtaProvider` serves
them directly. iCal and Channex are integrations of `core` (`channel_ical`, `channel_channex`) with a `real`
and a `simulated` provider each; the property's `IntegrationSetting` picks the mode (simulated by default).
"""

import ipaddress
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit, urlunsplit

import httpx

from apps.core import integrations
from apps.core.integrations import BaseProvider, register_provider
from apps.distribution.errors import CalendarSkipped, ChannelError
from apps.distribution.models import ChannelConnection, SimOtaInventory
from apps.distribution.types import InboundBooking, InboundRoom

SIM_CHANNELS = (ChannelConnection.Channel.BOOKSIM, ChannelConnection.Channel.AIRSIM)
CHANNEL_KINDS = {
    ChannelConnection.Channel.ICAL: "channel_ical",
    ChannelConnection.Channel.CHANNEX: "channel_channex",
}
SIM_FIELDS = ("available", "price", "min_los", "max_los", "closed_to_arrival", "closed_to_departure")
EXTERNAL_PREFIXES = {"booksim": "BS", "airsim": "AS", "channex": "CX", "ical": "IC"}


def write_sim_inventory(connection, batches) -> int:
    """Store the batches as the simulated OTA would: one cell per room × rate × night, overwritten by each
    push. A category without mapped rates keeps its availability in cells with an empty rate id."""
    cells = []
    for batch in batches:
        if not batch.external_room_id:
            continue
        rates = batch.rates or [None]
        for rate in rates:
            days = rate.days if rate is not None else [None] * len(batch.availability)
            for day, (night, available) in zip(days, batch.availability.items(), strict=True):
                cells.append(
                    SimOtaInventory(
                        connection=connection,
                        external_room_id=batch.external_room_id,
                        external_rate_id=rate.external_rate_id if rate is not None else "",
                        date=night,
                        available=available,
                        price=day.price if day is not None else None,
                        min_los=day.min_los if day is not None else None,
                        max_los=day.max_los if day is not None else None,
                        closed_to_arrival=bool(day and day.closed_to_arrival),
                        closed_to_departure=bool(day and day.closed_to_departure),
                        stop_sell=bool(day and day.stop_sell),
                    )
                )
    SimOtaInventory.objects.bulk_create(
        cells,
        batch_size=1000,
        update_conflicts=True,
        unique_fields=["connection", "external_room_id", "external_rate_id", "date"],
        update_fields=[*SIM_FIELDS, "stop_sell", "updated_at"],
    )
    return len(cells)


def suggested_catalog(prop, channel_code: str) -> dict:
    """Rooms and rates a simulated channel offers for mapping: one per active category and per active plan,
    with readable ids (`BS-DBL`, `BS-FLEX`)."""
    from apps.core.i18n import t
    from apps.inventory.models import RoomType
    from apps.rates.models import RatePlan

    prefix = EXTERNAL_PREFIXES.get(channel_code, "CH")
    rooms = [
        {"id": f"{prefix}-{room_type.code}", "title": t(room_type.name) or room_type.code}
        for room_type in RoomType.objects.filter(property=prop, is_active=True).order_by("sort_order", "code")
    ]
    rates = [
        {
            "id": f"{prefix}-{plan.code}",
            "title": t(plan.name) or plan.code,
            "room_id": None,
            "currency": prop.currency,
        }
        for plan in RatePlan.objects.filter(property=prop, is_active=True).order_by(
            "kind", "sort_order", "code"
        )
    ]
    return {"rooms": rooms, "rates": rates}


class SimulatedOtaProvider:
    """BookSim / AirSim: the OTA lives in this database (`SimOtaInventory`, `SimOtaBooking`). Its bookings
    reach the PMS through `importer.import_booking`, the same path a real channel uses."""

    mode = "simulated"
    label = "Simulador de OTAs"

    def push_ari(self, connection, batches) -> dict:
        return {"cells": write_sim_inventory(connection, batches)}

    def fetch_bookings(self, connection) -> list:
        return []  # BookSim/AirSim deliver each booking the moment it is made (see services.simulator)

    def acknowledge(self, connection, booking) -> None:
        return None

    def remote_catalog(self, connection=None) -> dict:
        return suggested_catalog(connection.property, connection.channel_code) if connection else {}

    def test_connection(self, connection=None) -> tuple[bool, str]:
        return True, "Simulador listo: la OTA recibe el ARI y crea reservas desde /app/simulators/ota"


class ChannelProvider(BaseProvider):
    """Base of the `channel_ical` / `channel_channex` providers: every method is optional."""

    def push_ari(self, connection, batches) -> dict:
        raise ChannelError(
            "Este canal no recibe disponibilidad ni tarifas", retryable=False, code="not_supported"
        )

    def fetch_bookings(self, connection) -> list:
        return []

    def acknowledge(self, connection, booking) -> None:
        return None

    def fetch_calendar(self, connection, mapping) -> str:
        raise CalendarSkipped("Este proveedor no descarga calendarios")

    def remote_catalog(self, connection=None) -> dict:
        return {"rooms": [], "rates": []}

    def test_connection(self, connection=None) -> tuple[bool, str]:
        return True, "OK"


# --- iCal ---------------------------------------------------------------------------------------------------

ICAL_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
ICAL_MAX_BYTES = 5 * 1024 * 1024
ICAL_USER_AGENT = "Housetel-ChannelManager/1.0 (+https://housetel.co)"
INTERNAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home")


def normalize_calendar_url(url: str) -> str:
    """`webcal://` (what listing sites often show) is HTTPS."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() == "webcal":
        parts = parts._replace(scheme="https")
    return urlunsplit(parts)


def check_public_url(url: str) -> None:
    """Refuse URLs that point to this server's private network (the import runs on the server): only
    http(s), no loopback/private/link-local IP literals and no single-label or `.local`-style host names.
    DNS answers are not resolved here (documented limitation)."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise ChannelError(
            "La URL del calendario debe empezar por https://", retryable=False, code="invalid_url"
        )
    host = parts.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if host == "localhost" or "." not in host or host.endswith(INTERNAL_SUFFIXES):
            raise ChannelError(
                "La URL del calendario apunta a una red interna", retryable=False, code="invalid_url"
            ) from None
        return
    if not address.is_global:
        raise ChannelError(
            "La URL del calendario apunta a una red interna", retryable=False, code="invalid_url"
        )


def _check_request(request: httpx.Request) -> None:  # every hop of a redirect chain is checked too
    check_public_url(str(request.url))


class RealIcalProvider(ChannelProvider):
    """Downloads the calendars of listing sites (Airbnb, VRBO, Booking.com…) over HTTP(S)."""

    kind = "channel_ical"
    mode = "real"
    label = "iCal: descarga los calendarios de Airbnb, VRBO, Booking.com…"
    CONFIG_FIELDS: list[dict] = []

    def fetch_calendar(self, connection, mapping) -> str:
        url = normalize_calendar_url(mapping.ical_import_url)
        check_public_url(url)
        try:
            with httpx.Client(
                timeout=ICAL_TIMEOUT,
                follow_redirects=True,
                max_redirects=5,
                headers={"User-Agent": ICAL_USER_AGENT, "Accept": "text/calendar, */*"},
                event_hooks={"request": [_check_request]},
            ) as client:
                response = client.get(url)
        except ChannelError:
            raise
        except httpx.HTTPError as exc:
            raise ChannelError(f"No se pudo conectar con el calendario ({type(exc).__name__})") from exc
        if response.status_code >= 400:
            raise ChannelError(
                f"El servidor del calendario respondió {response.status_code}",
                retryable=response.status_code >= 500 or response.status_code == 429,
            )
        if len(response.content) > ICAL_MAX_BYTES:
            raise ChannelError("El calendario pesa más de 5 MB", retryable=False)
        return response.text

    def test_connection(self, connection=None) -> tuple[bool, str]:
        if connection is None:
            return True, "Listo para descargar calendarios iCal por HTTPS"
        from apps.distribution.services.ical import local_export_mapping, parse_events

        mappings = [m for m in connection.room_mappings.all() if m.ical_import_url]
        if not mappings:
            return True, "Sin calendarios para importar: solo se exportan los de Housetel"
        problems, events = [], 0
        for mapping in mappings:
            try:
                local = local_export_mapping(mapping.ical_import_url)
                if local is None:
                    events += len(parse_events(self.fetch_calendar(connection, mapping)))
            except ChannelError as exc:
                problems.append(f"{mapping.room_type.code}: {exc.message}")
        if problems:
            return False, "; ".join(problems)
        return True, f"{len(mappings)} calendario(s) leídos ({events} eventos)"


class SimulatedIcalProvider(ChannelProvider):
    """Never goes to the internet: only calendars exported by Housetel itself are read (locally, by
    `services.ical`); any other URL is skipped until the property switches `channel_ical` to real."""

    kind = "channel_ical"
    mode = "simulated"
    label = "iCal simulado: solo calendarios de Housetel, sin internet"
    CONFIG_FIELDS: list[dict] = []

    def fetch_calendar(self, connection, mapping) -> str:
        raise CalendarSkipped(
            "Modo simulado: solo se leen calendarios exportados por Housetel. Cambia la integración iCal a "
            "modo real en Configuración → Integraciones para descargar este calendario"
        )

    def test_connection(self, connection=None) -> tuple[bool, str]:
        return True, "Modo simulado: se leen los calendarios de Housetel sin salir a internet"


# --- Channex ------------------------------------------------------------------------------------------------
# API v1 (docs.channex.io, verified 2026-09-27). Auth header `user-api-key`. JSON:API responses
# (`data[].{type,id,attributes}`, `meta`, `errors{code,title,details}`). Limits: 10 restriction/price and 10
# availability requests per minute per property (429 when exceeded), 10 MB per call. Values go one per night
# with `date` (the docs do not say whether `date_to` is inclusive).

CHANNEX_API_URLS = {
    "staging": "https://staging.channex.io/api/v1",
    "production": "https://app.channex.io/api/v1",
}
CHANNEX_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
CHANNEX_USER_AGENT = "Housetel-PMS/1.0 (+https://housetel.co)"
RATE_KINDS = frozenset({"rates", "restrictions"})


class ChannexClient:
    """Minimal Channex API client: JSON in and out, HTTP errors translated to `ChannelError` (retryable for
    network errors, 429 and 5xx; not retryable for a refused key or rejected values)."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def get(self, path: str, *, params: dict | None = None) -> dict:
        return self.request("GET", path, params=params)

    def post(self, path: str, *, payload: dict | None = None) -> dict:
        return self.request("POST", path, payload=payload)

    def request(self, method: str, path: str, *, params=None, payload=None) -> dict:
        headers = {
            "user-api-key": self.api_key,
            "Accept": "application/json",
            "User-Agent": CHANNEX_USER_AGENT,
        }
        try:
            with httpx.Client(timeout=CHANNEX_TIMEOUT) as client:
                response = client.request(
                    method, f"{self.base_url}{path}", params=params, json=payload, headers=headers
                )
        except httpx.HTTPError as exc:
            raise ChannelError(
                f"No se pudo conectar con Channex ({type(exc).__name__})", code="channex_unreachable"
            ) from exc
        if response.status_code >= 400:
            raise _channex_error(response)
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise ChannelError(
                "Channex respondió algo que no es JSON", code="channex_invalid_response"
            ) from exc


def _channex_error(response: httpx.Response) -> ChannelError:
    status = response.status_code
    detail = ""
    try:
        errors = response.json().get("errors") or {}
        if isinstance(errors, dict):
            detail = str(errors.get("title") or "")
            if errors.get("details"):
                detail = f"{detail}: {errors['details']}" if detail else str(errors["details"])
    except (ValueError, AttributeError):
        pass
    suffix = f" ({detail})" if detail else ""
    if status in (401, 403):
        return ChannelError(
            f"Channex rechazó la API key{suffix}", retryable=False, code="channex_unauthorized"
        )
    if status == 404:
        return ChannelError(
            f"Channex no encontró el recurso{suffix}", retryable=False, code="channex_not_found"
        )
    if status == 429:
        return ChannelError(
            "Channex limita a 10 envíos por minuto por propiedad: se reintentará", code="channex_rate_limited"
        )
    if status >= 500:
        return ChannelError(f"Channex no está disponible (HTTP {status})", code="channex_unavailable")
    return ChannelError(
        f"Channex rechazó el envío (HTTP {status}){suffix}", retryable=False, code="channex_rejected"
    )


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def _parse_time(value) -> time | None:
    try:
        return datetime.strptime(str(value)[:5], "%H:%M").time() if value else None
    except ValueError:
        return None


def _money(value) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "") else None
    except (InvalidOperation, ValueError):
        return None


def _nightly_rates(room: dict, checkin: date | None, checkout: date | None) -> list[dict] | None:
    """Channex `days` ({date: amount}) as PMS nightly rates when they cover exactly the stay; else the room
    amount spread over the nights (the last night takes the rounding); else None (the PMS prices it)."""
    if not checkin or not checkout or checkout <= checkin:
        return None
    nights = [checkin + timedelta(days=offset) for offset in range((checkout - checkin).days)]
    days = {_parse_date(key): _money(value) for key, value in (room.get("days") or {}).items()}
    if set(days) == set(nights) and all(amount is not None for amount in days.values()):
        return [{"date": night, "amount": days[night]} for night in nights]
    total = _money(room.get("amount"))
    if total is None or total <= 0:
        return None
    each = (total / len(nights)).quantize(Decimal("0.01"))
    amounts = [each] * (len(nights) - 1) + [total - each * (len(nights) - 1)]
    return [{"date": night, "amount": amount} for night, amount in zip(nights, amounts, strict=True)]


def revision_to_booking(item: dict) -> InboundBooking:
    """A Channex booking revision (`/booking_revisions/feed` item) as a channel booking. `external_id` is the
    Channex `booking_id` (stable across revisions); infants are not counted as guests (noted instead)."""
    attrs = item.get("attributes") or {}
    customer = attrs.get("customer") or {}
    rooms, infants = [], 0
    for room in attrs.get("rooms") or []:
        checkin = _parse_date(room.get("checkin_date") or attrs.get("arrival_date"))
        checkout = _parse_date(room.get("checkout_date") or attrs.get("departure_date"))
        occupancy = room.get("occupancy") or {}
        infants += int(occupancy.get("infants") or 0)
        rooms.append(
            InboundRoom(
                external_room_id=str(room.get("room_type_id") or ""),
                external_rate_id=str(room.get("rate_plan_id") or ""),
                checkin=checkin,
                checkout=checkout,
                adults=max(int(occupancy.get("adults") or 0), 1),
                children=int(occupancy.get("children") or 0),
                nightly_rates=_nightly_rates(room, checkin, checkout),
            )
        )
    ota = str(attrs.get("ota_name") or "Channex")
    code = str(attrs.get("ota_reservation_code") or attrs.get("unique_id") or "")
    notes = [f"{ota} · reserva {code}" if code else ota]
    if attrs.get("notes"):
        notes.append(str(attrs["notes"])[:1500])
    if infants:
        notes.append(f"Bebés: {infants}")
    return InboundBooking(
        external_id=str(attrs.get("booking_id") or attrs.get("unique_id") or item.get("id") or "")[:120],
        status=str(attrs.get("status") or "new"),
        guest={
            "first_name": str(customer.get("name") or ""),
            "last_name": str(customer.get("surname") or ""),
            "email": str(customer.get("mail") or ""),
            "phone": str(customer.get("phone") or ""),
            "country": str(customer.get("country") or ""),
            "language": str(customer.get("language") or ""),
        },
        rooms=rooms,
        currency=str(attrs.get("currency") or ""),
        notes="\n".join(notes),
        eta=_parse_time(attrs.get("arrival_hour")),
        raw=attrs,
        revision_id=str(attrs.get("revision_id") or item.get("id") or ""),
    )


def _flag(value) -> bool:
    return bool(value)


class RealChannexProvider(ChannelProvider):
    """Channex (sandbox or production): ARI out, booking revisions in. Credentials live in the property's
    `IntegrationSetting(kind="channel_channex")`: `environment`, `property_id` (the Channex property) and
    the secret `api_key`."""

    kind = "channel_channex"
    mode = "real"
    label = "Channex: Booking.com, Expedia y más de 50 OTAs"
    CONFIG_FIELDS = [
        {
            "name": "environment",
            "label_es": "Ambiente",
            "label_en": "Environment",
            "type": "select",
            "secret": False,
            "required": True,
            "options": [
                {"value": "staging", "label_es": "Sandbox (staging)", "label_en": "Sandbox (staging)"},
                {"value": "production", "label_es": "Producción", "label_en": "Production"},
            ],
            "help_es": "Usa el sandbox de Channex para probar sin afectar reservas reales.",
            "help_en": "Use the Channex sandbox to test without touching real bookings.",
        },
        {
            "name": "property_id",
            "label_es": "ID de la propiedad en Channex",
            "label_en": "Channex property ID",
            "type": "text",
            "secret": False,
            "required": True,
            "help_es": "UUID de la propiedad en Channex (Propiedades → detalle).",
            "help_en": "UUID of the property in Channex (Properties → details).",
        },
        {
            "name": "api_key",
            "label_es": "API key de Channex",
            "label_en": "Channex API key",
            "type": "password",
            "secret": True,
            "required": True,
            "help_es": "Se genera en Channex → Perfil → API keys.",
            "help_en": "Created in Channex → Profile → API keys.",
        },
    ]

    def client(self) -> ChannexClient:
        base_url = CHANNEX_API_URLS.get(self.config.get("environment") or "staging")
        api_key = self.secrets.get("api_key")
        if not base_url or not api_key:
            raise ChannelError(
                "Falta configurar Channex: ambiente y API key (Configuración → Integraciones)",
                retryable=False,
                code="integration_misconfigured",
            )
        return ChannexClient(base_url, api_key)

    def property_id(self) -> str:
        property_id = str(self.config.get("property_id") or "").strip()
        if not property_id:
            raise ChannelError(
                "Falta el ID de la propiedad en Channex (Configuración → Integraciones)",
                retryable=False,
                code="integration_misconfigured",
            )
        return property_id

    def push_ari(self, connection, batches) -> dict:
        client, property_id = self.client(), self.property_id()
        availability, restrictions = [], []
        for batch in batches:
            if "availability" in batch.kinds and batch.external_room_id:
                availability += [
                    {
                        "property_id": property_id,
                        "room_type_id": batch.external_room_id,
                        "date": night.isoformat(),
                        "availability": units,
                    }
                    for night, units in batch.availability.items()
                ]
            if RATE_KINDS & set(batch.kinds):
                for rate in batch.rates:
                    if rate.external_rate_id:
                        restrictions += [self._restriction(property_id, rate, day) for day in rate.days]
        response = {"availability": len(availability), "restrictions": len(restrictions), "warnings": []}
        for path, values in (("/availability", availability), ("/restrictions", restrictions)):
            if values:
                meta = client.post(path, payload={"values": values}).get("meta") or {}
                response["warnings"] += list(meta.get("warnings") or [])
        return response

    @staticmethod
    def _restriction(property_id: str, rate, day) -> dict:
        value = {
            "property_id": property_id,
            "rate_plan_id": rate.external_rate_id,
            "date": day.date.isoformat(),
        }
        if day.price is not None:  # Channex refuses a rate of 0: a closed night only goes stop-sell
            value["rate"] = f"{day.price:.2f}"
        value.update(
            min_stay_arrival=day.min_los or 1,  # positive integer: 1 = no minimum
            max_stay=day.max_los or 0,  # non-negative: 0 = no maximum
            closed_to_arrival=_flag(day.closed_to_arrival),
            closed_to_departure=_flag(day.closed_to_departure),
            stop_sell=_flag(day.stop_sell),
        )
        return value

    def fetch_bookings(self, connection) -> list[InboundBooking]:
        data = self.client().get(
            "/booking_revisions/feed",
            params={
                "filter[property_id]": self.property_id(),
                "order[inserted_at]": "asc",
                "pagination[limit]": 100,
            },
        )
        return [revision_to_booking(item) for item in data.get("data") or [] if isinstance(item, dict)]

    def acknowledge(self, connection, booking) -> None:
        if booking.revision_id:
            self.client().post(f"/booking_revisions/{booking.revision_id}/ack")

    def remote_catalog(self, connection=None) -> dict:
        client, property_id = self.client(), self.property_id()
        params = {"filter[property_id]": property_id}
        rooms = client.get("/room_types/options", params=params).get("data") or []
        rates = client.get("/rate_plans/options", params=params).get("data") or []
        return {
            "rooms": [
                {"id": item.get("id"), "title": (item.get("attributes") or {}).get("title") or item.get("id")}
                for item in rooms
            ],
            "rates": [
                {
                    "id": item.get("id"),
                    "title": (item.get("attributes") or {}).get("title") or item.get("id"),
                    "room_id": (item.get("attributes") or {}).get("room_type_id"),
                    "currency": (item.get("attributes") or {}).get("currency") or "",
                }
                for item in rates
            ],
        }

    def test_connection(self, connection=None) -> tuple[bool, str]:
        environment = self.config.get("environment") or "staging"
        try:
            client = self.client()
            data = client.get("/properties", params={"pagination[limit]": 100})
        except ChannelError as exc:
            return False, exc.message
        properties = [item for item in data.get("data") or [] if isinstance(item, dict)]
        property_id = str(self.config.get("property_id") or "").strip()
        if not property_id:
            return True, (
                f"API key válida ({environment}): {len(properties)} propiedad(es) visibles. Falta el ID de "
                "la propiedad de Channex"
            )
        match = next((item for item in properties if item.get("id") == property_id), None)
        total = int((data.get("meta") or {}).get("total") or len(properties))
        if match is None and total > len(properties):
            try:
                match = client.get(f"/properties/{property_id}").get("data")
            except ChannelError:
                match = None
        if not match:
            return False, f"La propiedad {property_id} no está entre las visibles con esta API key"
        title = (match.get("attributes") or {}).get("title") or property_id
        return True, f"Conectado a «{title}» en Channex ({environment})"


class SimulatedChannexProvider(ChannelProvider):
    """Channex without internet: the ARI lands in `SimOtaInventory` and the bookings made in the OTA
    simulator wait (`SimOtaBooking.pms_status = pending`) until the PMS pulls them, like the revisions
    feed."""

    kind = "channel_channex"
    mode = "simulated"
    label = "Channex simulado: sin internet, con el simulador de OTAs"
    CONFIG_FIELDS: list[dict] = []

    def push_ari(self, connection, batches) -> dict:
        return {"cells": write_sim_inventory(connection, batches), "warnings": []}

    def fetch_bookings(self, connection) -> list[InboundBooking]:
        from apps.distribution.services.simulator import pending_bookings

        return pending_bookings(connection)

    def acknowledge(self, connection, booking) -> None:
        from apps.distribution.services.simulator import acknowledge_booking

        acknowledge_booking(connection, booking)

    def reject(self, connection, booking, message: str) -> None:
        from apps.distribution.services.simulator import reject_booking

        reject_booking(connection, booking, message)

    def remote_catalog(self, connection=None) -> dict:
        return suggested_catalog(self.setting.property, "channex")

    def test_connection(self, connection=None) -> tuple[bool, str]:
        return (
            True,
            "Channex simulado: el ARI llega al simulador de OTAs y sus reservas se descargan sin internet",
        )


def provider_for(connection):
    """The provider serving this connection (for iCal/Channex, the one of the configured mode)."""
    if connection.channel_code in SIM_CHANNELS:
        return SimulatedOtaProvider()
    return integrations.get_provider(connection.property, CHANNEL_KINDS[connection.channel_code])


def connection_mode(connection) -> str:
    """`simulated` or `real`, read without creating the integration setting."""
    if connection.channel_code in SIM_CHANNELS:
        return "simulated"
    from apps.core.models import IntegrationSetting

    kind = CHANNEL_KINDS[connection.channel_code]
    setting = IntegrationSetting.objects.filter(property=connection.property, kind=kind).first()
    return setting.mode if setting is not None else integrations.default_mode(kind)


register_provider("channel_ical", "real", RealIcalProvider)
register_provider("channel_ical", "simulated", SimulatedIcalProvider)
register_provider("channel_channex", "real", RealChannexProvider)
register_provider("channel_channex", "simulated", SimulatedChannexProvider)
