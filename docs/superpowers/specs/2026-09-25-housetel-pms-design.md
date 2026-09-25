# Housetel — Diseño del sistema (PMS + OTA para Colombia)

Fecha: 2026-09-25 · Estado: aprobado por el usuario (decisiones recomendadas) · Idioma del código: inglés · Idioma del producto: ES (+EN)

Este documento es el **contrato común** para todos los agentes que construyen Housetel en paralelo. Si algo no está aquí, se decide siguiendo el espíritu del documento y se anota en `docs/integration-notes/<feature>.md`.

---

## 1. Producto

Housetel es un SaaS multi-hotel tipo Cloudbeds, más amigable y más automatizado, para **hoteles pequeños/medianos, hostales (venta por cama) y cadenas** en **Colombia**.

Incluye en una sola entrega:

1. **PMS**: panel "Hoy", calendario de reservas, reservas, check-in/out, huéspedes (CRM), folios y pagos, caja, housekeeping y mantenimiento, auditoría nocturna automática.
2. **Inventario configurable**: categorías (tipos de habitación) con parámetros completos → cada habitación hereda y puede sobreescribir cualquier parámetro → campos personalizados definidos por cada hotel. Dormitorios con camas vendibles.
3. **Tarifas tipo Cloudbeds**: planes base y derivados, temporadas, precio por día de semana, precio por ocupación, restricciones (estadía mín/máx, CTA, CTD, stop-sell), grilla con edición masiva, impuestos (IVA 19% con exención automática a extranjeros no residentes), políticas de cancelación, extras, códigos promocionales.
4. **Revenue management**: motor de reglas (ocupación, anticipación, día de semana, festivos de Colombia, eventos) con límites, + recomendaciones explicadas por IA que se aprueban con un clic (o se autoaplican si el hotel lo activa).
5. **Distribución**: marketplace público propio (tipo Booking.com, todos los hoteles de la plataforma), booking engine por hotel (página + widget embebible), channel manager (iCal real, Channex real/sandbox, simulador local de OTAs).
6. **Pagos**: Wompi (tarjeta, PSE, Nequi) + pagos manuales. El huésped paga a la cuenta Wompi del hotel; la plataforma registra comisión por reserva del marketplace y la liquida mensualmente.
7. **Legal Colombia**: factura electrónica DIAN (vía proveedor, ej. Factus), archivo SIRE (Migración Colombia), TRA (Tarjeta de Registro Alojamiento).
8. **Comunicación**: email y WhatsApp, plantillas ES/EN, mensajes automáticos del ciclo del huésped, bandeja unificada.
9. **Autoservicio del huésped**: check-in online (datos TRA, foto del documento, firma, hora de llegada, pago de saldo), portal del huésped, chatbot IA 24/7.
10. **IA**: copiloto del staff (con confirmación antes de actuar), chatbot de huéspedes, onboarding asistido, detección de anomalías, explicaciones de revenue.
11. **SaaS**: panel super-admin, planes con todo incluido (sin add-ons escondidos), prueba gratis, cobro recurrente vía Wompi, suspensión por mora, liquidación de comisiones del marketplace, registro de hoteles (signup).
12. **Seguridad operacional**: roles base + personalizados, automatizaciones que corren solas con registro de auditoría y deshacer, confirmación obligatoria para acciones de dinero riesgosas.

### 1.1 Qué hacemos mejor que Cloudbeds (tomado de reseñas reales)

| Queja en Cloudbeds | Respuesta en Housetel |
|---|---|
| Reportes con rangos de fecha / cálculos erróneos | Reportes basados en *business date* con tests de rangos exactos; un único motor de KPIs |
| Pagos que fallan o requieren confirmación manual | Verificación activa de transacciones (polling + webhook), conciliación automática, alertas |
| Sin app móvil / web no apta para celular | Todo responsive; vistas de housekeeping y recepción pensadas para celular |
| Bugs, cambios sin aviso | Tests por módulo + E2E; auditoría de todo cambio |
| Poca personalización | Herencia categoría→habitación, campos personalizados, roles personalizados, plantillas |
| Onboarding desordenado | Onboarding asistido por IA + checklist guiado |
| Add-ons y costos escondidos | Planes con todo incluido |
| Errores humanos | Restricciones en base de datos (imposible doble asignación de habitación), validaciones, automatizaciones, detección de anomalías |

### 1.2 Modo real vs simulado (regla transversal)

**Toda integración externa** (Wompi, Channex, iCal remoto, DIAN, SIRE, TRA, email, WhatsApp, LLM, cobro SaaS) tiene dos modos configurables **por propiedad** (o por plataforma para el cobro SaaS):

- `real`: usa el proveedor real o su sandbox con credenciales.
- `simulated`: implementación local con el mismo contrato, que recorre el flujo completo (estados, webhooks simulados, archivos, PDFs) sin salir a internet.

El modo por defecto es `simulated`, excepto: email (siempre SMTP; localmente Mailpit) y LLM (Gemini `real` si `GEMINI_API_KEY` existe; si falla por cuota → cae a simulado y registra aviso). La app debe funcionar de punta a punta con `docker compose up` sin credenciales.

---

## 2. Arquitectura

### 2.1 Stack

- **Backend**: Python 3.13, Django 5.2, Django REST Framework, django-filter, drf-spectacular (OpenAPI en `/api/docs/`), PostgreSQL 17 (extensión `btree_gist`), Redis 7, Celery 5 + Celery Beat (schedule estático generado desde el registro de automatizaciones), `cryptography` (Fernet para secretos), `holidays` (festivos CO), `icalendar`, `httpx`, `google-genai`, `anthropic`, `reportlab` (PDF), `openpyxl` (XLSX), `Pillow`, `phonenumbers`. Tests: `pytest`, `pytest-django`, `factory-boy`, `freezegun`, `respx`. Lint: `ruff`.
- **Frontend**: React 19 + TypeScript + Vite, React Router 7 (modo librería), TanStack Query, TanStack Table, TanStack Virtual, Tailwind CSS 4 + componentes estilo shadcn/ui (Radix), react-hook-form + zod, react-i18next, date-fns, Recharts, @dnd-kit, lucide-react, sonner (toasts), cmdk (paleta de comandos), `@fontsource-variable/manrope`. Tests: Vitest + Testing Library. Sin dependencias CDN (todo offline).
- **Infra local**: Docker Compose.

### 2.2 Servicios Docker (`docker-compose.yml`)

| Servicio | Imagen / build | Comando | Puerto host |
|---|---|---|---|
| `db` | postgres:17-alpine | — (healthcheck) | no expuesto |
| `redis` | redis:7-alpine | — | no expuesto |
| `backend` | `./backend` | migrate + `runserver 0.0.0.0:8000` | **8010**→8000 |
| `worker` | `./backend` | `celery -A config worker -l info` | — |
| `beat` | `./backend` | `celery -A config beat -l info` | — |
| `frontend` | `./frontend` | `npm run dev -- --host 0.0.0.0` | **5173** |
| `mailpit` | axllent/mailpit | — | **8025** (UI), SMTP interno 1025 |

- Código montado como volumen (`./backend:/app`, `./frontend:/app` + volumen anónimo `/app/node_modules`). No hace falta rebuild al cambiar código.
- Vite hace proxy de `/api` y `/media` a `http://backend:8000`. La app entera se usa en **http://localhost:5173**.
- `.env` (gitignored) con `DJANGO_SECRET_KEY`, `FERNET_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.5-flash`, `ANTHROPIC_API_KEY` (opcional), `WOMPI_PLATFORM_*` (opcional), etc. `.env.example` documentado y versionado.
- `Makefile`: `make up`, `make down`, `make seed`, `make test`, `make test-back`, `make test-front`, `make logs`, `make shell`, `make reset`.

### 2.3 Estructura del repositorio

```
/
├── docker-compose.yml  Makefile  README.md  .env.example  .gitignore
├── docs/superpowers/specs/…   docs/integration-notes/<feature>.md
├── backend/
│   ├── Dockerfile  requirements.txt  pyproject.toml (ruff, pytest)  manage.py  conftest.py
│   ├── config/  (settings.py, urls.py, celery.py, wsgi.py, asgi.py)
│   └── apps/<app>/  (models.py, services/ o services.py, api/ o views.py+serializers.py,
│                     urls.py, public_urls.py, permissions.py, automations.py, providers.py, tasks.py,
│                     signals.py/receivers.py, seed.py, admin.py, tests/, migrations/)
└── frontend/
    ├── Dockerfile  package.json  vite.config.ts  tsconfig*.json  index.html
    └── src/
        ├── main.tsx  app/ (router con auto-descubrimiento, providers, layouts, shell)
        ├── design/ (tokens.css, theme)   components/ui/ (primitivas)   components/ (compartidos)
        ├── lib/ (api client, auth, i18n, format, permissions, hooks)
        └── features/<feature>/ (routes.tsx, nav.ts, api.ts, pages/, components/,
                                 locales/es.json, locales/en.json, __tests__/)
```

### 2.4 Apps de Django y dueño (fase)

| App | Responsabilidad | Construye |
|---|---|---|
| `core` | Tenancy (Organization, Property), modelos base, auditoría + deshacer, alertas, framework de integraciones (real/simulado + secretos cifrados), framework de automatizaciones, registro de permisos, señales de dominio, utilidades de dinero/fechas | Fase A |
| `accounts` | User, Role, Membership, Invitation, auth | Fase A (API) / B3 (UI) |
| `inventory` | Amenity, RoomType, Room, Bed, CustomFieldDefinition, Photo, RoomBlock, herencia de atributos | modelos A / B1 |
| `rates` | Tax, CancellationPolicy, RatePlan, Season, RoomTypeRateDefaults, SeasonRate, DailyRate, Extra, PromoCode, motor de cotización | modelos A / B2a |
| `bookings` | Reservation, Stay, ReservationGroup, InventoryDay, servicios de reserva y disponibilidad | modelos A / B2b |
| `guests` | Guest, GuestDocument, deduplicación | modelos A / B3 |
| `finance` | Folio, Charge, Payment, Refund, PaymentIntent, CashShift, proveedores de pago | modelos A / B4 |
| `frontdesk` | Panel Hoy, calendario, auditoría nocturna, flujos de recepción | C1 |
| `housekeeping` | Tareas de limpieza, inspección, mantenimiento | C2 |
| `distribution` | Channel manager, iCal, Channex, simulador de OTAs | C3 |
| `marketplace` | Marketplace público, booking engine, widget | C4 |
| `guestportal` | Enlaces mágicos, check-in online, portal | C5 |
| `messaging` | Plantillas, envíos, bandeja unificada, email/WhatsApp | stub A / C6 |
| `compliance` | DIAN, SIRE, TRA | C7 |
| `revenue` | Reglas y recomendaciones de precio | C8 |
| `ai` | Proveedores LLM, copiloto, chatbot, onboarding, anomalías | stub A / C9 |
| `reports` | KPIs, reportes, exportaciones | C10 |
| `saas` | Planes, suscripciones, cobro, comisiones, super-admin, signup | C11 |
| (UI) `control` | Centro de control: integraciones, automatizaciones, auditoría+deshacer, alertas | C12 (usa modelos de `core`) |

> No se usa el nombre `platform` para una app (choca con la stdlib de Python).

---

## 3. Multi-tenancy, auth y permisos

- **Esquema compartido**: todas las tablas de negocio tienen `property` (y/o `organization`) como FK. Jerarquía: `Organization` (cliente/tenant, p. ej. una cadena) → `Property` (hotel/hostal) → `RoomType` → `Room` → `Bed`.
- **Huéspedes** (`Guest`) son por organización (compartidos entre propiedades de una cadena).
- **Auth**: sesión de Django por cookie + CSRF (el SPA está en el mismo origen vía proxy de Vite). Endpoints:
  - `GET  /api/v1/accounts/auth/csrf/` → pone cookie `csrftoken`
  - `POST /api/v1/accounts/auth/login/` `{email, password}` → `Me`
  - `POST /api/v1/accounts/auth/logout/`
  - `GET  /api/v1/accounts/me/` → `{id, email, full_name, language, is_platform_admin, memberships:[{organization:{id,name,slug,status}, role:{id,name,code}, permissions:[...codes], properties:[{id,name,slug,property_type,timezone,currency,business_date}]}]}`
- **Contexto de propiedad**: el frontend envía `X-Property-Id: <uuid>` en cada request de staff. La clase base `PropertyScopedViewSet` (core) valida que el usuario tenga acceso a esa propiedad, expone `request.property` y filtra los querysets por ella. Nunca se confía en un `property_id` del body.
- **Permisos**: códigos `<app>.<acción>` (p. ej. `bookings.view`, `bookings.manage`, `finance.refund`). Cada app declara los suyos en `apps/<app>/permissions.py` → `PERMISSIONS = [("finance.refund", "Reembolsar pagos", "Refund payments"), …]`. Los roles guardan una lista de códigos o **patrones** (`bookings.*`, `*`). DRF: `HasPropertyPermission("bookings.manage")`. Frontend: hook `useCan("bookings.manage")`.
- **Roles base** (plantillas de sistema, copiadas a cada organización):
  - `owner`: `*`
  - `manager`: `*` menos `saas.*`
  - `front_desk`: `frontdesk.*`, `bookings.*`, `guests.*`, `finance.view`, `finance.collect`, `messaging.*`, `guestportal.*`, `housekeeping.view`, `compliance.view`, `compliance.sire`, `reports.operational`, `ai.copilot`
  - `housekeeping`: `housekeeping.view`, `housekeeping.work`
  - `maintenance`: `housekeeping.view`, `housekeeping.maintenance`
  - `accountant`: `finance.*`, `reports.*`, `compliance.*`, `bookings.view`, `guests.view`
- **Acciones riesgosas** (`finance.refund`, `finance.void`, `bookings.waive_fee`, anular factura): requieren permiso específico **y** confirmación explícita en UI (diálogo que exige escribir el monto o el código de reserva) **y** el backend exige `confirm: true` en el body.
- **Super-admin** de plataforma: `User.is_platform_admin`; rutas `/api/v1/saas/admin/…` y UI `/admin`.
- Organización `suspended`: middleware devuelve 402 en toda la API de staff excepto `accounts` y `saas/billing`.

### 3.1 Convenciones de API

- Prefijos: staff `/api/v1/<app>/…` (auth + `X-Property-Id`), público `/api/v1/public/<app>/…` (sin auth; marketplace, booking engine, portal, chatbot, simuladores), webhooks `/api/v1/public/<app>/webhooks/<provider>/`.
- Paginación: `?page=&page_size=` → `{count, next, previous, results}`; `page_size` máx. 200.
- Errores: `{detail, code, fields?}` con HTTP correcto (400 validación, 403 permiso, 404, 409 conflicto de disponibilidad/estado, 402 suspendido).
- Dinero: `Decimal(14,2)` en BD, string en JSON (`"350000.00"`). Moneda por propiedad (COP por defecto). Fechas `YYYY-MM-DD`, datetimes ISO-8601 con zona.
- IDs: UUID (uuid4) como PK en todos los modelos de negocio. Códigos legibles adicionales donde el humano los usa (reserva `HT-7K2M9Q`).
- Campos traducibles: `JSONField` `{"es": "...", "en": "..."}` (helper `i18n_field()` y `t(value, lang)`).

---

## 4. Modelo de dominio núcleo (lo crea la Fase A)

Todos heredan de `core.models.BaseModel` (`id` UUID, `created_at`, `updated_at`). Listas de choices como `TextChoices`.

### core
- **Organization**: `name, slug(unique), legal_name, nit, country='CO', status[trial|active|past_due|suspended|cancelled], trial_ends_at, settings(JSON)`.
- **Property**: `organization, name, slug(unique global), property_type[hotel|hostel|boutique|aparthotel|glamping], description(i18n), address, city, department, country='CO', latitude, longitude, timezone='America/Bogota', currency='COP', default_language='es', check_in_time='15:00', check_out_time='12:00', phone, email, website, rnt_number, nit, legal_name, star_rating, house_rules(i18n), business_date(date), marketplace_listed(bool), commission_rate(Decimal, default 10.00), branding(JSON: primary_color, logo), status[active|inactive], settings(JSON)`.
- **AuditEvent**: `organization, property(null), actor(User null), actor_label, source[user|automation|ai|channel|guest|system|api], action(str, p. ej. "bookings.room_moved"), target_type, target_id, summary, changes(JSON before/after), reversible(bool), undo_data(JSON), undone_at, undone_by, request_id`.
- **Alert**: `property, kind, severity[info|warning|critical], title, message, link, dedupe_key, source, data(JSON), resolved_at, resolved_by`. Única abierta por `(property, dedupe_key)`.
- **IntegrationSetting**: `property(null = plataforma), kind[payments|channel_ical|channel_channex|einvoice|sire|tra|email|whatsapp|llm|saas_billing], mode[real|simulated], enabled, config(JSON), secrets_encrypted(text, Fernet), status[unknown|ok|error], status_message, last_checked_at`.
- **AutomationSetting**: `property, code, enabled, params(JSON)`; **AutomationRun**: `property, code, status[running|success|partial|failed|skipped], started_at, finished_at, summary, details(JSON)`.

### accounts
- **User** (custom, login por email): `email(unique), full_name, language, phone, is_platform_admin`.
- **Role**: `organization(null = plantilla), code, name, description, is_system, permissions(JSON list)`.
- **Membership**: `user, organization, role, all_properties(bool), properties(M2M Property), is_active`.
- **Invitation**: `organization, email, role, properties, token, expires_at, accepted_at, invited_by`.

### inventory
- **Amenity**: `organization(null = catálogo global), code, name(i18n), icon(lucide name), category[room|bathroom|property|accessibility|view]`.
- **RoomType** (categoría): `property, code, name(i18n), description(i18n), kind[private|dorm], base_occupancy, max_adults, max_children, max_occupancy, beds(JSON [{type,count}]), size_m2, view, smoking_allowed, accessible, amenities(M2M), color, housekeeping_minutes, sort_order, is_active, custom_values(JSON)`.
- **Room**: `property, room_type, number, name, floor, building, overrides(JSON — solo claves en ROOM_OVERRIDABLE_FIELDS), extra_amenities(M2M), removed_amenities(M2M), custom_values(JSON), housekeeping_status[clean|dirty|inspected|out_of_service], is_active, sort_order, notes, connecting_rooms(M2M self)`. Única `(property, number)`.
- **Bed** (solo dorms): `room, label, bed_type[single|bunk_top|bunk_bottom|double], is_active`.
- `ROOM_OVERRIDABLE_FIELDS = [name, description, base_occupancy, max_adults, max_children, max_occupancy, beds, size_m2, view, smoking_allowed, accessible, housekeeping_minutes]`. Servicio `effective_attributes(room) -> dict` (categoría + overrides + amenities ± + custom_values combinados, indicando qué campos están sobreescritos).
- **CustomFieldDefinition**: `organization, property(null = toda la org), applies_to[room_type|room|guest|reservation], key(slug), label(i18n), field_type[text|number|boolean|select|multiselect|date], options(JSON), required, default_value(JSON), show_in_marketplace(bool), sort_order`. Validación central `validate_custom_values(defs, values)`.
- **Photo**: `property, room_type(null), room(null), image, caption(i18n), sort_order`.
- **RoomBlock**: `room, bed(null), start_date, end_date(exclusive), kind[out_of_order|out_of_service|maintenance|owner_hold], reason, created_by, released_at`. Afecta disponibilidad.

### rates
- **Tax**: `property, code, name, rate(%), applies_to[room|extras|all], included_in_price(bool), exempt_foreign_non_residents(bool), is_active`. Seed: IVA 19% sobre alojamiento con exención a extranjeros no residentes (ET art. 481 lit. d); extras gravados normal.
- **CancellationPolicy**: `property, name(i18n), non_refundable, free_until_hours_before, penalty_type[first_night|percent|full], penalty_value, description(i18n)`.
- **RatePlan**: `property, code, name(i18n), kind[base|derived], parent(null), derivation_type[percent|amount], derivation_value(Decimal, ±), room_types(M2M), meal_plan[room_only|breakfast|half_board|full_board|all_inclusive], cancellation_policy, deposit_percent, is_public(bool), channels(JSON list: direct|marketplace|booking_engine|ota codes), min_los_default, is_active, sort_order`.
- **RoomTypeRateDefaults**: `room_type, rate_plan(base), price, dow_adjustments(JSON {"mon":0,…,"sat":15} en %), extra_adult_price, extra_child_price, child_age_limit=12, single_occupancy_price(null)`.
- **Season**: `property, name, start_date, end_date(incl.), priority, color`; **SeasonRate**: `season, room_type, rate_plan(base), price, dow_adjustments`.
- **DailyRate** (grilla materializada, solo planes base): `room_type, rate_plan, date, price, extra_adult_price, extra_child_price, min_los, max_los, closed_to_arrival, closed_to_departure, stop_sell, source[default|season|manual|revenue|bulk|channel], updated_by`. Única `(room_type, rate_plan, date)`. Las fechas sin fila se resuelven con temporada → defaults.
- **Extra**: `property, code, name(i18n), price, charge_type[per_stay|per_night|per_person|per_person_night], tax, sellable_online, is_active`.
- **PromoCode**: `property, code, discount_type[percent|amount], value, valid_from, valid_to, stay_from, stay_to, rate_plans(M2M), max_uses, uses, is_active`.

### bookings
- **ReservationGroup**: `property, name, contact_guest, notes`.
- **Reservation**: `property, code(unique), status[tentative|confirmed|checked_in|checked_out|cancelled|no_show], source[walk_in|phone|email|front_desk|booking_engine|marketplace|ota|api], channel_code(str), external_id, external_payload(JSON), booker(Guest), group(null), checkin_date, checkout_date, adults, children, currency, total_amount, language, eta(time null), special_requests, notes, promo_code(str), guarantee[none|card|deposit|ota], cancellation_policy_snapshot(JSON), cancelled_at, cancellation_reason, cancellation_fee, created_by(null), custom_values, tags(JSON)`.
- **Stay** (habitación dentro de la reserva): `reservation, room_type, rate_plan, room(null), bed(null), checkin_date, checkout_date, period(DateRangeField, generado en save), adults, children, children_ages(JSON), occupants(M2M Guest), nightly_rates(JSON [{date, amount}]), total_amount, status (mismo enum que Reservation), locked_room(bool), checked_in_at, checked_out_at`.
  - **ExclusionConstraint** (btree_gist): no pueden existir dos `Stay` activas (`status in tentative, confirmed, checked_in`) con el mismo `room` y `period` solapado; ídem para `bed`. Es la garantía en BD contra doble asignación.
- **InventoryDay**: `property, room_type, date, total_units, sold_units, blocked_units`. Única `(room_type, date)`. Se bloquea con `select_for_update` al reservar; unidades = habitaciones (private) o camas (dorm).

### guests
- **Guest**: `organization, first_name, last_name, email, phone(E.164), document_type[CC|CE|PA|TI|PEP|PPT|DNI|NIT|OTHER], document_number, nationality(ISO-2), country_of_residence(ISO-2), city_of_residence, birth_date, gender, address, language, is_vip, tags(JSON), notes, preferences(JSON), marketing_consent, data_processing_consent_at (Ley 1581/Habeas Data), custom_values, blacklisted, merged_into(null)`. Índice único parcial `(organization, document_type, document_number)` cuando hay documento.
  - Propiedad derivada `is_foreign_non_resident` = nacionalidad ≠ CO y residencia ≠ CO (controla exención de IVA y SIRE).
- **GuestDocument**: `guest, kind[id_front|id_back|passport|signature|other], file, uploaded_via[staff|portal]`.

### finance
- **Folio**: `property, reservation(null), stay(null), guest(null), folio_type[guest|master|house], status[open|closed], currency, closed_at`.
- **Charge**: `folio, business_date, kind[room|extra|tax|fee|cancellation_fee|adjustment|other], description, quantity, unit_price, amount, tax(null), tax_amount, stay(null), night_date(null), extra(null), posted_by(null), source, voided_at, voided_by, void_reason`. Nunca se borra; se anula con motivo.
- **Payment**: `folio, amount, method[cash|card_terminal|bank_transfer|wompi_card|wompi_pse|wompi_nequi|wompi_other|ota_collect|other], status[pending|approved|declined|voided|error], provider, provider_reference, provider_payload(JSON), business_date, received_by(null), notes`.
- **Refund**: `payment, amount, status[pending|approved|failed], provider_reference, reason, approved_by`.
- **PaymentIntent**: `property, folio, amount, currency, provider, mode[real|simulated], reference(unique), checkout_url, status[created|pending|approved|declined|expired|error], expires_at, return_url, payload(JSON)`.
- **CashShift**: `property, user, opened_at, closed_at, opening_float, expected_cash, counted_cash, difference, notes`.
- Saldo del folio = Σ cargos no anulados − Σ pagos aprobados + Σ reembolsos aprobados.

### 4.1 Señales de dominio (`core.signals`)

Se emiten siempre dentro de `transaction.on_commit`. Los productores (fases A/B) las envían; los consumidores (fase C) se suscriben en su `receivers.py`:

`reservation_created(reservation)`, `reservation_updated(reservation, changes)`, `reservation_cancelled(reservation)`, `reservation_no_show(reservation)`, `stay_checked_in(stay)`, `stay_checked_out(stay)`, `room_assigned(stay, old_room)`, `room_status_changed(room, old, new)`, `inventory_changed(property, room_type_ids, start, end)`, `rates_changed(property, room_type_ids, rate_plan_ids, start, end)`, `payment_received(payment)`, `folio_closed(folio)`, `guest_checked_in_online(reservation)`.

### 4.2 Contratos de servicios (firmas fijadas en Fase A; implementaciones reales en Fase B)

Los consumidores **solo** llaman a estas funciones (no escriben directo en modelos de otras apps). Los tipos viven en `apps/<app>/types.py` como `dataclasses`.

```python
# apps/rates/services/quote.py
def quote(*, property, room_type, rate_plan, checkin, checkout, adults, children=0,
          children_ages=None, promo_code=None, guest_is_foreign_non_resident=False) -> Quote
# Quote: nights[NightPrice(date, base, extra_adults, extra_children, discount, total)],
#        subtotal, taxes[TaxLine(code, name, rate, amount, included)], total, currency,
#        restrictions_ok, violations[str], promo_applied
def resolve_daily(room_type, rate_plan, start, end) -> list[DayRate]      # precio+restricciones efectivas
def set_daily_rates(*, property, room_type, rate_plan, start, end, price=None,
                    restrictions=None, dow=None, source="manual", actor=None) -> int  # emite rates_changed

# apps/bookings/services/availability.py
def availability(*, property, checkin, checkout, room_type_ids=None) -> dict[UUID, int]
def search_offers(*, property, checkin, checkout, adults, children=0, children_ages=None,
                  channel="direct", promo_code=None, guest_is_foreign_non_resident=False) -> list[Offer]
# Offer: room_type, rate_plan, available_units, quote

# apps/bookings/services/reservations.py
def create_reservation(req: ReservationRequest, *, actor=None, source_label=None) -> Reservation
#   ReservationRequest(property, booker: GuestInput|Guest, stays[StayRequest], source, channel_code,
#   external_id, notes, special_requests, promo_code, language, eta, allow_overbooking=False, status="confirmed")
#   Atómico: bloquea InventoryDay, valida restricciones, cotiza, crea folio y cargos por noche proyectados,
#   emite reservation_created. Lanza AvailabilityError (409) / RestrictionError (400).
def modify_stay(stay, *, checkin=None, checkout=None, room_type=None, rate_plan=None,
                adults=None, children=None, reprice=True, actor=None) -> Stay
def cancel_reservation(reservation, *, reason, waive_fee=False, actor=None, source="user") -> Reservation
def assign_room(stay, room, *, bed=None, actor=None, force=False) -> Stay
def auto_assign_rooms(*, property, date_from, date_to, actor=None) -> AssignmentReport
def check_in(stay, *, actor=None, force=False) -> Stay      # valida habitación asignada y limpia/inspeccionada, fecha
def check_out(stay, *, actor=None, force=False) -> Stay     # valida saldo (o force con permiso), marca hab. sucia
def mark_no_show(reservation, *, actor=None, source="automation") -> Reservation

# apps/finance/services.py
def get_or_create_folio(reservation, *, stay=None) -> Folio
def post_charge(folio, *, kind, amount, description, quantity=1, tax=None, stay=None,
                night_date=None, extra=None, actor=None, source="user") -> Charge
def void_charge(charge, *, reason, actor, confirm) -> Charge
def record_payment(folio, *, amount, method, reference="", actor=None, status="approved",
                   provider="manual", payload=None) -> Payment
def refund_payment(payment, *, amount, reason, actor, confirm) -> Refund
def create_payment_intent(folio, *, amount, return_url, provider_kind="payments") -> PaymentIntent
def sync_payment_intent(intent) -> PaymentIntent            # verifica activamente con el proveedor
def folio_balance(folio) -> Decimal
def reservation_balance(reservation) -> Decimal

# apps/inventory/services.py
def effective_attributes(room) -> dict
def block_room(room, *, start, end, kind, reason, actor=None, bed=None) -> RoomBlock   # emite inventory_changed
def set_housekeeping_status(room, status, *, actor=None, source="user") -> Room        # emite room_status_changed

# apps/messaging/services.py   (stub en A: registra en log; C6 implementa)
def send_message(*, property, template_code, guest=None, reservation=None, to=None,
                 channels=("email",), context=None, language=None) -> list[OutboundMessage]

# apps/ai/llm.py               (stub en A: simulado; C9 implementa)
def get_llm(property=None) -> LLMClient
#   LLMClient.generate(messages, *, system=None, tools=None, response_schema=None,
#                      temperature=0.2) -> LLMResult(text, tool_calls, data, provider, simulated)

# apps/core/…
audit.record(*, action, target, summary, actor=None, source="user", changes=None,
             reversible=False, undo_data=None, property=None) -> AuditEvent
audit.register_undo(action, handler)          # handler(event) revierte
alerts.raise_alert(*, property, kind, severity, title, message, link="", dedupe_key, data=None)
alerts.resolve_alert(property, dedupe_key)
integrations.register_provider(kind, mode, cls); integrations.get_provider(property, kind)
integrations.get_setting(property, kind) -> IntegrationSetting  # crea por defecto 'simulated'
automation.register(Automation(code, app, name_es, name_en, description_es, schedule(crontab),
                    handler(property, params) -> RunResult, default_enabled=True))
automation.run(code, property)                # envuelve en AutomationRun + auditoría source="automation"
permissions.has_perm(user, property, code)
```

---

## 5. Módulos funcionales y criterios de aceptación

Cada módulo es una **rebanada vertical** (backend + frontend + tests + seed). Criterios mínimos:

### B1 · Inventario y propiedad
- CRUD de categorías (todos los parámetros, amenidades, fotos, color, campos personalizados), habitaciones (heredan; formulario muestra valor heredado en gris y permite "sobreescribir"/"restaurar herencia"), camas para dorms, creación masiva de habitaciones (rango "101-120", piso), edición masiva (seleccionar N habitaciones → cambiar campo), definiciones de campos personalizados con validación.
- Bloqueos de habitación (fuera de servicio) con fechas.
- Perfil de la propiedad: datos legales (NIT, RNT), horarios, idiomas, políticas, reglas, branding.
- Vista "efectiva" de una habitación que resuelve la herencia; tests de herencia.

### B2a · Tarifas
- Planes base/derivados (derivado se recalcula solo), temporadas, precios por día de semana, ocupación (adulto/niño extra, ocupación sencilla), restricciones, impuestos, políticas de cancelación, extras, promo codes.
- **Grilla de tarifas**: categorías × fechas (30/60/90 días), edición en celda, edición masiva por rango + días de semana + campos (precio, min/max LOS, CTA/CTD, stop-sell), vista de disponibilidad en la misma grilla.
- `quote()` correcto con tests: noches, DOW, temporada, manual, derivado %, ocupación, niños por edad, promo, IVA incluido/excluido, exención extranjero.

### B2b · Motor de reservas (backend)
- `InventoryDay` se regenera desde datos (`rebuild_inventory(property, start, end)`) y se mantiene en cada cambio; bloqueos de habitación descuentan.
- Todas las funciones de §4.2 de bookings con tests de concurrencia (dos reservas simultáneas por la última unidad → una falla con 409), restricciones, dorms por cama, auto-asignación (respeta `locked_room`, conecta grupos, prefiere habitaciones limpias, no mueve check-ins), cambios de fechas con recotización, cancelación con penalidad según política, no-show.
- API de reservas: listar/filtrar, detalle, crear, modificar, cancelar, asignar, check-in/out, búsqueda de disponibilidad/ofertas.

### B3 · Huéspedes, usuarios y roles
- CRM: lista con búsqueda, perfil (datos, documentos, historial de estancias, gasto total, notas, VIP, preferencias), deduplicación sugerida + fusión, consentimiento Habeas Data.
- Usuarios: invitar por email, asignar rol y propiedades, desactivar. Roles personalizados con matriz de permisos agrupada por módulo.

### B4 · Finanzas y pagos
- Servicios §4.2 de finance, proveedores `payments` real (Wompi: checkout web, verificación por API de transacción, webhook de eventos con firma, llaves de integridad) y simulado (página `/sim/pay/:reference` para aprobar/rechazar/expirar).
- Componente reutilizable `<FolioPanel reservationId>` (cargos, pagos, saldo, agregar cargo/extra, registrar pago manual, enviar link de pago, anular con motivo, reembolsar con confirmación).
- Caja: abrir/cerrar turno, conteo, diferencia; exportable.

### C1 · Recepción (frontdesk)
- **Panel Hoy**: KPIs (ocupación, llegadas, salidas, en casa, ingresos del día), listas accionables (check-in/out en 1–2 clics), alertas, progreso de limpieza, recomendaciones IA pendientes.
- **Calendario**: grilla categorías/habitaciones/camas × días, virtualizada, arrastrar para mover habitación/fechas (con validación y confirmación), estirar para extender, arrastrar sobre vacío para crear reserva, colores por estado, bloqueos visibles, fila de disponibilidad y precio.
- Reservas: lista con filtros, detalle (stays, huéspedes, folio, mensajes, auditoría, documentos legales), asistente de nueva reserva (búsqueda de ofertas → huésped con autocompletar/dedup → extras → garantía/pago → confirmación), grupos, cancelar, no-show, mover habitación.
- **Auditoría nocturna** automática (Celery, hora configurable): marca no-shows, publica cargos de noche, avanza `business_date`, genera reporte de cierre, alerta de pendientes. Botón manual con vista previa.

### C2 · Housekeeping y mantenimiento
- Al check-out → habitación sucia + tarea; tareas diarias de "stayover" configurables; inspección opcional; asignación automática balanceada por minutos (`housekeeping_minutes`) y piso; vista móvil de camarera ("mis habitaciones", iniciar/terminar, reportar daño con foto); tablero de supervisión; tickets de mantenimiento que crean `RoomBlock` si inhabilitan la habitación.

### C3 · Distribución (channel manager)
- Conexiones por propiedad y canal; mapeo categoría/plan ↔ canal; cola de ARI (disponibilidad, tarifas, restricciones) disparada por señales con *debounce*; ingreso de reservas (nueva/modificación/cancelación) idempotente por `external_id`; log de sincronización; alertas de overbooking.
- **iCal**: exportar calendario por categoría/habitación (URL secreta) e importar de URL remota (real) con sincronización periódica.
- **Channex** (real/sandbox): conectores ARI y reservas según su API.
- **Simulador de OTAs** (`/app/simulators/ota`): OTAs ficticias "BookSim" y "AirSim" que muestran el ARI recibido y permiten crear/modificar/cancelar reservas que entran al PMS por el mismo camino que un canal real.

### C4 · Marketplace y booking engine
- Público `/`: buscador (ciudad, fechas, huéspedes), resultados con filtros (precio, tipo, amenidades, estrellas), página del hotel (fotos, descripción, categorías con precio real, políticas, amenidades, ubicación en texto), checkout (datos del huésped + consentimiento, extras, pago vía `create_payment_intent` o garantía), confirmación con enlace al portal del huésped.
- Booking engine por hotel `/h/:slug` con branding del hotel; widget embebible `/embed/:slug` + snippet copiable desde configuración.
- Staff: configuración de listing (visible en marketplace, fotos destacadas, descripción), promo codes visibles.

### C5 · Portal del huésped
- Enlace mágico firmado por reserva (`/g/:token`), enviado en confirmación y pre-llegada.
- Check-in online: datos de cada huésped (campos TRA/SIRE), foto del documento, consentimiento, firma (canvas), ETA, pago del saldo; al completarlo emite `guest_checked_in_online` y la reserva queda "lista" para recepción.
- Portal: ver reserva, modificar/cancelar dentro de política, comprar extras, descargar factura/recibo, ver mensajes, chatbot.

### C6 · Mensajería
- Plantillas por evento e idioma con variables (`{{guest.first_name}}`, `{{reservation.code}}`, `{{portal_url}}`…), vista previa.
- Automatizaciones: confirmación, pre-llegada (N días antes con link de check-in), día de llegada, post-estancia (encuesta/reseña), recordatorio de pago, cancelación.
- Canales: email (SMTP → Mailpit local; HTML bonito), WhatsApp Cloud API (real) / simulado. Webhook de entrada de WhatsApp.
- Bandeja unificada: hilos por reserva/huésped, responder desde la app, estado de entrega.
- Simulador de WhatsApp (`/app/simulators/whatsapp`): UI tipo teléfono para actuar como huésped.

### C7 · Legal Colombia
- **DIAN**: configuración de resolución de facturación (prefijo, rango, vigencia), emisión al check-out (automática o manual), IVA exento a extranjeros no residentes, notas crédito, estados, CUFE, PDF/XML. Real: adaptador a proveedor tecnológico (Factus API sandbox). Simulado: genera CUFE falso determinístico + PDF.
- **SIRE**: genera el archivo de cargue masivo de Migración Colombia (entradas/salidas de extranjeros) por rango de fechas, validación de campos faltantes, descarga, marcado como reportado. Real = archivo para subir al portal (no hay API pública); Simulado = además simula el acuse.
- **TRA**: registro por huésped al check-in con los datos del check-in online. Real: adaptador configurable al servicio de MinCIT; Simulado: número de TRA local.
- Alertas por datos faltantes y por pendientes de reportar.

### C8 · Revenue
- Reglas: por ocupación (umbrales → % ajuste), anticipación (last-minute / early-bird), día de semana, festivos CO (`holidays`), eventos manuales; límites mínimo/máximo por categoría; paso máximo por día.
- Corrida programada → recomendaciones (`pending/approved/rejected/applied/auto_applied`), aplicar vía `set_daily_rates(source="revenue")`, explicación por IA en lenguaje natural, modo autoaplicar por propiedad.
- UI: reglas, calendario de recomendaciones con aprobar/rechazar masivo, historial, impacto.

### C9 · IA
- Proveedores: `GeminiProvider` (google-genai, function calling, `GEMINI_MODEL`), `ClaudeProvider` (anthropic, opcional), `SimulatedProvider` (respuestas determinísticas útiles). Manejo de 429/errores → fallback + alerta.
- **Copiloto** (panel lateral + paleta ⌘K): herramientas de lectura (llegadas, disponibilidad, reservas, saldos, KPIs) y de acción (crear reserva, mover habitación, enviar mensaje, bloquear habitación) — las de acción devuelven una **propuesta** que el usuario confirma; se ejecutan con los servicios de §4.2 y se auditan con `source="ai"`. Respeta permisos del usuario.
- **Chatbot de huéspedes**: conocimiento de la propiedad (descripción, políticas, FAQ configurable, horarios), herramienta de disponibilidad/cotización, genera link al booking engine; escala a humano creando hilo en bandeja. Widget montado en los layouts públicos.
- **Onboarding asistido**: el usuario describe su hotel (texto libre y/o URL de su web) → la IA propone categorías, habitaciones, camas, tarifas, políticas → pantalla de revisión editable → crear todo con los servicios de inventario/tarifas.
- **Anomalías**: chequeos por reglas (reserva confirmada sin garantía a <48h, pagos duplicados, tarifa fuera de límites, noches sin cargo, VIP en habitación sucia a <2h, check-in sin TRA, factura no emitida tras check-out, diferencia de caja, sobreventa) → `Alert` + resumen IA diario.

### C10 · Reportes
- Motor único de KPIs sobre *business date*: ocupación, ADR, RevPAR, ingresos (alojamiento/extras/impuestos), por canal/fuente/categoría, pickup, on-the-books/pronóstico, cancelaciones, anticipación, duración media.
- Operativos: llegadas, salidas, en casa, no-shows, housekeeping. Financieros: ingresos diarios, pagos por método, turnos de caja, IVA, saldos por cobrar, comisiones.
- Filtros de rango correctos (inclusivo/exclusivo documentado), comparación con periodo anterior, gráficos, exportación CSV/XLSX/PDF. Tests con fixtures de rangos exactos.

### C11 · SaaS y super-admin
- Signup de hotel (`/signup`): crea organización + propiedad + usuario dueño + prueba de 14 días → onboarding (manual o IA).
- Planes: Starter (≤15 unidades), Pro (≤60), Cadena (ilimitado, multi-propiedad); todas las funciones incluidas. Precios en COP.
- Suscripciones: ciclo mensual, cobro vía Wompi (real/simulado, credenciales de plataforma), reintentos, `past_due` → `suspended`, reactivación al pagar; facturas de plataforma.
- Comisiones: registro por reserva de `marketplace` (receiver de `reservation_created`), ajuste por cancelación, liquidación mensual por organización, estado de cuenta.
- UI `/admin`: organizaciones (estado, plan, uso, suspender/reactivar, entrar como soporte en modo lectura), planes, suscripciones y cobros, comisiones, métricas de plataforma. UI de facturación para el hotel en configuración.

### C12 · Centro de control (UI sobre `core`)
- Integraciones: tarjeta por tipo, modo real/simulado, formulario de credenciales (secretos nunca se devuelven al frontend, solo "configurado"), probar conexión, estado.
- Automatizaciones: lista por propiedad (nombre, descripción, horario, activa, última corrida, resultado), activar/desactivar, parámetros, ejecutar ahora, historial.
- Auditoría: línea de tiempo filtrable, detalle antes/después, **deshacer** cuando `reversible`.
- Alertas: centro de alertas, resolver, enlaces al objeto.

---

## 6. Automatizaciones (registradas por cada app)

| Código | App | Horario por defecto |
|---|---|---|
| `frontdesk.night_audit` | frontdesk | diario 02:00 hora de la propiedad |
| `bookings.auto_assign_rooms` | bookings | diario 06:00 (llegadas de hoy y mañana) |
| `bookings.release_expired_tentative` | bookings | cada 15 min |
| `housekeeping.generate_daily_tasks` | housekeeping | diario 07:00 |
| `housekeeping.auto_assign` | housekeeping | diario 07:15 |
| `messaging.lifecycle_dispatch` | messaging | cada 10 min |
| `distribution.push_ari` | distribution | cada 1 min (cola con debounce) |
| `distribution.pull_ical` | distribution | cada 15 min |
| `finance.sync_pending_intents` | finance | cada 5 min |
| `revenue.run_rules` | revenue | diario 05:00 + cada 6 h |
| `ai.anomaly_scan` | ai | cada hora |
| `compliance.issue_pending_invoices` | compliance | cada 15 min |
| `compliance.sire_daily_file` | compliance | diario 08:00 |
| `saas.billing_cycle` | saas | diario 03:00 (plataforma) |
| `saas.commission_settlement` | saas | día 1 del mes |

Beat corre cada entrada global y el handler itera las propiedades donde la automatización está activa, respetando la zona horaria de la propiedad.

---

## 7. Frontend

### 7.1 Rutas

- Público: `/` (marketplace), `/search`, `/hotel/:slug`, `/book/:slug`, `/booking/:code/confirmed`, `/h/:slug` (booking engine), `/embed/:slug` (widget), `/g/:token` (portal) y `/g/:token/checkin`, `/sim/pay/:reference` (pago simulado), `/signup`, `/login`, `/invite/:token`.
- Staff `/app`: `/app` (Hoy), `/app/calendar`, `/app/reservations`, `/app/reservations/new`, `/app/reservations/:id`, `/app/guests`, `/app/guests/:id`, `/app/housekeeping`, `/app/maintenance`, `/app/rates`, `/app/rates/plans`, `/app/revenue`, `/app/channels`, `/app/inbox`, `/app/cashier`, `/app/compliance`, `/app/reports`, `/app/alerts`, `/app/onboarding`, `/app/simulators/{ota,whatsapp}`, `/app/settings/{property,room-types,rooms,custom-fields,taxes,policies,extras,booking-engine,users,roles,integrations,automations,audit,billing,messaging,compliance}`.
- Super-admin: `/admin`, `/admin/organizations`, `/admin/plans`, `/admin/billing`, `/admin/commissions`.

### 7.2 Auto-descubrimiento (sin archivos centrales compartidos)

- `src/app/registry.ts` usa `import.meta.glob('../features/*/routes.tsx', { eager: true })` y `import.meta.glob('../features/*/nav.ts', { eager: true })`. Cada feature exporta `routes: FeatureRoutes` (`{ public?: RouteObject[], app?: RouteObject[], admin?: RouteObject[] }`, páginas con `lazy`) y `nav: NavItem[]` (`{ section, label key, icon, path, permission, order }`).
- i18n: `import.meta.glob('../features/*/locales/*.json')` → namespace = nombre de la feature. Textos globales en `src/lib/i18n/locales/{es,en}/common.json`.
- Los layouts públicos incluyen `<PublicChatSlot/>` que monta `features/ai/public-widget.tsx` si existe.

### 7.3 Diseño — "cálido nórdico"

Mezcla de hospitalidad cálida y minimalismo nórdico: mucho aire, bordes finos, un solo acento cálido, estados suaves y legibles.

- Tipografía: **Manrope Variable** (local, `@fontsource-variable/manrope`); números con `font-variant-numeric: tabular-nums`. Base 14px en la app de staff, 16px en lo público.
- Tokens (CSS variables en `design/tokens.css`, claro/oscuro con `[data-theme]` + `prefers-color-scheme`):
  - Claro: `--bg #FAF8F5`, `--surface #FFFFFF`, `--surface-2 #F3F0EB`, `--border #E7E2DA`, `--text #1F1C19`, `--text-muted #6E675E`, `--accent #B4583B` (terracota suave), `--accent-hover #9A4A31`, `--accent-soft #F5E7E0`, `--success #5F7F66` (salvia) / `--success-soft #E8EFE8`, `--warning #B98A2E` (arena) / `#F8EFDA`, `--danger #B5473C` / `#F7E4E1`, `--info #4E6C88` (azul pizarra) / `#E5ECF3`.
  - Oscuro: `--bg #141311`, `--surface #1C1A18`, `--surface-2 #252220`, `--border #35312C`, `--text #EEEAE4`, `--text-muted #A59E94`, `--accent #D4775C`, softs con alfa sobre la superficie.
  - Estados de habitación: limpia → salvia, sucia → arena, inspeccionada → azul pizarra, fuera de servicio → piedra con rayado, ocupada → acento.
- Radio 10px, sombras mínimas, iconos lucide de 16–18px, foco visible, contraste AA.
- Shell de staff: sidebar colapsable (drawer en móvil), barra superior con selector de propiedad, fecha de negocio, búsqueda/⌘K, botón copiloto, alertas, tema, idioma, usuario.
- Público: más editorial (fotos grandes, tipografía más grande), branding del hotel en `/h/:slug`.

### 7.4 Componentes compartidos (Fase A)

`Button, Input, Select, Combobox, Checkbox, Switch, Textarea, Dialog, Drawer/Sheet, DropdownMenu, Tabs, Tooltip, Popover, Badge, Card, Table (TanStack), DataTable con filtros/paginación, EmptyState, Skeleton, PageHeader, FormField (react-hook-form), MoneyInput/MoneyText (COP), DateRangePicker, DatePicker, StatusBadge (reserva/habitación/pago), ConfirmDialog y DangerConfirmDialog (exige escribir texto), Stat/KPI tile, Toaster`.

Cliente API (`lib/api.ts`): fetch con cookies, CSRF automático, `X-Property-Id` desde el store de propiedad activa, errores tipados, hooks de TanStack Query.

---

## 8. Calidad y tests

- Backend: cada app con tests en `apps/<app>/tests/` (servicios, API, permisos, multi-tenancy — un usuario de otra organización nunca ve datos). Factories compartidas en `apps/<app>/tests/factories.py`; fixtures base en `backend/conftest.py`.
- Paralelismo: los tests usan `TEST_DB_NAME` (env) para que agentes distintos no choquen: `docker compose run --rm -e TEST_DB_NAME=test_<feature> backend pytest apps/<app>`.
- Frontend: Vitest por feature (`npx vitest run src/features/<feature>`), `npm run typecheck`, `npm run lint`.
- E2E final: recorrido manual automatizado con Claude-in-Chrome de todos los flujos principales (§10).
- Definición de "hecho" por módulo: tests verdes, typecheck limpio, seed de demo del módulo, criterios de §5 verificados, notas en `docs/integration-notes/<feature>.md`.

---

## 9. Reglas para agentes en paralelo

1. Cada agente **solo modifica** los directorios de su módulo: `backend/apps/<app>/` y `frontend/src/features/<feature>/` (+ su `docs/integration-notes/<feature>.md`).
2. Prohibido editar modelos/servicios de otra app. Si necesitas datos extra sobre un modelo ajeno, crea un modelo propio con FK/OneToOne en tu app. Si necesitas un cambio en otra app, descríbelo en tus integration-notes.
3. Solo generas migraciones de tu app: `python manage.py makemigrations <app>`.
4. No agregues dependencias (pip/npm) salvo necesidad real; si lo haces, anótalo en integration-notes (la fase de integración las consolida). Preferir lo ya instalado.
5. Archivos compartidos (settings, urls raíz, registry del frontend, docker-compose, package.json) son de la Fase A; la fase de integración es la única que los toca después.
6. Comunicación entre módulos solo vía contratos de §4.2 y señales de §4.1.
7. Cada módulo registra sus permisos, automatizaciones, proveedores de integración y seed en sus propios archivos (`permissions.py`, `automations.py`, `providers.py`, `seed.py`), que el core auto-descubre.
8. Textos de UI siempre vía i18n (ES completo, EN completo).
9. Commits: no los hacen los agentes; el orquestador hace commit al cerrar cada fase.

---

## 10. Datos de demo (`make seed`)

- Super-admin: `admin@housetel.co` / `housetel123`.
- Org "Casa Aurora" (plan Pro): **Hotel Casa Aurora**, Cartagena, boutique, 24 habitaciones (Estándar, Superior, Suite con vista al mar), dueño `owner@casaaurora.co`, recepción `recepcion@casaaurora.co`, housekeeping `limpieza@casaaurora.co`, contabilidad `contabilidad@casaaurora.co` (clave `housetel123`).
- Org "Grupo Andino" (plan Cadena): **Andino Medellín** (hotel 40 hab., El Poblado) y **Andino Hostel Bogotá** (La Candelaria; dormitorios de 6 y 8 camas + privadas), dueño `owner@grupoandino.co`.
- Huéspedes colombianos y extranjeros; reservas de −60 a +90 días en todos los estados y fuentes (directo, marketplace, BookSim, AirSim); pagos, folios, tareas de limpieza, mensajes, facturas simuladas, recomendaciones de revenue, alertas.
- Todo el seed es idempotente (`seed_demo --reset` limpia y recrea).

### 10.1 Flujos E2E a validar en Chrome (fase final)

1. Login staff → panel Hoy → check-in de una llegada (habitación limpia) → check-out con pago → habitación pasa a sucia → housekeeping la limpia desde vista móvil.
2. Crear reserva desde el calendario (arrastrar) y desde el asistente; moverla de habitación arrastrando; intento de doble asignación bloqueado.
3. Configurar categoría + habitación con override + campo personalizado; ver herencia.
4. Grilla de tarifas: edición masiva de fin de semana; plan derivado se actualiza; restricción min LOS bloquea una cotización.
5. Marketplace: buscar Cartagena → hotel → reservar con pago simulado (y Wompi sandbox si hay llaves) → confirmación → reserva visible en PMS con comisión registrada.
6. Booking engine `/h/:slug` y widget.
7. Portal del huésped: check-in online completo con firma → recepción ve "lista".
8. BookSim crea reserva → llega al PMS; cambio de tarifa en PMS → BookSim recibe ARI.
9. Mensaje WhatsApp simulado entrante → bandeja → respuesta; email visible en Mailpit.
10. Factura DIAN simulada al check-out; archivo SIRE generado; TRA registrado.
11. Revenue: correr reglas → aprobar recomendación → grilla actualizada.
12. Copiloto: "¿cuántas llegadas hay hoy?" y una acción con confirmación; onboarding IA de un hotel nuevo vía signup; chatbot público responde disponibilidad.
13. Auditoría: deshacer un movimiento de habitación. Automatizaciones: ejecutar auditoría nocturna manualmente.
14. Super-admin: ver organizaciones, suspender/reactivar, liquidación de comisiones.
15. Cambiar a inglés y a modo oscuro; vista móvil (375px) de Hoy, limpieza y portal.

---

## 11. Fuera de alcance (por ahora)

App nativa/PWA, SMS, kiosko, POS de restaurante, integración con cerraduras, multi-moneda por reserva, pagos con dispositivo físico (datáfono integrado), certificación real con Booking/Expedia (se cubre vía Channex).

## 12. Fases de construcción

- **A — Fundación** (2 agentes paralelos: backend-foundation, frontend-foundation).
- **B — Motores núcleo** (5 agentes: B1 inventario, B2a tarifas, B2b reservas, B3 huéspedes/usuarios, B4 finanzas).
- **C — Funcionalidades** (12 agentes: C1…C12), cada uno con pasada de verificación y corrección.
- **D — Integración** (consolidar dependencias, seed completo, suite completa verde, `docker compose up` limpio).
- **E — Validación E2E en Chrome** de los flujos de §10.1, corrigiendo lo que falle.

Entre fases el orquestador verifica (`docker compose up`, tests) y hace commit.
