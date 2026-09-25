# Housetel — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> En este proyecto la ejecución la orquestan **Workflows por fase**: cada tarea la toma un agente implementador (que DEBE usar `superpowers:test-driven-development`; si la tarea tiene UI, además `frontend-design:frontend-design`; si tiene gráficos, `dataviz`) seguido de un agente verificador.

**Goal:** Construir Housetel completo (PMS + marketplace propio + booking engine + channel manager + integraciones Colombia + IA + SaaS) corriendo localmente con `docker compose up`.

**Architecture:** Monorepo con backend Django/DRF/Celery y frontend React/Vite/TS. La Fase A crea los modelos núcleo, los contratos de servicios, los registros auto-descubiertos (permisos, automatizaciones, proveedores, seeds) y los puntos de extensión del frontend. Después, agentes en paralelo construyen rebanadas verticales por módulo. Cada agente es dueño exclusivo de sus directorios y se comunica con los demás solo vía contratos (§4.2 del spec y §C de este plan) y señales de dominio.

**Tech Stack:** Python 3.13, Django 5.2, DRF, Celery 5, PostgreSQL 17 (+btree_gist), Redis 7, React 19, TypeScript, Vite, Tailwind 4, React Router 7, TanStack Query/Table/Virtual, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-25-housetel-pms-design.md` (léelo completo antes de tu tarea; este plan lo complementa y, si hay conflicto, **manda este plan**).

## Global Constraints

- Python 3.13 · Django 5.2 LTS · DRF ≥3.16 · Celery ≥5.5 · PostgreSQL 17 con extensión `btree_gist` · Redis 7.
- Node 24 en Docker (host tiene Node 26) · React 19 · TypeScript estricto · Vite ≥7 · Tailwind CSS 4 (`@tailwindcss/vite`) · React Router 7 (modo librería, `createBrowserRouter`).
- Puertos host: frontend **5173**, backend **8010**, Mailpit **8025**. Postgres y Redis **no** se exponen (el host ya usa 5432 y 8000).
- La app corre completa sin credenciales externas: toda integración usa modo `simulated` por defecto. El LLM usa Gemini real con `GEMINI_API_KEY` del `.env` y cae a simulado si falla.
- El `.env` ya existe (lo creó el orquestador). **Nunca** lo commitees, lo imprimas completo ni copies la API key en código, tests, logs o documentación. Leer variables con `os.environ`.
- UI 100% vía i18n con ES y EN completos. Tema claro/oscuro. Responsive desde 375px.
- Dinero: `Decimal(14,2)`, strings en JSON. COP se redondea a pesos enteros (`ROUND_HALF_UP`) con `core.money.quantize`. `Charge.amount` es **neto**; `Charge.tax_amount` va aparte; total del cargo = `amount + tax_amount`.
- PK UUID en modelos de negocio. Zona horaria `America/Bogota`. Fechas de estadía: `checkin` inclusivo, `checkout` exclusivo.
- Sin CDNs: fuentes e íconos vía npm.
- Reglas de trabajo en paralelo: spec §9, más las de §B de este plan.

---

## §A. Modelo de ejecución

| Fase | Workflow | Agentes |
|---|---|---|
| A — Fundación | `housetel-phase-a` | A1 backend ∥ A2 frontend → A3 verificación de fase |
| B — Motores | `housetel-phase-b` | B1, B2a, B2b, B3, B4 (cada uno: implementa → verifica) → B-INT |
| C — Funcionalidades | `housetel-phase-c` | C1…C13 (cada uno: implementa → verifica) → C-INT |
| D — Integración | `housetel-phase-d` | D1 |
| E — E2E | orquestador con Claude-in-Chrome | — |

El orquestador levanta Docker, corre la suite y hace commit entre fases.

## §B. Reglas operativas para agentes

1. **Propiedad**: solo editas los paths listados en "Owner paths" de tu tarea y tu `docs/integration-notes/<tarea>.md`. Leer cualquier archivo está permitido. Leer modelos de otras apps vía ORM está permitido; **escribir** en ellos solo vía sus servicios de contrato.
2. **Migraciones**: solo de tu app (`python manage.py makemigrations <app>`). Puedes correr `migrate` en la BD de desarrollo; si choca con otro agente, reintenta.
3. **Modelos siempre importables**: tras editar `models.py` corre `docker compose run --rm backend python manage.py check`. Un modelo roto rompe a todos los agentes.
4. **Errores ajenos**: si un fallo proviene de código de otra app, no lo toques. Espera 1–2 min y reintenta. Si persiste, anótalo en tus integration-notes y continúa.
5. **Dependencias**: no agregues paquetes pip/npm salvo necesidad real. Si lo haces, anótalo en integration-notes con la razón (la fase de integración las consolida). Nunca corras `npm install <pkg>` en paralelo con otros agentes; si lo necesitas, anótalo y usa una alternativa.
6. **Tests aislados**: backend `docker compose run --rm -e TEST_DB_NAME=test_<tarea> backend pytest apps/<app> -q`; frontend `cd frontend && npx vitest run src/features/<feature>`; typecheck `cd frontend && npx tsc -p tsconfig.app.json --noEmit 2>&1 | grep -E "src/features/<feature>|src/components|src/lib|src/app" || true` (tu feature debe quedar sin errores).
7. **Señales**: los productores usan `core.signals.send_on_commit(...)` (internamente `send_robust`, que registra y no propaga excepciones de receivers). Los receivers van en `apps/<app>/receivers.py` (auto-descubierto). En tests usa el fixture `django_capture_on_commit_callbacks(execute=True)`.
8. **API docs**: documenta en tus integration-notes cada endpoint (método, path, payload y respuesta de ejemplo), las señales emitidas/escuchadas, las automatizaciones y los contratos implementados. Los agentes de fases posteriores los leen.
9. **Idioma**: código, nombres y comentarios en inglés; UI en ES/EN vía i18n; mensajes de error de API en español con `code` estable en inglés.
10. **No commits**: el orquestador commitea al cerrar cada fase.
11. **Calidad mínima por endpoint**: filtrado por propiedad/organización, chequeo de permiso, validación, test de aislamiento multi-tenant, test de permiso.

Plantilla de `docs/integration-notes/<tarea>.md`:

```markdown
# <Tarea> — integration notes
## API implementada
## Contratos implementados / consumidos
## Señales emitidas / escuchadas
## Automatizaciones registradas
## Proveedores de integración registrados
## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)
## Dependencias nuevas (pip/npm) y por qué
## Cambios requeridos en archivos compartidos u otras apps
## Limitaciones conocidas / pendientes
```

## §C. Contratos adicionales (complementan el spec §4.2)

Firmas que la Fase A crea (stub o implementación simple) y cuyos dueños completan en la Fase B:

```python
# apps/inventory/services.py
def release_block(block, *, actor=None) -> RoomBlock                       # emite inventory_changed
def provision_room_type(property, *, data: dict, room_numbers: list[str], floor: str | None = None,
                        beds_per_room: int | None = None, actor=None) -> RoomType
    # data: claves de RoomType (code, name{es,en}, kind, base_occupancy, max_adults, max_children,
    # max_occupancy, beds, size_m2, view, amenities[codes], color, housekeeping_minutes)

# apps/rates/services/provision.py
def provision_rates(property, *, room_type_prices: dict[str, dict], plans: list[dict] | None = None,
                    taxes_default: bool = True, policies_default: bool = True, actor=None) -> None
    # room_type_prices: {"DBL": {"price": "320000", "weekend_adjust_percent": 15,
    #                     "extra_adult_price": "60000", "extra_child_price": "30000"}}
    # plans=None → crea "Tarifa flexible" (base) + "No reembolsable" (−12%) + "Con desayuno" (+35000)

# apps/guests/services.py
def upsert_guest(organization, data: GuestInput, *, actor=None) -> Guest   # match por documento, luego email
def update_guest(guest, data: dict, *, source: str = "user", actor=None) -> Guest
def add_document(guest, *, kind: str, file, uploaded_via: str = "staff") -> GuestDocument
def find_duplicates(guest) -> list[Guest]
def merge_guests(primary, duplicate, *, actor) -> Guest

# apps/bookings/services/charges.py
def post_room_charges(stay, *, until_date, actor=None, source="automation") -> list[Charge]
    # publica (idempotente) cargos de alojamiento por cada noche < until_date aún no publicada

# apps/finance/services.py  (parámetro adicional)
def post_charge(folio, *, kind, amount, description, quantity=1, tax=None, tax_exempt=False,
                stay=None, night_date=None, extra=None, actor=None, source="user",
                business_date=None) -> Charge
    # amount = neto unitario; tax_amount = quantize(amount*quantity*tax.rate/100) si tax y no exento

# apps/core/tokens.py
def make_reservation_token(reservation) -> str
def read_reservation_token(token: str, *, max_age: int | None = None) -> Reservation | None
def portal_url(reservation) -> str        # f"{FRONTEND_URL}/g/{token}"
```

Campos adicionales respecto al spec:

- `Reservation.hold_expires_at` (datetime, null): expiración de reservas `tentative`.
- `Stay` de dormitorio: `room` = el dormitorio y `bed` = la cama. La exclusión por `room` aplica solo cuando `bed IS NULL`.
- Rol de sistema adicional `housekeeping_supervisor`.

Endpoints acordados entre tareas paralelas de la Fase C:

- C7 → C5: `GET /api/v1/public/compliance/portal/<token>/invoices/` → `[{id, number, kind, status, total, issued_at, pdf_url}]`, y `GET /api/v1/public/compliance/portal/<token>/invoices/<id>/pdf/`.
- C9 → C6: `POST /api/v1/ai/draft-reply/` `{guest_message, reservation_code?, language?, tone?}` → `{text, simulated}` (permiso `messaging.send`).
- C9 → C8: C8 usa `apps.ai.llm.get_llm(property).generate(...)` directamente.
- B2b → C1/C13: `GET /api/v1/bookings/calendar/?start=&end=` (ver B2b).

## §D. Catálogo de permisos y roles de sistema

Cada app declara en `apps/<app>/permissions.py` una lista `PERMISSIONS = [(code, label_es, label_en), ...]`. La Fase A crea todos estos archivos con estos códigos exactos:

| App | Códigos |
|---|---|
| accounts | `accounts.users_manage`, `accounts.roles_manage` |
| inventory | `inventory.view`, `inventory.manage` |
| rates | `rates.view`, `rates.manage` |
| bookings | `bookings.view`, `bookings.manage`, `bookings.checkin`, `bookings.cancel`, `bookings.waive_fee`, `bookings.checkout_with_balance`, `bookings.overbook` |
| guests | `guests.view`, `guests.manage`, `guests.merge`, `guests.export` |
| finance | `finance.view`, `finance.collect`, `finance.void`, `finance.refund`, `finance.cashier` |
| frontdesk | `frontdesk.view`, `frontdesk.night_audit` |
| housekeeping | `housekeeping.view`, `housekeeping.work`, `housekeeping.supervise`, `housekeeping.maintenance` |
| distribution | `distribution.view`, `distribution.manage` |
| marketplace | `marketplace.manage` |
| guestportal | `guestportal.view`, `guestportal.manage` |
| messaging | `messaging.view`, `messaging.send`, `messaging.templates` |
| compliance | `compliance.view`, `compliance.invoice`, `compliance.void_invoice`, `compliance.sire`, `compliance.tra`, `compliance.settings` |
| revenue | `revenue.view`, `revenue.manage` |
| ai | `ai.copilot`, `ai.onboarding`, `ai.settings` |
| reports | `reports.operational`, `reports.financial`, `reports.performance` |
| saas | `saas.billing_view`, `saas.billing_manage` |
| control | `control.integrations`, `control.automations`, `control.audit`, `control.audit_undo`, `control.alerts` |

Roles de sistema (`apps/accounts/roles.py`, `ROLE_TEMPLATES`; patrones con `fnmatch`):

```python
ROLE_TEMPLATES = {
    "owner": {"name": "Dueño", "permissions": ["*"]},
    "manager": {"name": "Gerente", "permissions": [
        "accounts.*", "inventory.*", "rates.*", "bookings.*", "guests.*", "finance.*", "frontdesk.*",
        "housekeeping.*", "distribution.*", "marketplace.*", "guestportal.*", "messaging.*",
        "compliance.*", "revenue.*", "ai.*", "reports.*", "control.*", "saas.billing_view"]},
    "front_desk": {"name": "Recepción", "permissions": [
        "frontdesk.view", "bookings.view", "bookings.manage", "bookings.checkin", "bookings.cancel",
        "guests.view", "guests.manage", "finance.view", "finance.collect", "finance.cashier",
        "messaging.view", "messaging.send", "guestportal.view", "guestportal.manage",
        "housekeeping.view", "compliance.view", "compliance.invoice", "compliance.sire", "compliance.tra",
        "reports.operational", "ai.copilot", "control.alerts", "inventory.view", "rates.view",
        "distribution.view", "revenue.view"]},
    "housekeeping_supervisor": {"name": "Supervisor de limpieza", "permissions": [
        "housekeeping.*", "inventory.view", "control.alerts"]},
    "housekeeping": {"name": "Housekeeping", "permissions": [
        "housekeeping.view", "housekeeping.work", "inventory.view"]},
    "maintenance": {"name": "Mantenimiento", "permissions": [
        "housekeeping.view", "housekeeping.maintenance", "inventory.view"]},
    "accountant": {"name": "Contabilidad", "permissions": [
        "finance.*", "reports.*", "compliance.*", "bookings.view", "guests.view", "control.audit",
        "control.alerts", "saas.billing_view", "inventory.view", "rates.view"]},
}
```

## §E. Puntos de extensión del frontend

`frontend/src/app/extensions.ts` (Fase A) auto-descubre por convención de nombre de archivo dentro de `src/features/<feature>/`. Nadie edita archivos centrales para registrarse.

```ts
import type { ComponentType } from 'react'
import type { RouteObject } from 'react-router'
import type { LucideIcon } from 'lucide-react'

export type NavSection = 'operations' | 'revenue' | 'insights' | 'compliance' | 'tools' | 'settings' | 'admin'
export interface NavItem { id: string; section: NavSection; labelKey: string; icon: LucideIcon; path: string; permission?: string; order?: number; platformAdmin?: boolean }
export interface FeatureRoutes { public?: RouteObject[]; app?: RouteObject[]; admin?: RouteObject[]; bare?: RouteObject[] }
export interface DashboardWidget { id: string; order: number; size: 'sm' | 'md' | 'lg' | 'full'; permission?: string; Component: ComponentType }
export interface ReservationTab { id: string; labelKey: string; order: number; permission?: string; Component: ComponentType<{ reservationId: string }> }
export interface ReservationAction { id: string; labelKey: string; icon: LucideIcon; order: number; permission?: string; danger?: boolean; Component: ComponentType<{ reservationId: string; close: () => void }> }
export interface GuestTab { id: string; labelKey: string; order: number; permission?: string; Component: ComponentType<{ guestId: string }> }
export interface TopbarItem { id: string; order: number; permission?: string; Component: ComponentType }
export interface CommandItem { id: string; group: string; labelKey: string; icon?: LucideIcon; keywords?: string[]; permission?: string; perform: (ctx: { navigate: (to: string) => void }) => void }
```

| Archivo en la feature | Export | Lo consume |
|---|---|---|
| `routes.tsx` | `export const routes: FeatureRoutes` | router (A2) |
| `nav.ts` | `export const nav: NavItem[]` | sidebar, settings nav, admin nav (A2) |
| `locales/es.json`, `locales/en.json` | JSON (namespace = nombre de carpeta) | i18n (A2) |
| `widgets.tsx` | `export const widgets: DashboardWidget[]` | panel Hoy (C1) |
| `reservation-tabs.tsx` | `export const reservationTabs: ReservationTab[]` | detalle de reserva (C1) |
| `reservation-actions.tsx` | `export const reservationActions: ReservationAction[]` | detalle de reserva (C1) |
| `guest-tabs.tsx` | `export const guestTabs: GuestTab[]` | perfil de huésped (B3) |
| `topbar.tsx` | `export const topbarItems: TopbarItem[]` | topbar (A2) |
| `commands.ts` | `export const commands: CommandItem[]` | paleta ⌘K (A2) |
| `public-widget.tsx` (solo `ai`) | `export default function PublicWidget(props: { propertySlug?: string; portalToken?: string })` | layouts públicos (A2) |

Helpers en `extensions.ts`: `getNav()`, `getFeatureRoutes()`, `useWidgets()`, `useReservationTabs()`, `useReservationActions()`, `useGuestTabs()`, `useTopbarItems()`, `useCommands()`. Filtran por permiso con `useCan` y ordenan por `order`. Usan `import.meta.glob('../features/*/<archivo>', { eager: true })`.

Rutas: en `app` los paths son relativos a `/app` (p. ej. `'calendar'`, `'settings/rooms'`), en `admin` relativos a `/admin`, en `public`/`bare` absolutos. Toda ruta `app` cuyo path empieza por `settings/` se anida en `SettingsLayout`. Las páginas usan `lazy: () => import('./pages/X').then(m => ({ Component: m.default }))`.

### Dueños de features del frontend

| Carpeta `src/features/` | Tarea | Rutas principales |
|---|---|---|
| `frontdesk` | C1 | `/app` (index), `/app/reservations*`, `/app/night-audit` |
| `calendar` | C13 | `/app/calendar` |
| `inventory` | B1 | `/app/settings/{property,room-types,rooms,custom-fields}` |
| `rates` | B2a | `/app/rates`, `/app/rates/plans`, `/app/rates/promos`, `/app/settings/{taxes,policies,extras}` |
| `guests` | B3 | `/app/guests`, `/app/guests/:id` |
| `team` | B3 | `/app/settings/{users,roles}`, `/invite/:token` |
| `finance` | B4 | `/app/cashier`, `/sim/pay/:reference` (bare) |
| `housekeeping` | C2 | `/app/housekeeping`, `/app/housekeeping/mine`, `/app/maintenance`, `/app/settings/housekeeping` |
| `channels` | C3 | `/app/channels`, `/app/simulators/ota` |
| `marketplace` | C4 | `/`, `/search`, `/hotel/:slug`, `/book/:slug`, `/booking/:code/confirmed`, `/h/:slug`, `/embed/:slug`, `/app/settings/booking-engine` |
| `guestportal` | C5 | `/g/:token`, `/g/:token/checkin`, `/app/settings/guest-portal` |
| `messaging` | C6 | `/app/inbox`, `/app/simulators/whatsapp`, `/app/settings/messaging` |
| `compliance` | C7 | `/app/compliance`, `/app/settings/compliance` |
| `revenue` | C8 | `/app/revenue` |
| `ai` | C9 | `/app/onboarding`, `/app/settings/chatbot`, `/app/settings/ai` |
| `reports` | C10 | `/app/reports`, `/app/reports/:reportId` |
| `saas` | C11 | `/signup`, `/admin/*`, `/app/settings/billing`, `/app/getting-started` |
| `control` | C12 | `/app/alerts`, `/app/settings/{integrations,automations,audit}` |

La Fase A crea **todas** estas carpetas con: `routes.tsx` (páginas `UnderConstruction` en sus rutas), `nav.ts` con sus ítems definitivos y `locales` ES/EN con las claves de navegación. El dueño luego lo reemplaza.

---

# FASE A — Fundación

### Task A1: Backend foundation

**Owner paths:** `docker-compose.yml`, `Makefile`, `README.md`, `.env.example`, `backend/**`, `docs/integration-notes/A1-backend-foundation.md`. **No toques** `.env` (ya existe) ni `frontend/**`.

**Interfaces producidas:** todo el spec §4 (modelos núcleo), §4.1 (señales), §4.2 + §C (contratos), §D (permisos/roles), registros del core, seed base, factories y fixtures.

- [ ] **Step 1: Infra y proyecto Django**

`docker-compose.yml`:

```yaml
name: housetel
x-backend: &backend
  build: ./backend
  env_file: .env
  environment:
    DATABASE_URL: postgres://housetel:housetel@db:5432/housetel
    REDIS_URL: redis://redis:6379/0
    EMAIL_HOST: mailpit
    EMAIL_PORT: "1025"
  volumes:
    - ./backend:/app
  depends_on:
    db:
      condition: service_healthy
    redis:
      condition: service_started

services:
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_DB: housetel
      POSTGRES_USER: housetel
      POSTGRES_PASSWORD: housetel
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U housetel -d housetel"]
      interval: 3s
      timeout: 3s
      retries: 30
  redis:
    image: redis:7-alpine
  backend:
    <<: *backend
    command: sh -c "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"
    ports:
      - "8010:8000"
  worker:
    <<: *backend
    command: celery -A config worker -l info --concurrency 2
  beat:
    <<: *backend
    command: celery -A config beat -l info --schedule /tmp/celerybeat-schedule
  frontend:
    build: ./frontend
    environment:
      VITE_PROXY_TARGET: http://backend:8000
    volumes:
      - ./frontend:/app
      - /app/node_modules
    ports:
      - "5173:5173"
    depends_on:
      - backend
  mailpit:
    image: axllent/mailpit
    ports:
      - "8025:8025"

volumes:
  pgdata: {}
```

`backend/Dockerfile`:

```dockerfile
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends gettext curl && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
```

`backend/requirements.txt` (con rangos `>=x,<y` y versiones actuales al instalar): `Django>=5.2,<5.3`, `djangorestframework`, `django-filter`, `drf-spectacular`, `psycopg[binary]>=3.2`, `dj-database-url`, `celery[redis]>=5.5`, `redis`, `cryptography`, `holidays`, `icalendar`, `httpx`, `google-genai`, `anthropic`, `reportlab`, `openpyxl`, `Pillow`, `phonenumbers`, `qrcode`, `python-dateutil`, `pytest`, `pytest-django`, `factory-boy`, `freezegun`, `respx`, `ruff`.

`backend/pyproject.toml`: configura `[tool.ruff]` (line-length 110, target py313, select `E,F,I,B,UP,DJ`) y `[tool.pytest.ini_options]` (`DJANGO_SETTINGS_MODULE = "config.settings"`, `python_files = ["test_*.py"]`, `addopts = "-p no:cacheprovider"`).

`backend/config/settings.py` (todo desde `os.environ`):
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS=["*"]` en dev, `FRONTEND_URL` (default `http://localhost:5173`), `FERNET_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL` (default `gemini-3.5-flash`), `ANTHROPIC_API_KEY`, `CLAUDE_MODEL`, `WOMPI_PLATFORM_*`.
- `LOCAL_APPS = ["core","accounts","inventory","rates","bookings","guests","finance","frontdesk","housekeeping","distribution","marketplace","guestportal","messaging","compliance","revenue","ai","reports","saas","control"]`; `INSTALLED_APPS` = contrib (incl. `django.contrib.postgres`) + `rest_framework`, `django_filters`, `drf_spectacular` + `[f"apps.{a}" for a in LOCAL_APPS]`.
- `AUTH_USER_MODEL = "accounts.User"`.
- `DATABASES = {"default": dj_database_url.parse(os.environ["DATABASE_URL"])}` y `DATABASES["default"]["TEST"] = {"NAME": os.environ.get("TEST_DB_NAME", "test_housetel")}`.
- `CACHES` en Redis, `CELERY_BROKER_URL = REDIS_URL`, `CELERY_TIMEZONE = "America/Bogota"`, `CELERY_TASK_ALWAYS_EAGER = False`.
- `EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"`, `EMAIL_HOST`, `EMAIL_PORT`, `DEFAULT_FROM_EMAIL = "Housetel <no-reply@housetel.co>"`.
- `TIME_ZONE = "America/Bogota"`, `USE_TZ = True`, `LANGUAGE_CODE = "es"`, `LANGUAGES = [("es","Español"),("en","English")]`.
- `MEDIA_ROOT = BASE_DIR / "media"`, `MEDIA_URL = "/media/"`, `STATIC_URL = "/static/"`.
- `CSRF_TRUSTED_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]`, `SESSION_COOKIE_SAMESITE = "Lax"`, `CSRF_COOKIE_HTTPONLY = False`.
- `REST_FRAMEWORK`: `DEFAULT_AUTHENTICATION_CLASSES=["rest_framework.authentication.SessionAuthentication"]`, `DEFAULT_PERMISSION_CLASSES=["rest_framework.permissions.IsAuthenticated"]`, `DEFAULT_PAGINATION_CLASS="apps.core.api.pagination.StandardPagination"`, `DEFAULT_FILTER_BACKENDS=["django_filters.rest_framework.DjangoFilterBackend","rest_framework.filters.SearchFilter","rest_framework.filters.OrderingFilter"]`, `EXCEPTION_HANDLER="apps.core.api.exceptions.exception_handler"`, `DEFAULT_SCHEMA_CLASS="drf_spectacular.openapi.AutoSchema"`, throttle `login: 10/min`.
- `LOGGING` a consola.

`backend/config/urls.py`:

```python
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
for app in settings.LOCAL_APPS:
    urlpatterns += [
        path(f"api/v1/public/{app}/", include(f"apps.{app}.public_urls")),
        path(f"api/v1/{app}/", include(f"apps.{app}.urls")),
    ]
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

`backend/config/celery.py`:

```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("housetel")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.on_after_finalize.connect
def register_automation_schedules(sender, **kwargs):
    import django
    django.setup()
    from apps.core import automation
    from apps.core.tasks import run_automation_task
    for item in automation.all():
        sender.add_periodic_task(item.schedule, run_automation_task.s(item.code), name=item.code)
```

`backend/config/__init__.py`: `from .celery import app as celery_app` (con `__all__`).

`Makefile` (usa `docker compose`): `up` (`up -d --build`), `down`, `logs`, `ps`, `migrate`, `seed` (`run --rm backend python manage.py seed_demo`), `reset` (`down -v` + `up -d --build` + migrate + seed con `--reset`), `test-back` (`run --rm backend pytest -q`), `test-front` (`run --rm frontend npm run test`), `test` (ambos), `lint`, `shell` (`run --rm backend python manage.py shell`).

`.env.example`: todas las variables del `.env` con valores vacíos o de ejemplo y un comentario por variable.

- [ ] **Step 2: `apps/core`**

Archivos: `models.py`, `api/pagination.py`, `api/exceptions.py`, `api/views.py`, `tenancy.py`, `permissions.py`, `audit.py`, `alerts.py`, `integrations.py`, `automation.py`, `signals.py`, `tokens.py`, `money.py`, `dates.py`, `codes.py`, `i18n.py`, `errors.py`, `tasks.py`, `seed.py`, `management/commands/seed_demo.py`, `apps.py`, `urls.py`, `public_urls.py`, `admin.py`, `migrations/0001_*` (incluye `BtreeGistExtension()` como primera operación) y `tests/`.

`models.py`: `BaseModel` (abstracto: `id` UUID uuid4, `created_at` auto_now_add, `updated_at` auto_now) y `Organization`, `Property`, `AuditEvent`, `Alert`, `IntegrationSetting`, `AutomationSetting`, `AutomationRun` exactamente con los campos del spec §4. `Property.business_date` default `timezone.localdate`. `Alert` tiene `UniqueConstraint(fields=["property","dedupe_key"], condition=Q(resolved_at__isnull=True), name="alert_open_unique")`. `IntegrationSetting` tiene `UniqueConstraint(fields=["property","kind"])` (nota: si `property` es null en Postgres, usa `nulls_distinct=False`).

`errors.py`:

```python
class DomainError(Exception):
    code = "domain_error"
    status_code = 400

    def __init__(self, message: str = "", *, code: str | None = None, **extra):
        super().__init__(message or self.__class__.__name__)
        self.message = message or str(self)
        if code:
            self.code = code
        self.extra = extra


class ConfirmationRequired(DomainError):
    code = "confirmation_required"
    status_code = 400


class PaymentRequiredError(DomainError):
    code = "organization_suspended"
    status_code = 402
```

`api/exceptions.py`: envuelve el handler de DRF y normaliza toda respuesta a `{"detail": str, "code": str, "fields"?: {campo: [msgs]}, ...extra}`. `DomainError` → `status_code` + `code` + `extra`; `ValidationError` → 400 `code="validation_error"` + `fields`; `IntegrityError` de exclusión → 409 `code="conflict"`.

`api/pagination.py`: `PageNumberPagination` con `page_size=25`, `page_size_query_param="page_size"`, `max_page_size=200`.

`tenancy.py`:

```python
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import permissions, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.views import APIView

from apps.core.errors import PaymentRequiredError
from apps.core.permissions import codes_match

PROPERTY_HEADER = "HTTP_X_PROPERTY_ID"


def resolve_property(request):
    from apps.accounts.models import Membership
    from apps.core.models import Property

    raw = request.META.get(PROPERTY_HEADER)
    if not raw:
        raise ValidationError({"detail": "Falta el encabezado X-Property-Id", "code": "property_required"})
    try:
        prop = Property.objects.select_related("organization").get(pk=raw)
    except (Property.DoesNotExist, ValueError, DjangoValidationError):
        raise NotFound("Propiedad no encontrada")
    membership = (
        Membership.objects.select_related("role")
        .filter(user=request.user, organization=prop.organization, is_active=True)
        .first()
    )
    if membership is None or not (membership.all_properties or membership.properties.filter(pk=prop.pk).exists()):
        raise NotFound("Propiedad no encontrada")
    return prop, membership


class PropertyAccess(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        prop, membership = resolve_property(request)
        request.property = prop
        request.organization = prop.organization
        request.membership = membership
        if prop.organization.status == "suspended" and not getattr(view, "allow_suspended", False):
            raise PaymentRequiredError("La organización está suspendida por falta de pago")
        code = view.get_required_permission() if hasattr(view, "get_required_permission") else None
        if code and not codes_match(membership.role.permissions, code):
            raise PermissionDenied({"detail": "No tienes permiso para esta acción", "code": "permission_denied",
                                    "permission": code})
        return True


class PropertyScopedMixin:
    """required_permissions: {"list": "x.view", "create": "x.manage", "*": "x.view"} (ViewSet: por action;
    APIView: por método en minúscula: {"get": ..., "post": ...})."""
    property_field = "property"
    required_permissions: dict = {}
    permission_classes = [permissions.IsAuthenticated, PropertyAccess]

    def get_required_permission(self):
        key = getattr(self, "action", None) or self.request.method.lower()
        return self.required_permissions.get(key) or self.required_permissions.get("*")

    def get_queryset(self):
        return super().get_queryset().filter(**{self.property_field: self.request.property})

    def perform_create(self, serializer):
        if self.property_field == "property":
            serializer.save(property=self.request.property)
        else:
            serializer.save()


class OrganizationScopedMixin(PropertyScopedMixin):
    property_field = "organization"

    def get_queryset(self):
        return super(PropertyScopedMixin, self).get_queryset().filter(organization=self.request.organization)

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)


class PropertyScopedViewSet(PropertyScopedMixin, viewsets.ModelViewSet):
    pass


class PropertyScopedAPIView(PropertyScopedMixin, APIView):
    def get_queryset(self):  # APIView no tiene queryset base
        raise NotImplementedError
```

`permissions.py`:

```python
from fnmatch import fnmatchcase
from importlib import import_module

from django.apps import apps as django_apps

_REGISTRY: dict[str, tuple[str, str]] = {}


def register(code: str, label_es: str, label_en: str) -> None:
    _REGISTRY[code] = (label_es, label_en)


def catalog() -> dict[str, tuple[str, str]]:
    return dict(sorted(_REGISTRY.items()))


def codes_match(granted: list[str], code: str) -> bool:
    return any(g == "*" or g == code or fnmatchcase(code, g) for g in granted or [])


def has_perm(user, prop, code: str) -> bool:
    from apps.accounts.models import Membership
    m = (Membership.objects.select_related("role")
         .filter(user=user, organization=prop.organization, is_active=True).first())
    if not m or not (m.all_properties or m.properties.filter(pk=prop.pk).exists()):
        return False
    return codes_match(m.role.permissions, code)


def autodiscover() -> None:
    for cfg in django_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        try:
            module = import_module(f"{cfg.name}.permissions")
        except ModuleNotFoundError as exc:
            if exc.name != f"{cfg.name}.permissions":
                raise
            continue
        for code, es, en in getattr(module, "PERMISSIONS", []):
            register(code, es, en)
```

> Ojo: `apps/core/permissions.py` es el registro. Las demás apps tienen su propio `apps/<app>/permissions.py` con la lista `PERMISSIONS`. `core` no declara permisos propios (`PERMISSIONS = []` se define aparte en `apps/core/permissions.py`, sin conflicto).

`audit.py`:

```python
def record(*, action, target=None, summary="", actor=None, source="user", changes=None,
           reversible=False, undo_data=None, property=None, organization=None) -> AuditEvent: ...
def register_undo(action: str, handler) -> None: ...            # handler(event) -> None; revierte
def undo(event, *, actor) -> AuditEvent: ...                    # valida reversible y no deshecho; llama al
                                                                # handler en transacción; marca undone_at/by;
                                                                # registra evento "core.undo"
def diff(before: dict, after: dict) -> dict: ...                # {"campo": [antes, después]}
```

`target_type` = `"app_label.model"` y `target_id` = str(pk). `organization` se deriva de `property` si no se pasa. `actor_label` = email del usuario o nombre de la automatización.

`alerts.py`: `raise_alert(*, property, kind, severity, title, message, link="", dedupe_key, data=None, source="system") -> Alert` (actualiza la abierta si existe misma dedupe_key) y `resolve_alert(property, dedupe_key, *, actor=None) -> int`.

`integrations.py`:

```python
import json
from cryptography.fernet import Fernet
from django.conf import settings

KINDS = ["payments", "channel_ical", "channel_channex", "einvoice", "sire", "tra", "email", "whatsapp",
         "llm", "saas_billing"]


class BaseProvider:
    kind: str = ""
    mode: str = ""            # "real" | "simulated"
    label: str = ""
    CONFIG_FIELDS: list[dict] = []
    # cada campo: {"name","label_es","label_en","type":"text|password|url|select|boolean|number",
    #              "secret":bool,"required":bool,"options":[{"value","label_es","label_en"}],"help_es":"","help_en":""}

    def __init__(self, setting):
        self.setting = setting
        self.config = setting.config or {}
        self.secrets = get_secrets(setting)

    def test_connection(self) -> tuple[bool, str]:
        return True, "OK"


_PROVIDERS: dict[tuple[str, str], type[BaseProvider]] = {}


def register_provider(kind: str, mode: str, cls: type[BaseProvider]) -> None: ...
def providers_for(kind: str) -> dict[str, type[BaseProvider]]: ...
def default_mode(kind: str) -> str:
    if kind == "email":
        return "real"
    if kind == "llm":
        return "real" if getattr(settings, "GEMINI_API_KEY", "") else "simulated"
    return "simulated"
def get_setting(property, kind: str) -> "IntegrationSetting": ...   # get_or_create(mode=default_mode, enabled=True)
def get_provider(property, kind: str) -> BaseProvider: ...
    # instancia la clase registrada para (kind, setting.mode); si no existe para ese modo pero existe
    # "simulated", usa simulated y levanta alerta (dedupe "integration:<kind>:fallback").
    # Si no hay ninguna → IntegrationNotAvailable(DomainError, code="integration_not_available").
def set_secrets(setting, data: dict) -> None: ...   # merge con existentes; cifra JSON con Fernet(settings.FERNET_KEY)
def get_secrets(setting) -> dict: ...
def autodiscover() -> None: ...   # importa apps.<app>.providers (el módulo llama register_provider)
```

`automation.py`:

```python
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class RunResult:
    status: str = "success"       # success | partial | failed | skipped
    summary: str = ""
    details: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Automation:
    code: str
    app: str
    name_es: str
    name_en: str
    description_es: str
    schedule: Any                 # celery.schedules.crontab(...) o segundos (float)
    handler: Callable             # handler(property_or_None, params: dict) -> RunResult
    default_enabled: bool = True
    scope: str = "property"       # property | platform
    default_params: dict = field(default_factory=dict)
    description_en: str = ""


def register(item: Automation) -> None: ...
def get(code: str) -> Automation: ...
def all() -> list[Automation]: ...
def is_enabled(code: str, property) -> bool: ...     # AutomationSetting o default_enabled
def params_for(code: str, property) -> dict: ...     # default_params ∪ setting.params
def run(code: str, property=None, *, params=None, triggered_by=None) -> "AutomationRun": ...
    # crea AutomationRun(status="running"), ejecuta handler; guarda status/summary/details/finished_at;
    # excepción → status="failed", details={"error": ...}, raise_alert(severity="warning",
    # dedupe_key=f"automation:{code}"); éxito → resolve_alert del mismo dedupe;
    # audit.record(action=f"automation.{code}", source="automation", actor=triggered_by)
def autodiscover() -> None: ...                       # importa apps.<app>.automations
```

`tasks.py`:

```python
from celery import shared_task


@shared_task(name="core.run_automation")
def run_automation_task(code: str, property_id: str | None = None):
    from apps.core import automation
    from apps.core.models import Property
    item = automation.get(code)
    if item.scope == "platform":
        automation.run(code, None)
        return
    qs = Property.objects.filter(status="active",
                                 organization__status__in=["trial", "active", "past_due"])
    if property_id:
        qs = qs.filter(pk=property_id)
    for prop in qs:
        if automation.is_enabled(code, prop):
            automation.run(code, prop)
```

`signals.py`:

```python
import logging

from django.db import transaction
from django.dispatch import Signal

logger = logging.getLogger("housetel.signals")

reservation_created = Signal()      # reservation
reservation_updated = Signal()      # reservation, changes: dict[str, tuple[old, new]]
reservation_cancelled = Signal()    # reservation
reservation_no_show = Signal()      # reservation
stay_checked_in = Signal()          # stay
stay_checked_out = Signal()         # stay
room_assigned = Signal()            # stay, old_room
room_status_changed = Signal()      # room, old, new
inventory_changed = Signal()        # property, room_type_ids: list, start: date|None, end: date|None
rates_changed = Signal()            # property, room_type_ids, rate_plan_ids, start, end
payment_received = Signal()         # payment
folio_closed = Signal()             # folio
guest_checked_in_online = Signal()  # reservation


def send_on_commit(signal: Signal, **kwargs) -> None:
    def _send():
        for receiver, result in signal.send_robust(sender=None, **kwargs):
            if isinstance(result, Exception):
                logger.error("Receiver %r failed: %r", receiver, result, exc_info=result)
    transaction.on_commit(_send)
```

`apps.py` (`CoreConfig.ready`): `permissions.autodiscover()`, `integrations.autodiscover()`, `automation.autodiscover()` y `autodiscover_modules("receivers")`.

`tokens.py` (spec §C):

```python
from django.conf import settings
from django.core import signing

SALT = "housetel.reservation"


def make_reservation_token(reservation) -> str:
    return signing.dumps({"r": str(reservation.pk)}, salt=SALT, compress=True)


def read_reservation_token(token: str, *, max_age: int | None = None):
    from apps.bookings.models import Reservation
    try:
        data = signing.loads(token, salt=SALT, max_age=max_age)
    except signing.BadSignature:
        return None
    return Reservation.objects.select_related("property").filter(pk=data.get("r")).first()


def portal_url(reservation) -> str:
    return f"{settings.FRONTEND_URL}/g/{make_reservation_token(reservation)}"
```

Otros módulos de `core`:
- `money.py`: `D(x) -> Decimal`, `quantize(amount, currency="COP") -> Decimal` (COP → `Decimal("1")`, otras → `Decimal("0.01")`, `ROUND_HALF_UP`), `apply_percent(amount, percent)`.
- `dates.py`: `nights(checkin, checkout) -> list[date]` y `daterange(start, end_exclusive)`, `overlaps(a_start, a_end, b_start, b_end)`, `property_now(property)`.
- `codes.py`: `generate_code(prefix="HT", length=6)`, alfabeto `23456789ABCDEFGHJKMNPQRSTUVWXYZ`.
- `i18n.py`: `t(value, lang="es")` (dict → valor del idioma, luego `es`, luego el primero no vacío; str → str).

`api/views.py`: `GET /api/v1/core/health/` (público, `AllowAny`, `{"status":"ok"}`) en `public_urls.py`.

- [ ] **Step 3: `apps/accounts`**

- `models.py`: `User(AbstractBaseUser, PermissionsMixin)` con `id` UUID, `email` único (USERNAME_FIELD), `full_name`, `language` (es/en), `phone`, `is_platform_admin`, `is_staff`, `is_active`, `date_joined`, más `UserManager` (`create_user`, `create_superuser`). También `Role`, `Membership` (única `(user, organization)`) e `Invitation` según el spec §4.
- `roles.py`: `ROLE_TEMPLATES` (§D).
- `services.py`: `ensure_system_roles(organization) -> dict[str, Role]` (crea o actualiza copias por organización con `is_system=True`) y `add_member(organization, user, role_code, *, all_properties=True, properties=None) -> Membership`.
- API (`urls.py`): `GET auth/csrf/` (`ensure_csrf_cookie`, `AllowAny`), `POST auth/login/` (`AllowAny`, throttle `login`, email case-insensitive; 400 `code="invalid_credentials"`), `POST auth/logout/`, `GET/PATCH me/` (PATCH solo `full_name`, `language`, `phone`). La respuesta `Me` tiene exactamente la forma del spec §3. Los códigos de permisos se exponen tal cual están en el rol (patrones incluidos); el frontend hace el matching.
- `permissions.py` con los códigos de §D.
- Admin de Django registrado.

- [ ] **Step 4: modelos de dominio**

Crea los modelos de `inventory`, `rates`, `bookings`, `guests` y `finance` exactamente con los campos del spec §4 y los agregados de §C. Registra todo en admin. Genera migraciones iniciales. Detalles obligatorios:

```python
# apps/bookings/models.py (fragmento obligatorio)
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateRangeField, RangeOperators
from django.db import models
from django.db.models import F, Func, Q, Value

ACTIVE_STAY_STATUSES = ["tentative", "confirmed", "checked_in"]


class DateRangeFunc(Func):
    function = "daterange"
    output_field = DateRangeField()


class Stay(BaseModel):
    # ... campos del spec ...
    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(checkout_date__gt=F("checkin_date")), name="stay_dates_valid"),
            ExclusionConstraint(
                name="stay_no_room_overlap",
                expressions=[
                    (DateRangeFunc("checkin_date", "checkout_date", Value("[)")), RangeOperators.OVERLAPS),
                    ("room", RangeOperators.EQUAL),
                ],
                condition=Q(status__in=ACTIVE_STAY_STATUSES, room__isnull=False, bed__isnull=True),
            ),
            ExclusionConstraint(
                name="stay_no_bed_overlap",
                expressions=[
                    (DateRangeFunc("checkin_date", "checkout_date", Value("[)")), RangeOperators.OVERLAPS),
                    ("bed", RangeOperators.EQUAL),
                ],
                condition=Q(status__in=ACTIVE_STAY_STATUSES, bed__isnull=False),
            ),
        ]
```

- `Stay` **no** lleva el campo `period` del spec: se reemplaza por la expresión `DateRangeFunc`. Las consultas de solapamiento usan `checkin_date__lt=end, checkout_date__gt=start`.
- `InventoryDay` con `UniqueConstraint(fields=["room_type","date"])` e índice `(property, date)`, más la propiedad `available`.
- `Reservation.code` único; `Reservation.hold_expires_at`.
- `DailyRate` con `UniqueConstraint(room_type, rate_plan, date)`.
- `Guest` con índice único parcial `(organization, document_type, document_number)` con condición `~Q(document_number="")`.
- `Room` con `UniqueConstraint(property, number)`.
- Choices como `TextChoices` en cada `models.py`.

- [ ] **Step 5: tipos y servicios de contrato**

`apps/rates/types.py`:

```python
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class NightPrice:
    date: date
    base: Decimal
    extra_adults: Decimal
    extra_children: Decimal
    discount: Decimal
    total: Decimal


@dataclass(frozen=True)
class TaxLine:
    code: str
    name: str
    rate: Decimal
    amount: Decimal
    included: bool
    exempt: bool = False


@dataclass(frozen=True)
class DayRate:
    date: date
    price: Decimal
    extra_adult_price: Decimal
    extra_child_price: Decimal
    min_los: int | None
    max_los: int | None
    closed_to_arrival: bool
    closed_to_departure: bool
    stop_sell: bool
    source: str


@dataclass(frozen=True)
class Quote:
    room_type_id: UUID
    rate_plan_id: UUID
    checkin: date
    checkout: date
    adults: int
    children: int
    nights: list[NightPrice]
    subtotal: Decimal              # Σ nights.total (ya con descuento)
    discount_total: Decimal
    taxes: list[TaxLine]
    tax_total: Decimal             # Σ impuestos NO incluidos y no exentos
    total: Decimal                 # subtotal + tax_total
    currency: str
    restrictions_ok: bool
    violations: list[str] = field(default_factory=list)
    promo_applied: str | None = None

    def to_dict(self) -> dict:     # JSON-safe: Decimal→str, date→isoformat, UUID→str
        ...
```

`apps/bookings/types.py`:

```python
from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from typing import Any
from uuid import UUID

from apps.core.errors import DomainError
from apps.guests.types import GuestInput
from apps.rates.types import Quote


@dataclass
class StayRequest:
    room_type_id: UUID
    rate_plan_id: UUID
    checkin: date
    checkout: date
    adults: int
    children: int = 0
    children_ages: list[int] = field(default_factory=list)
    room_id: UUID | None = None
    bed_id: UUID | None = None
    locked_room: bool = False
    occupants: list[GuestInput] = field(default_factory=list)
    nightly_rates: list[dict] | None = None     # precios impuestos por un canal: [{"date","amount"}]


@dataclass
class ReservationRequest:
    property: Any
    booker: Any                                 # GuestInput | Guest
    stays: list[StayRequest]
    source: str = "front_desk"
    channel_code: str = ""
    external_id: str = ""
    external_payload: dict = field(default_factory=dict)
    notes: str = ""
    special_requests: str = ""
    promo_code: str = ""
    language: str = "es"
    eta: time | None = None
    status: str = "confirmed"                   # confirmed | tentative
    allow_overbooking: bool = False
    enforce_restrictions: bool = True
    hold_minutes: int = 20
    guarantee: str = "none"
    group_id: UUID | None = None
    custom_values: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Offer:
    room_type_id: UUID
    rate_plan_id: UUID
    available_units: int
    units_needed: int                           # dorm: 1 por huésped; privada: 1
    quote: Quote                                # por unidad
    total: Decimal                              # quote.total * units_needed


@dataclass
class AssignmentReport:
    assigned: list[tuple[str, str]] = field(default_factory=list)   # (stay_id, room_or_bed_id)
    unassigned: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


class BookingError(DomainError):
    code = "booking_error"


class AvailabilityError(BookingError):
    code = "no_availability"
    status_code = 409


class RestrictionError(BookingError):
    code = "restriction_violation"


class InvalidStateError(BookingError):
    code = "invalid_state"
    status_code = 409


class RoomNotReadyError(BookingError):
    code = "room_not_ready"
    status_code = 409


class BalanceDueError(BookingError):
    code = "balance_due"
    status_code = 409
```

`apps/guests/types.py`: `@dataclass class GuestInput` con `first_name, last_name, email="", phone="", document_type="", document_number="", nationality="", country_of_residence="", city_of_residence="", birth_date: date | None = None, language="es", marketing_consent=False, data_processing_consent=False`.

`apps/ai/types.py`:

```python
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolCall:
    name: str
    arguments: dict
    id: str = ""


@dataclass
class LLMResult:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    data: dict | list | None = None
    provider: str = "simulated"
    model: str = ""
    simulated: bool = True
    usage: dict = field(default_factory=dict)


class LLMClient(Protocol):
    def generate(self, messages: list[dict], *, system: str | None = None, tools: list[dict] | None = None,
                 response_schema: dict | None = None, temperature: float = 0.2) -> LLMResult: ...
# messages: [{"role": "user"|"assistant"|"tool", "content": str, "tool_call_id"?: str, "name"?: str}]
# tools: [{"name": str, "description": str, "parameters": <JSON Schema>}]
```

Servicios (firmas exactas del spec §4.2 y §C). Nivel de implementación en la Fase A:

| Servicio | Fase A implementa | Completa |
|---|---|---|
| `rates.services.quote.quote` | Simple: precio base = `DailyRate` del plan base → `RoomTypeRateDefaults.price` → 0; derivación %/monto; impuestos `Tax` activos (no incluidos) con exención; `stop_sell` → violación | B2a |
| `rates.services.quote.resolve_daily` | Simple (DailyRate → defaults) | B2a |
| `rates.services.quote.set_daily_rates` | Simple (update_or_create + `rates_changed`) | B2a |
| `rates.services.provision.provision_rates` | `NotImplementedError` | B2a |
| `bookings.services.availability.availability` | Correcto pero lento (cuenta unidades activas − stays activas solapadas − bloqueos) | B2b |
| `bookings.services.availability.search_offers` | `NotImplementedError` | B2b |
| `bookings.services.reservations.*` | `NotImplementedError` | B2b |
| `bookings.services.charges.post_room_charges` | `NotImplementedError` | B2b |
| `finance.services`: `get_or_create_folio`, `post_charge`, `record_payment` (emite `payment_received`), `folio_balance`, `reservation_balance` | Implementación correcta simple | B4 |
| `finance.services`: `void_charge`, `refund_payment`, `create_payment_intent`, `sync_payment_intent` | `NotImplementedError` | B4 |
| `inventory.services`: `effective_attributes`, `block_room`, `release_block`, `set_housekeeping_status` | Implementación correcta simple (con señales) | B1 |
| `inventory.services.provision_room_type` | `NotImplementedError` | B1 |
| `guests.services`: `upsert_guest`, `update_guest`, `add_document` | Simple | B3 |
| `guests.services`: `find_duplicates`, `merge_guests` | `NotImplementedError` | B3 |
| `messaging.services.send_message` | Registra en log y devuelve `[]` | C6 |
| `ai.llm.get_llm` | Cliente simulado (`LLMResult(text="(modo simulado) …", simulated=True)`) | C9 |

`reservation_balance(reservation)`: `Σ stay.total_amount (activas)` + cargos no-alojamiento no anulados (`kind != "room"`, con impuestos) − pagos aprobados + reembolsos aprobados. Los cargos `room` consumen el total esperado y no se suman dos veces.

- [ ] **Step 6: apps esqueleto de la Fase C**

Para `frontdesk, housekeeping, distribution, marketplace, guestportal, messaging, compliance, revenue, ai, reports, saas, control` crea: `__init__.py`, `apps.py` (`name="apps.<app>"`, `label="<app>"`), `models.py` vacío, `urls.py` y `public_urls.py` con `urlpatterns = []`, `permissions.py` con los códigos de §D, `migrations/__init__.py`, `tests/__init__.py`. `messaging/services.py` y `ai/llm.py` + `ai/types.py` según el Step 5.

- [ ] **Step 7: factories y fixtures**

`apps/<app>/tests/factories.py` para core (`OrganizationFactory`, `PropertyFactory`), accounts (`UserFactory` con password `pass1234`, `RoleFactory`, `MembershipFactory`), inventory (`RoomTypeFactory`, `RoomFactory`, `BedFactory`, `DormRoomTypeFactory`), rates (`TaxFactory`, `CancellationPolicyFactory`, `RatePlanFactory`, `RoomTypeRateDefaultsFactory`), guests (`GuestFactory`, `ForeignGuestFactory`), bookings (`ReservationFactory`, `StayFactory`) y finance (`FolioFactory`, `ChargeFactory`, `PaymentFactory`).

`backend/conftest.py`:

```python
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def organization(db):
    from apps.accounts.services import ensure_system_roles
    from apps.core.tests.factories import OrganizationFactory
    org = OrganizationFactory(status="active")
    ensure_system_roles(org)
    return org


@pytest.fixture
def prop(organization):
    from apps.core.tests.factories import PropertyFactory
    return PropertyFactory(organization=organization)


@pytest.fixture
def make_member(organization):
    from apps.accounts.services import add_member
    from apps.accounts.tests.factories import UserFactory

    def _make(role_code="owner", *, properties=None, org=None, **user_kwargs):
        user = UserFactory(**user_kwargs)
        add_member(org or organization, user, role_code, all_properties=properties is None,
                   properties=properties)
        return user
    return _make


@pytest.fixture
def owner(make_member):
    return make_member("owner")


@pytest.fixture
def api_for():
    def _api(user, property_obj):
        client = APIClient()
        client.force_authenticate(user=user)
        client.credentials(HTTP_X_PROPERTY_ID=str(property_obj.pk))
        return client
    return _api


@pytest.fixture
def api(api_for, owner, prop):
    return api_for(owner, prop)


@pytest.fixture
def public_api():
    return APIClient()
```

- [ ] **Step 8: seed base**

`apps/core/seed.py`:

```python
SEED_ORDER = ["inventory", "rates", "guests", "bookings", "finance", "housekeeping", "distribution",
              "marketplace", "guestportal", "messaging", "compliance", "revenue", "ai", "saas",
              "frontdesk", "reports", "control"]


@dataclass
class SeedContext:
    today: date
    rng: random.Random            # random.Random(20260925) — determinístico
    orgs: dict[str, Organization]
    properties: dict[str, Property]   # claves: "aurora", "andino_mde", "andino_bog"
    users: dict[str, User]
    data: dict                         # espacio compartido entre seeders
    stdout: Any = None

    def log(self, msg: str) -> None: ...
```

`run(*, reset=False, stdout=None)`: si `reset`, borra organizaciones (cascade) y usuarios no-superadmin. Luego `seed_base()` crea: superadmin `admin@housetel.co` (`is_platform_admin`, `is_superuser`, `is_staff`); las orgs "Casa Aurora" (slug `casa-aurora`) y "Grupo Andino" (`grupo-andino`), ambas `active`; las propiedades del spec §10 con sus slugs `casa-aurora` (Cartagena, Bolívar, boutique, 10.4236,-75.5518), `andino-medellin` (Medellín, Antioquia, hotel, El Poblado 6.2086,-75.5659) y `andino-hostel-bogota` (Bogotá, Cundinamarca, hostel, La Candelaria 4.5981,-74.0758), todas con descripción ES/EN, RNT, NIT ficticio, `marketplace_listed=True` y `business_date=today`; los roles de sistema; y los usuarios del spec §10 con clave `housetel123`. Claves en `ctx.users`: `admin, aurora_owner, aurora_front, aurora_hk, aurora_acct, andino_owner, andino_front, andino_hk`. Después, por cada app en `SEED_ORDER`, importa `apps.<app>.seed` si existe y llama `seed(ctx)`, imprimiendo el progreso. Cada seeder debe ser idempotente (no duplica si ya hay datos). `manage.py seed_demo [--reset]`.

- [ ] **Step 9: tests de fundación (TDD — escríbelos primero)**

`apps/core/tests/`:
- `test_tenancy.py`: sin header → 400 `property_required`; propiedad de otra org → 404; membership restringida a otra propiedad → 404; permiso faltante → 403 con `permission`; org suspendida → 402 salvo `allow_suspended`.
- `test_permissions.py`: `codes_match` con `*`, exacto, `bookings.*`, no-match; el registro contiene todos los códigos de §D tras `autodiscover()`.
- `test_audit.py`: `record` crea el evento con organization derivada; `undo` llama al handler, marca `undone_at` y rechaza un segundo undo y los no reversibles.
- `test_alerts.py`: `raise_alert` con misma dedupe actualiza y no duplica; `resolve_alert`.
- `test_integrations.py`: roundtrip de secretos cifrados (en BD no aparece el texto plano); `get_setting` crea con `default_mode`; `get_provider` hace fallback a simulado con alerta.
- `test_automation.py`: `run` registra éxito, fallo (+alerta) y respeta `is_enabled`; `run_automation_task` itera solo propiedades activas.
- `test_signals.py`: `send_on_commit` no dispara hasta el commit; un receiver que lanza excepción no rompe a los demás.
- `test_tokens.py`: roundtrip, token alterado → None.
- `test_money_dates_codes.py`.
- `test_health.py`.

`apps/accounts/tests/test_auth.py`: csrf cookie; login OK/incorrecto; `me` con la forma exacta (memberships, permissions, properties con `business_date`); PATCH de language; logout; `ensure_system_roles` idempotente.

`apps/bookings/tests/test_constraints.py`: dos stays activas solapadas en la misma habitación → `IntegrityError`; la segunda cancelada → permitido; checkout de una = checkin de otra → permitido; dorm: dos stays en el mismo cuarto con camas distintas → permitido y en la misma cama → `IntegrityError`.

`apps/rates/tests/test_quote_basic.py`, `apps/finance/tests/test_balance_basic.py`, `apps/inventory/tests/test_services_basic.py`, `apps/guests/tests/test_upsert_basic.py`: un test por función implementada en el Step 5.

`apps/core/tests/test_seed.py`: `run()` dos veces no duplica y crea las 3 propiedades y 8 usuarios.

- [ ] **Step 10: verificación**

```bash
docker compose build backend
docker compose up -d db redis mailpit backend worker beat
docker compose run --rm -e TEST_DB_NAME=test_a1 backend pytest -q        # todo verde
docker compose run --rm backend ruff check .                              # limpio
docker compose run --rm backend python manage.py seed_demo
curl -s -c /tmp/hc -b /tmp/hc http://localhost:8010/api/v1/accounts/auth/csrf/ -o /dev/null
# login con CSRF (extrae csrftoken del cookie jar) → 200 y JSON Me; luego GET /api/v1/accounts/me/ → 200
curl -s http://localhost:8010/api/v1/public/core/health/                  # {"status":"ok"}
docker compose logs beat | grep -i "Scheduler"                           # beat arriba sin errores
```

Escribe `docs/integration-notes/A1-backend-foundation.md` y un `README.md` inicial con arquitectura, comandos y credenciales demo.

---

### Task A2: Frontend foundation

**Owner paths:** `frontend/**`, `docs/integration-notes/A2-frontend-foundation.md`.

**Interfaces producidas:** §E completo, cliente API, auth, permisos, i18n, tema, shell, layouts, componentes compartidos (spec §7.4), stubs de todas las features y página de login.

- [ ] **Step 1: proyecto y dependencias**

`frontend/package.json` con scripts `dev` (`vite`), `build` (`tsc -b && vite build`), `typecheck` (`tsc -p tsconfig.app.json --noEmit`), `test` (`vitest run`), `lint` (`eslint .`), `preview`.

Dependencias: `react`, `react-dom`, `react-router`, `@tanstack/react-query`, `@tanstack/react-table`, `@tanstack/react-virtual`, `radix-ui`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`, `sonner`, `cmdk`, `react-day-picker`, `date-fns`, `react-hook-form`, `@hookform/resolvers`, `zod`, `i18next`, `react-i18next`, `i18next-browser-languagedetector`, `recharts`, `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`, `zustand`, `@fontsource-variable/manrope`, `signature_pad`, `qrcode.react`, `react-markdown`.

Dev: `vite`, `@vitejs/plugin-react`, `@tailwindcss/vite`, `tailwindcss`, `typescript`, `@types/react`, `@types/react-dom`, `@types/node`, `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, `@testing-library/jest-dom`, `msw`, `eslint`, `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `globals`.

Genera `package-lock.json` con `npm install` en el host (sin `node_modules` previos).

`vite.config.ts`:

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

const target = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8010'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target, changeOrigin: false },
      '/media': { target, changeOrigin: false },
    },
  },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], css: false, globals: true },
})
```

`frontend/Dockerfile`:

```dockerfile
FROM node:24-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

Más `.dockerignore` (`node_modules`, `dist`, `coverage`), `tsconfig.json` / `tsconfig.app.json` / `tsconfig.node.json` (strict, `paths` `@/*`) y `eslint.config.js`.

- [ ] **Step 2: sistema de diseño "cálido nórdico"**

`src/design/tokens.css`: variables del spec §7.3 para claro (`:root`, `[data-theme="light"]`) y oscuro (`[data-theme="dark"]` y `@media (prefers-color-scheme: dark)` con `:root:not([data-theme="light"])`), incluidas `--room-clean`, `--room-dirty`, `--room-inspected`, `--room-ooo`, `--room-occupied` y los de estado de reserva (`--status-tentative`, `--status-confirmed`, `--status-checked-in`, `--status-checked-out`, `--status-cancelled`, `--status-no-show`). Mapea todo en `@theme` de Tailwind 4 para que existan clases como `bg-bg`, `bg-surface`, `bg-surface-2`, `border-border`, `text-fg`, `text-muted`, `bg-accent`, `text-accent`, `bg-accent-soft`, `bg-success-soft`, etc. Define `--font-sans: "Manrope Variable", ui-sans-serif, system-ui`, radios (`--radius: 10px`) y sombras mínimas. En `src/design/base.css`: importa `@fontsource-variable/manrope`, `tailwindcss` y tokens; `body` con `bg-bg text-fg`, 14px en `.app-shell` y 16px en `.public-shell`; `tabular-nums` para `.num`; foco visible.

Usa el skill `frontend-design:frontend-design` para que el resultado sea distintivo y no genérico: aire, jerarquía tipográfica clara, un solo acento terracota, bordes finos, estados suaves.

`index.html`: `lang="es"`, título "Housetel", favicon SVG propio (monograma "h" terracota) y script inline que aplica `data-theme` desde `localStorage` antes del render.

- [ ] **Step 3: librerías base**

- `src/lib/api.ts`:

```ts
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string,
              public fields?: Record<string, string[]>, public data?: Record<string, unknown>) { super(message) }
}
type Query = Record<string, string | number | boolean | undefined | null | string[]>
interface RequestOpts { params?: Query; body?: unknown; signal?: AbortSignal; public?: boolean; formData?: FormData }
export async function request<T>(method: string, path: string, opts?: RequestOpts): Promise<T>
export const api = { get, post, put, patch, delete: del }   // staff: base '/api/v1', envía X-Property-Id
export const publicApi = { get, post, put, patch, delete: del } // base '/api/v1/public', sin X-Property-Id
```

  Comportamiento: `credentials: 'include'`; en métodos no seguros asegura el cookie `csrftoken` (si no existe hace `GET /api/v1/accounts/auth/csrf/` una vez) y envía `X-CSRFToken`; `X-Property-Id` desde `useSession.getState().propertyId`; parsea el error `{detail, code, fields}` → `ApiError`; 401 en rutas `/app` o `/admin` → `window.location.assign('/login?next=...')`; 204 → `undefined`; `formData` → sin `Content-Type` JSON.
- `src/lib/session.ts`: store zustand persistido (`propertyId`, `setPropertyId`).
- `src/lib/auth.tsx`: `useMe()` (query `['me']`), `useLogin()`, `useLogout()`, `RequireAuth` (redirige a `/login?next=`), `RequirePlatformAdmin`, `useActiveProperty()` (propiedad activa o la primera de las memberships; sincroniza el store) y `useActiveMembership()`.
- `src/lib/permissions.ts`: `matchPermission(granted: string[], code: string)` (mismo algoritmo `fnmatch` que el backend: `*`, exacto, sufijo `.*`, comodines) y `useCan(code?: string): boolean`.
- `src/lib/i18n/index.ts`: i18next con detector (localStorage → navegador), `fallbackLng: 'es'`, namespace `common` + un namespace por feature cargado con `import.meta.glob('../../features/*/locales/*.json', { eager: true })`; `setLanguage(lang)` que además hace PATCH a `/accounts/me/` si hay sesión.
- `src/lib/format.ts`: `formatMoney(value: string|number, currency='COP', locale)` (COP sin decimales, `es-CO`), `formatDate`, `formatDateRange`, `nightsBetween`, `formatRelative`.
- `src/lib/theme.tsx`: `ThemeProvider` (`light|dark|system`, atributo `data-theme`) y `useTheme`.
- `src/lib/query.ts`: `queryClient` (staleTime 30s, retry 1, sin retry en 4xx).
- `src/test/setup.ts`: jest-dom, i18n de test y utilidades MSW (`server`).

- [ ] **Step 4: componentes compartidos**

`src/components/ui/`: `button, input, textarea, select, combobox, checkbox, switch, radio-group, label, dialog, sheet, dropdown-menu, popover, tooltip, tabs, badge, card, table, skeleton, separator, avatar, scroll-area, toggle-group, calendar (react-day-picker)`, estilo shadcn sobre `radix-ui` + CVA, usando los tokens.

`src/components/`: `PageHeader` (título, descripción, acciones, breadcrumbs), `EmptyState`, `ErrorState`, `LoadingState`, `UnderConstruction`, `DataTable` (TanStack: orden, filtros, paginación servidor/cliente, selección, densidad, estado vacío), `FormField` (react-hook-form), `MoneyText`, `MoneyInput` (COP con separador de miles), `DatePicker`, `DateRangePicker` (presets opcionales), `StatusBadge` (`kind: 'reservation'|'room'|'payment'|'task'`), `KpiTile` (valor, delta, sparkline opcional), `ConfirmDialog`, `DangerConfirmDialog` (exige escribir un texto exacto para confirmar), `Toaster` (sonner), `CommandPalette` (cmdk + `useCommands` + navegación + "Preguntar al copiloto" si existe), `Logo`.

- [ ] **Step 5: extensiones, router, layouts y shell**

- `src/app/extensions.ts` (§E completo con helpers).
- `src/app/router.tsx`: construye `createBrowserRouter` con `PublicLayout` (rutas `public` + `/login`), `BareLayout` (rutas `bare`), `/app` → `RequireAuth` + `AppLayout` (rutas `app`; las `settings/*` anidadas en `SettingsLayout` en `/app/settings`, cuyo index muestra una grilla de secciones), `/admin` → `RequirePlatformAdmin` + `AdminLayout` (rutas `admin`), 404 global y error boundary.
- `AppLayout`: sidebar colapsable con secciones (Operación, Ingresos, Análisis, Legal, Herramientas, Configuración). Los ítems salen de `getNav()` filtrados por permiso; en móvil es un drawer. Topbar con selector de propiedad (agrupado por organización), badge de fecha de negocio, botón de búsqueda (⌘K), `TopbarItems`, idioma, tema y menú de usuario (perfil, cerrar sesión). Si no hay propiedades → mensaje y logout.
- `PublicLayout`: header (logo Housetel, "Para hoteles" → `/signup`, idioma, "Ingresar"), footer y `<PublicChatSlot/>` (carga `features/ai/public-widget.tsx` con `import.meta.glob`; pasa `propertySlug` si la ruta tiene `:slug` y `portalToken` si tiene `:token`).
- `AdminLayout`: sidebar con la sección `admin` y un banner "Panel de plataforma".
- `SettingsLayout`: navegación secundaria desde la sección `settings`.
- `src/app/pages/LoginPage.tsx`: split con panel de marca (ilustración abstracta en tokens) y formulario email/clave con validación zod; muestra credenciales demo si `import.meta.env.DEV`; redirige a `next` o a `/app` (o a `/admin` si es solo platform admin).
- `src/app/pages/NotFound.tsx`.

- [ ] **Step 6: stubs de features**

Crea las 18 carpetas de §E con `routes.tsx`, `nav.ts` y `locales/{es,en}.json`. Cada `nav.ts` lleva sus ítems definitivos con ícono lucide y permiso:

| Feature | Ítems de nav (id · sección · path · permiso) |
|---|---|
| frontdesk | today·operations·`/app`·frontdesk.view; reservations·operations·`/app/reservations`·bookings.view; nightAudit·tools·`/app/night-audit`·frontdesk.night_audit |
| calendar | calendar·operations·`/app/calendar`·bookings.view |
| guests | guests·operations·`/app/guests`·guests.view |
| housekeeping | housekeeping·operations·`/app/housekeeping`·housekeeping.view; maintenance·operations·`/app/maintenance`·housekeeping.view; settingsHousekeeping·settings·`/app/settings/housekeeping`·housekeeping.supervise |
| messaging | inbox·operations·`/app/inbox`·messaging.view; waSim·tools·`/app/simulators/whatsapp`·messaging.send; settingsMessaging·settings·`/app/settings/messaging`·messaging.templates |
| finance | cashier·operations·`/app/cashier`·finance.view |
| rates | rates·revenue·`/app/rates`·rates.view; ratePlans·revenue·`/app/rates/plans`·rates.view; promos·revenue·`/app/rates/promos`·rates.view; taxes·settings·`/app/settings/taxes`·rates.manage; policies·settings·`/app/settings/policies`·rates.manage; extras·settings·`/app/settings/extras`·rates.manage |
| revenue | revenue·revenue·`/app/revenue`·revenue.view |
| channels | channels·revenue·`/app/channels`·distribution.view; otaSim·tools·`/app/simulators/ota`·distribution.manage |
| reports | reports·insights·`/app/reports`·reports.operational |
| control | alerts·insights·`/app/alerts`·control.alerts; integrations·settings·`/app/settings/integrations`·control.integrations; automations·settings·`/app/settings/automations`·control.automations; audit·settings·`/app/settings/audit`·control.audit |
| compliance | compliance·compliance·`/app/compliance`·compliance.view; settingsCompliance·settings·`/app/settings/compliance`·compliance.settings |
| inventory | property·settings·`/app/settings/property`·inventory.manage; roomTypes·settings·`/app/settings/room-types`·inventory.view; rooms·settings·`/app/settings/rooms`·inventory.view; customFields·settings·`/app/settings/custom-fields`·inventory.manage |
| team | users·settings·`/app/settings/users`·accounts.users_manage; roles·settings·`/app/settings/roles`·accounts.roles_manage |
| marketplace | bookingEngine·settings·`/app/settings/booking-engine`·marketplace.manage |
| guestportal | guestPortal·settings·`/app/settings/guest-portal`·guestportal.manage |
| ai | onboarding·tools·`/app/onboarding`·ai.onboarding; chatbot·settings·`/app/settings/chatbot`·ai.settings; aiSettings·settings·`/app/settings/ai`·ai.settings |
| saas | gettingStarted·tools·`/app/getting-started`·(sin permiso); billing·settings·`/app/settings/billing`·saas.billing_view; adminHome·admin·`/admin`·platformAdmin; adminOrgs·admin·`/admin/organizations`·platformAdmin; adminPlans·admin·`/admin/plans`·platformAdmin; adminBilling·admin·`/admin/billing`·platformAdmin; adminCommissions·admin·`/admin/commissions`·platformAdmin |

`routes.tsx` de cada stub registra sus rutas con `UnderConstruction`. `marketplace` registra `/` con una home provisional mínima (hero + buscador sin funcionalidad) para que la raíz no quede en blanco.

- [ ] **Step 7: tests (TDD) y verificación**

Tests: `src/lib/__tests__/api.test.ts` (CSRF, `X-Property-Id`, `ApiError` con fields, 204); `permissions.test.ts` (paridad con los casos del backend); `src/app/__tests__/extensions.test.ts` (descubre nav y rutas de los stubs, filtra por permiso, anida settings); `LoginPage.test.tsx` (validación, submit, redirección, con MSW); `format.test.ts` (COP `$ 320.000`); `theme.test.tsx`.

```bash
cd frontend && npm run typecheck && npm run lint && npm run test && npm run build
docker compose build frontend && docker compose up -d frontend
curl -s http://localhost:5173/ | grep -i "housetel"
curl -s http://localhost:5173/api/v1/public/core/health/     # proxy al backend (si A1 ya lo levantó)
```

Escribe `docs/integration-notes/A2-frontend-foundation.md` con la guía de uso de extensiones, componentes y cliente API para los agentes siguientes.

---

### Task A3: Verificación de la Fase A

Agente verificador con permiso para corregir **cualquier** archivo de la Fase A. Checklist:

- [ ] `docker compose down -v && docker compose up -d --build` levanta los 7 servicios. `docker compose ps` los muestra healthy/running y `docker compose logs backend worker beat frontend` no tiene tracebacks.
- [ ] `make seed` funciona dos veces seguidas.
- [ ] Backend: `pytest -q` verde y `ruff check .` limpio. Frontend: `typecheck`, `lint`, `test` y `build` verdes.
- [ ] Flujo real por el proxy de Vite (curl con cookie jar contra `http://localhost:5173/api/...`): csrf → login `owner@casaaurora.co` → me → GET a un endpoint scoped con `X-Property-Id` (crea un endpoint de prueba solo si no existe ninguno).
- [ ] Coherencia de contratos: cada firma del spec §4.2 y de §C existe con el nombre y los parámetros exactos (`grep`).
- [ ] Los permisos de §D existen en cada `permissions.py`; los roles de sistema coinciden; `nav.ts` y las rutas de las 18 features existen.
- [ ] Corrige lo que falle y documenta en `docs/integration-notes/A3-phase-a-check.md`.

---

# FASE B — Motores núcleo

> Todas las tareas B corren en paralelo. Antes de empezar lee spec, plan y las notas A1/A2.

### Task B1: Inventario y perfil de propiedad

**Owner paths:** `backend/apps/inventory/**`, `frontend/src/features/inventory/**`, `docs/integration-notes/B1-inventory.md`. Excepción autorizada: B1 expone el endpoint que edita `core.Property` (perfil) desde su propia app.

**Consumes:** `core` (tenancy, audit, signals).
**Produces:** servicios de inventario de §4.2 y §C completos (incluido `provision_room_type`), la API y la UI de configuración, fotos, campos personalizados y bloqueos.

**API** (`/api/v1/inventory/`; `inventory.view` para GET y `inventory.manage` para escritura):

| Método y path | Descripción |
|---|---|
| `GET/PATCH property/` | Perfil de `request.property` (PATCH: name, description, address, city, department, lat/lng, phone, email, website, rnt_number, nit, legal_name, star_rating, check_in_time, check_out_time, default_language, house_rules, branding) |
| `GET/POST amenities/` | Catálogo global + propio de la org (POST crea propio) |
| CRUD `room-types/` | Incluye `amenities` (codes), `units_count`, `custom_values`; `POST room-types/{id}/duplicate/` |
| `GET/POST/DELETE room-types/{id}/photos/`, `POST .../photos/reorder/` | multipart `image`, `caption` |
| CRUD `rooms/` | filtros `room_type, floor, housekeeping_status, is_active, search`; respuesta incluye `effective` (atributos resueltos) y `overridden_fields` |
| `POST rooms/bulk-create/` | `{room_type, numbers: "101-110,201,203", floor}` → crea; 400 si hay duplicados (lista cuáles) |
| `POST rooms/bulk-update/` | `{ids: [...], set: {campo: valor}, reset: [campos]}` (acepta campos de Room, overrides y custom_values) |
| `GET rooms/{id}/effective/` · `POST rooms/{id}/reset-override/` `{field}` | herencia |
| `POST rooms/{id}/status/` `{housekeeping_status}` | vía `set_housekeeping_status` |
| CRUD `rooms/{id}/beds/` · `POST rooms/{id}/beds/bulk/` `{count, prefix:"C"}` | dorms |
| CRUD `custom-fields/` | filtro `applies_to` |
| `GET/POST blocks/` · `POST blocks/{id}/release/` | vía `block_room` / `release_block` |
| `GET summary/` | unidades por categoría, totales, conteo por estado (para checklist y onboarding) |

**Reglas:** `overrides` solo acepta `ROOM_OVERRIDABLE_FIELDS`; `custom_values` validados con `validate_custom_values`; crear, borrar o desactivar habitaciones/camas, cambiar de categoría y crear o liberar bloqueos emiten `inventory_changed` (rango `None` = horizonte completo); una categoría `dorm` exige camas en sus habitaciones (advertencia en `summary` si falta); una habitación con reservas activas no se borra (409 `room_in_use`, sugiere desactivar).

**Frontend:** `/app/settings/property` (secciones General, Ubicación, Legal, Horarios e idiomas, Reglas, Marca); `/app/settings/room-types` (lista con color, unidades y capacidad + editor en página con pestañas General · Capacidad y camas · Amenidades · Fotos (drag & drop, orden) · Campos personalizados); `/app/settings/rooms` (tabla agrupada por categoría, selección múltiple → edición masiva, creación masiva por rangos, editor de habitación con valores heredados en gris, botón "Sobrescribir" / "Restaurar herencia" por campo, pestañas Camas y Bloqueos); `/app/settings/custom-fields`. Componente exportable `RoomStatusBadge`.

**Tests obligatorios** (`apps/inventory/tests/`): herencia (categoría, override con bandera, reset); validación de custom values (tipo, requerido, opción inválida); bulk-create (parseo de rangos "101-103,105" → 4, duplicados → 400); bulk-update solo afecta los seleccionados; camas para dorm; `block_room`/`release_block` emiten `inventory_changed` (capturando on_commit); `set_housekeeping_status` emite `room_status_changed`; `provision_room_type` crea categoría, habitaciones, camas y amenidades; borrar habitación con reservas activas → 409; aislamiento multi-tenant y permisos (housekeeping no puede editar). Frontend: editor de habitación (heredado vs sobrescrito), creación masiva y validación.

**Seed** (`apps/inventory/seed.py`): catálogo global de amenidades (≥30, ES/EN, íconos lucide) y categorías/habitaciones del spec §10:
- Aurora: Estándar (DBL, 10: 101–110, queen, 22 m²), Superior (SUP, 8: 201–208, king, balcón, 28 m²), Suite Vista al Mar (STE, 6: 301–306, king, bañera, 42 m²).
- Andino MDE: Estándar (20), Ejecutiva (14), Familiar (6).
- Hostel BOG: Dorm mixto 6 camas (2 cuartos × 6), Dorm mixto 8 camas (2 × 8), Dorm femenino 6 (1 × 6), Privada doble (6), Privada familiar (2).
- Campos personalizados de ejemplo: "Minibar" (boolean, room) y "Orientación" (select: mar, ciudad, jardín; room_type).
- Algunos overrides (p. ej. la 306 con vista panorámica).
- Fotos: intenta descargar `https://picsum.photos/seed/<slug>-<n>/1200/800` (timeout 5 s). Si falla, genera con Pillow degradados cálidos con el nombre, determinísticos.

**Aceptación:** el spec §5 B1 completo; la UI permite recorrer los 3 niveles de herencia.

---

### Task B2a: Tarifas

**Owner paths:** `backend/apps/rates/**`, `frontend/src/features/rates/**`, `docs/integration-notes/B2a-rates.md`.

**Consumes:** `bookings.services.availability.availability` (para la grilla), `core`.
**Produces:** `quote`, `resolve_daily`, `set_daily_rates` completos; `provision_rates`; API y UI de tarifas.

**Algoritmo de `quote` (normativo):**
1. `nights = core.dates.nights(checkin, checkout)`; si vacío → `violations=["invalid_dates"]`.
2. Plan base efectivo = el plan si es base, o su `parent` si es derivado.
3. Precio base por noche (plan base): `DailyRate` → `SeasonRate` de la temporada activa de mayor prioridad (con `dow_adjustments`) → `RoomTypeRateDefaults.price` con `dow_adjustments` → sin precio (violación `no_rate`). `dow_adjustments` usa claves `mon…sun` en %.
4. Derivado: `percent` → `price * (1 + v/100)`; `amount` → `price + v` (mínimo 0).
5. Ocupación: adultos por encima de `base_occupancy` × `extra_adult_price`; niños con edad ≤ `child_age_limit` × `extra_child_price`; niños mayores cuentan como adultos. Si `adults == 1` y hay `single_occupancy_price` → reemplaza el base. Dorm: 1 persona por unidad, sin extras.
6. Promo: si vigente (fechas de reserva y estadía, plan permitido, usos) → descuento % o monto por noche proporcional; `promo_applied=code`. Si no aplica → `violations += ["promo_invalid"]` sin bloquear (`restrictions_ok` no cambia por promo).
7. Restricciones sobre las filas del plan base: `stop_sell` en cualquier noche → `stop_sell`; `closed_to_arrival` en checkin → `cta`; `closed_to_departure` en la fila de la fecha de checkout → `ctd`; `min_los` de la noche de llegada (o `plan.min_los_default`) → `min_los`; `max_los` → `max_los`. `restrictions_ok = not violations_de_restricción`.
8. Impuestos (`Tax` activos con `applies_to in (room, all)`): si `exempt_foreign_non_residents` y el huésped es extranjero no residente → línea con `amount=0, exempt=True`; `included_in_price` → línea informativa `amount = subtotal - subtotal/(1+rate)` (no suma); si no → `amount = subtotal*rate`, suma a `tax_total`.
9. Redondeo con `core.money.quantize` por noche y en totales.

**`set_daily_rates`:** crea las filas faltantes con el precio resuelto para completar; aplica `price` o, si viene `restrictions={"price_delta_percent"|"price_delta_amount": x}`, ajuste relativo; filtra `dow` (lista 0–6, lunes=0); no permite planes derivados (DomainError `derived_plan_not_editable`); registra `audit.record(action="rates.bulk_update", reversible=True, undo_data={"rows": [valores previos]})`; registra el handler de undo que restaura; emite `rates_changed`.

**API** (`/api/v1/rates/`; `rates.view` / `rates.manage`): CRUD `taxes/`, `cancellation-policies/`, `rate-plans/` (validación: derivado solo de base, sin ciclos, `room_types` ⊆ los del padre), `room-type-defaults/` (upsert por room_type+plan), `seasons/` + `season-rates/`, `extras/`, `promo-codes/`. Además:
- `GET grid/?start&end&rate_plan` → `{dates:[...], holidays:[{date,name}], room_types:[{id, name, color, rows:[{date, price, extra_adult_price, extra_child_price, min_los, max_los, cta, ctd, stop_sell, source, available}] }]}`; si se pide un derivado, devuelve precios derivados en solo lectura.
- `POST grid/bulk/` `{room_type_ids, rate_plan_id, start, end, weekdays, set:{price?, price_delta_percent?, price_delta_amount?, min_los?, max_los?, cta?, ctd?, stop_sell?}}` → `{updated, audit_event_id}`.
- `POST quote/` → `Quote.to_dict()` (herramienta de prueba del staff).
- `GET holidays/?year=` (librería `holidays`, país CO).

**Frontend:** `/app/rates`: grilla categorías × fechas (14/30/60), selector de plan, filas por categoría (disponibilidad, precio editable en celda con Enter/Tab, min LOS, CTA/CTD/stop-sell como toggles compactos), fines de semana y festivos marcados, barra de edición masiva en panel lateral (rango, días de semana, campos), deshacer última edición (llama al undo genérico `POST /api/v1/control/audit/{id}/undo/` y, si aún no existe, muestra la acción deshabilitada), leyenda de `source`. `/app/rates/plans`: árbol base → derivados, editor, temporadas (lista + calendario anual simple), precios por defecto por categoría (base, ajustes por día, extras, ocupación sencilla). `/app/rates/promos`. `/app/settings/{taxes,policies,extras}`.

**Tests obligatorios:** todo el algoritmo de `quote` (un test por regla: defaults, DOW, temporada vs default, prioridad de temporada, manual vs temporada, derivado % y monto, extra adulto, límite de edad de niño, ocupación sencilla, promo válida/vencida/plan no permitido/usos agotados, stop_sell, CTA, CTD, min/max LOS, impuesto excluido, incluido, exención extranjero, redondeo COP, dorm por cama, suma multi-noche); `set_daily_rates` (crea filas completas, filtro de días, delta %, derivado prohibido, `rates_changed` con ids y rango, audit reversible y undo); validaciones de planes; API grid/bulk; permisos (front_desk ve pero no edita); aislamiento. Frontend: edición en celda, panel masivo (payload correcto con MSW).

**Seed:** por propiedad, IVA 19% (`included_in_price=False`, `exempt_foreign_non_residents=True`, `applies_to=room`) + IVA 19% para extras (`applies_to=extras`, sin exención); políticas "Flexible 48h" (gratis hasta 48 h, luego primera noche) y "No reembolsable"; planes Tarifa flexible (base), No reembolsable (−12%), Con desayuno (+35.000, `breakfast`); defaults (Aurora: DBL 320.000 / SUP 420.000 / STE 650.000, fin de semana +15%, adulto extra 60.000, niño 30.000; Andino MDE: 260.000 / 340.000 / 420.000; Hostel: cama 6 → 65.000, cama 8 → 55.000, femenino 70.000, privada doble 180.000, familiar 260.000); temporadas "Alta fin de año" (15 dic–15 ene, +30%) y "Semana Santa" con `SeasonRate`; extras (Desayuno 35.000 por persona-noche, Parqueadero 25.000 por noche, Late check-out 80.000 por estadía, Traslado aeropuerto 90.000 por estadía); promo `BIENVENIDA10` (10%); algunas restricciones de ejemplo (min LOS 2 los sábados de temporada alta).

**Aceptación:** spec §5 B2a.

---

### Task B2b: Motor de reservas (backend)

**Owner paths:** `backend/apps/bookings/**`, `docs/integration-notes/B2b-bookings.md` (sin frontend).

**Consumes:** `rates.services.quote.quote` (usa la firma; en tests puedes crear `RoomTypeRateDefaults` para que el quote simple de la Fase A funcione mientras B2a trabaja), `finance.services` (folio, cargos, balance), `guests.services.upsert_guest`, `inventory.services.set_housekeeping_status`, `core`.
**Produces:** todo lo de bookings en §4.2 y §C, API de reservas, calendario, disponibilidad y ofertas, receivers y automatizaciones.

**Inventario:**
- `rebuild_inventory(property, start, end, room_type_ids=None)`: `total_units` = habitaciones activas (private) o camas activas en habitaciones activas (dorm); `blocked_units` = bloqueos activos (`released_at is null`) que cubren la fecha (bloqueo de habitación dorm = todas sus camas; bloqueo de cama = 1); `sold_units` = stays activas que cubren la fecha (dorm: 1 por stay). Idempotente.
- Horizonte por defecto: hoy−7 → hoy+540.
- Receiver de `inventory_changed` → `rebuild_inventory` del rango (o del horizonte).
- Cada operación de reserva ajusta `sold_units` en la misma transacción bloqueando filas con `select_for_update()` en orden `(room_type_id, date)`; si faltan filas, primero `rebuild_inventory` del rango.
- Automatización `bookings.inventory_reconcile` (diaria 04:00): recalcula y, si hubo deriva, levanta alerta `inventory_drift`.

**Servicios (normativo):**
- `availability`: `min(available)` por categoría sobre las noches, desde `InventoryDay`.
- `search_offers`: categorías activas con capacidad (private: adultos ≤ max_adults, niños ≤ max_children, total ≤ max_occupancy; dorm: `units_needed = adults+children`) × planes activos aplicables (`room_types` contiene la categoría y `channel` ∈ `plan.channels` o `channels` vacío; `channel="direct"` incluye no públicos; otros canales solo `is_public`) → `quote` → incluir si `restrictions_ok` y `available ≥ units_needed`. Orden: total ascendente.
- `create_reservation`: todo en `transaction.atomic()`. Pasos: `upsert_guest` del booker; por stay valida capacidad, bloquea inventario, verifica disponibilidad (salvo `allow_overbooking` → alerta `overbooking`), cotiza (usa `nightly_rates` si vienen del canal) y aplica restricciones si `enforce_restrictions` (OTA: `False`). Crea `Reservation` (código único con reintento), `Stay`s con `nightly_rates` = `[{date, amount}]` (total por noche incl. impuestos no incluidos prorrateados; documenta la fórmula) y `total_amount`. Asigna habitación/cama si viene (`assign_room`). Guarda el snapshot de la política de cancelación. Si es `tentative` → `hold_expires_at = now + hold_minutes`. Crea el folio (`get_or_create_folio`). `audit.record`. `send_on_commit(reservation_created)` e `inventory_changed`.
- `modify_stay`: libera y toma inventario atómicamente, recotiza si `reprice`, desasigna la habitación si cambia la categoría o si la habitación ya no está libre en las nuevas fechas, actualiza los totales de la reserva, `reservation_updated` con `changes`.
- `cancel_reservation`: penalidad según el snapshot (no reembolsable → total; `free_until_hours_before` respecto a `checkin_date` + `property.check_in_time` en la zona de la propiedad; `first_night` / `percent` / `full`); `waive_fee` → 0 (el permiso se valida en la API); si fee > 0 → `post_charge(kind="cancellation_fee")`; libera inventario; `reservation_cancelled`.
- `assign_room`: valida categoría (si difiere exige `force` y registra upgrade), habitación activa, sin bloqueo en el periodo; `IntegrityError` de exclusión → `AvailabilityError("La habitación ya está ocupada en esas fechas")`; `audit.record(action="bookings.room_assigned", reversible=True, undo_data={"stay_id", "old_room_id", "old_bed_id"})`; registra el undo; `room_assigned`.
- `auto_assign_rooms`: stays sin habitación con llegada en el rango (no `locked_room`, no `checked_in`). Prioridad: VIP → grupos → estadías más largas. Candidatas libres en todo el periodo. Preferencias: (a) limpia/inspeccionada si la llegada es hoy, (b) mismo piso para el grupo, (c) menor fragmentación (preferir habitaciones cuyo hueco anterior o posterior sea 0 noches). Dorm por camas. Levanta alerta si quedan sin asignar para hoy.
- `check_in`: exige estado `confirmed` (o `tentative` con force), `checkin_date <= business_date` (si es anterior a hoy exige force) y habitación asignada (si falta intenta auto-asignar; si no puede → `InvalidStateError`); la habitación debe estar `clean` o `inspected` (si no → `RoomNotReadyError`, salvo force). Estado `checked_in`, `checked_in_at`, reserva `checked_in`, `stay_checked_in`.
- `check_out`: exige `checked_in`; si es salida anticipada ajusta `checkout_date` a `business_date` (libera noches futuras); `post_room_charges(until_date=checkout_date)`; si `reservation_balance > 0` y no force → `BalanceDueError(amount=…)`. Estado `checked_out`, `set_housekeeping_status(room, "dirty", source="automation")`, reserva `checked_out` cuando todas las stays salieron, `stay_checked_out`.
- `mark_no_show`: reserva `confirmed` con `checkin_date < business_date` sin check-in → `no_show`, libera inventario, cargo por no-show según la política (por defecto primera noche), `reservation_no_show`.
- `post_room_charges`: por noche `< until_date` sin cargo `room` no anulado → `post_charge(kind="room", amount=neto, tax=IVA de alojamiento, tax_exempt=booker.is_foreign_non_resident, night_date=noche, stay=stay, business_date=noche)`. Neto = monto de la noche sin impuesto (si el impuesto está incluido, `monto/(1+rate)`). Idempotente.
- Receiver `payment_received`: si la reserva está `tentative` y el pago está aprobado → `confirmed`, limpia hold, `reservation_updated(changes={"status": ("tentative","confirmed")})`.
- Automatizaciones: `bookings.auto_assign_rooms` (06:00, hoy y mañana), `bookings.release_expired_tentative` (cada 15 min: cancela sin cargo, `source="automation"`) y `bookings.inventory_reconcile`.

**API** (`/api/v1/bookings/`):

| Método y path | Permiso | Notas |
|---|---|---|
| `GET reservations/` | bookings.view | filtros: `status`, `source`, `channel_code`, `arrival_from/to`, `departure_from/to`, `in_house_on`, `room_type`, `unassigned=1`, `balance_due=1`, `q` (código, nombre, email, teléfono, external_id); orden |
| `POST reservations/` | bookings.manage | cuerpo = `ReservationRequest` en JSON (booker como objeto GuestInput o `booker_id`); 409/400 con `code` |
| `GET/PATCH reservations/{id}/` | view/manage | detalle: stays (con room, bed, rate plan, nightly_rates), booker, occupants, balance, folio_id, policy snapshot, `portal_url`, flags (`ready_for_checkin`) |
| `POST reservations/{id}/cancel/` | bookings.cancel (+waive_fee si aplica) | `{reason, waive_fee, confirm:true}`; GET `.../cancel-preview/` → fee |
| `POST reservations/{id}/confirm/` · `no-show/` | manage | |
| `POST stays/{id}/modify/` · `assign/` · `unassign/` | manage | `assign`: `{room_id, bed_id?, force?}` |
| `POST stays/{id}/check-in/` · `check-out/` | bookings.checkin (+checkout_with_balance si force) | |
| `POST/DELETE stays/{id}/occupants/` | manage | |
| `GET availability/?checkin&checkout` | view | `{room_type_id: units}` |
| `GET offers/?checkin&checkout&adults&children&channel` | view | lista de Offers serializados |
| `GET calendar/?start&end` | view | `{room_types:[{id,name,color,kind, rooms:[{id,number,floor,housekeeping_status, beds:[{id,label}]}]}], stays:[{id, reservation_id, code, status, source, channel_code, guest_name, room_id, bed_id, room_type_id, checkin, checkout, adults, children, balance_due, is_vip}], blocks:[{id, room_id, bed_id, start, end, kind, reason}], availability:{room_type_id:{date:units}}}` |
| `POST auto-assign/` | manage | `{date_from, date_to}` → AssignmentReport |
| CRUD `groups/` | manage | |
| `POST inventory/rebuild/` | manage | |

**Tests obligatorios:** disponibilidad decrementa y restaura; **concurrencia** (`@pytest.mark.django_db(transaction=True)`, dos hilos por la última unidad → uno `AvailabilityError`); exclusión (`assign_room` doble → `AvailabilityError`); camas de dorm individuales; restricciones (min LOS → `RestrictionError`); OTA sin restricciones pero con disponibilidad (y overbooking con alerta si `allow_overbooking`); modify fechas recotiza y mueve inventario; cancelación (ventana gratis, primera noche, no reembolsable, waive); no-show libera y cobra; check-in con habitación sucia → `RoomNotReadyError` (force OK); check-in auto-asigna; check-out publica cargos, exige saldo 0 y marca sucia; salida anticipada; auto-assign (prefiere limpias, respeta locked, agrupa por piso, minimiza huecos); `payment_received` confirma tentativa; expiración de tentativas; `rebuild` = incremental tras una secuencia aleatoria de operaciones; bloqueo reduce disponibilidad (vía receiver); señales on_commit; API (filtros, errores 409/400 con code, permisos, aislamiento); calendario (forma exacta).

**Seed** (después de guests; usa `ctx.rng`): reservas de −60 a +90 días con ocupación realista (55–85%, más alta los fines de semana y en temporada), estados coherentes con la fecha (pasadas → `checked_out`, algunas `no_show`/`cancelled`; en curso → `checked_in` con cargos publicados hasta ayer; futuras → `confirmed`/`tentative`), fuentes mezcladas (front_desk, phone, booking_engine, marketplace, ota con `channel_code` `booksim`/`airsim`), grupos (1–2), dorms con camas, huéspedes VIP, llegadas de hoy (algunas con habitación limpia y lista, otras sin asignar) y salidas de hoy. Usa los servicios de contrato (no inserts directos) excepto para ajustar estados históricos con los servicios `check_in`/`check_out` bajo `freezegun` o con `force`.

**Aceptación:** spec §5 B2b.

---

### Task B3: Huéspedes (CRM), usuarios y roles

**Owner paths:** `backend/apps/guests/**`, `backend/apps/accounts/**` (Fase A ya creó auth; B3 agrega usuarios/roles/invitaciones sin romper los endpoints existentes), `frontend/src/features/guests/**`, `frontend/src/features/team/**`, `docs/integration-notes/B3-guests-team.md`.

**Produces:** servicios de guests de §C completos, API/UI de CRM, `GuestPicker` exportable, API/UI de usuarios, roles e invitaciones.

**Guests API** (`/api/v1/guests/`, scoped por organización con `OrganizationScopedMixin`):
- CRUD `guests/` con búsqueda `q` (nombre, email, teléfono, documento), filtros (`is_vip`, `nationality`, `tag`, `has_stays`) y `stats` en el detalle (estancias, noches, gasto total, última estancia, próxima).
- `guests/{id}/stays/` (historial), `guests/{id}/documents/` (multipart), `GET guests/{id}/duplicates/`, `POST guests/merge/` `{primary_id, duplicate_id, confirm}` (`guests.merge`).
- `GET guests/{id}/export/` (JSON, `guests.export`) y `POST guests/{id}/anonymize/` `{confirm}` (Habeas Data).

**Reglas:**
- `upsert_guest` normaliza: nombres en title case, email en minúsculas, teléfono E.164 con `phonenumbers` (región CO por defecto), documento sin puntos ni espacios.
- `find_duplicates`: mismo documento; mismo email; o mismo teléfono + apellido similar.
- `merge_guests`: reapunta **genéricamente** todas las relaciones (`Guest._meta.related_objects`: FK y M2M, incluidas las de apps de la Fase C), fusiona campos vacíos, marca `merged_into`, audit. Los huéspedes fusionados no aparecen en listados.

**Accounts API (B3 agrega):**
- `GET/POST users/` (lista miembros; POST invita: `{email, role_id, all_properties, property_ids}` → `Invitation` + email con Django `send_mail` a Mailpit con link `${FRONTEND_URL}/invite/<token>`).
- `PATCH users/{membership_id}/` (rol, propiedades, activo).
- CRUD `roles/` (los de sistema son de solo lectura; `POST roles/{id}/duplicate/`).
- `GET permissions/` (catálogo agrupado por app con labels ES/EN).
- `GET invitations/` · `POST invitations/{id}/resend/` · `DELETE invitations/{id}/`.
- Público: `GET /api/v1/public/accounts/invitations/<token>/` y `POST .../accept/` `{full_name, password}` (crea o vincula el usuario, inicia sesión).
- Protecciones: no quitar ni degradar al último `owner`; nadie crea ni asigna un rol con permisos que él mismo no tiene; permisos `accounts.users_manage` / `accounts.roles_manage`.

**Frontend:** `/app/guests` (DataTable con búsqueda, filtros y VIP), `/app/guests/:id` (encabezado con badges, pestañas Resumen · Estancias · Documentos · Notas y preferencias + extensiones `useGuestTabs()`, banner de duplicados → asistente de fusión con comparación lado a lado, exportar, anonimizar con `DangerConfirmDialog`), diálogo crear/editar con selector de país ISO y tipo de documento. **Exporta** `features/guests/components/GuestPicker.tsx` (`value`, `onChange(guest | GuestInput)`, búsqueda con debounce, "Crear nuevo" en línea, aviso de posible duplicado). `features/team`: `/app/settings/users` (lista, invitar, cambiar rol y propiedades, desactivar), `/app/settings/roles` (lista + editor con matriz de permisos agrupada por módulo y "seleccionar todo por módulo"), `/invite/:token` (página pública de aceptación).

**Tests:** normalización y upsert por documento/email; duplicados; merge reapunta FK y M2M de otras apps (usa `Reservation.booker` y `Stay.occupants`) y marca `merged_into`; anonimizar; export; permisos y aislamiento (huéspedes de otra org invisibles); invitación → aceptar → login; último owner protegido; escalamiento de permisos bloqueado; catálogo. Frontend: GuestPicker (buscar, crear nuevo), matriz de permisos.

**Seed** (`guests` antes de `bookings`): ~180 huéspedes por organización (65% colombianos con CC y ciudades reales, 35% extranjeros con pasaporte de US, ES, FR, DE, BR, AR, MX, CA, GB con residencia en su país), 5% VIP, tags ("frecuente", "corporativo", "luna de miel"), consentimientos, algunos duplicados intencionales para demo de fusión.

**Aceptación:** spec §5 B3.

---

### Task B4: Finanzas y pagos

**Owner paths:** `backend/apps/finance/**`, `frontend/src/features/finance/**`, `docs/integration-notes/B4-finance.md`.

**Consumes:** `core` (integrations, signals, audit), modelos de bookings (lectura).
**Produces:** todos los servicios de finance (§4.2, §C), proveedores `payments` (`real` = Wompi, `simulated`), webhooks, página de pago simulada, `FolioPanel`, caja.

**Proveedores** (`apps/finance/providers.py`, registrados para `kind="payments"`):
- Interfaz `PaymentProvider(BaseProvider)`: `create_checkout(intent) -> dict` (`{"checkout_url": ...}`), `fetch_status(intent) -> dict` (`{"status", "method", "provider_reference", "payload"}`), `parse_webhook(request) -> dict | None` (valida la firma y devuelve `reference`/`status`), `refund(payment, amount) -> dict`.
- `WompiProvider` (`mode="real"`). `CONFIG_FIELDS`: `environment` (sandbox|production), `public_key`, `private_key` (secret), `integrity_secret` (secret), `events_secret` (secret). Base URL `https://sandbox.wompi.co/v1` o `https://production.wompi.co/v1`. Checkout Web `https://checkout.wompi.co/p/` con `public-key`, `currency=COP`, `amount-in-cents`, `reference`, `signature:integrity` = SHA256(`reference + amount_in_cents + currency + integrity_secret`) y `redirect-url`. Estado: `GET /transactions?reference=<ref>` (Bearer private key). Webhook `transaction.updated`: checksum SHA256 de los valores de `signature.properties` + `timestamp` + `events_secret`, comparado con `signature.checksum`. Mapea `APPROVED/DECLINED/VOIDED/ERROR/PENDING` y el método (`CARD`, `PSE`, `NEQUI`, ...). Verifica los detalles actuales en la documentación oficial (`https://docs.wompi.co`) con WebFetch antes de implementar y documenta lo que encontraste en tus notas. Reembolso: si Wompi no soporta reembolso vía API para el método, marca `Refund.status="pending"` con instrucción manual y alerta.
- `SimulatedPaymentProvider` (`mode="simulated"`): `checkout_url = f"{FRONTEND_URL}/sim/pay/{reference}"`; el estado lo decide la página simulada.
- Público: `GET /api/v1/public/finance/sim/intents/<reference>/` (monto, propiedad, estado, return_url) y `POST .../decide/` `{outcome: approved|declined|expired, method: card|pse|nequi}` (solo si el intent es `simulated`); `GET /api/v1/public/finance/intents/<reference>/status/` (dispara `sync_payment_intent` y devuelve el estado; lo usan las páginas de retorno); `POST /api/v1/public/finance/webhooks/wompi/`.
- `sync_payment_intent`: idempotente; al aprobar crea **un solo** `Payment` (único por `provider_reference`) vía `record_payment`, que emite `payment_received`.
- Automatización `finance.sync_pending_intents` (cada 5 min): intents `pending`/`created` < 24 h; vencidos → `expired`.

**Servicios (reglas):**
- `void_charge` y `refund_payment` exigen `confirm=True` (si no → `ConfirmationRequired`).
- Reembolso ≤ pago − reembolsos previos.
- Toda operación → `audit.record`.
- Pago en efectivo: exige turno de caja abierto del usuario si `property.settings.get("require_cash_shift", True)` (error `cash_shift_required`).
- Receiver `stay_checked_out`: si todas las stays salieron y el saldo es 0 → cierra folios y emite `folio_closed`.

**API** (`/api/v1/finance/`):
- `GET folios/?reservation=` y `GET folios/{id}/` (cargos, pagos, reembolsos, totales: `charges_total`, `tax_total`, `payments_total`, `refunds_total`, `balance`, `reservation_balance`).
- `POST folios/{id}/charges/` (`finance.collect`; acepta `{extra_id, quantity}` o `{kind, description, amount, quantity, tax_id}`) y `POST charges/{id}/void/` `{reason, confirm}` (`finance.void`).
- `POST folios/{id}/payments/` (`finance.collect`; manual: `cash`, `card_terminal`, `bank_transfer`, `other`) y `POST payments/{id}/refund/` `{amount, reason, confirm}` (`finance.refund`).
- `POST folios/{id}/payment-link/` `{amount, send_via?: ["email","whatsapp"]}` → intent + `checkout_url` (si hay `send_via` llama a `messaging.send_message(template_code="payment_link")`).
- `GET intents/`.
- `GET cash-shifts/current/`, `POST cash-shifts/open/` `{opening_float}`, `POST cash-shifts/{id}/close/` `{counted_cash, notes}` (calcula `expected_cash` y `difference`), `GET cash-shifts/` (historial, `finance.cashier`).
- `GET summary/?date=` (pagos por método del día).

**Frontend:**
- `features/finance/components/FolioPanel.tsx` (**exportado**, prop `reservationId`): tabla de cargos (neto, IVA, total, anulados tachados), pagos y reembolsos, saldo grande; acciones agregar extra/cargo, registrar pago manual, enviar link de pago (muestra link y QR), anular (DangerConfirm con motivo), reembolsar (DangerConfirm escribiendo el monto).
- `reservation-tabs.tsx` exporta la pestaña "Folio".
- `/app/cashier`: turno actual (abrir/cerrar con arqueo por denominaciones opcional), movimientos del turno, historial.
- `/sim/pay/:reference` (bare): pasarela simulada con banner "Modo simulación", monto, hotel, selector Tarjeta / PSE / Nequi con formularios falsos y botones Aprobar / Rechazar / Expirar; al decidir redirige a `return_url`.
- Exporta `PaymentStatusBadge`.

**Tests:** matemática de saldo (neto+IVA, exento, pagos, reembolsos, anulados); `reservation_balance` antes y después de publicar cargos (sin doble conteo); void/refund exigen confirm y permiso; reembolso excedido → error; firma de integridad Wompi con vector conocido; checksum de webhook válido/inválido; sync idempotente con webhooks repetidos (respx); flujo simulado approve/decline; expiración; `payment_received` emitido; cierre de folio al checkout con saldo 0; caja (esperado vs contado); efectivo sin turno → error; permisos; aislamiento. Frontend: FolioPanel (registrar pago, anular con confirmación), página simulada.

**Seed:** pagos para reservas pasadas (efectivo, datáfono, wompi_card simulados), depósitos en futuras (30–50%), algunas con saldo pendiente y un turno de caja abierto para `recepcion@casaaurora.co`.

**Aceptación:** spec §5 B4.

---

### Task B-INT: Integración de la Fase B

Agente con permiso sobre todos los paths de la Fase A y B:
- [ ] Aplica los "cambios requeridos" de las notas B1–B4 en archivos compartidos.
- [ ] `docker compose run --rm backend python manage.py makemigrations --check` sin cambios pendientes; `migrate` limpio en una BD nueva.
- [ ] `seed_demo --reset` completo con datos coherentes (reservas con cargos, pagos, disponibilidad consistente: `rebuild_inventory` no cambia nada).
- [ ] Suite backend completa verde; frontend `typecheck`, `lint`, `test` y `build` verdes.
- [ ] Smoke por el proxy: login → rooms, grid de tarifas, crear reserva por API, folio, pago simulado.
- [ ] Notas en `docs/integration-notes/B-INT.md`.

---

# FASE C — Funcionalidades

> Todas en paralelo. Antes de empezar, lee las notas A1, A2, B1–B4 y B-INT para conocer las APIs reales. Cada tarea: backend en su app, frontend en su feature y seed en su `seed.py`.

### Task C1: Recepción (frontdesk)

**Owner paths:** `backend/apps/frontdesk/**`, `frontend/src/features/frontdesk/**`, `docs/integration-notes/C1-frontdesk.md`.

**Backend:**
- `GET /api/v1/frontdesk/today/` (`frontdesk.view`): `{business_date, kpis:{occupancy_pct, rooms_occupied, rooms_available, arrivals_total, arrivals_done, departures_total, departures_done, in_house, revenue_today, adr_today}, arrivals:[{reservation_id, stay_id, code, guest_name, is_vip, room, room_status, eta, balance_due, online_checkin_done, ready, issues:[…]}], departures:[…], in_house:[…]}`. `online_checkin_done` se lee de `guestportal.OnlineCheckin` si el modelo existe (import protegido; si no, `false`).
- Modelo `NightAuditReport(property, business_date [único], started_at, finished_at, status, summary JSON, run)`.
- Automatización `frontdesk.night_audit` (02:00): (1) no-shows de llegadas `< nueva fecha` sin check-in si `property.settings.auto_no_show` (default True), (2) `post_room_charges` de in-house hasta el día siguiente a la `business_date` actual, (3) alertas de salidas vencidas sin check-out, (4) `business_date += 1`, (5) reporte. Idempotente por fecha.
- `GET night-audit/preview/` (qué haría) y `POST night-audit/run/` (`frontdesk.night_audit`); `GET night-audit/reports/`.

**Frontend:**
- `/app` "Hoy": saludo + fecha de negocio; KPIs; listas Llegadas / Salidas / En casa con acciones de 1–2 clics; `CheckInDialog` (verifica datos del huésped, elige habitación mostrando primero las limpias de su categoría, estado de check-in online, cobro de saldo con `FolioPanel` compacto o link, confirmar); `CheckOutDialog` (resumen de folio, pagar saldo, confirmar; bloquea si hay saldo salvo permiso); zona de widgets `useWidgets()`; accesos rápidos (Nueva reserva, Walk-in). Si el usuario no tiene `frontdesk.view` pero sí `housekeeping.work` → redirige a `/app/housekeeping/mine`.
- `/app/reservations`: DataTable con filtros y vistas rápidas (Llegadas hoy, Salidas hoy, En casa, Sin pagar, Sin asignar, Tentativas), búsqueda y export CSV.
- `/app/reservations/new?checkin&checkout&room_id&room_type_id`: asistente de 5 pasos (fechas y huéspedes → ofertas con desglose → huésped con `GuestPicker` → extras y notas → garantía/pago: ninguna, pago manual o link de pago) con modo Walk-in (llegada hoy + check-in inmediato).
- `/app/reservations/:id`: encabezado (código, estado, fuente/canal, fechas, huésped, saldo), tarjetas de stays (asignar habitación, check-in/out, modificar fechas con recotización visible, mover), pestañas (Resumen, Huéspedes) + `useReservationTabs()` (Folio de B4, y las de C5/C6/C7/C12), menú de acciones propio (cancelar con vista previa de penalidad, no-show, confirmar) + `useReservationActions()`.
- `/app/night-audit`: último reporte, vista previa, ejecutar.
- `commands.ts`: "Nueva reserva", "Buscar reserva por código".

**Tests:** números de `today` con fixtures exactos; night audit (cargos una sola vez, no-shows, avance de fecha, idempotencia, reporte); permisos. Frontend: CheckInDialog (flujo feliz y habitación sucia), validación de pasos del asistente, detalle con tabs de extensión (mock).

**Seed:** `NightAuditReport` de los últimos 30 días.

---

### Task C13: Calendario

**Owner paths:** `frontend/src/features/calendar/**`, `docs/integration-notes/C13-calendar.md` (solo frontend; si necesitas otro endpoint, descríbelo en las notas).

**Frontend `/app/calendar`:**
- Barra superior: navegación de fechas, rango 7/14/30, Hoy, filtros por categoría y estado, búsqueda.
- Grilla: columna izquierda categorías (colapsables) → habitaciones → camas (dorm). Días con fines de semana y festivos (`GET /api/v1/rates/holidays/`) sombreados y línea de hoy. Fila "Sin asignar" por categoría. Fila de disponibilidad y precio por categoría (`bookings/calendar` + `rates/grid`).
- Barras de reserva coloreadas por estado (tokens `--status-*`), con nombre, noches e íconos (VIP, saldo pendiente, canal). Bloqueos rayados.
- Interacciones con @dnd-kit:
  - Arrastrar vertical a otra habitación → `assign` (si cambia de categoría: diálogo "cambiar categoría y recotizar" → `modify` + `assign`).
  - Arrastrar horizontal → `modify` fechas.
  - Estirar el borde derecho → extender o acortar.
  - Arrastrar sobre celdas vacías → diálogo de creación rápida (o ir al asistente con parámetros).
  - Clic → panel lateral con resumen y acciones (check-in/out, abrir detalle).
  - Actualización optimista con rollback y toast ante 409/400.
- Virtualización de filas (TanStack Virtual) para 100+ unidades.
- Accesible por teclado y responsive: en móvil scroll horizontal, tocar barra → panel con acción "Mover".
- Utilidades puras testeables: `layout.ts` (posición y ancho de barras, recorte al rango, carriles), `dnd.ts` (traducir drop → payload API).

**Tests:** cálculos de layout (bordes de rango, checkout exclusivo), traducción de drops a payloads, rollback ante 409 (MSW), render con dorms.

---

### Task C2: Housekeeping y mantenimiento

**Owner paths:** `backend/apps/housekeeping/**`, `frontend/src/features/housekeeping/**`, `docs/integration-notes/C2-housekeeping.md`.

**Backend:**
- Modelos:
  - `HousekeepingSettings(property 1-1, stayover_frequency_days=1, require_inspection=False, auto_assign=True, minutes_per_shift=420)`.
  - `HousekeepingTask(property, room, bed null, kind[departure_clean|stayover|deep_clean|inspection|turndown|custom], status[pending|in_progress|done|inspected|cancelled], priority[low|normal|high|urgent], business_date, assigned_to null, estimated_minutes, started_at, finished_at, notes, reservation null, created_source)`.
  - `MaintenanceTicket(property, room null, title, description, priority, status[open|in_progress|resolved|cancelled], blocks_room, block null, reported_by, assigned_to null, resolved_at)`.
  - `TicketPhoto`.
- Receivers: `stay_checked_out` → tarea `departure_clean` (prioridad `high` si hay llegada hoy a esa habitación); `room_status_changed` a `dirty` sin tarea abierta → crea tarea.
- Terminar tarea de limpieza → `set_housekeeping_status(room, "clean")`; si `require_inspection` → además crea tarea `inspection`, y al inspeccionarla → `set_housekeeping_status(room, "inspected")`.
- Ticket con `blocks_room` → `block_room(kind="out_of_order")`; al resolver → `release_block`.
- Automatizaciones: `housekeeping.generate_daily_tasks` (07:00; stayovers según frecuencia y departures esperadas) y `housekeeping.auto_assign` (07:15; balancea por minutos y agrupa por piso entre usuarios con `housekeeping.work` activos en la propiedad).
- API: `tasks/` (filtros `date`, `status`, `assignee`, `mine=1`, `floor`), `tasks/{id}/start|finish|inspect|assign/`, `POST tasks/auto-assign/`, `GET board/` (habitaciones con estado, ocupación actual, próxima llegada hoy, tarea y asignado), CRUD `tickets/` + fotos, `GET/PATCH settings/`, `POST rooms/{id}/status/` (proxy validado).
- Permisos: work (solo sus tareas), supervise (todo), maintenance (tickets).

**Frontend:** `/app/housekeeping` (tablero por piso con tiles de color por estado, ícono de ocupación, badge "llega hoy", asignado; filtros; botón Auto-asignar; asignación por select; cambio rápido de estado), `/app/housekeeping/mine` (**mobile-first**: tarjetas grandes con Iniciar/Terminar, reportar daño con foto desde la cámara `<input capture>`), `/app/maintenance` (lista/tablero de tickets), `/app/settings/housekeeping`. `widgets.tsx`: progreso de limpieza del día.

**Tests:** tarea al checkout (prioridad), frecuencia de stayover, auto-asignación balanceada, terminar → limpia / inspección → inspeccionada, ticket bloquea y libera, housekeeper solo ve sus tareas, aislamiento. Frontend: vista móvil iniciar/terminar.

**Seed:** tareas de hoy (algunas en progreso, hechas o pendientes) asignadas a `limpieza@casaaurora.co`, 3 tickets (uno bloqueando habitación).

---

### Task C3: Distribución (channel manager)

**Owner paths:** `backend/apps/distribution/**`, `frontend/src/features/channels/**`, `docs/integration-notes/C3-distribution.md`.

**Backend:**
- Modelos: `ChannelConnection(property, channel_code[booksim|airsim|ical|channex], name, status[active|paused|error], settings JSON, last_sync_at, last_error)`, `RoomMapping(connection, room_type, external_room_id, ical_import_url, ical_export_token)`, `RateMapping(connection, rate_plan, external_rate_id, markup_percent)`, `AriUpdate(property, connection, room_type, rate_plan null, start, end, kinds JSON, status[pending|sent|failed], attempts, payload, response, sent_at)`, `SyncLog(connection, direction[in|out], kind, status, message, payload)`, `ExternalReservationMap(connection, external_id [único por conexión], reservation, last_payload_hash)`, `SimOtaInventory(connection, external_room_id, external_rate_id, date, available, price, min_los, stop_sell, updated_at)` y `SimOtaBooking(connection, external_id, status, payload, created_at)`.
- Proveedores (`kind` por canal): simulated OTA (BookSim/AirSim), `channel_ical` (real) y `channel_channex` (real y simulated).
- Salida: receivers de `inventory_changed` y `rates_changed` → encolan `AriUpdate` coalescido por (conexión, categoría) y unión de rangos; tarea Celery con `countdown=5` + automatización `distribution.push_ari` (cada minuto) → proveedor. Precios de planes derivados y `markup_percent` se calculan antes de enviar. Reintentos con backoff; fallo → alerta.
- Entrada: `import_booking(connection, dto)` idempotente por `external_id` con hash de payload. Nueva → `create_reservation(source="ota", channel_code, external_id, enforce_restrictions=False, allow_overbooking=True, nightly_rates del canal)` + alerta `overbooking` si faltaba disponibilidad. Modificación → `modify_stay`. Cancelación → `cancel_reservation(waive_fee=True, source="channel")`.
- iCal: `GET /api/v1/public/distribution/ical/<token>.ics` (por categoría o habitación: stays activas y bloqueos como VEVENT con UID estable). Importación periódica `distribution.pull_ical` (cada 15 min) de `ical_import_url` con httpx → VEVENTs a reservas OTA (huésped placeholder "Huésped <canal>", `external_id=UID`); eventos que desaparecen → cancelación.
- Channex: base `https://staging.channex.io/api/v1` (sandbox) con header `user-api-key`. ARI por `POST /availability` y `POST /restrictions`; reservas por `GET /booking_revisions/feed` + `POST /booking_revisions/:id/ack`. Verifica en la documentación oficial (docs.channex.io) con WebFetch y documenta. `test_connection` lista propiedades.
- API staff (`distribution.view/manage`): CRUD `connections/` con mappings anidados, `connections/{id}/test/`, `connections/{id}/full-sync/` (365 días), `connections/{id}/pause|resume/`, `logs/`, `queue/`. Simulador: `GET simulator/{connection_id}/inventory/?start&end`, `GET simulator/{connection_id}/bookings/`, `POST simulator/{connection_id}/bookings/` (crea reserva "en la OTA" → `import_booking`), `POST .../bookings/{external_id}/modify|cancel/`.

**Frontend:** `/app/channels` (tarjetas de conexión con estado, último sync y errores; asistente para agregar conexión: canal (BookSim, AirSim, Airbnb/VRBO/Booking vía iCal, Booking/Expedia vía Channex) → modo → mapeo de categorías y planes con markup → sync completo; log de sincronización filtrable; cola). `/app/simulators/ota` (selector de conexión, pestañas "Lo que ve la OTA" con grilla de ARI recibida y "Reservas de la OTA" con crear/modificar/cancelar y link a la reserva del PMS).

**Tests:** coalescencia de la cola; cálculo derivado + markup; import idempotente, modificación y cancelación; overbooking crea alerta; iCal export (VEVENTs correctos, checkout exclusivo) e import desde fixture `.ics` con cancelación por desaparición; adaptador Channex con respx (payloads); flujo del simulador de punta a punta (crear en BookSim → reserva `ota` en PMS; cambiar tarifa → `SimOtaInventory` actualizado tras push); permisos.

**Seed:** conexiones BookSim y AirSim (simuladas y mapeadas) para Aurora y Andino MDE; iCal export para el hostel; `SimOtaInventory` inicial vía full-sync; y las reservas OTA del seed de bookings vinculadas en `ExternalReservationMap`.

---

### Task C4: Marketplace y booking engine

**Owner paths:** `backend/apps/marketplace/**`, `frontend/src/features/marketplace/**`, `docs/integration-notes/C4-marketplace.md`. Excepción autorizada: C4 actualiza `Property.marketplace_listed` y `Property.branding` desde su propia API de listing.

**Backend:**
- Modelos: `BookingEngineSettings(property 1-1, enabled, primary_color, logo, hero_image, headline JSON i18n, show_promo_field, allowed_rate_plans M2M (vacío=todos públicos), min_advance_hours, max_advance_days, terms JSON i18n)` y `ListingContent(property 1-1, featured_photos M2M Photo, highlights JSON i18n, neighborhood)`.
- Público `/api/v1/public/marketplace/`:
  - `destinations/` (ciudades con propiedades listadas y conteo)
  - `search/?city&checkin&checkout&adults&children&type&min_price&max_price&amenities&stars&sort` → propiedades listadas y disponibles con la oferta más barata (total y por noche), foto destacada, amenidades principales y barrio (cache 60 s por combinación)
  - `properties/<slug>/` (info pública, fotos, amenidades, políticas, categorías con atributos efectivos típicos y fotos)
  - `properties/<slug>/offers/?checkin&checkout&adults&children&promo_code&via=marketplace|booking_engine`
  - `POST bookings/`: `{property_slug, via, checkin, checkout, items:[{room_type_id, rate_plan_id, quantity, adults, children, children_ages}], guest: GuestInput + consent, extras:[{extra_id, quantity}], promo_code, special_requests, eta, payment_option: pay_now|pay_at_hotel}`. Crea la reserva (`source` = `marketplace` o `booking_engine`); si el plan exige depósito (`deposit_percent > 0`) o `pay_now` → `tentative` + `create_payment_intent(depósito o total, return_url=f"{FRONTEND_URL}/booking/{code}/confirmed")`; si no → `confirmed`. Publica extras como cargos. Responde `{reservation_code, status, payment:{checkout_url, reference}|null, portal_url}`.
  - `GET bookings/<code>/?email=` (estado para la página de confirmación; 404 si el email no coincide).
  - `GET properties/<slug>/booking-engine/` (branding y config pública).
- Staff (`marketplace.manage`): `GET/PATCH booking-engine/`, `GET/PATCH listing/` (`marketplace_listed`, highlights, fotos destacadas, barrio), `GET embed-snippet/`.

**Frontend:**
- `/` home editorial: hero con buscador (destino combobox, rango de fechas, huéspedes), destinos destacados (Cartagena, Medellín, Bogotá, …), hoteles destacados y CTA "¿Tienes un hotel? Prueba Housetel" → `/signup`.
- `/search`: filtros en sidebar (sheet en móvil), tarjetas de resultado, orden, estado vacío.
- `/hotel/:slug`: galería, descripción, amenidades, categorías con ofertas (cantidad), políticas, ubicación (dirección + barrio), resumen sticky.
- `/book/:slug`: checkout con formulario del huésped (nacionalidad y país de residencia → muestra **automáticamente** "Exento de IVA" para extranjeros no residentes y recalcula), consentimiento Habeas Data obligatorio, extras, ETA, solicitudes especiales y opción de pago → redirige a `checkout_url`.
- `/booking/:code/confirmed`: sondea `finance/intents/<ref>/status`, muestra confirmación, link al portal y "agregar a calendario" (.ics).
- `/h/:slug`: booking engine con branding del hotel y mismo flujo (vía `booking_engine`). `/embed/:slug` (bare): widget compacto de búsqueda que abre `/h/:slug`.
- `/app/settings/booking-engine`: branding con vista previa en vivo, listing y snippet copiable.

**Tests:** búsqueda solo muestra listadas con disponibilidad; ofertas sin planes no públicos; booking crea tentativa + intent; pay_at_hotel confirma; aprobación simulada confirma la reserva (vía receiver de B2b, en test con on_commit); exención de IVA visible en totales; 409 sin disponibilidad; lookup exige email; aislamiento de settings. Frontend: buscador, validación del checkout, recálculo de exención.

**Seed:** `BookingEngineSettings` y `ListingContent` para las 3 propiedades con colores de marca propios.

---

### Task C5: Portal del huésped

**Owner paths:** `backend/apps/guestportal/**`, `frontend/src/features/guestportal/**`, `docs/integration-notes/C5-guestportal.md`.

**Backend:**
- Modelos: `GuestPortalSettings(property 1-1, checkin_opens_days_before=7, require_document_photo=True, require_signature=True, auto_approve_extras=True, terms JSON i18n)`, `OnlineCheckin(reservation 1-1, status[not_started|in_progress|completed], current_step, data JSON, signature FileField, accepted_terms_at, eta, completed_at, ip, user_agent)` y `ServiceRequest(reservation, kind[late_checkout|early_checkin|transfer|extra|other], extra null, quantity, notes, status[requested|approved|rejected|done], price, decided_by, decided_at)`.
- Público `/api/v1/public/guestportal/<token>/` (token vía `core.tokens`; inválido → 404):
  - `GET` resumen: propiedad y branding, reserva, stays, huéspedes, saldo, estado del check-in, extras disponibles, solicitudes, `can_cancel` + vista previa de penalidad.
  - `GET/POST checkin/`: pasos `guests` (datos TRA/SIRE por ocupante: nombres, tipo y número de documento, nacionalidad, país y ciudad de residencia, fecha de nacimiento, email, teléfono, motivo de viaje, procedencia y destino → `guests.services.upsert_guest`/`update_guest` + `Stay.occupants`), `documents` (multipart → `add_document(uploaded_via="portal")`), `arrival` (ETA), `signature` (PNG base64 + aceptar términos).
  - `POST checkin/complete/` (valida requeridos → `completed`, `send_on_commit(guest_checked_in_online)`).
  - `POST pay/` `{amount?}` → intent del saldo con `return_url=/g/<token>?paid=1`.
  - `GET extras/` y `POST requests/` (extras con auto-aprobación → `post_charge`; late checkout → `requested` + alerta al staff).
  - `POST cancel/` `{confirm}` (dentro de política, `source="guest"`) y `POST modify/` `{checkin, checkout}` (valida disponibilidad con ofertas, `modify_stay(reprice=True)`, devuelve el nuevo total y saldo).
- Staff: `GET checkins/?date` (estados de las llegadas), `GET reservations/{id}/checkin/` (datos, documentos, firma), `GET reservations/{id}/link/` (URL + QR PNG base64), `POST reservations/{id}/send-link/` (`send_message(template_code="checkin_invitation")`), `service-requests/` (aprobar/rechazar), `GET/PATCH settings/`.

**Frontend:** `/g/:token` (portal mobile-first con branding del hotel: tarjeta de reserva, CTA de check-in/estado, pagar saldo, extras, solicitudes, factura (usa el endpoint de C7 si responde; si 404 lo oculta), cancelar/modificar, chat vía `PublicChatSlot`), `/g/:token/checkin` (stepper Huéspedes → Documentos → Llegada → Firma y términos (`signature_pad`) → Pago → Listo, con progreso guardado). Staff: `reservation-tabs.tsx` "Check-in online" (datos, imágenes de documentos, firma), `reservation-actions.tsx` "Enviar link de check-in" y "Copiar link / QR", `/app/settings/guest-portal`, `widgets.tsx` (llegadas con check-in online completado).

**Tests:** token alterado → 404; el flujo guarda ocupantes en Guest; `complete` valida y emite señal; pago crea intent; extras publican cargo; late checkout crea solicitud y alerta; cancelar con penalidad según política; modificar recotiza; staff ve datos; aislamiento. Frontend: stepper (validaciones, firma requerida).

**Seed:** check-in online completado para ~40% de las llegadas de los próximos 3 días y algunas solicitudes pendientes.

---

### Task C6: Mensajería

**Owner paths:** `backend/apps/messaging/**`, `frontend/src/features/messaging/**`, `docs/integration-notes/C6-messaging.md`.

**Backend:**
- Modelos: `MessageTemplate(organization, property null, code, channel[email|whatsapp], language[es|en], subject, body, is_active)` (único `property, code, channel, language`), `Conversation(property, guest null, reservation null, channel, external_thread_key, status[open|closed], last_message_at, unread_count, assigned_to null)`, `Message(conversation, direction[in|out], channel[email|whatsapp|web_chat|ota|internal_note], sender_label, body, subject, status[queued|sent|delivered|read|failed|received], provider_message_id, error, template_code, sent_by null, ai_generated)`, `LifecycleRule(property, event[confirmation|pre_arrival|arrival_day|post_stay|payment_reminder|cancellation], enabled, days_offset, channels JSON, template_code)` y `LifecycleDispatch(reservation, event)` único.
- `send_message` real: resuelve la plantilla (propiedad → org → default del sistema) en el idioma del huésped; renderiza `{{variables}}` con un renderer propio seguro (`guest.first_name`, `guest.full_name`, `reservation.code`, `reservation.checkin`, `reservation.checkout`, `property.name`, `property.phone`, `portal_url`, `checkin_url`, `payment_url`, `balance`, `nights`); por canal obtiene el proveedor y envía; crea o reutiliza la `Conversation` y guarda `Message`. Email real = `EmailMultiAlternatives` (HTML con layout Housetel + texto plano) al SMTP del entorno (Mailpit); email simulado = solo guarda. WhatsApp real = Meta Cloud API (`POST https://graph.facebook.com/v21.0/{phone_number_id}/messages`, Bearer token; fuera de la ventana de 24 h usa plantilla aprobada configurada; verifica la versión actual en la documentación de Meta con WebFetch); WhatsApp simulado = guarda con estado `delivered`.
- Webhook WhatsApp real: `GET/POST /api/v1/public/messaging/webhooks/whatsapp/` (verify token + firma `X-Hub-Signature-256` con app secret) → mensaje entrante.
- Simulador: `POST /api/v1/messaging/simulator/whatsapp/inbound/` `{phone, body}` (staff, `messaging.send`) → busca el huésped por teléfono (o crea uno "Contacto WhatsApp") → conversación → `Message(in)`. `GET /api/v1/messaging/simulator/whatsapp/thread/?phone=` devuelve la conversación para la UI tipo teléfono.
- Receivers: `reservation_created` (si `confirmed`) y `reservation_updated` (a `confirmed`) → confirmación; `reservation_cancelled` → cancelación. Todo idempotente vía `LifecycleDispatch`.
- Automatización `messaging.lifecycle_dispatch` (cada 10 min): `pre_arrival` (checkin − offset días, a partir de las 9:00), `arrival_day`, `post_stay` (checkout + offset) y `payment_reminder` (saldo > 0 y llegada en ≤ offset días).
- API staff: `conversations/` (filtros: unread, channel, assigned, reservation, guest), `conversations/{id}/messages/` (GET; POST responde por el canal de la conversación o nota interna), `conversations/{id}/read|assign|close/`, CRUD `templates/` + `POST templates/preview/`, `lifecycle-rules/`, `GET variables/`.

**Frontend:** `/app/inbox` (lista de conversaciones con filtros y no leídos; hilo con burbujas por canal; compositor con insertar plantilla y "Borrador IA" que llama `POST /api/v1/ai/draft-reply/` y se oculta si responde 404; sidebar con contexto de reserva), `reservation-tabs.tsx` y `guest-tabs.tsx` "Mensajes", `/app/settings/messaging` (editor de plantillas ES/EN con variables y vista previa, reglas del ciclo con toggles y offsets), `/app/simulators/whatsapp` (mockup de teléfono: elegir huésped por teléfono, escribir como huésped, ver respuestas en vivo por polling), `topbar.tsx` (ícono de bandeja con no leídos).

**Tests:** render de plantillas (variables faltantes → vacío seguro, escape HTML en email); `send_message` por canal (email con backend locmem); adaptador WhatsApp real (respx) y webhook (verify + firma); simulador inbound vincula huésped por teléfono; idempotencia del ciclo; confirmación al confirmar reserva; idioma por huésped; permisos y aislamiento. Frontend: compositor con plantilla, simulador de WhatsApp.

**Seed:** plantillas por defecto ES/EN para todos los eventos + `checkin_invitation` + `payment_link`; reglas activas; conversaciones de ejemplo (WhatsApp y email) con mensajes entrantes sin leer.

---

### Task C7: Legal Colombia (DIAN, SIRE, TRA)

**Owner paths:** `backend/apps/compliance/**`, `frontend/src/features/compliance/**`, `docs/integration-notes/C7-compliance.md`.

**Backend:**
- Modelos: `ComplianceSettings(property 1-1, auto_issue_invoices=True, sire_establishment_code, sire_city_code, tra_establishment_id, …)`, `InvoiceResolution(property, prefix, resolution_number, from_number, to_number, current_number, valid_from, valid_to, technical_key, environment[test|production], is_active)`, `Invoice(property, reservation null, folio, number, prefix, full_number, kind[invoice|credit_note], status[draft|issued|accepted|rejected|cancelled|error], customer JSON, lines JSON, subtotal, tax_total, total, exempt_note, cufe, qr_data, xml_file, pdf_file, provider, provider_ref, provider_response JSON, related_invoice null, issued_at, error_message, attempts)`, `SireReport(property, period_start, period_end, file, status[generated|submitted|acknowledged], records_count, missing JSON, generated_at, submitted_at, ack_code)`, `SireRecord(report, guest, stay, movement[E|S], movement_date, data JSON)` y `TraRegistration(property, reservation, stay, guest, status[pending|registered|error], tra_number, payload JSON, response JSON, registered_at, error, attempts)`.
- **DIAN.** `issue_invoice(reservation|folio, *, actor)`: toma los cargos no anulados del folio; agrupa en líneas (Alojamiento N noches por categoría, cada extra, penalidades); aplica IVA 19% o exento (con nota "Exento de IVA — Art. 481 lit. d) E.T., servicios hoteleros a no residentes"); cliente = booker (o Consumidor final `222222222222`); numeración atómica con `select_for_update` sobre la resolución (valida rango y vigencia; alerta al 90% o a <30 días de vencer); envía al proveedor `einvoice`. Real (`FactusProvider`: sandbox `https://api-sandbox.factus.com.co`, OAuth2 password grant, `POST /v1/bills/validate`; verifica la documentación de Factus con WebFetch y documenta el mapeo). Simulado: CUFE = SHA-384 determinístico de los campos, `accepted`. Siempre genera un PDF con reportlab (encabezado del hotel, NIT, resolución, líneas, IVA/exento, total, QR con `qr_data`, CUFE). Nota crédito referenciando. Receiver `stay_checked_out` → si todas salieron y `auto_issue` → emitir. Automatización `compliance.issue_pending_invoices` (reintentos de `error`/`draft`).
- **SIRE.** `generate_sire(property, start, end)`: extranjeros (`nationality != "CO"`) con check-in (E) o check-out (S) en el periodo. Campos según el formato de cargue masivo de hospedaje de Migración Colombia (investiga el formato vigente con WebSearch/WebFetch; si no es concluyente, implementa el formato documentado más reciente y deja el mapeo de códigos en una tabla configurable `SIRE_DOCUMENT_TYPES`, `SIRE_COUNTRY_CODES`). Valida faltantes (lista en `missing` + alerta), archivo TXT/CSV descargable, `mark_submitted`; simulado: además genera `ack_code`. Automatización `compliance.sire_daily_file` (08:00, día anterior).
- **TRA.** Receiver `stay_checked_in` → `TraRegistration` por ocupante (booker incluido). Real: adaptador HTTP configurable al servicio de MinCIT (`CONFIG_FIELDS`: base_url, token, establishment_id; documenta lo encontrado). Simulado: `tra_number = "TRA-" + código`. Reintentos.
- Público: `GET /api/v1/public/compliance/portal/<token>/invoices/` y `/invoices/<id>/pdf/` (§C).
- Staff (`compliance.*`): CRUD `resolutions/`; `invoices/` (lista, detalle, `issue` por reserva, `retry`, `credit-note` (`compliance.void_invoice` + DangerConfirm), `pdf`, `xml`); `sire/` (`generate` `{start,end}`, lista, descarga, `mark-submitted`); `tra/` (lista, `retry`); `GET/PATCH settings/`; `GET pending/` (pendientes y faltantes).

**Frontend:** `/app/compliance` (pestañas Facturas · SIRE · TRA · Pendientes, con tablas, filtros, descargas y acciones), `reservation-tabs.tsx` "Legal" (factura y acciones, registros TRA, datos faltantes), `reservation-actions.tsx` "Emitir factura", `/app/settings/compliance` (resolución, modos real/simulado con link a integraciones, códigos SIRE/TRA), `widgets.tsx` (pendientes legales).

**Tests:** numeración secuencial y atómica (dos emisiones concurrentes → números distintos); rango agotado o vencido → error y alerta; exención en factura de extranjero; totales = folio; CUFE determinístico; PDF no vacío (bytes > 1 KB, empieza con `%PDF`); nota crédito; adaptador Factus (respx); archivo SIRE con fixture exacto (líneas esperadas); faltantes detectados; TRA al check-in (simulado) y reintento; portal invoices con token; permisos y aislamiento.

**Seed:** resolución de prueba por propiedad (prefijo `SETT`, rango 1–5000), facturas simuladas para las salidas pasadas, 1–2 reportes SIRE generados y TRA de las estadías recientes.

---

### Task C8: Revenue management

**Owner paths:** `backend/apps/revenue/**`, `frontend/src/features/revenue/**`, `docs/integration-notes/C8-revenue.md`.

**Backend:**
- Modelos: `RevenueSettings(property 1-1, enabled=True, auto_apply=False, horizon_days=120, max_daily_change_percent=20, min_change_percent=2)`, `PricingRule(property, name, kind[occupancy|lead_time|day_of_week|holiday|event], room_types M2M, params JSON, priority, combine[stack|max], is_active)`, `PriceBounds(room_type, rate_plan, min_price, max_price)`, `RevenueRun(property, started_at, finished_at, status, recommendations_count, summary, ai_summary)` y `RateRecommendation(property, run, room_type, rate_plan, date, current_price, anchor_price, recommended_price, change_percent, reasons JSON, explanation, status[pending|approved|rejected|applied|auto_applied|expired], decided_by, decided_at)`.
- Motor `compute_recommendations(property, *, start, end, persist=True)`: por categoría × plan base × fecha, el ancla = precio temporada/default (resuelto ignorando filas `source="revenue"`); aplica reglas:
  - ocupación on-the-books (`sold/total` de `InventoryDay`) por tramos `[{min,max,adjust}]`;
  - anticipación (`[{max_days, adjust}]` last-minute y `[{min_days, adjust}]` early-bird);
  - día de semana (`{"fri":5,"sat":10}`);
  - festivos CO (`holidays.CO`) y puentes (sábado–lunes festivo) con `adjust`;
  - eventos manuales `{start,end,adjust,name}`.
  - Combinación `stack` (suma) o `max`. Límites `PriceBounds`. Cambio máximo diario vs precio actual. Umbral mínimo. Razones legibles por regla.
- Explicación: plantilla determinística por recomendación + `ai_summary` del run vía `get_llm(property).generate(...)` (fallback a plantilla).
- Aplicar: `set_daily_rates(source="revenue", actor)` agrupando fechas contiguas. `auto_apply` → `auto_applied` con audit `source="automation"`. Recomendaciones de fechas pasadas → `expired`.
- Automatización `revenue.run_rules` (05:00 y cada 6 h).
- API (`revenue.view/manage`): `GET/PATCH settings/`, CRUD `rules/`, `bounds/`, `GET recommendations/?start&end&status&room_type`, `POST recommendations/approve|reject/` `{ids}`, `POST recommendations/apply/` `{ids}`, `runs/`, `POST run-now/`, `POST simulate/` (sin persistir).

**Frontend:** `/app/revenue` (KPIs: pendientes, cambio medio, impacto estimado; heatmap categoría × fecha con % recomendado (paleta divergente accesible); detalle con razones y explicación IA; aprobación/rechazo masivo; editor de reglas con constructores visuales por tipo; tabla de límites; ajustes con advertencia al activar auto-aplicar; historial de runs con resumen IA), `widgets.tsx` ("Recomendaciones de precio" con aprobar rápido).

**Tests:** tramos de ocupación; anticipación; día de semana; festivo (2026-10-12 lunes festivo en CO) y puente; stack vs max; límites; cambio máximo; umbral; aprobar → aplica con `source="revenue"` (verificar `DailyRate`); auto-apply; expiración; simulate no persiste; permisos. Frontend: aprobación masiva.

**Seed:** reglas por defecto (ocupación 0–40 → −8%, 70–85 → +8%, 85–100 → +15%; last-minute ≤3 días → −5%; sábado +8%; festivos y puentes +12%; evento "Festival de Música de Cartagena" en enero +20%), límites por categoría y un run inicial con recomendaciones pendientes.

---

### Task C9: IA (proveedores, copiloto, chatbot, onboarding, anomalías)

**Owner paths:** `backend/apps/ai/**`, `frontend/src/features/ai/**`, `docs/integration-notes/C9-ai.md`.

**Backend:**
- `llm.py` real: `get_llm(property)` según `IntegrationSetting(kind="llm")` (modo `real` → `config.provider` `gemini` (default) | `claude`; claves de plataforma desde el entorno) o simulado.
  - `GeminiClient`: `google-genai` (`genai.Client(api_key=...)`, `client.models.generate_content(model=GEMINI_MODEL, contents=..., config=types.GenerateContentConfig(system_instruction=..., tools=[types.Tool(function_declarations=[...])], response_mime_type="application/json", response_schema=..., temperature=...))`); mapea function calls a `ToolCall`. Verifica la API actual del SDK con Context7 o la documentación antes de escribir el adaptador.
  - `ClaudeClient`: SDK `anthropic`, `CLAUDE_MODEL`, tool use.
  - `SimulatedClient`: reglas por intención (llegadas, salidas, ocupación, disponibilidad, saldo, saludo) que devuelven `tool_calls` equivalentes, para que el copiloto funcione offline.
  - Errores 429/5xx/timeouts → reintento corto y luego fallback simulado + alerta `llm_degraded` (1 por día).
  - Modelo `AIUsage(property, feature, provider, model, input_tokens, output_tokens, latency_ms, success, error, created_at)`.
- **Copiloto** (`ai.copilot`):
  - Modelos `CopilotSession(user, property)`, `CopilotMessage(session, role, content, tool_calls, created_at)` y `CopilotAction(session, message, action_code, params, summary, status[proposed|executed|rejected|failed], result, executed_at)`.
  - Herramientas de lectura: `get_today_summary`, `list_arrivals`, `list_departures`, `search_reservations`, `get_reservation`, `check_availability`, `get_occupancy`, `find_guest`, `get_balance`, `list_alerts`, `get_rates`. Herramientas de acción (solo proponen): `create_reservation`, `move_room`, `check_in`, `check_out`, `send_message`, `block_room`, `add_extra`.
  - Bucle agente con máximo 5 iteraciones.
  - `POST copilot/sessions/{id}/messages/` → `{messages, proposals}`.
  - `POST copilot/actions/{id}/confirm|reject/`: al confirmar re-valida el permiso del usuario **en ese momento** y ejecuta con los servicios de contrato con audit `source="ai"`.
- **Chatbot público**: `POST /api/v1/public/ai/chat/<property_slug>/` `{session_id?, message, language}`. Modelos `PropertyFAQ(property, question, answer, language, sort)` y `ChatbotConversation(property, session_id, messages JSON, handoff_requested, contact JSON, created_at)`. Contexto: descripción, políticas, horarios, amenidades, categorías y FAQ. Herramienta `check_availability` (`search_offers(channel="booking_engine")`) → tarjetas con link a `/h/<slug>?checkin&checkout&adults`. Handoff (pide humano o baja confianza) → pide contacto → alerta `chatbot_handoff` con link. Rate limit por sesión.
- **Onboarding** (`ai.onboarding`):
  - `POST onboarding/propose/` `{description, website_url?}`: descarga el texto del sitio con httpx (timeout 8 s, máx. 20 k caracteres, sin scripts) → `response_schema` → propuesta `{property:{...}, room_types:[{code,name:{es,en},kind,base_occupancy,max_adults,max_children,beds,size_m2,amenities:[codes],units,room_numbers:[...],floor,base_price,weekend_adjust_percent}], policies, extras}`, normalizada y validada. Simulado: extrae números y palabras clave de la descripción con heurísticas.
  - `POST onboarding/apply/` (propuesta editada) → transacción con `provision_room_type` + `provision_rates` + actualización del perfil → resumen.
- **Anomalías**: automatización `ai.anomaly_scan` (cada hora) con chequeos por reglas → `raise_alert` con `dedupe_key` estable:
  - confirmada sin garantía ni pago con llegada < 48 h;
  - pagos duplicados (mismo folio, monto y método en < 10 min);
  - tarifa fuera de `PriceBounds` o < 30% del default;
  - noches in-house sin cargo tras la auditoría;
  - VIP que llega hoy con habitación sucia a < 2 h de su ETA;
  - check-in sin TRA registrado a +2 h;
  - checkout sin factura a +1 h (si auto_issue);
  - diferencia de caja > 50.000;
  - `sold_units > total_units`.
  - Automatización `ai.daily_brief` (07:30): resumen IA del día como alerta `info`.
- `POST draft-reply/` (§C, permiso `messaging.send`).
- API de settings: `GET/PATCH settings/` (proveedor preferido, features on/off), CRUD `faqs/`, `GET usage/`, `GET chatbot-conversations/`.

**Frontend:**
- `topbar.tsx`: botón "Copiloto" que abre un panel lateral (sheet) con historial, sugerencias rápidas, respuestas en markdown y **tarjetas de propuesta** con Confirmar/Rechazar.
- `commands.ts`: "Preguntar al copiloto…".
- `public-widget.tsx`: burbuja flotante → chat con tarjetas de disponibilidad y formulario de handoff; solo en rutas con `propertySlug`/`portalToken`.
- `/app/onboarding`: textarea + URL → propuesta en tablas editables (categorías, habitaciones, precios) → aplicar → resumen con links.
- `/app/settings/chatbot` (FAQ ES/EN, conversaciones).
- `/app/settings/ai` (proveedor, uso y estado; indica si está en simulado).

**Tests:** selección de proveedor y fallback en 429 (mock del cliente); forma de la petición a Gemini (mock de `genai.Client`); herramienta de lectura devuelve datos; herramienta de acción crea propuesta sin ejecutar; confirmar ejecuta y housekeeping no puede confirmar `create_reservation`; chatbot con simulado responde disponibilidad con tarjeta; handoff crea alerta; onboarding normaliza y `apply` crea entidades; cada regla de anomalía produce su alerta con fixture y respeta dedupe. **Un test marcado `@pytest.mark.live_llm`** (se salta sin `GEMINI_API_KEY` o con `-m "not live_llm"`) que llama a Gemini real con un prompt corto. Frontend: panel del copiloto con propuesta y confirmación (MSW), widget público.

**Seed:** FAQs (desayuno, parqueadero, mascotas, horarios, cómo llegar) ES/EN para las 3 propiedades y una conversación de chatbot con handoff.

---

### Task C10: Reportes

**Owner paths:** `backend/apps/reports/**`, `frontend/src/features/reports/**`, `docs/integration-notes/C10-reports.md`.

**Backend:**
- `engine.py`, un único motor de KPIs sobre la *business date*.
- Definiciones (documentadas en el código y en las notas):
  - rango `[start, end]` inclusivo en fechas de negocio;
  - `room nights sold(d)` = stays con estado `confirmed|checked_in|checked_out` que cubren `d` (checkin ≤ d < checkout);
  - `available room nights(d)` = `InventoryDay.total − blocked`;
  - `occupancy` = sold/available;
  - ingresos de alojamiento = Σ `Charge.amount` (neto) `kind="room"` no anulados con `business_date` en el rango (reales) + para fechas futuras el pronóstico = Σ `nightly_rates` netos de stays activas;
  - `ADR` = ingresos alojamiento / room nights sold;
  - `RevPAR` = ingresos alojamiento / available room nights.
  - Canceladas y no-show excluidas de sold (el fee cuenta como ingreso "otros"). Dorm: unidades = camas.
- Reportes (cada uno con endpoint JSON `GET /api/v1/reports/<id>/?start&end&compare=previous_period|previous_year&group_by` y `?format=csv|xlsx|pdf`):
  - `performance` (serie diaria de occupancy/ADR/RevPAR/ingresos + totales + comparación);
  - `revenue-by-segment` (fuente, canal, categoría, plan);
  - `pickup` (reservas creadas en los últimos N días para fechas futuras);
  - `forecast` (OTB próximos 90 días);
  - `cancellations`;
  - `booking-window` (anticipación y duración);
  - `arrivals`, `departures`, `in-house`, `no-shows` (fecha);
  - `housekeeping-status`;
  - `daily-revenue` (cargos por tipo);
  - `payments-by-method`;
  - `cash-shifts`;
  - `taxes` (base gravada, IVA, base exenta);
  - `receivables` (saldos abiertos);
  - `guests-by-nationality`.
- Permisos por categoría (`reports.operational/financial/performance`).
- Exportación: CSV (`;` + UTF-8 BOM para Excel), XLSX (openpyxl con formato) y PDF (reportlab con encabezado Housetel/propiedad).

**Frontend:** `/app/reports` (hub por categorías Rendimiento, Operación, Finanzas, Impuestos, con descripción), `/app/reports/:reportId` (rango con presets Hoy, Ayer, Esta semana, Este mes, Mes pasado, Últimos 30 días, Personalizado; comparación; tiles de KPI; gráfico Recharts siguiendo el skill `dataviz`; tabla; exportar CSV/XLSX/PDF), `widgets.tsx` (ocupación próximos 14 días).

**Tests** (fixture determinística: 10 habitaciones, stays hechas a mano): ocupación, ADR y RevPAR exactos para rangos con bordes (día de checkout no cuenta, fin inclusivo); cruce de mes; bloqueos excluidos del disponible; canceladas y no-show excluidas; cargos anulados excluidos; exento en reporte de impuestos; comparación con periodo anterior; CSV exacto (cabeceras y filas); XLSX y PDF generados; permisos y aislamiento.

---

### Task C11: SaaS y super-admin

**Owner paths:** `backend/apps/saas/**`, `frontend/src/features/saas/**`, `docs/integration-notes/C11-saas.md`. Excepción autorizada: C11 cambia `Organization.status`/`trial_ends_at` y crea organizaciones/propiedades/usuarios en el signup usando `accounts.services`.

**Backend:**
- Modelos: `Plan(code, name JSON i18n, description JSON, max_units null, max_properties null, price_monthly, price_yearly, is_active, sort)`, `Subscription(organization 1-1, plan, status[trialing|active|past_due|suspended|cancelled], billing_cycle[monthly|yearly], current_period_start, current_period_end, trial_ends_at, cancel_at_period_end, payment_source JSON, retries, next_retry_at)`, `PlatformInvoice(organization, number, period_start, period_end, lines JSON, subtotal, tax (IVA 19%), total, status[open|paid|void|failed], due_date, paid_at, payment_reference, pdf)`, `Commission(organization, property, reservation 1-1, base_amount, rate, amount, status[pending|settled|reversed], settlement null)` y `CommissionSettlement(organization, period_start, period_end, total, status[open|invoiced|paid], invoice null)`.
- Receivers: `reservation_created` / `reservation_updated` con `source="marketplace"` y estado `confirmed` → `Commission` (base = total de alojamiento neto de impuestos × `property.commission_rate`); `reservation_cancelled` → `reversed` (o recalculada sobre el fee si hubo penalidad).
- Cobro de plataforma: proveedor `saas_billing` (`property=None`): real = Wompi con las `WOMPI_PLATFORM_*` del entorno (fuente de pago tokenizada o link de pago); simulado = aprueba salvo `organization.settings.simulate_payment_failure`.
- Automatización `saas.billing_cycle` (plataforma, 03:00): trial vencido sin método → `past_due`; periodo vencido → factura (plan + IVA) → cobro → `active` y avanza el periodo, o `past_due` con reintentos días 1/3/7 → `suspended` (y `Organization.status = "suspended"`). Pago posterior → reactivación.
- Automatización `saas.commission_settlement` (día 1): liquida comisiones del mes anterior por org → líneas en la factura de plataforma.
- Límite de plan: si las unidades superan `max_units` → alerta `plan_limit` (soft, sin bloquear).
- Público: `POST /api/v1/public/saas/signup/` `{hotel_name, property_type, city, department, rooms_estimate, owner_name, email, password, phone, accept_terms}` → org (`trial`, 14 días) + propiedad (slug único) + `ensure_system_roles` + owner + subscription `trialing` (plan según unidades) + login de sesión → `{redirect: "/app/getting-started"}`. `GET /api/v1/public/saas/plans/`.
- Staff (`allow_suspended = True`): `GET billing/` (plan, estado, uso, próxima factura), `GET billing/invoices/`, `POST billing/invoices/{id}/pay/` (intent → checkout_url), `POST billing/change-plan/`, `POST billing/cancel/` (`saas.billing_manage`).
- Admin (`is_platform_admin`, sin `X-Property-Id`): `admin/metrics/` (MRR, orgs activas/trial/suspendidas, churn 30 días, GMV marketplace, comisiones del mes, serie de 12 meses), `admin/organizations/` (lista con plan, estado, unidades, propiedades, MRR y fecha; detalle con propiedades, usuarios, uso, facturas y comisiones; acciones `suspend`, `reactivate`, `extend-trial` `{days}`, `change-plan`), CRUD `admin/plans/`, `admin/invoices/`, `admin/commissions/` y `admin/settlements/`.

**Frontend:** `/signup` (público, dos columnas con beneficios; formulario en 2 pasos; al terminar → `/app/getting-started`); `/app/getting-started` (checklist con progreso real desde `inventory/summary`, `rates` y conteos: perfil, categorías y habitaciones (link a settings y a `/app/onboarding`), tarifas, pagos (integración), canales, equipo, primera reserva de prueba); `/app/settings/billing` (plan, uso vs límite, facturas, pagar, cambiar plan, cancelar); `/admin` (métricas con gráficos), `/admin/organizations` (+ detalle), `/admin/plans`, `/admin/billing` y `/admin/commissions`; banner global cuando la org está `past_due` o `suspended` (vía `topbar.tsx` o `widgets.tsx`).

**Tests:** signup crea todo e inicia sesión y el slug es único; comisión solo para marketplace confirmada; reversa al cancelar; liquidación mensual; ciclo de cobro (éxito, fallo, reintentos, suspensión con freezegun); org suspendida → 402 en API staff pero billing accesible; reactivación; admin exige platform admin; plan por unidades; alerta de límite.

**Seed:** planes Starter (≤15 unidades, 149.000/mes), Pro (≤60, 349.000), Cadena (ilimitado, 899.000; yearly −15%); suscripciones Aurora (Pro, activa) y Andino (Cadena, activa); 6 meses de facturas pagadas; comisiones de las reservas de marketplace del seed; una org extra "Hostal Demo Trial" en `trialing`.

---

### Task C12: Centro de control

**Owner paths:** `backend/apps/control/**` (solo API, sin modelos nuevos salvo que sean imprescindibles), `frontend/src/features/control/**`, `docs/integration-notes/C12-control.md`.

**Backend** (`/api/v1/control/`):
- `GET integrations/`: por cada kind de `core.integrations.KINDS` → `{kind, label, mode, enabled, status, status_message, last_checked_at, config (no secretos), secrets_configured: {campo: bool}, providers: {mode: {label, config_fields}}}`. `PATCH integrations/{kind}/` `{mode?, enabled?, config?, secrets?}` (secretos solo escritura, cifrados con `set_secrets`, nunca devueltos). `POST integrations/{kind}/test/` → `provider.test_connection()` y actualiza el estado. Permiso `control.integrations`.
- `GET automations/`: registradas (`scope=property`) con `enabled`, `params`, `schedule` legible (texto ES/EN desde el crontab), última corrida y estado. `PATCH automations/{code}/` `{enabled?, params?}`. `POST automations/{code}/run/` (síncrono si tarda <10 s, si no `.delay`; devuelve la corrida). `GET automation-runs/?code&status`. Permiso `control.automations`.
- `GET audit/?action&source&actor&target_type&target_id&start&end` y `GET audit/{id}/` (diff). `POST audit/{id}/undo/` (`control.audit_undo` + `confirm`) → `core.audit.undo`. Permiso `control.audit`.
- `GET alerts/?status=open|resolved&severity`, `POST alerts/{id}/resolve/`, `GET alerts/count/`. Permiso `control.alerts`.

**Frontend:**
- `/app/settings/integrations`: tarjeta por tipo con ícono, descripción ES/EN, estado, toggle **Real / Simulado**, formulario generado desde `config_fields` (password enmascarado con "configurado ✓") y "Probar conexión". Banner que explica el modo simulado.
- `/app/settings/automations`: tabla con toggle, horario, última corrida con badge, "Ejecutar ahora", diálogo de parámetros e historial en drawer.
- `/app/settings/audit`: línea de tiempo con filtros, diff antes/después y botón "Deshacer" (DangerConfirm) cuando `reversible && !undone_at`.
- `/app/alerts`: lista con chips de severidad, resolver y link al objeto.
- `topbar.tsx`: campana con conteo (polling 60 s) y popover de últimas alertas.
- `widgets.tsx`: alertas abiertas.
- `reservation-tabs.tsx`: "Historial" (audit filtrado por la reserva y sus stays).

**Tests:** secretos nunca en respuestas (ni en listas ni en detalle); roundtrip cifrado; cambio de modo; test_connection; toggle y run de automatización crea `AutomationRun`; undo llama al handler, marca `undone` y un segundo undo → 409; permisos por endpoint; aislamiento por propiedad. Frontend: formulario desde schema, undo con confirmación.

---

### Task C-INT: Integración de la Fase C

- [ ] Aplica los "cambios requeridos" de todas las notas C, sin romper la propiedad de módulos.
- [ ] `makemigrations --check` limpio y `migrate` desde cero.
- [ ] `seed_demo --reset` completo (todas las apps, orden `SEED_ORDER`) sin errores y con datos coherentes.
- [ ] Suite backend completa verde (excluye `live_llm`); frontend `typecheck`, `lint`, `test` y `build` verdes.
- [ ] Beat registra todas las automatizaciones de spec §6 (+ `bookings.inventory_reconcile`, `ai.daily_brief`) y el worker las ejecuta sin errores (`automation.run` manual de cada una).
- [ ] Todas las rutas del frontend de §E cargan sin error de consola (smoke con vitest render de cada página o con curl + build).
- [ ] Notas en `docs/integration-notes/C-INT.md`.

---

# FASE D — Integración final

### Task D1: Producto listo para demo

- [ ] `docker compose down -v && docker compose up -d --build && make seed` desde cero; tiempos razonables; `docker compose logs` sin tracebacks.
- [ ] Revisión de extremo a extremo por API (curl) de los 15 flujos del spec §10.1, corrigiendo bugs.
- [ ] Rendimiento básico: calendario (30 días × 60 unidades) responde < 500 ms; `today` < 300 ms; sin N+1 evidentes (`django.db.connection.queries` en tests clave).
- [ ] Seguridad: todas las vistas staff usan `PropertyScopedMixin`/`OrganizationScopedMixin`; las públicas no exponen datos de otras reservas; secretos nunca serializados; CSRF activo.
- [ ] i18n: sin textos hardcodeados en la UI (grep de strings en JSX fuera de `t(`), EN completo.
- [ ] README final (qué es, arquitectura, cómo correr, credenciales demo, cómo pasar integraciones a modo real, cómo correr tests, estructura) y `docs/integration-notes/D1-final.md`.

# FASE E — Validación E2E en Chrome (orquestador)

- [ ] Con `claude-in-chrome` recorrer los 15 flujos del spec §10.1 en `http://localhost:5173`, grabando GIFs de los flujos principales. Cada fallo → corrección (directa o con un agente) → re-verificación.
- [ ] Commit final y reporte al usuario.

---

## Self-review del plan (hecho)

- Cobertura del spec: §5 B1–B4 → B1–B4; C1–C12 → C1–C12 (+ C13 calendario separado de C1); §6 automatizaciones → asignadas a su app (+ `bookings.inventory_reconcile`, `ai.daily_brief`); §7 rutas → §E; §8 tests → por tarea + INT; §10 seed → seeds por app + `SEED_ORDER`; §10.1 → D1 + E. La suplantación de soporte del super-admin queda **fuera de alcance** (C11 ofrece el detalle de la organización en solo lectura).
- Consistencia de tipos: `Quote`, `Offer`, `ReservationRequest`, `StayRequest`, `GuestInput`, `LLMResult` definidos una vez (Fase A) y referenciados igual en B/C. `post_charge` incluye `tax_exempt` y `business_date` en todas las referencias.
- Endpoints compartidos entre tareas paralelas fijados en §C.
