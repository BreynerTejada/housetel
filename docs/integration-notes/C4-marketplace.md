# C4 — Marketplace y booking engine — integration notes

Estado: **MVP completo de punta a punta** (backend, API pública y de staff, frontend, seed) en **modo MVP sin
tests** (decisión del usuario: los tests se escriben después de validar en Chrome). Esta corrida retomó el
trabajo parcial de intentos anteriores: se evaluó todo, se completó lo que faltaba (las rutas del frontend
seguían siendo los stubs de A2), se corrigió lint/ruff y se hicieron ajustes menores (ver "Qué cambió en esta
corrida"). Verificación mínima hecha: `manage.py check`, migración al día, smoke con curl por el proxy de Vite
contra el seed, seed probado con rollback, `tsc` y `eslint` de la feature limpios, y una revisión visual rápida
con un Chrome headless propio (no el compartido).

Owner paths: `backend/apps/marketplace/**`, `frontend/src/features/marketplace/**` y esta nota. Excepción
autorizada por el plan: C4 escribe `Property.marketplace_listed` (listing) y `Property.branding["primary_color"]`
(el color del motor es también la marca del hotel que usan el portal y la pasarela).

Leer primero: **"Cómo probarlo en la UI"** (para la validación en Chrome) y **"Cambios requeridos en archivos
compartidos"** (para C-INT).

---

## Qué cambió en esta corrida

- `frontend/src/features/marketplace/routes.tsx`: conectadas todas las páginas (antes seguían los stubs
  `UnderConstruction`), incluidas `/h/:slug/book` y `/h/:slug/booking/:code` (sin chrome de Housetel).
- ESLint de la feature en 0: componente `AmenityIcon` (ícono estable, sin crear componentes en render) y helpers
  no-componente fuera de los archivos de componentes (`activeFilterCount` → `lib/search-params.ts`).
- Ruff de la app en 0 (líneas > 110) y `ruff format` limpio.
- Throttle de reservas públicas 20/h → **60/h por IP** (detrás del proxy de Vite todos los clientes comparten IP).
- Caché de búsqueda **versionada**: al guardar listing o motor se invalida al instante (antes hasta 60 s).
- El detalle público ya no expone el campo interno `amenity_codes`.
- `apps/marketplace/admin.py` (motor y ficha, con fotos destacadas en línea).
- Placeholder del código promocional sin forzar mayúsculas.

---

## API implementada

### Pública — `/api/v1/public/marketplace/` (sin sesión)

Throttles por IP definidos en las clases: lecturas 240/min, cotización 120/min, reservas 60/h, lookup 30/min.
Errores con la forma del core `{detail, code, fields?, ...extra}`.

| Método y path | Descripción |
|---|---|
| `GET destinations/` | Ciudades con hoteles listados, más hoteles primero: `[{city, department, properties_count, cover_photo}]` |
| `GET search/?city&checkin&checkout&adults&children&children_ages&type&stars&amenities&min_price&max_price&sort` | Hoteles listados de la ciudad (sin tildes ni mayúsculas); con fechas, solo los que tienen oferta vendible, con la más barata. Caché 60 s por combinación (versionada) |
| `GET properties/<slug>/?via=marketplace\|booking_engine` | Página pública del hotel (404 si ese canal no lo vende) |
| `GET properties/<slug>/offers/?checkin&checkout&adults&children&children_ages&promo_code&via&foreign` | Ofertas reservables (categoría × plan) con el total exacto |
| `POST checkout/quote/` | **(extra del plan)** cotización exacta de una selección (habitaciones, extras, promo, exención de IVA) sin escribir nada |
| `POST bookings/` | Crea la reserva (y el link de pago si se paga algo ahora) → 201 |
| `GET bookings/<code>/?email=` | Estado para la página de confirmación (404 si el email no es el del titular) |
| `GET properties/<slug>/booking-engine/` | Marca y configuración pública del motor (`/h/<slug>`, `/embed/<slug>`) |

Reglas comunes (servicio `engine`):
- Vende una propiedad `active` de una organización `trial|active|past_due`. Marketplace exige
  `Property.marketplace_listed`; booking engine exige `BookingEngineSettings.enabled` (por defecto true, sin fila).
- **Ventana de reserva en línea** (para ambos canales): llegada desde la fecha local de `ahora + min_advance_hours`
  hasta `hoy + max_advance_days`, máximo 30 noches. Errores 400: `invalid_dates`, `too_soon` (+`earliest_checkin`),
  `too_far` (+`latest_checkin`), `stay_too_long` (+`max_nights`). Las queries rechazan llegadas en el pasado
  (`validation_error` en `checkin`).
- Planes vendibles: activos, `is_public`, cuyo `channels` está vacío o incluye el canal; en el booking engine,
  además, solo los `allowed_rate_plans` (vacío = todos). Planes con `deposit_percent > 0` se ocultan si los pagos
  en línea están desactivados (`IntegrationSetting(payments).enabled = False`).

#### `GET search/` (respuesta real, recortada)

`type` (repetible) ∈ `hotel|hostel|boutique|aparthotel|glamping`; `stars` exactas (repetible); `amenities`
(el hotel debe tenerlas todas; códigos, repetible o separados por coma); `min_price`/`max_price` = precio por
noche; `sort` ∈ `recommended|price|-price|stars`. Sin fechas: todos los listados con `offer: null`.
`facets` salen de los hoteles listados del destino (no cambian con filtros ni fechas).

```json
{"count": 1, "city": "Cartagena", "checkin": "2026-11-13", "checkout": "2026-11-15", "nights": 2, "adults": 2, "children": 0,
 "results": [{"slug": "casa-aurora", "name": "Hotel Casa Aurora", "property_type": "boutique", "star_rating": 4,
   "city": "Cartagena", "department": "Bolívar", "neighborhood": "Centro Histórico",
   "tagline": {"es": "Casa colonial restaurada…", "en": "…"}, "highlights": [{"es": "…", "en": "…"}],
   "photo": "/media/photos/seed/casa-aurora-1.jpg", "photos": ["…4 máx."],
   "amenities": [{"code": "wifi", "name": {"es": "Wifi", "en": "Wi-Fi"}, "icon": "wifi", "category": "room"}],
   "currency": "COP",
   "offer": {"room_type": {"id": "…", "code": "DBL", "name": {"es": "Estándar", "en": "Standard"}},
             "rate_plan": {"id": "…", "code": "NR", "name": {"es": "No reembolsable", "en": "Non-refundable"}, "meal_plan": "room_only"},
             "total": "770740.00", "per_night": "385370.00", "currency": "COP", "available_units": 3, "units_needed": 1,
             "taxes_included": true}}],
 "facets": {"types": [{"value": "boutique", "count": 1}], "stars": [{"value": 4, "count": 1}],
            "amenities": [{"code": "air_conditioning", "name": {"es": "Aire acondicionado", "en": "…"}, "icon": "air-vent", "category": "room", "count": 1}]}}
```

#### `GET properties/<slug>/`

Tarjeta + `description, address, country, latitude, longitude, phone, email, website, rnt_number,
check_in_time, check_out_time, house_rules, policies{pets_allowed, smoking_allowed, children_allowed,
events_allowed, min_checkin_age}, languages, amenities (todas, hotel + categorías), photos [{id, url, caption}]
(destacadas en orden → galería → categorías), hero_image, room_types, cancellation_policies (de los planes del
canal), extras (vendibles en línea: {id, code, name, price, charge_type, tax_rate, tax_included}), headline,
terms, booking {earliest_checkin, latest_checkin, max_nights, min_advance_hours, max_advance_days,
show_promo_field, online_payments}, brand {primary_color, logo}, marketplace_listed, booking_engine_enabled,
via`. Categoría (solo las que vende algún plan del canal):

```json
{"id": "…", "code": "DBL", "name": {"es": "Estándar", "en": "Standard"}, "description": {"es": "…", "en": "…"},
 "kind": "private", "base_occupancy": 2, "max_adults": 2, "max_children": 1, "max_occupancy": 3,
 "beds": [{"type": "queen", "count": 1}], "size_m2": "22.00", "size_m2_range": null, "views": ["city"],
 "smoking_allowed": false, "accessible": false,
 "amenities": [{"code": "air_conditioning", "…": "…"}],            // las de la mayoría de sus habitaciones
 "photos": [{"id": "…", "url": "/media/photos/seed/casa-aurora-dbl-1.jpg", "caption": {"es": "…", "en": "…"}}],
 "features": [{"key": "orientation", "label": {"es": "Orientación", "en": "Orientation"}, "field_type": "select",
               "value": "city", "display": [{"es": "Ciudad", "en": "City"}]}],   // CustomFieldDefinition.show_in_marketplace
 "units_count": 10}
```

#### `GET properties/<slug>/offers/`

`search_offers(channel=via)` + filtros del canal. El total de cada oferta usa las **mismas noches que guarda
`create_reservation`** (IVA redondeado por noche), así que puede diferir en $1 de `quote.total` (IVA redondeado
sobre el subtotal): lo que ve el huésped es lo que cobra la reserva. `foreign=true` cotiza sin IVA de alojamiento.

```json
{"checkin": "2026-11-13", "checkout": "2026-11-15", "nights": 2, "adults": 2, "children": 0, "currency": "COP",
 "tax_exempt": false, "online_payments": true, "promo": null,             // o {"code": "BIENVENIDA10", "applied": true}
 "offers": [{"room_type_id": "…", "rate_plan_id": "…",
   "room_type": {"id": "…", "code": "DBL", "name": {…}, "kind": "private", "max_adults": 2, "max_children": 1, "max_occupancy": 3, "photo": "/media/…"},
   "rate_plan": {"id": "…", "code": "NR", "name": {…}, "meal_plan": "room_only", "deposit_percent": "0.00", "requires_payment": false,
                 "cancellation_policy": {"id": "…", "name": {…}, "description": {…}, "non_refundable": true, "free_until_hours_before": 0, "penalty_type": "full", "penalty_value": "0.00"}},
   "available_units": 3, "units_needed": 1, "max_quantity": 3,
   "quote": {"nights": [{"date": "2026-11-13", "base": "323840.00", "extra_adults": "0.00", "extra_children": "0.00", "discount": "0.00", "total": "323840.00"}], "…": "Quote.to_dict() por unidad"},
   "net_total": "647680.00", "tax_total": "123060.00", "total": "770740.00", "per_night": "385370.00",
   "tax_exempt": false, "promo_applied": null}]}
```

Dormitorio: `units_needed = adultos + niños` (una cama por persona) y la cotización es por cama.

#### `POST checkout/quote/` y `POST bookings/`

```json
{"property_slug": "casa-aurora", "via": "marketplace",                 // o "booking_engine"
 "checkin": "2026-11-13", "checkout": "2026-11-15",
 "items": [{"room_type_id": "…", "rate_plan_id": "…", "quantity": 1, "adults": 2, "children": 0, "children_ages": []}],
 "extras": [{"extra_id": "…", "quantity": null}],                        // null = regla del hotel (estadía/noche/persona/persona-noche)
 "promo_code": "", "payment_option": "pay_at_hotel",                     // o "pay_now"
 "guest": {"nationality": "US", "country_of_residence": "US"}}           // quote: solo esto; decide la exención de IVA
```

`POST bookings/` agrega `guest` completo (`first_name, last_name, email, phone, nationality,
country_of_residence` obligatorios; `document_type`, `document_number`, `city_of_residence` opcionales;
`data_processing_consent: true` **obligatorio** (Ley 1581) y `marketing_consent`), `special_requests`,
`eta` (`"HH:MM"` o null) y `language` (`es|en`). `items` 1–10, `quantity` 1–10, cada extra una sola vez.

Respuesta de la cotización (real, huésped US/US: alojamiento exento, el desayuno sigue gravado):

```json
{"property_slug": "casa-aurora", "via": "marketplace", "checkin": "2026-11-13", "checkout": "2026-11-15", "nights": 2,
 "currency": "COP", "tax_exempt": true,
 "items": [{"room_type_id": "…", "rate_plan_id": "…", "room_type_name": {…}, "room_type_kind": "private", "rate_plan_name": {…},
            "meal_plan": "room_only", "quantity": 1, "adults": 2, "children": 0, "units": 1,
            "net": "736000.00", "tax": "0.00", "total": "736000.00", "discount": "0.00", "deposit": "0.00",
            "deposit_percent": "0.00", "cancellation_policy": {…}}],
 "extras": [{"extra_id": "…", "code": "BREAKFAST", "name": {…}, "charge_type": "per_person_night", "quantity": 4,
             "unit_price": "35000.00", "net": "140000.00", "tax": "26600.00", "total": "166600.00", "tax_exempt": false}],
 "lodging_total": "736000.00", "extras_total": "166600.00", "tax_total": "26600.00", "discount_total": "0.00",
 "total": "902600.00", "deposit_total": "0.00", "requires_payment": false,
 "due_now": {"pay_now": "902600.00", "pay_at_hotel": "0.00"}, "payment_option": "pay_at_hotel",
 "amount_due_now": "0.00", "promo": null, "online_payments": true}
```

Reserva (`create_booking`):
- `pay_now` paga **todo** ahora; `pay_at_hotel` paga ahora solo el **depósito** de los planes que lo piden
  (`deposit_percent`), si no, nada.
- Si hay algo que pagar ahora → reserva `tentative`, `hold_minutes = 45` (≥ 30: PSE cabe; el link vence con el
  hold), `guarantee = "deposit"` y `finance.create_payment_intent(folio, amount, return_url = FRONTEND_URL +
  confirmation_path)`. El pago aprobado confirma la reserva vía el receiver `payment_received` de B2b. Si no hay
  nada que pagar → `confirmed`.
- `source` = `via` (`marketplace` | `booking_engine`); extras publicados como cargos con
  `finance.post_extra_charge(source="guest")`; todo en una transacción (si el link no se puede crear, no queda la
  reserva).
- `confirmation_path`: marketplace `/booking/<code>/confirmed`; booking engine `/h/<slug>/booking/<code>`.

```json
// 201 pagar en el hotel                                          // 201 pagar ahora
{"reservation_code": "HT-QS872J", "status": "confirmed",          {"reservation_code": "HT-WW4G2D", "status": "tentative",
 "via": "marketplace", "currency": "COP", "total": "1042440.00",   "via": "booking_engine", "total": "966000.00",
 "amount_due_now": "0.00", "payment": null,                         "amount_due_now": "966000.00",
 "hold_expires_at": null,                                           "payment": {"checkout_url": "http://localhost:5173/sim/pay/HT-WW4G2D-HSJP5K",
 "portal_url": "http://localhost:5173/g/<token>",                               "reference": "HT-WW4G2D-HSJP5K", "amount": "966000.00", "expires_at": "…"},
 "confirmation_path": "/booking/HT-QS872J/confirmed"}               "hold_expires_at": "…+45 min", "portal_url": "…",
                                                                    "confirmation_path": "/h/casa-aurora/booking/HT-WW4G2D"}
```

Errores de quote/bookings: 400 `validation_error` (+`fields`, p. ej. `fields.guest.data_processing_consent`),
`invalid_room_type`, `invalid_rate_plan`, `capacity_exceeded`, `restriction_violation` (+`violations`),
`no_rate`, `promo_invalid`, `invalid_extra`, `invalid_channel` y los de la ventana; 404 `not_found` /
`booking_engine_disabled`; 409 `no_availability` (+`shortfalls: [{room_type_id, available, requested}]`),
`online_payments_disabled`; 429 `throttled`.

#### `GET bookings/<code>/?email=`

Solo reservas `marketplace`/`booking_engine`; código y email sin distinguir mayúsculas; código inexistente y
email equivocado responden el mismo 404 (`"No encontramos una reserva con ese código y ese correo"`).

```json
{"code": "HT-WW4G2D", "status": "confirmed", "via": "booking_engine",
 "property": {"slug": "casa-aurora", "name": "Hotel Casa Aurora", "city": "Cartagena", "address": "…", "phone": "…", "email": "…",
              "timezone": "America/Bogota", "check_in_time": "15:00", "check_out_time": "12:00", "primary_color": "#0E6E74", "logo": ""},
 "checkin": "2026-11-06", "checkout": "2026-11-08", "nights": 2, "adults": 2, "children": 0, "currency": "COP",
 "booker": {"first_name": "Smoke", "last_name": "Engine", "email": "smoke.c4.engine@example.com"},
 "rooms": [{"room_type_name": {…}, "room_type_kind": "private", "rate_plan_name": {…}, "meal_plan": "room_only",
            "units": 1, "adults": 2, "children": 0, "total": "966000.00"}],
 "extras": [{"description": "Desayuno", "quantity": 4, "total": "166600.00"}],
 "total": "966000.00", "paid": "966000.00", "balance": "0.00", "tax_exempt": true,
 "cancellation_policy": {…snapshot…}, "hold_expires_at": null, "special_requests": "", "eta": null,
 "payment": {"reference": "HT-WW4G2D-HSJP5K", "status": "approved", "amount": "966000.00", "checkout_url": null, "expires_at": "…"},
 "portal_url": "http://localhost:5173/g/<token>", "confirmation_path": "/h/casa-aurora/booking/HT-WW4G2D", "created_at": "…"}
```

`payment.status` ∈ `created|pending|approved|declined|expired|error` (un link sin pagar pasado su vencimiento sale
`expired`); `checkout_url` solo mientras el link está abierto (para "Pagar"/"Reintentar").

#### `GET properties/<slug>/booking-engine/`

```json
{"slug": "casa-aurora", "name": "Hotel Casa Aurora", "city": "Cartagena", "department": "Bolívar", "property_type": "boutique",
 "star_rating": 4, "address": "…", "phone": "…", "email": "…", "currency": "COP", "enabled": true,
 "primary_color": "#0E6E74", "logo": "", "hero_image": "/media/…", "headline": {"es": "…", "en": "…"},
 "show_promo_field": true, "terms": {"es": "…", "en": "…"},
 "booking": {"earliest_checkin": "2026-09-27", "latest_checkin": "2027-09-27", "max_nights": 30, "online_payments": true},
 "languages": ["es", "en"]}
```

Con el motor apagado responde igual con `enabled: false` (la página muestra "no recibe reservas" y el contacto);
404 si la propiedad no existe o no vende.

### Staff — `/api/v1/marketplace/` (sesión + `X-Property-Id` + `marketplace.manage`)

| Método y path | Descripción |
|---|---|
| `GET booking-engine/` | Configuración del motor + planes seleccionables + URLs |
| `PATCH booking-engine/` | `enabled`, `primary_color` (`#RRGGBB`; también se escribe en `Property.branding`), `headline{es,en}` ≤ 120, `show_promo_field`, `allowed_rate_plans [uuid]` (públicos y activos de la propiedad; `[]` = todos), `min_advance_hours` 0–720, `max_advance_days` 1–730, `terms{es,en}` ≤ 2000 |
| `POST/DELETE booking-engine/logo/` · `booking-engine/hero/` | multipart `image` (JPG/PNG/WEBP ≤ 10 MB) → configuración; el archivo anterior se borra al hacer commit |
| `GET/PATCH listing/` | `marketplace_listed` (escribe `Property.marketplace_listed`), `tagline{es,en}` ≤ 140, `highlights [{es,en}]` ≤ 6 × 120, `neighborhood` ≤ 100, `featured_photo_ids [uuid]` ≤ 12 (fotos del hotel o de sus categorías; el orden es el de la lista, la primera es la portada) |
| `GET embed-snippet/` | `{engine_url, embed_url, iframe, button}` (HTML listo para copiar) |

Sin permiso → 403 `permission_denied` (`permission: "marketplace.manage"`); anónimo → 401; color inválido → 400
`validation_error` en `primary_color`. Toda escritura se audita: `marketplace.booking_engine_updated` (con diff),
`marketplace.logo_updated|logo_removed|hero_updated|hero_removed`, `marketplace.listing_updated` (con diff).

```json
// GET booking-engine/
{"enabled": true, "primary_color": "#0E6E74", "logo": "", "logo_is_custom": false, "hero_image": null,
 "headline": {"es": "…", "en": "…"}, "show_promo_field": true, "allowed_rate_plans": [], "min_advance_hours": 0,
 "max_advance_days": 365, "terms": {…},
 "rate_plans": [{"id": "…", "code": "FLEX", "name": {…}, "kind": "base", "channels": [], "sells_on_engine": true}],
 "public_url": "http://localhost:5173/h/casa-aurora", "embed_url": "http://localhost:5173/embed/casa-aurora",
 "property": {"name": "Hotel Casa Aurora", "slug": "casa-aurora", "city": "Cartagena"}}
// GET listing/
{"marketplace_listed": true, "tagline": {…}, "highlights": [{…}], "neighborhood": "Centro Histórico", "featured_photo_ids": ["…"],
 "photos": [{"id": "…", "url": "/media/…", "caption": {…}, "room_type": {"id": "…", "code": "DBL", "name": {…}} | null}],
 "description": {…}, "name": "Hotel Casa Aurora", "city": "Cartagena", "star_rating": 4, "property_type": "boutique",
 "public_url": "http://localhost:5173/hotel/casa-aurora"}
```

## Modelos (migración `marketplace/0001`, ya aplicada)

- `BookingEngineSettings` (1-1 `Property`, `related_name="booking_engine"`): `enabled, primary_color (vacío →
  marca del hotel), logo, hero_image (vacío → primera foto), headline i18n, show_promo_field, allowed_rate_plans
  M2M RatePlan (vacío = todos los públicos), min_advance_hours, max_advance_days (365), terms i18n`.
- `ListingContent` (1-1 `Property`, `related_name="listing"`): `featured_photos` (M2M `Photo` vía
  `ListingPhoto` con `sort_order`), `tagline` i18n, `highlights` JSON, `neighborhood`.
- Las filas son opcionales: sin ellas se usan los valores por defecto (las lecturas públicas nunca escriben).

## Contratos implementados / consumidos

No implementa contratos del spec. Consume (solo por servicios): `bookings.services.availability.search_offers`
y `availability`, `bookings.services.reservations.create_reservation` (con `status`, `hold_minutes`,
`guarantee`), `bookings.services.pricing` (`lodging_tax`, `night_entry`, `tax_exempt`, `QUOTE_WARNINGS`),
`rates.services.quote.quote`, `finance.services` (`get_or_create_folio`, `post_extra_charge`,
`reservation_balance`, `create_payment_intent`, `extra_unit_net`, `intent_is_stale`), `core.tokens.portal_url`,
`core.audit`, `inventory.services.effective_attributes` (lectura) y lectura por ORM de inventario, tarifas,
reservas y pagos. El titular se crea/actualiza con `upsert_guest` dentro de `create_reservation`.

## Señales emitidas / escuchadas

C4 no emite ni escucha señales propias. Sus reservas pasan por `create_reservation`, que emite
`reservation_created` (con `source = marketplace | booking_engine`) e `inventory_changed`; el pago aprobado emite
`payment_received` y B2b confirma la tentativa. El seed actualiza el motor dentro de `seeding()`; su único efecto
al commit es invalidar la caché de búsqueda.

## Automatizaciones registradas

Ninguna. Las tentativas vencidas las cancela `bookings.release_expired_tentative` y los links vencidos los cierra
`finance.sync_pending_intents`.

## Proveedores de integración registrados

Ninguno. Los pagos usan el proveedor `payments` de B4 (simulado por defecto → `/sim/pay/<ref>`; Wompi real con
llaves).

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

Rutas (`routes.tsx`, todas `lazy`): `public` `/`, `/search`, `/hotel/:slug`, `/book/:slug`,
`/booking/:code/confirmed`, `/h/:slug`, `/h/:slug/book`, `/h/:slug/booking/:code` (las tres `/h/*` con
`handle: {chrome: 'none'}`); `bare` `/embed/:slug`; `app` `settings/booking-engine`. `nav.ts` sin cambios. No
exporta widgets, tabs, acciones, topbar ni comandos.

Piezas reutilizables (import directo):
- `lib/brand.ts`: `brandStyle(color)` (deriva todos los tokens de acento del color del hotel, con texto legible) y
  `lib/useBrandTheme.ts`: `useBrandTheme(color)` (pinta el documento, incluidos portales). **C5** puede usarlo para
  el portal con `Property.branding.primary_color`.
- `lib/text.ts`: `policySummary(policy, t)` / `components/RoomTypeCard.tsx` `PolicyLine` (política de cancelación
  en palabras del huésped), `tr(i18n, lang)`, `bedsLabel`, `guestsLabel`.
- `lib/ics.ts`: `buildIcs` / `downloadIcs` (evento de estadía RFC 5545).
- `components/SearchBar`, `GuestsPicker` (adultos, niños y edades), `DestinationField`, `EngineShell`,
  `AmenityIcon`, `Stars`.
- **Enlaces profundos** (C9 chatbot, correos de C6): motor
  `/h/<slug>?checkin=YYYY-MM-DD&checkout=YYYY-MM-DD&adults=2&children=1&ages=7&promo=CODIGO`, marketplace
  `/hotel/<slug>?…` (mismos parámetros), búsqueda `/search?city=Cartagena&checkin=…&checkout=…&adults=2`,
  checkout directo `/book/<slug>?…&items=<room_type_id>:<rate_plan_id>:<cantidad>`.

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

1. **C-INT — `frontend/src/app/__tests__/router.test.tsx` (A2)**: asume los stubs.
   - `hides the Housetel header on hotel-branded pages` espera el título del stub "Reservas directas" en
     `/h/casa-aurora`: ahora la página pide `GET /api/v1/public/marketplace/properties/casa-aurora/booking-engine/`
     y `…/properties/casa-aurora/?via=booking_engine`. Agregar handlers MSW y afirmar el nombre del hotel (o solo
     que no está el header de Housetel).
   - `shows the marketplace home…` sigue encontrando "Reserva directo con el hotel.", pero la home pide
     `destinations/` y `search/`: agregar handlers (`[]` y `{count: 0, results: [], facets: {types: [], stars: [],
     amenities: []}, nights: 0, …}`) para no ensuciar stderr.
2. **D1 — throttles por IP detrás de proxy**: el proxy de Vite no reenvía la IP del cliente (`xfwd` apagado), así
   que en desarrollo todos comparten el mismo cupo (reservas 60/h). En producción configurar
   `REST_FRAMEWORK["NUM_PROXIES"]` (o equivalente) según el proxy real.
3. **C11 (comisiones)**: las reservas del marketplace llegan con `source="marketplace"` por `create_reservation`
   (`reservation_created`, nunca durante el seed). Las del motor propio llevan `source="booking_engine"` (sin
   comisión según el spec).
4. **C6 (mensajería)**: si se envía confirmación de reservas en línea, filtrar `reservation_created` por
   `source ∈ {marketplace, booking_engine}` e incluir `portal_url`. La página de confirmación **no** promete correo.
5. **C9 (chatbot)**: usar los enlaces profundos de arriba para "link al booking engine".
6. **D1 — media**: fotos, logo y portada del motor se sirven en `/media/` solo con `DEBUG` (igual que B1).

## Seed (`apps/marketplace/seed.py`)

`BookingEngineSettings` + `ListingContent` para las 3 propiedades, con color de marca propio (también escrito en
`Property.branding.primary_color`): Casa Aurora `#0E6E74` (verde caribe), Andino Medellín `#3D5A80` (azul
andino), Andino Hostel Bogotá `#8A4F7D` (ciruela Candelaria); frase de bienvenida y condiciones ES/EN; barrio
(Centro Histórico, El Poblado, La Candelaria), frase de tarjeta, 3 destacados y 4 fotos destacadas (3 de la
galería + 1 de categoría); `marketplace_listed = True`. Idempotente por fila (una fila existente se respeta tal
como la dejó el hotel). **0,16 s**; probado sobre la BD de desarrollo dentro de una transacción revertida (dos
corridas, mismos conteos: 3 motores, 3 fichas, 12 fotos destacadas; después del rollback la BD quedó igual). La BD
de desarrollo **todavía no tiene estas filas** (las crea C-INT con `seed_demo`); sin ellas todo funciona con los
valores por defecto (color de marca de B1, sin frase ni barrio). Para aplicarlo solo, sin `seed_demo`:

```bash
docker compose exec -T backend python manage.py shell -c "
import random; from datetime import date
from apps.core.seed import SeedContext, RNG_SEED; from apps.core.models import Property
from apps.core.signals import seeding; from apps.marketplace import seed
ctx = SeedContext(today=date.today(), rng=random.Random(RNG_SEED))
ctx.properties = {k: Property.objects.get(slug=v) for k, v in {'aurora': 'casa-aurora', 'andino_mde': 'andino-medellin', 'andino_bog': 'andino-hostel-bogota'}.items()}
with seeding(): seed.seed(ctx)"
```

## Limitaciones conocidas / pendientes

- **Modo MVP**: no se escribieron ni corrieron tests. En los owner paths quedaron tests de intentos anteriores
  (`backend/apps/marketplace/tests/`, `frontend/src/features/marketplace/__tests__/`) sin revisar; pueden necesitar
  ajustes por los cambios de esta corrida (throttle 60/h, clave de caché versionada, `amenity_codes` fuera del
  detalle). Se retoman en la fase de tests.
- Los planes del demo tienen `deposit_percent = 0`: el camino "pagar en el hotel con depósito" no se ve con el
  seed (el de pago en línea se prueba con "Pagar ahora"). Para verlo, poner un depósito a un plan en
  `/app/rates/plans`.
- Grupo por habitación: al elegir N habitaciones de una oferta, cada una lleva el grupo buscado (2 adultos × 2
  habitaciones = 4 huéspedes).
- La búsqueda se cachea 60 s; se invalida al cambiar listing o motor, no al cambiar tarifas o disponibilidad.
- Ciudad exacta (sin tildes ni mayúsculas), no difusa; el campo de destino sugiere las ciudades con hoteles.
- Ubicación en texto (dirección, barrio, altitud y clima), sin mapa; sin reseñas.
- Un enlace de búsqueda compartido con fechas pasadas muestra el error de la API ("La llegada no puede ser en el
  pasado").
- El entorno de desarrollo recarga el backend a menudo mientras otros agentes editan: un 502 puntual por el proxy
  es eso, no un fallo del marketplace (reintentar).

## Datos que dejó la verificación en la BD de desarrollo

- 2 reservas en Casa Aurora del **6 al 8 de noviembre de 2026**, útiles para probar la confirmación:
  - `HT-QS872J`: marketplace, pagar en el hotel, **confirmada**, Estándar · Tarifa flexible + desayuno × 4, titular
    "Smoke Marketplace" (`smoke.c4@example.com`, CO/CO), total $1.042.440.
  - `HT-WW4G2D`: booking engine, pagada ahora con tarjeta simulada → **confirmada**, Superior · Tarifa flexible,
    titular "Smoke Engine" (`smoke.c4.engine@example.com`, US/US, IVA exento), total $966.000.
- 2 eventos de auditoría `marketplace.booking_engine_updated` del dueño (cambio y reversión de la frase y la
  anticipación). La fila de motor que creó esa prueba se borró para no bloquear el seed.

---

## Cómo probarlo en la UI

URL: <http://localhost:5173>. Staff: `owner@casaaurora.co` / `housetel123` (tiene `marketplace.manage`);
`recepcion@casaaurora.co` / `housetel123` **no** lo tiene. Fechas sugeridas con disponibilidad en los tres
hoteles al 27-sep-2026: **20 → 22 de octubre de 2026** (si una categoría ya no aparece, mover unos días). Tras el
seed de C-INT cambian los colores de marca, aparecen barrio, frase y destacados (ver "Seed").

1. **Home `/`** (ES/EN, claro/oscuro, 375 px).
   - Esperado: titular editorial "Reserva directo con el hotel.", buscador (Destino · Fechas · Huéspedes ·
     "Buscar"), sección "De la costa al páramo" con los destinos parados en su altitud (Cartagena 2 m, Medellín
     1.495 m, Bogotá 2.640 m) sobre los pisos térmicos (cada punto lleva a su búsqueda), "Dónde quedarte"
     (3 destinos con foto), "Alojamientos en Housetel" (3 hoteles), "Cómo funciona reservar aquí" y la tarjeta
     "¿Tienes un hotel o un hostal?" con "Prueba Housetel gratis" → `/signup`.
   - A 375 px: sin scroll horizontal; el perfil de altitud se desplaza de lado y los pisos pasan a una leyenda.
2. **Buscar**: escribir "Cart" en Destino → sugerencia "Cartagena · Bolívar · 1 alojamiento · 2 m · Cálido";
   elegir 20–22 oct, 2 adultos → "Buscar".
   - Esperado: `/search?city=Cartagena&checkin=…` con la tarjeta de Hotel Casa Aurora, tarifa más barata "Desde
     $ … por noche, IVA incluido" y "Total por 2 noches: $ …". Sin ciudad: los 3 hoteles.
   - Filtros (barra lateral; en móvil botón "Filtros" → hoja inferior): tipo, estrellas, amenidades, precio por
     noche (botón aplicar). Orden: recomendados, precio ↑/↓, estrellas. Un filtro sin resultados (p. ej. precio
     máximo 100.000) → "No hay alojamientos disponibles con esos criterios" con "Quitar filtros".
3. **Página del hotel** `/hotel/casa-aurora?checkin=2026-10-20&checkout=2026-10-22&adults=2`.
   - Esperado: galería (mosaico; en móvil tira deslizable; "Ver las 13 fotos" abre el visor), tipo y estrellas,
     "Habitaciones y tarifas": por categoría (Estándar, Superior, Suite) sus tarifas (No reembolsable, Tarifa
     flexible, Con desayuno) con la política en palabras ("Cancelación gratis hasta 2 días antes de la llegada"),
     total de la estadía, precio por noche y "Elegir" → selector de cantidad (tope = unidades libres).
   - Panel "Tu estadía" (fechas, huéspedes, código promocional, "Ver disponibilidad") y "Tu selección" (fijo en
     escritorio; barra inferior en móvil) con el total y "Reservar".
   - Código `BIENVENIDA10` → "Código BIENVENIDA10 aplicado" y precios con 10 % menos; un código falso → aviso rojo.
   - Debajo: sobre el hotel, amenidades por grupo, políticas (horarios, mascotas, niños…), ubicación y contacto.
4. **Checkout** (elegir 1 Estándar · Tarifa flexible → "Reservar") → `/book/casa-aurora?…&items=…`.
   - Sin datos: "Confirmar reserva" muestra los errores (nombre, correo, celular, nacionalidad, país, y
     "Necesitamos tu autorización para gestionar la reserva." en Habeas Data).
   - Nacionalidad y país donde vives = Colombia → texto "El alojamiento incluye el IVA del 19 %…".
     Cambiar ambos a **Estados Unidos** → aparece en verde **"Exento de IVA de alojamiento"** y el resumen se
     recalcula solo (IVA solo de extras, "IVA de alojamiento exento", total menor). Estados Unidos + vive en
     Colombia → vuelve a pagar IVA.
   - Marcar "Desayuno" → línea "Desayuno × 4" (2 personas × 2 noches) con su IVA en el resumen.
   - Hora estimada de llegada y solicitudes especiales opcionales.
5. **Reserva con pago en el hotel**: "Pagar en el hotel" + autorización → "Confirmar reserva".
   - Esperado: `/booking/<código>/confirmed` → "Tu reserva está confirmada", la llave con el código, fechas con
     horarios, habitación, extras, total/saldo, política, "Abrir mi reserva" (portal `/g/<token>` de C5),
     "Agregar al calendario" (descarga `<código>.ics`) y contacto del hotel.
   - En el PMS (owner): `/app/reservations` → la reserva con fuente marketplace y el huésped nuevo.
6. **Reserva pagando ahora**: repetir con "Pagar ahora" → botón "Reservar y pagar $ …".
   - Esperado: redirige a la pasarela simulada `/sim/pay/<ref>` ("Modo simulación"); "Pagar" → vuelve a la
     confirmación → "Estamos confirmando tu pago" y en segundos "Tu reserva está confirmada", con "Pagado" = total
     y saldo 0. "Simular rechazo" → "Intentar de nuevo" en la confirmación; "Dejar vencer" → "Volver a reservar".
   - Abrir la confirmación en otra pestaña o navegador pide el correo ("Abre tu reserva"); con un correo distinto
     → "No encontramos una reserva con ese código y ese correo". Ejemplo listo: `/booking/HT-QS872J/confirmed`
     con `smoke.c4@example.com`.
7. **Booking engine** `/h/casa-aurora?checkin=2026-10-20&checkout=2026-10-22&adults=2` (también
   `/h/andino-hostel-bogota?…&adults=3` para camas de dormitorio y `/h/andino-medellin`).
   - Esperado: sin header/footer de Housetel; cabecera con logo o monograma y nombre del hotel, "Tarifa directa
     del hotel", color del hotel en botones y acentos, frase de bienvenida (tras el seed) y pie "Reservas directas
     con tecnología Housetel". Mismo flujo: checkout en `/h/<slug>/book`, confirmación en
     `/h/<slug>/booking/<código>`, y la pasarela vuelve ahí.
   - En el hostal con 3 adultos una oferta de dormitorio dice "3 camas para tu grupo".
8. **Widget** `/embed/casa-aurora`.
   - Esperado: caja compacta con el nombre del hotel, llegada/salida (controles nativos), adultos, niños y
     "Ver disponibilidad" → abre `/h/casa-aurora?checkin=…` en otra pestaña. Fechas fuera de la ventana → mensaje.
9. **Configuración** (owner) `/app/settings/booking-engine` → "Motor de reservas", botón "Ver mi página".
   - Pestaña **"Página de reservas"**: "Recibir reservas en tu página" (apagarlo → `/h/casa-aurora` muestra "Este
     hotel no recibe reservas en línea por ahora" con el contacto); color con selector y código (aviso de
     contraste en vivo; `#12` → "Usa un color #RRGGBB.") y **vista previa en vivo**; subir logo y portada (se ven en la
     vista previa y en `/h/…`); frase de bienvenida y condiciones ES/EN; anticipación mínima (p. ej. 48 h →
     llegar mañana en `/h/…` muestra desde qué fecha se puede); reservas hasta N días; mostrar código
     promocional; tarifas que vende la página (marcar solo "Tarifa flexible" → `/h/…` solo ofrece esa). La barra
     "Tienes cambios sin guardar" aparece al editar.
   - Pestaña **"Marketplace"**: "Aparecer en el marketplace de Housetel" (apagarlo → el hotel desaparece al instante
     de `/`, `/search` y `/hotel/<slug>` muestra "Este alojamiento no está disponible"; volver a encenderlo); frase de tarjeta ES/EN,
     barrio, hasta 6 destacados, fotos destacadas en orden (flechas) con **vista previa de la tarjeta**.
   - Pestaña **"En tu web"**: enlaces del motor y del widget, snippet `<iframe>` copiable con vista previa real,
     botón "Reservar ahora" copiable y códigos promocionales activos (`BIENVENIDA10`) con enlace a gestionarlos.
   - `recepcion@casaaurora.co` no ve "Motor de reservas" en Configuración (entrar por URL → sin permiso).

---

## Verificación (esta corrida, sin tests)

```bash
docker compose exec -T backend python manage.py check                                   # sin problemas
docker compose exec -T backend python manage.py makemigrations marketplace --check --dry-run   # No changes
docker compose exec -T backend ruff check apps/marketplace && ruff format --check apps/marketplace   # limpio
docker compose exec -T backend python manage.py spectacular --validate                 # 0 errores; ningún warning de marketplace
cd frontend && npx tsc -p tsconfig.app.json --noEmit | grep src/features/marketplace   # sin errores
npx eslint src/features/marketplace                                                    # limpio
```

- i18n: ES/EN con las mismas claves (script de paridad) y todas las claves usadas existen, también las dinámicas.
- **Smoke por el proxy de Vite** (cookie jar + CSRF, script en el scratchpad): destinos (3, con portada); búsqueda
  sin fechas (ciudad sin tildes), con fechas (3 hoteles), `type=hostel`, `sort=price`, `max_price`, fechas pasadas →
  400; detalle y 404; ofertas CO vs `foreign=true` (exento, más barato), solo planes públicos, booking engine con
  los mismos planes; cotización CO (IVA) vs US/US (alojamiento exento, desayuno gravado, cantidad 4) vs US
  residente en CO (paga IVA); `BIENVENIDA10` aplicado y código falso → 400 `promo_invalid`; 10 habitaciones → 409
  `no_availability` con `shortfalls`; sin Habeas Data → 400; reserva pagar en el hotel → `confirmed`; lookup con el
  email en otras mayúsculas → 200 y email ajeno → 404; reserva del motor pagar ahora → `tentative` + link con
  retorno a `/h/casa-aurora/booking/<código>` → pasarela simulada aprueba → `paid` → reserva `confirmed`, saldo 0,
  exenta; config pública del motor; staff: GET/PATCH motor (y reversión), color inválido → 400, listing, snippet,
  las dos reservas visibles en `GET /bookings/reservations/` con su fuente; recepción → 403; anónimo → 401.
- Seed con rollback (ver "Seed"). Invalidación de la caché de búsqueda comprobada (la versión sube y la clave cambia).
- Revisión visual con **Chrome headless propio** (perfil aislado; no el navegador compartido): home y página de
  hotel a 1440 px, configuración del motor a 1440 px, y por CDP a 375 px `scrollWidth = 375` (sin scroll
  horizontal) en `/`, `/search` (con y sin fechas), `/hotel/…`, `/book/…`, `/booking/…/confirmed`, `/h/…` y
  `/embed/…`. La validación completa en Chrome la hace el orquestador.
