# C1 — Recepción (frontdesk) — integration notes

Estado: **implementado de punta a punta en MODO MVP** (decisión del usuario: sin tests nuevos, sin TDD y sin correr
suites; los tests se escriben después de validar en Chrome). Esta sesión retomó un intento previo interrumpido: el
backend y el frontend heredados estaban casi completos; se revisaron contra el plan, se corrigieron y se completaron
(ver "Cambios de esta sesión"). Owner paths: `backend/apps/frontdesk/**`, `frontend/src/features/frontdesk/**` y
esta nota. No se tocó nada fuera de ellos. Sin dependencias nuevas. Sin commits.

Verificación mínima hecha (evidencia al final): `manage.py check` limpio, migración `frontdesk/0001` al día,
`ruff check`/`ruff format --check` limpios en la app, curl por el proxy de Vite (5173) contra el seed con los roles
dueño/recepción/limpieza, automatización y `POST night-audit/run/` probados **dentro de una transacción revertida**
(la fecha de negocio compartida no se movió), seed probado con rollback, `tsc` y `eslint` sin errores en la feature.

---

## Cómo probarlo en la UI

App: **http://localhost:5173**. Usuarios (clave `housetel123`): `owner@casaaurora.co` (dueño: todo),
`recepcion@casaaurora.co` (rol recepción: sin auditoría nocturna), `limpieza@casaaurora.co` (housekeeping),
`owner@grupoandino.co` (Andino Medellín + Andino Hostel Bogotá, con dormitorios por cama).
Fecha de negocio del demo: **2026-09-27** (igual a la fecha calendario). Los códigos de abajo son los del seed actual;
otros agentes están probando sobre la misma BD, así que alguno puede haber cambiado de estado.

1. **Panel Hoy (`/app`)** — entrar como `recepcion@casaaurora.co`.
   - Esperado: saludo con el nombre ("Buenas tardes, Andrés"), fecha de negocio arriba, botones **Walk-in** y
     **Nueva reserva**; 5 cifras (ocupación ≈ 61 % "14 de 23", llegadas 0 de 2, salidas 0 de 6, en casa 18,
     ingresos del día con ADR); panel **Movimientos de hoy** con pestañas Llegadas / Salidas / En casa (contador
     hecho/total); **tablero de llaves** por piso (llaves teñidas: limpia salvia, sucia arena, inspeccionada azul,
     ocupada terracota, bloqueada rayada; marcador de llegada/salida); zona de **widgets** de otras features
     (progreso de limpieza de C2, check-ins online de C5, recomendaciones de C8, si su permiso lo permite).
   - Llegadas: **HT-D62XA4** (Luis Fernando Gómez Quintero, hab. 102) con chip **Lista**; **HT-M2BDPV** (Julián Pérez
     Ramírez, hab. 207) con chip **Hab. aún ocupada** (Antoine Bernard, HT-UYRN4J, sale hoy y no ha hecho check-out).
2. **Check-in en 1–2 clics** — en Llegadas, botón **Check-in** de HT-D62XA4.
   - Diálogo: datos del huésped (documento, nacionalidad, email, teléfono, aviso si falta el documento, estado del
     check-in online), **habitación** (la 102 asignada y limpia; lista de alternativas con las limpias y libres de
     su categoría primero), **saldo** con `FolioPanel` compacto (se puede cobrar ahí mismo) y **Confirmar check-in**.
   - Resultado: toast "Check-in hecho: … en la 102", la fila pasa a "En casa" (abajo, atenuada), llegadas 1 de 2, la
     llave 102 se vuelve terracota.
   - Probar también HT-M2BDPV: el diálogo avisa "La 207 sigue ocupada: Antoine Bernard aún no ha hecho check-out" y
     **propone otra habitación limpia y libre** de su categoría; confirmar la mueve y hace el check-in.
3. **Check-out con pago** — pestaña Salidas → **Check-out** de HT-9NMCKG (hab. 104, saldo ≈ $690.590) o de
   HT-UYRN4J (207).
   - Diálogo: folio compacto; el botón **Confirmar check-out** está **bloqueado** mientras haya saldo (con
     `bookings.checkout_with_balance` —dueño— aparece la casilla "Hacer check-out con saldo pendiente"). Registrar el
     pago en el folio (recepción tiene turno de caja abierto: efectivo sirve; el dueño no tiene turno → usar
     datáfono), el saldo baja a 0 y el botón se habilita.
   - Resultado: toast, salidas 1 de 6, la habitación queda **sucia** (llave arena) → sigue el flujo de C2 en
     `/app/housekeeping/mine` con `limpieza@casaaurora.co`. HT-YHBSUF (205) y HT-85AY9Q (208) salen sin saldo.
   - Salida anticipada: un huésped "En casa" que no sale hoy muestra el aviso "se liberan N noches".
4. **Tablero de llaves** — clic en una llave: llegada asignada → abre el check-in; ocupada que sale hoy → abre el
   check-out; ocupada que se queda → abre la reserva; libre (103, 106, 107, 109) → abre el asistente con esa
   habitación y hoy/mañana; dormitorios (Andino Hostel) → calendario. Tooltip y `aria-label` con el estado.
5. **Reservas (`/app/reservations`)** — tabla paginada en servidor con vistas rápidas **Todas / Llegadas hoy /
   Salidas hoy / En casa / Sin pagar / Sin asignar / Tentativas**, búsqueda (código, nombre, email, teléfono),
   filtros de estado, fuente y rango de llegada, orden por columnas y **Exportar CSV** (descarga
   `reservas-2026-09-27.csv` con todas las filas del filtro, separador `;`). El estado vive en la URL
   (`?view=arrivals&q=gomez`). Clic en una fila → detalle.
6. **Nueva reserva (`/app/reservations/new`)** — asistente de 5 pasos con resumen lateral:
   fechas y huéspedes (niños con edad, código promocional, "extranjero no residente" sin IVA) → **ofertas**
   agrupadas por categoría con total, precio por noche, plan de comidas y política → **huésped** con `GuestPicker`
   (buscar o crear en línea; aviso de duplicados) + fuente e idioma → extras (cantidad por defecto según tipo),
   hora de llegada, pedidos y notas → **garantía**: ninguna, pago ahora (efectivo/datáfono/transferencia/otro,
   sugiere el depósito del plan) o link de pago (con envío por email), y casilla "tentativa". Crear → detalle de la
   reserva nueva con los extras y el pago ya en el folio.
   - **Walk-in**: botón Walk-in en Hoy (o el interruptor del paso 1): llegada hoy, se eligen noches; al crear
     asigna una habitación limpia y libre y hace el check-in → toast "Reserva … creada y huésped en casa".
   - Desde el tablero: `?checkin&checkout&room_id&room_type_id` preselecciona la habitación (chip "Habitación
     elegida").
7. **Detalle (`/app/reservations/:id`)** — encabezado con código, estado, fuente/canal, huésped (VIP), fechas,
   **saldo** y acción principal (Check-in / Check-out si hay una sola estadía); menú **Más acciones**: Confirmar
   (tentativas), No-show (confirmadas con llegada pasada), **Cancelar** (vista previa de la penalidad; exonerarla
   exige `bookings.waive_fee` y escribir el código), más las acciones de otras features (C5: enviar link del
   portal, QR). Pestañas **Resumen** (tarjetas de estadía con asignar/mover habitación, cambiar fechas con la
   **recotización visible** antes de guardar, desglose por noche; datos editables: ETA, garantía, idioma, pedidos,
   notas, link del portal) y **Huéspedes** (titular y acompañantes por estadía con `GuestPicker`), más las de otras
   features: **Folio** (B4), check-in online y solicitudes (C5), etc.
8. **Auditoría nocturna (`/app/night-audit`)** — solo con `frontdesk.night_audit` (dueño/gerente; recepción ve el
   aviso y el historial). Muestra el día abierto, la **vista previa real** (noches a publicar ≈ 12, llegadas que
   quedarían como no-show, salidas vencidas, tentativas, ocupación/ingresos/ADR/RevPAR/cobrado) y **Cerrar el día**
   con confirmación. **Hacerlo al final de la validación**: avanza la fecha de negocio a 2026-09-28 y marca como
   no-show las llegadas de hoy que no hicieron check-in. Después el botón queda deshabilitado ("Este día todavía no
   ha empezado") y el cierre aparece en **Cierres anteriores** con su detalle. La barra superior muestra la nueva
   fecha. El centro de control (C12) → "Ejecutar ahora" corre la versión programada: solo cierra días que ya
   terminaron, así que con la fecha al día responde "omitida: la fecha de negocio está al día".
   - El historial de 30 cierres lo crea `apps/frontdesk/seed.py` (lo corre `seed_demo`; en esta sesión solo se probó
     con rollback, así que hasta que C-INT siembre verás "Aún no hay cierres registrados"). Para cargarlo sin el
     seed completo: `docker compose exec -T backend python manage.py shell -c "import random; from apps.core.seed
     import SeedContext, PROPERTIES; from apps.core.models import Property; from apps.frontdesk import seed;
     ctx = SeedContext(today=None, rng=random.Random(1)); ctx.properties = {k: Property.objects.get(slug=v['slug'])
     for k, v in PROPERTIES.items()}; seed.seed(ctx)"` (idempotente, ~7 s).
9. **Paleta ⌘K** — "Nueva reserva", "Walk-in" y "Buscar reserva por código" (si se escribe un código, p. ej.
   `ht-d62xa4`, abre la lista filtrada por él; si no, la lista con el buscador enfocado).
10. **Roles** — `limpieza@casaaurora.co` al entrar a `/app` es **redirigido a `/app/housekeeping/mine`** (sin
    `frontdesk.view` y con `housekeeping.work`); un supervisor de limpieza va a `/app/housekeeping`; contabilidad
    (sin `frontdesk.view`) va a su primera página visible.
11. **Móvil 375 px y tema oscuro / EN** — Hoy, lista, asistente y detalle sin scroll horizontal de página (pestañas
    y vistas rápidas se desplazan dentro de su barra); todo el texto en ES/EN.

---

## API implementada

Base `/api/v1/frontdesk/`, sesión + `X-Property-Id` (reglas de tenancy de A1: 400 `property_required`, 404 propiedad
ajena, 403 `permission_denied` + `permission`, 402 organización suspendida). Dinero: strings con 2 decimales.

| Método y path | Permiso | Respuesta |
|---|---|---|
| `GET today/` | `frontdesk.view` | tablero del día (abajo) |
| `GET night-audit/preview/` | `frontdesk.night_audit` | lo que haría cerrar el día (la auditoría real en una transacción revertida) |
| `POST night-audit/run/` `{business_date}` | `frontdesk.night_audit` | 201 reporte (cerró ahora) · 200 reporte existente (ese día ya estaba cerrado) · 409 |
| `GET night-audit/reports/` · `GET night-audit/reports/{id}/` | `frontdesk.view` | reportes (paginado `{count,next,previous,results}`, más reciente primero) |
| `GET reservations/export/?<filtros de bookings>&ordering=&lang=es\|en` | `bookings.view` | CSV (`;`, UTF-8 con BOM) de **todas** las reservas del filtro (máx. 10.000) |
| `GET reservations/{id}/online-checkin/` | `bookings.view` | `{reservation_id, status, completed_at}` del check-in online de C5 (`status` null si nunca empezó) |

La lista, el detalle y todas las acciones sobre reservas usan la API de **bookings** (B2b); el folio, la de
**finance** (B4). C1 no duplica endpoints.

### `GET today/`

Respuesta real (acortada; una fila por **estadía**: una estadía de dormitorio es una cama):

```json
{
  "business_date": "2026-09-27", "calendar_date": "2026-09-27", "currency": "COP",
  "kpis": {"occupancy_pct": 60.9, "rooms_occupied": 14, "rooms_available": 23, "rooms_blocked": 1, "rooms_free": 9,
           "arrivals_total": 2, "arrivals_done": 0, "arrivals_late": 0,
           "departures_total": 6, "departures_done": 0, "departures_overdue": 0,
           "in_house": 18, "guests_in_house": 33,
           "room_revenue_today": "6459800.00", "other_revenue_today": "8399098.00", "revenue_today": "14858898.00",
           "adr_today": "461414.00", "collected_today": "14922758.00"},
  "arrivals": [{
    "stay_id": "7def…", "reservation_id": "2ab0…", "code": "HT-M2BDPV", "status": "confirmed",
    "reservation_status": "confirmed", "source": "walk_in", "channel_code": "", "guest_id": "2242…",
    "guest_name": "Julián Pérez Ramírez", "is_vip": false, "room_id": "a8d1…", "room": "207", "bed_id": null,
    "bed": null, "room_status": "clean",
    "room_type": {"id": "a063…", "code": "SUP", "name": {"es": "Superior", "en": "Superior"}, "color": "#5F7F66", "kind": "private"},
    "checkin": "2026-09-27", "checkout": "2026-09-30", "nights": 3, "adults": 2, "children": 0, "eta": null,
    "balance": "1005400.00", "balance_due": "1005400.00", "online_checkin_done": false,
    "checked_in_at": null, "checked_out_at": null, "departs_today": false,
    "occupied_by": {"stay_id": "e807…", "reservation_id": "b091…", "code": "HT-UYRN4J",
                    "guest_name": "Antoine Bernard", "checkout": "2026-09-27", "departing": true},
    "done": false, "ready": false, "issues": ["room_occupied"]
  }],
  "departures": [{"…misma forma…": "", "issues": ["balance_due"], "ready": false, "done": false}],
  "in_house": [{"…misma forma…": ""}],
  "rooms": [{"id": "a8d1…", "number": "207", "floor": "2",
             "room_type": {"id": "…", "code": "SUP", "color": "#5F7F66", "kind": "private"},
             "housekeeping_status": "clean", "blocked": false,
             "occupant": {"stay_id": "…", "reservation_id": "…", "guest_name": "Antoine Bernard", "checkout": "2026-09-27", "departing": true},
             "arrival": {"stay_id": "…", "reservation_id": "…", "guest_name": "Julián Pérez Ramírez", "checkin": "2026-09-27", "late": false},
             "beds": null}],
  "previous": null,
  "night_audit": {"due": false, "last_report": null}
}
```

- **Llegadas** (`arrivals`): estadías con llegada = fecha de negocio (pendientes o ya hechas, `done`) y pendientes con
  llegada pasada (issue `late_arrival`, no cuentan en `arrivals_total`). **Salidas**: en casa con salida hoy
  (pendientes) o finalizadas hoy (`done`), más en casa con salida vencida (`overdue`). **En casa**: toda estadía
  `checked_in`. Orden: pendientes primero (llegadas por ETA, tardías arriba; salidas vencidas arriba), luego por
  habitación.
- `issues` de llegada: `late_arrival`, `tentative`, `unassigned`, **`room_occupied`** (su habitación/cama aún tiene
  un huésped en casa: `occupied_by`), `room_not_ready` (sucia o fuera de servicio). `ready` = pendiente sin issues
  (1 clic basta). Salida: `overdue`, `balance_due`; `ready` = se puede hacer check-out sin cobrar.
- `balance` = saldo de la reserva (mismo cálculo que `finance.reservation_balance`, vía `with_balance` de bookings);
  `balance_due` = max(saldo, 0).
- `online_checkin_done` = `guestportal.OnlineCheckin.status == "completed"` (import protegido: `false` si C5 no está).
- `rooms` (tablero de llaves): toda habitación activa de categoría activa, por piso (numéricos primero) y orden;
  `blocked` = un `RoomBlock` activo cubre hoy; privadas: `occupant` (huésped en casa; si hay dos, el que se queda) y
  `arrival` (llegada pendiente asignada que cubre hoy); dormitorios: `beds {total, occupied, departing, arriving,
  blocked}`.
- `kpis` (definiciones compartidas con el cierre, `services/figures.py`): vendidas = estadías `confirmed|checked_in|
  checked_out` que cubren la noche; disponibles = `InventoryDay.total − blocked` (contrato `availability`);
  ocupación = vendidas/disponibles (1 decimal); ingreso de alojamiento = neto de la noche (cargo `room` publicado o,
  si aún no, el `net` de `nightly_rates`); otros ingresos = neto de cargos no-`room` con esa fecha de negocio
  (extras, penalidades, ajustes); ADR = alojamiento/vendidas; cobrado = pagos aprobados − reembolsos aprobados del
  día. `previous` = cifras del día anterior según su reporte de cierre (null sin reporte). `night_audit.due` = la
  fecha de negocio quedó atrás del calendario.
- Rendimiento medido por el proxy: 150–250 ms (Aurora 34 KB, Andino 56 KB).

### Auditoría nocturna

`GET night-audit/preview/` →

```json
{"business_date": "2026-09-27", "next_business_date": "2026-09-28", "calendar_date": "2026-09-27",
 "due": false, "can_run": true, "reason": null,
 "summary": {"business_date": "2026-09-27", "next_business_date": "2026-09-28", "auto_no_show": true,
   "room_charges": {"stays": 12, "nights": 12, "net": "5758200.00", "tax": "844778.00", "total": "6602978.00"},
   "no_shows": [{"reservation_id": "…", "code": "HT-D62XA4", "guest_name": "…", "checkin": "2026-09-27", "fee": "670208.00"}],
   "no_show_fees": "1170008.00",
   "overdue_departures": [{"stay_id": "…", "reservation_id": "…", "code": "HT-85AY9Q", "guest_name": "…", "room": "208", "bed": null, "checkout": "2026-09-27"}],
   "pending_tentative": [{"reservation_id": "…", "code": "…", "guest_name": "…", "checkin": "…", "hold_expires_at": "…"}],
   "errors": [],
   "activity": {"arrivals": 0, "departures": 0, "in_house": 18, "cancellations": 25, "no_shows": 2},
   "figures": {"rooms_occupied": 12, "rooms_available": 23, "rooms_blocked": 1, "rooms_free": 11, "occupancy_pct": 52.2,
               "room_revenue": "5758200.00", "other_revenue": "8399098.00", "revenue": "14157298.00", "adr": "479850.00",
               "revpar": "250357.00", "collected": "14922758.00",
               "payments": {"count": 10, "total": "14972758.00", "refunds": "50000.00",
                            "by_method": [{"method": "card_terminal", "count": 3, "total": "7329818.00"}]}}},
 "last_report": null}
```

`reason: "audit_ahead"` (y `summary: null`) cuando la fecha de negocio va por delante del calendario.

`POST night-audit/run/` `{"business_date": "2026-09-27"}` (la fecha que el usuario vio en la vista previa: un doble
clic o una segunda pestaña nunca cierran dos días) → **201**:

```json
{"id": "24f2…", "business_date": "2026-09-27", "status": "completed",
 "started_at": "2026-09-27T15:55:29-05:00", "finished_at": "2026-09-27T15:55:30-05:00",
 "triggered_by": {"id": "…", "full_name": "Valentina Rojas", "email": "owner@casaaurora.co"},
 "run_id": "ed16…", "summary": {"…misma forma que la vista previa…": ""}, "created_at": "…"}
```

- Repetir con la misma fecha → **200** con el mismo reporte (nada cambia).
- 409 `business_date_changed` (`business_date` = la actual) si esa ya no es la fecha de negocio;
  409 `audit_ahead` (`business_date`, `calendar_date`) si el día aún no empezó en la zona de la propiedad.
- `status`: `running | completed | partial` (partial = alguna reserva falló; queda en `summary.errors` y en la alerta).

Qué hace `close_business_day(prop)` para la fecha `D`, en una transacción con la propiedad bloqueada
(`select_for_update`): (1) `bookings.post_room_charges(stay, until_date=D+1)` de cada estadía en casa (idempotente:
también publica noches perdidas); (2) `business_date = D+1`; (3) si `property.settings["auto_no_show"]` (default
`True`) → `bookings.mark_no_show` de las confirmadas con llegada `< D+1` sin check-in (penalidad según política,
fechada D+1); las tentativas solo se listan (las libera `bookings.release_expired_tentative`); (4) alerta
`frontdesk:overdue_departures` si quedan huéspedes con salida ≤ D, alerta `frontdesk:night_audit_errors` si algo
falló (ambas se resuelven solas cuando ya no aplica); (5) `NightAuditReport` + auditoría `frontdesk.night_audit`
(`source="user"` si lo corrió alguien, `"automation"` si no). Cada estadía/reserva va en su propio savepoint: un
error de dominio (p. ej. folio cerrado) no detiene el cierre y se reintenta el día siguiente. **Idempotente por
fecha**: un día con reporte `completed|partial` no se vuelve a cerrar.

### CSV de reservas

`GET reservations/export/?status=checked_in&lang=es` → `text/csv; charset=utf-8`, `Content-Disposition: attachment;
filename="reservas-2026-09-27.csv"`. Acepta los mismos filtros que `GET /api/v1/bookings/reservations/` (el
`ReservationFilter` de bookings) y `ordering`. Columnas ES: `Código;Estado;Fuente;Canal;Llegada;Salida;Noches;
Adultos;Niños;Huésped;Email;Teléfono;Habitaciones;Categorías;Total;Saldo;Moneda;Creada` (EN con `lang=en`).

## Modelo (`frontdesk/0001_initial`)

`NightAuditReport(property FK CASCADE, business_date [único por propiedad], started_at, finished_at, status
[running|completed|partial], summary JSON, run FK core.AutomationRun SET_NULL, triggered_by FK User SET_NULL)`,
orden `-business_date`. Registrado en el admin de Django.

## Contratos implementados / consumidos

- Consumidos (solo lectura salvo los servicios de contrato): `bookings.services.charges.post_room_charges`,
  `bookings.services.reservations.mark_no_show`, `bookings.services.availability.availability`,
  `bookings.services.queries.with_balance`, `bookings.services.rooms.READY_STATUSES`,
  `bookings.api.filters.ReservationFilter`; modelos `bookings`, `inventory` (Room, RoomBlock), `finance` (Charge,
  Payment, Refund) y `guestportal.OnlineCheckin` (import protegido con `apps.get_model`); `core.audit`,
  `core.alerts`, `core.automation`, `core.dates`, `core.money`.
- Servicios propios reutilizables (estables): `apps.frontdesk.services.today.today_board(prop)`,
  `online_checkins_done(reservation_ids)`; `apps.frontdesk.services.figures.day_figures(prop, day)` (**C10**: úsenlo
  o repliquen sus definiciones para que Hoy, el cierre y los reportes den los mismos números),
  `sold_stays`, `room_revenue`, `other_revenue`, `payments`; `apps.frontdesk.services.night_audit.
  close_business_day(prop, *, business_date=None, actor=None, run=None, auto_no_show=None) -> (report, closed_now)`,
  `preview_night_audit(prop)`, `audit_state(prop)`, `run_manual(prop, *, business_date, actor)`.
  **C9 (copiloto)** puede usar `today_board` para "¿cuántas llegadas hay hoy?".

## Señales emitidas / escuchadas

- Emitidas por C1 directamente: ninguna. El cierre las provoca a través de bookings: `reservation_no_show` e
  `inventory_changed` (por cada no-show). `post_room_charges` no emite señales.
- Escuchadas: ninguna (no hay `receivers.py`), así que no hay nada que proteger con `is_seeding()`.
- Alertas (`Alert.kind` · `dedupe_key`): `overdue_departures` · `frontdesk:overdue_departures` (warning, link `/app`);
  `night_audit_errors` · `frontdesk:night_audit_errors` (warning, link `/app/night-audit`). Auditoría:
  `frontdesk.night_audit` (no reversible).

## Automatizaciones registradas

| Código | Horario | Qué hace |
|---|---|---|
| `frontdesk.night_audit` | diario 02:00 (crontab) | **Programada** (beat o "Ejecutar ahora" de C12): cierra, del más viejo al más nuevo, los días de negocio que ya terminaron en la zona horaria de la propiedad (máx. 7 por corrida → `partial` si queda atraso); con la fecha al día → `skipped` "La fecha de negocio (…) está al día". **Manual** (`params={"mode": "manual", "business_date": "YYYY-MM-DD"}`, lo usa el botón de `/app/night-audit` vía `run_manual`): cierra esa fecha aunque el día no haya terminado; ya cerrada → `skipped`. Param opcional `auto_no_show` (bool) sobrescribe `property.settings["auto_no_show"]`. `details`: `closed`, `reports`, `business_date`, `no_shows`, `room_nights`, `errors` |

## Proveedores de integración registrados

Ninguno.

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

- `routes.tsx` (todas `lazy`): `index` → Hoy, `reservations`, `reservations/new`, `reservations/:id`, `night-audit`.
- `nav.ts`: sin cambios (`today` `frontdesk.view`, `reservations` `bookings.view`, `nightAudit`
  `frontdesk.night_audit`).
- `commands.ts`: `frontdesk.newReservation`, `frontdesk.walkIn` (`bookings.manage`), `frontdesk.findReservation`
  (`bookings.view`; usa `ctx.query` para detectar un código `HT-…`).
- **Consumidores implementados** (plan §E): `useWidgets()` en la zona de widgets de Hoy (grilla 12 columnas:
  `sm`=3, `md`=6, `lg`=8, `full`=12; cada widget con `ErrorBoundary` + `Suspense`, uno roto no tumba el panel);
  `useReservationTabs()` y `useReservationActions()` en el detalle (las pestañas reciben `{reservationId}` con
  `?tab=<id>` en la URL; las acciones se abren en un diálogo y reciben `{reservationId, close}`).
- Componentes reutilizables (p. ej. para el panel lateral del calendario C13 o el copiloto):
  - `CheckInDialog` (`components/CheckInDialog.tsx`): `{open, onOpenChange, stayId, reservationId, onDone?}`.
  - `CheckOutDialog` (`components/CheckOutDialog.tsx`): mismas props.
  - `api.ts`: tipos (`TodayBoard`, `TodayRow`, `ReservationDetail`, `Offer`, `NightAuditReport`…), fetchers de
    bookings (`checkIn`, `checkOut`, `assignRoom`, `modifyStay`, `cancelReservation`…), hooks (`useToday`,
    `useReservation`, `useReservations`, `useRoomOptions`, `useOffers`…), `frontdeskKeys` (`['frontdesk', …]`),
    `bookingKeys` (`['bookings', …]`) y `useRefreshFrontDesk()` (invalida `frontdesk`, `bookings` y `finance`).
    **C13**: tras mover/crear en el calendario invaliden `['bookings']` y `['frontdesk']` para que Hoy se refresque.
  - `lib/units.ts` (unidades listas y libres, ocupación actual), `lib/quickViews.ts` (vistas rápidas ↔ filtros).
- Reutilizados de otras features: `GuestPicker` (B3) en el asistente y en acompañantes; `FolioPanel` (B4) compacto
  en check-in/check-out; `RoomKeyTag` (B1); `saveBlob` (B4) para el CSV.

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

1. **B2b / bookings (sugerido para C-INT o D)** — `check_in` solo mira el estado de limpieza: acepta una habitación
   limpia donde todavía está en casa el huésped que sale hoy (los periodos no se solapan), y
   `auto_assign_rooms` (06:00) asigna llegadas de hoy a esas habitaciones (en el seed actual: 207, 402, 104, camas de
   D1/D2/D4…). C1 lo mitiga en la UI (issue `room_occupied`, el check-in y el walk-in proponen una unidad libre),
   pero conviene que el backend responda 409 `room_occupied` (salvo `force`) cuando otra estadía `checked_in` ocupa
   la misma habitación/cama, y que la auto-asignación de llegadas de hoy prefiera unidades sin huésped saliente.
2. **A2 / tests compartidos (C-INT)** — `src/app/__tests__/shell.test.tsx` y `router.test.tsx` renderizan `/app`:
   Hoy ahora pide `GET /api/v1/frontdesk/today/` (y los widgets de C2/C5/C8 sus datos). Agregar handlers MSW vacíos
   con la forma de `TodayBoard` para que no salga `[MSW] Error … without a matching request handler`.
3. **C12** — el spec pide "alertas" en Hoy: llegarían como widget (`control/widgets.tsx`), que aún no existe. Las
   alertas propias de C1 (`overdue_departures`, `night_audit_errors`) ya se ven en el centro de alertas de C12 cuando
   exista.
4. `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]`: nada que agregar por C1 (el `status` del reporte se serializa
   como texto para no chocar con otros enums). Los 17 warnings actuales de `spectacular --validate` son de otras apps
   (messaging `GuestRef`/`UserRef`/`ReservationRef` vs finance, y enums `kind/status/language/mode`).

## Limitaciones conocidas / pendientes

- **Sin tests nuevos** (modo MVP). Los tests heredados de intentos anteriores (`backend/apps/frontdesk/tests/`,
  `frontend/src/features/frontdesk/__tests__/`) no se corrieron ni se actualizaron (salvo agregar `occupied_by` al
  fixture `makeRow` para que compile); pueden fallar por los cambios de esta sesión (issue `room_occupied`, helpers
  movidos a `lib/`).
- El historial de cierres está vacío en la BD de desarrollo hasta que corra el seed (ver "Cómo probarlo", paso 8).
- Cerrar el día antes de medianoche marca como no-show las llegadas pendientes de hoy (es la semántica del cierre;
  la vista previa y la confirmación lo dicen).
- La detección de "habitación aún ocupada" en los diálogos usa el tablero Hoy (`frontdesk.view`); un rol con
  `bookings.checkin` sin `frontdesk.view` no la ve (el backend tampoco la bloquea, ver cambio 1).
- El asistente crea reservas de **una** estadía (una categoría); varias habitaciones o grupos van por la API de
  bookings (`groups/`, `stays` múltiples) o el calendario. En dormitorios B2b divide en una estadía por cama y el
  walk-in hace check-in de todas.
- Llaves de dormitorio en el tablero: solo conteos por cama y abren el calendario (sin acción por cama).
- Algunos importes de la historia de cierres usan COP por defecto en `MoneyText` (todas las propiedades demo son COP).
- "Otros ingresos del día" en el demo está dominado por 4 penalidades no reembolsables creadas y canceladas hoy por
  el seed (documentado en B-INT); el KPI es correcto por definición.

## Cambios de esta sesión (sobre el trabajo heredado)

- **Backend**: issue `room_occupied` + `occupied_by` en las llegadas de Hoy (antes una llegada asignada a una
  habitación limpia con el huésped saliente adentro salía como "Lista"); el resumen de la automatización manual
  mostraba la fecha de negocio vieja (instancia sin refrescar) y el cálculo de "aún quedan días" podía quedar
  desfasado tras 7 días de recuperación.
- **Frontend**: los diálogos de check-in y de asignar habitación marcan las unidades con huésped en casa ("Ocupada ·
  nombre"), no las proponen y separan lo que exige `force` en el backend (tentativa, llegada tardía, habitación sin
  limpiar) de las advertencias (habitación ocupada); el walk-in asigna una unidad limpia y libre a **cada** estadía
  (antes solo hacía check-in de la primera, sin elegir habitación); chip "Hab. aún ocupada"; chip "Check-in online
  listo"; insignia del grupo en el encabezado del detalle; confirmación del cierre más explícita; moneda de la propiedad en el resumen del cierre; eslint limpio
  (helpers movidos de componentes a `lib/units.ts`, `lib/stays.ts` y `lib/wizard.ts`).

## Verificación (sin tests, modo MVP)

- `docker compose exec -T backend python manage.py check` → "System check identified no issues" (un intento
  intermedio falló por `apps/compliance/codes.py` a medio escribir por C7, y el runserver cayó un momento (502) por
  `apps/ai/api/serializers.py` de C9; al reintentar, todo limpio: no eran errores de C1).
- `makemigrations frontdesk --check --dry-run` → "No changes detected in app 'frontdesk'".
- `ruff check apps/frontdesk` → "All checks passed!"; `ruff format --check apps/frontdesk` → 27 archivos formateados.
- curl por el proxy (`http://localhost:5173/api/...`, cookie jar + CSRF, script propio en el scratchpad):
  - dueño Aurora: `today/` 200 (224 ms), `night-audit/preview/` 200, `reports/` 200, `reservations/export/` 200
    (CSV con 18 filas en casa), `online-checkin/` 200.
  - dueño Andino (Hostel y Medellín): los mismos 200; Hostel con camas (`D3/C7`).
  - `recepcion@casaaurora.co`: `today/` 200, `preview/` **403** `frontdesk.night_audit`, `reports/` 200, export 200.
  - `limpieza@casaaurora.co`: todo **403**.
- Auditoría en **una transacción revertida** (APIClient + `automation.run`, shell de Django): programada → `skipped`
  (fecha al día); manual → `success`, 12 noches publicadas una sola vez (0 duplicadas, 0 faltantes), 2 no-shows,
  6 salidas vencidas con alerta, fecha → 2026-09-28; repetir → `skipped` sin cerrar otro día; API → 201, 200 (mismo
  reporte), 409 `audit_ahead`, 409 `business_date_changed`, recepción 403; recuperación de 2 días atrasados → cierra
  09-25 y 09-26. Tras el rollback: fechas de negocio intactas (2026-09-27) y 0 reportes.
- Seed (`apps/frontdesk/seed.py`) dos veces en una transacción revertida: 90 reportes (30 por propiedad, del
  2026-08-28 al 2026-09-26, ninguno ≥ fecha de negocio) en **7,0 s**; la segunda corrida no crea nada (0,00 s).
- Frontend: `npx tsc -p tsconfig.app.json --noEmit | grep src/features/frontdesk` → sin salida;
  `npx eslint src/features/frontdesk` → sin problemas (antes 7 errores `react-refresh/only-export-components`).
  Claves i18n: 443 en ES y EN, sin diferencias; todas las claves usadas existen. Los 38 módulos de la feature
  cargan en el dev server de Vite (`curl http://localhost:5173/src/features/frontdesk/...` → 200).
