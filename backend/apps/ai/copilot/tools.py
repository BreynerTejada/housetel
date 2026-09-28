"""Copilot tools (plan C9).

Read tools answer with the hotel's real data, scoped to the active property. Action tools never write: they
validate, resolve what the user meant (codes → ids) and return a `Proposal`, stored as a `CopilotAction` that
the user confirms or rejects (`apps.ai.copilot.actions.execute_action`). A tool is offered to the model only
when the user has its permission, and the permission is checked again when a tool runs.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db.models import Prefetch, Q, Sum

from apps.ai import nlp
from apps.core.errors import DomainError
from apps.core.i18n import t

logger = logging.getLogger("housetel.ai")

MAX_ITEMS = 20
MAX_NIGHTS = 31
ACTIVE_STAY = ["tentative", "confirmed", "checked_in"]
SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


class ToolError(DomainError):
    code = "tool_error"


@dataclass
class ToolContext:
    property: Any
    user: Any
    session: Any = None
    lang: str = "es"
    message: Any = None  # the assistant message whose tool calls are running (proposals point to it)
    _granted: list | None = field(default=None, repr=False)

    def can(self, code: str) -> bool:
        from apps.core.permissions import codes_match

        if self._granted is None:
            self._granted = granted_permissions(self.user, self.property)
        return codes_match(self._granted, code)

    def text(self, es: str, en: str) -> str:
        return en if self.lang == "en" else es


def granted_permissions(user, prop) -> list[str]:
    """The permission codes/patterns of the user's active membership in the property ([] without access)."""
    from apps.accounts.models import Membership

    membership = (
        Membership.objects.select_related("role")
        .filter(user=user, organization=prop.organization, is_active=True)
        .first()
    )
    if membership is None or not (
        membership.all_properties or membership.properties.filter(pk=prop.pk).exists()
    ):
        return []
    return list(membership.role.permissions or [])


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    permission: str
    handler: Callable
    kind: str = "read"  # read | action

    def schema(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


@dataclass
class Proposal:
    action_code: str
    permission: str
    params: dict
    summary: str
    details: dict


REGISTRY: dict[str, Tool] = {}


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


def tool(name: str, description: str, properties: dict, permission: str, *, required=None, kind="read"):
    def register(handler):
        REGISTRY[name] = Tool(name, description, _schema(properties, required), permission, handler, kind)
        return handler

    return register


def available_tools(user, prop) -> list[Tool]:
    from apps.core.permissions import codes_match

    granted = granted_permissions(user, prop)
    return [item for item in REGISTRY.values() if codes_match(granted, item.permission)]


def _clean_arguments(item: Tool, arguments) -> dict:
    if not isinstance(arguments, dict):
        return {}
    properties = item.parameters.get("properties", {})
    clean = {}
    for key, value in arguments.items():
        if key not in properties or value in (None, ""):
            continue
        if properties[key].get("type") == "integer":
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ToolError(f"«{key}» debe ser un número entero") from None
        clean[key] = value
    return clean


def run_tool(ctx: ToolContext, name: str, arguments) -> dict:
    """Run a tool for the copilot; errors come back as `{"error": message}` for the model to explain."""
    item = REGISTRY.get(name)
    if item is None:
        return {"error": f"Herramienta desconocida: {name}"}
    if not ctx.can(item.permission):
        return {
            "error": ctx.text(
                "No tienes permiso para esta acción", "You don't have permission for this action"
            ),
            "permission": item.permission,
        }
    try:
        result = item.handler(ctx, **_clean_arguments(item, arguments))
    except DomainError as exc:
        return {"error": exc.message}
    except TypeError as exc:
        return {"error": f"Argumentos inválidos: {exc}"}
    except Exception:
        logger.exception("Copilot tool %s failed", name)
        return {"error": ctx.text("No se pudo completar la consulta", "The request could not be completed")}
    if isinstance(result, Proposal):
        return _propose(ctx, result)
    return result


def _propose(ctx: ToolContext, proposal: Proposal) -> dict:
    from apps.ai.models import CopilotAction

    if ctx.session is None:
        return {"error": "Las acciones solo se proponen dentro de una conversación del copiloto"}
    action = CopilotAction.objects.create(
        session=ctx.session,
        message=ctx.message,
        action_code=proposal.action_code,
        params=proposal.params,
        summary=proposal.summary[:500],
        details=proposal.details,
        permission=proposal.permission,
    )
    return {
        "proposal": {
            "id": str(action.pk),
            "action": action.action_code,
            "summary": action.summary,
            "details": action.details,
            "status": action.status,
        }
    }


# ---- helpers ----------------------------------------------------------------------------------------------


def money(value) -> str:
    return f"{Decimal(value or 0):.2f}"


def percent(part, whole) -> float:
    if not whole:
        return 0.0
    return float((Decimal(part) * 100 / Decimal(whole)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def parse_day(value, field_name: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ToolError(f"Fecha inválida en «{field_name}»: usa AAAA-MM-DD") from None


def stay_range(ctx, checkin, checkout, *, allow_past=False) -> tuple[date, date]:
    start = parse_day(checkin, "checkin")
    end = parse_day(checkout, "checkout")
    if start is None or end is None:
        raise ToolError(
            ctx.text("Indica la fecha de llegada y la de salida", "Give the arrival and departure dates")
        )
    if end <= start:
        raise ToolError(
            ctx.text("La salida debe ser posterior a la llegada", "Departure must be after arrival")
        )
    if (end - start).days > MAX_NIGHTS:
        raise ToolError(ctx.text(f"Máximo {MAX_NIGHTS} noches", f"At most {MAX_NIGHTS} nights"))
    if not allow_past and start < ctx.property.business_date:
        raise ToolError(
            ctx.text(
                f"La llegada no puede ser anterior a la fecha de negocio ({ctx.property.business_date})",
                f"Arrival cannot be before the business date ({ctx.property.business_date})",
            )
        )
    return start, end


def reservation_by_code(ctx, code):
    from apps.bookings.models import Reservation

    found = (
        Reservation.objects.select_related("booker")
        .filter(property=ctx.property, code__iexact=str(code or "").strip())
        .first()
    )
    if found is None:
        raise ToolError(ctx.text(f"No encontré la reserva {code}", f"Reservation {code} was not found"))
    return found


def room_by_number(ctx, number):
    from apps.inventory.models import Room

    room = (
        Room.objects.select_related("room_type")
        .filter(property=ctx.property, number__iexact=str(number or "").strip(), is_active=True)
        .first()
    )
    if room is None:
        raise ToolError(ctx.text(f"No existe la habitación {number}", f"Room {number} does not exist"))
    return room


def _stays_prefetch():
    from apps.bookings.models import Stay

    return Prefetch(
        "stays", queryset=Stay.objects.select_related("room", "room_type").order_by("checkin_date", "id")
    )


def _reservation_item(ctx, reservation, *, day=None, on="checkin") -> dict:
    stays = [stay for stay in reservation.stays.all() if stay.status not in ("cancelled", "no_show")]
    if day is not None:
        stays = [stay for stay in stays if getattr(stay, f"{on}_date") == day] or stays
    rooms = [stay.room.number for stay in stays if stay.room_id]
    first_room = next((stay.room for stay in stays if stay.room_id), None)
    return {
        "code": reservation.code,
        "guest": reservation.booker.full_name,
        "vip": reservation.booker.is_vip,
        "status": reservation.status,
        "checkin": reservation.checkin_date.isoformat(),
        "checkout": reservation.checkout_date.isoformat(),
        "rooms": rooms,
        "room_status": first_room.housekeeping_status if first_room else None,
        "eta": reservation.eta.strftime("%H:%M") if reservation.eta else None,
        "balance": money(getattr(reservation, "balance", 0)),
    }


def _reservations_on(ctx, **stay_filters):
    from apps.bookings.models import Reservation
    from apps.bookings.services.queries import with_balance

    queryset = (
        Reservation.objects.filter(
            property=ctx.property, **{f"stays__{k}": v for k, v in stay_filters.items()}
        )
        .distinct()
        .select_related("booker")
        .prefetch_related(_stays_prefetch())
        .order_by("code")
    )
    return with_balance(queryset)


# ---- read tools -----------------------------------------------------------------------------------------

DATE = {"type": "string", "description": "Fecha AAAA-MM-DD"}
CODE = {"type": "string", "description": "Código de la reserva, p. ej. HT-7K2M9Q"}


@tool(
    "get_today_summary",
    "Resumen del día de negocio: llegadas, salidas, huéspedes en casa, ocupación y cobros de hoy.",
    {},
    "bookings.view",
)
def get_today_summary(ctx):
    from apps.bookings.models import InventoryDay, Stay
    from apps.bookings.services.availability import availability
    from apps.finance.models import Payment

    day = ctx.property.business_date
    stays = Stay.objects.filter(reservation__property=ctx.property)
    arrivals = stays.filter(checkin_date=day).exclude(status__in=["cancelled", "no_show"])
    departures = stays.filter(checkout_date=day, status__in=["checked_in", "checked_out"])
    availability(property=ctx.property, checkin=day, checkout=day + timedelta(days=1))  # materializes the day
    inventory = InventoryDay.objects.filter(
        property=ctx.property, date=day, room_type__is_active=True
    ).aggregate(sold=Sum("sold_units"), total=Sum("total_units"), blocked=Sum("blocked_units"))
    sellable = (inventory["total"] or 0) - (inventory["blocked"] or 0)
    collected = Payment.objects.filter(
        folio__property=ctx.property, status="approved", business_date=day
    ).aggregate(total=Sum("amount"))["total"]
    return {
        "date": day.isoformat(),
        "arrivals": {
            "total": arrivals.count(),
            "done": arrivals.filter(status__in=["checked_in", "checked_out"]).count(),
        },
        "departures": {"total": departures.count(), "done": departures.filter(status="checked_out").count()},
        "in_house": stays.filter(status="checked_in").count(),
        "units_sold": inventory["sold"] or 0,
        "units_total": sellable,
        "occupancy_pct": percent(inventory["sold"] or 0, sellable),
        "collected_today": money(collected),
        "currency": ctx.property.currency,
    }


@tool(
    "list_arrivals",
    "Reservas que llegan en una fecha (por defecto hoy): huésped, habitación, estado y saldo.",
    {"date": DATE},
    "bookings.view",
)
def list_arrivals(ctx, date=None):
    day = parse_day(date, "date") or ctx.property.business_date
    reservations = _reservations_on(ctx, checkin_date=day, status__in=ACTIVE_STAY)
    items = [_reservation_item(ctx, reservation, day=day) for reservation in reservations[:MAX_ITEMS]]
    return {"date": day.isoformat(), "count": reservations.count(), "items": items}


@tool(
    "list_departures",
    "Reservas que salen en una fecha (por defecto hoy): huésped, habitación, estado y saldo pendiente.",
    {"date": DATE},
    "bookings.view",
)
def list_departures(ctx, date=None):
    day = parse_day(date, "date") or ctx.property.business_date
    reservations = _reservations_on(ctx, checkout_date=day, status__in=["checked_in", "checked_out"])
    items = [
        _reservation_item(ctx, reservation, day=day, on="checkout")
        for reservation in reservations[:MAX_ITEMS]
    ]
    return {"date": day.isoformat(), "count": reservations.count(), "items": items}


@tool(
    "search_reservations",
    "Busca reservas por código, nombre, email o teléfono del huésped, estado o rango de llegada.",
    {
        "query": {"type": "string", "description": "Texto a buscar"},
        "status": {
            "type": "string",
            "enum": ["tentative", "confirmed", "checked_in", "checked_out", "cancelled", "no_show"],
        },
        "arrival_from": DATE,
        "arrival_to": DATE,
    },
    "bookings.view",
)
def search_reservations(ctx, query=None, status=None, arrival_from=None, arrival_to=None):
    from apps.bookings.models import Reservation
    from apps.bookings.services.queries import with_balance

    queryset = Reservation.objects.filter(property=ctx.property)
    for word in (query or "").split():
        queryset = queryset.filter(
            Q(code__icontains=word)
            | Q(booker__first_name__unaccent__icontains=word)
            | Q(booker__last_name__unaccent__icontains=word)
            | Q(booker__email__icontains=word)
            | Q(booker__phone__icontains=word)
            | Q(external_id__icontains=word)
        )
    if status:
        queryset = queryset.filter(status=status)
    if start := parse_day(arrival_from, "arrival_from"):
        queryset = queryset.filter(checkin_date__gte=start)
    if end := parse_day(arrival_to, "arrival_to"):
        queryset = queryset.filter(checkin_date__lte=end)
    queryset = with_balance(
        queryset.select_related("booker").prefetch_related(_stays_prefetch()).order_by("checkin_date", "code")
    )
    return {"count": queryset.count(), "items": [_reservation_item(ctx, item) for item in queryset[:10]]}


@tool(
    "get_reservation",
    "Detalle de una reserva por su código.",
    {"code": CODE},
    "bookings.view",
    required=["code"],
)
def get_reservation(ctx, code):
    from apps.bookings.services.queries import with_balance

    found = reservation_by_code(ctx, code)
    reservation = (
        with_balance(type(found).objects.filter(pk=found.pk)).prefetch_related(_stays_prefetch()).get()
    )
    item = _reservation_item(ctx, reservation)
    stays = [stay for stay in reservation.stays.all()]
    item.update(
        {
            "nights": (reservation.checkout_date - reservation.checkin_date).days,
            "adults": reservation.adults,
            "children": reservation.children,
            "source": reservation.source,
            "channel": reservation.channel_code,
            "total": money(reservation.total_amount),
            "currency": reservation.currency,
            "notes": reservation.notes,
            "special_requests": reservation.special_requests,
            "email": reservation.booker.email,
            "phone": reservation.booker.phone,
            "room_types": sorted({t(stay.room_type.name, ctx.lang) for stay in stays}),
        }
    )
    return item


@tool(
    "check_availability",
    "Disponibilidad y precio (la oferta más barata por categoría) para unas fechas y huéspedes.",
    {
        "checkin": DATE,
        "checkout": DATE,
        "adults": {"type": "integer", "description": "Adultos (por defecto 2)"},
        "children": {"type": "integer", "description": "Niños"},
    },
    "bookings.view",
    required=["checkin", "checkout"],
)
def check_availability(ctx, checkin=None, checkout=None, adults=2, children=0):
    start, end = stay_range(ctx, checkin, checkout)
    options = offer_options(ctx.property, start, end, adults=adults, children=children, lang=ctx.lang)
    return {
        "checkin": start.isoformat(),
        "checkout": end.isoformat(),
        "nights": (end - start).days,
        "adults": adults,
        "children": children,
        "currency": ctx.property.currency,
        "options": options,
    }


def offer_options(
    prop, start, end, *, adults=2, children=0, lang="es", channel="direct", prefer_plan_id=None
) -> list[dict]:
    """One sellable offer per category (shared by the copilot and the chatbot): the offer of
    `prefer_plan_id` when that plan sells the category, otherwise the cheapest one."""
    from apps.bookings.services.availability import search_offers
    from apps.inventory.models import RoomType
    from apps.rates.models import RatePlan

    offers = search_offers(
        property=prop,
        checkin=start,
        checkout=end,
        adults=max(1, int(adults or 1)),
        children=max(0, int(children or 0)),
        channel=channel,
    )
    cheapest = {}
    for offer in offers:  # cheapest first
        current = cheapest.get(offer.room_type_id)
        preferred = prefer_plan_id is not None and offer.rate_plan_id == prefer_plan_id
        if current is None or (preferred and current.rate_plan_id != prefer_plan_id):
            cheapest[offer.room_type_id] = offer
    room_types = RoomType.objects.in_bulk([offer.room_type_id for offer in cheapest.values()])
    plans = RatePlan.objects.in_bulk([offer.rate_plan_id for offer in cheapest.values()])
    nights = max(1, (end - start).days)
    options = []
    for offer in cheapest.values():
        room_type, plan = room_types[offer.room_type_id], plans[offer.rate_plan_id]
        options.append(
            {
                "room_type_id": str(room_type.pk),
                "room_type_code": room_type.code,
                "room_type": t(room_type.name, lang),
                "kind": room_type.kind,
                "max_occupancy": room_type.max_occupancy,
                "available": offer.available_units,
                "units_needed": offer.units_needed,
                "rate_plan_id": str(plan.pk),
                "rate_plan_code": plan.code,
                "rate_plan": t(plan.name, lang),
                "total": money(offer.total),
                "per_night": money(
                    (Decimal(offer.total) / nights).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                ),
            }
        )
    return options


@tool(
    "get_occupancy",
    "Ocupación por noche en un rango (por defecto los próximos 7 días desde hoy).",
    {"start": DATE, "end": {"type": "string", "description": "Fecha AAAA-MM-DD (exclusiva)"}},
    "bookings.view",
)
def get_occupancy(ctx, start=None, end=None):
    from apps.bookings.models import InventoryDay
    from apps.bookings.services.availability import availability_by_date

    first = parse_day(start, "start") or ctx.property.business_date
    last = parse_day(end, "end") or first + timedelta(days=7)
    if last <= first:
        raise ToolError(ctx.text("El fin debe ser posterior al inicio", "The end must be after the start"))
    last = min(last, first + timedelta(days=MAX_NIGHTS))
    availability_by_date(property=ctx.property, start=first, end=last)  # materializes the nights
    rows = (
        InventoryDay.objects.filter(
            property=ctx.property, date__gte=first, date__lt=last, room_type__is_active=True
        )
        .values("date")
        .annotate(sold=Sum("sold_units"), total=Sum("total_units"), blocked=Sum("blocked_units"))
        .order_by("date")
    )
    nights = []
    for row in rows:
        sellable = (row["total"] or 0) - (row["blocked"] or 0)
        nights.append(
            {
                "date": row["date"].isoformat(),
                "sold": row["sold"] or 0,
                "total": sellable,
                "pct": percent(row["sold"] or 0, sellable),
            }
        )
    sold, total = sum(n["sold"] for n in nights), sum(n["total"] for n in nights)
    return {
        "start": first.isoformat(),
        "end": last.isoformat(),
        "average_pct": percent(sold, total),
        "nights": nights,
    }


@tool(
    "find_guest",
    "Busca huéspedes de la organización por nombre, email, teléfono o documento.",
    {"query": {"type": "string", "description": "Nombre, email, teléfono o documento"}},
    "guests.view",
    required=["query"],
)
def find_guest(ctx, query=""):
    from apps.guests.api.filters import search_q
    from apps.guests.models import Guest

    if not str(query).strip():
        raise ToolError(ctx.text("Dime a quién busco", "Tell me who to look for"))
    guests = (
        Guest.objects.filter(organization=ctx.property.organization, merged_into__isnull=True)
        .filter(search_q(str(query)))
        .order_by("last_name", "first_name")[:5]
    )
    return {
        "count": len(guests),
        "items": [
            {
                "id": str(guest.pk),
                "name": guest.full_name,
                "email": guest.email,
                "phone": guest.phone,
                "document": f"{guest.document_type} {guest.document_number}".strip(),
                "nationality": guest.nationality,
                "vip": guest.is_vip,
            }
            for guest in guests
        ],
    }


@tool(
    "get_balance",
    "Saldo pendiente de una reserva (total, pagado y por cobrar).",
    {"code": CODE},
    "finance.view",
    required=["code"],
)
def get_balance(ctx, code):
    from apps.finance.models import Payment, Refund
    from apps.finance.services import reservation_balance

    reservation = reservation_by_code(ctx, code)
    balance = reservation_balance(reservation)
    paid = (
        Payment.objects.filter(folio__reservation=reservation, status="approved").aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )
    refunded = (
        Refund.objects.filter(payment__folio__reservation=reservation, status="approved").aggregate(
            total=Sum("amount")
        )["total"]
        or 0
    )
    net_paid = Decimal(paid) - Decimal(refunded)
    return {
        "code": reservation.code,
        "guest": reservation.booker.full_name,
        "status": reservation.status,
        "total": money(balance + net_paid),
        "paid": money(net_paid),
        "balance": money(balance),
        "currency": reservation.currency,
    }


@tool(
    "list_alerts",
    "Alertas abiertas del hotel (las críticas primero).",
    {"severity": {"type": "string", "enum": ["info", "warning", "critical"]}},
    "control.alerts",
)
def list_alerts(ctx, severity=None):
    from apps.core.models import Alert

    alerts = Alert.objects.filter(property=ctx.property, resolved_at__isnull=True)
    if severity:
        alerts = alerts.filter(severity=severity)
    ordered = sorted(
        alerts.order_by("-created_at")[:50], key=lambda alert: SEVERITY_ORDER.get(alert.severity, 3)
    )
    return {
        "count": alerts.count(),
        "items": [
            {
                "title": alert.title,
                "severity": alert.severity,
                "message": alert.message[:300],
                "kind": alert.kind,
                "link": alert.link,
                "created_at": alert.created_at.isoformat(),
            }
            for alert in ordered[:10]
        ],
    }


@tool(
    "get_rates",
    "Precio por noche del plan base para un rango de fechas (máximo 14 noches) y una o todas las categorías.",
    {
        "start": DATE,
        "end": {"type": "string", "description": "Fecha AAAA-MM-DD (exclusiva)"},
        "room_type": {"type": "string", "description": "Código de la categoría (opcional)"},
    },
    "rates.view",
)
def get_rates(ctx, start=None, end=None, room_type=None):
    from apps.inventory.models import RoomType
    from apps.rates.services.grid import default_plan
    from apps.rates.services.quote import resolve_daily

    first = parse_day(start, "start") or ctx.property.business_date
    last = parse_day(end, "end") or first + timedelta(days=7)
    if last <= first:
        raise ToolError(ctx.text("El fin debe ser posterior al inicio", "The end must be after the start"))
    last = min(last, first + timedelta(days=14))
    plan = default_plan(ctx.property)
    if plan is None:
        raise ToolError(
            ctx.text("El hotel aún no tiene un plan de tarifas", "The hotel has no rate plan yet")
        )
    room_types = RoomType.objects.filter(property=ctx.property, is_active=True).order_by("sort_order", "code")
    if room_type:
        room_types = room_types.filter(code__iexact=room_type)
        if not room_types:
            raise ToolError(
                ctx.text(f"No existe la categoría {room_type}", f"Room type {room_type} does not exist")
            )
    return {
        "plan": t(plan.name, ctx.lang),
        "currency": ctx.property.currency,
        "start": first.isoformat(),
        "end": last.isoformat(),
        "room_types": [
            {
                "code": item.code,
                "name": t(item.name, ctx.lang),
                "nights": [
                    {
                        "date": day.date.isoformat(),
                        "price": money(day.price),
                        "stop_sell": day.stop_sell,
                        "min_los": day.min_los,
                    }
                    for day in resolve_daily(item, plan, first, last)
                ],
            }
            for item in room_types
        ],
    }


# ---- action tools (proposals) --------------------------------------------------------------------------


def _range_label(ctx, start: date, end: date) -> str:
    nights = (end - start).days
    unit = ctx.text("noche" if nights == 1 else "noches", "night" if nights == 1 else "nights")
    return f"{nlp.format_date(start, ctx.lang)} → {nlp.format_date(end, ctx.lang)} ({nights} {unit})"


def _split_name(full_name: str) -> tuple[str, str]:
    parts = str(full_name or "").split()
    if not parts:
        return "", ""
    return parts[0], " ".join(parts[1:])


@tool(
    "create_reservation",
    "Propone crear una reserva (no la crea: el usuario la confirma). Usa guest_id de find_guest o el nombre "
    "del huésped nuevo. Sin categoría elige la oferta más barata.",
    {
        "checkin": DATE,
        "checkout": DATE,
        "adults": {"type": "integer"},
        "children": {"type": "integer"},
        "room_type": {"type": "string", "description": "Código de la categoría (opcional)"},
        "rate_plan": {"type": "string", "description": "Código del plan (opcional)"},
        "guest_id": {"type": "string", "description": "Id de un huésped existente (find_guest)"},
        "guest_name": {"type": "string", "description": "Nombre y apellido de un huésped nuevo"},
        "guest_email": {"type": "string"},
        "guest_phone": {"type": "string"},
        "notes": {"type": "string"},
    },
    "bookings.manage",
    required=["checkin", "checkout"],
    kind="action",
)
def propose_create_reservation(
    ctx,
    checkin=None,
    checkout=None,
    adults=2,
    children=0,
    room_type=None,
    rate_plan=None,
    guest_id=None,
    guest_name=None,
    guest_email=None,
    guest_phone=None,
    notes="",
):
    from apps.guests.models import Guest

    start, end = stay_range(ctx, checkin, checkout)
    if guest_id:
        guest = (
            Guest.objects.filter(
                organization=ctx.property.organization, pk=guest_id, merged_into__isnull=True
            ).first()
            if _is_uuid(guest_id)
            else None
        )
        if guest is None:
            raise ToolError(ctx.text("No encontré ese huésped", "That guest was not found"))
        guest_params, guest_label = {"guest_id": str(guest.pk)}, guest.full_name
    else:
        first, last = _split_name(guest_name)
        if not first:
            raise ToolError(ctx.text("¿A nombre de quién hago la reserva?", "Who is the reservation for?"))
        guest_params = {
            "guest": {
                "first_name": first,
                "last_name": last,
                "email": guest_email or "",
                "phone": guest_phone or "",
            }
        }
        guest_label = f"{first} {last}".strip()
    from apps.rates.models import RatePlan
    from apps.rates.services.grid import default_plan

    if rate_plan:
        plan = RatePlan.objects.filter(
            property=ctx.property, code__iexact=str(rate_plan).strip(), is_active=True
        ).first()
        if plan is None:
            raise ToolError(
                ctx.text(f"No existe el plan de tarifa {rate_plan}", f"Rate plan {rate_plan} does not exist")
            )
    else:  # the hotel's standard (flexible) rate unless the user asks for another plan
        plan = default_plan(ctx.property)
    options = offer_options(
        ctx.property,
        start,
        end,
        adults=adults,
        children=children,
        lang=ctx.lang,
        prefer_plan_id=plan.pk if plan else None,
    )
    if room_type:
        options = [option for option in options if option["room_type_code"].lower() == str(room_type).lower()]
    if rate_plan:
        options = [option for option in options if option["rate_plan_id"] == str(plan.pk)]
    if not options:
        raise ToolError(
            ctx.text(
                f"No hay disponibilidad para {_range_label(ctx, start, end)}"
                + (f" en {room_type}" if room_type else ""),
                f"No availability for {_range_label(ctx, start, end)}"
                + (f" in {room_type}" if room_type else ""),
            )
        )
    preferred = str(plan.pk) if plan else ""
    option = min(options, key=lambda item: (item["rate_plan_id"] != preferred, Decimal(item["total"])))
    nights = (end - start).days
    summary = ctx.text(
        f"Crear reserva para {guest_label} · {option['room_type']} · {_range_label(ctx, start, end)} · "
        f"{nlp.format_money(option['total'], ctx.property.currency)}",
        f"Create a reservation for {guest_label} · {option['room_type']} · {_range_label(ctx, start, end)} · "
        f"{nlp.format_money(option['total'], ctx.property.currency)}",
    )
    return Proposal(
        action_code="create_reservation",
        permission="bookings.manage",
        params={
            "room_type_id": option["room_type_id"],
            "rate_plan_id": option["rate_plan_id"],
            "checkin": start.isoformat(),
            "checkout": end.isoformat(),
            "adults": int(adults or 1),
            "children": int(children or 0),
            "notes": str(notes or "")[:1000],
            **guest_params,
        },
        summary=summary,
        details={
            "guest": guest_label,
            "room_type": option["room_type"],
            "room_type_code": option["room_type_code"],
            "rate_plan": option["rate_plan"],
            "checkin": start.isoformat(),
            "checkout": end.isoformat(),
            "nights": nights,
            "adults": int(adults or 1),
            "children": int(children or 0),
            "total": option["total"],
            "currency": ctx.property.currency,
        },
    )


def _is_uuid(value) -> bool:
    from uuid import UUID

    try:
        UUID(str(value))
    except ValueError:
        return False
    return True


def _active_stays(reservation, statuses):
    return [
        stay
        for stay in reservation.stays.select_related("room", "room_type").order_by("checkin_date", "id")
        if stay.status in statuses
    ]


@tool(
    "move_room",
    "Propone mover una reserva a otra habitación (no la mueve: el usuario lo confirma).",
    {
        "reservation_code": CODE,
        "room_number": {"type": "string", "description": "Número de la habitación destino"},
    },
    "bookings.manage",
    required=["reservation_code", "room_number"],
    kind="action",
)
def propose_move_room(ctx, reservation_code=None, room_number=None):
    from apps.bookings.models import Stay

    reservation = reservation_by_code(ctx, reservation_code)
    stays = _active_stays(reservation, ACTIVE_STAY)
    if not stays:
        raise ToolError(
            ctx.text(
                f"{reservation.code} no tiene estadías activas", f"{reservation.code} has no active stay"
            )
        )
    stay = stays[0]
    room = room_by_number(ctx, room_number)
    if stay.room_id == room.pk:
        raise ToolError(
            ctx.text(
                f"{reservation.code} ya está en la {room.number}",
                f"{reservation.code} is already in {room.number}",
            )
        )
    if room.room_type.kind != stay.room_type.kind:
        raise ToolError(
            ctx.text(
                "No se puede mezclar dormitorio y habitación privada", "Dorm and private rooms can't be mixed"
            )
        )
    busy = Stay.objects.filter(
        room=room,
        status__in=ACTIVE_STAY,
        bed__isnull=True,
        checkin_date__lt=stay.checkout_date,
        checkout_date__gt=stay.checkin_date,
    ).exclude(pk=stay.pk)
    if room.room_type.kind == "private" and busy.exists():
        raise ToolError(
            ctx.text(
                f"La {room.number} está ocupada en esas fechas", f"Room {room.number} is taken on those dates"
            )
        )
    category_change = room.room_type_id != stay.room_type_id
    origin = stay.room.number if stay.room_id else None
    summary = ctx.text(
        f"Mover {reservation.code} ({reservation.booker.full_name}) "
        + (f"de la {origin} " if origin else "")
        + f"a la {room.number}"
        + (f" · cambio de categoría a {t(room.room_type.name, 'es')}" if category_change else ""),
        f"Move {reservation.code} ({reservation.booker.full_name}) "
        + (f"from {origin} " if origin else "")
        + f"to {room.number}"
        + (f" · category change to {t(room.room_type.name, 'en')}" if category_change else ""),
    )
    return Proposal(
        action_code="move_room",
        permission="bookings.manage",
        params={"stay_id": str(stay.pk), "room_id": str(room.pk), "force": category_change},
        summary=summary,
        details={
            "code": reservation.code,
            "guest": reservation.booker.full_name,
            "from_room": origin,
            "to_room": room.number,
            "category_change": category_change,
            "to_room_type": t(room.room_type.name, ctx.lang),
            "checkin": stay.checkin_date.isoformat(),
            "checkout": stay.checkout_date.isoformat(),
            "reservation_id": str(reservation.pk),
        },
    )


@tool(
    "check_in",
    "Propone hacer el check-in de una reserva que llega hoy (no lo hace: el usuario lo confirma).",
    {"reservation_code": CODE},
    "bookings.checkin",
    required=["reservation_code"],
    kind="action",
)
def propose_check_in(ctx, reservation_code=None):
    from apps.finance.services import reservation_balance

    reservation = reservation_by_code(ctx, reservation_code)
    today = ctx.property.business_date
    stays = [
        stay for stay in _active_stays(reservation, ["tentative", "confirmed"]) if stay.checkin_date <= today
    ]
    if not stays:
        if reservation.checkin_date > today:
            raise ToolError(
                ctx.text(
                    f"{reservation.code} llega el {nlp.format_date(reservation.checkin_date)}",
                    f"{reservation.code} arrives on {nlp.format_date(reservation.checkin_date, 'en')}",
                )
            )
        raise ToolError(
            ctx.text(
                f"{reservation.code} no tiene check-in pendiente",
                f"{reservation.code} has no pending check-in",
            )
        )
    warnings = []
    for stay in stays:
        if stay.status == "tentative":
            warnings.append(
                ctx.text(
                    "La reserva es tentativa: confírmala primero",
                    "The reservation is tentative: confirm it first",
                )
            )
        if not stay.room_id:
            warnings.append(
                ctx.text(
                    "Se asignará una habitación libre automáticamente",
                    "A free room will be assigned automatically",
                )
            )
        elif stay.room.housekeeping_status not in ("clean", "inspected"):
            warnings.append(
                ctx.text(
                    f"La habitación {stay.room.number} no está lista (estado: "
                    f"{stay.room.housekeeping_status})",
                    f"Room {stay.room.number} is not ready (status: {stay.room.housekeeping_status})",
                )
            )
    balance = reservation_balance(reservation)
    rooms = [stay.room.number for stay in stays if stay.room_id]
    return Proposal(
        action_code="check_in",
        permission="bookings.checkin",
        params={"stay_ids": [str(stay.pk) for stay in stays]},
        summary=ctx.text(
            f"Check-in de {reservation.code} ({reservation.booker.full_name})"
            + (f" · hab. {', '.join(rooms)}" if rooms else ""),
            f"Check in {reservation.code} ({reservation.booker.full_name})"
            + (f" · room {', '.join(rooms)}" if rooms else ""),
        ),
        details={
            "code": reservation.code,
            "guest": reservation.booker.full_name,
            "rooms": rooms,
            "warnings": warnings,
            "balance": money(balance),
            "currency": reservation.currency,
            "reservation_id": str(reservation.pk),
        },
    )


@tool(
    "check_out",
    "Propone hacer el check-out de una reserva en casa (no lo hace: el usuario lo confirma).",
    {"reservation_code": CODE},
    "bookings.checkin",
    required=["reservation_code"],
    kind="action",
)
def propose_check_out(ctx, reservation_code=None):
    from apps.finance.services import reservation_balance

    reservation = reservation_by_code(ctx, reservation_code)
    stays = _active_stays(reservation, ["checked_in"])
    if not stays:
        raise ToolError(
            ctx.text(f"{reservation.code} no está en casa", f"{reservation.code} is not in house")
        )
    balance = reservation_balance(reservation)
    warnings = []
    if balance > 0:
        warnings.append(
            ctx.text(
                f"Saldo pendiente de {nlp.format_money(balance, reservation.currency)}: cóbralo antes del "
                "check-out",
                f"Balance due of {nlp.format_money(balance, reservation.currency)}: collect it before "
                "checking out",
            )
        )
    rooms = [stay.room.number for stay in stays if stay.room_id]
    return Proposal(
        action_code="check_out",
        permission="bookings.checkin",
        params={"stay_ids": [str(stay.pk) for stay in stays]},
        summary=ctx.text(
            f"Check-out de {reservation.code} ({reservation.booker.full_name})"
            + (f" · hab. {', '.join(rooms)}" if rooms else ""),
            f"Check out {reservation.code} ({reservation.booker.full_name})"
            + (f" · room {', '.join(rooms)}" if rooms else ""),
        ),
        details={
            "code": reservation.code,
            "guest": reservation.booker.full_name,
            "rooms": rooms,
            "warnings": warnings,
            "balance": money(balance),
            "currency": reservation.currency,
            "reservation_id": str(reservation.pk),
        },
    )


MESSAGE_TEMPLATES = [
    "confirmation",
    "pre_arrival",
    "arrival_day",
    "post_stay",
    "payment_reminder",
    "checkin_invitation",
]


@tool(
    "send_message",
    "Propone enviar un mensaje al huésped de una reserva: una plantilla del hotel o un texto libre "
    "(message). No lo envía: el usuario lo confirma.",
    {
        "reservation_code": CODE,
        "template_code": {"type": "string", "enum": MESSAGE_TEMPLATES},
        "message": {"type": "string", "description": "Texto libre para el huésped"},
        "channel": {"type": "string", "enum": ["email", "whatsapp"]},
    },
    "messaging.send",
    required=["reservation_code"],
    kind="action",
)
def propose_send_message(ctx, reservation_code=None, template_code=None, message=None, channel="email"):
    reservation = reservation_by_code(ctx, reservation_code)
    guest = reservation.booker
    if channel not in ("email", "whatsapp"):
        raise ToolError(
            ctx.text("Canal inválido: usa email o whatsapp", "Invalid channel: use email or whatsapp")
        )
    address = guest.email if channel == "email" else guest.phone
    if not address:
        raise ToolError(
            ctx.text(
                f"{guest.full_name} no tiene {'email' if channel == 'email' else 'teléfono'} registrado",
                f"{guest.full_name} has no {'email' if channel == 'email' else 'phone'} on file",
            )
        )
    if message:
        template = "custom_message"
    elif template_code in MESSAGE_TEMPLATES:
        template = template_code
    else:
        raise ToolError(
            ctx.text("Indica el mensaje o la plantilla a enviar", "Give the message or the template to send")
        )
    return Proposal(
        action_code="send_message",
        permission="messaging.send",
        params={
            "reservation_id": str(reservation.pk),
            "template_code": template,
            "message": str(message or "")[:2000],
            "channel": channel,
        },
        summary=ctx.text(
            f"Enviar {'WhatsApp' if channel == 'whatsapp' else 'email'} a {guest.full_name} "
            f"({reservation.code})",
            f"Send {'a WhatsApp' if channel == 'whatsapp' else 'an email'} to {guest.full_name} "
            f"({reservation.code})",
        ),
        details={
            "code": reservation.code,
            "guest": guest.full_name,
            "channel": channel,
            "to": address,
            "template_code": template,
            "message": str(message or "")[:2000],
            "reservation_id": str(reservation.pk),
        },
    )


BLOCK_KINDS = ["out_of_service", "out_of_order", "maintenance", "owner_hold"]


@tool(
    "block_room",
    "Propone bloquear una habitación por unas fechas (mantenimiento, fuera de servicio). No la bloquea: el "
    "usuario lo confirma.",
    {
        "room_number": {"type": "string"},
        "start": DATE,
        "end": {"type": "string", "description": "Fecha AAAA-MM-DD (exclusiva)"},
        "kind": {"type": "string", "enum": BLOCK_KINDS},
        "reason": {"type": "string"},
    },
    "inventory.manage",
    required=["room_number"],
    kind="action",
)
def propose_block_room(ctx, room_number=None, start=None, end=None, kind="out_of_service", reason=""):
    from apps.bookings.models import Stay

    room = room_by_number(ctx, room_number)
    first = parse_day(start, "start") or ctx.property.business_date
    last = parse_day(end, "end") or first + timedelta(days=1)
    if last <= first:
        raise ToolError(ctx.text("El fin debe ser posterior al inicio", "The end must be after the start"))
    if kind not in BLOCK_KINDS:
        kind = "out_of_service"
    booked = list(
        Stay.objects.filter(room=room, status__in=ACTIVE_STAY, checkin_date__lt=last, checkout_date__gt=first)
        .values_list("reservation__code", flat=True)
        .distinct()[:5]
    )
    if booked:
        raise ToolError(
            ctx.text(
                f"La {room.number} tiene reservas en esas fechas ({', '.join(booked)}): muévelas primero",
                f"Room {room.number} has reservations on those dates ({', '.join(booked)}): move them first",
            )
        )
    return Proposal(
        action_code="block_room",
        permission="inventory.manage",
        params={
            "room_id": str(room.pk),
            "start": first.isoformat(),
            "end": last.isoformat(),
            "kind": kind,
            "reason": str(reason or "")[:300],
        },
        summary=ctx.text(
            f"Bloquear la {room.number} · {_range_label(ctx, first, last)}",
            f"Block room {room.number} · {_range_label(ctx, first, last)}",
        ),
        details={
            "room": room.number,
            "start": first.isoformat(),
            "end": last.isoformat(),
            "nights": (last - first).days,
            "kind": kind,
            "reason": str(reason or "")[:300],
        },
    )


def extra_quantity(extra, reservation) -> int:
    nights = max(1, (reservation.checkout_date - reservation.checkin_date).days)
    persons = max(1, reservation.adults + reservation.children)
    return {
        "per_stay": 1,
        "per_night": nights,
        "per_person": persons,
        "per_person_night": persons * nights,
    }.get(extra.charge_type, 1)


@tool(
    "add_extra",
    "Propone agregar un extra (desayuno, parqueadero, traslado…) al folio de una reserva. No lo cobra: el "
    "usuario lo confirma.",
    {
        "reservation_code": CODE,
        "extra": {"type": "string", "description": "Código o nombre del extra"},
        "quantity": {"type": "integer"},
    },
    "finance.collect",
    required=["reservation_code", "extra"],
    kind="action",
)
def propose_add_extra(ctx, reservation_code=None, extra=None, quantity=None):
    from apps.rates.models import Extra

    reservation = reservation_by_code(ctx, reservation_code)
    if reservation.status in ("cancelled", "no_show"):
        raise ToolError(ctx.text(f"{reservation.code} está cancelada", f"{reservation.code} is cancelled"))
    extras = Extra.objects.filter(property=ctx.property, is_active=True)
    wanted = str(extra or "").strip()
    found = extras.filter(code__iexact=wanted).first() or next(
        (
            item
            for item in extras
            if nlp.norm(wanted)
            and (
                nlp.norm(wanted) in nlp.norm(t(item.name, "es"))
                or nlp.norm(wanted) in nlp.norm(t(item.name, "en"))
            )
        ),
        None,
    )
    if found is None:
        names = ", ".join(t(item.name, ctx.lang) for item in extras[:8])
        raise ToolError(
            ctx.text(
                f"No encontré el extra «{wanted}». Disponibles: {names}",
                f"Extra “{wanted}” not found. Available: {names}",
            )
        )
    units = int(quantity) if quantity else extra_quantity(found, reservation)
    if units < 1:
        raise ToolError(ctx.text("La cantidad debe ser al menos 1", "Quantity must be at least 1"))
    subtotal, tax_amount = extra_amounts(found, units, reservation)
    total = subtotal + tax_amount
    price_label = nlp.format_money(total, reservation.currency)
    name = t(found.name, ctx.lang)
    return Proposal(
        action_code="add_extra",
        permission="finance.collect",
        params={"reservation_id": str(reservation.pk), "extra_id": str(found.pk), "quantity": units},
        summary=ctx.text(
            f"Agregar {units} × {name} a {reservation.code} · {price_label}",
            f"Add {units} × {name} to {reservation.code} · {price_label}",
        ),
        details={
            "code": reservation.code,
            "guest": reservation.booker.full_name,
            "extra": name,
            "quantity": units,
            "unit_price": money(found.price),
            "subtotal": money(subtotal),
            "tax": money(tax_amount),
            "total": money(total),
            "currency": reservation.currency,
            "reservation_id": str(reservation.pk),
        },
    )


def extra_amounts(extra, units: int, reservation) -> tuple[Decimal, Decimal]:
    """(net, tax) the folio will get for `units` of `extra`: the same rules as
    `finance.services.post_extra_charge` (tax included in the price is split; foreign non-residents are
    exempt from taxes flagged so), computed without writing anything."""
    from apps.core.money import quantize
    from apps.finance.services import extra_unit_net

    tax = extra.tax if extra.tax_id and extra.tax.is_active else None
    net = quantize(extra_unit_net(extra, tax) * units, reservation.currency)
    exempt = bool(tax and tax.exempt_foreign_non_residents and reservation.booker.is_foreign_non_resident)
    if tax is None or exempt:
        return net, Decimal("0")
    return net, quantize(net * Decimal(tax.rate) / 100, reservation.currency)
