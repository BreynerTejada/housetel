# B2b — Motor de reservas (backend) — integration notes

Estado: tarea B2b completa (reanudada desde un intento previo interrumpido: el trabajo heredado se revisó, se
completó con TDD y se corrigió) y **revisada por el verificador de B2b** (ver "Verificación › Pasada del
verificador": 4 correcciones con test). `docker compose run --rm -e TEST_DB_NAME=test_b2bv backend pytest
apps/bookings -q` → todo verde. Sin frontend. Sin migraciones nuevas (los modelos de la Fase A bastan).

Lectura obligatoria para C1 (recepción), C13 (calendario), C3 (canales), C4 (marketplace), C5 (portal), C9
(IA), C10 (reportes), C2 (housekeeping), C6 (mensajería) y C11 (comisiones): "Guía rápida", "API implementada"
y "Señales".

---

## Guía rápida

- **Servicios (backend de otras apps)** — únicos puntos de escritura sobre reservas:
  `apps.bookings.services.reservations` (`create_reservation`, `modify_stay`, `preview_modify_stay`,
  `cancel_reservation`, `confirm_reservation`, `update_reservation`, `assign_room`, `unassign_room`,
  `auto_assign_rooms`, `check_in`, `check_out`, `mark_no_show`, `add_occupant`, `remove_occupant`),
  `apps.bookings.services.charges.post_room_charges`, `apps.bookings.services.availability`
  (`availability`, `search_offers`), `apps.bookings.services.inventory.rebuild_inventory`, lecturas
  `apps.bookings.services.policies.cancellation_fee` (vista previa de penalidad) y
  `apps.bookings.services.assignment.room_options`. Tipos y errores en `apps/bookings/types.py`.
- **API de staff**: `/api/v1/bookings/…` con sesión + `X-Property-Id` (reglas de tenancy de A1: 400
  `property_required`, 404 propiedad/objeto ajeno, 403 `permission_denied` + `permission`, 402 suspendida).
  No hay API pública de bookings: C4/C5 exponen la suya y llaman a los servicios.
- **Fechas**: `checkin` inclusivo, `checkout` exclusivo en todo (`[checkin, checkout)`); rangos `start/end`
  de calendario, señales e inventario también semiabiertos. Filtros `arrival_*`/`departure_*` y el rango de
  `auto-assign` son **inclusivos** (se dice en cada uno).
- **Dinero**: strings con 2 decimales (`"380800.00"`); COP redondeado a pesos.
- **"Hoy" operativo** = `property.business_date` (no el reloj): check-in, no-show, salida anticipada, flags y
  auto-asignación lo usan.
- **Errores**: `{detail, code, ...extra}` (ver tabla "Errores y códigos").

---

## API implementada

Permisos (§D): `bookings.view` (lecturas), `bookings.manage` (crear/modificar/asignar/grupos),
`bookings.checkin` (check-in/out), `bookings.cancel`, `bookings.waive_fee`, `bookings.checkout_with_balance`,
`bookings.overbook`.

| Método y path | Permiso | Respuesta |
|---|---|---|
| `GET reservations/` | view | página de `ReservationList` (filtros abajo) |
| `POST reservations/` | manage (+`overbook` si `allow_overbooking`) | 201 `ReservationDetail` |
| `GET reservations/{id}/` | view | `ReservationDetail` |
| `PATCH reservations/{id}/` | manage | `ReservationDetail` (solo campos libres) |
| `POST reservations/{id}/cancel/` | cancel (+`waive_fee` si `waive_fee`) | `ReservationDetail` |
| `GET reservations/{id}/cancel-preview/` | view | `{fee, currency, reason, free_until, non_refundable, policy}` |
| `POST reservations/{id}/confirm/` | manage | `ReservationDetail` (tentativa → confirmada) |
| `POST reservations/{id}/no-show/` | manage | `ReservationDetail` |
| `GET stays/{id}/` | view | `StayDetail` |
| `POST stays/{id}/modify/` | manage | `ReservationDetail` |
| `POST stays/{id}/modify-preview/` | manage | vista previa (no guarda nada) |
| `GET stays/{id}/room-options/` | view | habitaciones/camas a las que puede ir |
| `POST stays/{id}/assign/` · `unassign/` | manage | `ReservationDetail` |
| `POST stays/{id}/check-in/` | checkin | `ReservationDetail` |
| `POST stays/{id}/check-out/` | checkin (+`checkout_with_balance` si `force`) | `ReservationDetail` |
| `POST/DELETE stays/{id}/occupants/` | manage | `ReservationDetail` |
| `GET availability/` | view | `{room_type_id: unidades}` |
| `GET offers/` | view | `[Offer]` (más barata primero) |
| `GET calendar/` | view | grilla completa (C1/C13) |
| `POST auto-assign/` | manage | reporte de asignación |
| CRUD `groups/` | view (GET) / manage | `ReservationGroup` |
| `POST inventory/rebuild/` | manage | `{created, updated, drift}` |

Todas las acciones de escritura sobre una reserva o estadía responden con el **detalle completo actualizado
de la reserva** (así la UI refresca stays, saldo y flags de una vez). Toda la API está en `/api/docs/`.

### `GET reservations/` — lista

Paginada `{count, next, previous, results}` (`page`, `page_size` ≤ 200). Filtros (combinables; los de fecha son
inclusivos):

| Parámetro | Significado |
|---|---|
| `status` (repetible) | `tentative, confirmed, checked_in, checked_out, cancelled, no_show` |
| `source` (repetible) | `walk_in, phone, email, front_desk, booking_engine, marketplace, ota, api` |
| `channel_code` | p. ej. `booksim` |
| `arrival_from` / `arrival_to` | `arrival_from ≤ checkin_date ≤ arrival_to` |
| `departure_from` / `departure_to` | igual con `checkout_date` |
| `in_house_on=YYYY-MM-DD` | alguna estadía `confirmed/checked_in/checked_out` cubre esa noche (`checkin ≤ d < checkout`) |
| `room_type=<uuid>` | alguna estadía de esa categoría |
| `unassigned=1` / `0` | tiene (o no) estadías tentativas/confirmadas sin habitación |
| `balance_due=1` / `0` | saldo > 0 (o ≤ 0) |
| `booker=<uuid>` · `group=<uuid>` | por huésped titular / grupo |
| `q` | código, nombre completo, email o teléfono del titular, `external_id` (icontains) |
| `ordering` | `checkin_date, checkout_date, created_at, code, total_amount, balance` (± ; por defecto `-checkin_date,-created_at`) |

Vistas rápidas de C1: llegadas hoy = `arrival_from=arrival_to=<business_date>&status=confirmed&status=tentative`;
salidas hoy = `departure_from=departure_to=<bd>&status=checked_in`; en casa = `status=checked_in`; sin pagar =
`balance_due=1`; sin asignar = `unassigned=1`; tentativas = `status=tentative`.

Ítem (`ReservationList`):

```json
{
  "id": "5b29fc55-…", "code": "HT-897GAN", "status": "confirmed", "source": "ota",
  "channel_code": "booksim", "external_id": "BK-1001",
  "checkin_date": "2026-10-05", "checkout_date": "2026-10-07", "nights": 2, "adults": 2, "children": 0,
  "currency": "COP", "total_amount": "761600.00", "balance": "761600.00", "guarantee": "none",
  "hold_expires_at": null, "created_at": "2026-09-26T19:23:22.796971-05:00",
  "booker": {"id": "…", "full_name": "Laura Gómez", "email": "laura3@example.com", "phone": "",
             "is_vip": false, "nationality": "CO"},
  "group": null,
  "stays": [{"id": "…", "status": "confirmed",
             "room_type": {"id": "…", "code": "DBL", "name": {"es": "Estándar", "en": "Standard"},
                           "kind": "private", "color": "#4E6C88"},
             "room": null, "bed": null}]
}
```

`balance` sale de una anotación SQL equivalente a `finance.reservation_balance` (un test mantiene ambas
iguales). Una tentativa trae `hold_expires_at` (fin de la retención).

### `POST reservations/` — crear

Cuerpo = `ReservationRequest` en JSON. El titular va como objeto `booker` (GuestInput → `upsert_guest`) **o**
como `booker_id` (huésped existente de la organización):

```json
{
  "booker": {"first_name": "Laura", "last_name": "Gómez", "email": "laura@example.com",
             "phone": "+573001234567", "document_type": "CC", "document_number": "52123456",
             "nationality": "CO", "country_of_residence": "CO", "city_of_residence": "",
             "birth_date": null, "language": "es", "marketing_consent": false,
             "data_processing_consent": true},
  "stays": [{
    "room_type_id": "<uuid>", "rate_plan_id": "<uuid>",
    "checkin": "2026-10-01", "checkout": "2026-10-03",
    "adults": 2, "children": 1, "children_ages": [7],
    "room_id": "<uuid>|null", "bed_id": "<uuid>|null", "locked_room": false,
    "occupants": [{"first_name": "Ana", "last_name": "Gómez"}], "occupant_ids": ["<guest uuid>"],
    "nightly_rates": null
  }],
  "source": "phone", "channel_code": "", "external_id": "", "external_payload": {},
  "notes": "Llega tarde", "special_requests": "", "promo_code": "", "language": "es", "eta": "21:30",
  "status": "confirmed", "allow_overbooking": false, "enforce_restrictions": true, "hold_minutes": 20,
  "guarantee": "card", "group_id": null, "custom_values": {}
}
```

- Valores por defecto: `source="front_desk"`, `status="confirmed"` (o `"tentative"`), `guarantee="none"`
  (`none|card|deposit|ota`), `hold_minutes=20` (solo tentativas; 0 = sin vencimiento), `adults` requerido,
  `children=0`. `children_ages` (si viene) debe tener un valor por niño.
- `nightly_rates` = precios impuestos por un canal: `[{"date": "2026-10-01", "amount": "300000"}]`, cubriendo
  exactamente las noches (mismo significado que el precio cotizado: antes del IVA no incluido).
- Una estadía de **dormitorio** para N huéspedes se convierte en **N estadías de una cama** (camas distintas);
  con `room_id` de un dorm sin `bed_id` se asignan camas libres de ese cuarto; un `bed_id` es para 1 huésped.
- El staff queda auditado como `source="user"` sin importar el `source` de la reserva.
- Respuesta 201 = `ReservationDetail` (abajo). Errores: 409 `no_availability` (+`shortfalls`), 400
  `restriction_violation` (+`violations`), 400 `capacity_exceeded`, `invalid_room_type`, `invalid_rate_plan`,
  `invalid_dates`, `invalid_guest`, `invalid_room`/`invalid_bed`/`category_mismatch`, `promo_invalid`,
  `no_rate`, `invalid_nightly_rates`, `invalid_children_ages`, `invalid_group`, `invalid_custom_values`,
  `validation_error` (+`fields`); 403 `bookings.overbook` si pide sobreventa sin permiso.

### `GET reservations/{id}/` — detalle (`ReservationDetail`)

Respuesta real (acortada en los ids):

```json
{
  "id": "944d5504-…", "code": "HT-BVNNDB", "status": "confirmed", "source": "phone",
  "channel_code": "", "external_id": "", "checkin_date": "2026-10-01", "checkout_date": "2026-10-03",
  "nights": 2, "adults": 2, "children": 0, "currency": "COP",
  "total_amount": "761600.00", "balance": "761600.00", "guarantee": "card", "hold_expires_at": null,
  "created_at": "2026-09-26T19:23:22.439446-05:00",
  "booker": {"id": "…", "first_name": "Laura", "last_name": "Gómez", "full_name": "Laura Gómez",
             "email": "laura@example.com", "phone": "+573001234567", "document_type": "CC",
             "document_number": "52123456", "nationality": "CO", "country_of_residence": "CO",
             "language": "es", "is_vip": false, "is_foreign_non_resident": false},
  "group": null,
  "stays": [{
    "id": "4ee28d25-…", "status": "confirmed", "checkin_date": "2026-10-01", "checkout_date": "2026-10-03",
    "nights": 2, "adults": 2, "children": 0, "children_ages": [],
    "room_type": {"id": "…", "code": "DBL", "name": {"es": "…", "en": "…"}, "kind": "private", "color": "#4E6C88"},
    "rate_plan": {"id": "…", "code": "BAR", "name": {"es": "Tarifa BAR", "en": "Rate BAR"}, "meal_plan": "room_only"},
    "room": {"id": "…", "number": "101", "floor": "1", "housekeeping_status": "clean"},
    "bed": null, "locked_room": false,
    "nightly_rates": [
      {"date": "2026-10-01", "amount": "380800.00", "net": "320000.00", "tax": "60800.00"},
      {"date": "2026-10-02", "amount": "380800.00", "net": "320000.00", "tax": "60800.00"}],
    "total_amount": "761600.00", "checked_in_at": null, "checked_out_at": null, "occupants": []
  }],
  "language": "es", "eta": "21:30:00", "special_requests": "", "notes": "Llega tarde", "promo_code": "",
  "cancellation_policy_snapshot": {"id": "…", "name": {"es": "Flexible 48h", "en": "Flexible 48h"},
    "description": {}, "non_refundable": false, "free_until_hours_before": 48,
    "penalty_type": "first_night", "penalty_value": "0.00", "rate_plan_id": "…"},
  "cancelled_at": null, "cancellation_reason": "", "cancellation_fee": "0.00",
  "custom_values": {}, "tags": [], "external_payload": {},
  "created_by": {"id": "…", "full_name": "Usuario 0", "email": "user0@example.com"},
  "updated_at": "2026-09-26T19:23:22.439466-05:00",
  "folio_id": "878f3f28-…",
  "portal_url": "http://localhost:5173/g/<token firmado>",
  "flags": {"ready_for_checkin": true, "arrives_today": true, "departs_today": false,
            "in_house": false, "unassigned": false, "balance_due": true}
}
```

- `balance` = `finance.reservation_balance`; `folio_id` = folio `guest` de la reserva (para `<FolioPanel>`);
  `portal_url` = `core.tokens.portal_url`.
- `occupants`: misma forma que `booker`.
- `flags` (respecto a `business_date`): `ready_for_checkin` (confirmada, llega hoy o antes y sigue vigente,
  todas sus estadías pendientes con habitación limpia/inspeccionada), `arrives_today`, `departs_today`
  (en casa y sale hoy), `in_house`, `unassigned` (alguna pendiente sin habitación), `balance_due`.
  El check-in online (C5) no entra en estos flags.
- `cancellation_policy_snapshot` = `{}` si el plan no tiene política.

### `PATCH reservations/{id}/`

Solo campos libres: `notes`, `special_requests`, `eta` (`"HH:MM"`/null), `language`, `guarantee`,
`custom_values` (validados), `tags` (lista de strings), `group_id` (null lo quita), `booker_id` (otro
huésped de la organización). Fechas, estadías, precios y estado solo cambian por sus acciones.

### Cancelación

- `GET reservations/{id}/cancel-preview/` →
  `{"fee": "0.00", "currency": "COP", "reason": "free_window", "free_until": "2026-09-29T15:00:00-05:00",
  "non_refundable": false, "policy": {…snapshot…}}`. `reason`: `tentative` (siempre gratis), `no_policy`,
  `non_refundable` (total), `free_window` (gratis hasta `free_until`), `first_night`, `percent`, `full`.
- `POST reservations/{id}/cancel/` `{"reason": "Cambio de planes", "waive_fee": false, "confirm": true}` →
  detalle con `status: "cancelled"`, `cancelled_at`, `cancellation_reason`, `cancellation_fee`. Sin
  `confirm: true` → 400 `confirmation_required`. `waive_fee: true` exige además `bookings.waive_fee`.
  Solo tentativas/confirmadas (en casa → 409 `invalid_state`).

### Estadías

- `POST stays/{id}/modify/` `{"checkin"?, "checkout"?, "room_type_id"?, "rate_plan_id"?, "adults"?,
  "children"?, "reprice": true}` → detalle. 409 `no_availability` si una noche nueva no tiene unidad; 400
  `invalid_room_type`/`invalid_rate_plan`/`capacity_exceeded`/`invalid_dates`; 409 `invalid_state` (estadía
  inactiva o en casa cambiando llegada/categoría).
- `POST stays/{id}/modify-preview/` (mismo cuerpo) → lo que haría el cambio, **sin guardar nada** (mismos
  errores):

  ```json
  {"stay": {"id": "…", "checkin_date": "2026-10-01", "checkout_date": "2026-10-04", "nights": 3,
            "room_type_id": "…", "rate_plan_id": "…", "room_id": "…", "bed_id": null,
            "adults": 2, "children": 0, "total_amount": "1142400.00",
            "nightly_rates": [{"date": "2026-10-01", "amount": "380800.00", "net": "320000.00", "tax": "60800.00"}, …]},
   "room_kept": true, "current_total": "761600.00", "difference": "380800.00",
   "reservation_total": "1142400.00", "balance": "1142400.00"}
  ```

  `room_kept`: `true` la conserva, `false` la perdería (queda sin asignar), `null` si aún no tenía.
- `GET stays/{id}/room-options/` → dónde puede ir la estadía, mejor primero: habitaciones (o camas) libres y
  sin bloqueo en todas sus noches; primero su categoría ordenada como la auto-asignación (limpias/inspeccionadas
  primero si llega hoy o está en casa, sin huecos, orden de habitación), luego otras categorías del mismo tipo
  (privada/dorm) con unidad disponible todas las noches (asignarlas es cambio de categoría → `force`). No lista
  la unidad actual:

  ```json
  [{"room_id": "…", "room_number": "102", "floor": "1", "room_type_id": "…", "room_type_code": "DBL",
    "bed_id": null, "bed_label": null, "housekeeping_status": "clean", "ready": true, "same_category": true},
   {"room_id": "…", "room_number": "301", "floor": "3", "room_type_id": "…", "room_type_code": "STE",
    "bed_id": null, "bed_label": null, "housekeeping_status": "clean", "ready": true, "same_category": false}]
  ```
- `POST stays/{id}/assign/` `{"room_id": "<uuid>", "bed_id": "<uuid>|null", "force": false}` → detalle.
  409 `no_availability` (ocupada: la garantiza la restricción de exclusión de la BD), 409 `room_blocked`, 400
  `category_mismatch` (otra categoría sin `force`), 400 `invalid_room`/`invalid_bed`. En dorm sin `bed_id`
  toma la primera cama libre. Mover a un huésped **en casa** deja la habitación anterior `dirty`.
- `POST stays/{id}/unassign/` → detalle (en casa → 409 `invalid_state`).
- `POST stays/{id}/check-in/` `{"force": false}` → detalle. 409 `room_not_ready` (+`room_id`,
  `housekeeping_status`) si la habitación no está limpia/inspeccionada; 409 `invalid_state` (tentativa sin
  force, llegada futura, llegada pasada o estadía ya terminada sin force, sin habitación libre para
  auto-asignar).
- `POST stays/{id}/check-out/` `{"force": false}` → detalle. 409 `balance_due` + `amount` (ej.
  `{"detail": "La reserva tiene un saldo pendiente de 77350.00", "code": "balance_due", "amount":
  "77350.00"}`); `force: true` exige `bookings.checkout_with_balance`.
- `POST stays/{id}/occupants/` `{"guest_id": "<uuid>"}` o `{"guest": {GuestInput}}`; `DELETE
  stays/{id}/occupants/?guest_id=<uuid>` → detalle.
- `GET stays/{id}/` → la estadía (misma forma que en el detalle) + `reservation_id` y `code`.

### `GET availability/?checkin=&checkout=[&room_type=<uuid>…]`

`{"<room_type_id>": 0, "<otro>": 1, "<dorm>": 3}` = mínimo de unidades vendibles sobre las noches, por
categoría **activa** (dorm: camas). **Puede ser negativo** (sobreventa). `checkout` debe ser > `checkin`.

### `GET offers/?checkin=&checkout=&adults=2&children=0&children_ages=4,7&channel=direct&promo_code=&foreign=0`

Lista de ofertas vendibles, total ascendente (desempate: orden de categoría y de plan). Cada una:

```json
{
  "room_type_id": "…", "rate_plan_id": "…",
  "room_type": {"id": "…", "code": "DBL", "name": {"es": "…", "en": "…"}, "kind": "private",
                "color": "#4E6C88", "max_adults": 2, "max_children": 1, "max_occupancy": 3},
  "rate_plan": {"id": "…", "code": "BAR", "name": {"es": "…", "en": "…"}, "meal_plan": "room_only",
                "is_public": true, "deposit_percent": "0.00", "cancellation_policy": {…snapshot…|null}},
  "available_units": 3, "units_needed": 1,
  "quote": {"room_type_id": "…", "rate_plan_id": "…", "checkin": "2026-10-10", "checkout": "2026-10-12",
            "adults": 2, "children": 0,
            "nights": [{"date": "2026-10-10", "base": "320000.00", "extra_adults": "0.00",
                        "extra_children": "0.00", "discount": "0.00", "total": "320000.00"}, …],
            "subtotal": "640000.00", "discount_total": "0.00",
            "taxes": [{"code": "IVA", "name": "IVA 19%", "rate": "19.00", "amount": "121600.00",
                       "included": false, "exempt": false}],
            "tax_total": "121600.00", "total": "761600.00", "currency": "COP",
            "restrictions_ok": true, "violations": [], "promo_applied": null},
  "total": "761600.00"
}
```

- `quote` = `Quote.to_dict()` de rates **por unidad**; `total = quote.total × units_needed`.
- Dorm: `units_needed = adults + children` (1 cama por persona) y la cotización es por cama (1 adulto).
- Reglas de `search_offers` en "Contratos". `foreign=1` cotiza sin IVA (extranjero no residente).

### `GET calendar/?start=&end=` (C1/C13)

Rango semiabierto `[start, end)`, máximo 93 días (si no, 400 `range_too_long`). Forma exacta:

```json
{
  "room_types": [{
    "id": "…", "code": "DBL", "name": {"es": "Estándar", "en": "Standard"}, "color": "#4E6C88", "kind": "private",
    "rooms": [{"id": "…", "number": "101", "floor": "1", "housekeeping_status": "clean", "beds": []}, …]
  }, {
    "id": "…", "code": "DORM", "name": {…}, "color": "…", "kind": "dorm",
    "rooms": [{"id": "…", "number": "D1", "floor": "1", "housekeeping_status": "clean",
               "beds": [{"id": "…", "label": "A"}, {"id": "…", "label": "B"}]}]
  }],
  "stays": [{
    "id": "…", "reservation_id": "…", "code": "HT-BVNNDB", "status": "confirmed", "source": "phone",
    "channel_code": "", "guest_name": "Laura Gómez", "room_id": "…|null", "bed_id": "…|null",
    "room_type_id": "…", "checkin": "2026-10-01", "checkout": "2026-10-03", "adults": 2, "children": 0,
    "balance_due": true, "is_vip": false
  }],
  "blocks": [{"id": "…", "room_id": "…", "bed_id": null, "start": "2026-10-02", "end": "2026-10-05",
              "kind": "maintenance", "reason": "Pintura"}],
  "availability": {"<room_type_id>": {"2026-10-01": 2, "2026-10-02": 0, "2026-10-03": 1}}
}
```

- Categorías y habitaciones/camas **activas**, en orden (`sort_order`, código / número / etiqueta).
- `stays`: estadías `tentative/confirmed/checked_in/checked_out` que tocan el rango (canceladas y no-show no
  salen). `room_id: null` → fila "Sin asignar" de su `room_type_id`. En dorm, `room_id` = el cuarto y `bed_id`
  = la cama. Una estadía con upgrade tiene `room_type_id` = la categoría reservada y `room_id` en otra
  categoría. `checkout` es exclusivo (la barra termina el día anterior).
- `blocks`: bloqueos activos (`end` exclusivo); `bed_id: null` = todo el cuarto.
- `availability`: unidades vendibles por noche (desde `InventoryDay`; puede ser negativa).
- Precios: C13 los toma de `GET /api/v1/rates/grid/` (B2a).

### `POST auto-assign/` `{"date_from": "2026-10-01", "date_to": "2026-10-02"}` (ambos inclusivos)

```json
{"assigned": [{"stay_id": "…", "reservation_id": "…", "code": "HT-G8DBG7", "room_id": "…",
               "room_number": "102", "bed_id": null, "bed_label": null}],
 "unassigned": [{"stay_id": "…", "reservation_id": "…", "code": "HT-…"}],
 "messages": ["HT-…: no hay habitaciones libres en DBL del 2026-10-01 al 2026-10-03"]}
```

### `groups/` (CRUD)

`{"id", "name", "notes", "contact_guest_id" (escritura, huésped de la organización), "contact_guest"
(lectura: {id, full_name, email, phone, is_vip, nationality} | null), "reservations_count", "created_at"}`.
Borrar un grupo deja sus reservas sin grupo. Para meter reservas a un grupo: `group_id` al crear o `PATCH`.

### `POST inventory/rebuild/` `{"start"?, "end"?, "room_type_ids"?}`

Recalcula `InventoryDay` (por defecto el horizonte) → `{"created": 9, "updated": 0, "drift": []}`
(`drift`: hasta 50 filas corregidas con `{room_type_id, date, <campo>: [antes, después]}`). Auditado
`bookings.inventory_rebuilt`.

### Errores y códigos

| HTTP | `code` | Cuándo |
|---|---|---|
| 409 | `no_availability` | sin unidad (crear, modificar, upgrade, habitación ocupada). Crear añade `shortfalls: [{room_type_id, date, available, requested}]` |
| 409 | `room_blocked` | habitación/cama bloqueada en esas fechas |
| 409 | `invalid_state` | transición no permitida (cancelar en casa, check-in de tentativa sin force, etc.) |
| 409 | `room_not_ready` | check-in en habitación no limpia/inspeccionada (+`room_id`, `housekeeping_status`) |
| 409 | `balance_due` | check-out con saldo (+`amount`) |
| 400 | `restriction_violation` | restricciones de tarifa (+`violations`: `stop_sell`, `cta`, `ctd`, `min_los`, `max_los`) |
| 400 | `capacity_exceeded`, `invalid_dates`, `invalid_room_type`, `invalid_rate_plan`, `invalid_room`, `invalid_bed`, `category_mismatch`, `invalid_guest`, `invalid_group`, `invalid_nightly_rates`, `invalid_children_ages`, `promo_invalid`, `no_rate`, `invalid_status`, `invalid_source`, `invalid_guarantee`, `invalid_field`, `no_stays`, `range_too_long`, `invalid_custom_values` (+`fields`) | validación de dominio |
| 400 | `confirmation_required` | cancelar sin `confirm: true` |
| 400 | `validation_error` | cuerpo/query inválido (+`fields`) |

---

## Contratos implementados / consumidos

Firmas exactas del spec §4.2 y plan §C (congeladas por `apps/core/tests/test_contracts.py`, que sigue verde).

### Disponibilidad e inventario (`services/availability.py`, `services/inventory.py`)

- `InventoryDay` por `(room_type, date)`: `total_units` = habitaciones activas (privadas) o camas activas de
  habitaciones activas (dorm); `blocked_units` = unidades distintas bajo bloqueos activos (`released_at`
  null) de habitaciones activas (bloqueo de cuarto dorm = todas sus camas; de cama = 1); `sold_units` =
  estadías **activas** (`tentative/confirmed/checked_in`) que cubren la noche, contadas en la categoría de su
  habitación asignada (un upgrade ocupa la categoría superior) o, sin habitación, en la reservada.
  `available = total − sold − blocked` (puede ser negativo). Una estadía `checked_out` deja de contar.
- `rebuild_inventory(property, start=None, end=None, room_type_ids=None) -> RebuildResult` (idempotente;
  horizonte por defecto `[business_date − 7, business_date + 540]`); devuelve `created`, `updated` (deriva) y
  `drift`.
- Las operaciones de reserva ajustan `sold_units` en su propia transacción con `select_for_update()` en orden
  `(room_type_id, date)` (`adjust_inventory`); si faltan filas las materializa antes. Orden global de locks:
  Reservation → Stay → InventoryDay. Esto más la exclusión en BD garantizan que dos reservas simultáneas por
  la última unidad → una recibe 409 (test real con dos hilos y dos conexiones).
- `availability(*, property, checkin, checkout, room_type_ids=None) -> dict[UUID, int]`: mínimo sobre las
  noches desde `InventoryDay`, solo categorías activas; rango vacío → 0.
- `search_offers(*, property, checkin, checkout, adults, children=0, children_ages=None, channel="direct",
  promo_code=None, guest_is_foreign_non_resident=False) -> list[Offer]`: categorías activas donde cabe el grupo
  (privada: `1 ≤ adults ≤ max_adults`, `children ≤ max_children`, `adults+children ≤ max_occupancy`; dorm:
  `units_needed = adults + children`, niños solo si `max_children > 0`) × planes activos que incluyen la
  categoría y aplican al canal (`channels` vacío = todos; `"direct"` incluye planes no públicos, los demás
  canales solo `is_public`) → `quote` → se incluye si `restrictions_ok`, hay precio (sin `no_rate`) y
  `available ≥ units_needed`. `channel` = `direct | booking_engine | marketplace | <código OTA>`.
  `promo_code` se pasa al quote (un promo inválido solo agrega el aviso `promo_invalid`).

### Reservas (`services/reservations.py`)

- `create_reservation(req, *, actor=None, source_label=None) -> Reservation` — atómico: upsert del titular y
  ocupantes (`guests.upsert_guest`), valida grupo, custom values, categoría/plan activos de la propiedad,
  capacidad, fechas, habitación/cama pedida; toma inventario (409 salvo `allow_overbooking` → alerta
  `overbooking` crítica); cotiza cada estadía con `rates.quote` (o usa `nightly_rates` del canal); si
  `enforce_restrictions` (default; OTA: `False`): restricciones → `RestrictionError`, sin precio → `no_rate`,
  promo inválido → `promo_invalid`. Crea Reservation (código `HT-XXXXXX` único con reintento), Stays,
  asignación pedida, folio (`finance.get_or_create_folio`), snapshot de la política del plan de la **primera**
  estadía (el derivado sin política hereda la del padre), `hold_expires_at = now + hold_minutes` si es
  tentativa. Audita `bookings.reservation_created`; emite `reservation_created` e `inventory_changed`.
  - `source_label`: una fuente de auditoría (`user, automation, ai, channel, guest, system, api`) o, si no,
    la etiqueta del actor (p. ej. `"BookSim"`). Sin él: `ota → channel`, `marketplace/booking_engine →
    guest`, `api → api`, resto `user`. C9 debe pasar `source_label="ai"`; C3 `"channel"` (o el nombre del canal).
- `modify_stay(stay, *, checkin=None, checkout=None, room_type=None, rate_plan=None, adults=None,
  children=None, reprice=True, actor=None) -> Stay` — libera y toma inventario en una transacción (409 si falta
  unidad); restricciones **no** se aplican (cambio del staff/canal). Precio: `reprice=True` recotiza todas
  las noches (con el promo de la reserva), `False` conserva el precio pactado de las noches que quedan y cotiza
  solo las nuevas; las noches con cargo `room` publicado conservan siempre su monto. Habitación: se conserva
  si sigue libre y sin bloqueo y la categoría no cambia (o pasa a ser la de la habitación, p. ej. un upgrade
  que se queda con la suite); si no, queda sin asignar (`room_assigned` con la anterior). En casa: no cambia
  llegada ni categoría (salvo a la de su habitación), no sale antes de `business_date` y conserva la
  habitación (si no, 409). Un nuevo plan en la primera estadía refresca `cancellation_policy_snapshot`.
  Actualiza fechas/huéspedes/total de la reserva; audita `bookings.stay_modified`; emite
  `reservation_updated(changes=…, stay=…)` e `inventory_changed`.
- `preview_modify_stay(stay, **changes) -> dict` — mismo cálculo en una transacción que se revierte (sin
  auditoría ni señales). Útil para C1/C13/C5 antes de confirmar.
- `cancel_reservation(reservation, *, reason, waive_fee=False, actor=None, source="user") -> Reservation` —
  solo tentativa/confirmada; penalidad desde el snapshot (`policies.cancellation_fee`: tentativa o sin
  política → 0; no reembolsable → total; gratis hasta `checkin_date` a la `check_in_time` de la propiedad en
  su zona horaria − `free_until_hours_before`; después `first_night` (primera noche de cada estadía, con IVA),
  `percent` (del total) o `full`); `waive_fee` → 0 (el permiso lo valida la API). Si fee > 0 →
  `finance.post_charge(kind="cancellation_fee")` sin IVA. Libera inventario, estadías y reserva `cancelled`
  (la habitación queda registrada como historia pero ya no bloquea). `source` va a la auditoría y al cargo.
  Emite `reservation_cancelled` e `inventory_changed`.
- `confirm_reservation(reservation, *, actor=None, source="user")` — tentativa → confirmada (y sus estadías),
  limpia la retención; `reservation_updated(changes={"status": ("tentative", "confirmed")})`.
- `update_reservation(reservation, data, *, actor=None, source="user")` — campos libres del PATCH;
  `reservation_updated(changes=…)`.
- `assign_room(stay, room, *, bed=None, actor=None, force=False) -> Stay` — valida propiedad, habitación
  activa, no mezclar dorm/privada, categoría (otra → `force`: el precio y la categoría reservada no cambian,
  la unidad de inventario se mueve y la categoría destino debe tener unidad libre), bloqueo (409
  `room_blocked`), exclusión en BD → 409 `no_availability`. Audita `bookings.room_assigned` **reversible**
  (`undo_data = {stay_id, old_room_id, old_bed_id}`; el undo genérico de C12 funciona:
  `POST /api/v1/control/audit/{id}/undo/`). Emite `room_assigned(stay, old_room)`. Mover a un huésped en
  casa deja la habitación anterior sucia.
- `unassign_room(stay, *, actor=None)` — solo pendientes; reversible (`bookings.room_unassigned`).
- `auto_assign_rooms(*, property, date_from, date_to, actor=None) -> AssignmentReport` — estadías
  tentativas/confirmadas sin habitación, sin `locked_room`, con llegada en `[date_from, date_to]` (inclusivo);
  nunca mueve asignaciones ni huéspedes en casa. Prioridad: VIP → grupos (un `ReservationGroup` o una reserva
  con varias estadías) → estadías más largas → llegada. Preferencias: (a) limpia/inspeccionada si llega hoy,
  (b) habitaciones **conectadas** (`Room.connecting_rooms`) con las que el grupo ya tiene, luego el mismo piso
  del grupo (dorm: el mismo cuarto), (c) menor fragmentación (hueco de 0 noches antes/después), (d) orden.
  Alerta `unassigned_arrivals` si quedan llegadas de hoy sin habitación (se resuelve sola). Un run por
  propiedad a la vez (advisory lock).
- `check_in(stay, *, actor=None, force=False) -> Stay` — confirmada (tentativa con `force`: además confirma
  las otras estadías de la reserva); `checkin_date ≤ business_date` (antes → `force`; estadía ya terminada →
  `force`, para registrar historia); sin habitación → auto-asigna la mejor (limpias primero; sin ninguna →
  409); habitación `clean`/`inspected` o `RoomNotReadyError` (salvo `force`). Refresca la exención de IVA de
  las noches no cobradas con los datos actuales del titular (p. ej. el pasaporte tomado en recepción). Reserva
  → `checked_in`; emite `stay_checked_in`.
- `check_out(stay, *, actor=None, force=False) -> Stay` — solo en casa; salida anticipada: `checkout_date =
  business_date` (mínimo una noche), libera noches futuras, `reservation_updated`; `post_room_charges(until_date
  =checkout)`; `finance.reservation_balance > 0` → `BalanceDueError(amount)` salvo `force` (si falla no queda
  nada); habitación → `dirty` (`set_housekeeping_status(source="automation")`); reserva `checked_out` cuando
  ya no quedan estadías activas. Al commit: `stay_checked_out` **antes** de `room_status_changed`. Si libera
  noches desde hoy (sale el día de llegada) emite `inventory_changed`.
- `mark_no_show(reservation, *, actor=None, source="automation") -> Reservation` — confirmada con
  `checkin_date < business_date`; libera todas las noches; penalidad (`policies.no_show_fee`: no
  reembolsable → total, si no el tipo de la política, sin política → primera noche) como cargo
  `cancellation_fee` y en `cancellation_fee`; emite `reservation_no_show` e `inventory_changed`.
- `add_occupant(stay, guest_or_GuestInput, *, actor=None) -> Guest` / `remove_occupant(stay, guest, *,
  actor=None)`.

### Cargos (`services/charges.py`)

- `post_room_charges(stay, *, until_date, actor=None, source="automation") -> list[Charge]` — un cargo `room`
  por noche `< until_date` sin cargo `room` no anulado (una noche anulada se vuelve a publicar); canceladas y
  no-show no reciben nada; va al folio guest de la reserva; `amount` = neto de la noche, `tax` = IVA de
  alojamiento, `tax_exempt` = el titular es extranjero no residente (hoy), `night_date` = `business_date` =
  la noche. Idempotente. Si el cargo publicado difiere de la noche (cambió la exención, redondeo) la noche, la
  estadía y la reserva siguen al cargo: **Σ cargos room = total de la estadía**. C1 (auditoría nocturna) la
  llama con `until_date = business_date + 1` para los huéspedes en casa.

### `Stay.nightly_rates` y totales (fórmula)

Cada noche: `{"date", "amount", "net", "tax"}` (strings). `precio` = `NightPrice.total` del quote (con extras
de ocupación y promo) o el `amount` del canal. Impuesto de alojamiento = primer `Tax` activo `applies_to`
room/all por código (el mismo que publica `post_room_charges`):
- sin impuesto, o exento (extranjero no residente y `exempt_foreign_non_residents`): `net = precio, tax = 0`;
- no incluido: `net = precio`, `tax = quantize(net × rate / 100)`;
- incluido: `net = quantize(precio / (1 + rate/100))`, `tax = quantize(net × rate / 100)`;
- `amount = net + tax`; `Stay.total_amount = Σ amount`; `Reservation.total_amount = Σ stays` (incluye
  canceladas: para saldos usar `finance.reservation_balance`, que suma solo estadías facturables).

El IVA se redondea por noche igual que `finance.post_charge`, así Σ cargos = total (puede diferir en pesos del
`Quote.total`, que redondea el IVA sobre el subtotal). Un solo impuesto de alojamiento por noche.

### Consumidos

`rates.services.quote.quote` (y `Quote.to_dict()`), `finance.services` (`get_or_create_folio`, `post_charge`,
`reservation_balance`), `guests.services.upsert_guest`, `inventory.services.set_housekeeping_status` y
`validate_custom_values`, `core` (`audit`, `alerts`, `signals`, `tokens`, `money`, `dates`).

---

## Señales emitidas / escuchadas

Todas con `core.signals.send_on_commit` (solo tras el commit; `send_robust`). Los receivers reciben
`sender=None` + kwargs; **acepten `**kwargs`** (hay kwargs extra).

| Señal | kwargs | La emite |
|---|---|---|
| `reservation_created` | `reservation` | `create_reservation` |
| `reservation_updated` | `reservation`, `changes: {campo: (antes, después)}`, a veces `stay` | `modify_stay` (claves `checkin_date`, `checkout_date`, `adults`, `children`, `total_amount`, `cancellation_policy` y `stay.<campo>`: `checkin_date, checkout_date, room_type_id, rate_plan_id, room_id, bed_id, adults, children, total_amount`), `confirm_reservation` (`{"status": ("tentative", "confirmed")}`), `update_reservation` (campos libres), salida anticipada en `check_out` |
| `reservation_cancelled` | `reservation` | `cancel_reservation` (también la automatización de tentativas vencidas) |
| `reservation_no_show` | `reservation` | `mark_no_show` |
| `stay_checked_in` | `stay` | `check_in` |
| `stay_checked_out` | `stay` | `check_out` (antes que el `room_status_changed` de la habitación) |
| `room_assigned` | `stay`, `old_room` (Room o None) | `assign_room`, `unassign_room` (stay sin room), `modify_stay` cuando pierde la habitación, undo |
| `inventory_changed` | `property`, `room_type_ids`, `start`, `end`, **`origin="bookings"`** | crear, modificar, cancelar, no-show, cambio de categoría al asignar/desasignar, salida anticipada o el día de llegada |
| `room_status_changed` | (la emite `inventory.set_housekeeping_status`) | check-out y movimiento de huésped en casa (→ `dirty`) |

Escuchadas (`receivers.py`):
- `inventory_changed` → `rebuild_inventory` del rango (`start/end` None = horizonte; `room_type_ids` vacío =
  todas). Ignora los eventos con `origin="bookings"` (ya ajustados en su transacción). Así los bloqueos,
  altas/bajas de habitaciones y camas (B1, C2) mueven la disponibilidad.
- `payment_received` → si el pago está aprobado y la reserva es tentativa → `confirm_reservation(source=
  "system")`. Si la reserva ya estaba cancelada: pagar lo que aún debe (su penalidad) es el flujo normal y no
  alerta; solo si el pago deja **saldo a favor** del huésped (`reservation_balance < 0`, p. ej. una retención
  que venció antes de que se aprobara el pago en línea) → alerta `payment_after_cancellation` con `credit`
  (reembolsar o rehacer la reserva).

Undo registrado: `bookings.room_assigned` y `bookings.room_unassigned` (`audit.register_undo`).

Acciones de auditoría (`AuditEvent.action`): `bookings.reservation_created`, `bookings.reservation_updated`,
`bookings.reservation_confirmed`, `bookings.reservation_cancelled`, `bookings.reservation_no_show`,
`bookings.stay_modified`, `bookings.room_assigned` (reversible), `bookings.room_unassigned` (reversible),
`bookings.stay_checked_in`, `bookings.stay_checked_out`, `bookings.occupant_added`,
`bookings.occupant_removed`, `bookings.inventory_rebuilt`.

Alertas (`Alert.kind` · `dedupe_key`): `overbooking` · `bookings:overbooking:<reservation_id>` (crítica);
`unassigned_arrivals` · `bookings:unassigned_arrivals:<YYYY-MM-DD>`; `inventory_drift` ·
`bookings:inventory_drift`; `payment_after_cancellation` · `bookings:payment_after_cancellation:<payment_id>`
(`data`: `reservation_id`, `payment_id`, `credit` = saldo a favor en string).

## Automatizaciones registradas

| Código | Horario | Qué hace |
|---|---|---|
| `bookings.auto_assign_rooms` | diario 06:00 | `auto_assign_rooms` de hoy a hoy + `days_ahead` (param, default 1); `partial` si quedan sin asignar |
| `bookings.release_expired_tentative` | cada 15 min | cancela sin penalidad (`source="automation"`) las tentativas con `hold_expires_at` vencido |
| `bookings.inventory_reconcile` | diario 04:00 | `rebuild_inventory` del horizonte (crea las filas nuevas del horizonte); si corrigió deriva → alerta `inventory_drift` (se resuelve sola cuando no hay) |

## Proveedores de integración registrados

Ninguno.

## Extensiones de frontend exportadas

No aplica (tarea solo backend). C1/C13 consumen la API de arriba.

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

1. **B-INT / `config/settings.py`** — `manage.py spectacular --validate --fail-on-warn` falla ahora por
   colisiones de nombres de enums entre apps (campos `status`, `source`, `kind` con opciones distintas en
   bookings, finance, inventory, guests). Agregar a `SPECTACULAR_SETTINGS`:
   ```python
   "ENUM_NAME_OVERRIDES": {
       "BookingStatusEnum": "apps.bookings.models.BookingStatus",
       "ReservationSourceEnum": "apps.bookings.models.Reservation.Source",
       "RoomTypeKindEnum": "apps.inventory.models.RoomType.Kind",
       "RoomBlockKindEnum": "apps.inventory.models.RoomBlock.Kind",
       "GuestDocumentKindEnum": "apps.guests.models.GuestDocument.Kind",
   },
   ```
   **Verificado** por el verificador de B2b con el código de todas las apps al 2026-09-26 (settings temporal
   fuera del repo que solo agrega este bloque): `manage.py spectacular --validate --fail-on-warn` → exit 0 (sin
   el bloque: 5 warnings de colisión `kind`/`status`/`source`, 0 errores). Si otra app agrega enums nuevos que
   choquen, sumar su entrada.
2. **Fase C, receivers**: el seed de bookings emite al commit las señales de **cada** operación histórica
   (miles de `reservation_created`, `stay_checked_in/out`, `room_status_changed`…). C2 (tareas de limpieza),
   C6 (emails de confirmación), C11 (comisiones) y C3 (ARI) deben ignorar eventos históricos (p. ej.
   `stay.checkout_date < property.business_date - 1`, o reservas con `created_at` antiguo) o limpiar lo que
   generen en su propio seed; si no, el demo amanece con cientos de tareas/emails.
3. **C1 (auditoría nocturna)**: usar `mark_no_show(source="automation")` para llegadas `< nueva fecha` y
   `post_room_charges(stay, until_date=business_date + 1)` para `checked_in`; el receiver de B4 cierra folios.
4. **C3**: nueva OTA → `create_reservation(ReservationRequest(source="ota", channel_code=…, external_id=…,
   enforce_restrictions=False, allow_overbooking=True, stays=[StayRequest(…, nightly_rates=[…])]),
   source_label="channel")`; modificación → `modify_stay`; cancelación → `cancel_reservation(waive_fee=True,
   source="channel")`. Para ARI escuchar `inventory_changed` (acotar a fechas ≥ hoy).
5. **C4**: ofertas `search_offers(channel="marketplace" | "booking_engine")`; reserva con pago → `status=
   "tentative"` (+`hold_minutes`) y el `payment_received` aprobado la confirma solo.
6. **C5**: vista previa de penalidad `policies.cancellation_fee(reservation).as_dict(currency)`, cancelar con
   `source="guest"`, modificar con `preview_modify_stay` + `modify_stay(reprice=True)` (restricciones de tarifa
   no se aplican en `modify_stay`; si el portal las quiere, validar antes con `search_offers`/`quote`).

## Seed (`apps/bookings/seed.py`)

Corre después de inventory, rates y guests (usa `ctx.data["guests"][<org>]`; sin datos, crea 18 huéspedes
propios). Por propiedad con categorías, habitaciones y plan: materializa `InventoryDay` de la ventana, y crea
reservas **por los servicios** de −60 a +90 días, unidad por unidad (habitación o cama) sin choques,
ocupación ≈ 55–85 % (más alta viernes/sábado y dic–ene), estancias de 1–7 noches (dorm 1–5), fuentes
mezcladas (recepción, teléfono, email, walk-in, booking engine, marketplace y OTA `booksim`/`airsim` con
`external_id` y sin restricciones), planes FLEX/NR/BB, 1–2 grupos, grupos de amigos en dorms, VIPs, `created_at`
con anticipación realista. Estados según la fecha: pasadas → `check_in`/`check_out` con force (todas las noches
cobradas), algunas no-show/canceladas; en curso → en casa con cargos hasta ayer; hoy: ≥ 2 llegadas (una en
habitación libre y lista, otra sin asignar; si el hotel está lleno una salida pasa a hoy) y salidas de hoy;
futuras → confirmadas, algunas tentativas (retención de 2–4 días) y canceladas. Estados de habitación finales
coherentes con hoy. Los pagos los pone el seed de finance. Idempotente (propiedad con reservas → se omite).
Intentos que chocan con restricciones de tarifa (p. ej. min LOS de temporada) se omiten y se registran.
`ctx.data["bookings"][<propiedad>] = {"reservations", "arrivals_today", "in_house", "departures_today"}` (ids).

Prueba en seco sobre la BD de desarrollo (inventario B1 + huéspedes B3 reales + seed de rates de B2a, todo en una
transacción revertida): Aurora 743 reservas, Andino MDE 1251, Hostel 1307 (1837 estadías de cama); deriva de
inventario 0; llegadas/salidas de hoy presentes. **Tarda ≈ 6–8 min** (≈ 0,1–0,14 s por reserva: cada una
pasa por los servicios con auditoría; el verificador midió 342 s para bookings + 161 s para finance en una BD
aislada). B-INT: correr `make seed` en segundo plano o con timeout amplio (la cadena completa ≈ 9 min).

## Limitaciones conocidas / pendientes

- Una sola política por reserva (la del plan de la primera estadía); reservas multi-estadía con planes
  distintos usan esa.
- No se cancela una estadía suelta de una reserva multi-estadía, ni una reserva parcialmente en casa.
- `modify_stay` no aplica restricciones de tarifa (min LOS, CTA…); las valida quien vende (ofertas/quote).
- Un solo impuesto de alojamiento por noche (el primer `Tax` room/all activo por código).
- El receiver de `inventory_changed` recalcula en el mismo proceso (tras el commit); un evento sin rango
  recalcula ~550 días por categoría (medido: 0,09 s para las 3 categorías de Andino MDE sin reservas). Si
  con muchas reservas llegara a molestar, moverlo a Celery en D.
- `GET availability/offers/calendar` pueden materializar filas faltantes de `InventoryDay` (escritura en GET).
- Filas de `InventoryDay` más allá del horizonte (+540 días; existen solo si alguien reservó tan lejos): un
  `inventory_changed` sin rango o la conciliación diaria recalculan solo el horizonte, así que un cambio de
  habitaciones no las corrige hasta que la fecha entra al horizonte (la conciliación lo arregla y alerta
  `inventory_drift`).
- El seed tarda ≈ 6–8 min con el demo completo (ver arriba).

## Verificación

- `docker compose run --rm -e TEST_DB_NAME=test_b2b backend pytest apps/bookings -q` → **361 passed**
  (≈ 2 min; el seed se prueba una sola vez por módulo dentro de una transacción revertida). También verdes con
  mi código: `apps/finance`, `apps/rates`, `apps/guests`, `apps/core` (1273 passed) e `apps/inventory`.
  Incluye los obligatorios del plan: disponibilidad decrementa y
  restaura; **concurrencia real** (`transaction=True`, dos hilos por la última unidad → uno 409, con filas
  existentes y sin materializar); exclusión (`assign_room` doble → 409); camas de dorm; min LOS →
  `RestrictionError`; OTA sin restricciones con disponibilidad y overbooking con alerta; modify recotiza y
  mueve inventario; cancelación (ventana gratis, primera noche, no reembolsable, waive); no-show libera y
  cobra; check-in sucia → `RoomNotReadyError` (force OK) y auto-asigna; check-out publica cargos, exige saldo
  y marca sucia; salida anticipada; auto-assign (limpias, locked, piso, conectadas, huecos); `payment_received`
  confirma; tentativas vencidas; `rebuild` = incremental tras 120 operaciones aleatorias (2 semillas); bloqueo
  vía receiver; señales on_commit; API (filtros, 409/400 con code, permisos, aislamiento); calendario (forma
  exacta); seed. Además `test_api_permissions.py` recorre las 29 combinaciones método/ruta de la API: permiso
  exacto (housekeeping 403 con el código, contabilidad solo lee) y aislamiento entre organizaciones (404).
- `apps/core/tests/test_contracts.py` (142), `test_domain_contract.py` y `test_migrations.py` verdes; `ruff
  check` y `ruff format --check` limpios en `apps/bookings`; `manage.py check` sin problemas;
  `makemigrations --check` sin cambios.
- Smoke en el servidor real (8010): login `owner@casaaurora.co` → `GET reservations/`, `calendar/`,
  `availability/`, `offers/`, `groups/` → 200.

### Pasada del verificador (2026-09-26/27)

Revisé contra el plan (tarea B2b: Inventario, Servicios, API, tests obligatorios, Seed, Aceptación = spec §5 B2b),
el spec §4.2/§5 y estas notas. Todo lo que pide el plan está implementado y cada test obligatorio existe, prueba
lo que dice (sin tests vacíos) y pasa. Corregí 4 cosas; cada corrección con su test visto primero en rojo:

1. **Alerta falsa `payment_after_cancellation`.** El receiver de `payment_received` alertaba "reembólsalo" ante
   cualquier pago aprobado en una reserva cancelada, incluido el pago de su propia penalidad (el flujo normal).
   La cadena completa de seeds (inventory → rates → guests → bookings → finance) dejaba **57 alertas falsas**
   abiertas, porque el seed de B4 cobra la penalidad de la mitad de las canceladas. Ahora solo alerta si el pago
   deja saldo a favor del huésped (`reservation_balance < 0`) y guarda ese `credit` en `data`. Con la cadena
   repetida: 0 alertas abiertas. Tests: `test_receivers_automations.py::TestPaymentReceived` (pagar la
   penalidad no alerta; pagar de más sí, con `credit`).
2. **N+1 en `room-options`, check-in y auto-asignación.** `assignment.load_units` hacía una consulta de camas
   por cada dormitorio. Ahora usa `prefetch_related`. Nuevo `test_api_queries.py`: las consultas de
   `reservations/`, `calendar/`, `groups/` y `room-options/` no crecen con las filas (las 3 primeras ya
   estaban bien).
3. **`POST inventory/rebuild/` no era atómico.** El recálculo y su auditoría iban en transacciones separadas.
   Ahora van juntos. Test: `test_api_misc.py::TestInventoryRebuild::test_the_rebuild_and_its_audit_are_one_transaction`.
4. **`ruff check apps/bookings` fallaba** con 10 líneas de más de 110 caracteres, aunque el reporte decía
   "All checks passed". Ya queda limpio. También quité el encabezado obsoleto "not implemented yet" de
   `services/reservations.py`.

Revisado sin hallazgos:
- **Seguridad**: todas las vistas usan `PropertyScopedMixin`/`PropertyScopedAPIView` y filtran por
  `request.property`; los ids del cuerpo (categoría, plan, habitación, cama, grupo, huésped) se validan contra
  la propiedad u organización; los permisos adicionales (`waive_fee`, `overbook`, `checkout_with_balance`) se
  exigen. No se exponen secretos ni archivos de documentos.
- **Contratos**: firmas y tipos exactos.
- **Errores** `{detail, code}`: comprobado también por el proxy.
- **Transacciones** en todos los servicios y señales solo con `send_on_commit`.
- **Concurrencia**: orden de locks Reservation → Stay → InventoryDay; materialización insertada en orden
  global.

Evidencia (Docker Compose, `/home/breyner/Documents/new_project`):
- `pytest apps/bookings -q` (TEST_DB_NAME=test_b2bv) → **388 passed**.
- `pytest apps/core/tests/test_contracts.py test_domain_contract.py test_migrations.py` → **357 passed**.
- `pytest apps/finance apps/rates apps/inventory apps/guests apps/core` con este código → **1642 passed**.
- `ruff check` + `ruff format --check` (apps/bookings) limpios; `manage.py check` sin problemas;
  `makemigrations --check` → "No changes detected".
- **Cadena real de seeds en una BD de test aislada** (no toca la BD de desarrollo): inventory, rates, guests,
  bookings y finance del código actual.
  - Reservas: Aurora 755, Andino MDE 1241, Hostel 1346 (1840 estadías de cama).
  - Estados: todos presentes (checked_out, checked_in, confirmed, tentative, cancelled, no_show).
  - Fuentes: front_desk, phone, email, walk_in, booking_engine, marketplace y ota.
  - Inventario: `rebuild_inventory` sin deriva (0 filas corregidas) y 0 noches futuras sobrevendidas.
  - Operación de hoy:

    | Propiedad | Llegadas (sin asignar / listas) | Salidas | En casa |
    |---|---|---|---|
    | Aurora | 4 (2 / 2) | 3 | 17 |
    | Andino MDE | 5 (1 / 4) | 6 | 32 |
    | Hostel | 25 (8 / 13) | 25 | 36 |

  - Todos los huéspedes en casa tienen cobradas exactamente las noches hasta ayer.
  - 0 alertas abiertas.
  - Segunda corrida de bookings: 0 s y ninguna reserva nueva (idempotente).
  - Tiempos: bookings 342 s y finance 161 s.
- Smoke por el proxy de Vite (5173) con `owner@casaaurora.co`: `GET reservations/`, `calendar/`,
  `availability/`, `offers/`, `groups/` → 200; `POST reservations/` inválido → 400 `{detail, code, fields}`.
