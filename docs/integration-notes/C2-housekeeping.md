# C2 — Housekeeping y mantenimiento — integration notes

Estado: **implementado de punta a punta y verificado en modo MVP (sin tests nuevos ni suites)**, 2026-09-27.
Esta corrida retomó el trabajo parcial de intentos anteriores (backend y frontend casi completos, migración ya
aplicada), lo revisó contra el plan y corrigió 4 problemas de comportamiento y 5 de UI (ver "Correcciones de esta
corrida"). Verificación: `manage.py check` y `makemigrations housekeeping --check` limpios, ruff limpio, smoke de
la API por el proxy de Vite con 5 usuarios del seed (**0 fallas**), las 2 automatizaciones con `automation.run`,
seed probado en una transacción revertida (**2,0 s**), `tsc` y `eslint` sin errores en la feature, y revisión en
un Chrome headless propio (1440 y 375 px, claro/oscuro, ES/EN) sin errores de consola.

Owner paths: `backend/apps/housekeeping/**`, `frontend/src/features/housekeeping/**` y esta nota. No se tocó nada
fuera de ellos. Sin dependencias nuevas.

---

## Cómo probarlo en la UI

Todo en `http://localhost:5173`, clave `housetel123`. Fecha de negocio del demo: la de la propiedad (hoy).

| Usuario | Rol | Qué ve |
|---|---|---|
| `owner@casaaurora.co` | dueño (supervisa todo) | tablero, mantenimiento, configuración |
| `limpieza@casaaurora.co` (Luz Marina Pérez) | housekeeping | al entrar a `/app` C1 la manda a `/app/housekeeping/mine` |
| `recepcion@casaaurora.co` | recepción | tablero y mantenimiento **solo lectura** (sin botones de estado ni "Reportar daño") |
| `contabilidad@casaaurora.co` | contabilidad | no tiene "Limpieza" ni "Mantenimiento" en el menú |
| `owner@grupoandino.co` → propiedad **Andino Medellín** | dueño | hotel con **inspección obligatoria** (14 inspecciones pendientes en el seed) |
| `limpieza@grupoandino.co` (José Martínez) | housekeeping | solo Andino Medellín |

### 1. Tablero de supervisión — `/app/housekeeping` (owner, 1440 px)
- Arriba: "Habitaciones" (Sucias / Limpias / Inspeccionadas / Fuera de servicio + ocupadas), "Tareas del día"
  (`N de M tareas terminadas`, barra, minutos hechos de totales, chips en curso / pendientes / sin asignar) y
  "Carga por persona" (minutos del día contra el turno de 7 h; en naranja si lo supera).
- Filtros: estado (con conteos), persona (incluye "Sin asignar") y "Solo con tareas".
- Tiles por piso (3 pisos, 24 habitaciones en Casa Aurora) teñidos por estado: limpia = salvia, sucia = arena,
  inspeccionada = pizarra, fuera de servicio = piedra rayada. Muestran huéspedes en casa, "Sale hoy", "Llega
  hoy/Llega HH:MM", estrella VIP, daños reportados, y la tarea con su asignada.
- **Esperado en el seed**: la habitación bloqueada por «Aire acondicionado no enfría» aparece rayada "Fuera de
  servicio" con "1 daño reportado" (hoy es la 110; tras el `seed_demo --reset` de C-INT será una habitación libre,
  p. ej. la 109); 207 tiene huéspedes que salen hoy y una llegada.
- Clic en un tile → panel lateral: botones de estado, ocupación, llegada, bloqueo, daños ("Ver en
  mantenimiento"), tareas (asignar con el select, Iniciar / Terminar, Aprobar inspección / No aprobar, Cancelar
  tarea), "Nueva tarea" y "Reportar daño". En una salida con el huésped adentro, "Iniciar" está deshabilitado y el
  panel dice "El huésped aún no ha hecho check-out".
- Cambio rápido de estado: en una habitación libre y limpia (p. ej. 103) → "Sucia" → toast "Habitación 103:
  Sucia"; el tile pasa a arena y aparece "Salida · Pendiente" **ya asignada a Luz Marina** (asignación
  automática). Volver a "Limpia" → esa tarea pendiente queda cancelada.
- "Generar tareas del día" → "No había tareas nuevas por crear" (idempotente). "Auto-asignar" → reparte las
  pendientes sin asignar.
- Nueva tarea: panel de una habitación → "Nueva tarea" → Limpieza profunda · Alta · Luz Marina → "Crear tarea".

### 2. Vista móvil de la camarera — `/app/housekeeping/mine` (limpieza@casaaurora.co, 375 px)
- Encabezado con la fecha, "N de M listas", "X h Y min por hacer" y la barra de progreso; botón actualizar (la lista
  se refresca sola cada minuto).
- Tarjetas grandes con forma de colgador de puerta: "En curso" (la 204 en el seed, con nota y botón **Terminar**),
  "Siguientes" (banda arena "Por hacer" con **Iniciar**; banda piedra rayada "En espera" cuando el huésped aún no
  sale: botón deshabilitado y el aviso), y "Terminadas" (lista con "Lista a las HH:MM").
- Iniciar una "Por hacer" → pasa a "En curso" ("Empezaste a las HH:MM"); Terminar → pasa a "Terminadas" y en el
  tablero la habitación queda "Limpia".
- "Reportar daño" en una tarjeta → hoja inferior: ¿Qué pasó?, Detalles, **"Tomar o elegir fotos"** (en un
  teléfono abre la cámara: `<input type=file accept="image/*" capture="environment">`), prioridad y "La habitación
  no se puede usar" (bloqueo con fecha). Enviar → toast "Reporte enviado a mantenimiento" y el ticket aparece en
  `/app/maintenance`.

### 3. Flujo E2E 1 del spec (check-out → sucia → limpieza desde el móvil)
1. Recepción hace el check-out de una salida de hoy (en el seed: 104, 208, 304 de Casa Aurora o 207, que además
   tiene una llegada) → la habitación pasa a "Sucia".
2. Su "Limpieza de salida" (planificada en la mañana, "En espera") queda habilitada para Luz Marina; si la
   habitación no tenía tarea, se crea una nueva **asignada a Luz Marina** en ese momento (prioridad alta si llega
   alguien hoy).
3. Luz Marina, en `/app/housekeeping/mine` (actualizar o esperar 1 min), la inicia y la termina → la habitación
   queda "Limpia" y recepción puede hacer el check-in de la llegada.

### 4. Inspección — Andino Medellín (owner@grupoandino.co, selector de propiedad → Andino Medellín)
- En el tablero hay habitaciones con "Inspección · Pendiente". Panel → "Aprobar inspección" → la habitación queda
  "Inspeccionada". "No aprobar" → vuelve a "Sucia" con una limpieza de prioridad alta asignada a quien la limpió.
- Como `limpieza@grupoandino.co`: terminar una limpieza deja la habitación "Limpia" y crea su inspección; la
  camarera no puede aprobarla.

### 5. Mantenimiento — `/app/maintenance`
- Vista "Pendientes" en dos columnas (Abiertos / En curso), más "Resueltos" y "Todos"; buscador, "Solo los que
  bloquean" y "Reportados por mí o a mi cargo". `/app/maintenance?room=<id>` filtra por habitación (enlace desde el
  panel del tablero) y `?new=1` abre el formulario (comando ⌘K "Reportar un daño").
- Seed (por hotel): «Aire acondicionado no enfría» (abierto, **bloquea** una habitación 2 noches: tarjeta rayada
  "Bloquea la habitación hasta el …"), «Grifo del lavamanos gotea» (abierto, con **foto**) y «Bombillo fundido en
  el pasillo» (área común, en curso).
- Abrir «Grifo…» → la foto carga (privada, vía API con sesión). Acciones (mantenimiento/supervisión): responsable,
  "La habitación no se puede usar" + "Hasta" + Guardar, Empezar, "Qué se hizo" + **Marcar resuelto** (si bloqueaba:
  libera el bloqueo y la habitación pasa a "Sucia" con su limpieza), Cancelar reporte (restaura el estado previo),
  Eliminar (solo supervisión).
- Bloquear una habitación con reservas en esas fechas → error "La habitación … tiene reservas…" y botón "Bloquear de
  todas formas" (mantenimiento/supervisión). El bloqueo es un `RoomBlock` `out_of_order`: se ve en
  `/app/settings/rooms` (bloqueos de la habitación) y en el calendario, y quita disponibilidad.

### 6. Configuración — `/app/settings/housekeeping` (supervisión)
Repaso de huéspedes en casa (todos los días / cada 2 / 3 días / semanal / sin repaso), Exigir inspección,
Asignación automática, Minutos por turno (60–900) → "Guardar cambios" → toast. Sin `housekeeping.supervise` se ve
en solo lectura.

### 7. Otros puntos
- Panel Hoy (`/app`): widget **"Limpieza de hoy"** (progreso, habitaciones por estado, daños abiertos y
  bloqueantes, enlace "Ver tablero de limpieza").
- ⌘K (con `housekeeping.work`): "Mis habitaciones de hoy" y "Reportar un daño".
- Inglés y modo oscuro completos; 375 px sin desbordes en tablero, "Mis habitaciones" y mantenimiento.

---

## API implementada

Base `/api/v1/housekeeping/` (sesión + `X-Property-Id`; reglas de tenancy de A1: 400 `property_required`, 404
propiedad u objeto de otra propiedad/organización, 403 `permission_denied` + `permission`, 401 anónimo). Listas
paginadas `{count, next, previous, results}` (`page_size` ≤ 200). Toda escritura se audita (`housekeeping.*`).

Permisos (plan §D): `view` lee todo; **`work` solo ve y trabaja sus tareas** (lista, detalle y tablero filtrados a
las asignadas a ella); `supervise` todo; `maintenance` trabaja los tickets. "Report" = `work` o `maintenance` o
`supervise`; "Repair" = `maintenance` o `supervise`.

| Método y path | Permiso | Descripción |
|---|---|---|
| `GET tasks/` | view | Tareas de la fecha de negocio **+ las abiertas de días anteriores**. Filtros: `date=AAAA-MM-DD`, `status` (repetible), `kind` (repetible), `floor`, `assignee=none\|me\|<uuid>`, `mine=1`. Orden: en curso, pendientes, terminadas…; luego prioridad y habitación |
| `GET tasks/{id}/` | view | Tarea |
| `POST tasks/` | supervise | `{room_id, kind, priority?, notes?, assigned_to_id?, bed_id?, estimated_minutes?}` → 201. Segunda salida/repaso abierta en la habitación → 409 `task_exists` |
| `PATCH tasks/{id}/` | supervise | `{priority?, notes?, estimated_minutes?}` (solo abiertas) |
| `POST tasks/{id}/start/` | work | pending → in_progress (si no tenía asignada, la toma quien la inicia). Salida con el huésped aún en casa → 409 `guest_in_room` |
| `POST tasks/{id}/finish/` | work | `{notes?}` → done; una limpieza deja la habitación `clean` (salvo `out_of_service`) y, con `require_inspection`, crea la inspección |
| `POST tasks/{id}/inspect/` | supervise | `{passed=true, notes?}` (inspección abierta o limpieza terminada). Aprobada → habitación `inspected`; no aprobada → `dirty` + limpieza alta para quien la limpió |
| `POST tasks/{id}/assign/` | supervise | `{user_id \| null}`; alguien sin `housekeeping.work` en el hotel → 400 `invalid_assignee` |
| `POST tasks/{id}/cancel/` | supervise | `{reason?}` |
| `POST tasks/auto-assign/` | supervise | `{user_ids?}` → `{business_date, assigned, unassigned, staff:[{user_id, full_name, minutes, tasks}], overloaded:[ids], minutes_per_shift}` |
| `POST tasks/generate/` | supervise | Corre la generación diaria ahora → `{created, stayovers, departures, dirty_rooms, rooms_marked_dirty}` (idempotente) |
| `GET board/` | view | `{business_date, settings, summary, staff, floors:[{floor, rooms:[…]}]}` |
| `GET summary/` | view | Progreso del día (lo usa el widget) |
| `GET staff/` | view | `{housekeepers:[{id, full_name, email, minutes, minutes_done, tasks, tasks_done}], maintenance:[{id, full_name, email, open_tickets}]}` |
| `GET/PATCH settings/` | view / supervise | `{stayover_frequency_days (0–30; 0 = sin repaso), require_inspection, auto_assign, minutes_per_shift (60–900)}` |
| `POST rooms/{id}/status/` | work o supervise | `{housekeeping_status}` → `{id, number, housekeeping_status}` vía `inventory.set_housekeeping_status`. `work` solo `clean`/`dirty`; `supervise` cualquiera. Habitación retenida por un ticket que bloquea → 409 `room_blocked` (`ticket_id`) |
| `GET tickets/` | view | Filtros: `status`, `priority` (repetibles), `room`, `assignee=none\|me\|<uuid>`, `blocking=true\|false`, `mine=1` (reportados o asignados a mí), `q` (título, descripción, lugar o número exacto de habitación) |
| `GET tickets/{id}/` | view | Ticket |
| `POST tickets/` | report | JSON o **multipart** (`photos` repetible): `{title, room_id?, location?, description?, priority?, blocks_room?, blocked_until? (exclusivo; por defecto mañana), assigned_to_id?, force?}` → 201. Con reservas en el rango → 409 `room_has_reservations` (`reservations: [códigos]`); `force` solo repair |
| `PATCH tickets/{id}/` | repair | `{title?, description?, location?, priority?, assigned_to_id?, blocks_room?, blocked_until?, force?}`: activar/desactivar el bloqueo o moverlo |
| `DELETE tickets/{id}/` | supervise | 204 (libera el bloqueo si estaba abierto y borra las fotos) |
| `POST tickets/{id}/start/` | repair | open → in_progress (se asigna a quien empieza si atiende mantenimiento) |
| `POST tickets/{id}/resolve/` | repair | `{notes?}` → libera el bloqueo y manda la habitación a limpieza (`dirty`) |
| `POST tickets/{id}/cancel/` | repair | `{reason?}` → libera el bloqueo y restaura el estado previo de la habitación |
| `POST tickets/{id}/photos/` | report (sus tickets; repair cualquiera) | multipart `image` → 201 foto |
| `DELETE tickets/{id}/photos/{photo_id}/` | ídem | 204 |
| `GET ticket-photos/{id}/file/` | view | La foto (stream, `Cache-Control: private, no-store`, `nosniff`). **Única** forma de leerla: se guardan fuera de `/media/` |

Fotos: JPEG/PNG/WebP/HEIC reconocidas por contenido, ≤ 10 MB, máximo 6 por ticket (`file_too_large`,
`invalid_file_type`, `too_many_photos`). Otros códigos: `invalid_state` 409, `ticket_closed` 409, `title_required`,
`room_required`, `invalid_room`, `invalid_bed`, `invalid_kind`, `invalid_priority`, `invalid_dates`.

Tarea (real, recortada):

```json
{"id": "3bb726f1-…", "room": {"id": "a8d1373e-…", "number": "207", "name": "", "floor": "2",
  "housekeeping_status": "clean", "room_type": {"id": "…", "code": "SUP", "name": {"es": "Superior", "en": "Superior"},
  "color": "#5F7F66", "kind": "private"}},
 "bed": null, "kind": "departure_clean", "status": "pending", "priority": "high", "business_date": "2026-09-27",
 "assigned_to": {"id": "9664080e-…", "full_name": "Luz Marina Pérez", "email": "limpieza@casaaurora.co"},
 "estimated_minutes": 35, "started_at": null, "finished_at": null, "finished_by": null, "notes": "",
 "reservation": {"id": "…", "code": "HT-UYRN4J"}, "created_source": "daily",
 "waiting_for_checkout": true, "arrival_today": {"code": "HT-M2BDPV", "eta": null, "is_vip": false},
 "overdue": false, "created_at": "…", "updated_at": "…"}
```

- `kind` ∈ `departure_clean | stayover | deep_clean | inspection | turndown | custom`; `status` ∈ `pending |
  in_progress | done | inspected | cancelled`; `priority` ∈ `low | normal | high | urgent`; `created_source` ∈
  `checkout | status_change | daily | inspection | manual | seed`.
- `waiting_for_checkout`: salida cuyo huésped sigue en casa (no se puede iniciar). `overdue`: abierta de un día
  anterior. Minutos estimados: salida = `housekeeping_minutes` de la habitación (override o categoría), repaso = la
  mitad (≥ 10), profunda = el doble, inspección y cobertura = 10.

Habitación del tablero (real, recortada):

```json
{"id": "a8d1373e-…", "number": "207", "floor": "2", "housekeeping_status": "clean", "room_type": {"code": "SUP", "…": "…"},
 "occupied": true, "in_house": {"code": "HT-UYRN4J", "checkout_date": "2026-09-27", "departs_today": true, "guests": 2, "is_vip": false},
 "arrival_today": {"code": "HT-M2BDPV", "eta": null, "is_vip": false}, "tasks": ["…tareas del día…"],
 "active_block": null, "open_tickets": 0}
```

`summary` (real): `{"business_date": "2026-09-27", "rooms": {"total": 24, "clean": 15, "dirty": 8, "inspected": 0,
"out_of_service": 1, "occupied": 18}, "tasks": {"total": 20, "pending": 11, "in_progress": 1, "done": 8,
"inspections_pending": 0, "unassigned": 0}, "minutes": {"total": 552, "done": 189}, "tickets": {"open": 3,
"blocking": 1}}` (las inspecciones no cuentan en `tasks.total`).

Ticket (real, recortado):

```json
{"id": "d84fa818-…", "room": {"id": "…", "number": "101", "…": "…"}, "location": "", "title": "Grifo del lavamanos gotea",
 "description": "Gotea constantemente…", "priority": "normal", "status": "open", "blocks_room": false,
 "blocked_until": null, "block": null,
 "reported_by": {"id": "…", "full_name": "Luz Marina Pérez", "email": "limpieza@casaaurora.co"},
 "assigned_to": null, "started_at": null, "resolved_at": null, "resolved_by": null, "resolution_notes": "",
 "photos": [{"id": "b71bdae2-…", "content_type": "image/jpeg", "size": 19961,
             "file_url": "/api/v1/housekeeping/ticket-photos/b71bdae2-…/file/", "uploaded_by": {"…": "…"}, "created_at": "…"}],
 "created_at": "…", "updated_at": "…"}
```

`block` (si bloquea): `{id, start_date, end_date, released_at}`.

## Contratos implementados / consumidos

- **Consumidos** (únicas escrituras fuera de la app): `inventory.services.set_housekeeping_status(room, status,
  actor=, source=)` (terminar, inspeccionar, proxy de estado, tickets, repasos de la generación diaria),
  `inventory.services.block_room(room, start=, end=, kind="out_of_order", reason=, actor=)` y
  `release_block(block, actor=)`. Lecturas ORM: `bookings.Stay` (ocupación, llegadas de hoy, salidas),
  `inventory.Room/RoomBlock/Bed`, `accounts.Membership` (quién limpia). `core`: `audit`, `permissions.has_perm/
  codes_match`, `automation`, `signals`, `tenancy`.
- **Servicios propios para otras apps** (`apps/housekeeping/services/…`, escriben con auditoría):
  `tasks.ensure_turnover_task / start_task / finish_task / inspect_task / assign_task / create_task / cancel_task /
  update_task`, `generation.generate_daily_tasks(property)`, `assignment.auto_assign(property, staff=None)`,
  `assignment.assign_new_task(task)`, `assignment.eligible_staff(property)` (quien recibe habitaciones:
  `housekeeping.work` sin `housekeeping.supervise`), `tickets.create_ticket / update_ticket / resolve_ticket /
  cancel_ticket / add_photo`, `rooms.set_room_status(room, status, actor=)`, `config.get_settings(property)`.
  Lecturas: `selectors.summary(property)` (mismo JSON que `GET summary/`; útil para C10/C12 o el copiloto),
  `selectors.board(property)`.

## Señales emitidas / escuchadas

- Emitidas (indirectamente, por los contratos de inventario): `room_status_changed` y `inventory_changed` (bloqueos).
- Escuchadas (`receivers.py`, todas con `if is_seeding(): return`):
  - `stay_checked_out` → limpieza de salida de la habitación (prioridad alta si llega alguien hoy; en un dorm, de la
    cama, y se amplía a todo el cuarto si otra cama la necesita). Si se crea nueva y el hotel tiene asignación
    automática, se asigna al instante (`assign_new_task`).
  - `room_status_changed` → `dirty` sin limpieza abierta: la crea (repaso si está ocupada, salida si no) y la asigna
    igual; `clean`/`inspected` marcado fuera de una tarea: cancela sus salidas/repasos **pendientes** (una en curso
    se respeta). Si una habitación retenida por un ticket que bloquea pasa de `out_of_service` a `dirty` (el
    `check_out` de B2b siempre la ensucia), vuelve a `out_of_service` y el ticket recuerda que necesita limpieza.
- La BD garantiza una sola salida/repaso abierta por habitación (`hk_one_open_turnover_per_room`): receivers
  concurrentes nunca duplican.

Acciones de auditoría: `housekeeping.task_created, task_started, task_finished, task_inspected, task_assigned,
task_updated, task_cancelled, tasks_auto_assigned, settings_updated, ticket_created, ticket_updated,
ticket_started, ticket_resolved, ticket_cancelled, ticket_deleted, ticket_photo_added, ticket_photo_deleted`.

## Automatizaciones registradas

| Código | Horario | Qué hace |
|---|---|---|
| `housekeeping.generate_daily_tasks` | diario 07:00 | Salidas esperadas (en casa con salida hoy o vencida), repasos según `stayover_frequency_days` (la habitación pasa a sucia) y habitaciones sucias sin tarea. Omite las fuera de servicio. Idempotente |
| `housekeeping.auto_assign` | diario 07:15 | Reparte las pendientes sin asignar (no inspecciones) entre quienes limpian en el hotel: balance por minutos y agrupación por piso. `skipped` si `auto_assign` está apagado; `partial` si no hay personal (Andino Hostel) o quedan sin asignar |

`automation.run` manual en las 3 propiedades: todo `success` salvo `auto_assign` del hostal (`partial`: no tiene
personal de limpieza).

## Proveedores de integración registrados

Ninguno.

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

- `routes.tsx` (lazy): `housekeeping` (tablero), `housekeeping/mine`, `maintenance`, `settings/housekeeping`.
  `nav.ts` sin cambios (ítems del plan).
- `widgets.tsx`: `housekeeping.progress` (order 40, `md`, `housekeeping.view`) → `CleaningProgress` (cuerpo lazy).
- `commands.ts`: `housekeeping.mine` (navegación) y `housekeeping.report` (acción → `/app/maintenance?new=1`), ambos
  con `housekeeping.work`.
- `api.ts`: tipos (`HkTask`, `BoardRoom`, `HkSummary`, `MaintenanceTicket`…), `hkKeys` y hooks `useHkSummary`,
  `useBoard`, `useMyTasks`, `useStaff`, `useHkSettings`, `useTickets`, `useHkMutation` (invalida todo
  `['housekeeping']` al escribir).
- Componentes reutilizables (`components/`): `RoomTile`, `DoorHangerCard`, `ReportDamageSheet` (`room` fijo o
  `rooms` para elegir), `ProgressMeter`, `RoomStateCounts`, `TaskBadges`/`PriorityBadge`, `PrivatePhoto`.
- Usa de otras features: `RoomKeyTag` (inventory) y `useDebouncedValue` (guests).

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

1. **Tests del shell/router de A2 (C-INT)**: `/app/housekeeping` ya es una página real que pide
   `GET /api/v1/housekeeping/board/`. En `src/app/__tests__/shell.test.tsx` y `router.test.tsx` agregar un handler
   MSW con la forma vacía: `{business_date: "2026-09-25", settings: {stayover_frequency_days: 1,
   require_inspection: false, auto_assign: true, minutes_per_shift: 420}, summary: {business_date: "2026-09-25",
   rooms: {total: 0, clean: 0, dirty: 0, inspected: 0, out_of_service: 0, occupied: 0}, tasks: {total: 0,
   pending: 0, in_progress: 0, done: 0, inspections_pending: 0, unassigned: 0}, minutes: {total: 0, done: 0},
   tickets: {open: 0, blocking: 0}}, staff: [], floors: []}`. El widget del panel Hoy pide `GET
   /api/v1/housekeeping/summary/` (la parte `summary` de arriba).
2. **Opcional (seed de core, A1)**: no hay usuario de mantenimiento en el demo; los tickets los atiende el dueño.
   Para mostrar el rol, agregar a `USERS` p. ej. `mantenimiento@casaaurora.co` con rol `maintenance`: aparece solo
   en "Responsable" de los tickets y en `GET staff/` → `maintenance`.
3. **Opcional (B2b)**: `check_out` y el movimiento de un huésped en casa ponen la habitación en `dirty` aunque
   esté `out_of_service`. Housekeeping lo compensa (receiver), pero lo limpio sería respetar `out_of_service` ahí.
4. OpenAPI: housekeeping no agrega colisiones de enums (las choices de requests son strings validados). Las 3
   colisiones `kind`/`status` que muestra hoy `spectacular --validate` son de compliance (C7).

## Seed (`apps/housekeeping/seed.py`, orden después de `finance`)

Por propiedad con habitaciones, todo por los servicios (auditoría, bloqueos e inventario coherentes); idempotente
(un hotel con tareas de su fecha de negocio se omite; con tickets no recibe más; nunca pisa la configuración):
1. Configuración por defecto; **Andino Medellín exige inspección**.
2. Tres tickets: «Aire acondicionado no enfría» bloquea 2 noches una habitación **libre** (sin huésped en casa, sin
   estadías ni bloqueos en esas noches) vía `block_room`; «Grifo del lavamanos gotea» en una habitación ocupada,
   reportado por la camarera con una foto dibujada (Pillow, determinista, sin red); «Bombillo fundido en el pasillo»
   (área común, en curso).
3. Tareas de hoy: generación diaria + auto-asignación (Casa Aurora → Luz Marina; Medellín → José; el hostal no tiene
   personal: sin asignar).
4. Progreso de la mañana: cada camarera terminó ~la mitad de lo que podía hacer (habitación limpia; inspección
   pendiente donde se exige), tiene una en curso y el resto espera; las salidas con el huésped adentro quedan
   pendientes. Horas repartidas hacia atrás desde ahora, nunca antes de la medianoche.

Prueba en una transacción revertida sobre la BD de desarrollo (borrando antes los datos de housekeeping): **2,0 s**;
Casa Aurora 19 tareas (12 pendientes, 6 terminadas, 1 en curso; todas de Luz Marina), Medellín 47 (13 inspecciones),
hostal 11 sin asignar; 3 tickets por hotel, el bloqueante en una habitación sin huésped (Casa Aurora 109).
Invariantes comprobadas: una sola salida/repaso abierta por habitación, terminadas con habitación limpia y horas
coherentes.

**Estado actual de la BD de desarrollo**: un intento anterior corrió este seed de verdad (11:13) con el error del
punto 1 de "Correcciones": el ticket bloqueante de Casa Aurora quedó en la **110**, que tiene un huésped que sale
hoy (HT-FXD58H). Es coherente gracias a la corrección 2 (al hacer su check-out sigue fuera de servicio y recibe su
limpieza); el `seed_demo --reset` de C-INT elegirá una habitación libre. Mi smoke dejó además historia inocua:
tareas canceladas en 103/106/107 de Casa Aurora, una limpieza profunda terminada en la 106, y en Medellín dos
inspecciones resueltas (una no aprobada, con su limpieza de repetición) y una limpieza terminada por José (601).

## Correcciones de esta corrida

Backend:
1. **Seed: ticket bloqueante en una habitación con huésped adentro.** `_vacant_room` consideraba libre una
   habitación cuyo huésped sale hoy (checkout exclusivo) → la bloqueaba y la dejaba fuera de servicio con el
   huésped dentro. Ahora excluye toda habitación con una estadía `checked_in`.
2. **Check-out de una habitación bloqueada por un ticket**: `bookings.check_out` la ponía `dirty` y perdía el
   `out_of_service` mientras el bloqueo seguía activo. `tickets.hold_blocked_room` (desde el receiver) la devuelve a
   fuera de servicio y marca `room_status_before = "dirty"` para que resolver/cancelar la mande a limpieza.
3. **Tareas del día sin asignar**: las limpiezas que nacen durante el día (check-out, habitación marcada sucia,
   ticket resuelto) quedaban sin asignar hasta la auto-asignación de las 07:15 y la camarera no las veía en su móvil
   (rompía el flujo E2E 1). Con `auto_assign` activo se asignan al instante con la misma regla (piso + balance).
4. Probado por simulación en transacciones revertidas: salida de la 110 → sigue fuera de servicio con su limpieza →
   al resolver el ticket pasa a sucia con una sola limpieza abierta; asignación inmediata con/sin `auto_assign` y
   sin personal.

Frontend (encontrado en la revisión headless):
1. **Tablero recortado a 375 px**: los grids raíz tenían una columna implícita `auto` que crecía al min-content del
   selector de estados; ahora `grid-cols-1` (`minmax(0,1fr)`) en las 4 páginas y en el resumen del día.
2. Tiles: "2 huéspedes · Sale hoy" se partía palabra por palabra; ahora cada parte es indivisible y envuelve.
3. Resumen: "Inspeccionadas" y "Fuera de servicio" se truncaban a 1440 px; la tarjeta usa 2 columnas desde `lg`.
4. Mantenimiento: el buscador quedaba de ~80 px junto al selector en móvil; ahora ocupa el ancho completo.
5. Panel de habitación: explica por qué "Iniciar" está deshabilitado ("El huésped aún no ha hecho check-out").

## Verificación (esta corrida, sin tests)

```bash
docker compose exec -T backend python manage.py check                                   # sin problemas
docker compose exec -T backend python manage.py makemigrations housekeeping --check --dry-run   # No changes
docker compose exec -T backend sh -c "ruff check apps/housekeeping && ruff format --check apps/housekeeping"  # limpio
cd frontend && npx tsc -p tsconfig.app.json --noEmit 2>&1 | grep src/features/housekeeping   # vacío
npx eslint src/features/housekeeping                                                    # exit 0
```

- **Smoke por el proxy** (`http://localhost:5173/api/v1/housekeeping/…`, cookie jar + CSRF; script en el
  scratchpad de la sesión): ~90 requests con dueño, camarera, recepción y contabilidad de Casa Aurora y dueño y
  camarera de Andino — lecturas y filtros del tablero, resumen, personal, configuración, tareas y tickets; foto
  privada (200 `image/jpeg`); la camarera solo ve las suyas; salida con huésped → 409 `guest_in_room`; proxy de
  estado (sucia → tarea `status_change`; limpia → cancelada; `inspected` → 403 para la camarera); crear, asignar,
  editar, iniciar, terminar, cancelar; generar (idempotente) y auto-asignar; configuración (400 fuera de rango);
  ticket multipart con foto (archivo no imagen → 400), empezar, resolver, borrar; ticket bloqueante (bloqueo
  `out_of_order` visible en inventario, estado → 409 `room_blocked`, mover fecha, cancelar restaura `clean`); bloquear
  ocupada → 409 `room_has_reservations`; recepción 403 al trabajar/reportar; contabilidad 403; otra organización 404
  (tablero, tarea, ticket, foto); anónimo 401; inspección aprobada → `inspected`, no aprobada → `dirty` + repetición
  alta asignada; terminar con inspección requerida → limpia + inspección; camarera restringida a Medellín → hostal
  404. **0 fallas**.
- Automatizaciones: `automation.run` de las 2 en las 3 propiedades, sin errores.
- Chrome headless propio (perfil temporal, puerto 9444/9445; no el navegador compartido): tablero, panel, mantenimiento
  con foto, configuración, Hoy con el widget, móvil de la camarera y hoja de reporte; 1440 y 375 px; oscuro y claro;
  ES y EN (el idioma del perfil de la camarera se restauró a `es`). Sin errores de consola (solo el 401 conocido de
  `/me` en `/login`) y sin desborde horizontal a 375 px.

## Limitaciones conocidas / pendientes

- **Tests**: `backend/apps/housekeeping/tests/` y `frontend/src/features/housekeeping/__tests__/` vienen de un intento
  anterior y **no se corrieron** en esta fase (modo MVP, decisión del usuario). Pueden necesitar ajustes por la
  asignación inmediata de los receivers, la compensación de habitaciones bloqueadas y los cambios de layout.
- Cobertura nocturna (`turndown`) y "otra tarea" (`custom`) no cambian el estado de la habitación.
- En dorms, la tarea de salida es por cama solo mientras una cama lo necesita; si varias lo necesitan se amplía a
  todo el cuarto.
- La auto-asignación es voraz (determinista); el `overloaded` de su reporte mira los minutos abiertos, mientras el
  tablero compara los minutos del día (hechos + abiertos) con el turno.
- Sin notificaciones push: la vista móvil y el tablero se refrescan cada 60 s (y al escribir).
- Fotos HEIC se aceptan pero Chrome no las muestra (Safari/iOS suele subir JPEG desde la cámara).
- No hay usuario de mantenimiento en el demo (ver "Cambios requeridos" 2).
