# B1 — Inventario y perfil de propiedad — integration notes

Estado: tarea B1 completa y **verificada** (pasada del verificador, 2026-09-26). La implementación retomó un
intento anterior que se había cortado y lo completó con TDD (ruta duplicada de las fotos, conteo de subidas,
provisión robusta para IA/signup, carreras concurrentes, integridad de los campos personalizados, errores del
servidor por campo en la UI, lint y copy). El verificador revisó todo contra el plan y el spec y corrigió, también
con TDD, lo que se lista en "Correcciones del verificador". Evidencia en "Verificación".

Owner paths: `backend/apps/inventory/**`, `frontend/src/features/inventory/**` y esta nota. No se tocó nada fuera
de ellos. No hay migraciones nuevas: `models.py` no cambió desde la Fase A.

---

## Guía rápida para otras tareas

| Si eres… | Usa |
|---|---|
| **B2b** (reservas) | Señal `inventory_changed` (abajo) para `rebuild_inventory`. Unidades: habitaciones activas (privada) o camas activas de habitaciones activas (dorm). Bloqueos activos = `RoomBlock.released_at IS NULL`, `[start_date, end_date)`. Estado de limpieza: solo `set_housekeeping_status`. |
| **C1 / C13** (recepción, calendario) | `RoomStatusBadge`, `RoomKeyTag` y `CategoryChip` de `features/inventory/components/`. Hooks `useRooms`, `useRoomTypes` en `features/inventory/api.ts`. |
| **C2** (housekeeping) | `set_housekeeping_status(room, status, actor=, source=)`, `block_room(...)` / `release_block(...)` (tickets que inhabilitan). El endpoint `rooms/{id}/status/` de inventario exige `inventory.manage`; el rol housekeeping no lo tiene, así que C2 expone su propio proxy, como dice el plan. |
| **C4** (marketplace) | Las fotos son **públicas**: `Photo.image.url` es `/media/photos/...` y no pide sesión. Fotos de categoría: `room_type.photos.all()` (orden `sort_order, created_at`). Galería del hotel: `Photo.objects.filter(property=p, room_type=None, room=None)`. Atributos por habitación: `effective_attributes(room)`. Campos visibles: `CustomFieldDefinition.show_in_marketplace`. |
| **C9** (onboarding IA) | `provision_room_type(...)` (contrato completo abajo). Códigos de amenidades válidos: `GET /api/v1/inventory/amenities/`. Tipos de cama: `single, twin, double, queen, king, bunk, sofa_bed, crib`. |
| **C11** (signup, primeros pasos) | `provision_room_type(...)`. Checklist: `GET /api/v1/inventory/summary/` (`totals.units`, `warnings`, `profile_missing`). |
| **B3 / B2b** (campos de huésped y reserva) | `validate_custom_values(defs, values)`. Para elegir las definiciones con el alcance correcto (org + propiedad) usa `apps.inventory.custom_fields.custom_field_definitions(organization=, applies_to=, property=)`. |

---

## API implementada

Base `/api/v1/inventory/`. Todas llevan `X-Property-Id` y usan `PropertyScopedMixin`: los objetos de otra
propiedad u organización responden 404. `GET` exige `inventory.view` y toda escritura `inventory.manage`. Un rol
sin permiso recibe 403 `{"detail": "No tienes permiso para esta acción", "code": "permission_denied",
"permission": "inventory.manage"}`. Housekeeping, mantenimiento, recepción y contabilidad solo leen.

**Paginación.** Estas listas son **arrays planos**, sin paginar (el catálogo de un hotel cabe en una respuesta):
`amenities/`, `room-types/`, `rooms/`, `custom-fields/`, `rooms/{id}/beds/`, `.../photos/`. Solo `blocks/` usa la
paginación estándar `{count, next, previous, results}`, con `page_size` de hasta 200.

Todas las escrituras quedan auditadas con `audit.record` (acciones `inventory.*`, ver "Señales"). Los errores
siguen el formato del core: `{detail, code, fields?, ...extra}`.

### Perfil de la propiedad (excepción autorizada: B1 edita `core.Property`)

| Método y path | Descripción |
|---|---|
| `GET property/` | Perfil de `request.property` |
| `PATCH property/` | Campos editables: `name, description{es,en}, address, city, department, latitude, longitude, phone, email, website, rnt_number, nit, legal_name, star_rating (1–5 o null), check_in_time "HH:MM", check_out_time, default_language (es\|en), house_rules{es,en}, branding{primary_color}, languages[], policies{}, amenities[]`. Los de solo lectura se ignoran. Nunca se toma la propiedad del body. |
| `POST property/logo/` · `DELETE property/logo/` | multipart `image` (JPG/PNG/WEBP ≤ 10 MB) → perfil con `branding.logo = "/media/branding/<property_id>/<uuid>.<ext>"` |
| `GET/POST property/photos/` · `PATCH/DELETE property/photos/{photo_id}/` · `POST property/photos/reorder/` | Galería del hotel (fotos sin categoría). Mismo contrato que las fotos de categoría. |

- `languages`, `policies` y `amenities` (amenidades del hotel) se guardan en `Property.settings`, con esas mismas
  claves.
- `policies` se combina con los valores por defecto `{pets_allowed: false, smoking_allowed: false,
  children_allowed: true, events_allowed: false, min_checkin_age: 18}`. Una clave desconocida da 400.
- `nit`: se quitan puntos y espacios y se valida `\d{6,12}(-\d)?`. Por ejemplo, `901.234.567-1` queda
  `901234567-1`.

Respuesta real (Casa Aurora, recortada):

```json
{
  "id": "f605ce02-…", "name": "Hotel Casa Aurora", "slug": "casa-aurora", "property_type": "boutique",
  "status": "active", "timezone": "America/Bogota", "currency": "COP", "business_date": "2026-09-25",
  "marketplace_listed": true,
  "description": {"es": "Casa colonial restaurada…", "en": "A restored colonial house…"},
  "address": "Calle del Cuartel #36-77, Centro Histórico", "city": "Cartagena", "department": "Bolívar",
  "country": "CO", "latitude": "10.423600", "longitude": "-75.551800", "phone": "+57 605 660 1234",
  "email": "reservas@casaaurora.co", "website": "https://casaaurora.co", "rnt_number": "RNT 98765",
  "nit": "901234567-1", "legal_name": "Casa Aurora Hoteles S.A.S.", "star_rating": 4,
  "check_in_time": "15:00", "check_out_time": "12:00", "default_language": "es",
  "house_rules": {"es": "Check-in desde las 15:00…", "en": "Check-in from 3 pm…"},
  "branding": {"primary_color": "#B4583B", "logo": ""},
  "languages": ["es", "en"],
  "policies": {"pets_allowed": false, "smoking_allowed": false, "children_allowed": true,
               "events_allowed": true, "min_checkin_age": 18},
  "amenities": ["wifi", "pool", "restaurant", "bar", "breakfast", "reception_24h", "terrace"]
}
```

### Amenidades

| Método y path | Descripción |
|---|---|
| `GET amenities/` | Catálogo global (`organization = null`, 47 del seed) + las propias de la organización. Si un código se repite, gana el propio. |
| `POST amenities/` | `{code, name, icon?, category}` → crea una amenidad propia. `code` se normaliza a slug (`"Rooftop Bar"` → `"rooftop-bar"`) y no puede repetir uno del catálogo. |
| `PATCH/DELETE amenities/{id}/` | Solo las propias. Una global responde 403 `global_amenity_read_only`. Si cambia el `code` o se borra, los perfiles de las propiedades de la organización que la listaban (`Property.settings["amenities"]`) siguen el código nuevo o la pierden (antes quedaba un código fantasma que hacía fallar el siguiente guardado del perfil). |

Las amenidades propias se auditan (`inventory.amenity_created/updated/deleted`) a nivel de organización
(`AuditEvent.property = null`), igual que los campos personalizados de alcance organización.

```json
{"id": "1c4c72cd-…", "code": "elevator", "name": {"es": "Ascensor", "en": "Elevator"},
 "icon": "arrow-up-down", "category": "accessibility", "is_global": true}
```

`category` ∈ `room | bathroom | property | accessibility | view`. `icon` es el nombre lucide en kebab-case; el
frontend tiene un set curado en `lib/amenityIcons.ts` y, si no conoce el nombre, usa `sparkles`.

### Categorías (`room-types/`)

| Método y path | Descripción |
|---|---|
| `GET room-types/?kind=&is_active=` | Lista con conteos |
| `POST room-types/` · `PATCH/PUT room-types/{id}/` · `DELETE room-types/{id}/` | CRUD |
| `POST room-types/{id}/duplicate/` | `{code?, name?}` → copia parámetros, amenidades y valores personalizados (no habitaciones ni fotos). Código por defecto `STE2`; nombre por defecto `"<nombre> (copia)"` / `"(copy)"`. |

Fila (real, recortada):

```json
{
  "id": "1670a4e3-…", "code": "STE", "name": {"es": "Suite Vista al Mar", "en": "Sea View Suite"},
  "description": {"es": "…", "en": "…"}, "kind": "private",
  "base_occupancy": 2, "max_adults": 3, "max_children": 2, "max_occupancy": 4,
  "beds": [{"type": "king", "count": 1}, {"type": "sofa_bed", "count": 1}],
  "size_m2": "42.00", "view": "sea", "smoking_allowed": false, "accessible": false,
  "amenities": ["air_conditioning", "bathtub", "wifi"], "color": "#B4583B", "housekeeping_minutes": 50,
  "sort_order": 30, "is_active": true, "custom_values": {"orientation": "sea"},
  "rooms_count": 6, "active_rooms_count": 6, "beds_count": 0, "units_count": 6,
  "photos_count": 3, "cover_photo": "/media/photos/seed/casa-aurora-ste-1.jpg",
  "created_at": "…", "updated_at": "…"
}
```

Reglas de validación. Son las mismas para la API y para `provision_room_type`.
- `name`: texto o `{es, en}`; al menos un idioma y máximo 100 caracteres. Un texto plano se toma como español.
- `code`:
  - Se permiten A–Z, 0–9, `_` y `-`, con un máximo de 20 caracteres.
  - Se pasa a mayúsculas y es único en la propiedad.
  - Si falta al crear, se deriva del nombre y se mantiene único: "Suite Vista al Mar" → `SVM`, y si ya existe,
    `SVM2`.
  - La API **rechaza** un código inválido. `provision_room_type` lo **sanea** (ver contrato).
- Ocupación de una categoría privada:
  - `base ≤ max`, `adults ≤ max` y `children ≤ max − 1`, con rangos de 1 a 20 (los niños desde 0).
  - Al crear, se completa lo que falte.
- Dorm: la ocupación se fuerza siempre a 1/1/0/1, porque la unidad es una cama para una persona.
- `kind` no puede cambiar si la categoría ya tiene habitaciones (400 en `kind`).
- **Nuevo (esta corrida):** cambiar la ocupación de una categoría no puede dejar inválida a una habitación que
  sobrescribe ocupación. Error 400 en el campo cambiado (por ejemplo `max_occupancy`): `"La habitación 306
  sobrescribe la ocupación y quedaría inválida: ajústala primero"`.
- `beds`:
  - Formato `[{type, count}]`, con `type ∈ single, twin, double, queen, king, bunk, sofa_bed, crib`.
  - El tipo no distingue mayúsculas; `count` va de 1 a 20; máximo 10 tipos.
- `size_m2` ≥ 1, redondeado a 2 decimales (24.335 → 24.34). `color` en formato `#RRGGBB`. `housekeeping_minutes`
  entre 5 y 480.
- `custom_values`: se valida con las definiciones `room_type` de la organización y de la propiedad.
- Desactivar una categoría con reservas activas → 409 `room_type_in_use` (extra `active_stays`).
- Borrar una categoría con habitaciones o con historial de reservas → 409 `room_type_in_use`. La alternativa es
  desactivarla.

### Fotos de categoría (públicas)

| Método y path | Descripción |
|---|---|
| `GET room-types/{id}/photos/` | `[{id, url, caption{es,en}, sort_order, room_type, created_at}]` en orden |
| `POST room-types/{id}/photos/` | multipart `image` (JPG/PNG/WEBP ≤ 10 MB, se valida con Pillow) + `caption` opcional (texto o JSON `{"es","en"}`) → 201. Queda la última y se guarda en `photos/<año>/<mes>/<uuid>.<ext>`. |
| `PATCH room-types/{id}/photos/{photo_id}/` | `{caption}` (auditado como `inventory.photo_updated` si cambia) |
| `DELETE room-types/{id}/photos/{photo_id}/` | 204. El archivo se borra del storage al hacer commit (receiver `post_delete`, también cuando el borrado viene en cascada). |
| `POST room-types/{id}/photos/reorder/` | `{ids: [...]}`: exactamente las fotos de esa galería, sin faltantes ni repetidas (400 en otro caso) → fotos en el nuevo orden. La primera es la portada (`cover_photo`). Un cambio real de orden se audita (`inventory.photos_reordered`, objetivo = la categoría o la propiedad). |

### Habitaciones (`rooms/`)

| Método y path | Descripción |
|---|---|
| `GET rooms/?room_type=&floor=&building=&housekeeping_status=&is_active=&search=` | Lista ordenada por categoría y número. Cada fila trae `effective`, `overridden_fields` y `active_block`. El número de queries es constante (8), no crece con las habitaciones (test que compara 3 vs 15 habitaciones; lo mismo para `room-types/`). |
| `POST rooms/` · `PATCH/PUT rooms/{id}/` · `DELETE rooms/{id}/` | CRUD. `housekeeping_status` es de solo lectura aquí, y editar una habitación (una o en bloque) **nunca** reescribe el estado de limpieza que leyó: se guardan solo las columnas editadas, así un check-out o una camarera que cambia el estado a la vez no se pierde. |
| `POST rooms/bulk-create/` | `{room_type, numbers: "101-110,201,203", floor?, building?, beds_per_room?}` |
| `POST rooms/bulk-update/` | `{ids: [...], set: {campo: valor}, reset: [campos]}` |
| `GET rooms/{id}/effective/` | `effective_attributes(room)` + `inherited`: los valores de la categoría, para mostrar qué reemplaza cada override |
| `POST rooms/{id}/reset-override/` | `{field}`: un campo sobrescribible, `custom_values.<clave>` o `amenities` → la habitación vuelve a heredar |
| `POST rooms/{id}/status/` | `{housekeeping_status: clean\|dirty\|inspected\|out_of_service}`, vía `set_housekeeping_status` |

Fila (real, habitación 306, recortada):

```json
{
  "id": "dfabc58b-…", "number": "306", "name": "", "floor": "3", "building": "",
  "room_type": "1670a4e3-…", "room_type_code": "STE", "room_type_name": {"es": "Suite Vista al Mar", "en": "…"},
  "kind": "private", "color": "#B4583B",
  "overrides": {"name": {"es": "Suite Panorámica", "en": "Panoramic Suite"}, "view": "panoramic", "size_m2": "48.00"},
  "extra_amenities": [], "removed_amenities": [], "custom_values": {"minibar": true},
  "housekeeping_status": "clean", "is_active": true, "sort_order": 0, "notes": "", "connecting_rooms": [],
  "beds_count": 0, "active_beds_count": 0,
  "effective": {"name": {"es": "Suite Panorámica", "en": "Panoramic Suite"}, "view": "panoramic",
                "size_m2": "48.00", "max_adults": 3, "…": "…",
                "amenities": ["air_conditioning", "…"], "custom_values": {"orientation": "sea", "minibar": true},
                "overridden_fields": ["name", "size_m2", "view"], "overridden_custom_fields": ["minibar"]},
  "overridden_fields": ["name", "size_m2", "view"],
  "active_block": null
}
```

`active_block` es el bloqueo activo actual o el próximo (no liberado y con `end_date > business_date`):
`{id, bed, start_date, end_date, kind, reason}` o `null`.

Reglas de habitaciones:
- `number` se recorta, es obligatorio y único en la propiedad. La categoría debe ser de la misma propiedad.
- `overrides`:
  - Solo acepta las claves de `ROOM_OVERRIDABLE_FIELDS`: `name, description, base_occupancy, max_adults,
    max_children, max_occupancy, beds, size_m2, view, smoking_allowed, accessible, housekeeping_minutes`.
  - Cada valor se valida igual que el campo de la categoría. `size_m2` se guarda como texto `"48.00"`.
  - La ocupación **efectiva** (categoría ⊕ override) debe seguir siendo válida.
  - En un dorm no se puede sobrescribir la ocupación.
- `extra_amenities` / `removed_amenities` usan códigos y no pueden solaparse.
- `custom_values` = campos propios de la habitación (`applies_to=room`; aplican el valor por defecto y la
  obligatoriedad) + sobrescrituras de campos de la categoría (`applies_to=room_type`, solo las claves enviadas).
  En `PATCH` el objeto se **reemplaza** entero.
- Cambiar de categoría o desactivar una habitación con reservas activas asignadas → 409 `room_in_use` (extra
  `rooms` o `active_stays`).
- `DELETE`:
  - Con reservas activas → 409 `room_in_use` (`active_stays: n`).
  - Con historial → 409 `room_in_use` con la sugerencia de desactivarla.
  - Sin nada de eso → 204.

**Creación masiva** (`bulk-create`):
- Formato de `numbers`:
  - Partes separadas por `,`, `;` o salto de línea.
  - Rangos `<letras><dígitos>-<letras><dígitos>` con el mismo prefijo: `101-110`, `A8-A10`, `B1-3`. `01-03`
    conserva los ceros.
  - Cualquier otra parte es literal: `Suite Mar`, `PH-1`.
- Límites: máximo 500 números por solicitud y 20 caracteres por número.
- `floor: null` infiere el piso de cada número: `305` → `3`, `1203` → `12`, `D1` → `""`.
- Dorm: `beds_per_room` (0–50) crea camas `C1…Cn`. Si viene `null`, sale de la configuración de camas de la
  categoría (un camarote cuenta dos).
- A las habitaciones creadas se les aplican los valores por defecto de los campos `room`.
- Se ejecuta en una transacción con la fila de la propiedad bloqueada: dos creaciones simultáneas del mismo rango
  nunca dan `IntegrityError`.

```json
// 201
{"count": 2, "rooms": [{"id": "ee16e266-…", "number": "401", "floor": "4", "room_type_code": "DBL", "…": "…"}]}
// 400: nada se crea
{"detail": "Estos números ya existen o se repiten: 101, 102, 103", "code": "duplicate_room_numbers",
 "duplicates": ["101", "102", "103"], "fields": {"numbers": ["Estos números ya existen o se repiten: 101, 102, 103"]}}
// 400
{"detail": "El rango «110-101» termina antes de empezar", "code": "invalid_room_numbers", "fields": {"numbers": ["…"]}}
```

**Edición masiva** (`bulk-update`): todo o nada, y solo sobre los `ids` enviados, que deben ser de la propiedad.
- Claves aceptadas en `set`:
  - Campos propios: `floor, building, name` (nombre propio de la habitación), `room_type, is_active, sort_order,
    notes, housekeeping_status` (pasa por `set_housekeeping_status`).
  - Campos sobrescribibles: `view` u `overrides.view`, y `overrides.name` para el nombre de categoría.
  - `custom_values.<clave>`; el valor `null` la borra.
- Claves aceptadas en `reset`: los campos sobrescribibles, `custom_values.<clave>` y `amenities`.
- Una clave desconocida → 400 con esa clave en `fields`.

```json
// POST {"ids": ["…101", "…102"], "set": {"view": "sea", "custom_values.minibar": true}, "reset": ["accessible"]}
{"updated": 2, "rooms": [{"overrides": {"view": "sea"}, "custom_values": {"minibar": true}, "…": "…"}]}
// set {"max_adults": 9} → 400
{"detail": "La ocupación resultante no es válida", "code": "validation_error",
 "fields": {"max_adults": ["Ocupación inválida en 101"]}}
```

### Camas de dormitorio (`rooms/{id}/beds/`)

| Método y path | Descripción |
|---|---|
| `GET/POST rooms/{id}/beds/` · `GET/PUT/PATCH/DELETE rooms/{id}/beds/{bed_id}/` | `{id, room, label, bed_type (single\|bunk_top\|bunk_bottom\|double), is_active}`. Etiqueta única por habitación; se listan en orden natural (C1, C2, C10). |
| `POST rooms/{id}/beds/bulk/` | `{count: 1–50, prefix: "C", bed_type?: single\|…\|bunk}`. Continúa la numeración (`C3, C4…`); `bunk` alterna abajo y arriba. |

- Una habitación privada → 400 `not_a_dorm`.
- Desactivar una cama con reservas activas, o borrar una con historial → 409 `bed_in_use`.

### Campos personalizados (`custom-fields/`)

| Método y path | Descripción |
|---|---|
| `GET custom-fields/?applies_to=room_type\|room\|guest\|reservation` | Definiciones de la organización (`scope: "organization"`) + las de la propiedad activa (`scope: "property"`) |
| `POST custom-fields/` | `{applies_to, key, label{es,en}, field_type, options?, required?, default_value?, show_in_marketplace?, sort_order?, scope?: organization\|property}` |
| `PATCH custom-fields/{id}/` | `label, options, required, default_value, show_in_marketplace, sort_order`. `key`, `applies_to`, `field_type` y `scope` no cambian después de crear (400). |
| `DELETE custom-fields/{id}/` | Borra la definición y quita su clave de los `custom_values` de categorías y habitaciones de su alcance |

```json
{"id": "696b89e7-…", "applies_to": "room_type", "key": "orientation", "label": {"es": "Orientación", "en": "Orientation"},
 "field_type": "select", "options": [{"value": "sea", "label": {"es": "Mar", "en": "Sea"}}, "…"],
 "required": false, "default_value": null, "show_in_marketplace": true, "sort_order": 20, "scope": "organization"}
```

Reglas:
- `key` cumple `^[a-z][a-z0-9_]{0,49}$`. `field_type` ∈ `text, number, boolean, select, multiselect, date`.
- `options` (obligatorias en select y multiselect) son textos o `{value, label}`; se normalizan a `{value,
  label}` y no pueden repetirse.
- `default_value` se valida contra el tipo y las opciones.
- Unicidad de la clave:
  - Una clave de organización choca con cualquier definición con esa clave.
  - Una clave de propiedad choca con la de organización o con otra de la misma propiedad.
  - **Nuevo:** los campos `room` y `room_type` comparten un solo espacio de nombres. La habitación hereda los
    valores de su categoría y los sobrescribe por clave, así que dos claves iguales serían ambiguas.
  - `guest` y `reservation` tienen cada uno el suyo.
- **Nuevo:** si al editar un `select`/`multiselect` se **quitan opciones**, las categorías y habitaciones de su
  alcance pierden esos valores (en un multiselect solo esos elementos). Si no se limpiaran, un valor huérfano
  bloquearía el siguiente guardado de esa habitación. La auditoría registra cuántos valores se limpiaron.
- Borrar o editar definiciones `guest`/`reservation` **no** toca los datos de huéspedes ni de reservas: esos datos
  son de B3/B2b.

### Bloqueos (`blocks/`)

| Método y path | Descripción |
|---|---|
| `GET blocks/?active=&current=&room=&bed=&kind=&start=&end=` | Paginado. `active=true` = no liberados; `current=true` = no liberados con `end_date > business_date`; `start`/`end` filtran por solapamiento con `[start, end)`. |
| `GET blocks/{id}/` | Detalle |
| `POST blocks/` | `{room, bed?, start_date, end_date (exclusiva), kind, reason?, force?}`, vía `block_room` → 201 |
| `POST blocks/{id}/release/` | Vía `release_block` (idempotente) → bloqueo con `released_at` |

```json
// POST {"room": "…101", "start_date": "2026-10-10", "end_date": "2026-10-12", "kind": "maintenance", "reason": "Pintura"}
{"id": "354b6387-…", "room": "8723804e-…", "room_number": "101", "room_type": "3a3747f1-…", "bed": null,
 "bed_label": null, "start_date": "2026-10-10", "end_date": "2026-10-12", "kind": "maintenance",
 "reason": "Pintura", "created_by_name": "Valentina Rojas", "released_at": null, "is_active": true, "created_at": "…"}
```

- `kind` ∈ `out_of_order, out_of_service, maintenance, owner_hold`. La cama debe ser de esa habitación.
- Dos bloqueos activos que se solapan en la misma habitación → 409 `block_overlap` (extra `block_id`). Un bloqueo
  de toda la habitación excluye los de sus camas, y un bloqueo de cama excluye el de la habitación y el de esa
  misma cama.
- Si hay reservas activas en el periodo → 409 `room_has_reservations` (extra `reservations: [códigos]`), salvo con
  `force: true`. Las reservas quedan como estaban: reasignarlas es tarea de recepción.

### Resumen (`summary/`)

`GET summary/` sirve para el checklist de primeros pasos (C11) y para el onboarding (C9):

```json
{
  "room_types": [{"id": "…", "code": "DBL", "name": {"es": "Estándar", "en": "Standard"}, "kind": "private",
                  "color": "#4E6C88", "is_active": true, "max_occupancy": 3, "rooms": 10, "active_rooms": 10,
                  "beds": 0, "units": 10}],
  "totals": {"room_types": 3, "active_room_types": 3, "rooms": 24, "active_rooms": 24, "beds": 0, "units": 24},
  "housekeeping": {"clean": 24, "dirty": 0, "inspected": 0, "out_of_service": 0},
  "blocked_today": 0,
  "warnings": [],
  "profile_missing": []
}
```

- `warnings`:
  - `room_type_without_rooms` (`room_type_id`).
  - `dorm_room_without_beds` (`room_type_id`, `room_id`). Es la advertencia de "un dorm exige camas".
- `profile_missing`: los campos recomendados que están vacíos, de `legal_name, nit, rnt_number, phone, email,
  address, city, description`.
- `units` = habitaciones activas (privada) o camas activas de habitaciones activas (dorm). `totals.units` suma
  solo las categorías activas.

---

## Contratos implementados / consumidos

Firmas y tipos de retorno sin cambios (los fija `apps/core/tests/test_contracts.py`, en verde).

```python
# apps/inventory/services.py
def effective_attributes(room) -> dict
def block_room(room, *, start, end, kind, reason, actor=None, bed=None) -> RoomBlock
def release_block(block, *, actor=None) -> RoomBlock
def set_housekeeping_status(room, status, *, actor=None, source="user") -> Room
def provision_room_type(property, *, data: dict, room_numbers: list[str], floor: str | None = None,
                        beds_per_room: int | None = None, actor=None) -> RoomType
def validate_custom_values(defs, values) -> dict   # re-exportado desde apps.inventory.custom_fields
```

**`effective_attributes(room)`**
- Devuelve todas las claves de `ROOM_OVERRIDABLE_FIELDS`, con el override o el valor de la categoría. `size_m2`
  viene como `Decimal`.
- `amenities`: categoría + extra − removidas, ordenadas.
- `custom_values`: categoría ⊕ habitación; gana la habitación.
- Marcadores: `overridden_fields`, `amenities_added`, `amenities_removed`, `overridden_custom_fields`.
- Identificadores: `room_id`, `room_type_id`, `number`, `room_name`, `floor`, `building`, `kind`.
- Usa `.all()`, así que aprovecha el `prefetch_related` del llamador.

**`block_room`**
- Errores 400: `invalid_dates` (si `end ≤ start`), `invalid_bed`, `invalid_kind`.
- Error 409: `block_overlap`.
- Bloquea la fila de la habitación para serializar los bloqueos. Audita `inventory.room_blocked` y emite
  `inventory_changed(start, end)`.

**`release_block`**: idempotente. Audita y emite `inventory_changed` una sola vez.

**`set_housekeeping_status`**
- Un estado desconocido → `invalid_status`.
- Si el estado no cambia, no hace nada.
- Si cambia: guarda, audita (con `source`) y emite `room_status_changed(room, old, new)`.

**`validate_custom_values(defs, values)`**
- Aplica `default_value` y rechaza claves desconocidas, obligatorios vacíos y tipos inválidos. Tipos: text → str;
  number → int/float; boolean → bool; select → una opción; multiselect → lista de opciones; date → `"AAAA-MM-DD"`.
- Error: `DomainError(code="invalid_custom_values", fields={clave: [msg]})`.

**`provision_room_type`** (para C9 onboarding y C11 signup, pensado para datos generados):

```python
room_type = provision_room_type(
    prop,
    data={"name": {"es": "Dormitorio mixto 6 camas", "en": "6-bed mixed dorm"}, "kind": "dorm",
          "beds": [{"type": "bunk", "count": 3}], "amenities": ["wifi", "lockers"], "size_m2": 24,
          "units": 12, "base_price": "65000"},           # claves desconocidas (units, base_price…) se ignoran
    room_numbers=["D1-D2"],                               # o ["D1", "D2"]; ints aceptados; [] = solo categoría
    floor=None,                                           # None infiere el piso por número; "" lo deja vacío
    beds_per_room=6,                                      # solo dorm; None → de `beds` (camarote = 2)
    actor=request.user,
)
room_type.rooms.all()   # las habitaciones creadas (y sus camas si es dorm)
```

- `data` se valida **exactamente como la API** (`RoomTypeSerializer`).
- Normalizaciones seguras, aplicadas solo en la provisión:
  - `name`/`description` en texto plano se toman como español.
  - `code` se **sanea**:
    - Se pasa a ASCII y a mayúsculas; cada tramo de otros caracteres se vuelve `-`; se recorta a 20 caracteres.
    - Ejemplos: `"Suite Vista"` → `SUITE-VISTA`, `"suíte"` → `SUITE`, `305` → `"305"`.
    - Si queda vacío o falta, se deriva del nombre y se mantiene único.
  - `kind` y los tipos de cama no distinguen mayúsculas (`" Dorm "` → `dorm`, `"Queen"` → `queen`).
  - `size_m2` se redondea a 2 decimales.
  - La ocupación que falte se completa.
- Errores (**no se crea nada**):
  - `validation_error`, con `fields` sobre cualquier campo de la categoría y además `data`, `floor` y
    `beds_per_room`. `beds_per_room` también falla si un dormitorio con habitaciones quedaría sin camas:
    `beds_per_room=0`, o `None` sin configuración de camas.
  - `invalid_room_numbers`.
  - `duplicate_room_numbers`, con `duplicates` (los que ya existen o se repiten) y `fields.room_numbers`.
  - Un código de categoría ya usado en la propiedad → `validation_error` en `code`.
- **Concurrencia**: bloquea la fila de la propiedad, así que dos provisiones simultáneas (doble envío, reintento)
  quedan en serie. La segunda recibe `validation_error` (código) o `duplicate_room_numbers`, nunca un
  `IntegrityError`. Está probado con dos hilos reales.
- Funciona dentro de la transacción del llamador (C9 envuelve provisión + tarifas + perfil).
- Audita `inventory.room_type_provisioned` y emite `inventory_changed(room_type_ids=[id], start=None, end=None)`
  al hacer commit.
- Amenidades: acepta códigos del catálogo global y los propios de la organización. Uno desconocido → error en
  `amenities`, con los códigos. C9 debe filtrar la propuesta contra `GET amenities/`.

**Helpers públicos adicionales** (no son contrato del spec, pero son estables):

| Helper | Uso |
|---|---|
| `apps.inventory.custom_fields.custom_field_definitions(*, organization, applies_to, property=None)` | Definiciones con el alcance correcto (org + propiedad) |
| `apps.inventory.custom_fields.clean_custom_values(defs, values, *, partial=False)` | Como `validate_custom_values`; con `partial=True` valida solo las claves dadas, sin defaults ni obligatoriedad |
| `apps.inventory.numbering.parse_room_numbers(spec)` / `infer_floor(number)` | Validar rangos de números (por ejemplo en la revisión del onboarding) |
| `apps.inventory.services.inventory_summary(property)` | El mismo payload de `GET summary/` |
| `services.bulk_create_rooms`, `bulk_update_rooms`, `delete_room`, `reset_override`, `save_room_type`, `save_room`, `save_bed`, `create_beds`, `delete_bed`, `duplicate_room_type`, `create_custom_field`, `update_custom_field`, `delete_custom_field`, `save_amenity`, `delete_amenity`, `add_photo`, `update_photo_caption`, `reorder_photos(photos, ids, *, gallery=None, actor=None)` | Lo que usa la API, con auditoría y señales (cada una en su transacción). Mejor usar estos que escribir directo en los modelos. |

**Consumidos:** `core.tenancy`, `core.audit`, `core.signals`, `core.errors`, y los modelos de bookings en modo
lectura (`Stay`, `ACTIVE_STAY_STATUSES`) para las reglas de "en uso". No se usa ningún servicio de otra app.

---

## Señales emitidas / escuchadas

Emitidas siempre con `send_on_commit`:

| Señal | Cuándo | `start`, `end` |
|---|---|---|
| `inventory_changed(property, room_type_ids, start, end)` | `block_room` / `release_block` | rango del bloqueo `[start, end)` |
| ídem | crear, borrar, desactivar o activar habitaciones (una, masiva o provisión); cambiar una habitación de categoría (**ambas** categorías en `room_type_ids`); crear, desactivar o borrar camas; crear una categoría o cambiar su `is_active` | `None, None` (todo el horizonte) |
| `room_status_changed(room, old, new)` | `set_housekeeping_status` con cambio real (API `status/`, `bulk-update` con `housekeeping_status`, otras apps) | — |

- `room_type_ids` es una lista de UUID, sin repetidos.
- Cambiar atributos que no afectan las unidades (color, nombre, amenidades…) **no** emite nada.
- Escuchadas: ninguna señal de dominio. Internamente, `post_delete` de `Photo` borra el archivo al hacer commit.

Acciones de auditoría (`AuditEvent.action`), todas con actor. Llevan propiedad salvo las de nivel organización
(amenidades propias y campos personalizados de alcance organización: `property = null`, `organization` puesta).
Ninguna es reversible. Toda escritura de la API de inventario queda auditada:

`inventory.property_updated, logo_updated, logo_removed, room_type_created, room_type_updated,
room_type_deleted, room_type_provisioned, room_created, room_updated, room_deleted, rooms_bulk_created,
rooms_bulk_updated, room_override_reset, room_status_changed, room_blocked, block_released, bed_created,
bed_updated, bed_deleted, beds_created, custom_field_created, custom_field_updated, custom_field_deleted,
amenity_created, amenity_updated, amenity_deleted, photo_added, photo_updated, photos_reordered, photo_deleted`.

C12 (auditoría): para ver los eventos de una propiedad incluye también los de su organización con
`property IS NULL`.

## Automatizaciones registradas

Ninguna.

## Proveedores de integración registrados

Ninguno.

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

- **Rutas** (`routes.tsx`, carga perezosa; todas se anidan en `SettingsLayout`):
  - `settings/property`
  - `settings/room-types` y `settings/room-types/:roomTypeId` (`new` para crear)
  - `settings/rooms` y `settings/rooms/:roomId`
  - `settings/custom-fields`
- `nav.ts` queda sin cambios (los ítems del plan).
- No exporta widgets, pestañas, acciones, topbar ni comandos.

Componentes reutilizables, en `frontend/src/features/inventory/components/`:

| Componente | Props | Uso sugerido |
|---|---|---|
| `RoomStatusBadge` (export nombrado y default) | `status`, `className?` | Estado de limpieza (C1, C2, C13); usa `StatusBadge kind="room"` |
| `RoomKeyTag` | `number`, `status?` (incluye `occupied`), `inactive?`, `size? sm\|md\|lg` | Número de habitación como llave del casillero de recepción, teñida por estado |
| `CategoryChip` | `code`, `name?`, `color`, `showName?` | Color, código y nombre de la categoría |
| `AmenityPicker` | `mode="select"` (`value`, `onChange`) o `mode="inherit"` (`inherited`, `extra`, `removed`, `onChange`) | Selección de amenidades agrupadas por tipo |
| `CustomFieldInput` | `definition`, `value`, `onChange`, `labelledBy?`, `id?` | Input de un campo personalizado según su tipo (B3 o C1 lo pueden usar para huésped o reserva) |
| `PhotoGallery` | `roomTypeId \| null`, `canEdit`, `label` | Galería con subida, arrastre y botones para mover |
| `InheritedField`, `I18nTextInput`, `BedConfigEditor`, `ViewSelect`, `TabErrorDot`, `SaveBar` | — | Piezas internas; se pueden reusar |

- `api.ts` tiene los tipos (`Room`, `RoomType`, `EffectiveAttributes`, `CustomFieldDefinition`, `RoomBlock`,
  `InventorySummary`, `PropertyProfile`…), las query keys `inventoryKeys` y los hooks `useRooms(filters)`,
  `useRoom`, `useRoomEffective`, `useRoomTypes`, `useRoomType`, `useAmenities`, `useCustomFields(appliesTo?)`,
  `useBlocks(filters)`, `useBeds`, `usePhotos`, `usePropertyProfile`, `useInventorySummary` y
  `useInvalidateInventory()`.
- `lib/`:
  - `roomNumbers.ts`: el mismo parser de rangos que el backend.
  - `amenityIcons.ts`.
  - `attributes.ts`: textos de atributos y reglas de ocupación.
  - `fieldErrors.ts`: `flattenFieldErrors(fields)` pasa los `fields` de la API a claves con punto
    (`custom_values.minibar`).
  - `text.ts`: `tr(i18n, lang)` y `naturalCompare`.

UI (resumen):
- **Propiedad**: secciones General · Ubicación y contacto · Datos legales · Horarios e idiomas · Reglas y
  políticas · Marca · Fotos del hotel, con barra de guardado.
- **Categorías**: tarjetas con portada, color, unidades y capacidad. El editor tiene las pestañas General ·
  Capacidad y camas · Amenidades · Fotos (arrastrar y ordenar) · Campos personalizados.
- **Habitaciones**:
  - Tabla agrupada por categoría, con filtros y selección múltiple → edición masiva en un panel lateral.
  - Creación masiva con vista previa exacta, que marca repetidos y existentes.
  - Editor con valores heredados en gris ("Heredado de …"), botones "Sobrescribir" y "Restaurar herencia" por
    campo, y las pestañas Amenidades, Campos personalizados, Camas (solo dorm) y Bloqueos.
- **Campos personalizados**: definiciones por destino.
- **Nuevo:** los errores de validación del servidor aparecen junto a su campo. El editor salta a la pestaña que
  los contiene y la marca con un punto. Su nombre accesible incluye ", con errores".
- **Recorrido de los niveles de herencia** (verificador): el editor de categoría enlaza a "Ver sus N
  habitaciones" (`/app/settings/rooms?room_type=<id>`: la página de habitaciones lee y escribe ese filtro en la
  URL); el chip de categoría del editor de habitación enlaza a su categoría ("Abrir la categoría …"); la pestaña
  Camas muestra el tercer nivel en los dormitorios.
- **Editores que no pierden trabajo** (verificador): los editores de habitación y de categoría ya no se remontan
  cuando llega una versión nueva del servidor (`lib/useServerDraft.ts`): después de guardar se quedan en la
  pestaña abierta, y si otra persona cambia el registro mientras editas (p. ej. housekeeping pone la habitación
  sucia) los campos que no tocaste toman el valor nuevo y lo que escribiste se conserva.
- **Nueva habitación** pide los campos personalizados de habitación obligatorios sin valor por defecto (antes la
  creación fallaba sin mostrar nada) y muestra los errores del servidor que no son del número.
- Los filtros, la creación masiva (que arranca en la categoría filtrada), el reintento de carga (reintenta
  categorías y habitaciones) y los errores de la edición masiva (dicen qué habitaciones fallan) se corrigieron en
  la verificación.

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

1. **`backend/config/settings.py` (B-INT):** `manage.py spectacular --validate` da 5 warnings de colisión de
   nombres de enum. Dos vienen de inventario: `KindD0cEnum` (RoomType.kind, usado también por componentes de
   bookings y rates) y `KindE3fEnum` (RoomBlock.kind). Los otros tres vienen de guests y bookings. Propuesta:
   ```python
   SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"] = {
       "RoomTypeKindEnum": "apps.inventory.models.RoomType.Kind",
       "RoomBlockKindEnum": "apps.inventory.models.RoomBlock.Kind",
       # y los de guests (GuestDocument.kind) y bookings (status, source) que reporten B3/B2b
   }
   ```
2. **`frontend/src/test/setup.ts` (B-INT):** agregar `afterEach(() => toast.dismiss())` (de `sonner`).
   - Sonner 2.0.8 reenvía los toasts activos al `<Toaster>` del test siguiente. Ocurre en `Observer.subscribe`,
     que hace replay de `getActiveToasts()`.
   - Con eso, un test puede ver un toast de otro. Aquí lo resolví solo en `PhotoGallery.test.tsx`.
3. **Media de desarrollo:** el intento anterior sembró fotos con la ruta duplicada
   `photos/2026/09/photos/seed/<slug>.jpg`. El bug ya está corregido; ahora el seed guarda en
   `photos/seed/<slug>.jpg` y las subidas en `photos/<año>/<mes>/<uuid>.<ext>`. Las filas viejas siguen
   funcionando, y `seed_demo --reset` las regenera limpias.
4. **C2 (housekeeping):** crea su propio endpoint de estado para el rol housekeeping, que no tiene
   `inventory.manage`, y llama a `set_housekeeping_status`.
5. **C4:** en producción las fotos necesitan un servidor de media. Hoy `/media/` lo sirve Django solo con
   `DEBUG` (ver A1). Es tema de D1.

## Limitaciones conocidas / pendientes

- **Undo:** las acciones de inventario se auditan pero no son reversibles (no hay handler de undo).
- **Paginación:** las listas de catálogo (`rooms/`, `room-types/`, etc.) no se paginan. Es una desviación
  deliberada del spec §3.1; ver "API implementada".
- **Campos obligatorios nuevos:** no se rellenan en los registros existentes. Se exigen en el siguiente guardado
  de cada categoría o habitación, y la UI lo muestra en el campo. La creación de **una** habitación los pide
  (API y diálogo); la creación **masiva** y `provision_room_type` solo aplican los valores por defecto (una
  definición obligatoria sin valor por defecto no bloquea crear en bloque).
- **Alcance organización:** cualquier miembro con `inventory.manage` en una propiedad puede crear, editar o borrar
  amenidades propias y campos personalizados de alcance organización, que afectan a todas las propiedades de la
  organización (mismo criterio que los huéspedes, que son por organización). Si se quiere restringirlo a
  miembros con `all_properties`, es un cambio pequeño en `AmenityViewSet`/`CustomFieldViewSet`.
- **Sin UI (la API ya los soporta):**
  - `connecting_rooms` (habitaciones comunicadas).
  - `Photo.room` (fotos por habitación; el plan solo pedía fotos por categoría).
  - En la edición masiva, los overrides de nombre, descripción y camas: el panel ofrece los campos más comunes y
    la API acepta `overrides.<campo>` para todos.
- **Bloqueos:** con `force` se puede bloquear una habitación con reservas. Las reservas no se tocan: reasignarlas
  es tarea de recepción o de `assign_room` (B2b). No hay una página global de bloqueos; se gestionan por
  habitación y el calendario (C13) los muestra.
- **Fotos del seed:** vienen de `https://picsum.photos/seed/<slug>-<n>/1200/800`, que son imágenes genéricas, no
  de hoteles. Sin red (o con `SEED_OFFLINE=1`) se generan degradados cálidos con Pillow, determinísticos.
- **Revisión visual:** la hice con un Chrome headless propio, manejado por CDP desde un script. No usé el
  navegador compartido del MCP porque B2a y B4 lo estaban usando. El verificador repitió la revisión igual
  (Chrome headless propio con perfil temporal en el puerto 9333).
- **Rastro de la verificación en la BD de desarrollo:** la prueba en vivo del verificador agregó y quitó una
  amenidad (Bañera) a la habitación 110 de Casa Aurora y la pasó a sucia y de vuelta a limpia. Todo quedó como
  estaba; solo quedan esos eventos en la auditoría.

---

## Tests obligatorios (plan B1) → dónde están

| Requisito | Tests |
|---|---|
| Herencia: categoría, override con bandera, reset | `test_services_basic.py::TestEffectiveAttributes`, `test_services.py::TestResetOverride`, `test_api_rooms.py::TestInheritanceEndpoints` y `TestList` |
| Validación de custom values: tipo, requerido, opción inválida | `test_services_basic.py::TestValidateCustomValues`, `test_api_rooms.py`, `test_api_custom_fields.py` |
| Bulk-create: `"101-103,105"` → 4; duplicados → 400 | `test_services.py::TestBulkCreateRooms`, `test_api_rooms.py::TestBulkCreate`, `test_numbering.py` |
| Bulk-update solo afecta a los seleccionados | `test_services.py::TestBulkUpdateRooms`, `test_api_rooms.py::TestBulkUpdate` |
| Camas para dorm | `test_api_beds.py`, `test_provision.py::TestDorms`, `test_services.py` (bulk-create dorm) |
| `block_room` / `release_block` emiten `inventory_changed` (on_commit) | `test_services_basic.py::TestBlocks`, `test_api_blocks.py` |
| `set_housekeeping_status` emite `room_status_changed` | `test_services_basic.py::TestHousekeepingStatus`, `test_api_rooms.py::TestStatus` |
| `provision_room_type` crea categoría, habitaciones, camas y amenidades | `test_provision.py` (normalización, validación, concurrencia, efectos) |
| Borrar habitación con reservas activas → 409 | `test_services.py::TestDeleteRoom`, `test_api_rooms.py::TestDelete` |
| Aislamiento multi-tenant y permisos (housekeeping no edita) | `test_api_access.py` (todas las rutas: anónimo 401, otra org 404, housekeeping y recepción 403 al escribir) |
| Seed | `test_seed.py` |
| Frontend: editor de habitación (heredado vs sobrescrito), creación masiva y validación | `RoomEditorPage.test.tsx`, `BulkCreateDialog.test.tsx`, `roomNumbers.test.ts`, además de `RoomsPage`, `RoomTypeEditorPage`, `RoomTypesPage`, `PropertyPage`, `CustomFieldsPage`, `CreateRoomDialog`, `CustomFieldInput`, `PhotoGallery` y `fieldErrors` |
| N+1 en listados (verificador) | `test_api_rooms.py::TestList::test_the_number_of_queries_does_not_grow_with_the_rooms`, `test_api_room_types.py::TestList::test_the_number_of_queries_does_not_grow_with_the_categories` (probados con mutación: quitar un `prefetch_related` los pone en rojo) |

## Correcciones del verificador (2026-09-26)

Cada corrección de comportamiento tiene su test, visto primero en rojo por la razón esperada y después en verde.
Las guardas de N+1 (el comportamiento ya era correcto) se validaron por mutación.

Backend:
1. **Pérdida del estado de limpieza al editar una habitación.** `save_room` y `bulk_update_rooms` hacían
   `room.save()` completo y reescribían el `housekeeping_status` leído al empezar: un check-out (→ sucia) o una
   camarera que la limpiaba en ese momento se perdía. Ahora se guardan solo las columnas editadas.
   Tests: `test_services.py::TestHousekeepingStatusIsNeverOverwritten` (edición simple y en bloque).
2. **Escrituras sin auditar.** Crear, editar y borrar amenidades propias, editar la descripción de una foto y
   reordenar fotos no dejaban `AuditEvent` (la nota decía que todo se auditaba). Nuevos servicios
   `save_amenity`, `delete_amenity`, `update_photo_caption` y `reorder_photos(..., gallery=, actor=)`.
   Tests: `test_api_amenities_summary.py::test_own_amenity_changes_are_audited`,
   `test_api_photos.py::test_caption_edits_and_reorders_are_audited`.
3. **Campo personalizado creado sin su auditoría.** La vista creaba la definición y después auditaba, fuera de una
   transacción. Ahora `services.create_custom_field` hace ambas cosas atómicamente.
   Test: `test_api_custom_fields.py::test_creation_is_audited_together_with_the_definition`.
4. **Código de amenidad fantasma en los perfiles.** Borrar o re-codificar una amenidad propia dejaba su código en
   `Property.settings["amenities"]` y el siguiente guardado del perfil fallaba con "Amenidades desconocidas" sin
   que la UI pudiera mostrar ni quitar ese código. Ahora los perfiles de la organización siguen el cambio.
   Test: `test_api_amenities_summary.py::test_the_property_profiles_follow_a_deleted_or_recoded_amenity`.
5. Guardas de N+1 (ver la tabla) y docstring de `inventory_summary` corregido (anunciaba una advertencia
   `inactive_room_type_with_rooms` que no existe).

Frontend:
1. **Los editores de habitación y categoría se remontaban con cada versión nueva del servidor** (la `key` incluía
   `updated_at`): tras guardar volvían a la primera pestaña, y una recarga en segundo plano (p. ej. al volver a la
   ventana después de que housekeeping cambió el estado) borraba lo que el usuario estaba escribiendo. Nuevo hook
   `lib/useServerDraft.ts` (rebase de los campos no tocados). Tests en `RoomEditorPage.test.tsx` y
   `RoomTypeEditorPage.test.tsx` ("stays on the tab…", "keeps what the user is typing…").
2. **Perfil: errores anidados como "[object Object]".** Los errores de `branding.primary_color` o de
   `policies.*` se mostraban así; ahora se aplanan y se muestran junto a su campo. Descripción, reglas de la casa,
   idiomas y amenidades también muestran su error. Tests en `PropertyPage.test.tsx`.
3. **Nueva habitación fallaba en silencio** si había un campo de habitación obligatorio sin valor por defecto (el
   diálogo solo mostraba errores del número). Ahora pide esos campos y muestra cualquier otro error del servidor.
   Tests: `CreateRoomDialog.test.tsx`.
4. **Opciones numéricas** (la API acepta números como valor de opción): el select enviaba `"2"` en vez de `2`
   (rechazado por el backend), el multiselect no marcaba los valores guardados, y editar la etiqueta del campo
   reescribía los valores como texto, así que el backend los veía como opciones quitadas y borraba los datos que
   las usaban. Tests: `CustomFieldInput.test.tsx`, `CustomFieldsPage.test.tsx`.
5. **Habitaciones:** el reintento solo recargaba las habitaciones (no las categorías); "Crear en bloque" ignoraba
   la categoría filtrada; la edición masiva rechazada no decía qué habitaciones fallaban. Además, el filtro de
   categoría vive en la URL (`?room_type=`) y hay enlaces categoría ↔ habitaciones. Tests en
   `RoomsPage.test.tsx`, `RoomTypeEditorPage.test.tsx` y `RoomEditorPage.test.tsx`.

Revisado y sin cambios: cada fila de la tabla API del plan B1 existe; permisos y aislamiento de cada endpoint (`test_api_access`
cubre anónimo 401, otra org 404, housekeeping/recepción 403); firmas de contrato; `send_on_commit` en todas las
señales; formato `{detail, code, fields}`; seed contra el spec §10 e idempotencia (también con una corrida real
sobre la BD de desarrollo dentro de una transacción con rollback: mismos conteos tras dos corridas, sin
advertencias en el resumen de las tres propiedades); i18n sin textos fijos en la UI.

## Verificación (corrida real del verificador, 2026-09-26)

```bash
docker compose run --rm -e TEST_DB_NAME=test_b1v backend pytest apps/inventory -q        # 296 passed (eran 288)
docker compose run --rm -e TEST_DB_NAME=test_b1v backend pytest apps/core/tests/test_contracts.py -q   # 142 passed
docker compose run --rm -e TEST_DB_NAME=test_b1v backend pytest apps/core/tests/test_domain_contract.py -q  # 211 passed
docker compose run --rm -e TEST_DB_NAME=test_b1v backend pytest apps/bookings/tests/test_inventory.py \
  apps/bookings/tests/test_consistency.py apps/bookings/tests/test_api_misc.py \
  apps/bookings/tests/test_availability_basic.py apps/guests -q                           # 208 passed (usan inventario)
docker compose run --rm backend ruff check apps/inventory && ruff format --check apps/inventory   # limpio
docker compose run --rm backend python manage.py check                                   # sin problemas
docker compose run --rm backend python manage.py makemigrations inventory --check --dry-run   # No changes
docker compose run --rm backend python manage.py spectacular --validate                  # 0 errores; 5 warnings de enums (B-INT, abajo)
cd frontend && npx vitest run src/features/inventory                                     # 12 archivos, 62 tests (eran 46)
docker compose run --rm --no-deps frontend npx vitest run src/features/inventory         # ídem en Node 24
npx tsc -p tsconfig.app.json --noEmit                                                    # exit 0, sin errores
npx eslint src/features/inventory                                                        # limpio
npx vitest run src/lib/__tests__/i18n.test.ts src/app/__tests__/extensions.test.ts src/app/__tests__/router.test.tsx  # 32 passed
```

Prueba en vivo del verificador (Chrome headless propio por CDP, `owner@casaaurora.co`), consola sin errores:
- Editor de categoría → "Ver sus 10 habitaciones" → habitaciones filtradas por DBL (URL `?room_type=`) →
  habitación → "Abrir la categoría Estándar" vuelve a la categoría.
- Guardar desde la pestaña Amenidades deja esa pestaña abierta tras la recarga.
- Con el piso escrito sin guardar, cambiar el estado a sucia por la API y volver a la ventana (recarga tras 30 s):
  el badge pasa a "Sucia" y el piso escrito se conserva.
- Perfil con color `#12` → "Color inválido (#RRGGBB)" en la sección Marca, sin "[object Object]".
- 375 px en claro y oscuro (editor de categoría, habitaciones filtradas, diálogo de nueva habitación, editor de
  habitación): sin desbordamiento horizontal; las pestañas se desplazan.

De la corrida de implementación (sigue siendo válido):
- Payloads de ejemplo: salen de la BD de desarrollo. Las escrituras de ejemplo corrieron dentro de una transacción
  con rollback, y después comprobé que no quedó nada escrito.
- Revisión visual en Chrome headless propio, sin errores de consola:
  - Anchos: 1440 px y 375 px. Temas claro y oscuro.
  - Vistas: habitaciones, editor de habitación (incluido el estado de error del servidor), categorías, editor de
    categoría y fotos, propiedad, campos personalizados.
