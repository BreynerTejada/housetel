# A1 — Backend foundation — integration notes

Estado: Steps 1–10 completos y verificados (ver "Verificación"). Esta tarea continuó un intento previo de A1 que
se había interrumpido: todo el código heredado quedó cubierto por tests (116 al inicio → **740** al cierre) y lo
nuevo se hizo con TDD.

Lectura obligatoria para las fases B/C: secciones "Guía rápida" y "Contratos". Las firmas están congeladas por
`apps/core/tests/test_contracts.py` y los campos de modelos por `apps/core/tests/test_domain_contract.py`
(puedes **agregar** campos a los modelos de tu app; no renombrar ni quitar los del spec).

---

## Guía rápida para agentes B/C

### Levantar y probar

```bash
docker compose up -d --build db redis mailpit backend worker beat      # backend en http://localhost:8010
docker compose run --rm -e TEST_DB_NAME=test_<tarea> backend pytest apps/<app> -q
docker compose run --rm backend ruff check .        # line-length 110; `ruff format .` para formatear
docker compose run --rm backend python manage.py makemigrations <app>
docker compose run --rm backend python manage.py seed_demo            # idempotente; --reset recrea
```

### Vista de staff (patrón obligatorio)

```python
from apps.core.tenancy import PropertyScopedViewSet, PropertyScopedAPIView, OrganizationScopedMixin

class RoomTypeViewSet(PropertyScopedViewSet):          # filtra por request.property y la asigna al crear
    queryset = RoomType.objects.all()
    serializer_class = RoomTypeSerializer
    required_permissions = {"list": "inventory.view", "retrieve": "inventory.view", "*": "inventory.manage"}

class TodayView(PropertyScopedAPIView):                # APIView: permisos por método en minúscula
    required_permissions = {"get": "frontdesk.view"}
    def get(self, request): ...                        # request.property / .organization / .membership

class GuestViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):   # filas por organización
    required_permissions = {"*": "guests.view", "create": "guests.manage"}
```

- `X-Property-Id` es obligatorio: sin él → 400 `property_required`; propiedad ajena, UUID inválido o membership
  restringida a otra propiedad → 404; permiso faltante → 403 `{"code": "permission_denied", "permission": "<code>"}`;
  organización `suspended` → 402 `organization_suspended` (salvo `allow_suspended = True` en la vista, p. ej. billing).
- Modelos sin FK directa a `property` (p. ej. `RoomBlock`): `property_field = "room__property"` y sobrescribe
  `perform_create` (el mixin solo inyecta `property=` cuando `property_field == "property"`).
- Nunca confíes en un `property`/`property_id` del body.
- `PropertyScopedMixin` ya documenta el header `X-Property-Id` en `/api/docs/` (schema propio
  `PropertyScopedAutoSchema`). En `APIView` usa `@extend_schema(request=..., responses=...)` para que el schema no
  muestre errores (ver `apps/accounts/api/views.py`).
- Vistas públicas: `authentication_classes = []`, `permission_classes = [AllowAny]`, en `public_urls.py`.

### Errores (spec §3.1)

Toda respuesta de error es `{"detail": str, "code": str, "fields"?: {...}, ...extra}` (`apps/core/api/exceptions.py`):

| Origen | HTTP | code |
|---|---|---|
| `DomainError(msg, code=..., **extra)` y subclases | `status_code` de la clase | su `code`; `extra` va en el JSON (Decimal → `"150000.00"`, fechas ISO, UUID str) |
| `serializers.ValidationError` con campos | 400 | `validation_error` + `fields: {campo: [msgs]}` (`detail` = primer mensaje) |
| `ValidationError("msg", code="x")` sin campos | 400 | `x` (o `validation_error` si el code es genérico) |
| `ValidationError({"detail": ..., "code": ...})` | 400 | el `code` dado |
| Django `ValidationError` / `Http404` / `PermissionDenied` | 400 / 404 / 403 | `validation_error` / `not_found` / `permission_denied` |
| Anónimo en endpoint protegido | **401** | `not_authenticated` (header `WWW-Authenticate: Session realm="api"`) |
| Sesión sin token CSRF en escritura | 403 | `csrf_failed` |
| Violación de exclusión o unique en BD (`IntegrityError` 23P01/23505) | 409 | `conflict` |
| Borrar fila referenciada (`ProtectedError`/`RestrictedError`) | 409 | `in_use` |
| Cualquier otra excepción | 500 | (no se oculta) |

Para errores de validación de dominio con campos: `DomainError("…", code="invalid_custom_values", fields={...})`.
Mensajes en español, `code` estable en inglés.

### Convenciones de datos

- **Rangos**: todos los `start, end` de contratos y señales son semiabiertos `[start, end)` (igual que
  `checkin`/`checkout`). Excepción: `Season.end_date` es inclusivo. `RoomBlock.end_date` es exclusivo.
- **Dinero**: `Decimal`; `apps.core.money.quantize(x, currency)` (COP → pesos enteros, `ROUND_HALF_UP`),
  `D(x)`, `apply_percent(x, pct)`, `percent_of(x, pct)`, `money_field()` = `DecimalField(14, 2)`. En JSON, strings.
- **i18n de datos**: `i18n_field()` (JSON `{"es","en"}`) y `apps.core.i18n.t(value, lang)`.
- **Códigos legibles**: `apps.core.codes.generate_code(prefix="HT", length=6)` (sin 0/O/1/I/L).
  `Reservation.code` se autogenera en `save()` si viene vacío (colisión → `IntegrityError`; B2b reintenta).
- **Fechas**: `apps.core.dates.nights(checkin, checkout)`, `daterange(start, end_exclusive)`,
  `overlaps(a_start, a_end, b_start, b_end)`, `property_now(property)`.

### Factories y fixtures

- `backend/conftest.py`: `organization` (activa, con roles de sistema), `prop`, `make_member(role_code="owner", *,
  properties=None, org=None, **user_kwargs)`, `owner`, `api_for(user, prop)` (APIClient con `force_authenticate` +
  `X-Property-Id`), `api` (owner en `prop`), `public_api`. Un autouse limpia la caché (throttles) entre tests.
- `apps/<app>/tests/factories.py`:
  - core: `OrganizationFactory` (status `active`), `PropertyFactory`.
  - accounts: `UserFactory` (clave `pass1234`), `RoleFactory`, `MembershipFactory`.
  - inventory: `AmenityFactory`, `RoomTypeFactory` (privada), `DormRoomTypeFactory`, `RoomFactory`, `BedFactory`
    (en un dorm), `RoomBlockFactory`. **La propiedad de una habitación sale de su categoría**:
    `RoomFactory(room_type=rt)` o `RoomFactory(room_type__property=prop)`.
  - rates: `TaxFactory` (IVA 19 % excluido, exento a extranjeros), `CancellationPolicyFactory`, `RatePlanFactory`
    (`room_types=[...]`), `DerivedRatePlanFactory` (−12 %), `RoomTypeRateDefaultsFactory` (320.000),
    `DailyRateFactory`, `ExtraFactory`.
  - guests: `GuestFactory` (colombiano residente), `ForeignGuestFactory` (US/US, pasaporte).
  - bookings: `ReservationGroupFactory`, `ReservationFactory` (booker en la org de la propiedad),
    `StayFactory` (categoría y plan en la propiedad de la reserva; `room=None` por defecto; `occupants=[...]`).
  - finance: `FolioFactory` (de una reserva; casa: `FolioFactory(reservation=None, property=prop)`),
    `ChargeFactory`, `PaymentFactory`.
- Señales en tests: `django_capture_on_commit_callbacks(execute=True)`.

---

## API implementada

| Método y path | Auth | Descripción |
|---|---|---|
| `GET /api/v1/public/core/health/` | pública | `{"status": "ok"}` (sin BD ni sesión) |
| `GET /api/v1/accounts/auth/csrf/` | pública | pone la cookie `csrftoken` (legible por JS) y responde `{"csrf_token": "..."}` |
| `POST /api/v1/accounts/auth/login/` | pública + **CSRF** | `{email, password}` → `Me` + cookie `sessionid`. Email sin distinguir mayúsculas. Errores: 400 `invalid_credentials`, 400 `validation_error`, 403 `csrf_failed`, 429 `throttled` (10/min por IP) |
| `POST /api/v1/accounts/auth/logout/` | cualquiera (CSRF si hay sesión) | 204 (idempotente) |
| `GET /api/v1/accounts/me/` | sesión | `Me` |
| `PATCH /api/v1/accounts/me/` | sesión + CSRF | solo `full_name`, `language` (`es`/`en`), `phone` → `Me`; otros campos se ignoran |
| `GET /api/v1/core/context/` | sesión + `X-Property-Id` | **(A3)** `{property, organization, role, permissions}` de la propiedad activa (mismas formas que en `Me`); cualquier miembro con acceso; 400/404/402 según las reglas de tenancy |
| `GET /api/docs/`, `GET /api/schema/` | pública | Swagger / OpenAPI (sin warnings al generar) |
| `/django-admin/` | superusuario | admin de Django con todos los modelos núcleo |

`Me` (forma del spec §3 + `phone`, agregado en A3 porque el `PATCH` lo escribe; login cambia el token CSRF → el
cliente debe releer la cookie):

```json
{
  "id": "85d089f8-…", "email": "owner@casaaurora.co", "full_name": "Valentina Rojas", "language": "es",
  "phone": "", "is_platform_admin": false,
  "memberships": [{
    "organization": {"id": "…", "name": "Casa Aurora", "slug": "casa-aurora", "status": "active"},
    "role": {"id": "…", "name": "Dueño", "code": "owner"},
    "permissions": ["*"],
    "properties": [{"id": "…", "name": "Hotel Casa Aurora", "slug": "casa-aurora", "property_type": "boutique",
                    "timezone": "America/Bogota", "currency": "COP", "business_date": "2026-09-25"}]
  }]
}
```

Solo memberships activas, ordenadas por nombre de organización; `properties` = todas las de la org si
`all_properties`, si no las asignadas (ordenadas por nombre). Los permisos se exponen tal cual (patrones incluidos).

---

## Contratos implementados / consumidos

Nivel de implementación en la Fase A (plan Step 5). "Stub" = firma exacta + docstring + `NotImplementedError`.

| Contrato | Fase A | Completa |
|---|---|---|
| `rates.services.quote.quote(*, property, room_type, rate_plan, checkin, checkout, adults, children=0, children_ages=None, promo_code=None, guest_is_foreign_non_resident=False) -> Quote` | Simple (ver abajo) | B2a |
| `rates.services.quote.resolve_daily(room_type, rate_plan, start, end) -> list[DayRate]` | DailyRate → defaults → 0 | B2a |
| `rates.services.quote.set_daily_rates(*, property, room_type, rate_plan, start, end, price=None, restrictions=None, dow=None, source="manual", actor=None) -> int` | Simple + `rates_changed` | B2a |
| `rates.services.provision.provision_rates(property, *, room_type_prices, plans=None, taxes_default=True, policies_default=True, actor=None)` | Stub | B2a |
| `bookings.services.availability.availability(*, property, checkin, checkout, room_type_ids=None) -> dict[UUID, int]` | Correcto pero lento (desde tablas) | B2b |
| `bookings.services.availability.search_offers(...) -> list[Offer]` | Stub | B2b |
| `bookings.services.reservations.{create_reservation, modify_stay, cancel_reservation, assign_room, auto_assign_rooms, check_in, check_out, mark_no_show}` | Stubs | B2b |
| `bookings.services.charges.post_room_charges(stay, *, until_date, actor=None, source="automation")` | Stub | B2b |
| `finance.services.get_or_create_folio / post_charge / record_payment / folio_balance / reservation_balance` | Implementados | B4 |
| `finance.services.void_charge / refund_payment / create_payment_intent / sync_payment_intent` | Stubs | B4 |
| `inventory.services.effective_attributes / block_room / release_block / set_housekeeping_status / validate_custom_values` | Implementados | B1 |
| `inventory.services.provision_room_type(property, *, data, room_numbers, floor=None, beds_per_room=None, actor=None)` | Stub | B1 |
| `guests.services.upsert_guest / update_guest / add_document` | Simples | B3 |
| `guests.services.find_duplicates / merge_guests` | Stubs | B3 |
| `messaging.services.send_message(*, property, template_code, guest=None, reservation=None, to=None, channels=("email",), context=None, language=None) -> list[OutboundMessage]` | Stub: registra en log (sin datos del destinatario) y devuelve `[]` | C6 |
| `ai.llm.get_llm(property=None) -> LLMClient` | Siempre `SimulatedLLMClient` (`"(modo simulado) …"`) | C9 |
| `core.tokens.make_reservation_token / read_reservation_token(token, *, max_age=None) / portal_url` | Implementados | — |
| `core.audit / alerts / integrations / automation / permissions / signals` (spec §4.2) | Implementados | — |

Tipos compartidos (dataclasses, exactamente los del plan): `apps/rates/types.py` (`NightPrice`, `TaxLine`, `DayRate`,
`Quote` con `to_dict()` JSON-safe y dinero `"0.00"`), `apps/bookings/types.py` (`StayRequest`, `ReservationRequest`,
`Offer`, `AssignmentReport` + errores `BookingError` 400, `AvailabilityError` 409 `no_availability`,
`RestrictionError` 400 `restriction_violation`, `InvalidStateError` 409, `RoomNotReadyError` 409, `BalanceDueError`
409), `apps/guests/types.py` (`GuestInput`), `apps/ai/types.py` (`ToolCall`, `LLMResult`, `LLMClient`), y
**`apps/messaging/types.py` (`OutboundMessage`: channel, to, status, subject, body, template_code,
provider_message_id, error, message_id)** — el spec nombra el tipo sin definirlo; C6 puede ampliarlo.

### Semántica de lo implementado (para no romperla al completar)

- **`quote` (Fase A)**: precio por noche del plan **base** (`DailyRate` → `RoomTypeRateDefaults.price` → 0);
  derivado: `percent` → `precio × (1 + v/100)`, `amount` → `precio + v` (mín. 0); redondeo por noche y totales con
  `quantize`. Impuestos: `Tax` activos con `applies_to` `room`/`all`, ordenados por `code`; excluidos suman a
  `tax_total` (`subtotal × rate/100`), incluidos son informativos (`subtotal − subtotal/(1+rate)`), extranjero no
  residente con `exempt_foreign_non_residents` → línea `amount=0, exempt=True`. `violations`: `invalid_dates`
  (sin noches; `restrictions_ok=False`), `stop_sell` (restricción → `restrictions_ok=False`) y `no_rate` (aviso: no
  hay precio configurado; **no** cambia `restrictions_ok`). No aplica aún: temporadas, DOW, extras de ocupación,
  ocupación sencilla, promos (ignora `promo_code`), CTA/CTD/LOS.
- **`resolve_daily`**: resuelve contra `rate_plan.base_plan`; si el plan es derivado devuelve el precio derivado (sin
  redondear) con las restricciones del base. `source` = fuente del `DailyRate`, `"default"` o `"none"` (sin precio).
  Extras de adulto/niño: los del `DailyRate` o, si son null, los de `RoomTypeRateDefaults`.
- **`set_daily_rates`**: solo planes base (derivado → `derived_plan_not_editable`). `restrictions` acepta los nombres
  de campo del modelo (`min_los`, `max_los`, `closed_to_arrival`, `closed_to_departure`, `stop_sell`) más
  `price_delta_percent` / `price_delta_amount`; otra clave → `invalid_restriction`. `dow` = lista 0–6 (lunes = 0).
  Crea filas faltantes con el precio resuelto; precio final redondeado a la moneda. Devuelve cuántas noches escribió
  y, si > 0, emite `rates_changed(property, room_type_ids=[rt.pk], rate_plan_ids=[plan.pk], start, end)`. Aún sin
  audit reversible (B2a).
- **`availability`**: por categoría **activa**: unidades activas (habitaciones activas; en dorm, camas activas de
  habitaciones activas) − stays activas (`tentative|confirmed|checked_in`) que cubren la noche (asignadas o no) −
  bloqueos activos (bloqueo de habitación dorm = todas sus camas activas; de cama = 1); mínimo sobre las noches.
  **Puede ser negativo** (sobreventa). Rango vacío → 0 por categoría. `InventoryDay.available` sigue la misma regla.
- **`post_charge`**: `amount` = neto unitario; `unit_price` se guarda a centavos; `Charge.amount =
  quantize(amount × quantity)`; `tax_amount = quantize(neto × tax.rate/100)`, o 0 si `tax_exempt` (el `tax` queda
  referenciado: **exento = `tax` presente y `tax_amount = 0`**, útil para facturas y reporte de IVA). Folio cerrado →
  `folio_closed`; `kind` inválido → `invalid_kind`; `business_date` por defecto = `property.business_date`. Sin audit
  (B4 lo agrega).
- **`record_payment`**: monto redondeado a la moneda y > 0 (`invalid_amount`); valida `method`/`status`;
  `business_date` = de la propiedad; si `status="approved"` emite `payment_received(payment)` al commit.
- **`get_or_create_folio`**: un folio `guest` por reserva (o por `stay` si se pasa); serializa llamadas concurrentes
  bloqueando la reserva.
- **`folio_balance`** = Σ cargos no anulados (neto + IVA) − pagos aprobados + reembolsos aprobados.
- **`reservation_balance`** = Σ `Stay.total_amount` de stays **facturables** (`tentative|confirmed|checked_in|
  checked_out`: todas menos canceladas/no-show; incluye impuestos) + cargos no-`room` no anulados (con IVA) − pagos
  aprobados + reembolsos aprobados, sobre todos los folios de la reserva. Los cargos `room` no se suman (consumen el
  total esperado). Nota: `checked_out` cuenta a propósito (si no, el saldo tras el check-out sería negativo y B4 no
  podría cerrar folios con saldo 0).
- **`effective_attributes(room)`** → dict con todas las claves de `ROOM_OVERRIDABLE_FIELDS` (override o valor de la
  categoría), `amenities` (códigos: categoría + extra − removidas, ordenados), `custom_values` (categoría ⊕
  habitación, gana la habitación), marcadores `overridden_fields`, `amenities_added`, `amenities_removed`,
  `overridden_custom_fields`, e identificadores `room_id`, `room_type_id`, `number`, `room_name` (= `Room.name`),
  `floor`, `building`, `kind`. Claves de override desconocidas se ignoran (`Room.clean()` las rechaza).
- **`block_room`**: valida rango (`invalid_dates`), cama de la misma habitación (`invalid_bed`) y `kind`
  (`invalid_kind`); audita `inventory.room_blocked`; emite `inventory_changed(property, room_type_ids=[...],
  start, end)`. **`release_block`**: idempotente; audita `inventory.block_released`; emite `inventory_changed` una vez.
- **`set_housekeeping_status`**: estado inválido → `invalid_status`; si no cambia no hace nada; si cambia guarda,
  audita `inventory.room_status_changed` (con `source`) y emite `room_status_changed(room, old, new)`.
- **`validate_custom_values(defs, values) -> dict`**: aplica `default_value`; rechaza claves desconocidas,
  requeridos faltantes y tipos inválidos (text: str · number: int/float · boolean: bool · select: valor de
  `options` · multiselect: lista de valores · date: `"AAAA-MM-DD"`). Error: `DomainError(code=
  "invalid_custom_values", fields={clave: [msg]})`. `options` acepta `[{"value": ..., "label": {...}}]` o strings.
- **`upsert_guest(org, GuestInput)`**: normaliza (trim, email en minúsculas, tipo de doc/nacionalidad/residencia en
  mayúsculas); busca por documento (`document_type` + `document_number`); si no hay y viene email, busca por email
  **solo entre huéspedes sin documento** (si viene documento) o entre todos (si no); ignora fusionados; rellena con
  los valores no vacíos (nunca borra); consentimientos solo se otorgan (`data_processing_consent_at` se fija una
  vez). B3 agrega teléfono E.164 y title case.
- **`update_guest(guest, data, *, source, actor)`**: campos editables = datos personales + `gender, address,
  is_vip, tags, notes, preferences, marketing_consent, data_processing_consent_at, custom_values, blacklisted`; otros
  (incl. `organization`, `merged_into`) → `invalid_field`. Audita `guests.guest_updated` con el diff.
- **`add_document`** valida `kind` y `uploaded_via`.
- **`read_reservation_token`** devuelve la reserva (con `property`) o `None` si el token es inválido, alterado, de
  otro salt, expirado (`max_age`) o de una reserva inexistente.

---

## Modelos (spec §4 + plan §C) y decisiones

Todos heredan `BaseModel` (UUID, `created_at`, `updated_at`); choices como `TextChoices` en cada `models.py`.

- Migraciones iniciales regeneradas; `core/0001` arranca con `BtreeGistExtension()`. Test que exige que no haya
  migraciones pendientes: `apps/core/tests/test_migrations.py`.
- `Stay`: sin campo `period`; `CheckConstraint` `stay_dates_valid` y las dos `ExclusionConstraint` del plan
  (`stay_no_room_overlap` cuando `bed IS NULL`, `stay_no_bed_overlap` por cama; estados activos
  `ACTIVE_STAY_STATUSES = ["tentative", "confirmed", "checked_in"]`). Estadía de dorm: `room` = dormitorio,
  `bed` = cama. `Stay.nights` (propiedad). Reservation/Stay comparten `BookingStatus`.
- `Reservation.hold_expires_at`, `Reservation.code` único (autogenerado en `save()`), `CheckConstraint` de fechas.
- `InventoryDay`: único `(room_type, date)`, índice `(property, date)`, propiedad `available` (puede ser negativa).
- `DailyRate`: único `(room_type, rate_plan, date)`; `extra_adult_price`/`extra_child_price` **nullables** (null →
  defaults); `source` por defecto `manual`.
- `RatePlan`: `CheckConstraint` base ⇔ sin `parent`, derivado ⇔ con `parent`; propiedad `base_plan`;
  `channels = []` significa "todos los canales".
- `Guest`: índice único parcial `(organization, document_type, document_number)` si `document_number != ""`;
  `document_type` admite vacío; `gender` ∈ `F|M|X` o vacío; `is_foreign_non_resident` = nacionalidad no vacía y ≠ CO y
  residencia ≠ CO (residencia vacía de un extranjero cuenta como no residente; sin nacionalidad nunca exime).
- `Room`: único `(property, number)`; `Room.clean()` valida claves de `overrides` y que la categoría sea de la misma
  propiedad (llama `full_clean()` o valida en el serializer). `CustomFieldDefinition` único
  `(organization, property, applies_to, key)` con nulls no distintos. `Amenity` único `(organization, code)` (catálogo
  global = `organization` null). `Bed` único `(room, label)`.
- `User.email` se normaliza (trim + minúsculas) en **todo** `save()`; unicidad case-insensitive en BD.
- `on_delete` pensado para historia + reset: `RESTRICT` en referencias que la historia necesita
  (`Room.room_type`, `Stay.room_type/rate_plan/room/bed`, `Reservation.booker`, `Folio.reservation/stay`,
  `RatePlan.parent`) → borrar directo una fila en uso lanza `RestrictedError` (API: 409 `in_use`), pero borrar una
  **organización** borra todo su grafo (lo usa `seed_demo --reset`; test `apps/core/tests/test_cascade.py`).
  `CashShift.user` es `PROTECT`; el resto de referencias a usuarios son `SET_NULL`.
- `Charge.amount` neto, `tax_amount` aparte, propiedad `total`; `Charge.is_voided`.
- Todos los modelos están registrados en el admin de Django (`IntegrationSetting` oculta `secrets_encrypted`,
  `Invitation` oculta `token`).

---

## Señales emitidas / escuchadas

Definidas en `apps/core/signals.py` (spec §4.1); los productores usan `send_on_commit(signal, **kwargs)` (usa
`send_robust`; un receiver que falla se registra en el log `housetel.signals` y no rompe a los demás). Los receivers
reciben `sender=None, signal=..., **kwargs`.

Emitidas por A1: `rates_changed` (`set_daily_rates`), `payment_received` (`record_payment` aprobado),
`inventory_changed` (`block_room`, `release_block`), `room_status_changed` (`set_housekeeping_status`).
Escuchadas: ninguna. `inventory_changed(start=None, end=None)` significa "todo el horizonte".

## Automatizaciones registradas

- `core.cleanup` (plataforma, diario 04:30): borra `AutomationRun` de más de `run_retention_days` (90) y sesiones
  expiradas.

Beat genera su horario estático desde `automation.all()` (`config/celery.py`); cada entrada llama la tarea
`core.run_automation(code)`, que corre la automatización en cada propiedad activa de organizaciones
`trial|active|past_due` donde esté habilitada (o una vez si `scope="platform"`). `automation.run` envuelve en
`AutomationRun`, hace rollback del handler si falla, levanta/resuelve la alerta `automation:<code>` y audita con
`source="automation"`.

## Proveedores de integración registrados

Ninguno (A1 entrega el framework `apps/core/integrations.py`). Sin proveedor registrado, `get_provider` lanza
`IntegrationNotAvailable` (400 `integration_not_available`); si falta el del modo configurado pero existe el
simulado, usa el simulado y levanta la alerta `integration:<kind>:fallback`. Secretos: `set_secrets` (merge; `None`
borra, `""` conserva) cifrados con Fernet (`FERNET_KEY`), `get_secrets` devuelve `{}` si no se pueden descifrar.

## Extensiones de frontend exportadas

No aplica (backend). Para A2: anónimo → **401** (no 403) y CSRF inválido → 403 `csrf_failed`; el login exige
`X-CSRFToken` y **rota** el token (releer la cookie `csrftoken` después del login).

## Dependencias nuevas (pip/npm) y por qué

Ninguna fuera de la lista del plan (`backend/requirements.txt` con rangos `>=x,<y`, versiones actuales).

## Cambios requeridos en archivos compartidos u otras apps

Ninguno pendiente. Desviaciones deliberadas respecto al texto del plan (ya aplicadas, cubiertas por tests):

1. `DEFAULT_AUTHENTICATION_CLASSES` usa `apps.core.api.authentication.SessionAuthentication` (subclase de la de DRF)
   para responder 401 a anónimos y `csrf_failed`; necesario para el contrato de A2 ("401 → /login").
2. `apps.core.middleware.RequestIdMiddleware` (primero en `MIDDLEWARE`): `X-Request-ID` entrante válido o uuid4;
   llena `AuditEvent.request_id` y se devuelve en la respuesta.
3. `docker-compose.yml`: los servicios del backend corren como `${HOST_UID:-1000}:${HOST_GID:-1000}` (los archivos
   creados por el contenedor —migraciones, media— quedan editables en el host), `HOME=/tmp`, y `env_file` con
   `required: false` (Compose ≥ 2.24).
4. `Makefile`: además de los targets del plan, `up-back` (solo backend), `makemigrations`, `check`, `format`, `help`;
   `reset` migra y siembra antes de levantar todo (evita la carrera con el `migrate` del arranque del backend).
5. Seed: `ctx.orgs` usa las claves `"aurora"` y `"andino"`; `limpieza@grupoandino.co` está restringido a Andino
   Medellín (demuestra memberships por propiedad); los datos existentes no se sobrescriben al re-sembrar.

## Seed (para los `seed.py` de cada app)

`apps/core/seed.py`: `SEED_ORDER` (plan Step 8), `SeedContext(today, rng=random.Random(20260925), orgs, properties,
users, data, stdout)` con `ctx.log(msg)`. Claves: `ctx.properties["aurora" | "andino_mde" | "andino_bog"]`,
`ctx.users["admin" | "aurora_owner" | "aurora_front" | "aurora_hk" | "aurora_acct" | "andino_owner" |
"andino_front" | "andino_hk"]`. Cada app define `apps/<app>/seed.py` con `def seed(ctx): ...` idempotente; corre en
su propia transacción, en el orden de `SEED_ORDER`. Un `ModuleNotFoundError` dentro de un seeder existente **no** se
oculta. `apps/core/tests/test_seed.py` aísla los seeders de apps (cada app prueba su seed).

## Verificación (Step 10, corrida real)

- `docker compose build backend` ✓ · `docker compose up -d --build db redis mailpit backend worker beat` ✓
  (backend en 8010; la BD y Redis no se exponen); migraciones aplicadas limpias en la BD de desarrollo.
- `docker compose run --rm -e TEST_DB_NAME=test_a1 backend pytest -q` → **740 passed**.
- `docker compose run --rm backend ruff check .` → `All checks passed!` (y `ruff format --check` limpio).
- `seed_demo` dos veces → mismos conteos: 2 orgs, 3 propiedades, 8 usuarios, 7 memberships, 14 roles.
- curl: `GET auth/csrf/` 200 (cookie) → `POST auth/login/` sin token 403 `csrf_failed`, con token 200 `Me` →
  `GET me/` 200 → `POST auth/logout/` 204 → `GET me/` 401 `not_authenticated`. `GET public/core/health/` 200
  `{"status":"ok"}`; `/api/docs/` y `/api/schema/` 200.
- Beat arriba (`beat: Starting...`), su horario persistido contiene `core.cleanup → core.run_automation
  ('core.cleanup',)` a las 04:30; el worker ejecutó esa tarea encolada (AutomationRun `success` + audit
  `source="automation"`). Sin tracebacks en backend/worker/beat.

## Limitaciones conocidas / pendientes

- Stubs de fase B (ver tabla de contratos): se levantan con `NotImplementedError`.
- `InventoryDay` existe pero nadie lo mantiene todavía (B2b: `rebuild_inventory` + receivers); `availability` de la
  Fase A calcula desde las tablas.
- `post_charge`/`record_payment` no auditan ni exigen turno de caja (B4). `set_daily_rates` aún sin audit
  reversible ni undo (B2a).
- Los archivos subidos (fotos, documentos de huéspedes) se sirven en `/media/` sin autenticación mientras
  `DEBUG=1` (helper `static()` de Django). Para documentos de identidad, B3/C5 deberían servirlos por una vista
  autenticada.
- `get_llm` siempre devuelve el cliente simulado (C9 conecta Gemini/Claude según `IntegrationSetting(kind="llm")`).
