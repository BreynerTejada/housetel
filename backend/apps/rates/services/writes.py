"""Writes of the DailyRate grid (plan B2a: `set_daily_rates` and `POST grid/bulk/`).

`bulk_update_rates` writes `[start, end)` of a BASE plan for one or more categories in one transaction:
- missing rows are created with the resolved price (season/defaults with weekday %), keeping that source, so
  their price keeps following the configuration (`resolution.FOLLOWING_SOURCES`); a night without any
  configured price only accepts an exact `price` (`no_rate` otherwise: a restriction or a relative change
  alone would create a row priced at 0 and sell the night for free);
- `price` sets an exact price, `price_delta_percent` / `price_delta_amount` adjust the current price
  (never below 0; for a following row, the price it follows today); prices are rounded to the currency. A
  price change marks the row with `source`; restriction-only changes keep the row's source;
- `dow` keeps only those weekdays (Monday = 0);
- one reversible audit event (`rates.bulk_update`) stores every touched row before/after; its undo handler
  restores the previous rows (deleting the ones the write created) and refuses with `undo_conflict` when a row
  changed after the write;
- `rates_changed` is sent after commit with the written categories, the base plan and its derived plans.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.core import audit, signals
from apps.core.dates import daterange
from apps.core.errors import DomainError
from apps.core.models import AuditEvent
from apps.core.money import D, apply_percent, quantize
from apps.rates.models import DailyRate, RatePlan
from apps.rates.services.resolution import FOLLOWING_SOURCES, resolve_base_days

AUDIT_ACTION = "rates.bulk_update"
LOS_FIELDS = ("min_los", "max_los")
FLAG_FIELDS = ("closed_to_arrival", "closed_to_departure", "stop_sell")
RESTRICTION_FIELDS = (*LOS_FIELDS, *FLAG_FIELDS)
PRICE_DELTAS = ("price_delta_percent", "price_delta_amount")
MONEY_FIELDS = ("price", "extra_adult_price", "extra_child_price")
SNAPSHOT_FIELDS = (*MONEY_FIELDS, *RESTRICTION_FIELDS, "source")
AUDIT_SOURCES = {"revenue": "automation", "channel": "channel"}
CENTS = Decimal("0.01")


@dataclass(frozen=True)
class WriteResult:
    updated: int
    event: AuditEvent | None = None


def bulk_update_rates(
    *,
    property,
    room_types,
    rate_plan,
    start: date,
    end: date,
    price=None,
    restrictions=None,
    dow=None,
    source: str = "bulk",
    actor=None,
) -> WriteResult:
    """Write the grid of a BASE plan for every category in `room_types` (see the module docstring)."""
    if rate_plan.kind != RatePlan.Kind.BASE:
        raise DomainError(
            "Los planes derivados se calculan desde su plan base", code="derived_plan_not_editable"
        )
    restrictions = _clean_restrictions(restrictions)
    price = _clean_price(price)
    weekdays = _clean_weekdays(dow)
    user = actor if getattr(actor, "is_authenticated", False) else None
    currency = property.currency or "COP"
    changes_price = price is not None or any(key in restrictions for key in PRICE_DELTAS)

    items: list[dict] = []
    written_types = []
    with transaction.atomic():
        for room_type in room_types:
            count_before = len(items)
            existing = {
                row.date: row
                for row in DailyRate.objects.select_for_update().filter(
                    room_type=room_type, rate_plan=rate_plan, date__gte=start, date__lt=end
                )
            }
            resolved = {day.date: day for day in resolve_base_days(room_type, rate_plan, start, end)}
            for day in daterange(start, end):
                if weekdays is not None and day.weekday() not in weekdays:
                    continue
                row = existing.get(day)
                before = _snapshot(row) if row is not None else None
                before_user = str(row.updated_by_id) if row is not None and row.updated_by_id else None
                resolved_day = resolved[day]
                if row is None:
                    if resolved_day.source == "none" and price is None:
                        raise _no_rate(room_type, day)
                    row = DailyRate(
                        room_type=room_type,
                        rate_plan=rate_plan,
                        date=day,
                        price=resolved_day.price,
                        source=resolved_day.source if resolved_day.source in FOLLOWING_SOURCES else source,
                    )
                elif row.source in FOLLOWING_SOURCES:
                    # nobody set its price: start from the price it follows today (season/defaults)
                    row.price, row.source = resolved_day.price, resolved_day.source
                _apply(row, price, restrictions, currency)
                if changes_price:
                    row.source = source
                row.updated_by = user
                row.save()
                items.append(
                    {
                        "room_type_id": str(room_type.pk),
                        "rate_plan_id": str(rate_plan.pk),
                        "date": day.isoformat(),
                        "before": before,
                        "before_updated_by": before_user,
                        "after": _snapshot(row),
                    }
                )
            if len(items) > count_before:
                written_types.append(room_type)
        if not items:
            return WriteResult(updated=0)
        event = audit.record(
            action=AUDIT_ACTION,
            target=rate_plan,
            property=property,
            actor=actor,
            source="user" if user is not None else AUDIT_SOURCES.get(source, "system"),
            summary=_summary(written_types, start, end, len(items)),
            changes={
                "room_types": [room_type.code for room_type in written_types],
                "start": start.isoformat(),
                "end": end.isoformat(),
                "weekdays": sorted(weekdays) if weekdays is not None else None,
                "price": None if price is None else format(price, "f"),
                "restrictions": {key: _jsonable(value) for key, value in restrictions.items()},
                "source": source,
                "nights": len(items),
            },
            reversible=True,
            undo_data={"rows": items},
        )
        emit_rates_changed(property, [room_type.pk for room_type in written_types], [rate_plan], start, end)
    return WriteResult(updated=len(items), event=event)


def emit_rates_changed(property, room_type_ids, base_plans, start, end) -> None:
    """`rates_changed` after commit; `rate_plan_ids` = each base plan followed by its derived plans."""
    plan_ids = []
    for plan in base_plans:
        plan_ids.append(plan.pk)
        plan_ids.extend(RatePlan.objects.filter(parent=plan).values_list("pk", flat=True))
    signals.send_on_commit(
        signals.rates_changed,
        property=property,
        room_type_ids=list(room_type_ids),
        rate_plan_ids=plan_ids,
        start=start,
        end=end,
    )


def undo_bulk_update(event: AuditEvent) -> None:
    """Undo handler of `rates.bulk_update` (registered by RatesConfig.ready)."""
    items = (event.undo_data or {}).get("rows") or []
    if not items:
        return
    current = {
        (str(row.room_type_id), str(row.rate_plan_id), row.date.isoformat()): row
        for row in DailyRate.objects.select_for_update().filter(
            room_type_id__in={item["room_type_id"] for item in items},
            rate_plan_id__in={item["rate_plan_id"] for item in items},
            date__in={date.fromisoformat(item["date"]) for item in items},
        )
    }
    keys = [(item["room_type_id"], item["rate_plan_id"], item["date"]) for item in items]
    for key, item in zip(keys, items, strict=True):
        row = current.get(key)
        if row is None or _snapshot(row) != item["after"]:
            raise audit.UndoError(
                "Estas tarifas cambiaron después de la edición: deshaz primero los cambios más recientes",
                code="undo_conflict",
            )
    for key, item in zip(keys, items, strict=True):
        row = current[key]
        if item["before"] is None:
            row.delete()
            continue
        for field in SNAPSHOT_FIELDS:
            value = item["before"][field]
            setattr(row, field, D(value) if field in MONEY_FIELDS and value is not None else value)
        row.updated_by_id = item.get("before_updated_by")
        row.save()

    dates = sorted(date.fromisoformat(item["date"]) for item in items)
    room_type_ids = list(dict.fromkeys(row.room_type_id for row in current.values()))
    plans = RatePlan.objects.filter(pk__in={item["rate_plan_id"] for item in items})
    emit_rates_changed(event.property, room_type_ids, list(plans), dates[0], dates[-1] + timedelta(days=1))


def register_undo_handlers() -> None:
    audit.register_undo(AUDIT_ACTION, undo_bulk_update)


# ---- helpers ------------------------------------------------------------------------------------------


def _invalid_restriction(message: str) -> DomainError:
    return DomainError(message, code="invalid_restriction")


def _no_rate(room_type, day: date) -> DomainError:
    """A night without any configured price only accepts an exact price (else it would sell at 0)."""
    return DomainError(
        f"{room_type.code} no tiene precio el {day:%d/%m/%Y}: fija un precio exacto o configura el precio "
        "por defecto de la categoría",
        code="no_rate",
        room_type=room_type.code,
        date=day,
    )


def _clean_price(price):
    if price is None:
        return None
    try:
        value = D(price)
    except (InvalidOperation, TypeError, ValueError):
        raise DomainError("El precio debe ser un número", code="invalid_price") from None
    if not value.is_finite() or value < 0:
        raise DomainError("El precio no puede ser negativo", code="invalid_price")
    return value


def _clean_weekdays(dow):
    if dow is None:
        return None
    try:
        weekdays = {int(day) for day in dow}
    except (TypeError, ValueError):
        raise DomainError(
            "Los días de la semana van de 0 (lunes) a 6 (domingo)", code="invalid_dow"
        ) from None
    if any(isinstance(day, bool) for day in dow) or not weekdays <= set(range(7)):
        raise DomainError("Los días de la semana van de 0 (lunes) a 6 (domingo)", code="invalid_dow")
    return weekdays


def _clean_restrictions(restrictions) -> dict:
    restrictions = dict(restrictions or {})
    unknown = set(restrictions) - set(RESTRICTION_FIELDS) - set(PRICE_DELTAS)
    if unknown:
        raise _invalid_restriction(f"Restricciones desconocidas: {', '.join(sorted(unknown))}")
    for key in LOS_FIELDS:
        value = restrictions.get(key)
        if key in restrictions and value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise _invalid_restriction("La estadía mínima y máxima deben ser de al menos 1 noche")
    for key in FLAG_FIELDS:
        if key in restrictions and not isinstance(restrictions[key], bool):
            raise _invalid_restriction("Las restricciones de llegada, salida y venta son sí o no")
    for key in PRICE_DELTAS:
        if key in restrictions:
            try:
                value = D(restrictions[key])
            except (InvalidOperation, TypeError, ValueError):
                raise _invalid_restriction("El ajuste de precio debe ser un número") from None
            if not value.is_finite() or (key == "price_delta_percent" and value < -100):
                raise _invalid_restriction("El ajuste porcentual no puede bajar de -100 %")
            restrictions[key] = value
    return restrictions


def _apply(row: DailyRate, price, restrictions: dict, currency: str) -> None:
    if price is not None:
        row.price = price
    if "price_delta_percent" in restrictions:
        row.price = apply_percent(row.price, restrictions["price_delta_percent"])
    if "price_delta_amount" in restrictions:
        row.price = D(row.price) + restrictions["price_delta_amount"]
    row.price = quantize(max(D(row.price), Decimal("0")), currency)
    for key in RESTRICTION_FIELDS:
        if key in restrictions:
            setattr(row, key, restrictions[key])


def _money(value) -> str | None:
    return None if value is None else format(D(value).quantize(CENTS), "f")


def _snapshot(row: DailyRate) -> dict:
    data = {field: getattr(row, field) for field in SNAPSHOT_FIELDS}
    for field in MONEY_FIELDS:
        data[field] = _money(data[field])
    return data


def _jsonable(value):
    return format(value, "f") if isinstance(value, Decimal) else value


def _summary(room_types, start: date, end: date, nights: int) -> str:
    codes = ", ".join(room_type.code for room_type in room_types)
    last = end - timedelta(days=1)
    return f"Tarifas actualizadas ({codes}): {start:%d/%m/%Y}–{last:%d/%m/%Y}, {nights} noches"
