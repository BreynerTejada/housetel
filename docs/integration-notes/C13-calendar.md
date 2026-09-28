# C13 — Calendario — integration notes

Estado: **completo en modo MVP** (sin tests nuevos, por decisión del usuario). Tarea solo de frontend
(`frontend/src/features/calendar/**`); no hay backend, migraciones, seed, señales ni automatizaciones propias.
Reanudada desde un intento previo interrumpido: se conservó y revisó lo que había (grilla virtualizada, barras,
DnD de mover/estirar con diálogos de confirmación, panel lateral, barra de herramientas) y se completó lo que
faltaba: **creación rápida arrastrando sobre días vacíos** (y con un toque en el celular), **diálogo "Mover…"**
(el camino en el celular y sin arrastrar), validación de **cupo por categoría** antes de mover o crear, el botón
"Nueva reserva", arreglos de lint y de rendimiento. Todo se probó de punta a punta contra el demo real (ver
"Verificación").

Última reanudación (tercera pasada, 27–28 sep): se revisó todo el código heredado (nada a medio escribir:
`tsc`/`eslint` limpios), se re-verificó la API y se volvió a recorrer la UI entera en un Chrome headless propio.
Cambios de esta pasada: los toasts del calendario tienen su propia posición (`lib/toast.ts`: abajo al centro;
arriba al centro en el celular, donde el panel es una hoja inferior), y los diálogos **"Mover…"** y **"Nueva
reserva"** tienen encabezado y botones fijos con el cuerpo desplazable (antes, en el celular o con un tablero de
40 habitaciones / 34 camas, el botón principal quedaba fuera de la pantalla); en la creación rápida, "Crear
reserva" sin huésped devuelve el foco (y el scroll) al campo, y un error del servidor se desplaza a la vista.

---

## Qué hay en `/app/calendar`

- **Barra superior**: semana anterior / siguiente, selector de fecha de inicio, "Hoy" (vuelve al día anterior a la
  fecha de negocio), 7 / 14 / 30 días (se recuerda por navegador), filtro de categorías y de estados, búsqueda por
  huésped o código (sin tildes; Enter salta a la siguiente coincidencia, despliega el grupo si estaba plegado).
  Botón **"Nueva reserva"** → asistente de C1 (`/app/reservations/new`), solo con `bookings.manage`.
- **Grilla** (una sola caja con scroll, cabecera de días y columna de habitaciones fijas): por categoría una fila
  resumen (**disponibilidad** de `bookings/calendar` + **precio** del primer plan base de `rates/grid`, tachado si
  hay stop-sell), la fila **"Sin asignar"** (en carriles; se pliega sola en conteos por noche si necesitaría más de
  4 carriles, y el usuario puede desplegarla), las habitaciones y, en dorms, el dormitorio (con camas libres por
  noche `3/6`) seguido de sus **camas**. Fines de semana (vie y sáb) y **festivos** (`rates/holidays`) sombreados;
  línea de **hoy** a mitad de columna (donde terminan las salidas y empiezan las llegadas). Categorías plegables
  (se recuerda por navegador).
- **Barras**: de mitad del día de llegada a mitad del de salida (checkout exclusivo), color por estado (tokens
  `--status-*`; tentativa con borde punteado), nombre, noches, íconos VIP ★, saldo pendiente $, upgrade ↗ y canal
  online 🌐 (OTA / marketplace / motor). Bloqueos rayados con el motivo (en dorms, el bloqueo del cuarto se repite
  en sus camas).
- **Interacciones** (solo con `bookings.manage`; con solo `bookings.view` todo es de lectura):
  - Arrastrar una barra a otra fila → `assign` (misma categoría: inmediato, con **Deshacer** en el toast).
  - A una habitación de **otra categoría** → diálogo: "Upgrade sin cambiar el precio" (`assign` con `force`) o
    "Cambiar a X y recotizar" (`modify` con `room_type_id` + `assign`), con el nuevo total del servidor.
  - Arrastrar en horizontal → `modify` de fechas; **estirar el borde derecho** → extender/acortar la salida. Ambos
    piden confirmación con el total nuevo (`modify-preview`) y avisan si la habitación se pierde.
  - **Arrastrar sobre días vacíos** de una fila (habitación, cama, dormitorio o "Sin asignar") → **creación rápida**
    (con el mouse también un clic = 1 noche; en el celular un toque = 1 noche, y deslizar hace scroll).
  - Clic (o Enter) en una barra → **panel lateral** (hoja inferior en el celular): resumen, total y saldo,
    check-in / check-out (con los casos `room_not_ready` y `balance_due`), **Mover…**, Quitar habitación, Abrir
    reserva.
  - Teclado: foco en una barra, **M** la levanta, flechas mueven (↑/↓ filas, ←/→ días), **Shift+M** estira la
    salida, Enter suelta, Escape cancela; región `aria-live` que narra el destino.
  - Actualización **optimista** con rollback y toast ante 409/400 (si falló un paso intermedio, avisa que el cambio
    quedó a medias y refresca).
- **Validación local antes de llamar al servidor** (`lib/dnd.ts`, el servidor valida de nuevo): huésped en casa no
  cambia la llegada ni sale antes de hoy ni queda sin habitación; llegada no antes de la fecha de negocio; dorms y
  privadas no se mezclan; habitación/cama libre y sin bloqueo; **cupo de la categoría** en las noches nuevas
  (nuevo: `no_units`, porque las reservas sin asignar también ocupan cupo y el servidor rechazaría con 409).
  El fantasma del arrastre se pone rojo con el motivo ("Ocupada por … (HT-…)", "Bloqueada…", "No queda cupo de
  Superior la noche del sáb 3 oct").
- **Creación rápida** (`components/CreateDialog.tsx`): lugar y noches dibujados; huésped con el `GuestPicker` de
  B3 (buscar o crear en línea; manda `booker_id` o `booker`); fechas; adultos/niños (una cama = 1 huésped; un
  dormitorio o la fila "Sin asignar" de un dorm = una cama por huésped); tarifas vendibles de esa categoría
  (`GET offers/?channel=direct`, por defecto la más barata **reembolsable**, marca "No reembolsable" y depósito);
  notas. Crea con `POST reservations/` (`source=front_desk`, `status=confirmed`, `room_id`/`bed_id` del lugar);
  toast "Reserva HT-… creada" con "Ver". "Abrir en el asistente" lleva los mismos datos a C1.
- **Mover…** (`components/MoveDialog.tsx`): fechas (huésped en casa: solo la salida) y un **tablero de llaves**
  (motivo del login) con las habitaciones de la categoría reservada y, como "otra categoría", las del mismo tipo
  (dorms: cama por cama). Cada llave dice su estado (libre / lista / sucia / ocupada / bloqueada / sin cupo) leído
  del calendario **de exactamente esas noches**; las no disponibles no se pueden elegir. La elección sigue el mismo
  camino que un arrastre (inmediato, o los diálogos de fechas / categoría).
- Ambos diálogos (creación rápida y "Mover…") usan `SCROLL_DIALOG` (`lib/constants.ts`): encabezado y botones
  fijos, cuerpo con scroll propio, para que el botón principal siempre esté a la vista (celular, hoteles grandes,
  hostales con muchas camas). En el celular el enlace "Abrir en el asistente" va al final del formulario.
- Toasts del calendario (`lib/toast.ts`, `calendarToast`): abajo al centro en escritorio y arriba al centro en el
  celular, para no tapar los botones del panel lateral / hoja inferior ("Mover…", "Abrir reserva").
- Responsive desde 375 px (columna de habitaciones de 104 px, scroll horizontal, días con ancho mínimo), claro y
  oscuro, ES/EN completos.

## API implementada

Ninguna (frontend). **Consumida** (todas con sesión + `X-Property-Id`):

| Llamada | Para qué | Permiso |
|---|---|---|
| `GET /api/v1/bookings/calendar/?start&end` | grilla (se pide desde el día anterior al primero visible, para ver las salidas de ese día); también la ventana exacta de una estadía en "Mover…" (máx. 93 días) | bookings.view |
| `GET /api/v1/rates/grid/?start&end&lang` | precio por noche del primer plan base (misma query key que la grilla de tarifas: comparten caché) | rates.view (si falta, no se muestran precios ni festivos) |
| `GET /api/v1/rates/holidays/?year&lang` | festivos de cada año del rango | rates.view |
| `GET /api/v1/bookings/reservations/{id}/` | panel lateral (total, saldo, ETA, notas) | bookings.view |
| `POST /api/v1/bookings/stays/{id}/assign/` `{room_id, bed_id, force?}` | mover de habitación / upgrade / deshacer | bookings.manage |
| `POST /api/v1/bookings/stays/{id}/unassign/` | "Sin asignar" / deshacer | bookings.manage |
| `POST /api/v1/bookings/stays/{id}/modify/` `{checkin?, checkout?, room_type_id?, reprice}` | fechas (`reprice: false`: las noches que quedan conservan su precio) y cambio de categoría (`reprice: true`) | bookings.manage |
| `POST /api/v1/bookings/stays/{id}/modify-preview/` | total nuevo y si se pierde la habitación, antes de confirmar | bookings.manage |
| `POST /api/v1/bookings/stays/{id}/check-in/` · `check-out/` `{force}` | acciones del panel | bookings.checkin (+ `checkout_with_balance` para salir con saldo) |
| `GET /api/v1/bookings/offers/?checkin&checkout&adults&children&channel=direct` | tarifas de la creación rápida | bookings.view |
| `POST /api/v1/bookings/reservations/` | crear la reserva rápida | bookings.manage |

Cuerpo que manda la creación rápida (probado contra el demo):

```json
{"booker_id": "<uuid>",
 "stays": [{"room_type_id": "<uuid>", "rate_plan_id": "<uuid FLEX>", "checkin": "2026-10-03", "checkout": "2026-10-05",
            "adults": 1, "children": 0, "room_id": "<uuid D1>", "bed_id": "<uuid cama C1>"}],
 "source": "front_desk", "status": "confirmed", "notes": "…"}
```

(o `"booker": {GuestInput}` para un huésped nuevo del `GuestPicker`). Respuesta 201 `ReservationDetail` → toast con
`code` y enlace a `/app/reservations/{id}`. Errores mostrados en el diálogo con el `detail` del servidor (p. ej.
409 `no_availability` "La habitación ya está ocupada en esas fechas", 400 `restriction_violation`).

No hace falta ningún endpoint nuevo.

## Contratos implementados / consumidos

- Forma exacta de `GET calendar/` de B2b (tipos en `api.ts`: `CalendarData`, `CalStay`, `CalBlock`, …) y de
  `GET grid/` de B2a (`GridResponse`, importado de `features/rates/api`).
- `GuestPicker`, `isExistingGuest`, `GuestInput` de `features/guests` (B3); `RoomKeyTag` de `features/inventory` (B1).
- Deshacer de un movimiento: se hace desde el toast re-asignando la habitación anterior (con `force` si era un
  upgrade) o quitándola; no depende del endpoint genérico de auditoría de C12.

Utilidades puras (para los tests de la fase posterior): `lib/layout.ts` (columnas de una estadía con recorte al
rango y checkout exclusivo, carriles, filas, alturas, plegado por defecto), `lib/dnd.ts` (`planChange` = traducir un
destino a pasos de API o a un motivo de rechazo; `checkCreate`; `previewDrop`, `resolveMove`, `keyboardDelta`,
`undoSteps`, `unitsShortfall`), `lib/dates.ts`, `lib/labels.ts`, `lib/constants.ts`.

## Señales emitidas / escuchadas

No aplica (frontend). Tras cada acción se invalida `['bookings']` (grilla, ventana de "Mover…" y detalle).

## Automatizaciones registradas

Ninguna.

## Proveedores de integración registrados

Ninguno.

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

- `routes.tsx`: `app: [{ path: 'calendar', lazy }]` (página `pages/CalendarPage.tsx`).
- `nav.ts`: el ítem de A2 sin cambios (`operations`, permiso `bookings.view`, orden 20).
- No exporta widgets, tabs, acciones, topbar ni comandos (el ⌘K ya lista la página por su nav).

## Dependencias nuevas (pip/npm) y por qué

Ninguna (usa `@dnd-kit/core`, `@tanstack/react-virtual`, `radix-ui`, ya instalados).

## Cambios requeridos en archivos compartidos u otras apps

1. **C-INT — tests del shell/router de A2** (`src/app/__tests__/shell.test.tsx`, `router.test.tsx`): al renderizar
   `/app/calendar` ahora se piden `GET /api/v1/bookings/calendar/`, `/api/v1/rates/grid/` y
   `/api/v1/rates/holidays/`; agregar handlers vacíos de MSW (`{room_types: [], stays: [], blocks: [],
   availability: {}}`, `{rate_plan: null, currency: 'COP', start, end, dates: [], holidays: [], room_types: []}`,
   `[]`) para que no impriman errores.
2. ~~Toaster abajo a la derecha tapando el pie del panel~~ → **resuelto dentro del calendario** (`lib/toast.ts`
   pone sus toasts abajo al centro / arriba al centro en el celular). No hace falta tocar `components/Toaster.tsx`;
   si A2 quisiera la misma regla para toda la app, podría copiarla.
3. **Nada que hacer en C1**: su asistente ya lee `checkin`, `checkout`, `adults`, `room_type_id` y `room_id`
   (`frontdesk/lib/wizard.ts` → `initialWizardState`), que es lo que manda "Abrir en el asistente". Opcional: si C1
   quisiera preseleccionar camas de dorm, podría aceptar también `bed_id` (hoy el calendario no lo manda).

## Limitaciones conocidas / pendientes

- **Sin tests nuevos** (modo MVP). Los archivos de `__tests__/` son del intento anterior y **no se corrieron**;
  algunos pueden necesitar ajustes (p. ej. los textos para lectores de pantalla de las celdas ahora van en el
  `aria-label` de la celda, no en spans ocultos; se quitaron `useRoomOptions`/`RoomOption`, que ya no se usan).
  Quedan para la fase de tests.
- La validación local solo ve las noches cargadas (rango visible + el día anterior, o la ventana de "Mover…"); fuera
  de ellas decide el servidor (409 → rollback + toast).
- "Mover…" no ofrece "cualquier cama libre de un dormitorio" (se elige la cama); arrastrar a la fila del
  dormitorio sí lo hace.
- La creación rápida es de una sola estadía, sin extras ni pago (para eso, "Abrir en el asistente"). No pide el
  consentimiento Habeas Data del huésped nuevo (lo hace el asistente de C1 / el CRM).
- La línea de hoy se dibuja detrás de las filas: sobre las barras con fondo translúcido (tema oscuro) se ve tenue.
- En desarrollo (React dev) el scroll de 30 días en el hostel queda en ~12–25 ms por paso tras los arreglos
  (antes 40–350 ms: los sensores de dnd-kit se recreaban en cada frame y re-renderizaban todas las barras).
- Datos que dejé en la BD de desarrollo durante las pruebas (C-INT la re-siembra): reservas **HT-RQM8BU** y
  **HT-7KCCHG** creadas y canceladas (la primera tenía plan no reembolsable: su penalidad se anuló por la API de
  finanzas, saldo 0); movimientos de prueba deshechos (quedan sus eventos de auditoría). En la última pasada solo
  hubo movimientos deshechos (HT-BDBZHV 107→103→107, HT-279QGQ 101→102→101 dos veces, HT-D62XA4 102→103→102;
  comprobado por la API que cada una quedó en su habitación original) y las creaciones se probaron dentro de una
  transacción revertida (no quedó ninguna reserva nueva).
- **Nota para la validación en Chrome** (no es del calendario): durante esta pasada el servidor de Vite
  compartido (`:5173`) estuvo un rato sin cargar la app entera porque `features/saas/routes.tsx` (C11, en curso)
  importaba páginas que aún no existían (error de `vite:import-analysis` en pantalla). Mientras tanto el recorrido
  se hizo en un Vite **privado** (puerto 5199, mismo código, con un plugin que cambiaba por un componente vacío solo
  los imports faltantes de otras features; sin tocar archivos compartidos ni el servidor de 5173). Al final C11 ya
  había creado esas páginas y el recorrido de escritorio y de celular se repitió **contra 5173**, sin errores. Si la
  pantalla de error de Vite vuelve a aparecer, es de la feature que nombre, no del calendario.

## Verificación (sin tests)

- `npx tsc -p tsconfig.app.json --noEmit | grep src/features/calendar` → sin errores; `npx eslint
  src/features/calendar` → limpio (se arreglaron 3 errores `react-refresh/only-export-components` del intento
  anterior moviendo constantes a `lib/constants.ts`). `manage.py check` → sin problemas (no hay backend propio).
- API contra el demo por el proxy de Vite (cookie jar + CSRF, `recepcion@casaaurora.co` y `owner@grupoandino.co`):
  `calendar` (Aurora 87 estadías / 33 sin asignar / 1 bloqueo en 16 días; hostel 212 estadías con camas), `grid`,
  `holidays`, `reservations/{id}`, `assign` (200 a una libre, **409 `no_availability`** a una ocupada, 200 de vuelta),
  `modify-preview` (+1 noche: `room_kept: true`, diferencia; otra categoría: `room_kept: false`), `offers`,
  `POST reservations/` (201 y la barra aparece en `calendar`; 409 sobre una habitación ocupada), `cancel`.
- Recorrido en un **Chrome headless propio** (perfil y puerto propios, no el navegador compartido): carga sin errores
  de consola (Aurora y hostel, claro y oscuro, 1440 px y 375 px); dibujar 2 noches → fantasma "2 noches · Nueva
  reserva en la 103" → diálogo con tarifas (por defecto "Tarifa flexible"); crear de verdad una reserva en la cama
  C1 de D1 eligiendo un huésped con el `GuestPicker` → toast "Reserva HT-7KCCHG creada" y barra en la cama;
  arrastrar una barra una fila abajo → "… ahora está en Hab. 102" + Deshacer → vuelve a la 101; teclado M ↓ Enter →
  mismo resultado; estirar el borde → "¿Cambiar las fechas?" con total del servidor; "Mover…" → tablero de llaves →
  102 → movida + Deshacer; elegir una Superior → diálogo de categoría con "Nuevo total"; celular: toque en barra →
  hoja inferior, "Mover…" → tablero, toque en día vacío → creación rápida, deslizar → scroll sin abrir nada.
- **Última pasada (27–28 sep)**:
  - `npx tsc -p tsconfig.app.json --noEmit | grep src/features/calendar` → nada; `npx eslint src/features/calendar`
    → limpio; claves i18n: ES y EN con las mismas 213 claves y todas las usadas en el código presentes (también las
    dinámicas: estados, motivos `invalid.*`, `block.kinds.*`, `create.meals.*`, `sources.*`); cada módulo de la
    feature compila en Vite (200). `docker compose exec -T backend python manage.py check` → sin problemas. No hay
    app backend propia: no aplica `makemigrations --check`, seed ni automatizaciones.
  - API por el proxy de Vite (`localhost:5173`, cookie jar + CSRF): `calendar` de Aurora (3 categorías, 24 hab.,
    87 estadías / 33 sin asignar, 1 bloqueo; claves de estadía = contrato de B2b), `rates/grid` (plan FLEX),
    `rates/holidays` (19 en 2026), `reservations/{id}`, `assign` a una libre y de vuelta (200/200), `assign` a una
    ocupada → **409 `no_availability`**, `modify-preview` (+1 noche: `room_kept: true`; otra categoría:
    `room_kept: false` y nuevo total), `offers?channel=direct`; `contabilidad@` lee `calendar` y recibe **403** en
    `assign`; hostel: 5 categorías (3 dorm, 34 camas), 371 estadías (146 con cama), `grid` FLEX.
  - `POST reservations/` con exactamente los cuerpos del diálogo, dentro de una transacción revertida
    (`manage.py shell`, `APIClient`): huésped existente en la 101 → 201 `confirmed`; misma habitación otra vez →
    409 `no_availability`; huésped nuevo (`booker`) sin habitación → 201; hostel: una cama (C1 de D4) → 201; el
    dormitorio D4 para 2 huéspedes → 201 con 2 estadías en C2 y C3; fila "Sin asignar" del dorm para 2 → 201.
  - Las secuencias de pasos que arma `planChange`, contra la API real y también revertidas: mover de habitación
    (`assign`) → 200; fechas + otra habitación (`modify reprice:false` → `assign`) → 200/200; cambio de categoría
    (`modify room_type_id reprice:true` → `assign` a una Superior) → 200/200 con el total recotizado; upgrade
    (`assign force:true`) → 200 conservando categoría y precio (sin `force` → 400 `category_mismatch`, por eso el
    calendario lo manda); `unassign` → 200; en casa: `unassign` y cambiar la llegada → 409 `invalid_state` (el
    calendario ya los rechaza antes de llamar: `in_house_unassign`, `in_house_arrival`).
  - Recorrido en un Chrome headless propio (perfil y puerto propios; primero contra el Vite privado y al final
    contra el compartido `localhost:5173`, ver la nota de arriba), sin errores de consola: carga
    de Aurora y del hostel (1440 px y 375 px, oscuro y claro); dibujar 2 y 3 noches → "Nueva reserva" con tarifas
    (por defecto "Tarifa flexible"); arrastrar una reserva una fila abajo → "… ahora está en Hab. 102" con Deshacer
    (toast abajo al centro) → "Cambio deshecho"; teclado M ↓ Enter → igual; panel → "Mover…" → tablero (Aurora y
    hostel con 34 camas: botón "Mover" visible sin scroll); celular: toque en barra → hoja inferior → "Mover…" →
    elegir la 103 → "Mover" (botones fijos a la vista) → toast arriba al centro → Deshacer; toque en día vacío →
    "Nueva reserva" con "Crear reserva" visible; "Crear reserva" sin huésped → foco y scroll al campo con el error.

---

## Cómo probarlo en la UI

Usuarios demo (clave `housetel123`): `owner@casaaurora.co` (Hotel Casa Aurora, 24 hab.), `recepcion@casaaurora.co`
(rol recepción: puede todo lo del calendario), `contabilidad@casaaurora.co` (solo lectura), `owner@grupoandino.co`
(Andino Medellín 40 hab. y **Andino Hostel Bogotá** con dormitorios por cama; cambiar de propiedad con el selector de
la barra superior). La fecha de negocio del demo es la que muestra la barra superior (hoy 27 sep 2026). Los códigos
de reserva de abajo son del demo actual y cambian si se re-siembra: usar cualquier reserva equivalente.

1. **Cargar** `http://localhost:5173/app/calendar` como `owner@casaaurora.co`.
   Esperado: título "Calendario", 14 días desde el día anterior a la fecha de negocio (columna "DOM 27" resaltada y
   línea terracota), categorías Estándar / Superior / Suite con fila de disponibilidad y precio ("368 mil"),
   fila "SIN ASIGNAR" (plegada con conteos por noche si hay muchas), habitaciones 101… con estado de limpieza,
   barras de colores, el bloqueo rayado de la 110 ("Mantenimiento: …"), leyenda abajo. Consola sin errores.
2. **Barra de herramientas**: 7 / 14 / 30 días; flechas de semana y "Hoy"; "Categorías: Todas" → dejar solo
   Superior; "Estados" → quitar "Finalizada"; buscar un apellido (p. ej. "Montoya") → "N en estas fechas" y Enter
   lleva el foco a la barra (despliega el grupo si estaba plegado).
3. **Panel**: clic en una barra → panel a la derecha con código, estado, llegada/salida/noches, habitación,
   categoría, huéspedes, canal, total y saldo, y acciones. En una llegada de hoy con habitación limpia aparece
   "Hacer check-in"; en un huésped en casa, "Hacer check-out" (si debe saldo muestra el aviso con "Abrir la reserva
   para cobrar").
4. **Mover arrastrando**: arrastrar una reserva confirmada futura (p. ej. HT-279QGQ, Hab. 101, 3–6 oct) una fila
   abajo a una habitación libre de su categoría. Esperado: mientras arrastra, fantasma punteado "Hab. 102 · 3–6 oct"
   (rojo con el motivo si está ocupada); al soltar, la barra se mueve al instante y toast "… ahora está en Hab. 102"
   con **Deshacer** (los toasts del calendario salen abajo al centro) → vuelve a la 101 ("Cambio deshecho"). Soltar
   sobre una ocupada → toast rojo "Ocupada por … (HT-…) en esas noches." y no cambia nada.
5. **Otra categoría**: arrastrar esa reserva a una habitación libre de Superior (o usar "Mover…" y elegir una
   Superior). Esperado: diálogo "La 20x es de otra categoría" con "Upgrade sin cambiar el precio" (marcado) y
   "Cambiar a Superior y recotizar — Nuevo total: $ … (+$ …)". Cancelar no cambia nada.
6. **Fechas**: arrastrar la barra en horizontal un día, o estirar su **borde derecho** (aparece al pasar el mouse).
   Esperado: "¿Cambiar las fechas?" con Ahora / Nuevas fechas, total de la estadía y diferencia calculados por el
   servidor; "Cambiar fechas" aplica, Cancelar no.
7. **Creación rápida**: arrastrar sobre 2 días vacíos de una habitación, desde hoy en adelante. Esperado: fantasma
   "2 noches · Nueva reserva en la 103" y, al soltar, diálogo "Nueva reserva" con el lugar ("Hab. 103 · Estándar"),
   fechas, adultos 2 / niños 0 y tarifas vendibles con total y precio por noche (preseleccionada "Tarifa flexible";
   la no reembolsable dice "No reembolsable"). Buscar un huésped en "Huésped" (p. ej. "Laura") y elegirlo, o "Crear
   huésped nuevo" → "Crear reserva". Esperado: toast "Reserva HT-… creada" con "Ver" y la barra nueva en la grilla.
   Sin huésped → "Elige un huésped o crea uno nuevo." y el foco vuelve al campo. Encabezado y botones del diálogo
   quedan fijos y el formulario hace scroll si no cabe. Dibujar sobre días pasados o sobre una reserva → toast rojo
   con el motivo. "Abrir en el asistente" abre `/app/reservations/new?checkin=…&checkout=…&adults=…&room_type_id=…&room_id=…`.
8. **Mover…** (camino del celular): clic en una barra → "Mover…". Esperado: diálogo "Mover la reserva" con fechas y
   el tablero de llaves: categoría reservada ("RESERVADA") y las demás ("OTRA CATEGORÍA"), cada llave con su estado
   (actual / libre / lista / sucia / ocupada / bloqueada / sin cupo); las ocupadas están rayadas y no se pueden
   elegir. Elegir una libre → "Mover" → igual que el paso 4 (o los diálogos de los pasos 5 y 6). En un huésped en
   casa solo se puede cambiar la salida ("El huésped ya está en casa: solo cambia la salida."). Con muchos cuartos
   (Andino Medellín, 40) o camas (hostel, 34) el tablero hace scroll y "Cancelar" / "Mover" siguen a la vista.
9. **Teclado**: Tab hasta una barra, **M**, ↓ (o ←/→), Enter. Esperado: el fantasma sigue las flechas y al soltar se
   mueve con el toast de Deshacer; Escape cancela.
10. **Hostel (dorms)**: como `owner@grupoandino.co`, propiedad "Andino Hostel Bogotá". Esperado: dormitorios D1, D2…
    con camas libres por noche ("0/6", "4/6") y sus camas C1…C6 como filas; arrastrar sobre días vacíos de una
    cama → creación rápida con adultos fijos en 1 ("Una cama es para un huésped.") y precios por cama; sobre la
    fila del dormitorio → una cama por huésped.
11. **Celular (375 px)**: la grilla hace scroll horizontal con la columna de habitaciones fija; tocar una barra abre
    la hoja inferior con "Mover…" (el tablero ocupa la pantalla y los botones "Cancelar" / "Mover" quedan fijos
    abajo); tras mover, el toast sale **arriba** al centro con Deshacer; tocar un día vacío (hoy o después) abre la
    creación rápida con "Crear reserva" siempre visible; deslizar hace scroll sin abrir nada.
12. **Solo lectura**: como `contabilidad@casaaurora.co` no hay botón "Nueva reserva", las barras no se arrastran,
    dibujar no hace nada y el panel no tiene acciones (solo "Abrir reserva").
13. **Idioma y tema**: cambiar a inglés y a oscuro desde la barra superior: todo el calendario (diálogos, toasts,
    leyenda, motivos) cambia de idioma; los colores de estado siguen legibles.
