# C3 — Distribución (channel manager) — integration notes

Estado: **backend y frontend completos en modo MVP y verificados de punta a punta** (2026-09-27). Esta pasada retomó el
trabajo parcial de dos intentos anteriores (backend casi completo, frontend con 4 archivos): se revisó y corrigió el
backend, se construyó todo el frontend (`/app/channels` y `/app/simulators/ota`) y se escribió esta nota.

Modo MVP (decisión del usuario): **no se escribieron ni se corrieron tests** en esta fase. Los tests que dejaron los
intentos anteriores (`backend/apps/distribution/tests/`, `frontend/src/features/channels/__tests__/`) siguen en su
sitio sin correr; ver "Para la fase de tests".

Owner paths: `backend/apps/distribution/**`, `frontend/src/features/channels/**` y esta nota. No se tocó nada más.

---

## Resumen en una pantalla

- **Salida (ARI)**: los receivers de `inventory_changed` y `rates_changed` encolan un `AriUpdate` por (conexión,
  categoría) que acumula la unión de rangos y tipos (coalescencia) → push Celery con `countdown=5 s` (debounce) +
  automatización `distribution.push_ari` cada minuto. Los valores se calculan al enviar: disponibilidad de
  `InventoryDay` (nunca negativa), precio por noche con `rates.resolve_daily` (derivados resueltos) × (1 + recargo),
  restricciones del plan base. Plan borrado / inactivo / no público / no habilitado para el canal / noche sin precio →
  la tarifa viaja **cerrada** (stop-sell). Reintentos con backoff (30 s, 2 min, 8 min, 30 min) y, tras 5 fallos,
  alerta crítica `channel_sync_failed` + conexión en `error`.
- **Entrada**: `services.importer.import_booking(connection, InboundBooking)` es el único camino (simulador, feed de
  Channex, eventos iCal). Idempotente por `(conexión, external_id)` + SHA-256 del payload. Nueva →
  `create_reservation(source="ota", channel_code, external_id, enforce_restrictions=False, allow_overbooking=True,
  guarantee="ota", nightly_rates del canal)`; modificación → `modify_stay(reprice=False)`; cancelación →
  `cancel_reservation(waive_fee=True, source="channel")`. Faltó unidad → la reserva entra igual y bookings levanta la
  alerta `overbooking`. Error → log + alerta `channel_import_failed` (se resuelve sola con el siguiente import bueno).
- **iCal**: exportación pública por token secreto (categoría o habitación) y importación periódica (real: HTTPS con
  protección SSRF; simulado: solo calendarios exportados por Housetel).
- **Channex**: adaptador real básico según docs.channex.io (ARI por `POST /availability` y `POST /restrictions`,
  reservas por `GET /booking_revisions/feed` + `POST /booking_revisions/:id/ack`) y uno simulado sin internet.
- **Simulador de OTAs**: BookSim y AirSim (y Channex simulado) viven en la BD (`SimOtaInventory`, `SimOtaBooking`):
  muestran el ARI recibido y venden solo lo que recibieron; sus reservas entran al PMS por `import_booking`.

---

## API implementada

Staff: `/api/v1/distribution/…` con sesión + `X-Property-Id` (reglas de tenancy de A1). `distribution.view` para los
GET, `distribution.manage` para todo lo demás (incluido crear reservas en el simulador). Errores `{detail, code,
fields?, …}`. Los campos de opciones se exponen como **strings** (sin enums en OpenAPI → sin colisiones de nombres).

| Método y path | Permiso | Respuesta |
|---|---|---|
| `GET connections/` | view | lista plana (sin paginar) de `Connection` con `stats` |
| `POST connections/` | manage | 201 `Connection` + `sync` (resumen de la sync completa o `null`) |
| `GET connections/{id}/` | view | `Connection` |
| `PATCH connections/{id}/` | manage | `Connection` + `sync`. Una lista de mapeos **reemplaza** la actual (ítems con `id` se conservan) |
| `DELETE connections/{id}/` | manage | 204 (las reservas quedan en el PMS) |
| `POST connections/{id}/test/` | manage | `{ok, message}` (también guarda el estado de la integración iCal/Channex) |
| `POST connections/{id}/full-sync/` | manage | `{sent, retrying, failed, connections}` (365 días, síncrono). 409 `connection_paused`; 400 `not_supported` (iCal) |
| `POST connections/{id}/pause/` | manage | `Connection` |
| `POST connections/{id}/resume/` | manage | `{connection, sync}` (hace sync completa en canales push) |
| `POST connections/{id}/pull/` | manage | iCal: `{created, modified, cancelled, unchanged, failed, skipped, calendars}`; Channex: `{created, modified, cancelled, unchanged, ignored, failed, acknowledged, errors, connections}`. 400 `not_supported` (BookSim/AirSim entregan solas); 409 `connection_paused` |
| `GET logs/` | view | paginado `SyncLog`. Filtros: `connection`, `direction` (`in`/`out`), `status` (repetible: `success, warning, error, skipped`), `kind`, `reservation`, `date_from`, `date_to` (inclusivos), `q` (mensaje o código externo) |
| `GET queue/` | view | paginado `AriUpdate`. Filtros `connection`, `status` (repetible: `pending, sending, sent, failed`) |
| `POST queue/retry/` | manage | `{connection?}` → fallidas a pendientes y envía **ya** todo lo pendiente (ignora el backoff): `{retried, sent, retrying, failed, connections}`. La UI lo usa como "Enviar ahora" |
| `GET options/` | view | todo lo que necesita el asistente (abajo) |
| `GET options/catalog/?channel=booksim\|airsim\|channex` | view | `{rooms:[{id,title}], rates:[{id,title,room_id,currency}]}`: sugeridos (`BS-DBL`, `BS-FLEX`) o, con Channex real, los de la API de Channex (502/400 con el `code` del error) |
| `GET simulator/{connection_id}/inventory/?start&end` | view | grilla de lo que tiene la OTA (por defecto 14 noches desde la fecha de negocio; máx. 62). 400 `not_simulated` si la conexión es real |
| `GET simulator/{connection_id}/bookings/` | view | paginado `OtaBooking` (más nuevas primero) con la reserva del PMS |
| `POST simulator/{connection_id}/bookings/` | manage | 201 `OtaBooking`. 409 `ota_not_sellable` + `reasons[]`; 400 `not_simulated`, `unknown_room`, `unknown_rate`, `invalid_dates`, `invalid_occupancy` |
| `POST simulator/{connection_id}/bookings/{external_id}/modify/` | manage | nueva revisión → `OtaBooking` (mismos errores; `force` para sobreventa) |
| `POST simulator/{connection_id}/bookings/{external_id}/cancel/` | manage | revisión `cancelled` → `OtaBooking`. 409 `booking_cancelled` |
| `POST simulator/{connection_id}/bookings/{external_id}/deliver/` | manage | reentrega la revisión actual al PMS (idempotente) |

Pública (sin sesión): `GET /api/v1/public/distribution/ical/<token>.ics` → `text/calendar` (404 token desconocido;
throttle 120/min; `Cache-Control: private, max-age=300`). La URL completa la da `room_mappings[].ical_export_url`
(`FRONTEND_URL` + path, pasa por el proxy de Vite).

### `Connection` (respuesta real, recortada)

```json
{
  "id": "465f792c-…", "channel_code": "booksim", "channel_label": "BookSim", "name": "BookSim",
  "status": "active", "mode": "simulated", "delivery": "push", "simulated": true, "settings": {},
  "last_sync_at": "2026-09-27T16:21:46-05:00", "last_error": "",
  "room_mappings": [{"id": "…", "room_type": "<uuid>", "room_type_code": "DBL",
    "room_type_name": {"es": "Estándar", "en": "Standard"}, "room": null, "room_number": null,
    "external_room_id": "BS-DBL", "ical_import_url": "", "ical_export_url": null,
    "ical_last_sync_at": null, "ical_last_error": ""}],
  "rate_mappings": [{"id": "…", "rate_plan": "<uuid>", "rate_plan_code": "FLEX",
    "rate_plan_name": {"es": "Tarifa flexible", "en": "Flexible rate"}, "room_type": null, "room_type_code": null,
    "external_rate_id": "BS-FLEX", "markup_percent": "15.00"}],
  "stats": {"pending_updates": 0, "failed_updates": 0, "reservations": 99, "errors_24h": 0, "in_errors_24h": 0,
            "last_out_at": "2026-09-27T21:21:46Z", "last_in_at": "2026-09-27T21:21:41Z"},
  "integration": null
}
```

- `delivery`: `push` (la OTA envía sus reservas: BookSim/AirSim), `pull` (el PMS las descarga: Channex) o `ical`.
- `simulated`: la sirve el simulador de OTAs (BookSim, AirSim, Channex en modo simulado).
- `integration` (solo iCal/Channex): `{kind, mode, enabled, config (no secreta), secrets: ["api_key"]}` — los
  secretos **nunca** se devuelven, solo sus nombres.
- `rate_plan: null` = el plan se borró: el canal recibe esa tarifa cerrada hasta que se re-mapee.

### Crear / editar (`POST` / `PATCH connections/`)

```json
{
  "channel_code": "channex",                  // solo al crear: booksim | airsim | ical | channex
  "name": "Channex",
  "mode": "simulated",                        // iCal/Channex: real | simulated (se guarda para toda la propiedad)
  "integration": {"config": {"environment": "staging", "property_id": "<uuid Channex>"},
                  "secrets": {"api_key": "…"}},   // solo Channex real; "" conserva el secreto guardado
  "settings": {"import_all_events": false},   // solo iCal
  "room_mappings": [{"id": "<opcional>", "room_type": "<uuid>", "room": null,
                     "external_room_id": "CX-DBL", "ical_import_url": ""}],
  "rate_mappings": [{"id": "<opcional>", "rate_plan": "<uuid>", "room_type": "<uuid o null>",
                     "external_rate_id": "CX-FLEX-DBL", "markup_percent": "10"}],
  "full_sync": true                           // enviar ya 365 días (si no, viaja con la cola)
}
```

Validaciones (400 `validation_error` con `fields.room_mappings` / `rate_mappings` / `settings` / `integration`):
categoría/plan de otro hotel, códigos repetidos o vacíos (salvo iCal), habitaciones sueltas solo en iCal, URL de
importación solo en iCal (https/webcal, sin redes internas), tarifas no permitidas en iCal, recargo entre −90 y 300.
BookSim/AirSim/Channex: una conexión por propiedad (409 `channel_already_connected`); iCal: varias (una por portal).

### `options/` (recortado)

```json
{
  "channels": [{"code": "booksim", "label": "BookSim", "delivery": "push", "pushes_ari": true,
                "modes": ["simulated"], "multiple": false, "connected": true, "integration": null}, …],
  "room_types": [{"id": "…", "code": "DBL", "name": {…}, "kind": "private", "color": "#4E6C88", "is_active": true,
                  "rooms": [{"id": "…", "number": "101"}, …]}],
  "rate_plans": [{"id": "…", "code": "FLEX", "name": {…}, "kind": "base", "room_types": ["…"], "is_public": true,
                  "is_active": true, "channels": [],
                  "sample": {"room_type": "…", "room_type_code": "DBL", "date": "2026-09-27", "price": "320000.00"},
                  "samples": [{"room_type": "…", "room_type_code": "DBL", "date": "2026-09-27", "price": "320000.00"},
                              {"room_type": "…", "room_type_code": "SUP", "date": "2026-09-27", "price": "420000.00"}]}],
  "integrations": {"channel_channex": {"kind": "channel_channex", "mode": "simulated", "enabled": true,
                   "config": {}, "secrets": [], "fields": [/* CONFIG_FIELDS del proveedor real */]},
                   "channel_ical": {…}},
  "currency": "COP", "business_date": "2026-09-27"
}
```

### Simulador

`GET simulator/{id}/inventory/?start=2026-10-10&end=2026-10-12`:

```json
{"connection": {"id": "…", "name": "BookSim", "channel_code": "booksim", "ota": "BookSim", "delivery": "push"},
 "start": "2026-10-10", "end": "2026-10-12", "currency": "COP", "dates": ["2026-10-10", "2026-10-11"],
 "rooms": [{"external_room_id": "BS-DBL",
            "room_type": {"id": "…", "code": "DBL", "name": {…}, "kind": "private", "color": "#4E6C88"},
            "rates": [{"external_rate_id": "BS-FLEX", "rate_plan": {"id": "…", "code": "FLEX", "name": {…}},
                       "markup_percent": "15.00",
                       "cells": [{"date": "2026-10-10", "available": 5, "price": "368000.00", "min_los": null,
                                  "max_los": null, "closed_to_arrival": false, "closed_to_departure": false,
                                  "stop_sell": false}, null]}]}],
 "last_update": "2026-09-27T16:21:46-05:00"}
```

`cells[i] = null` = la OTA nunca recibió esa noche. Una categoría sin tarifas mapeadas tiene una fila con
`external_rate_id: ""` (solo disponibilidad).

`POST simulator/{id}/bookings/`:

```json
{"external_room_id": "BS-DBL", "external_rate_id": "BS-FLEX", "checkin": "2026-11-03", "checkout": "2026-11-05",
 "adults": 2, "children": 0, "guest": {"first_name": "…", "last_name": "…", "email": "…", "country": "US"},
 "notes": "", "force": false}
→ 201 {"id": "…", "external_id": "BS-7508321", "status": "new", "revision": 1, "pms_status": "imported",
       "pms_message": "Reserva HT-MVBTM3 creada",
       "payload": {"ota": "BookSim", "guest": {…}, "rooms": [{"external_room_id": "BS-DBL", "external_rate_id": "BS-FLEX",
                   "checkin": "2026-11-03", "checkout": "2026-11-05", "adults": 2, "children": 0,
                   "nightly_rates": [{"date": "2026-11-03", "amount": "368000.00"}, …]}],
                   "currency": "COP", "total": "736000.00", "notes": "", "forced": false},
       "reservation": {"id": "…", "code": "HT-MVBTM3", "status": "confirmed"}, …}
```

- Sin `guest` la OTA inventa uno (60 % colombiano). En dormitorios cada huésped es una cama y `nightly_rates` es el
  total por noche (B2b lo reparte por cama).
- La OTA solo vende lo que recibió: cada noche con celda, precio, unidades (camas por huésped en dorm) y sin stop-sell;
  CTA/min/max LOS de la noche de llegada y CTD de la salida. Si no → 409 `ota_not_sellable` con `reasons` (texto en
  español). `force: true` la crea igual (sobreventa simulada).
- Modificar solo re-chequea las noches nuevas; las noches que ya tenía conservan su precio.
- BookSim/AirSim entregan cada revisión al PMS al momento; el Channex simulado la deja `pms_status=pending` hasta que el
  PMS descarga el feed (`POST connections/{id}/pull/` o la automatización).

---

## Contratos implementados / consumidos

Consumidos (solo por sus servicios): `bookings.services.reservations.create_reservation / modify_stay /
cancel_reservation`, `bookings.services.availability.availability_by_date` (lectura), `rates.services.quote.
resolve_daily`, `core.audit.record`, `core.alerts.raise_alert/resolve_alert`, `core.integrations.*`,
`core.automation.register`, `core.signals`, `core.money`, `core.dates`. Lectura ORM de `RoomType`, `Room`, `Bed`,
`RatePlan`, `Stay`, `RoomBlock`, `Reservation` (permitido por el plan §B).

Servicios de distribución que otra app puede llamar (no hace falta en la Fase C):
- `apps.distribution.services.queue.enqueue_ari(property, *, room_type_ids=None, start=None, end=None,
  kinds=("availability","rates","restrictions"), rate_plan_ids=None, connection=None, schedule=True)`.
- `apps.distribution.services.importer.import_booking(connection, InboundBooking, *, actor=None)` → `ImportResult`.
- `apps.distribution.services.queue.full_sync(connection, *, actor=None)`.

Tipos: `apps/distribution/types.py` (`AriBatch`, `AriRate`, `AriRateDay`, `InboundBooking`, `InboundRoom`,
`ImportResult`).

## Señales emitidas / escuchadas

Escuchadas (`receivers.py`, todas con `if is_seeding(): return`):
- `inventory_changed` → `enqueue_ari(kinds=availability)` (incluye `origin="bookings"`: son justo las reservas que los
  canales deben conocer). Rango acotado a `[business_date, business_date + 365)`.
- `rates_changed` → `enqueue_ari(kinds=rates+restrictions, rate_plan_ids)` (se ignora si ningún mapeo usa esos planes).
- Django `pre_delete` de `RatePlan` (solo se escucha): al borrar un plan mapeado se encola su cierre en el canal
  (B2a no emite `rates_changed` al borrar planes).

Emitidas: ninguna propia. Los servicios de bookings emiten `reservation_created/updated/cancelled` e
`inventory_changed` cuando se importa una reserva de canal.

Auditoría (`AuditEvent.action`): `distribution.connection_created`, `connection_updated`, `connection_deleted`,
`connection_paused`, `connection_resumed`, `full_sync`, `integration_configured` (sin secretos). Las reservas
importadas se auditan en bookings con `source="channel"` y el nombre del canal como etiqueta.

Alertas (`kind` · `dedupe_key`): `channel_sync_failed` · `distribution:ari:<conexión>` (crítica);
`channel_import_failed` · `distribution:import:<conexión>:<external_id>` (crítica); `ical_import_failed` ·
`distribution:ical:<mapeo>` (warning); `channel_pull_failed` · `distribution:pull:<conexión>` (warning). La de
sobreventa la levanta bookings (`overbooking` · `bookings:overbooking:<reserva>`). Todas se resuelven solas con el
siguiente intento bueno.

## Automatizaciones registradas

| Código | Horario | Qué hace |
|---|---|---|
| `distribution.push_ari` | cada minuto | envía la cola de ARI (lo que el push con debounce no alcanzó, reintentos vencidos). `skipped` si no hay nada |
| `distribution.pull_ical` | cada 15 min | importa los calendarios iCal remotos; los eventos que desaparecen cancelan su reserva (solo si aún no empezó y el calendario no llegó vacío) |
| `distribution.pull_bookings` | cada 5 min | **(extra al spec §6)** descarga y confirma las revisiones del feed de Channex (real o simulado) |

Además: tarea Celery `distribution.push_ari_queue(property_id)` (la programa el debounce, `countdown=5`).
Verificadas con `automation.run` manual (sin trabajo → `skipped`; con cola, calendario y feed pendientes → `success`,
dentro de una transacción revertida).

## Proveedores de integración registrados

| Kind | Modo | Clase | Qué hace |
|---|---|---|---|
| `channel_ical` | `real` | `RealIcalProvider` | descarga por HTTPS (`webcal://` → `https://`), timeout 15 s, máx. 5 MB, redirecciones verificadas; rechaza loopback/privadas/link-local y hosts internos |
| `channel_ical` | `simulated` | `SimulatedIcalProvider` | sin internet: solo lee calendarios exportados por Housetel (los demás quedan "omitidos" con aviso) |
| `channel_channex` | `real` | `RealChannexProvider` | `CONFIG_FIELDS`: `environment` (staging/production), `property_id`, secreto `api_key`. Header `user-api-key`. ARI por noche (`date`) a `POST /availability` y `POST /restrictions` (`rate` como string decimal; `min_stay_arrival` ≥ 1; `max_stay` 0 = sin máximo; booleanos CTA/CTD/stop_sell), `meta.warnings` → log warning. Reservas: `GET /booking_revisions/feed?filter[property_id]&order[inserted_at]=asc&pagination[limit]=100` + `POST /booking_revisions/:id/ack` (solo las aplicadas; las fallidas quedan en el feed). Catálogo: `/room_types/options` y `/rate_plans/options`. `test_connection` lista `/properties`. Errores: 401/403/404 no reintentables; 429/5xx/red reintentables |
| `channel_channex` | `simulated` | `SimulatedChannexProvider` | ARI al simulador y feed de `SimOtaBooking` pendientes |

BookSim/AirSim no tienen kind propio: los sirve `SimulatedOtaProvider` (interno). El modo iCal/Channex es por
propiedad (`IntegrationSetting`); el asistente de Canales lo cambia y C12 también podrá (Configuración →
Integraciones).

Verificado contra docs.channex.io (2026-09-27): endpoints, formato de `values`, `rate` string/entero en unidades
mínimas, `meta.warnings`, feed/ack y atributos de la revisión (`booking_id`, `revision_id`, `status`
new/modified/cancelled, `customer{name,surname,mail,phone,country,language}`, `rooms[]{room_type_id, rate_plan_id,
checkin_date, checkout_date, occupancy{adults,children,infants}, days, amount}`, `arrival_hour`, `ota_name`,
`ota_reservation_code`).

## Extensiones de frontend exportadas

- `routes.tsx`: `/app/channels` y `/app/simulators/ota` (lazy). `nav.ts` sin cambios (Canales en Ingresos con
  `distribution.view`; Simulador de OTAs en Herramientas con `distribution.manage`).
- No exporta widgets, tabs, acciones, topbar ni comandos.
- Piezas reutilizables (import directo): `features/channels/api.ts` (tipos + hooks `useConnections`,
  `useChannelOptions`, `useSyncLogs`, `useAriQueue`, `useSimInventory`, `useSimBookings`, `useChannelCatalog`,
  `useChannelsMutation`), `components/ChannelMark` (insignia BS/AS/CX/iCal) y `components/SyncLanes` (los dos
  "cables" de estado de una conexión), `lib/channels.ts` (`channelPrice` idéntico al backend, `otaQuote`, borrador del
  asistente).

### Páginas

- `/app/channels`: pestañas **Conexiones** (tarjetas con estado, modo, recargo, cables "Disponibilidad y tarifas" →
  / ← "Reservas" con su estado y hora, URLs iCal con "Copiar URL", acciones Probar / Simulador / Descargar o Importar /
  Sincronizar todo / Editar / Pausar-Reanudar / Eliminar; tarjeta "Conectar otro canal"), **Registro** (filtros por
  conexión, dirección, resultado y texto; detalle con payload y enlace a la reserva) y **Cola de envíos** (estado,
  rango, tipos, intentos, "Enviar ahora"). Asistente en hoja lateral: canal → conexión (nombre, modo, credenciales de
  Channex, opción iCal) → mapeo (categorías con código o URL iCal; tarifas con código, recargo y vista previa "Hoy en
  DBL: $ 320.000 → $ 368.000", aviso si el plan le llegará cerrado; catálogo de Channex real) → confirmar (con sync de
  365 días). Se refresca sola (tarjetas 15 s, cola 5 s, registro 15 s).
- `/app/simulators/ota`: selector de OTA y una ventana de la extranet de la OTA (barra de dirección
  `extranet.booksim.test/<hotel>`). **Lo que ve la OTA**: grilla habitación × tarifa × noche (unidades, precio con
  recargo, 2n/CTA/CTD, cerrada/agotada/sin datos), se refresca cada 5 s y **las celdas que un push acaba de cambiar
  brillan** (con movimiento reducido: contorno fijo); tocar una noche a la venta abre la reserva prellenada.
  **Reservas de la OTA**: crear (vista previa de lo que cobra la OTA; si la rechaza, motivos + "Forzar (simular
  sobreventa)"), modificar, cancelar, reentregar, "Descargar en el PMS" (Channex simulado), enlace a la reserva del PMS
  con su estado. Solo para `distribution.manage` (los demás ven un aviso).

## Dependencias nuevas (pip/npm) y por qué

Ninguna (`httpx`, `icalendar`, TanStack Query, Radix ya estaban).

## Cambios requeridos en archivos compartidos u otras apps

1. **C-INT: reiniciar `worker` y `beat`** (`docker compose restart worker beat`) después de integrar. Hoy ambos
   arrancaron (10:10) con una versión vieja del WIP: beat **no programa** ninguna `distribution.*` y el worker tiene en
   memoria el código del primer intento (sin proveedores iCal/Channex registrados). En esta sesión el push con debounce
   de BookSim/AirSim sí funcionó con el worker viejo; un push de Channex por el worker viejo fallaría hasta reiniciarlo.
   Mientras tanto la UI tiene "Enviar ahora" (cola) y "Sincronizar todo", que envían en el proceso web.
2. **C-INT: lista de automatizaciones de beat**: sumar `distribution.pull_bookings` (cada 5 min) a las del spec §6.
3. Sin cambios de settings: los choices se exponen como strings (no hay enums nuevos en OpenAPI; verificado que
   `spectacular --validate` no reporta nada de distribución).
4. **Seed**: `SEED_ORDER` ya tiene `distribution` después de `finance`. El seed de C3 (abajo) ya está **aplicado en la
   BD de desarrollo** (se probó antes en una transacción revertida); `seed_demo --reset` lo recrea.

## Seed (`apps/distribution/seed.py`, idempotente: se omite la propiedad que ya tiene conexiones)

- Por propiedad con categorías (Casa Aurora, Andino Medellín y Andino Hostel): **BookSim** (+15 %) y **AirSim**
  (+12 %) simulados, mapeados categoría por categoría (`BS-DBL`, `AS-FLEX`…) con los planes FLEX, NR y BB, y la
  **sincronización completa explícita** de 365 noches (`SimOtaInventory`). Mientras corre el seed los receivers no hacen
  nada (`is_seeding()`), así las miles de señales históricas de bookings nunca llegan a la cola.
- Andino Hostel Bogotá: además **Airbnb (iCal)** con un calendario exportado por categoría.
- Las reservas OTA del seed de bookings (`source="ota"`, `booksim`/`airsim`) quedan vinculadas en
  `ExternalReservationMap` (con el hash del payload que enviaría la OTA) y aparecen como reservas del simulador ya
  importadas (`SimOtaBooking`; un grupo de dorm = una habitación del canal con todas sus camas).
- Prueba con rollback sobre el demo completo: **4,4 s**; 7 conexiones, 27 mapeos de categoría, 18 de tarifa, 22
  envíos de ARI, 24.090 celdas de OTA, 867 reservas vinculadas (Aurora 193/193, Medellín 334/334, Hostel 340/340);
  segunda corrida 0,0 s sin cambios. Aplicado después en la BD de desarrollo (6 s).

## Limitaciones conocidas / pendientes

- Channex real es básico: un valor por noche (sin comprimir rangos `date_from/date_to`) en una sola llamada por
  endpoint; sin precios por ocupación (`rates[]`), sin webhooks (se lee el feed cada 5 min) y sin probar contra el
  sandbox real (no hay credenciales en `.env`). Un hotel grande con muchas tarifas podría chocar con el límite de 10
  llamadas/min o 10 MB por llamada de Channex.
- Una modificación que cambia el número de habitaciones (o de huéspedes de dormitorio) no se aplica sola: falla con
  `manual_modification_required` + alerta. Las noches nuevas de una modificación toman el precio del PMS
  (`modify_stay(reprice=False)` no acepta precios del canal).
- El simulador vende una habitación por reserva (el adaptador de Channex real sí soporta varias).
- iCal: importa con huésped genérico "Huésped <canal>" y precio del PMS; en modo simulado solo lee calendarios de
  Housetel (un calendario de categoría con varias unidades exporta "No disponible", que se trata como bloqueo salvo
  `import_all_events`); la protección SSRF no resuelve DNS (un dominio público que apunte a una IP interna pasaría).
- Una reserva de canal sobre una tarifa cuyo plan se borró se importa con otro plan que venda la categoría (los
  precios son los del canal); la tarifa se sigue enviando cerrada.
- Los códigos externos de las reservas OTA del seed de bookings (`BO-…`, `AI-…`) no siguen el formato de las nuevas del
  simulador (`BS-…`, `AS-HM…`): cosmético.

## Para la fase de tests

- Tests existentes sin correr en esta fase: `backend/apps/distribution/tests/` (api, ari, automations, channex con
  respx, ical export/import con fixtures `.ics`, import, push, queue, seed, simulator) y
  `frontend/src/features/channels/__tests__/channels-lib.test.ts`.
- Cambios de comportamiento de esta pasada que algún test viejo puede no esperar: `POST/PATCH connections/` devuelven
  además `sync`; `options.rate_plans[]` trae `samples` y `sample` ahora incluye `room_type_code` (rompe la aserción exacta de `test_api.py:467`; `sample` es opcional en el tipo TS); el asistente envía
  `full_sync: true` también al editar (antes solo al crear); una reserva sobre una tarifa de plan borrado se importa
  con un plan de respaldo en vez de fallar `unmapped_rate`.
- Casos del plan a cubrir: coalescencia de la cola; derivado + recargo; import idempotente / modificación /
  cancelación; overbooking con alerta; export iCal (checkout exclusivo) e import con cancelación por desaparición;
  Channex con respx; ciclo del simulador (BookSim → reserva `ota`; cambio de tarifa → `SimOtaInventory`); permisos.

---

## Cómo probarlo en la UI

Prerrequisitos: stack arriba, seed completo (el de C3 ya está aplicado en la BD de desarrollo; tras un
`seed_demo --reset` se recrea) y, para que el ARI viaje solo tras un cambio, **worker y beat reiniciados** después
de C-INT (si no, usar "Enviar ahora" en la cola o "Enviar N cambios pendientes" en el simulador). Todo en
`http://localhost:5173`.

1. **Canales** — entra con `owner@casaaurora.co` / `housetel123` (Hotel Casa Aurora) → menú Ingresos → **Canales**
   (`/app/channels`). Esperado: tarjetas **AirSim** y **BookSim** con "Activa" + "Simulado", "3 categorías · 3 tarifas
   · recargo +12 %/+15 %", cables "Disponibilidad y tarifas — Al día" y "Reservas — Recibiendo", "~97 reservas de este
   canal", y la tarjeta punteada "Conectar otro canal" (iCal y Channex).
2. **Registro y cola** — pestaña **Registro**: entradas "Disponibilidad y tarifas" (↗ Enviado) e "Historial vinculado"
   (↙ Recibido); filtra por AirSim / Recibido / Error; clic en una entrada → hoja con el payload JSON y, si es una
   reserva, "Abrir la reserva HT-…". Pestaña **Cola de envíos**: filas "Enviada" con rango y "Disponibilidad"/
   "Tarifas"; botón **Enviar ahora** → toast.
3. **Reserva desde la OTA → PMS** — botón **Simulador de OTAs** (o menú Herramientas → Simulador de OTAs,
   `/app/simulators/ota`) → chip **BookSim**. Esperado: ventana "Extranet de BookSim" con la dirección
   `extranet.booksim.test/casa-aurora`, "Último ARI recibido hace …" y la grilla: BS-DBL/BS-SUP/BS-STE con unidades
   libres y tarifas BS-FLEX/NR/BB a precio del plan +15 % (p. ej. DBL FLEX entre semana **$ 368.000** = 320.000 × 1,15).
   Toca un precio de una noche futura → diálogo "Nueva reserva en BookSim" prellenado con la vista previa verde "La OTA
   la vende: 1 noche · $ 368.000" → **Reservar en BookSim**. Esperado: toast "BS-xxxxxxx reservada en la OTA → HT-XXXXXX
   en el PMS" con **Ver reserva**, y la pestaña "Reservas de la OTA" muestra la reserva "Nueva" con "En el PMS:
   HT-XXXXXX · Confirmada". "Ver reserva" abre `/app/reservations/<id>` con fuente OTA, canal booksim y el código
   externo.
4. **Sin sobreventa entre canales (ARI → OTA)** — cambia al chip **AirSim** y ve a la semana de esa noche (flechas).
   Esperado: en ≤ ~10 s las unidades de AS-DBL en esas noches bajan en 1 y las celdas **brillan** un instante (la
   grilla se refresca sola cada 5 s).
5. **Cambio de tarifa en el PMS → la OTA lo recibe** — menú **Tarifas** (`/app/rates`), plan Tarifa flexible, cambia
   el precio de Estándar en una noche futura (p. ej. 400.000). Vuelve al simulador → BookSim, misma noche. Esperado: en
   ≤ ~10 s la celda BS-FLEX muestra **400.000 × 1,15 = $ 460.000** (y NR/BB se recalculan) y brilla. (Deshaz el cambio
   después con el botón Deshacer de la grilla si está disponible.)
6. **Modificar y cancelar** — en "Reservas de la OTA" → **Modificar** la reserva del paso 3 (sal un día después) →
   "Enviar el cambio" → la fila queda "Modificada · revisión 2" y la reserva del PMS con la nueva salida. **Cancelar** →
   confirmar → fila "Cancelada", reserva del PMS "Cancelada" y la disponibilidad vuelve en AirSim.
7. **Sobreventa simulada** — en la grilla de BookSim busca una noche con **0** unidades (celda roja; los precios salen
   tachados y no son clicables) → "Nueva reserva" con esa noche. Esperado: la vista previa dice "La OTA no puede
   venderla así"; al reservar, "BookSim rechazó la reserva" con motivos → **Forzar (simular sobreventa)** → la reserva
   entra al PMS (fila con insignia "Forzada") y aparece la alerta de sobreventa en **Alertas**. (Cancélala después.)
8. **Asistente + Channex simulado (reservas por descarga)** — en Canales → **Conectar canal** → **Booking.com y
   Expedia (Channex)** → Nombre "Channex", modo **Simulado** → Continuar → Mapeo con códigos `CX-DBL`… y tarifas
   `CX-FLEX-DBL`… con vista previa "Hoy en DBL: $ 320.000 → …" (sube el recargo a 10 y mira el precio cambiar) →
   Continuar → **Conectar Channex**. Esperado: toast "Channex conectado: ya recibió 365 días…" y una tarjeta Channex con
   "Simulado" y el cable de reservas. En el simulador → chip Channex → nueva reserva → la fila queda "Esperando
   descarga" → **Descargar en el PMS** → toast "Reservas: 1 nuevas…" y la fila pasa a "Aplicada" con su HT-….
   (Elimínala después desde el menú ⋯ de la tarjeta si no la quieres en el demo.)
9. **iCal** — menú de propiedad → **Andino Hostel Bogotá** (o entra con `owner@grupoandino.co`) → Canales. Esperado:
   tarjeta **Airbnb** con 5 calendarios, cada uno con **Copiar URL**; abre la URL copiada en una pestaña → descarga un
   `.ics` (VEVENT de día completo, salida exclusiva, sin datos del huésped: "Reservado"/"Bloqueado" en categorías de
   una sola habitación, "No disponible" en dormitorios o categorías con varias unidades). Editar la conexión permite pegar una URL iCal de importación por categoría.
10. **Pausar / reanudar** — ⋯ de BookSim → **Pausar** → insignia "Pausada", cables en gris y el simulador avisa que no
    recibe cambios; **Reanudar** → toast "reanudado y sincronizado".
11. **Permisos** — `recepcion@casaaurora.co`: ve Canales (solo lectura: sin "Conectar canal", sin menú ⋯ ni botones) y
    no tiene "Simulador de OTAs" en el menú (si entra por URL ve el aviso). `limpieza@casaaurora.co`: no ve Canales.
12. **Móvil (375 px), oscuro e inglés** — las tarjetas se apilan; la grilla de la OTA se desplaza dentro de su marco sin
    scroll horizontal de página; el asistente ocupa todo el ancho. Tema oscuro e inglés (menú de idioma) cubiertos por
    tokens e i18n completos.

---

## Verificación (esta pasada, sin tests)

- `docker compose exec -T backend python manage.py check` → sin problemas; `makemigrations distribution --check
  --dry-run` → "No changes detected" (migración `0001_initial` aplicada); `ruff check` limpio en el código de la app
  (quedan 2 líneas largas en tests viejos).
- Seed en transacción revertida (script de B1/B-INT): 4,4 s, idempotente, conteos arriba; luego aplicado a la BD de
  desarrollo.
- Automatizaciones con `automation.run` manual: las 3 sin error (`skipped` sin trabajo; `success` con cola, calendario
  iCal y feed de Channex pendientes, dentro de una transacción revertida).
- Curl por el proxy de Vite (cookie jar + CSRF, `owner@casaaurora.co`), **todo OK**: connections, options, catalog,
  logs (con filtros), queue; grilla del simulador; reserva en BookSim → reserva OTA en el PMS con canal, código externo
  y **precio del canal respetado** (neto PMS = total OTA); **AirSim recibió la disponibilidad nueva (6 → 5) vía el
  push con debounce del worker**; reentrega idempotente; modificación (revisión 2, salida extendida en el PMS); 409
  `ota_not_sellable` con motivos para noches sin ARI; cancelación → reserva cancelada; **cambio de tarifa en la grilla
  → BookSim recibió 333.333 × 1,15 = 383.333** (revertido luego con `core.audit.undo`); test, full sync, pausa (409 al
  sincronizar pausada), reanudar; conexión iCal temporal → `.ics` público (y 404 al borrarla); Channex simulado
  temporal → reserva pendiente → pull `created=1, acknowledged=1` → cancelación descargada. Permisos: recepción 403
  `distribution.manage` al sincronizar/usar el simulador; limpieza 403 `distribution.view`; otra organización 404.
- Plan borrado (rollback): la tarifa pasa a `stop_sell` sin precio en la OTA, el simulador rechaza, una reserva forzada
  entra con plan de respaldo, el serializer muestra `rate_plan_code: null`.
- Frontend: `npx tsc -p tsconfig.app.json --noEmit | grep src/features/channels` → sin errores; `npx eslint
  src/features/channels` → limpio; paridad ES/EN de claves verificada.
- Revisión visual en un Chrome headless **propio** (no el compartido) contra un Vite privado sin HMR: Canales,
  Registro (+detalle), Cola, asistente (4 pasos), simulador (grilla, diálogo, reservas) en claro y oscuro, 1440 y
  375 px sin scroll horizontal de página; el flujo 3 y el brillo del paso 4 se vieron en vivo. En la BD de desarrollo
  quedan canceladas las reservas de prueba (`BS-9567178`/HT-WNTRP4 "Smoke Canales", `BS-3347531`/HT-5MFF9G,
  `BS-7508321`/HT-MVBTM3).
