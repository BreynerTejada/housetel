# C-INT — Integración de la Fase C (modo MVP) — integration notes

Estado: **checklist de C-INT completo** (2026-09-28, modo MVP: sin escribir ni correr suites de tests, por decisión
del usuario). Se aplicaron los "cambios requeridos" de las 13 notas C, se corrigieron 7 problemas de integración
encontrados al juntar los módulos, se recreó todo desde una BD vacía (migraciones + `seed_demo --reset` completo) y
se verificó por API, por automatizaciones y con un recorrido de las 69 rutas (+ 5 roles) en un Chrome headless
propio. El stack queda arriba con el seed completo cargado y worker y beat recién arrancados (programan las 20
automatizaciones). Sin commits; `.env` intacto; sin dependencias nuevas.

**Para la Fase E (validación en Chrome) lee "Checklist consolidado — cómo probar en la UI"** (al final). El resto
es evidencia y contexto.

---

## Checklist del plan (C-INT) → resultado

| Punto | Resultado |
|---|---|
| Cambios requeridos de las notas C1–C13 | Aplicados (tabla siguiente). Nada quedó `partial`: los 13 implementadores terminaron |
| `makemigrations --check` limpio y `migrate` desde BD nueva | `docker compose down -v` → BD vacía → `migrate`: **40 migraciones**, 0 pendientes; `makemigrations --check --dry-run` → "No changes detected"; `manage.py check` sin problemas |
| `seed_demo --reset` completo | **9 min 10 s** en BD nueva, sin errores (tiempos por app abajo). Worker y beat detenidos durante el seed. Idempotencia: un segundo `seed_demo` sobre el demo cargado (en transacción revertida) tarda 9 s y **no crea ninguna fila** |
| Datos coherentes | `make check-data` → **Integridad OK** en las 4 propiedades, incluidas 4 invariantes nuevas de la Fase C. Sin datos espurios por señales históricas: tareas de limpieza solo de hoy, **0 correos** en Mailpit tras el seed, comisiones = solo reservas del marketplace, cola ARI vacía |
| OpenAPI | `spectacular --validate --fail-on-warn` → **0 warnings** (antes 10) |
| Frontend | `typecheck` ✓, `lint` ✓ (todo `eslint .`), `build` ✓ (contenedor, Node 24) |
| Backend lint | `ruff check .` y `ruff format --check .` limpios en todo el backend (formateé los tests heredados de C3/C5/C7, sin cambiar lógica) |
| Beat registra todas las automatizaciones | **20 entradas** (las 15 del spec §6 + `bookings.inventory_reconcile`, `ai.daily_brief`, `compliance.tra_retry`, `distribution.pull_bookings`, `core.cleanup`). Worker registra `core.run_automation`, `control.run_automation_now`, `distribution.push_ari_queue` |
| Cada automatización corre con `automation.run` manual | `make check-automations`: **75 corridas, 0 fallidas** (20 × propiedades + plataforma + auditoría nocturna manual), en transacción revertida. Además el **worker** ejecutó de verdad 9 de ellas y beat viene corriendo las frecuentes (`push_ari` cada minuto, `*/5`, `*/10`, `*/15`): 0 fallidas |
| `make smoke` | **SMOKE OK · 27 requests**, ampliado con 4 pasos de la Fase C (Hoy, portal del huésped, BookSim → PMS → cancelación de la OTA, WhatsApp → bandeja) |
| Endpoints principales con el seed | `make sweep` (nuevo): **308 GET, 0 errores** (91 por propiedad × 3 + super-admin + públicos); el más lento es la vista previa de la auditoría nocturna (~1 s), el resto < 400 ms |
| Rutas del frontend (§E) sin errores de consola | `make routes` (nuevo, Chrome headless propio): **80 visitas OK a 1440 px y a 375 px** = las 69 rutas + 11 de roles (aterrizaje en `/app` de limpieza, mantenimiento, recepción y contabilidad, y sus páginas); sin excepciones, sin `console.error`, sin respuestas API ≥ 400 inesperadas, sin overlay de Vite y **sin scroll horizontal** |
| Suite backend / `npm run test` | **No se corrieron** (modo MVP). Ver "Pendientes" |
| Notas | Este archivo; README actualizado |

## Cambios requeridos de las notas C → aplicados

| Origen | Cambio | Dónde |
|---|---|---|
| C7, C8, C9 (+ colisiones de C1/C5/C6 citadas) | `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]`: `InvoiceStatusEnum`, `InvoiceKindEnum` (mismo set que `InvoiceResolution.DocumentKind`), `SireReportStatusEnum`, `TraRegistrationStatusEnum`, `IntegrationModeEnum` (real/simulado de core, finanzas y compliance), `PricingRuleKindEnum`, `RateRecommendationStatusEnum`, `RevenueRunStatusEnum`, `LanguageEnum` (es/en con etiquetas), `LanguageCodeEnum` y `ModeCodeEnum` (códigos pelados de los serializers de IA e inventario). De 10 warnings a 0 | `backend/config/settings.py` |
| C3, C8, C9, C11, C12 | Reiniciar worker y beat con el código nuevo | Se levantaron de cero después del seed (con `down -v`); tras el último cambio de revenue reinicié el worker |
| C3 | `distribution.pull_bookings` en la verificación de beat | Incluida (20 entradas) |
| C11 | `KpiTile`: la tabla `sr-only` del sparkline desbordaba el viewport | `frontend/src/components/KpiTile.tsx` (la tabla va dentro de un `div.sr-only` recortado); quité el parche local de `saas/pages/admin/AdminHomePage.tsx` |
| C5, C7, C12 | `/app/reservations/:id` medía ~530–590 px a 375 px | `frontdesk/pages/ReservationDetailPage.tsx`: `grid-cols-1` en el contenedor y el resumen, `min-w-0` en `Tabs`. Verificado: 0 px de desborde a 375 |
| C7 | Unificar la convención de `ReservationAction` | Ya estaba unificada (C5 corrigió sus acciones): el host (C1) pone el `Dialog`; la acción solo dibuja el cuerpo. Documentado en `src/app/extensions.ts` (JSDoc de `ReservationAction`) y en el comentario de `guestportal/reservation-actions.tsx` |
| C1, C2, C4, C6, C7, C8, C12, C13 | Handlers MSW para `shell.test.tsx` y `router.test.tsx` (el shell y Hoy ya piden datos) | `src/test/shell.ts` (`apiNotFoundFallback`: toda API GET sin handler propio responde 404 vacío en esos 2 archivos) + registro en sus `beforeEach`; el test del motor `/h/casa-aurora` ahora da la config del motor y afirma la marca del hotel. **Sin correr** (modo MVP) |
| C11 (opcional) | Dueño de organización suspendida → aterriza en facturación | `frontend/src/lib/auth.tsx` (`homeFor`): si todas sus organizaciones con propiedades están `suspended` y puede ver facturación → `/app/settings/billing` |
| C2 (opcional) | Usuario de mantenimiento en el demo | `apps/core/seed.py`: `mantenimiento@casaaurora.co` (Jorge Castillo, rol `maintenance`); el seed de C2 le pone "en curso" el ticket del bombillo |
| C1 (sugerido, parcial) | La auto-asignación mandaba llegadas de hoy a habitaciones donde el huésped que sale hoy sigue adentro | `apps/bookings/services/assignment.py`: para llegadas de hoy/atrasadas, una unidad con una estadía `checked_in` que termina ese día (o antes) cuenta como "no lista", igual que una sucia. Aplica a `auto_assign_rooms` (06:00), a la asignación al hacer check-in y al orden de `room-options`. El 409 `room_occupied` en `check_in` queda para D1 (ver Pendientes) |
| C2 | Throttle de login compartido por todos a través del proxy de Vite | `settings.py`: `LOGIN_THROTTLE_RATE` (env) con 30/min por defecto en desarrollo (`DEBUG` y fuera de pytest) y 10/min en producción y en tests; documentado en `.env.example` |
| C4, C9, C12 (opcionales / D1) | `NUM_PROXIES`, `rates.create_extra`, `default` en selects de proveedores, 409 de B2b | No aplicados: ver Pendientes |

## Problemas de integración encontrados y corregidos

1. **Falsas alarmas "Check-in sin TRA" en el hostal** (15 alertas repetidas por reserva). Causa: la regla de C9
   (`ai.anomaly_scan`) revisaba toda estadía en casa sin TRA registrada, pero en un dormitorio las camas extra de una
   reserva no tienen huéspedes con nombre, así que C7 no tiene a quién registrar (su `lodged_guests` solo cuenta los
   ocupantes y al titular en la primera estadía). Arreglo en `apps/ai/anomalies.py::missing_tra`: solo estadías con
   ocupantes o la primera de la reserva. Resultado: 1 alerta legítima en el hostal y 1 en Medellín (datos
   faltantes), y el scan siguiente resolvió solas las otras 14.
2. **Llegadas asignadas a habitaciones todavía ocupadas** (lo reportó C1): ver la fila de C1 arriba.
3. **Cuota de Gemini consumida por los resúmenes de revenue**: `revenue.run_rules` corre 4 veces al día por hotel y
   cada corrida pedía su resumen a Gemini (12 llamadas diarias de una cuota gratuita de 20, más el resumen del día
   de C9). Nuevo parámetro `ai_summary_once_a_day` (por defecto activo): las corridas programadas piden el resumen IA
   solo la primera vez del día; las demás usan el resumen determinístico. "Correr ahora" (manual) siempre lo pide.
   Configurable en `/app/settings/automations` → Revenue → Parámetros (etiquetas ES/EN agregadas en `control`).
   Archivo: `apps/revenue/automations.py`. Verificado: programada → `pending` (IA), segunda programada → `skipped`,
   manual → `pending`.
4. **Esquema OpenAPI con 10 warnings** (enums de C7/C8/C9 que chocaban con los de core/finanzas/cuentas): overrides.
5. **Desborde horizontal a 375 px** en el detalle de reserva (C1) y en tiles con sparkline (`KpiTile` compartido).
6. **`ruff` del backend en rojo** por 16 archivos de tests heredados de C3/C5/C7 sin formatear y 7 líneas largas:
   `ruff format` + `noqa` en líneas de fixtures exactas (sin tocar lógica).
7. **`make seed` repetido no era del todo idempotente**: el seed de tarifas (B2a) volvía a llamar a
   `provision_rates` en cada corrida, que no duplica datos pero audita "Tarifas iniciales" y vuelve a agregar todas
   las categorías a los planes (deshaciendo ediciones del usuario). Ahora solo aprovisiona si la propiedad no tiene
   el plan FLEX (`apps/rates/seed.py`). Con eso una segunda corrida completa no crea ni una fila.

Verificado de punta a punta por API (además del smoke), con datos del seed:
- **Check-out → housekeeping + DIAN + folio** (Andino Medellín, HT-YW3DB6): tarea "Limpieza de salida", factura
  `SETT214` aceptada al instante (receiver de C7), folio cerrado, habitación 206 sucia.
- **Check-in → TRA** (Andino Medellín, HT-XVQASN): 2 registros TRA `registered` (titular y acompañante).
- **Marketplace → comisión → reversa** (Andino Medellín, HT-5UF334): reserva `marketplace` confirmada (pago en el
  hotel) → comisión `pending` de $45.760 (10 % del alojamiento sin IVA) → cancelada sin penalidad → `reversed`.
- **BookSim → PMS → cancelación** (smoke): la reserva llega como `ota`/`booksim` confirmada y la cancelación de la
  OTA la cancela en el PMS.

## Seed (`seed_demo --reset` sobre BD nueva)

`docker compose down -v` → `migrate` → `seed_demo --reset` con worker y beat **detenidos** (si no, beat despacha
mensajes y ARI sobre datos a medio sembrar). Tiempos (host de 12 núcleos; ahora el comando los imprime por app):

| App | s | App | s | App | s |
|---|---|---|---|---|---|
| inventory | 10,4 | housekeeping | 2,1 | compliance | 33,8 |
| rates | 0,9 | distribution | 5,0 | revenue | 0,5 |
| guests | 4,2 | marketplace | 0,1 | ai | 0,0 |
| bookings | 346,7 | guestportal | 2,1 | saas | 0,4 |
| finance | 131,7 | messaging | 1,1 | frontdesk | 3,1 |
| | | | | reports / control | 1,6 / 0,5 |

Total **9 min 10 s** (las apps de la Fase C suman ~50 s).

Estado sembrado (fecha de negocio **2026-09-28** en las 4 propiedades):

| | Casa Aurora | Andino Medellín | Andino Hostel Bogotá |
|---|---|---|---|
| Reservas | 746 | 1.258 | 1.358 |
| Hoy: llegadas / salidas / en casa | 5 / 5 / 13 | 3 / 4 / 27 (antes de mis pruebas) | 11 estadías / 12 / 28 |
| Tareas de limpieza de hoy | 18 (6 hechas, 1 en curso) | 47 (con inspección) | 9 (sin personal) |
| Tickets de mantenimiento | 3 (uno bloquea la 206) | 3 | 3 |
| Documentos DIAN (incl. 1 nota crédito) / reportes SIRE / TRA | 132 / 2 / 19 | 214 / 2 / 31 | 255 / 2 / 26 |
| Conversaciones (bandeja) | 5 | 5 | 5 |
| Recomendaciones de revenue pendientes | 240 | 236 | 426 |
| Reportes de auditoría nocturna | 30 | 30 | 30 |
| Check-ins online completados (próx. 3 días) | 6 | 8 | 11 |

Plataforma: 3 planes, 14 facturas de plataforma pagadas, 638 comisiones (508 pendientes, 114 liquidadas, 16
revertidas al sembrar), org **Hostal Demo Trial** en prueba (`owner@hostaldemo.co`), MRR $1.248.000.

`check_integrity` (`make check-data`, ~35 s) sumó una sección de la Fase C: comisiones solo de reservas del
marketplace y cada reserva del marketplace confirmada/en casa/finalizada con la suya; toda reserva OTA vinculada a
su canal (`ExternalReservationMap`); nada de la Fase C fechado después de la fecha de negocio (tareas de limpieza,
reportes de auditoría) y ninguna factura emitida en el futuro. Todo **ok**.

## Automatizaciones

Beat (horario estático desde el registro; zona `America/Bogota`):

| Código | Horario | Código | Horario |
|---|---|---|---|
| `frontdesk.night_audit` | 02:00 | `messaging.lifecycle_dispatch` | cada 10 min |
| `saas.billing_cycle` (plataforma) | 03:00 | `distribution.push_ari` | cada minuto |
| `bookings.inventory_reconcile` | 04:00 | `distribution.pull_ical` | cada 15 min |
| `saas.commission_settlement` (plataforma) | día 1, 04:00 | `distribution.pull_bookings` | cada 5 min |
| `core.cleanup` (plataforma) | 04:30 | `finance.sync_pending_intents` | cada 5 min |
| `revenue.run_rules` | 05, 11, 17 y 23 h | `bookings.release_expired_tentative` | cada 15 min |
| `bookings.auto_assign_rooms` | 06:00 | `compliance.issue_pending_invoices` | cada 15 min |
| `housekeeping.generate_daily_tasks` | 07:00 | `compliance.tra_retry` | cada 15 min |
| `housekeeping.auto_assign` | 07:15 | `ai.anomaly_scan` | cada hora |
| `ai.daily_brief` | 07:30 | `compliance.sire_daily_file` | 08:00 |

`make check-automations` (nuevo, `backend/scripts/automations_check.py`): corre cada una en cada propiedad en una
transacción revertida, con el LLM en simulado dentro de la transacción (no gasta cuota). Resultado: 75 corridas, 0
fallidas. Resultados típicos: auditoría programada "omitida: la fecha está al día"; manual → "1 día cerrado: 8
noches publicadas, 5 no-shows" en Casa Aurora; revenue 240/236/426 recomendaciones; `tra_retry` `partial` (1
huésped con datos faltantes por hotel, esperado); `housekeeping.auto_assign` `partial` en el hostal (no tiene
personal de limpieza, esperado).

Qué cambia sola la demo en las próximas horas (útil para la validación):
- **`compliance.issue_pending_invoices` ya emitió** (01:15) las 2 salidas "sin factura" que dejó el seed de C7 para
  la demo de Pendientes (su ventana es de 3 días). Pendientes → Facturas queda en 0; el flujo de emisión se ve al
  hacer un check-out o con "Emitir factura" en la pestaña Legal de una reserva en casa.
- A las 02:00 del **29-sep** la auditoría nocturna cierra el 28: la fecha de negocio pasa a 29-sep, las llegadas del
  28 sin check-in quedan no-show y se publican las noches. Validar el mismo día o contar con ese salto.
- 05:00 revenue (1 resumen IA por hotel), 06:00 `auto_assign_rooms` (asigna las llegadas de hoy y mañana que el
  seed deja sin habitación; hoy Casa Aurora tiene 4 de 5 sin asignar), 07:30 resumen del día (IA).

## Herramientas nuevas (para E, D1 y la fase de tests)

| Comando | Qué hace |
|---|---|
| `make check-data` | Ahora también las invariantes de la Fase C (arriba) |
| `make check-automations` | Todas las automatizaciones × propiedades en transacción revertida (~12 s) |
| `make smoke` | Smoke por el proxy + Hoy, portal, BookSim ⇄ PMS y WhatsApp → bandeja (~5 s) |
| `make sweep` | `backend/scripts/endpoints_sweep.py`: 308 GET de solo lectura de todos los módulos, dueños de ambas organizaciones, super-admin y APIs públicas; tabla de los más lentos |
| `make routes` | `frontend/scripts/route-smoke.mjs`: abre las 69 rutas (y el aterrizaje de 4 roles más) en un Chrome headless propio (perfil temporal, puerto 9557; nunca el navegador compartido) y reporta excepciones, `console.error`, API ≥ 400, overlay de Vite, falta de `<h1>` y desborde horizontal. `WIDTH=375` para celular, `ONLY=/app/revenue,/app$` para filtrar. Necesita Node ≥ 22 y Chrome en el host (`CHROME=`) |

## Datos de prueba que dejé en la BD de desarrollo

- `make smoke`: **HT-PRZ5RA** (Casa Aurora, 18–20 oct, "Smoke Integración", depósito 30 %), **HT-QTHBQ7** (BookSim,
  Casa Aurora, cancelada por la OTA) y el hilo de WhatsApp **+57 300 555 0101 "Smoke WhatsApp"** (sin leer). Cada
  corrida de `make smoke` deja otro juego.
- Pruebas cruzadas en **Andino Medellín**: check-out de **HT-YW3DB6** (hab. 206, factura SETT214) y check-in de
  **HT-XVQASN** (hab. 401, TRA); reserva del marketplace **HT-5UF334** (cancelada, comisión revertida); y
  **HT-DDB846** (AirSim, 26 dic) quedó **cancelada por error** en una prueba: la cancelé también en el simulador de
  AirSim (OTA y PMS coinciden) y reembolsé su pago de $1.064.000, porque `check_integrity` marcaba el saldo a favor.
  Casa Aurora quedó intacta salvo el smoke. En Mailpit quedan los 6 correos de esas pruebas.
- Un `seed_demo --reset` (o `make reset`) deja todo como recién sembrado.
- Ojo en la Fase E: cancelar una reserva **ya pagada** deja saldo a favor hasta reembolsarla desde el folio; mientras
  tanto `make check-data` lo reporta ("saldos: ninguna reserva con saldo a favor"). Es esperado, no un bug.

## Pendientes y limitaciones

- **Tests (modo MVP)**: no se escribieron ni corrieron. Hay tests heredados de intentos anteriores en casi todas las
  apps C (backend y frontend) que pueden estar desactualizados (las notas C1–C13 listan los probables). Los handlers
  de `shell.test.tsx`/`router.test.tsx` quedaron puestos pero sin correr. La fase de tests va después de E.
- **B2b / D1**: `check_in` no responde 409 `room_occupied` cuando otra estadía `checked_in` ocupa la misma
  habitación o cama (la UI de C1 lo avisa y la auto-asignación ya lo evita). `check_out` y mover a un huésped en casa
  ponen `dirty` una habitación `out_of_service` (C2 lo compensa).
- **D1**: `REST_FRAMEWORK["NUM_PROXIES"]` en producción para los throttles por IP (C4); `/api/docs/` con Swagger por
  CDN (A3); `/media/` solo con `DEBUG` (B1/C4); chunk de i18n de 539 KB (todas las traducciones en el bundle
  inicial: aviso de Vite, no error).
- **Proveedores reales sin probar en vivo** (no hay credenciales en `.env`): Channex, Wompi plataforma, Meta WhatsApp,
  Factus, TRA/MinCIT, Claude. Gemini sí (C9), con cuota gratuita de 20 llamadas/día: con la cuota agotada todo cae al
  asistente simulado (preguntas concretas).
- `accountant` aterriza en `/app/calendar` (primera página visible del menú); podría ser Reportes.
- Hora de la auditoría nocturna fija a las 02:00 (el horario de beat es estático) y horarios de automatizaciones en
  la zona de `CELERY_TIMEZONE`.
- Opcionales no aplicados: servicio `rates.create_extra` para el onboarding de C9; `default` en los selects
  obligatorios de los proveedores (C12 ya asume la primera opción).

---

## Checklist consolidado — cómo probar en la UI (Fase E)

**Entorno.** App **http://localhost:5173** · Mailpit **http://localhost:8025** · clave de todos: **`housetel123`**.
Fecha de negocio **lunes 28-sep-2026** (ver arriba qué cambia a las 02:00 del 29). Todo corre en modo simulado
salvo email (SMTP → Mailpit) y el LLM (Gemini real, cae a simulado).

| Usuario | Rol / para qué |
|---|---|
| `owner@casaaurora.co` (Valentina Rojas) | Dueño de Hotel Casa Aurora (Cartagena, 24 hab.): casi todo el checklist |
| `recepcion@casaaurora.co` (Andrés Gómez) | Recepción (turno de caja abierto: puede cobrar en efectivo) |
| `limpieza@casaaurora.co` (Luz Marina Pérez) | Housekeeping (vista móvil) |
| `mantenimiento@casaaurora.co` (Jorge Castillo) | Mantenimiento (**nuevo**): tickets |
| `contabilidad@casaaurora.co` (Carolina Díaz) | Contabilidad (solo lectura de operación; finanzas, reportes, legal) |
| `owner@grupoandino.co` (Santiago Restrepo) | Andino Medellín (40 hab., inspección obligatoria) y Andino Hostel Bogotá (dormitorios por cama) |
| `limpieza@grupoandino.co` | Housekeeping de Andino Medellín |
| `owner@hostaldemo.co` (Mariana Cárdenas) | Org "Hostal Demo Trial" en prueba, sin inventario (para signup/prueba/mora sin tocar el demo) |
| `admin@housetel.co` | Super-admin → `/admin` |

**Datos de hoy en Casa Aurora** (seed actual; si ya se usaron, tomar cualquier equivalente):
- Llegadas (5): **HT-DPZNNK** Luisa Fernanda Hernández Pérez, hab. **306** inspeccionada → chip **Lista**, check-in
  online ya hecho, saldo $1.160.500; **HT-3A5UVK**, **HT-PG3XW8**, **HT-66W5BZ**, **HT-TWCZRF** sin habitación hasta
  la auto-asignación de las 06:00 (el diálogo de check-in propone una limpia y libre).
- Salidas (5): **HT-FGMNUP** Michael Miller hab. 102 (debe $302.440) · **HT-Z7T4QM** Julien Durand 107 ($0) ·
  **HT-QCB8Q3** Juan Pablo Vargas Ríos 108 ($0) · **HT-238JNH** Carlos Pérez Mejía 203 (debe $537.570) ·
  **HT-SKM3WX** Freya Williams 304 (debe $1.072.000).
- Bandeja: WhatsApp de **Juan Pablo Vargas Ríos** (HT-QCB8Q3) "¿Tienen toallas para la playa?", **Carolina Mejía**
  (pregunta disponibilidad, sin reserva), **Luisa Fernanda Hernández Pérez** (HT-DPZNNK, vuelo 9:40 p. m.); email de
  **Juan Pablo González Jiménez** (HT-HJBDFN, cama extra).
- Limpieza: ticket «Aire acondicionado no enfría» **bloquea la 206**; «Grifo del lavamanos gotea» en la 102 (con
  foto); «Bombillo fundido» en curso con Jorge Castillo.
- Links del portal: `docker compose exec -T backend python manage.py portal_links --property casa-aurora --days 3
  --status not_started` (hoy: HT-66W5BZ, HT-TWCZRF; mañana: HT-4KVEXH…).

**Orden recomendado**: flujos 1–12 y 14–15 en cualquier orden; **la auditoría nocturna manual (13b) al final**
(mueve la fecha de negocio y marca no-shows); para suspender/mora usar **Hostal Demo Trial** o un hotel creado con
el signup, no Casa Aurora; deshacer lo que cambie precios o modos (auto-aplicar de revenue, integraciones en real).
El detalle fino de cada módulo está en su nota (`C<n>-*.md`, sección "Cómo probarlo en la UI").

### Flujos E2E del spec §10.1

**1. Recepción → limpieza** (`/app`, `recepcion@casaaurora.co`; C1, C2, C7)
1. `/app` (Hoy): saludo, fecha de negocio, 5 cifras (ocupación 56,5 % "13 de 23", llegadas 0 de 5, salidas 0 de 5,
   en casa 13, ingresos/ADR), Movimientos de hoy (Llegadas / Salidas / En casa), tablero de llaves por piso y
   widgets (Alertas, Limpieza de hoy, Check-in online de hoy, Ocupación 14 días, Recomendaciones de precio,
   Pendientes legales, según permisos).
2. Llegadas → **Check-in** de HT-DPZNNK → diálogo con datos del huésped, check-in online "completado", hab. 306 y
   saldo con `FolioPanel` compacto → Confirmar → toast "Check-in hecho… en la 306", la fila pasa a En casa, la llave
   306 se vuelve terracota. Con una llegada sin habitación el diálogo propone una limpia y libre.
3. Salidas → **Check-out** de HT-FGMNUP (102): "Confirmar check-out" bloqueado mientras debe → cobrar en el folio
   (efectivo: recepción tiene turno) → saldo 0 → confirmar → la 102 queda **sucia** (llave arena).
4. `limpieza@casaaurora.co` en `/app/housekeeping/mine` a **375 px**: la "Limpieza de salida" de la 102 queda
   habilitada (o se crea asignada a Luz Marina) → **Iniciar** → **Terminar** → en `/app/housekeeping` (dueño) la
   102 queda **Limpia**.
5. La reserva del check-out (pestaña **Legal**) ya tiene su factura DIAN **aceptada** (sello, CUFE, PDF), y la del
   check-in sus registros **TRA**.

**2. Calendario** (`/app/calendar`, `owner@casaaurora.co`; C13)
- Carga 14 días con categorías, filas de disponibilidad/precio, "Sin asignar", el bloqueo rayado de la 206, línea de
  hoy. Rango 7/14/30, filtros, búsqueda por apellido.
- **Arrastrar** una reserva futura (p. ej. HT-YCH4FN, hab. 101, 4–7 oct) a otra habitación libre de su categoría →
  toast con **Deshacer**; soltar sobre una ocupada → toast rojo "Ocupada por …" y no cambia (**doble asignación
  bloqueada**). A otra categoría → diálogo upgrade/recotizar. Estirar el borde derecho → diálogo de fechas con total.
- **Arrastrar sobre días vacíos** → "Nueva reserva" con tarifas → elegir huésped → "Crear reserva" → barra nueva.
  "Abrir en el asistente" → `/app/reservations/new?...` prellenado.
- Asistente `/app/reservations/new`: 5 pasos (fechas → ofertas → `GuestPicker` → extras → garantía) → detalle de la
  reserva nueva. **Walk-in** desde Hoy: asigna habitación limpia y hace el check-in.
- Hostel (selector de propiedad → Andino Hostel Bogotá): dormitorios con camas como filas; crear sobre una cama.

**3. Inventario con herencia** (`/app/settings/room-types`, `/app/settings/rooms`, `/app/settings/custom-fields`; B1)
- Crear un campo personalizado; editar una categoría; en una habitación (p. ej. la 306, que ya tiene overrides) ver
  valores heredados en gris, "Sobreescribir" y "Restaurar herencia".

**4. Grilla de tarifas** (`/app/rates`; B2a, C12)
- Edición masiva de fines de semana en un rango → el plan derivado (No reembolsable −12 %, Con desayuno) se
  recalcula; poner min LOS 3 en una noche y cotizar 1 noche en el asistente → la oferta no aparece o da
  restricción. **Deshacer** de la grilla funciona (usa la auditoría de C12).

**5. Marketplace** (`/`, anónimo; C4, B4, C11)
- `/` → buscar **Cartagena**, 20–22 oct, 2 adultos → `/search` con Hotel Casa Aurora → `/hotel/casa-aurora` →
  1 Estándar · Tarifa flexible → **Reservar** → checkout: Habeas Data obligatorio; nacionalidad y residencia
  **Estados Unidos** → "Exento de IVA de alojamiento" y total recalculado → **Pagar ahora** → pasarela simulada
  `/sim/pay/<ref>` → **Pagar** → `/booking/<código>/confirmed` "Tu reserva está confirmada" (portal, .ics).
- En el PMS (`owner@casaaurora.co`) la reserva con fuente marketplace; en `/app/settings/billing` → Comisiones del
  marketplace (o `/admin/commissions` buscando el código) aparece **Pendiente** (10 % del alojamiento sin IVA).
  Cancelarla sin penalidad desde el PMS → comisión **Revertida**.

**6. Booking engine y widget** (anónimo; C4)
- `/h/casa-aurora?checkin=2026-10-20&checkout=2026-10-22&adults=2`: sin header de Housetel, marca y color del hotel,
  mismo flujo en `/h/<slug>/book`. `/h/andino-hostel-bogota?...&adults=3` → "3 camas para tu grupo".
- `/embed/casa-aurora`: caja compacta → "Ver disponibilidad" abre `/h/casa-aurora?...`.
- `/app/settings/booking-engine` (dueño): color con vista previa en vivo, logo/portada, planes vendibles, snippet
  `<iframe>` copiable, pestaña Marketplace (apagar "Aparecer en el marketplace" lo saca de `/search`).

**7. Portal del huésped y check-in online** (link de `portal_links`, anónimo, **375 px**; C5)
- `/g/<token>` de HT-66W5BZ: tarjeta de la reserva con "Haz tu check-in online", cuenta con **Pagar**, extras,
  solicitudes, mensajes, cambios/cancelación, datos del hotel y la burbuja del chatbot.
- `/g/<token>/checkin`: Huéspedes (fecha de nacimiento, viaje) → Documentos (subir p. ej.
  `backend/media/photos/seed/casa-aurora-1.jpg`) → Llegada ("Aún no lo sé") → **firma** + aceptar términos → Pago o
  "Pagar en el hotel" → **Listo**.
- Recepción: en Hoy la llegada muestra **"Check-in online listo"**; el detalle tiene la pestaña **Check-in online**
  (datos, miniaturas privadas del documento, firma) y **Solicitudes**; "Más acciones" → **Enviar link de check-in**
  (correo en Mailpit) y **Copiar link / QR**. Un token alterado → "Este enlace no es válido".

**8. Canales y simulador de OTAs** (`/app/channels`, `/app/simulators/ota`, dueño; C3)
- Canales: tarjetas **BookSim** (+15 %) y **AirSim** (+12 %) "Activa · Simulado", Registro y Cola de envíos.
- Simulador → BookSim: grilla ARI (DBL FLEX entre semana = precio del plan × 1,15) → tocar un precio futuro →
  **Reservar en BookSim** → toast "BS-… → HT-…" y la reserva en el PMS (fuente OTA, canal booksim).
- AirSim, esas noches: las unidades bajan en 1 y **brillan** en ≤ ~10 s (worker con debounce).
- Cambiar un precio en `/app/rates` → en BookSim la celda muestra precio × 1,15 en ≤ ~10 s. Modificar y cancelar
  desde "Reservas de la OTA" → el PMS los refleja. Hostel → tarjeta Airbnb (iCal) con **Copiar URL** (.ics).

**9. WhatsApp y email** (`/app/inbox`, `/app/simulators/whatsapp`, dueño o recepción; C6, C9)
- Topbar: ícono de bandeja con no leídos → hilo de Juan Pablo Vargas Ríos (toallas): burbujas, nota interna,
  "Ventana de WhatsApp abierta" → responder `Hola {{guest.first_name}}, ya te las llevamos **en 10 minutos**` →
  entregado ✓✓. "Plantilla" y **Borrador IA**.
- Simulador: "Otro número" `+57 300 555 0199`, "Paula Díaz" → escribir "Hola, ¿tienen parqueadero?" → "Ver en la
  bandeja" → responder → la respuesta aparece en el teléfono en ≤ 3 s.
- Email: responder el hilo de Juan Pablo González Jiménez → en **Mailpit** llega "Re: …" con el layout Housetel.
  Crear una reserva confirmada con email → Mailpit "Reserva confirmada · HT-…"; cancelarla → "Reserva cancelada".
- `/app/settings/messaging`: plantillas ES/EN con variables y vista previa real; pestaña Mensajes automáticos.

**10. Legal Colombia** (`/app/compliance`, dueño; C7)
- Tarjetas DIAN / SIRE (tira de 30 días) / TRA; Facturas (hoja con sello, CUFE, QR, **Ver PDF**, XML); **Anular con
  nota crédito** escribiendo el número; SIRE → **Generar archivo** (TXT) y **Marcar como reportado** (acuse
  simulado); TRA por huésped con **Reintentar**. Pendientes: facturas en 0 (la automatización ya emitió las del
  seed), TRA con datos faltantes, SIRE por subir.
- Factura al check-out y TRA al check-in: ver flujo 1.5. Reserva en casa → pestaña **Legal** → **Emitir factura**
  (vista previa con IVA/exento).
- `/app/settings/compliance`: resolución SETT 1–5000, reglas DIAN, códigos SIRE/TRA.

**11. Revenue** (`/app/revenue`, dueño; C8, B2a)
- KPIs (240 pendientes), heatmap categoría × 30 noches (12-oct festivo) → **Correr ahora** → toast y resumen IA
  ("Escribiendo el resumen con IA…" → Gemini o "Resumen automático") → celda → detalle con razones → **Explicar con
  IA** → **Aprobar y aplicar** → **Ver la grilla de tarifas**: esa noche con el precio nuevo (fuente revenue).
- Masivo (barra de selección), Reglas (5 tarjetas; nueva regla tipo Evento con "Probar con los datos de hoy"),
  Límites, Historial, Ajustes (**auto-aplicar**: activarlo y volver a apagarlo).

**12. IA** (dueño; C9, C11)
- **Copiloto** (botón arriba o Ctrl+J): "¿Cuántas llegadas hay hoy?" → lista de las 5 llegadas; "Crea una reserva
  para Ana Torres del 12 al 14 de octubre para 2 adultos" → tarjeta **Acción propuesta** → **Confirmar** → "Ejecutada"
  + Abrir la reserva (auditoría con fuente IA). Recepción no puede confirmar "Bloquea la 110…"; limpieza no ve el
  botón.
- **Onboarding vía signup**: `/signup` (anónimo) → hotel nuevo (9 habitaciones, correo nuevo) → `/app/getting-started`
  (chip "Prueba · 14 días", 0 de 7) → "Crea tus habitaciones con ayuda de la IA" → `/app/onboarding` → **Usar un
  ejemplo** → **Proponer configuración** → revisar → **Crear todo** → categorías, habitaciones y tarifas creadas.
- **Chatbot público** en `/h/casa-aurora`: "¿Tienen habitación del 12 al 14 de octubre para 2 adultos?" → tarjetas
  con **Reservar**; "¿Tienen parqueadero?" (FAQ); "Quiero hablar con una persona" → formulario → alerta "Un huésped
  pide hablar con el equipo" + hilo "Chat web" en la bandeja. `/app/settings/chatbot` y `/app/settings/ai`.

**13. Auditoría y automatizaciones** (dueño; C12, C1)
- a) Mover una reserva de habitación (calendario o "Asignar habitación") → `/app/settings/audit` (o pestaña
  **Historial** de la reserva) → "Asignó la habitación…" → **Deshacer** escribiendo **DESHACER** → la estadía vuelve
  a su habitación y aparece "Deshizo: …".
- `/app/settings/automations`: agrupadas por módulo con riel de 24 h y próxima ejecución; **Ejecutar ahora** en
  "Conciliación de inventario" → toast con el resumen; Historial; Parámetros (p. ej. Revenue: "Resumen con IA solo
  en la primera corrida programada del día").
- b) **Al final**: `/app/night-audit` → vista previa (noches a publicar, no-shows, salidas vencidas) → **Cerrar el
  día** → la fecha de la barra superior pasa a **29-sep**, el cierre aparece en "Cierres anteriores" (30 del seed +
  el nuevo). "Ejecutar ahora" de la auditoría en Automatizaciones responde "omitida: la fecha de negocio está al día".

**14. Super-admin** (`admin@housetel.co`; C11)
- `/admin`: MRR $1.248.000, tiles con sparkline (sin desborde), gráficos por mes. `/admin/organizations` (3 orgs) →
  detalle de **Hostal Demo Trial** → **Suspender** (escribir el slug) → como `owner@hostaldemo.co` al entrar
  aterriza en **Plan y facturación** (nuevo) con el aviso rojo; el resto de la app responde 402 → admin
  **Reactivar**. **Terminar prueba ahora** → "Pago pendiente" → el dueño paga desde facturación → Activa.
- `/admin/commissions` → **Liquidar un mes** (agosto 2026: idempotente); `/admin/billing` → **Correr ciclo de
  cobro**; `/admin/plans`.

**15. Idioma, tema y móvil** (todos)
- Cambiar a **inglés** y a **oscuro** desde la barra superior: todo traducido. A **375 px**: Hoy, `/app/housekeeping/mine`,
  `/g/<token>` y `/g/<token>/checkin` sin scroll horizontal (verificado con `make routes`, `WIDTH=375`, en las 69 rutas).

### Extras por módulo (si hay tiempo)

| Módulo | Ruta · usuario | Qué mirar |
|---|---|---|
| Reservas (C1) | `/app/reservations` · recepción | Vistas rápidas (Llegadas hoy, Sin asignar, Tentativas…), búsqueda, **Exportar CSV**; detalle con Cancelar (vista previa de penalidad), No-show, recotización al cambiar fechas |
| Hoy / tablero de llaves (C1) | `/app` · dueño | Clic en llave libre → asistente con esa habitación; ⌘K "Nueva reserva", "Walk-in", "Buscar reserva por código" |
| Limpieza (C2) | `/app/housekeeping` · dueño | Filtros, Auto-asignar, "Generar tareas" (idempotente), cambio rápido Sucia/Limpia; Andino Medellín: **Aprobar inspección** |
| Mantenimiento (C2) | `/app/maintenance` · `mantenimiento@casaaurora.co` | Aterriza aquí; tickets con foto privada; resolver el de la 206 libera el bloqueo y la deja sucia |
| Portal staff (C5) | `/app/settings/guest-portal` · dueño | Apagar "Pedir foto del documento" quita el paso Documentos |
| Reportes (C10) | `/app/reports` · dueño | Hub "Este mes de un vistazo" (ocupación 56,5 %, ADR $460.664, RevPAR $260.487); Rendimiento con comparación y exportar CSV/XLSX/PDF; Impuestos; recepción solo ve Operación |
| Facturación (C11) | `/app/settings/billing` · dueño | Plan Pro activo, próximo cobro 15-oct-2026, VISA •••• 4242 simulada, uso 24/60; cambiar a anual y volver; contabilidad solo lectura |
| Centro de control (C12) | `/app/settings/integrations` · dueño | "7 de 9 en simulado"; **Probar conexión**; Real en Pagos pide llaves y nunca devuelve secretos → volver a Simulado. Campana y `/app/alerts` (resolver en bloque) |
| Permisos | varios | Recepción: sin Integraciones/Automatizaciones/Registro ni Motor de reservas; contabilidad: aterriza en Calendario (solo lectura), ve Reportes y Legal; limpieza: solo limpieza |

---

## API implementada

Ninguna nueva. Herramientas: `make check-automations`, `make sweep`, `make routes`; `check_integrity` con la sección
de la Fase C; `make smoke` ampliado.

## Contratos implementados / consumidos

Sin cambios de firmas. Cambio de comportamiento en `bookings.services.assignment.rank` (preferencia por unidades sin
huésped en casa para llegadas de hoy).

## Señales emitidas / escuchadas

Ninguna nueva.

## Automatizaciones registradas

Ninguna nueva. `revenue.run_rules` suma el parámetro `ai_summary_once_a_day` (por defecto `true`).

## Proveedores de integración registrados

Ninguno nuevo.

## Extensiones de frontend exportadas

Ninguna nueva. Compartidos tocados: `KpiTile`, `lib/auth.tsx` (`homeFor`), `app/extensions.ts` (JSDoc de
`ReservationAction`), `src/test/shell.ts` (nuevo) y los 2 tests del shell.

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

Ninguno pendiente de la Fase C (los opcionales y los de D1 están en "Pendientes").

## Cómo repetir

```bash
cd /home/breyner/Documents/new_project
docker compose down -v && docker compose up -d db redis mailpit
docker compose run --rm backend python manage.py migrate --noinput
docker compose run --rm backend sh -c "python manage.py makemigrations --check --dry-run && python manage.py check"
docker compose run --rm backend python manage.py seed_demo --reset      # ~9 min, worker/beat apagados
docker compose up -d                                                    # backend, frontend, worker, beat
make check && make check-data && make check-automations
make smoke && make sweep && make routes && WIDTH=375 make routes
docker compose exec -T backend sh -c "ruff check . && ruff format --check ."
docker compose exec -T frontend sh -c "npm run typecheck && npm run lint && npx tsc -b && npx vite build --outDir /tmp/dist-check --emptyOutDir"
```

Archivos tocados en C-INT: `backend/config/settings.py`, `.env.example`, `Makefile`, `README.md`,
`backend/apps/core/seed.py`, `backend/apps/core/management/commands/check_integrity.py`,
`backend/apps/bookings/services/assignment.py`, `backend/apps/ai/anomalies.py`, `backend/apps/revenue/automations.py`,
`backend/apps/rates/seed.py`,
`backend/scripts/smoke_proxy.py`, `backend/scripts/endpoints_sweep.py` (nuevo), `backend/scripts/automations_check.py`
(nuevo), tests formateados de `apps/compliance`, `apps/distribution` y `apps/guestportal`,
`frontend/src/components/KpiTile.tsx`, `frontend/src/lib/auth.tsx`, `frontend/src/app/extensions.ts`,
`frontend/src/app/__tests__/shell.test.tsx`, `frontend/src/app/__tests__/router.test.tsx`, `frontend/src/test/shell.ts`
(nuevo), `frontend/src/features/frontdesk/pages/ReservationDetailPage.tsx`,
`frontend/src/features/saas/pages/admin/AdminHomePage.tsx`, `frontend/src/features/guestportal/reservation-actions.tsx`,
`frontend/src/features/control/locales/{es,en}.json`, `frontend/scripts/route-smoke.mjs` (nuevo) y esta nota.
