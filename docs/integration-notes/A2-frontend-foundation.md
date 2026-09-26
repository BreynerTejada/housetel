# A2 — Frontend foundation — integration notes

Estado: Steps 1–7 del plan completos. `npm run typecheck`, `npm run lint` (0 errores, 0 warnings),
`npm run test` (23 archivos, 176 tests) y `npm run build` (sin warnings) en verde en el host (Node 26)
y los tests también dentro del contenedor (`docker compose run --rm --no-deps frontend npm run test`,
Node 24). Login real verificado contra el backend de A1 a través del proxy de Vite en Docker.

Esta nota es la guía para los agentes de las fases B y C: **cómo registrar tu feature, cómo llamar a
la API, qué componentes usar y cómo probar**.

---

## Cómo correr

```bash
# Docker (lo normal): http://localhost:5173, proxy /api y /media → http://backend:8000
docker compose up -d frontend            # también levanta backend (depends_on)
docker compose run --rm --no-deps frontend npm run test

# Host (Node ≥ 24), backend publicado en 8010:
cd frontend && npm install && npm run dev          # VITE_PROXY_TARGET por defecto http://localhost:8010
npx vitest run src/features/<feature>              # tests de tu feature
npm run typecheck && npm run lint && npm run test && npm run build
```

## Estructura

```
frontend/src/
  main.tsx                     monta AppProviders + RouterProvider
  app/
    extensions.ts              §E: tipos + auto-descubrimiento + hooks (useNav, useWidgets, ...)
    routes.tsx / router.ts     árbol de rutas (buildRoutes) y router del navegador
    providers.tsx              QueryClient, ThemeProvider, Tooltip.Provider, Toaster
    layouts/                   AppLayout, SettingsLayout, AdminLayout, PublicLayout, BareLayout
    shell/                     sidebar, selector de propiedad, fecha de negocio, menús, PublicChatSlot
    pages/                     LoginPage (+ login/RoomRack), SettingsIndex, NotFound, RouteError
  components/ui/               primitivas (shadcn sobre radix-ui + CVA + tokens)
  components/                  componentes compartidos (DataTable, FormField, Money, ...)
  design/                      tokens.css (tokens + @theme de Tailwind 4), base.css
  lib/                         api, auth, permissions, session, i18n, format, date-ranges, errors,
                               query, theme, hooks, utils (cn)
  features/<feature>/          routes.tsx, nav.ts, locales/{es,en}.json (+ tus páginas)
  test/                        setup.ts, server.ts (MSW), render.tsx, fixtures.ts
```

---

## Extensiones (plan §E) — cómo se registra una feature

Nadie edita archivos centrales. `src/app/extensions.ts` descubre por nombre de archivo dentro de
`src/features/<feature>/` con `import.meta.glob(..., { eager: true })`:

| Archivo | Export | Lo consume |
|---|---|---|
| `routes.tsx` | `export const routes: FeatureRoutes` | router |
| `nav.ts` | `export const nav: NavItem[]` | sidebar, configuración, admin, paleta ⌘K |
| `locales/es.json`, `locales/en.json` | JSON (namespace = nombre de la carpeta) | i18n |
| `widgets.tsx` | `export const widgets: DashboardWidget[]` | panel Hoy (C1, `useWidgets()`) |
| `reservation-tabs.tsx` | `export const reservationTabs: ReservationTab[]` | detalle de reserva (C1) |
| `reservation-actions.tsx` | `export const reservationActions: ReservationAction[]` | detalle de reserva (C1) |
| `guest-tabs.tsx` | `export const guestTabs: GuestTab[]` | perfil de huésped (B3) |
| `topbar.tsx` | `export const topbarItems: TopbarItem[]` | barra superior (ya montado) |
| `commands.ts` | `export const commands: CommandItem[]` | paleta ⌘K (ya montada) |
| `public-widget.tsx` (solo `ai`) | `export default function PublicWidget({ propertySlug, portalToken })` | layouts públicos (`PublicChatSlot`, carga perezosa) |

Hooks (filtran por permiso de la membresía activa y ordenan por `order`): `useNav(section?)`,
`useWidgets()`, `useReservationTabs()`, `useReservationActions()`, `useGuestTabs()`,
`useTopbarItems()`, `useCommands()`. Sin hooks: `getNav()`, `getFeatureRoutes()`.
Utilidades puras: `filterNav`, `findActiveNav`, `splitSettingsRoutes`, `collectItems`, `visibleItems`.

Reglas importantes:

1. **En archivos de extensión (`nav.ts`, `routes.tsx`, `widgets.tsx`, `*-tabs.tsx`, `*-actions.tsx`,
   `topbar.tsx`, `commands.ts`) importa de `@/app/extensions` solo tipos** (`import type`). Se cargan
   de forma eager desde `extensions.ts`; un import en tiempo de ejecución crea un ciclo.
2. Rutas: en `app` los paths son relativos a `/app` (`'calendar'`, `'settings/rooms'`; la página Hoy es
   `{ index: true }`), en `admin` relativos a `/admin`, en `public`/`bare` absolutos. Toda ruta `app`
   con prefijo `settings/` se anida sola en `SettingsLayout`.
3. Páginas con carga perezosa (el bundle de marketplace no debe cargar tu código):
   ```tsx
   export const routes: FeatureRoutes = {
     app: [{ path: 'calendar', lazy: () => import('./pages/CalendarPage').then((m) => ({ Component: m.default })) }],
   }
   ```
4. Páginas públicas con marca del hotel (booking engine `/h/:slug`, portal `/g/:token`): agrega
   `handle: { chrome: 'none' }` y `PublicLayout` oculta el header/footer de Housetel (el `PublicChatSlot`
   sigue montado). Los stubs de `marketplace` y `guestportal` ya lo traen.
5. `NavItem` tiene un campo **opcional** adicional `descriptionKey` (una línea que se muestra en el
   índice `/app/settings`). `CommandContext` tiene un campo opcional adicional `query` (el texto escrito
   en la paleta; lo usa "Preguntar al copiloto…"). Ambos son compatibles con el contrato §E.
6. `CommandItem.group`: `'actions'` o `'navigation'` usan los títulos comunes; cualquier otro valor se
   traduce como clave i18n (p. ej. `'ai:commands.group'`).
7. Admin: los ítems con `platformAdmin: true` solo los ve `me.is_platform_admin`; no se muestran en el
   sidebar del hotel (el menú de cuenta tiene "Panel de plataforma").

### Reemplazar tu stub

Cada feature ya tiene `routes.tsx` con `UnderConstruction`, `nav.ts` con sus ítems **definitivos**
(ids, secciones, paths y permisos del plan; no los cambies sin anotarlo) y `locales/{es,en}.json`
con `nav.*` (y `pages.*` para rutas de detalle). Para construir tu feature: cambia el `element` de
cada ruta por `lazy: ...` hacia tus páginas, conserva los paths, y agrega tus claves en ambos idiomas.
El test `src/app/__tests__/extensions.test.ts` fija la tabla de nav del plan y
`router.test.tsx` verifica que **cada ítem de nav resuelve a una ruta real** (sin enlaces muertos).

---

## Cliente API (`src/lib/api.ts`)

```ts
import { api, publicApi, ApiError, isApiError } from '@/lib/api'

api.get<Page<Reservation>>('/bookings/reservations/', { params: { status: ['confirmed', 'tentative'], page: 2 } })
api.post<Reservation>('/bookings/reservations/', body)            // X-CSRFToken automático
api.patch<Room>(`/inventory/rooms/${id}/`, { name })
api.delete(`/rates/extras/${id}/`)                                 // 204 → undefined
api.post(`/inventory/room-types/${id}/photos/`, undefined, { formData })   // multipart
api.get<Blob>('/reports/performance/', { params: { format: 'csv' }, responseType: 'blob' })  // descargas con X-Property-Id
publicApi.get('/marketplace/search/', { params })                  // base /api/v1/public, sin X-Property-Id
```

- Base staff `/api/v1` con `X-Property-Id` tomado de `useSession.getState().propertyId`; base pública
  `/api/v1/public` sin ese header. `credentials: 'include'`.
- CSRF: en métodos no seguros lee el cookie `csrftoken`; si no existe hace `GET /accounts/auth/csrf/`
  una sola vez (aunque haya peticiones concurrentes) y envía `X-CSRFToken`.
- Query: los arrays repiten la clave; `undefined`, `null` y `''` se omiten.
- Errores → `ApiError(status, code, message, fields?, data?)` con el cuerpo `{detail, code, fields}`
  del backend (`data` = cuerpo completo, incluye extras como `permission` o `amount`). Red caída →
  `status 0`, `code 'network_error'`; página no JSON → `code 'http_error'`.
- 401 (o 403 con `code` `not_authenticated`/`authentication_failed`) en rutas `/app` o `/admin` →
  `window.location.assign('/login?next=…')`. Desactívalo por petición con `{ authRedirect: false }`.
- Mensaje para el usuario: `errorMessage(error, t)` de `@/lib/errors` (usa el `detail` en español del
  backend; si no hay, textos claros para red, 402, 403, 404 o genérico).
- TanStack Query: `queryClient` con `staleTime 30 s`, sin reintentos en 4xx y uno en 5xx/red
  (`shouldRetry`). **Al cambiar de propiedad se cancelan y eliminan todas las queries excepto `['me']`**,
  así que las claves no necesitan incluir el `propertyId`.
- Toasts: `import { toast } from 'sonner'` (el `Toaster` ya está montado y tematizado).

## Sesión, auth y permisos (`src/lib/auth.tsx`, `src/lib/permissions.ts`)

- `useMe()` → `Me | null` (null = anónimo; nunca redirige). Tipos `Me`, `Membership`, `PropertySummary`
  con la forma exacta del spec §3 (verificada contra el backend real de A1) más `phone` (A3).
- `useActiveProperty()` → `{ property, membership, properties, setProperty, synced }`. `property` trae
  `id, name, slug, property_type, timezone, currency, business_date`. **Usa `property.business_date`
  como "hoy" operativo** (no `new Date()`). `AppLayout` solo renderiza la página cuando el store ya tiene
  el `X-Property-Id` correcto (`synced`), así la primera petición nunca sale sin header.
- `useActiveMembership()`, `useCan('bookings.manage')` (mismo algoritmo `fnmatch` que el backend:
  `*`, exacto, `app.*`, `?`, clases `[...]`), `usePermissionChecker()` para filtrar listas.
- `useLogin()`, `useLogout()` (limpia caché y propiedad; los guards mandan a `/login` limpio),
  `RequireAuth`, `RequirePlatformAdmin`, `homeFor(me)`, `safeNext(next)` (evita redirecciones abiertas).
- Sesión expirada → `/login?next=<ruta>`; logout explícito → `/login` sin `next`.

## i18n (`src/lib/i18n`)

- Namespace común `common` (por defecto) + un namespace por feature (`useTranslation('rates')` o
  `t('rates:nav.rates')`). Detección: localStorage `housetel.lang` → navegador; `fallbackLng: 'es'`.
- `setLanguage(lang, queryClient)` cambia el idioma y hace `PATCH /accounts/me/` si hay sesión; al
  cargar la app manda el idioma del perfil del usuario.
- **Test obligatorio de paridad**: `src/lib/__tests__/i18n.test.ts` falla si un namespace no tiene
  exactamente las mismas claves en ES y EN.
- Mensajes de validación zod como claves comunes: `validation.required`, `validation.email`,
  `validation.minLength`, `validation.number` (`FormField` las traduce; texto plano también funciona).
- Claves comunes útiles: `actions.*`, `states.*`, `errors.*`, `status.{reservation,room,payment,task}.*`,
  `table.*`, `date.*` (incluye `date.nights_one/_other`), `propertyTypes.*`, `languages.*`.

## Formato y fechas (`src/lib/format.ts`, `src/lib/date-ranges.ts`)

`formatMoney('320000.00')` → `$ 320.000` (COP sin decimales, `es-CO`); `formatNumber`, `formatPercent`
(puntos porcentuales), `parseDate('2026-10-12')` (día local, nunca medianoche UTC), `toISODate(date)`,
`formatDate(value, pattern?, lang)`, `formatDateRange(a, b, lang)`, `nightsBetween(checkin, checkout)`
(checkout exclusivo), `formatRelative`. `rangePreset(id, today)` para rangos de reportes (ambos extremos
inclusivos; semana lunes–domingo): `today, yesterday, tomorrow, thisWeek, next7, thisMonth, lastMonth, last30`.

---

## Sistema de diseño "cálido nórdico"

Tokens en `src/design/tokens.css` (claro/oscuro con `[data-theme]` + `prefers-color-scheme`), mapeados
en `@theme` de Tailwind 4. El tema se aplica antes del primer render (script en `index.html`) y el
`ThemeProvider` resuelve `system`.

- Superficies y texto: `bg-bg`, `bg-surface`, `bg-surface-2`, `bg-surface-3`, `border-border`,
  `border-border-strong`, `text-fg`, `text-muted`, `text-subtle`.
- Acento (uno solo, terracota): `bg-accent`, `hover:bg-accent-hover`, `bg-accent-soft`,
  `text-accent-ink`, `text-on-accent`. **`Button variant="primary"` solo para la acción principal de
  cada vista** (el variant por defecto es `secondary`).
- Estados: `success | warning | danger | info | stone`, cada uno con `bg-x`, `bg-x-soft` y `text-x-ink`.
  **Para texto sobre fondos suaves usa siempre `-ink`** (los colores sólidos del spec no pasan AA como
  texto; contrastes medidos en ambos temas). En modo oscuro el texto sobre el acento es casi negro.
- Dominio: `bg-room-{clean,dirty,inspected,ooo,occupied}` (+ `-soft`) y
  `bg-status-{tentative,confirmed,checked-in,checked-out,cancelled,no-show}`; las variables CSS
  `--status-*-soft` / `--status-*-ink` y `--room-*-soft` / `--room-*-ink` existen para barras del
  calendario. Significado: tentativa → arena, confirmada → pizarra, en casa → terracota, finalizada →
  salvia, cancelada → piedra, no show → arcilla.
- Tipografía: Manrope Variable (local). `.num` = cifras tabulares (tablas, folios, columnas);
  `.eyebrow` = etiqueta pequeña en mayúsculas; `text-2xs` (11 px). Staff 14 px (`.app-shell`),
  público 16 px (`.public-shell`). Radio 10 px (`rounded-lg`), sombras mínimas `shadow-xs..lg`.
- `.hatch` = rayado para bloqueos / fuera de servicio. Animaciones `animate-pop-in/out`,
  `animate-sheet-in-*`; `prefers-reduced-motion` las anula globalmente.
- Firma visual: el **tablero de habitaciones** (key rack de recepción) en el login y el motivo de
  llaves (logo = llavero con perforación, fecha de negocio con "perforación", colgador de puerta en
  `UnderConstruction`).

## Componentes

`src/components/ui/`: `button` (variants primary/secondary/subtle/ghost/danger/link, sizes
sm/md/lg/icon/icon-sm, `loading`, `asChild`), `input`, `textarea`, `label`, `select`, `combobox`
(búsqueda, `options: {value,label,description?}`), `checkbox`, `switch`, `radio-group`, `dialog`,
`sheet` (left/right/bottom), `dropdown-menu`, `popover`, `tooltip` (`<Tooltip content>`), `tabs`
(subrayadas), `badge` (tones), `card`, `table`, `skeleton`, `separator`, `avatar` (+ `initials()`),
`scroll-area`, `toggle-group`, `command` (cmdk), `calendar` (react-day-picker v9, locale según idioma).

`src/components/`:

| Componente | Uso |
|---|---|
| `PageHeader` | `title`, `description`, `actions`, `breadcrumbs=[{label,to?}]` |
| `EmptyState` / `ErrorState` / `LoadingState` | vacío con acción · error con `onRetry` (usa `errorMessage`) · `variant="spinner" \| "rows"` |
| `UnderConstruction` | placeholder de los stubs (`titleKey`) |
| `DataTable` | TanStack: orden (siempre asc primero), búsqueda cliente (`enableSearch`) o servidor (`search`/`onSearchChange`), paginación cliente (`pageSize`) o servidor (`server={{ rowCount, pagination, onPaginationChange, sorting?, onSortingChange? }}`), selección (`enableSelection`, `onSelectionChange`), `onRowClick`, densidad, `toolbar`, `empty`. `columnDef.meta.align = 'right'` para cifras |
| `FormField` | react-hook-form: `render={({ field, ...a11y }) => <Input {...field} {...a11y} />}` (label, descripción, error y aria enlazados) |
| `MoneyInput` / `MoneyText` | `value` string API (`"350000.00"`), `onChange("350000")`; muestra `$ 350.000` |
| `DatePicker` / `DateRangePicker` | valores `YYYY-MM-DD`; rango con dos clics, `showNights`, `minNights`, `presets`, `today` (pasa la fecha de negocio), `min`/`max` |
| `StatusBadge` | `kind: 'reservation' \| 'room' \| 'payment' \| 'task'`, `status` (texto i18n + color del sistema; desconocido → neutro) |
| `KpiTile` | contrato dataviz: `label`, `value`, `delta` + `deltaLabel` + `deltaPeriod`, `intent` (`higher-is-better` / `lower-is-better`), `trend=[{label,value}]` (sparkline con tabla accesible y teclado) |
| `ConfirmDialog` / `DangerConfirmDialog` | `onConfirm` async: spinner, cierra al resolver, muestra el `detail` si falla. Danger exige escribir `confirmText` exacto (monto o código). El backend igual exige `confirm: true` |
| `CommandPalette` | ya montada en `AppLayout` (⌘K / Ctrl+K) con nav + `commands.ts` |
| `Logo`, `Toaster`, `ErrorBoundary` | — |

Hooks (`src/lib/hooks.ts`): `useHotkey(key, handler, { mod })`, `useMediaQuery(query)`,
`useReducedMotion()`, `useLocalStorageState(key, initial)` (solo preferencias por usuario).

---

## Tests (Vitest + Testing Library + MSW)

- `src/test/setup.ts`: jest-dom, i18n forzado a español en cada test, MSW con
  `onUnhandledRequest: 'error'` (toda petición debe tener handler), polyfills de jsdom para Radix/cmdk,
  `asyncUtilTimeout` 8 s (Vitest `testTimeout` 15 s, para que un `findBy*` fallido muestre su error real).
- `src/test/render.tsx`: `renderWithProviders(ui, { route, path, routes, queryClient })` (providers
  reales + memory router; devuelve `router`, `queryClient`, `user`), `renderRoutes(buildRoutes(), { route })`
  para flujos completos, `preloadLazyRoutes()` para `beforeAll(preloadLazyRoutes, 60_000)` en tests de
  rutas (las shells son lazy).
- `src/test/fixtures.ts`: `makeMe(overrides)`, `mockMe(me | null)` (anónimo = 403 `not_authenticated`),
  `auroraMembership(permissions, roleCode)`, `andinoMembership(...)`, propiedades de ejemplo.
- Para métodos no seguros pon `document.cookie = 'csrftoken=t; path=/'` en `beforeEach` (o agrega un
  handler para `GET /api/v1/accounts/auth/csrf/`).
- Resetea el store en `beforeEach`: `useSession.setState({ propertyId: null, loggedOut: false })`.

---

## API implementada

Ninguna (solo frontend). Consumidos del backend de A1: `GET /api/v1/accounts/auth/csrf/`,
`POST /api/v1/accounts/auth/login/`, `POST /api/v1/accounts/auth/logout/`,
`GET/PATCH /api/v1/accounts/me/`, `GET /api/v1/public/core/health/`.

Verificado en vivo (Docker, proxy de Vite): csrf 200 + cookie; `/me` anónimo → **401**
`{"detail": "...", "code": "not_authenticated"}` (el cliente acepta también el 403 típico de DRF);
login de `owner@casaaurora.co` y `recepcion@casaaurora.co` → 200 con `Me` idéntico al tipo del
frontend; `PATCH /me` → 200; logout → `/me` vuelve a 401. El sidebar de recepción coincide con el rol
`front_desk` de §D.

## Contratos implementados / consumidos

§E completo (tipos y hooks), `Me` del spec §3, convenciones de API del spec §3.1.

## Señales emitidas / escuchadas · Automatizaciones · Proveedores de integración

No aplica (frontend).

## Extensiones de frontend exportadas

Los 18 stubs (`frontdesk, calendar, inventory, rates, guests, team, finance, housekeeping, channels,
marketplace, guestportal, messaging, compliance, revenue, ai, reports, saas, control`) exportan
`routes` y `nav` con los 46 ítems de la tabla del plan (Step 6). `marketplace` registra una home
provisional en `/` (hero + buscador que solo navega a `/search`). Ninguna feature exporta todavía
widgets, tabs, acciones, topbar ni comandos.

## Dependencias nuevas (pip/npm) y por qué

Exactamente la lista del plan (Step 1), más `@testing-library/dom` (peer dependency obligatoria de
`@testing-library/react` 16). Versiones instaladas relevantes: React 19.3, React Router 7.18, Vite 8.3
(rolldown), TypeScript 6.0, Tailwind 4.3, Vitest 5.0, ESLint 10, zod 4.6, i18next 26, radix-ui 1.6,
lucide-react 1.48. Ojo con lucide 1.x: se eliminaron alias antiguos (`History` → usar `FileClock`,
`Building2` → `Building`/`Hotel`, `Loader2` → `LoaderCircle`); verifica el nombre en
`node_modules/lucide-react/dist/lucide-react.d.ts`.

## Cambios requeridos en archivos compartidos u otras apps

- ~~A1/B3 (sugerido): incluir `phone` en `GET /accounts/me/`~~ **Hecho en A3**: `Me.phone` existe en el
  backend y en el tipo `Me` del frontend (antes el diálogo "Mi perfil" lo mostraba vacío y lo borraba al
  guardar otro campo).
- Para A3: `docker compose up -d frontend` también arranca `backend` (y sus dependencias) por el
  `depends_on`; durante A2 usé `--no-deps` para levantar solo el frontend sin tocar el trabajo de A1.
- No se modificó nada fuera de `frontend/**` y esta nota.

## Decisiones técnicas a conocer

- **Code splitting**: `AppLayout`, `AdminLayout`, `SettingsLayout`, `SettingsIndex`, `LoginPage`, el
  diálogo de perfil y la paleta ⌘K se cargan con `lazy` (la paleta se precarga en idle). React, React DOM
  y el router van en un chunk `react-vendor` cacheable (`build.rolldownOptions.output.codeSplitting`).
  Resultado: ningún chunk > 500 kB; entrada ≈ 111 kB + vendor ≈ 313 kB.
- ESLint: regla `react-hooks/incompatible-library` desactivada (solo aplica con React Compiler, que no
  se usa; TanStack Table/Virtual la disparan). `react-refresh/only-export-components` permite los
  exports de extensión (`routes`, `nav`, `widgets`, ...).
- Responsive: en teléfonos (< 640 px) la fecha de negocio va bajo el nombre del hotel y los menús de
  idioma y tema pasan al menú de cuenta (se renderizan condicionalmente, no solo ocultos por CSS).
- La paleta ⌘K lista todas las páginas visibles (incluidas las de configuración, con sufijo de sección
  para no repetir nombres como "Limpieza").

## Limitaciones conocidas / pendientes

- Todas las páginas de feature son stubs (`UnderConstruction`) hasta que su dueño las construya.
- El índice de configuración no agrupa secciones (el contrato `NavItem` no tiene grupo); se ordenan
  por `order`.
- No hay worker de MSW en el navegador: el desarrollo en vivo requiere el backend.
- El header público no detecta sesión iniciada (evita una llamada a `/me` en cada página pública);
  `/login` sí redirige al usuario ya autenticado.
- Verificación visual hecha con Chrome DevTools (claro/oscuro, ES/EN, 1440 px y 375 px, drawer móvil,
  paleta, configuración) y consola sin errores ni warnings.
