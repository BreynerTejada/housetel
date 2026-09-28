# P3 — Reservas multi-habitación, grupos y cupos — integration notes

Estado: **completo en modo MVP** (backend + API + frontend + seed). No se escribieron ni corrieron tests (decisión
del usuario). Están implementados los 6 requisitos de P3:

1. Asistente multi-habitación.
2. Agregar y cancelar habitaciones en una reserva existente.
3. Grupos con lista, detalle y rooming list editable.
4. Cupos (allotments) con retención de inventario, pickup y liberación automática.
5. Check-in con 409 `room_occupied`.
6. Aterrizaje por rol y nombres en 2 líneas en Hoy móvil.

Esta sesión **retomó un intento previo interrumpido**. El backend estaba casi completo. En el frontend faltaban las
rutas, el menú, la página de detalle del grupo, el pickup desde el cupo y todo el i18n. Se revisó, se completó y se
corrigió (ver "Cambios de esta sesión").

Owner paths tocados: `backend/apps/bookings/**`, `backend/apps/frontdesk/**`, `frontend/src/features/frontdesk/**` y
esta nota. No toqué nada fuera de ellos ni `features/calendar`. Sin dependencias nuevas; `.env` intacto; sin commits.

**P-INT, lo imprescindible** (detalle en "Cambios requeridos"):
- reiniciar worker y beat, para que programen `bookings.release_group_blocks`;
- `seed_demo --reset` ya incluye los grupos de P3;
- el cambio 2 de P4 (`with_balance`) **ya está aplicado** aquí.

---

## Cómo probarlo en la UI

**Datos.** El seed de P3 (`apps/bookings/seed.py::seed_groups`) corre dentro del seed de bookings, así que
`seed_demo --reset` (P-INT) lo carga. Sobre un demo ya cargado, como la BD de desarrollo de hoy, que **aún no tiene
cupos**:

```bash
docker compose exec -T backend python manage.py seed_groups --dry-run   # en una transacción revertida
docker compose exec -T backend python manage.py seed_groups             # ~1 s, idempotente (por nombre de grupo)
```

Qué deja (fecha de negocio = F; los códigos de reserva salen al azar):

| Propiedad (usuario) | Grupo | Cupo | Pickup |
|---|---|---|---|
| Hotel Casa Aurora (`owner@casaaurora.co`) | **Hay Festival · Editorial Caribe** (contacto, notas) | hasta 6 Estándar (DBL; según disponibilidad), F+28 → F+31, se libera 7 días antes | 1–2 reservas del cupo; siempre queda ≥ 1 unidad apartada; 3 nombres en la rooming list |
| Casa Aurora | — | — | Reserva de **dos categorías** ("Familia: dos habitaciones…"), F+10, 3 noches, 2 adultos + 2 adultos y un niño |
| Andino Medellín (`owner@grupoandino.co`) | **Colombiamoda · Textiles del Valle** | hasta 8 de la categoría más libre, F+14, 3 noches | 2 reservas + un **segundo cupo ya liberado** con 1 habitación tomada (se ve rayado) |
| Andino Hostel Bogotá (`owner@grupoandino.co`) | **Intercambio Universidad de los Andes** | hasta 10 **camas** de dormitorio, F+9, 4 noches | 1 reserva de varias camas |

Los grupos del seed de B2b (**Boda Rodríguez · Pérez**, **Congreso Médico Andino**, sin cupos) siguen ahí. Clave de
todos los usuarios: `housetel123`.

| # | Dónde | Pasos | Resultado esperado |
|---|---|---|---|
| 1 | Menú **Operación → Grupos** (`/app/groups`; ⌘K "Ver grupos y cupos") | Abrir | Tarjeta por grupo: nombre y estado (**Próximo / En casa / Pasado**), contacto, fechas y noches, habitaciones y reservas, medidor **Tomado del cupo** (%, "N de M tomadas") o "Sin cupos", **Saldo**. Pestañas "Próximos y en casa / Pasados / Todos" en la URL (`?when=`), búsqueda por nombre |
| 2 | **Nuevo grupo** | Nombre, contacto (buscar o crear con `GuestPicker`), notas → **Crear grupo** | Toast y se abre su detalle vacío |
| 3 | Detalle **Hay Festival** (`/app/groups/<id>`) | Encabezado y cifras | Eyebrow "Grupo" y estado, fechas, contacto con email/teléfono, notas; acciones **Nueva reserva de grupo**, **Editar**, ⋯ (**Exportar rooming list (CSV)**, **Borrar grupo**). Cifras: Habitaciones, Tomado del cupo (medidor), Rooming list "n/N" (medidor) y Saldo del grupo |
| 4 | Sección **Cupos** | Revisar la tarjeta del cupo | "N habitaciones Estándar", fechas, chip **"Se libera en N días, el …"** (arena si es hoy, piedra si ya se liberó). Tira **noche por noche** tipo casillero de llaves: por noche una ranura por unidad, **llena** (color de la categoría) si está tomada, **punteada terracota** si sigue apartada y **rayada** si ya volvió a la venta. Si el cupo pasa de 8 unidades, una columna proporcional. Esta noche resaltada. Debajo: "x de N tomadas · %" y "n noches-habitación siguen apartadas" |
| 5 | **Nuevo cupo** | Categoría (con su número de habitaciones o camas), noches, habitaciones por noche (+/−), fecha de liberación (por defecto 7 días antes, nunca antes de hoy) → **Crear cupo** | La disponibilidad general baja en esas noches: en el asistente y en el calendario quedan menos. Si alguna noche no alcanza, sale 409 con la noche; quien tenga `bookings.overbook` ve "Apartar igual… (sobreventa)" |
| 6 | En un cupo: **Editar** | Bajar las unidades por debajo de lo ya tomado en alguna noche | El contador no baja de ese mínimo ("El grupo ya tomó N…"); subirlas sin disponibilidad → 409 |
| 7 | En un cupo: **Reservar desde el cupo** | Abre el asistente con `?group=&block=&checkin=&checkout=` | Paso 1 con el banner "Reserva del grupo · Desde el cupo de N × Estándar · fechas"; paso 2 solo con esa categoría y **"Quedan"** = lo apartado + lo libre (aunque el hotel esté lleno). Al crear, la estadía queda con el chip **"Del cupo"** y el pickup del cupo sube; la disponibilidad general **no cambia**. No aplica restricciones de tarifa (mínimo de noches, etc.) |
| 8 | En un cupo: **Liberar** | Confirmar | Toast "n noches-habitación vuelven a la venta"; la tira pasa a rayada y la disponibilidad general sube. Las reservas del grupo no cambian. **Borrar** (papelera) solo aparece si nadie tomó del cupo |
| 9 | **Rooming list** | Tocar "Agregar nombre" en una habitación, escribir "Ana María Pérez" → Enter | Se guarda en línea (✓), el chip "N sin nombre" baja. Esc cancela; al salir del campo también guarda. Escribir el **nombre del titular** lo vincula a él (no crea un homónimo). Tabla en escritorio y tarjetas en 375 px; habitación como llave (o "Sin habitación"), categoría y tarifa, fechas, reserva y titular, chip "Del cupo". **Exportar CSV** descarga `rooming-<grupo>.csv` (`;`, Excel) |
| 10 | **Reservas del grupo** | Revisar; ícono de desvincular en una fila | Código, estado, titular, fechas, habitaciones con sus categorías y saldo. Quitar del grupo pide confirmación. Una reserva con habitaciones **del cupo** no puede salir del grupo (mensaje del backend) |
| 11 | **Agregar reserva existente** | Buscar por código, nombre, email o teléfono → **Agregar** (o **Mover aquí** si es de otro grupo) | Se suma a la lista y a la rooming list |
| 12 | **Nueva reserva del grupo** / **Nueva reserva de grupo** (lista) | Asistente con `?group=` (fechas del grupo) o `?group_mode=1` | Paso 1: banner del grupo existente, o interruptor **"Reserva de grupo"** con el nombre del grupo nuevo (obligatorio si está activo) |
| 13 | Asistente multi-habitación (`/app/reservations/new`) | 5 adultos + 1 niño con edad → Continuar | Paso 2 **"Habitaciones y tarifas"**: por categoría "Hasta N personas · Quedan N"; en cada tarifa el precio **por habitación** para su ocupación estándar, por noche y un selector **− n +** (se pueden mezclar categorías y tarifas). Barra "5 adultos, 1 niño · 2 habitaciones elegidas · Caben hasta 6 personas" |
| 14 | Mismo paso | Elegir 2 Estándar + 1 Suite | **"¿Quién duerme en cada habitación?"**: reparto automático (un adulto por habitación, luego hasta la ocupación estándar, luego los niños) con − / + de adultos y niños por habitación, precio exacto de cada una (recotizado con sus huéspedes) y **Repartir automáticamente**. Errores claros si alguien queda sin cama, si una habitación no tiene adulto o supera su capacidad |
| 15 | Resumen lateral | Revisar | "3 habitaciones": cada una con categoría, tarifa, huéspedes y precio; total. Con grupo: chip del grupo (y "Desde el cupo") |
| 16 | Titular extranjero | En el paso Huésped elegir un titular extranjero no residente (o crear uno con nacionalidad y residencia EE. UU.) | Ofertas y resumen se **recotizan sin IVA** solos, sin perder las habitaciones elegidas |
| 17 | Pago | Paso Garantía | El monto sugerido suma el depósito de cada tarifa ("Cada tarifa pide su propio depósito" si difieren) |
| 18 | Crear | **Crear reserva** | Toast "Reserva HT-… creada · 3 habitaciones" → detalle con **3 habitaciones**. Walk-in: asigna una habitación limpia y libre a cada estadía y hace check-in de todas |
| 19 | Dormitorio (Andino Hostel) | Asistente con 3 adultos | La cantidad cuenta **camas** ("Camas de …", "Quedan N camas", precio por cama); cada cama = un huésped (con opción Adulto/Niño si el dormitorio admite niños) |
| 20 | Detalle de reserva | Pestaña Resumen | Encabezado "N habitaciones" + **Agregar habitación**; en cada habitación pendiente, **Cancelar habitación** (solo si hay más de una activa) |
| 21 | **Agregar habitación** | Fechas (las de la reserva por defecto), categoría y tarifa, huéspedes → total exacto → **Agregar a la reserva** | 201 y la tarjeta nueva aparece; total y saldo suben. Si la reserva es de un grupo con cupo abierto: selector **"¿De dónde sale?"** (disponibilidad general o el cupo). En dormitorio agrega una cama por huésped |
| 22 | **Cancelar habitación** | Motivo; ver la penalidad | Vista previa **proporcional** (la política de la reserva aplicada solo a esa habitación: gratis en ventana, primera noche, %, total o no reembolsable). Condonar exige `bookings.waive_fee` y escribir el código. Si es la **última activa**, avisa que se cancela toda la reserva y el botón dice "Cancelar reserva" |
| 23 | Check-in con la habitación aún ocupada | Llegada de hoy asignada a una habitación cuyo huésped sale hoy y no ha hecho check-out → **Check-in** | El diálogo ya lo advertía; ahora también el backend responde **409 `room_occupied`** ("La habitación 107 sigue ocupada: … aún no hace check-out"). El diálogo lo muestra como advertencia y "Hacer check-in igual" lo fuerza |
| 24 | Aterrizaje por rol | Entrar como `limpieza@`, `mantenimiento@`, `contabilidad@casaaurora.co` | `/app` los lleva a `/app/housekeeping/mine`, `/app/maintenance` y **`/app/reports`** (antes Calendario). El supervisor de limpieza sigue en `/app/housekeeping`; otros roles sin Hoy, al primer ítem de su menú |
| 25 | Hoy en 375 px | Pestañas Llegadas / Salidas | Los nombres largos ocupan **hasta 2 líneas** antes de cortarse; los botones Check-in/out quedan como íconos (con `aria-label`) |
| 26 | Automatización | `/app/settings/automations` → Reservas → **Liberar cupos de grupos** → Ejecutar ahora | "omitida: ningún cupo llega hoy…" o "N cupo(s) liberado(s): M noches-habitación vuelven a la venta" |
| 27 | Idioma, tema, móvil | EN / oscuro / 375 px | Todo traducido (ES/EN con paridad, 684 claves); sin scroll horizontal |

---

## API implementada

Base `/api/v1/bookings/` (sesión + `X-Property-Id`, reglas de tenancy de A1). Dinero en strings con 2 decimales.

| Método y path | Permiso | Qué hace |
|---|---|---|
| `GET room-offers/?checkin&checkout[&promo_code][&foreign=1][&block=<id>]` | `bookings.view` | Ofertas **por habitación** para el asistente: categoría con unidad libre × planes directos, cotizadas para 1 unidad a su ocupación estándar |
| `POST reservations/quote/` | `bookings.view` | Cotiza varias estadías como lo haría la reserva (no guarda ni retiene nada) |
| `POST reservations/` | `bookings.manage` | Igual que antes + N estadías, `group_name`, `stays[].group_block_id` |
| `POST reservations/{id}/stays/` | `bookings.manage` (+`overbook`) | Agrega una habitación (o camas) a una reserva tentativa, confirmada o en casa → 201 detalle |
| `GET stays/{id}/cancel-preview/` | `bookings.view` | Penalidad proporcional y si cancela o finaliza la reserva |
| `POST stays/{id}/cancel/` | `bookings.cancel` (+`waive_fee`) | Cancela una habitación → detalle |
| `POST stays/{id}/rooming/` | `bookings.manage` | Nombre del huésped de esa habitación → fila de la rooming list |
| `GET groups/?when=upcoming\|past\|all&q=` | `bookings.view` | Lista paginada con `figures` |
| `GET groups/{id}/` | `bookings.view` | Grupo + `blocks` + `reservations` + `rooming` |
| `POST/PATCH/DELETE groups/…` | `bookings.manage` | CRUD (auditado); borrar libera sus cupos y deja las reservas sin grupo |
| `POST groups/{id}/blocks/` | `bookings.manage` (+`overbook`) | Nuevo cupo → 201 |
| `GET/PATCH/DELETE blocks/{id}/` · `POST blocks/{id}/release/` | view / manage | Ver, editar, borrar (sin pickups) o liberar un cupo |
| `GET /api/v1/frontdesk/groups/{id}/rooming-list/?lang=es\|en` | `bookings.view` | Rooming list en CSV (`;`, UTF-8 con BOM) |

### `GET room-offers/?checkin=2026-11-07&checkout=2026-11-10`

Misma forma que `offers/` (B2b), con `room_type.base_occupancy`, `units_needed = 1` y `total` = la cotización de una
unidad. Dormitorio: 1 cama = 1 adulto. `available_units` = cuántas se pueden agregar (el asistente descuenta las ya
elegidas por categoría). Con `block`: solo la categoría del cupo, `available_units` = disponibilidad general + lo que
el cupo aún aparta en cada noche (mínimo sobre las noches) y sin restricciones de tarifa. Se excluyen los planes sin
precio o con restricciones que fallen (sin `block`).

```json
[{"room_type_id": "801a…", "rate_plan_id": "1207…",
  "room_type": {"id": "801a…", "code": "DBL", "name": {"es": "Estándar", "en": "Standard"}, "kind": "private",
                "color": "#4E6C88", "max_adults": 2, "max_children": 1, "max_occupancy": 3, "base_occupancy": 2},
  "rate_plan": {"id": "1207…", "code": "NR", "name": {"es": "No reembolsable", "en": "Non-refundable"},
                "meal_plan": "room_only", "is_public": true, "deposit_percent": "0.00", "cancellation_policy": {…}},
  "available_units": 3, "units_needed": 1,
  "quote": {"adults": 2, "children": 0, "nights": [{"date": "2026-11-07", "total": "323840.00", …}, …],
            "subtotal": "887040.00", "taxes": [{"code": "IVA", "amount": "168538.00", "exempt": false, …}],
            "total": "1055578.00", "currency": "COP", "restrictions_ok": true, "violations": []},
  "total": "1055578.00"}]
```

### `POST reservations/quote/`

`{"stays": [<StayRequest>…], "promo_code": "", "foreign": false}`. Cada estadía tiene la misma forma que en
`POST reservations/` (incluye `group_block_id`, que solo se valida). Mismos 400 de validación que crear (categoría,
plan, capacidad, fechas, edades); la disponibilidad no se revisa aquí.

```json
{"currency": "COP", "total": "2441024.00",
 "stays": [{"index": 0, "room_type_id": "801a…", "rate_plan_id": "1207…", "checkin": "2026-11-07",
            "checkout": "2026-11-10", "nights": 3, "adults": 2, "children": 0, "units": 1,
            "total": "1055578.00", "per_night": "351859.00", "restrictions_ok": true, "violations": []},
           {"index": 1, "…": "…", "adults": 1, "units": 1, "total": "1385446.00", "per_night": "461815.00"}]}
```

`units` > 1 = estadía de dormitorio por varias camas (una por huésped). Con `foreign: true` se cotiza sin IVA de
alojamiento (extranjero no residente).

### `POST reservations/` (ampliado)

```json
{"booker": {…} | "booker_id": "…",
 "stays": [{"room_type_id": "…", "rate_plan_id": "…", "checkin": "…", "checkout": "…", "adults": 2, "children": 1,
            "children_ages": [7]},
           {"room_type_id": "…", "rate_plan_id": "…", "checkin": "…", "checkout": "…", "adults": 1,
            "group_block_id": "<cupo>|null"}],
 "group_id": "<grupo existente>|null",
 "group_name": "Boda Torres · Díaz",
 "enforce_restrictions": false,
 "…": "resto igual a B2b"}
```

- `group_name` crea el grupo en la misma transacción (el titular queda como contacto; audita `bookings.group_created`).
  Con `group_id` a la vez → 400 `validation_error`.
- `group_block_id` = pickup del cupo:
  - la estadía toma las unidades apartadas (la disponibilidad general no cambia);
  - las noches fuera del cupo necesitan disponibilidad general;
  - la reserva queda en el grupo del cupo (`group_id` de otro grupo → 400 `invalid_group`);
  - errores: cupo liberado → 409 `block_released`; cupo de otra categoría → 400 `category_mismatch`; cupo de otra
    propiedad → 400 `invalid_block`;
  - sin precio → 400 `no_rate`, aunque `enforce_restrictions` sea `false`.
- El asistente manda `enforce_restrictions: false` solo en los pickups.

### `POST reservations/{id}/stays/` — agregar habitación

Cuerpo = un `StayRequest` (+ `group_block_id`, `allow_overbooking`, `enforce_restrictions` (default `false`)); `checkin`
y `checkout` por defecto los de la reserva:

```json
{"room_type_id": "…", "rate_plan_id": "…", "adults": 2, "children": 0, "children_ages": [],
 "checkin": "2026-11-07", "checkout": "2026-11-10", "group_block_id": null}
```

- Validación y precio como al crear. Usa el código promocional de la reserva y la exención de IVA del titular.
- Sin precio → 400 `no_rate`. Sin unidad → 409 `no_availability` + `shortfalls`.
- La llegada no puede ser antes de la fecha de negocio (400 `invalid_dates`).
- Reservas canceladas, no-show o finalizadas → 409 `invalid_state`.
- La estadía nueva queda `tentative` si la reserva es tentativa; si no, `confirmed` (también en reservas en casa:
  espera su propio check-in).
- Fechas, huéspedes y total de la reserva se recalculan.
- Emite `reservation_updated` (con `stay` y `changes["stays"] = (antes, después)`) e `inventory_changed`.
- Responde **201** con el detalle de la reserva.

### Cancelar una habitación

- `GET stays/{id}/cancel-preview/`:

  ```json
  {"fee": "1055578.00", "currency": "COP", "reason": "non_refundable", "free_until": null, "non_refundable": true,
   "policy": {…snapshot…}, "stay_total": "1055578.00", "cancels_reservation": false, "ends_reservation": false}
  ```

  - `reason` usa los mismos valores de `cancel-preview/` de la reserva.
  - `cancels_reservation`: es la última habitación activa de una reserva que aún no llega (se cancela toda, con la
    penalidad de la reserva).
  - `ends_reservation`: las demás ya salieron (la reserva queda `checked_out`).
- `POST stays/{id}/cancel/` `{"reason": "…", "waive_fee": false, "confirm": true}` → detalle:
  - sin `confirm: true` → 400 `confirmation_required`;
  - `waive_fee` exige `bookings.waive_fee`;
  - habitación en casa o ya cancelada → 409 `invalid_state`.

### Grupos

`GET groups/?when=upcoming` (lista paginada; `upcoming` = su última noche es hoy o después, o sin fechas, ordenado por
llegada; `past` = terminados, el más reciente primero):

```json
{"count": 1, "results": [{
  "id": "4cba…", "name": "Boda Torres · Díaz", "notes": "", "reservations_count": 2,
  "contact_guest": {"id": "…", "full_name": "Ana Torres", "email": "", "phone": "", "is_vip": false, "nationality": ""},
  "figures": {"start": "2026-11-07", "end": "2026-11-10", "reservations": 2, "rooms": 3, "blocks": 1,
              "blocked_units": 2, "picked_rooms": 1, "room_nights": 6, "picked_room_nights": 3, "pickup_pct": 50.0,
              "balance": "3826470.00", "state": "upcoming"},
  "created_at": "…"}]}
```

- `figures.start/end`: primera llegada y última salida de sus habitaciones vivas y de sus cupos.
- `rooms`: estadías vivas (camas en dormitorio).
- `pickup_pct`: noches-habitación tomadas / apartadas; `null` sin cupos.
- `balance`: Σ saldos de sus reservas (regla de `finance.reservation_balance`, que con P4 excluye lo de empresas con
  crédito).
- `state`: `upcoming | in_house | past | empty`, según la fecha de negocio.
- Cifras calculadas en bloque (consultas constantes por página).

`GET groups/{id}/` = lo mismo + `currency`, `business_date` y:
- `blocks`: `[BlockSerializer]`;
- `reservations`: forma de `ReservationList`, con saldo;
- `rooming`: una fila por habitación, sin canceladas ni no-show, ordenadas por llegada y código.

Fila de la rooming list (también la respuesta de `POST stays/{id}/rooming/`):

```json
{"stay_id": "a210…", "reservation_id": "b844…", "code": "HT-92D8TX", "status": "confirmed", "booker_name": "Ana Torres",
 "room_type": {"id": "…", "code": "DBL", "name": {…}, "kind": "private", "color": "#4E6C88"},
 "rate_plan": {"id": "…", "code": "NR", "name": {…}},
 "room": {"id": "…", "number": "203", "housekeeping_status": "clean"} | null, "bed": {"id": "…", "label": "A"} | null,
 "checkin": "2026-11-07", "checkout": "2026-11-10", "nights": 3, "adults": 2, "children": 0,
 "guest": {"id": "…", "first_name": "Ana", "last_name": "Torres", "full_name": "Ana Torres"} | null,
 "occupants": 1, "group_block_id": null, "total_amount": "1055578.00"}
```

`POST stays/{id}/rooming/` `{"first_name": "Ana", "last_name": "Torres"}`:
- el nombre es el del **primer ocupante** de la estadía;
- el nombre del titular (sin importar mayúsculas, tildes ni espacios) vincula al titular;
- un huésped "solo nombre" escrito antes aquí se renombra en el mismo registro;
- un huésped real que era el primer ocupante se reemplaza en esa habitación (sigue en la organización);
- vacío quita un "solo nombre";
- audita `bookings.rooming_updated`.

### Cupos

`BlockSerializer`:

```json
{"id": "572a…", "group_id": "4cba…",
 "room_type": {"id": "…", "code": "SUP", "name": {…}, "kind": "private", "color": "#5F7F66"},
 "start": "2026-11-07", "end": "2026-11-10", "units": 2, "release_date": "2026-10-31", "released_at": null,
 "pickup": {"nights": [{"date": "2026-11-07", "units": 2, "picked": 1, "remaining": 1}, …],
            "room_nights": 6, "picked_room_nights": 3, "pickup_pct": 50.0, "picked_rooms": 1,
            "remaining_min": 1, "released": false},
 "created_at": "…"}
```

- `POST groups/{id}/blocks/` `{"room_type_id", "start", "end", "units", "release_date", "allow_overbooking"?}`:
  - `end` es exclusivo;
  - `start ≥ hoy`, `hoy ≤ release_date ≤ start` → si no, 400 `invalid_dates` / `invalid_release_date`;
  - 1 ≤ `units` ≤ unidades activas de la categoría → si no, 400 `invalid_units`;
  - una noche sin esas unidades → 409 `no_availability` + `shortfalls`;
  - `allow_overbooking` exige `bookings.overbook`.
- `PATCH blocks/{id}/` `{units?, start?, end?, release_date?, allow_overbooking?}`:
  - bajar de lo ya tomado en alguna noche → 400 `block_below_pickup` (+`picked`);
  - `release_date` entre hoy y la última noche;
  - cupo liberado → 409 `invalid_state`.
- `POST blocks/{id}/release/`: idempotente; lo no tomado vuelve a la venta y los pickups conservan su reserva y su
  habitación.
- `DELETE blocks/{id}/` → 204; con pickups → 409 `block_has_pickups` (liberarlo en su lugar).
- `PATCH reservations/{id}/` `{"group_id": …}`: si la reserva tiene pickups de un cupo de su grupo → 400
  `block_pickups`.

### Check-in (cambio de comportamiento)

`POST stays/{id}/check-in/` `{"force": false}` responde **409** si otra estadía `checked_in` sigue en esa habitación
(o cama), típicamente el huésped que sale hoy y no ha hecho check-out:

```json
{"detail": "La habitación 107 sigue ocupada: Julien Durand (HT-Z7T4QM) aún no hace check-out", "code": "room_occupied",
 "room_id": "…", "bed_id": null,
 "occupied_by": {"stay_id": "…", "reservation_id": "…", "code": "HT-Z7T4QM", "guest_name": "Julien Durand",
                 "checkout": "2026-09-28"}}
```

`force: true` hace el check-in igual. Es un `RoomNotReadyError` con `code="room_occupied"`; la habitación sucia sigue
siendo `room_not_ready`.

---

## Modelo (migración `bookings/0002_groups_allotments`, aplicada en la BD de desarrollo)

- **`GroupBlock`**: `group` (FK `ReservationGroup` CASCADE, `blocks`), `room_type` (FK RESTRICT), `start`, `end`
  (exclusivo), `units`, `release_date`, `released_at`. Checks: `end > start` y `units ≥ 1`; índice
  `(room_type, start, end)`. En el admin es de **solo lectura**: cambiarlo mueve el inventario, así que se hace por
  los servicios.
- **`Stay.group_block`**: FK SET_NULL. Marca la estadía como tomada del cupo (pickup).
- **`InventoryDay.held_units`** (default 0): contador propio de lo apartado por cupos sin tomar.
  - `available = total − sold − blocked − held` (propiedad del modelo, `available_by_date`, `availability`,
    ofertas, ARI y calendario).
  - Para ocupación, lo apartado sigue siendo inventario disponible (Hoy y reportes usan `total − blocked`).
  - Regla por cupo sin liberar y noche: `max(0, units − tomadas)`. "Tomadas" cuenta las estadías del cupo en
    tentative, confirmed, checked_in o checked_out que cubren la noche.
  - Un pickup mueve una unidad de apartada a vendida. Cancelar o no-show la devuelve al cupo mientras no se libere.
  - `rebuild_inventory` recalcula `held_units` igual que el incremental (deriva 0 verificada tras operaciones, seed y
    automatización).
  - `InventoryDay.objects.only(...)` con algún contador carga los cuatro. Así el `.only(…)` de la grilla de tarifas
    (escrito antes de `held_units`) no hace una consulta extra por fila (medido: 159 → 4 consultas).
- **`Reservation.Source.IMPORT`** (`"import"`, "Importación") para P5. También está en el CSV de reservas y en los
  filtros del frontend.

## Contratos implementados / consumidos

Firmas exactas (`apps.bookings.services.*`):

```python
# reservations.py
def cancel_stay(stay, *, reason, waive_fee=False, actor=None) -> Reservation          # contrato del plan P3
def preview_cancel_stay(stay) -> dict                                                 # la vista previa de arriba
def add_stay(reservation, stay_req, *, block=None, actor=None, allow_overbooking=False,
             enforce_restrictions=False) -> Reservation
def create_reservation_in_blocks(req: ReservationRequest, *, blocks: dict, actor=None, source_label=None) -> Reservation
    # blocks = {índice de la estadía en req.stays: GroupBlock}; create_reservation(req) no cambia
def quote_stays(property, stays: list[StayRequest], *, promo_code="", foreign=False) -> dict
# policies.py
def stay_cancellation_fee(stay, *, now=None) -> FeeQuote                              # política aplicada a 1 estadía
# availability.py
def room_offers(*, property, checkin, checkout, promo_code=None, guest_is_foreign_non_resident=False,
                block=None) -> list[Offer]
# blocks.py
def create_block(group, *, room_type, start, end, units, release_date, actor=None, allow_overbooking=False) -> GroupBlock
def update_block(block, *, units=None, start=None, end=None, release_date=None, actor=None,
                 allow_overbooking=False) -> GroupBlock
def release_block(block, *, actor=None, source=None) -> GroupBlock                    # idempotente
def delete_block(block, *, actor=None) -> None
def release_due_blocks(property, *, actor=None) -> list[dict]                         # la automatización
def pickup_summary(block) -> dict
def availability_with_block(block, checkin, checkout) -> int
# groups.py
def group_figures(groups, *, today=None) -> dict
def rooming_list(group) -> list[dict]
def set_rooming_name(stay, *, first_name, last_name="", actor=None) -> Stay
def delete_group(group, *, actor=None) -> None
# inventory.py
def adjust_inventory(property, deltas, *, allow_overbooking=False, held=None) -> list[dict]   # + held (kw)
def count_holds(type_ids, start, end) -> Counter
```

Detalles de comportamiento:
- **Penalidad proporcional** (`stay_cancellation_fee`): la política de la reserva aplicada solo a esa estadía.
  - Gratis si la reserva o la estadía es tentativa, o si no hay política.
  - No reembolsable → total de la estadía.
  - Gratis hasta `free_until_hours_before` antes de **su** llegada.
  - Después: `first_night` (su primera noche), `percent` (de su total) o `full`.
  - Se cobra como cargo `cancellation_fee` sin IVA y se suma a `Reservation.cancellation_fee`.
  - `cancel_reservation` y `mark_no_show` ahora **suman** su penalidad a la que ya hubiera de habitaciones canceladas
    antes; antes la reemplazaban.
- `refresh_reservation`: fechas y huéspedes de la reserva siguen a las estadías vivas. Una habitación cancelada sola ya
  no mueve la llegada ni cuenta sus huéspedes. El total sigue sumando todas las estadías, como documentó B2b.
- Orden de locks: Reservation → Stay → GroupBlock (por pk) → InventoryDay.
- `bookings.services.queries.with_balance` usa ahora `finance.balances.annotate_reservation_balance` (**cambio 2 de
  P4**, aplicado aquí porque bookings es de P3). Verificado igual a `finance.reservation_balance` en 1.200 reservas de
  las 3 propiedades; ~0,05 s para las 1.358 del hostal. Afecta a todas sus lecturas: lista de reservas, Hoy, grupos,
  reportes, copiloto, `check_integrity` y export.

Consumidos:
- `rates.quote` (vía `pricing.price_stay`);
- `guests.services.upsert_guest` y `update_guest`;
- `finance.services.post_charge` y `get_or_create_folio`;
- `finance.balances.annotate_reservation_balance` (P4);
- `core.audit`, `core.signals`, `core.automation`.

## Señales emitidas / escuchadas

Ninguna nueva; todas con `send_on_commit`.

| Operación | Señales |
|---|---|
| Agregar habitación | `reservation_updated(reservation, changes, stay)` (con `changes["stays"]`) + `inventory_changed(origin="bookings")` |
| Cancelar una habitación | `reservation_updated(changes={"stay.status": ("confirmed", "cancelled"), …}, stay)` + `inventory_changed`. La última activa → las de `cancel_reservation` (`reservation_cancelled`) |
| Crear, editar, liberar o borrar cupo | `inventory_changed(property, room_type_ids=[categoría], start, end, origin="bookings")` (distribution empuja ARI; el receiver de bookings lo ignora) |
| Pickup | Las de `create_reservation` |

- `check_in` con `room_occupied` no emite nada.
- No hay receivers nuevos, así que no hay nada que proteger con `is_seeding()`.

Auditoría (`AuditEvent.action`), todas no reversibles:
`bookings.stay_added`, `bookings.stay_cancelled`, `bookings.group_created`, `bookings.group_updated`,
`bookings.group_deleted`, `bookings.group_block_created`, `bookings.group_block_updated`,
`bookings.group_block_released`, `bookings.group_block_deleted`, `bookings.rooming_updated`.

## Automatizaciones registradas

| Código | Horario | Qué hace |
|---|---|---|
| `bookings.release_group_blocks` | diario 02:30 (después de la auditoría nocturna de las 02:00, que mueve la fecha de negocio) | Libera los cupos sin liberar con `release_date ≤ fecha de negocio`, cada uno en su transacción. `skipped` si no hay; si no, "N cupo(s) liberado(s): M noches-habitación vuelven a la venta". `details`: `released` (`[{block_id, group, room_type, freed}]`) y `freed_room_nights` |

## Proveedores de integración registrados

Ninguno.

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

- **Rutas** (`routes.tsx`, lazy): `groups`, `groups/:id`.
- **Menú** (`nav.ts`): `groups` (Operación, orden 35, `bookings.view`, ícono `UsersRound`).
- **⌘K** (`commands.ts`): `frontdesk.groupReservation` (`bookings.manage` → `/app/reservations/new?group_mode=1`) y
  `frontdesk.groups` (`bookings.view`).
- **Asistente**: parámetros de URL nuevos `?group=<id>`, `&block=<id>` y `?group_mode=1`.
- **Componentes nuevos**:
  - `AddStayDialog`, `CancelStayDialog`;
  - en `components/groups/`: `GroupFormDialog`, `BlockFormDialog`, `BlockCard`, `PickupStrip` (la tira noche por
    noche), `PickupMeter`, `RoomingList`, `GroupReservations`, `AddReservationDialog`.
- **Libs**: `lib/groups.ts` y `lib/wizard.ts` (multi-habitación: `selection`, `split`, `autoSplit`, `splitProblem`,
  `buildStays`, `quoteInput`…).
- **`api.ts`**: tipos y fetchers de todo lo anterior (`RoomOffer`, `StaysQuote`, `GroupDetail`, `GroupBlock`,
  `RoomingRow`…). Las claves viven bajo `['bookings', …]`, así que `useRefreshFrontDesk()` también refresca grupos.
- El asistente **conserva el arreglo de exención de IVA** (`bookerIsForeignNonResident`): al elegir el titular cambia
  `foreign`, y las ofertas por habitación y la cotización se recotizan solas sin perder la selección.

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps (para P-INT)

1. **Worker y beat**: reiniciarlos con el código nuevo para que beat programe `bookings.release_group_blocks`
   (02:30). "Ejecutar ahora" ya funciona sin reiniciar: el registro vive en el proceso web.
2. **Seed**: nada que tocar. `seed_groups` corre dentro de `apps/bookings/seed.py::seed` y tarda ~1 s. Probado en una
   transacción revertida sobre el demo actual:
   - grupos, cupos y pickups en las 3 propiedades, y la reserva de dos categorías en Casa Aurora;
   - deriva de inventario 0 en las 3;
   - segunda corrida sin cambios.
   Para un demo ya cargado: `manage.py seed_groups [--dry-run]`.
3. **P4 cambio 2 (`with_balance`)**: **ya aplicado** en `apps/bookings/services/queries.py` (ver Contratos). P-INT
   solo debe verificarlo con `make check-data`.
4. **Opcional, `rates/services/grid.py` (sin dueño en P)**: agregar `"held_units"` a su `.only(...)`. No hace falta:
   `InventoryDayQuerySet.only` ya lo agrega. Solo deja el código explícito.
5. **Opcional, verificación** (`backend/scripts/smoke_proxy.py`, `endpoints_sweep.py`, `frontend/scripts/route-smoke.mjs`):
   - agregar las rutas `/app/groups` y `/app/groups/<id>`, y los GET `bookings/groups/`, `bookings/groups/<id>/`,
     `bookings/room-offers/`;
   - paso de smoke sugerido: crear una reserva de 2 habitaciones con `group_name` → `groups/<id>/blocks/` → pickup
     con `group_block_id` → `blocks/<id>/release/` → cancelar la reserva (`waive_fee`) y borrar el grupo. Es el guion de
     mi verificación, abajo.
6. **Opcional, `check_integrity`**: invariante "cada estadía con `group_block` es de la categoría del cupo". El
   conteo `held_units` ya lo cubre la deriva de `rebuild_inventory`.
7. **Observaciones de otras tareas (no son de P3)**:
   - P6 / guestportal: en Hoy a 375 px, el widget "Check-in online de hoy" corta su contador "4/5" y los chevrons
     de las filas en el borde derecho de la tarjeta. No hay scroll de página.
   - P5 / imports: `check_integrity` falla hoy en Andino Medellín con "cargos: en casa, noches cobradas hasta ayer ·
     HT-UBUAJ6". Es una reserva importada en casa (`source=import`, "Prueba P5") sin los cargos de alojamiento de
     las noches pasadas. Casa Aurora y el resto pasan, incluido "reservation_balance = with_balance (SQL)" con el
     cambio de P4.

## Limitaciones conocidas / pendientes

- **Tests**: no se escribieron ni corrieron.
  - `frontend/src/features/frontdesk/__tests__/wizard.test.ts` se adaptó **solo para que compile**: el estado cambió
    de `offer` a `selection` y algunas firmas reciben `offers`. El proyecto entero pasa `tsc` y `tsc -b` no se rompe.
  - Los tests heredados de bookings, frontdesk y el frontend pueden estar desactualizados por la multi-habitación, el
    409 de check-in, `room_offers` y el `refresh_reservation` nuevo.
- **Una sola política por reserva** (la de la primera estadía, como en B2b): una habitación agregada con otra tarifa
  se cancela con la política de la reserva. En la vista previa se ve cuál aplica.
- **Tras "Agregar habitación" no se reenvían correos** ni se reemiten documentos. Emite `reservation_updated` con
  `changes["stays"]`; los consumidores (mensajería, ARI) reaccionan como a cualquier cambio.
- **Cancelar una habitación** solo aplica a habitaciones pendientes; a un huésped en casa se le hace check-out
  (salida anticipada). Cancelar la última habitación activa de una reserva **en casa** (las demás ya salieron) la
  deja `checked_out`.
- **Cupos**:
  - Una categoría por cupo (un grupo puede tener varios).
  - Las fechas del cupo y de las estadías son independientes: una estadía del cupo más larga toma disponibilidad
    general en las noches de más.
  - Un pickup que cambia de categoría (`modify_stay`) sale del cupo. Un upgrade por asignación (`assign_room` con
    `force`) lo conserva.
  - El calendario (C13) muestra la disponibilidad ya descontada, pero **no dibuja los cupos**. Sería una mejora de
    `features/calendar`, que no es de P3.
- **Rooming list**:
  - Los nombres escritos crean huéspedes "solo nombre" (sin documento): el registro TRA/SIRE de esas personas los
    pedirá al hacer check-in, como con cualquier acompañante sin datos.
  - Un "solo nombre" que se reemplaza o se borra queda en Huéspedes sin estadías. Se puede fusionar o limpiar desde
    Huéspedes; no lo borro para no perder auditoría.
- **Aterrizaje**: el supervisor de limpieza (`housekeeping.supervise`) va al tablero `/app/housekeeping`, no a
  `/mine`, igual que en C1. El requisito dice "`housekeeping.work` → `/mine`" y el supervisor también tiene `work`,
  pero su página es el tablero.
- **Mensajes de error de dominio en español** (como todo el backend). El frontend muestra el `detail`.

## Cambios de esta sesión (sobre el trabajo heredado)

- **Backend**:
  - Pickup sin precio → 400 `no_rate` aunque se salten restricciones.
  - Auditoría al editar un grupo (`bookings.group_updated`).
  - `housekeeping_status` en la fila de la rooming list.
  - El nombre del titular en la rooming list lo vincula en vez de crear un homónimo.
  - `InventoryDayQuerySet.only`, que elimina la N+1 que `held_units` había causado en la grilla de tarifas.
  - Cambio 2 de P4 en `with_balance`.
  - Comando `seed_groups [--dry-run]`.
- **Frontend**:
  - Rutas y menú de Grupos.
  - Página de **detalle del grupo**: cifras, cupos con la tira noche por noche, crear, editar, liberar y borrar cupo,
    rooming list editable en línea y CSV, reservas del grupo con quitar y agregar existente, editar y borrar grupo.
  - **Pickup desde el cupo** en el asistente (`?block=`) y en "Agregar habitación".
  - ⌘K.
  - **i18n ES/EN** de todo P3: 241 claves nuevas por idioma, paridad 684/684.
  - El + de las tarifas agotadas ya no se ve como botón primario.
  - Códigos de reserva sin partirse en móvil.
  - `wizard.test.ts` compila.

## Verificación (sin tests, modo MVP)

- `docker compose exec -T backend python manage.py check` → "System check identified no issues".
- `makemigrations bookings frontdesk --check --dry-run` → "No changes detected". `showmigrations`:
  `bookings.0002_groups_allotments` aplicada.
- `ruff check` y `ruff format --check` limpios en `apps/bookings` y `apps/frontdesk`.
- `spectacular --validate`: sin warnings de bookings o frontdesk (los 2 únicos son de `imports`, P5).
- **Curl por el proxy de Vite** (`http://localhost:5173/api/...`, cookie jar + CSRF, como `smoke_proxy.py`), con
  `owner@casaaurora.co` sobre el demo. Guion en el scratchpad de la sesión (`p3_verify.py`): **43 comprobaciones, 0
  fallas** (~120 requests, 40–630 ms cada una):
  - `room-offers` normal y `foreign=1` (sin IVA);
  - `quote` de 3 habitaciones (Σ líneas = total);
  - crear reserva de 3 habitaciones con `group_name` (total = cotización; disponibilidad −2);
  - lista y detalle de grupos;
  - cupo de 2: la disponibilidad general baja 2; 60 unidades → 400 `invalid_units`;
  - `room-offers?block` (solo su categoría, disponibilidad + apartado);
  - **pickup** (la disponibilidad no cambia; pickup 1/2);
  - PATCH del cupo: crecer sin cupo → 409 `no_availability`; bajar a 1 → +1 general; mover `release_date`; volver
    a 2;
  - agregar habitación (201, 4 estadías);
  - `cancel-preview` (no reembolsable: penalidad = total de la habitación); cancelar sin `confirm` → 400; cancelar
    una habitación (la reserva sigue confirmada);
  - rooming: nombre, renombrar en el mismo registro, CSV con el nombre y "Del cupo";
  - PATCH `group_id` de una reserva ajena (entra y sale); pickup fuera de su grupo → 400 `block_pickups`;
  - liberar cupo (+1 general); borrar cupo con pickups → 409 y sin pickups → 204;
  - `recepcion@` lee el grupo; `limpieza@` → 403;
  - limpieza final: cancelar las reservas de prueba y borrar el grupo; la disponibilidad vuelve exactamente al
    inicio.
- **En una transacción revertida** (`manage.py shell`, `p3_rollback.py`; la BD compartida no cambió):
  - check-in en la 107 con Julien Durand (HT-Z7T4QM) aún en casa → **409 `room_occupied`** con `occupied_by`; con
    `force` → 200;
  - `automation.run("bookings.release_group_blocks")` → `success` "1 cupo(s)… 2 noche(s)-habitación"; segunda corrida
    `skipped`; `held_units` 0 → 1 → 0; `rebuild_inventory` sin deriva;
  - **seed** de bookings dos veces: 0,8 s y 0,1 s; grupos, cupos, pickups y nombres en las 3 propiedades; la reserva
    de dos categorías; deriva 0; la segunda corrida no crea nada;
  - `manage.py seed_groups --dry-run` → 1,0 s y todo revertido.
- **Frontend**:
  - `npx tsc -p tsconfig.app.json --noEmit` → **0 errores en todo el proyecto**, incluidos los tests de la feature;
  - `npx eslint src/features/frontdesk` → limpio;
  - claves i18n ES = EN (684) y todas las usadas existen;
  - los módulos nuevos cargan en Vite (200).
- **Revisión visual en un Chrome headless propio** (perfil temporal, puertos 9571–9575; nunca el navegador
  compartido), con datos de prueba creados y borrados por API:
  - lista y detalle de grupos, reserva de 3 habitaciones, asistente (pickup desde el cupo y multi-habitación con
    reparto), diálogos (agregar habitación, cancelar habitación, nuevo cupo) y el detalle en inglés;
  - 1440 y 375 px, tema oscuro: sin errores de consola, sin API ≥ 400 y sin desborde horizontal;
  - `frontend/scripts/route-smoke.mjs` con `ONLY=/app$,/app/reservations,/app/calendar`: **ROUTES OK** a 1440 (12) y
    375 px (10);
  - aterrizajes comprobados: limpieza → `/app/housekeeping/mine`, mantenimiento → `/app/maintenance`, contabilidad →
    `/app/reports`, recepción y dueño → Hoy.
- **Datos que quedaron en la BD de desarrollo**: 16 reservas de prueba en Casa Aurora, todas **canceladas**, con
  saldo 0 y notas "Prueba P3".
  - Guion: HT-CZ67QN, HT-N4V8XA, HT-WPGJX4, HT-Q4SQFP, HT-CE7D7C y HT-CWRSCY. La penalidad de prueba de HT-WPGJX4
    se anuló en el folio y su `cancellation_fee` quedó en 0, así que `check_integrity` pasa.
  - Capturas: HT-M3W9DB, HT-78PDHF, HT-SPUSSQ, HT-ZHRWD6, HT-KHYRSH, HT-GVWGWU, HT-ZTXDD6, HT-9JG39K, HT-PCZGB2 y
    HT-QNU6NS (titulares "Prueba Visual P3" e "Invitada Visual P3").
  - Los grupos de prueba se borraron.
  - Un `seed_demo --reset` deja todo limpio.
