# B-INT — Integración de la Fase B — integration notes

Estado: **checklist de B-INT completo y verificado** (2026-09-27). Se aplicaron todos los "cambios requeridos" de
las notas B1–B4, se corrigieron 6 problemas de integración con su causa raíz (cada uno con un test visto en rojo
primero) y quedó el stack arriba con el seed completo recién cargado. Sin commits; `.env` intacto; sin dependencias
nuevas.

Lectura obligatoria para la Fase C: **"Para la Fase C"** (abajo). El resto es evidencia.

---

## Checklist del plan (B-INT) → resultado

| Punto | Resultado |
|---|---|
| Cambios requeridos de B1–B4 en archivos compartidos | Aplicados (tabla siguiente) |
| `makemigrations --check` y `migrate` en BD nueva | `docker compose down -v` → BD vacía → `migrate`: 29 migraciones aplicadas, 0 pendientes; `makemigrations --check --dry-run` → "No changes detected"; `manage.py check` sin problemas |
| `seed_demo --reset` completo y coherente | Completo (3 propiedades, 3.333 reservas, 2.315 pagos). `check_integrity` y un chequeo ampliado de 88 invariantes: **0 fallas** (detalle en "Seed") |
| Suite backend completa | `docker compose run --rm -e TEST_DB_NAME=test_bint backend pytest -q` → **2.153 passed**; `ruff check .` y `ruff format --check .` limpios |
| Frontend | En el contenedor (Node 24): `typecheck` ✓, `lint` ✓, `test` → **63 archivos, 437 tests**, sin stderr (antes había errores de MSW), `build` ✓ |
| Smoke por el proxy de Vite | 15 requests con cookie jar + CSRF contra `http://localhost:5173/api/...`: login → habitaciones → grilla → ofertas → reserva tentativa → folio → link de pago simulado → la pasarela decide `approved` → reserva **confirmada**, pago `wompi_card` registrado una vez, saldo = total − depósito → logout → 401 |
| Notas | Este archivo; README actualizado |
| Stack arriba con el seed completo | Sí: 7 servicios `Up` (db y mailpit `healthy`), 0 tracebacks en los logs, beat con las 5 automatizaciones de A+B |

## Cambios requeridos de B1–B4 → aplicados

| Origen | Cambio | Dónde | Test |
|---|---|---|---|
| B1, B2a, B2b, B3 | `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]` con `BookingStatusEnum`, `ReservationSourceEnum`, `RoomTypeKindEnum`, `RoomBlockKindEnum`, `GuestDocumentKindEnum` (el bloque verificado por B2b). Antes: 5 warnings y nombres con hash (`KindD0cEnum`) | `backend/config/settings.py` | `apps/core/tests/test_schema.py::test_the_schema_generates_without_warnings` (corre `spectacular --validate --fail-on-warn`) y `::test_colliding_enums_get_stable_names`; también `make check` |
| B1 | `afterEach(() => toast.dismiss())`: Sonner reenviaba los toasts activos al `<Toaster>` del test siguiente. Se quitó el parche local de `PhotoGallery.test.tsx` | `frontend/src/test/setup.ts` | `src/components/__tests__/Toaster.test.tsx` |
| B1 | Fotos del seed con ruta duplicada (`photos/2026/09/photos/seed/…`) | BD recreada; las 45 fotos quedan en `photos/seed/<slug>.jpg`. Los 45 archivos huérfanos viejos se movieron fuera del repo | — |
| B3 | `backend/media-private/` en `.gitignore` (defensa adicional al `.gitignore` que escribe el storage) | `.gitignore` | `git check-ignore` |
| B3 | `PRIVATE_MEDIA_ROOT` configurable para producción (opcional) | `settings.py` (env `PRIVATE_MEDIA_ROOT`; sin valor → `<MEDIA_ROOT>-private`; en tests siempre el temporal) y `.env.example` | — (sin cambio de comportamiento por defecto) |
| B3 | El buscador de `DataTable` no tenía `name` (issue de Chrome en toda página con búsqueda) | `frontend/src/components/DataTable.tsx` (`name="search"`) | `DataTable.test.tsx` ("names the search box"); en Chrome, `/app/settings/users` quedó con 0 controles sin nombre y consola vacía |
| B2b, B4 | El seed completo tarda ~10 min: correrlo en segundo plano | Corrido en segundo plano; tiempos en "Seed" y en el README | — |

Los demás puntos de esas secciones son para la Fase C (ver "Para la Fase C").

## Problemas de integración encontrados y corregidos (causa raíz)

1. **Test intermitente de finanzas** (`finance/tests/test_seed.py::test_seed_builds_a_believable_ledger`, lo reportó
   B2a). Causa: el seed daba link de pago solo al 70 % de las reservas tentativas, con un dado sembrado por el UUID
   (aleatorio) de cada reserva; con 3 tentativas el test fallaba en ~2,7 % de las corridas. Arreglo: toda tentativa
   recibe su link pendiente (es una retención esperando el pago; es lo que dice la docstring y el plan). Test
   determinista con 20 tentativas: `test_every_tentative_booking_gets_its_pending_link`.
2. **Errores de MSW en stderr** en dos tests compartidos de A2 (`shell.test.tsx`, `router.test.tsx`): desde que
   las páginas de tarifas y habitaciones son reales, esos tests del shell hacían peticiones sin handler. Se agregaron
   handlers vacíos con la forma correcta (listas o páginas). La corrida del contenedor quedó sin stderr.
3. **Historia fechada "hoy" en el seed** (coherencia por fecha de negocio, base de los reportes de C10): las
   cancelaciones históricas tenían `cancelled_at` = el momento del seed y **todas** las penalidades de cancelación y
   no-show se publicaban con `business_date` = hoy (Casa Aurora: 33 cargos por $30,7 M "de hoy"; la caja mostraba
   "Cargos publicados hoy: $30.721.540"). Arreglo, respetando dueños:
   - `bookings/seed.py` fecha `cancelled_at`: una cancelación pasada ocurrió el día de llegada, antes o cerca del
     check-in (cancelación tardía: por eso pagó penalidad); una futura, entre la creación y hoy, salvo que su
     penalidad dependa de lo cerca de la llegada (entonces se queda hoy). Test:
     `bookings/tests/test_seed.py::test_cancellations_are_dated_when_they_happened`.
   - `finance/seed.py` fecha la penalidad en su día (el de la cancelación; el de la auditoría nocturna siguiente
     a la llegada para un no-show, porque `mark_no_show` exige fecha de negocio > llegada) y la cobra ese mismo día.
     Solo mueve cargos hacia atrás (una penalidad publicada en vivo no se toca). Test:
     `finance/tests/test_seed.py::test_penalties_are_dated_and_paid_on_the_day_they_were_posted`.
   - Resultado: las penalidades "de hoy" bajaron de 33 a 4 en Casa Aurora (las 4 restantes son reservas no
     reembolsables creadas y canceladas hoy).
4. **Turno de caja "de hoy" abierto ayer** si el seed corre en la primera media hora después de medianoche (el turno
   abría "hace 30 min" = 23:5x del día anterior). Ahora nunca antes de las 00:00 de hoy. Test:
   `test_todays_shift_opens_today_even_when_the_demo_is_seeded_right_after_midnight`.
5. **`make check` no validaba el esquema OpenAPI**: ahora corre también `spectacular --validate --fail-on-warn`.
6. **Faltaba una herramienta repetible para el checklist de integración**: nuevo comando de solo lectura
   `python manage.py check_integrity [--property <slug>]` (`make check-data`) y el smoke por el proxy como script
   (`make smoke`). Ver "Herramientas".

## Seed (`seed_demo --reset`)

Corrida final sobre la BD de desarrollo (con reset de un demo completo ya cargado):

| | Casa Aurora | Andino Medellín | Andino Hostel Bogotá |
|---|---|---|---|
| Categorías / habitaciones | 3 / 24 | 3 / 40 | 5 / 13 (dorms por cama) |
| Reservas | 737 | 1.244 | 1.352 |
| checked_out / checked_in / confirmed / tentative / cancelled / no_show | 254 / 18 / 395 / 21 / 39 / 10 | 399 / 31 / 681 / 37 / 71 / 25 | 453 / 20 / 746 / 34 / 74 / 25 |
| Pagos aprobados | 514 | 847 | 954 |
| Links de pago (creados / aprobados / rechazado demo) | 72 / 257 / 1 | 123 / 415 / 1 | 125 / 487 / 1 |
| Turnos de caja (abierto hoy) | 6 (1) | 6 (1) | 0 |
| Hoy: llegadas (listas / sin asignar), salidas, en casa | 2 (1/1), 6, 18 | 5 (1/2), 7, 31 | 7 (2/3), 14, 32 |

Fuentes: recepción, teléfono, email, walk-in, booking engine, marketplace y OTA (BookSim/AirSim). 366 huéspedes.
0 alertas abiertas. Después se sumaron las 2 reservas del smoke (ver "Limitaciones").

Invariantes comprobadas (`check_integrity` + script ampliado del verificador, 0 fallas):
- `rebuild_inventory` sobre la ventana de estadías y el horizonte: **0 filas con deriva**; 0 noches futuras
  sobrevendidas.
- `Stay.total_amount` = Σ `nightly_rates` (una por noche); total de reserva = Σ estadías.
- `finance.reservation_balance` = anotación SQL `with_balance` en las 3.333 reservas; ninguna con saldo a favor;
  todo folio cerrado en 0 (folio y reserva); `folio_balance` = cargos − pagos + reembolsos.
- Estadías finalizadas: Σ cargos `room` = total; en casa: exactamente las noches hasta ayer; pendientes,
  canceladas y no-show: sin cargos `room`; penalidades = `cancellation_fee`.
- Toda reserva finalizada tiene cargos y pagos (6–8 % queda como cuenta por cobrar, a propósito); en casa: unas
  pagas y otras debiendo; confirmadas: ~60 % con depósito; **todas** las tentativas con link pendiente y sin pago.
- Cada link aprobado tiene exactamente un pago; nada fechado después de la fecha de negocio ni creado en el futuro;
  penalidades fechadas (y cobradas) el día en que ocurrieron; el turno abierto es de hoy.

Tiempos (host de 12 núcleos):
- BD nueva, perfilado (`SEED_OFFLINE=1`): **594 s ≈ 10 min** — bookings 411 s, su commit y receivers 15 s,
  finance 151 s, el resto ~20 s. Tiempo en receivers de señales: 23 s en total (`stay_checked_out` 14 s,
  `inventory_changed` 4 s, `payment_received` 4 s).
- `seed_demo --reset` sobre un demo completo, perfilado en una BD aparte: **694 s ≈ 11,6 min** (bookings 489 s,
  commit 15 s, finance 171 s); el reset en sí tarda 2 s (44.577 filas en cascada). La corrida que dejó cargada la BD
  de desarrollo tardó 23 min: tuvo la suite completa en paralelo y una pausa de ~6 min al empezar finanzas que no se
  reprodujo (ver "Limitaciones").

## Herramientas nuevas (para C-INT y D)

- `make check-data` → `python manage.py check_integrity [--property <slug>]` (`apps/core/management/commands/`):
  invariantes de inventario y dinero de solo lectura (el `rebuild_inventory` corre en una transacción revertida).
  Imprime `ok`/`FALLA` por chequeo con ejemplos y sale con error si algo falla. ~45 s con el demo completo. Tests:
  `apps/core/tests/test_check_integrity.py` (hotel coherente pasa; deriva, folio cerrado con saldo y estadía
  descuadrada fallan; no repara nada).
- `make smoke` → `python3 backend/scripts/smoke_proxy.py [base_url]`: el smoke de arriba (solo stdlib, desde el
  host). Deja una reserva confirmada del huésped "Smoke Integración".
- `make check` ahora incluye el esquema OpenAPI sin warnings.

## Rendimiento con el demo completo (por el proxy de Vite)

Medido sobre la primera carga del seed (mismo volumen que la final). 75 GET de staff (25 endpoints × 3 propiedades:
listas de reservas con filtros y búsqueda, detalle, calendario de 31 días, ofertas, disponibilidad, grilla de 30 y
90 noches, huéspedes con orden por estancias, detalle y estancias, folios, resumen de caja, turnos, links,
usuarios, roles): **todos 200, máximo 407 ms** (lista de huéspedes ordenada por estancias), la mayoría < 200 ms.
Calendario del hostel: 165 KB.

## Revisión en navegador (Chrome, contexto aislado)

Sobre la primera carga del seed (en la caja se vio el problema 3: "Cargos publicados hoy: $30.721.540"). Dueño de
Casa Aurora: grilla de tarifas con disponibilidad real ("Lleno" en la suite), huéspedes (estancias y última
estancia desde reservas), usuarios (buscador con `name`); recepción: caja con turno abierto, movimientos, cobros del
día e historial. Consola sin errores (solo el 401 conocido de `/me` en `/login`, documentado en A3).

---

## API implementada

Ninguna nueva. Comando de gestión `check_integrity` y script `backend/scripts/smoke_proxy.py` (arriba).

## Contratos implementados / consumidos

Sin cambios de firmas ni tipos (`apps/core/tests/test_contracts.py` en verde dentro de la suite completa).
`check_integrity` consume `bookings.services.inventory.rebuild_inventory`, `bookings.services.queries.with_balance`,
`finance.services.folio_balance` y `reservation_balance` (solo lectura).

## Señales emitidas / escuchadas

Ninguna nueva. Medido en el seed: 3.588 `inventory_changed`, 3.333 `reservation_created`, 2.366 `payment_received`,
2.210 `room_assigned`, 1.352 `stay_checked_in`, 1.271 `stay_checked_out`, 1.017 `folio_closed`, 184
`reservation_cancelled`, 122 `room_status_changed`, 60 `reservation_no_show`, 14 `rates_changed`.

## Automatizaciones registradas

Ninguna nueva. Beat programa las 5 de A+B: `core.cleanup` (04:30, plataforma), `bookings.auto_assign_rooms` (06:00),
`bookings.inventory_reconcile` (04:00), `bookings.release_expired_tentative` (*/15 min),
`finance.sync_pending_intents` (*/5 min).

## Proveedores de integración registrados

Ninguno nuevo (`payments`: simulado por defecto, Wompi real).

## Extensiones de frontend exportadas

Ninguna nueva. Cambios compartidos: `DataTable` (`name="search"`) y `src/test/setup.ts` (descarta toasts después
de cada test).

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

Ninguno pendiente de la Fase B.

## Para la Fase C (leer)

1. **Enums de OpenAPI**: si tu app agrega un campo de opciones llamado igual que otro (`kind`, `status`, `source`,
   `method`…) con opciones distintas, `test_schema.py` y `make check` fallan: agrega tu entrada a
   `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]` en C-INT (o anótalo en tus notas).
2. **Tests del shell/router (A2)**: `src/app/__tests__/shell.test.tsx` y `router.test.tsx` renderizan páginas reales
   en `/app` (Hoy, stub de C1), `/app/housekeeping` (C2), `/app/calendar` (C13), `/app/rates/plans` y
   `/app/settings/rooms`. Al reemplazar un stub que pide datos, esos tests imprimen `[MSW] Error: intercepted a
   request without a matching request handler`: agrega handlers vacíos ahí (en C-INT, que es quien toca archivos
   compartidos) o anótalo.
3. **Toasts en tests**: ya no hace falta `toast.dismiss()` por archivo; lo hace `src/test/setup.ts`.
4. **Señales del seed**: `seed_demo` emite al commit las señales de miles de operaciones históricas (números
   arriba). Los receivers de C2 (tareas de limpieza), C3 (ARI), C6 (emails), C11 (comisiones) deben ignorar lo
   histórico (p. ej. `stay.checkout_date < property.business_date - 1` o reservas creadas hace días) o su seed debe
   limpiarlo; si no, el demo amanece con cientos de tareas o correos. `stay_checked_out` ya cuesta 14 s en el seed:
   cuidado con receivers lentos (cada uno se ejecuta miles de veces).
5. **Fechas de negocio del seed**: pagos, cargos de noches, penalidades, check-in/out y creación de reservas están
   fechados cuando ocurrieron (−60…+90 días). Si tu seed agrega historia (C1 reportes de auditoría nocturna, C7
   facturas, C10), féchala igual; `check_integrity` exige que nada quede después de la fecha de negocio.
6. **Verificar al integrar**: `make check`, `make check-data` (tras el seed) y `make smoke`. El seed completo tarda
   ~10 min en BD nueva (más con carga): córrelo en segundo plano; `make reset` recrea todo.
7. **C2** necesita su propio endpoint de estado de limpieza (el de inventario exige `inventory.manage`). **C12**:
   `GET /api/v1/control/audit/{id}/` y `POST …/undo/` habilitan el "Deshacer" de la grilla de tarifas. **C6**:
   plantilla `payment_link`. **C4**: holds de tentativas suficientes para PSE (el link vence con el hold).

## Limitaciones conocidas / pendientes

- **Duración del seed**: ~10 min en BD nueva (≈ 0,12 s por reserva, todo por los servicios con auditoría y
  señales). La corrida con reset sobre el demo cargado tardó 23 min con la suite completa en paralelo y una pausa de
  ~6 min al empezar finanzas (sin eventos ni escrituras): no se reprodujo al repetir el reset con perfilado en una
  BD aparte. Si vuelve a aparecer, mirar `pg_stat_activity` durante la pausa.
- **Reservas del smoke**: en la BD de desarrollo quedan 2 reservas confirmadas extra en Casa Aurora, del 17 al 19
  de octubre (`HT-ARZVHC` y `HT-UDVY33`, huésped "Smoke Integración" `smoke.bint@example.com`, depósito del 30 % con
  tarjeta simulada): las dejaron el smoke final y la prueba de `make smoke`. Por eso Casa Aurora muestra 184
  huéspedes en vez de 183 y 739 reservas. `check_integrity` pasa con ellas.
- `/api/docs/` sigue cargando Swagger UI desde un CDN (heredado de A3; para D1 con `drf-spectacular-sidecar`).
- `/media/` lo sirve Django solo con `DEBUG` (fotos públicas; los documentos de huéspedes ya no están ahí). D1.
- El Andino Hostel no tiene turno de caja en el demo (el seed de finanzas solo abre turnos para recepción de Casa
  Aurora y de Andino Medellín); es así por diseño de B4.

## Cómo repetir

```bash
cd /home/breyner/Documents/new_project
docker compose down -v && docker compose up -d db redis mailpit
docker compose run --rm backend python manage.py migrate --noinput
docker compose run --rm backend sh -c "python manage.py makemigrations --check --dry-run && python manage.py check"
docker compose run --rm backend python manage.py seed_demo --reset      # ~10 min: en segundo plano
docker compose up -d
make check && make check-data && make smoke
docker compose run --rm -e TEST_DB_NAME=test_bint backend sh -c "ruff check . && ruff format --check . && pytest -q"
docker compose run --rm --no-deps frontend sh -c "npm run typecheck && npm run lint && npm run test \
  && npm run build -- --outDir /tmp/dist-check --emptyOutDir"
```

Archivos tocados en B-INT: `backend/config/settings.py`, `.gitignore`, `.env.example`, `Makefile`, `README.md`,
`backend/apps/core/management/commands/check_integrity.py` (nuevo), `backend/apps/core/tests/test_schema.py`,
`backend/apps/core/tests/test_check_integrity.py` (nuevo), `backend/scripts/smoke_proxy.py` (nuevo),
`backend/apps/bookings/seed.py`, `backend/apps/bookings/tests/test_seed.py`, `backend/apps/finance/seed.py`,
`backend/apps/finance/tests/test_seed.py`, `frontend/src/test/setup.ts`, `frontend/src/components/DataTable.tsx`,
`frontend/src/components/__tests__/DataTable.test.tsx`, `frontend/src/components/__tests__/Toaster.test.tsx`
(nuevo), `frontend/src/app/__tests__/shell.test.tsx`, `frontend/src/app/__tests__/router.test.tsx`,
`frontend/src/features/inventory/__tests__/PhotoGallery.test.tsx` y esta nota.
