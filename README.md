# Housetel

PMS hotelero SaaS para Colombia (tipo Cloudbeds): PMS + marketplace propio + booking engine + channel manager +
integraciones legales colombianas (DIAN, SIRE, TRA) + IA. Todo corre localmente con Docker Compose y funciona sin
credenciales externas: cada integración arranca en modo **simulado**.

- Diseño (contrato común): [`docs/superpowers/specs/2026-09-25-housetel-pms-design.md`](docs/superpowers/specs/2026-09-25-housetel-pms-design.md)
- Plan de implementación (manda sobre el spec): [`docs/superpowers/plans/2026-09-25-housetel-implementation.md`](docs/superpowers/plans/2026-09-25-housetel-implementation.md)
- Notas de integración por tarea: [`docs/integration-notes/`](docs/integration-notes/)

## Arranque rápido

```bash
cp .env.example .env        # y completa DJANGO_SECRET_KEY / FERNET_KEY (ver comentarios)
make up                     # construye y levanta todos los servicios
make seed                   # datos de demo (idempotente; la primera vez tarda ~9 min, ver abajo)
```

Abre **http://localhost:5173** (la app completa; Vite hace proxy de `/api` y `/media` al backend).

| Servicio | Qué es | URL en el host |
|---|---|---|
| `frontend` | React 19 + Vite | http://localhost:5173 |
| `backend` | Django 5.2 + DRF (`runserver`, migra al arrancar) | http://localhost:8010 · docs API: http://localhost:8010/api/docs/ |
| `worker` | Celery worker | — |
| `beat` | Celery beat (horario generado desde el registro de automatizaciones) | — |
| `db` | PostgreSQL 17 (+ `btree_gist`) | no expuesto |
| `redis` | Redis 7 (broker + caché) | no expuesto |
| `mailpit` | SMTP local + bandeja web | http://localhost:8025 |

Solo el backend (útil mientras el frontend no está listo): `make up-back`.

## Credenciales demo (clave `housetel123`)

| Usuario | Rol |
|---|---|
| `admin@housetel.co` | Super-admin de la plataforma |
| `owner@casaaurora.co` | Dueño · Casa Aurora (Hotel Casa Aurora, Cartagena) |
| `recepcion@casaaurora.co` | Recepción · Casa Aurora |
| `limpieza@casaaurora.co` | Housekeeping · Casa Aurora |
| `contabilidad@casaaurora.co` | Contabilidad · Casa Aurora |
| `mantenimiento@casaaurora.co` | Mantenimiento · Casa Aurora (tickets) |
| `owner@grupoandino.co` | Dueño · Grupo Andino (Andino Medellín y Andino Hostel Bogotá) |
| `recepcion@grupoandino.co` | Recepción · Grupo Andino |
| `limpieza@grupoandino.co` | Housekeeping · Grupo Andino (solo Andino Medellín) |
| `owner@hostaldemo.co` | Dueño · Hostal Demo Trial (organización en prueba, sin inventario) |

Admin de Django: http://localhost:8010/django-admin/ (con `admin@housetel.co`).

## Datos de demo (`make seed`)

`seed_demo` recorre `SEED_ORDER` (cada app tiene su `seed.py`, idempotente) y crea todo **por los servicios de
contrato** (auditoría, señales e inventario incluidos). La primera carga tarda **≈ 9 min** (unas 3.360 reservas;
imprime el tiempo de cada app); repetirla solo revisa y no duplica. `make reset` borra la BD y la recrea desde cero
(migraciones + seed). Mientras corre conviene tener `worker` y `beat` detenidos (`make reset` ya lo hace así): las
automatizaciones no deben actuar sobre datos a medio sembrar.

- **Inventario**: Hotel Casa Aurora (24 habitaciones: Estándar, Superior, Suite Vista al Mar), Andino Medellín
  (40) y Andino Hostel Bogotá (dormitorios de 6 y 8 camas + privadas); amenidades, fotos, campos personalizados
  y overrides de ejemplo (p. ej. la 306).
- **Tarifas**: IVA 19 % (exento a extranjeros no residentes), políticas "Flexible 48h" y "No reembolsable",
  planes Tarifa flexible / No reembolsable (−12 %) / Con desayuno, temporadas, extras y el código `BIENVENIDA10`.
- **Huéspedes**: 183 por organización (colombianos y extranjeros, VIP, etiquetas, 3 duplicados para la demo de
  fusión); un rol propio y una invitación pendiente por organización.
- **Reservas** de −60 a +90 días en todos los estados y fuentes (recepción, teléfono, email, walk-in, booking
  engine, marketplace, BookSim/AirSim), con llegadas y salidas de hoy, huéspedes en casa y grupos.
- **Finanzas**: cargos por noche, pagos (efectivo, datáfono, transferencia, pasarela simulada), depósitos, links de
  pago pendientes, penalidades, folios cerrados en 0 y un turno de caja abierto para `recepcion@casaaurora.co` (y
  `recepcion@grupoandino.co` en Medellín).
- **Fase C**: tareas de limpieza de hoy y 3 tickets por hotel (uno bloquea una habitación); BookSim y AirSim
  conectados y sincronizados (+ iCal en el hostal); motor de reservas y listing con la marca de cada hotel;
  check-ins online completados y solicitudes del portal; plantillas, reglas del ciclo y conversaciones de ejemplo;
  resolución DIAN de pruebas con facturas de las salidas de los últimos 30 días, reportes SIRE y TRA; reglas,
  límites y recomendaciones de revenue; FAQ del chatbot; planes, suscripciones, facturas de plataforma y comisiones;
  30 cierres de auditoría nocturna; alertas reales de las anomalías del demo. Resumen y cifras:
  `docs/integration-notes/C-INT.md`.

## Qué funciona hoy (Fases A–C)

| Área | Rutas |
|---|---|
| Recepción | `/app` (Hoy: cifras, llegadas/salidas/en casa, tablero de llaves, widgets), `/app/reservations` (+ `/new`, `/:id`), `/app/night-audit` |
| Calendario | `/app/calendar` (arrastrar para mover/crear/estirar, dormitorios por cama) |
| Limpieza y mantenimiento | `/app/housekeeping`, `/app/housekeeping/mine` (móvil), `/app/maintenance`, `/app/settings/housekeeping` |
| Tarifas y revenue | `/app/rates`, `/app/rates/plans`, `/app/rates/promos`, `/app/revenue`, `/app/settings/{taxes,policies,extras}` |
| Canales | `/app/channels`, `/app/simulators/ota` (BookSim/AirSim/Channex simulados, iCal real) |
| Huéspedes, mensajes, caja | `/app/guests`, `/app/inbox`, `/app/simulators/whatsapp`, `/app/cashier` |
| Legal Colombia | `/app/compliance` (DIAN, SIRE, TRA), `/app/settings/compliance` |
| Reportes | `/app/reports`, `/app/reports/:id` (CSV/XLSX/PDF) |
| IA | copiloto (topbar, Ctrl+J), `/app/onboarding`, `/app/settings/{chatbot,ai}`, chatbot público en `/h/:slug` y `/g/:token` |
| Centro de control | `/app/alerts`, `/app/settings/{integrations,automations,audit}` |
| Configuración | `/app/settings/{property,room-types,rooms,custom-fields,booking-engine,guest-portal,messaging,users,roles,billing}` |
| Público | `/` (marketplace), `/search`, `/hotel/:slug`, `/book/:slug`, `/booking/:code/confirmed`, `/h/:slug` (motor del hotel), `/embed/:slug`, `/g/:token` (portal y check-in online), `/signup`, `/sim/pay/:reference` |
| Plataforma | `/admin` (métricas, organizaciones, planes, cobros, comisiones), `/app/getting-started`, `/app/settings/billing` |

Documentación de cada módulo (API con ejemplos, contratos, señales, cómo probarlo en la UI): `docs/integration-notes/`
(A1–A3, B1–B4, `B-INT.md`, C1–C13 y `C-INT.md`, que trae el checklist consolidado para validar en el navegador).

## Comandos

```bash
make help                          # lista todo
make up / make down / make ps / make logs
make migrate                       # aplica migraciones
make makemigrations APP=inventory  # migraciones de una app
make seed                          # datos de demo (idempotente)
make reset                         # borra la BD y recrea todo con datos de demo frescos
make test                          # backend + frontend
make test-back ARGS="apps/core"    # pytest (TEST_DB_NAME=test_x para correr en paralelo)
make test-front
make lint / make format            # ruff (backend) + eslint (frontend)
make check                         # system checks + migraciones pendientes + esquema OpenAPI sin warnings
make check-data                    # invariantes de inventario, dinero y datos de la Fase C (después del seed)
make check-automations             # cada automatización × propiedad en una transacción revertida
make smoke                         # smoke E2E de la API por el proxy de Vite (deja unos registros de prueba)
make sweep                         # GET de solo lectura a los endpoints principales de todos los módulos
make routes                        # abre todas las rutas en un Chrome headless propio (WIDTH=375 para celular)
make shell                         # shell de Django
```

Tests aislados por agente/tarea (bases de prueba distintas):

```bash
docker compose run --rm -e TEST_DB_NAME=test_<tarea> backend pytest apps/<app> -q
```

## Arquitectura

Monorepo: `backend/` (Python 3.13, Django 5.2, DRF, Celery 5, PostgreSQL 17, Redis 7) y `frontend/`
(React 19 + TypeScript + Vite, Tailwind 4, TanStack). El código se monta como volumen: no hace falta reconstruir
al cambiar código (sí al cambiar dependencias).

```
backend/
├── config/            settings (todo desde variables de entorno), urls, celery
├── conftest.py        fixtures comunes: organization, prop, make_member, owner, api, api_for, public_api
└── apps/
    ├── core/          tenancy, permisos, auditoría + deshacer, alertas, integraciones real/simulado,
    │                  automatizaciones, señales de dominio, tokens, dinero/fechas, seed
    ├── accounts/      User (login por email), Role, Membership, Invitation, auth (sesión + CSRF)
    ├── inventory/     categorías → habitaciones → camas, herencia de atributos, bloqueos
    ├── rates/         impuestos, políticas, planes base/derivados, grilla diaria, extras, promos, cotizador
    ├── bookings/      reservas, estadías (exclusión en BD contra doble asignación), inventario diario
    ├── guests/        huéspedes (CRM por organización); documentos de identidad fuera de /media
    │                  (`backend/media-private/` o PRIVATE_MEDIA_ROOT), solo por la API autenticada
    ├── finance/       folios, cargos (neto + IVA aparte), pagos, reembolsos, intents, caja
    └── frontdesk, housekeeping, distribution, marketplace, guestportal, messaging, compliance,
        revenue, ai, reports, saas, control      (módulos de la Fase C)

frontend/src/
├── app/               árbol de rutas, puntos de extensión (extensions.ts), layouts, shell, login
├── components/        compartidos (DataTable, FormField, Money, DatePicker, …) · ui/ (primitivas Radix)
├── design/            tokens "cálido nórdico" (claro/oscuro) y estilos base
├── lib/               cliente API (CSRF + X-Property-Id), auth/Me, permisos (fnmatch), i18n, formato
└── features/<f>/      routes.tsx, nav.ts, locales/{es,en}.json (+ widgets, pestañas, topbar, comandos)
```

Cada feature del frontend se registra sola por convención de archivos (plan §E; guía en
`docs/integration-notes/A2-frontend-foundation.md`).

Convenciones clave (detalle en el spec §3 y en `docs/integration-notes/A1-backend-foundation.md`):

- **API staff** `/api/v1/<app>/…` con sesión + CSRF y encabezado `X-Property-Id` (p. ej.
  `GET /api/v1/core/context/` devuelve la propiedad activa, el rol y los permisos); **pública**
  `/api/v1/public/<app>/…`. Errores siempre `{"detail", "code", "fields"?}`; anónimo → 401.
- **Permisos** `<app>.<acción>` declarados en `apps/<app>/permissions.py`; roles con patrones (`bookings.*`, `*`).
- **Dinero** `Decimal(14,2)`, strings en JSON; COP redondeado a pesos (`core.money.quantize`).
- **Fechas** de estadía: llegada inclusiva, salida exclusiva; rangos de servicios `[start, end)`.
- **Auto-descubrimiento**: cada app registra `permissions.py`, `providers.py`, `automations.py`,
  `receivers.py` y `seed.py`; nadie edita archivos centrales para registrarse.

## Integraciones: modo real vs simulado

Toda integración externa (pagos Wompi, Channex, iCal, DIAN, SIRE, TRA, email, WhatsApp, LLM, cobro SaaS) tiene un
proveedor `real` y uno `simulated`, configurable por propiedad en `IntegrationSetting` (los secretos se guardan
cifrados con Fernet). Por defecto todo es `simulated`, salvo email (SMTP → Mailpit en local) y el LLM (Gemini real
si existe `GEMINI_API_KEY`, con caída a simulado).
