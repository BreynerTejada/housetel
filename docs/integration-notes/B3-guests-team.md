# B3 — Huéspedes (CRM), usuarios y roles — integration notes

Estado: tarea completa y verificada. La implementación retomó un intento interrumpido; después pasó una
verificación independiente que corrigió 6 defectos de backend (2 de seguridad) y 9 de frontend, todos con TDD
(ver "Verificación B3 — lo corregido"). Owner paths: `backend/apps/guests/**`, `backend/apps/accounts/**`,
`frontend/src/features/guests/**`, `frontend/src/features/team/**` y esta nota. No se tocó nada fuera de ellos.

Lectura rápida para otras tareas:

- **C1 (asistente de reserva, check-in):** usa `GuestPicker` (sección "Extensiones de frontend") y manda al
  backend `booker_id` (huésped existente) o `booker` (GuestInput nuevo; `create_reservation` hace el upsert).
- **C5 (portal):** los documentos de identidad se guardan con `add_document(..., uploaded_via="portal")` y
  **nunca** tienen URL pública; en la UI de staff se ven por `GET /api/v1/guests/documents/<id>/file/`.
- **C6/C7:** si guardan copias de datos personales del huésped, suscríbanse a `guest_anonymized` y
  `guests_merged` (sección "Señales").
- **Cualquier app con FK o M2M a `Guest`:** la fusión las reapunta sola (genérico sobre
  `Guest._meta.related_objects`). No hay que registrarse en ningún lado.

---

## API implementada

Todas las rutas de staff exigen sesión + `X-Property-Id` (reglas de A1: 400 `property_required`, 404 si la
propiedad no es accesible, 403 `permission_denied` con `permission`, 402 si la organización está suspendida,
salvo los endpoints de equipo: ver "Equipo").
**Los huéspedes son de la organización** (`OrganizationScopedMixin`): cualquier hotel de la cadena ve los
mismos huéspedes, también un miembro restringido a otro hotel de la misma organización. Errores con la forma
`{detail, code, fields?, ...extra}`.

### Huéspedes (`/api/v1/guests/`)

| Método y path | Permiso | Descripción |
|---|---|---|
| `GET guests/` | `guests.view` | Lista paginada (`page`, `page_size` ≤ 200). Excluye fusionados. Filtros: `q`, `is_vip`, `blacklisted`, `nationality` (ISO-2, sin distinguir mayúsculas), `tag`, `has_stays` (`true`/`false`). Orden: `ordering=last_name\|first_name\|created_at\|stays_count\|last_stay_date` (prefijo `-`); siempre desempata por `id`, así las páginas nunca repiten ni saltan huéspedes |
| `POST guests/` | `guests.manage` | Crea (normalizado). Documento ya registrado → 409 `guest_exists` con `guest_id` |
| `GET guests/<id>/` | `guests.view` | Detalle + `stats` (también funciona para fusionados/anonimizados, en solo lectura) |
| `PATCH/PUT guests/<id>/` | `guests.manage` | Edita. Fusionado → 409 `guest_merged` (+`guest_id` del principal); anonimizado → 409 `guest_anonymized`; tomar el documento de otro → 409 `guest_exists` |
| `DELETE guests/<id>/` | `guests.manage` | Solo si nada lo referencia; si tiene historial → 409 `guest_in_use` con `relations` (usar anonimizar o fusionar) |
| `GET guests/<id>/stays/` | `guests.view` | Reservas como titular u ocupante, en todos los hoteles de la org, más recientes primero (paginado) |
| `GET guests/<id>/documents/` | `guests.view` | Documentos de identidad (metadatos + `file_url` privado) |
| `POST guests/<id>/documents/` | `guests.manage` | multipart `kind` (`id_front\|id_back\|passport\|signature\|other`) + `file` (JPG/PNG/WebP/HEIC/PDF por contenido, ≤ 10 MB). 400 `invalid_file_type` / `file_too_large` |
| `DELETE documents/<doc_id>/` | `guests.manage` | Borra el documento (el archivo se elimina al confirmar la transacción) |
| `GET documents/<doc_id>/file/` | `guests.view` | **Único acceso al archivo** (stream). `?download=1` → attachment. Cabeceras `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store` |
| `GET guests/<id>/duplicates/` | `guests.view` | Posibles duplicados con `reasons` |
| `GET guests/lookup/?first_name&last_name&email&phone&document_type&document_number&nationality&country_of_residence` | `guests.view` | Duplicados de datos **sin guardar** (lo usan el formulario y el `GuestPicker` antes de crear) |
| `POST guests/merge/` | `guests.merge` | `{primary_id, duplicate_id, confirm: true}` → detalle del principal. Sin `confirm` → 400 `confirmation_required`; de otra org → 404; ya fusionado → 409 `already_merged`; anonimizado → 409 `guest_anonymized` |
| `GET guests/<id>/export/` | `guests.export` | Habeas Data (derecho de acceso): descarga JSON `huesped-<id>.json`; se audita `guests.exported` |
| `POST guests/<id>/anonymize/` | `guests.export` | Habeas Data (supresión): `{confirm: true}` → detalle anonimizado. Irreversible; 409 `already_anonymized`; registro ya fusionado → 409 `guest_merged` con el `guest_id` del principal (anonimizar el principal borra también sus fusionados) |
| `GET guests/tags/` | `guests.view` | Etiquetas usadas en la org (para filtros y autocompletar) |

Búsqueda `q`: cada palabra debe coincidir con nombre o apellido (sin tildes, extensión `unaccent`), email,
dígitos del teléfono (≥ 3) o documento; la consulta completa también casa un teléfono o documento con
formato (`"300 111 2233"`, `"1.020.304.050"`).

Fila de `GET guests/` (también de `duplicates`/`lookup`, que agregan `reasons`):

```json
{"id": "f46c6f95-…", "first_name": "Alejandro", "last_name": "Castaño Pérez", "full_name": "Alejandro Castaño Pérez",
 "email": "alejandro.castano164@example.net", "phone": "+573009154025", "document_type": "CC",
 "document_number": "72090316", "nationality": "CO", "country_of_residence": "CO", "city_of_residence": "Cartagena",
 "language": "es", "is_vip": false, "blacklisted": false, "tags": [], "is_foreign_non_resident": false,
 "anonymized_at": null, "stays_count": 0, "reservations_count": 0, "last_stay_date": null,
 "created_at": "2026-09-26T18:46:17.062204-05:00"}
```

Detalle = fila + `birth_date, gender (F|M|X|""), address, notes, preferences {clave: texto}, marketing_consent,
data_processing_consent_at, custom_values, merged_into, updated_at, documents_count` y:

```json
"stats": {"reservations_count": 4, "stays_count": 3, "nights": 8, "total_spent": "2450000.00",
          "cancellations": 1, "no_shows": 0,
          "last_stay": {"reservation_id": "…", "code": "HT-7K2M9Q", "property_id": "…", "property_name": "Hotel Casa Aurora",
                        "checkin": "2026-06-01", "checkout": "2026-06-04", "status": "checked_out"},
          "next_stay": null}
```

Definiciones de `stats` (a nivel organización): reservas = titular u ocupante; estancias = reservas
`checked_in`/`checked_out`; noches = Σ noches de esas; `total_spent` = Σ (neto + IVA) de cargos no anulados de
folios de reservas donde es **titular** (los acompañantes no pagan); próxima = `tentative`/`confirmed` con
llegada ≥ fecha de negocio de la propiedad del header. `stays_count`, `reservations_count` y `last_stay_date`
de la fila coinciden con `stats` también en el detalle.

Escritura (`POST`/`PATCH`): `first_name` (obligatorio al crear), `last_name, email, phone, document_type,
document_number, nationality, country_of_residence, city_of_residence, birth_date, gender, address, language
(es|en), is_vip, blacklisted, tags (≤ 20 × 40 car.), notes, preferences, marketing_consent, custom_values`
(validados contra `CustomFieldDefinition(applies_to="guest")` de la org/propiedad con
`inventory.services.validate_custom_values`) y `data_processing_consent` (solo escritura: `true` registra
ahora la autorización Habeas Data si no existía, `false` la revoca). Validaciones: teléfono utilizable, país
ISO-2, `document_type` requerido si hay número, fecha de nacimiento no futura.

Documento:

```json
{"id": "7a41293e-…", "guest": "0c9264b9-…", "kind": "passport", "uploaded_via": "staff",
 "created_at": "2026-09-26T18:46:44.518754-05:00", "file_url": "/api/v1/guests/documents/7a41293e-…/file/",
 "content_type": "image/png", "filename": "passport-20260926.png", "size": 24}
```

Fila de `stays/`: `{id (reserva), code, status, source, channel_code, checkin, checkout, nights, adults,
children, total_amount, currency, property: {id, name}, role: "booker"|"occupant", rooms: ["101"]}`.

### Equipo (`/api/v1/accounts/`, se suman a `auth/*` y `me/` de A1 sin cambiarlos)

Como pide el spec §3 ("402 en toda la API de staff **excepto accounts** y saas/billing"), estos endpoints
siguen respondiendo cuando la organización está `suspended` (`allow_suspended = True`): el dueño puede
quitar accesos o invitar a quien resuelva el pago. Huéspedes sí devuelve 402.

| Método y path | Permiso | Descripción |
|---|---|---|
| `GET users/` | `accounts.users_manage` | Miembros de la org (activos primero, incluye inactivos). `id` = **membership id** |
| `POST users/` | `accounts.users_manage` | Invita: `{email, role_id, all_properties=true, property_ids=[]}` → `Invitation` + `email_sent` (201). Envía `send_mail` (Mailpit en local) con `${FRONTEND_URL}/invite/<token>`. Si el SMTP falla, la invitación queda y `email_sent=false` (la UI muestra el enlace para compartirlo). Reinvitar el mismo email reemplaza la invitación pendiente (nuevo token, 7 días), salvo que esa invitación dé más acceso que el tuyo → 403 `permission_escalation`. Miembro activo → 409 `already_member` |
| `PATCH users/<membership_id>/` | `accounts.users_manage` | `{role_id?, all_properties?, property_ids?, is_active?}`. Desactivarse a sí mismo → 400 `cannot_deactivate_self` |
| `GET invitations/` | `accounts.users_manage` | Pendientes y vencidas (no aceptadas), `status` `pending\|expired`, `editable` (puedes reenviarla/revocarla). `invite_url` solo si está pendiente **y** es `editable`: el enlace es un secreto al portador (quien lo abre crea esa cuenta y entra con ese rol) |
| `POST invitations/<id>/resend/` | `accounts.users_manage` | Nuevo token (el anterior deja de servir) + 7 días + correo. Fuera de tu alcance → 403 `permission_escalation` |
| `DELETE invitations/<id>/` | `accounts.users_manage` | Revoca. Fuera de tu alcance → 403 `permission_escalation` |
| `GET roles/` | `accounts.roles_manage` **o** `accounts.users_manage` (para poder asignarlos) | Roles de sistema + propios con `members_count`, `assignable`, `editable` |
| `POST roles/` · `PATCH/PUT/DELETE roles/<id>/` | `accounts.roles_manage` | `{name, description?, permissions: [...]}`. Sistema → 409 `system_role`; permisos inexistentes → 400 `invalid_permissions` + `unknown`; nombre repetido → 400 `fields.name`; en uso (miembros o invitaciones pendientes) → 409 `role_in_use`. El `code` se genera del nombre y nunca choca con los de sistema (`owner_2`) |
| `POST roles/<id>/duplicate/` | `accounts.roles_manage` | Copia editable ("Copia de Recepción", "Copia de Recepción (2)"…) |
| `GET permissions/` | cualquier miembro | Catálogo agrupado por módulo, en el orden declarado en cada `permissions.py`: `[{code, label_es, label_en, permissions: [{code, label_es, label_en}]}]` |

Públicos (`/api/v1/public/accounts/`):

| Método y path | Descripción |
|---|---|
| `GET invitations/<token>/` | `{email, organization: {name}, role: {name, code}, properties: [nombres], all_properties, invited_by, expires_at, status: pending\|expired\|accepted, user_exists}` (sin token ni ids). Token desconocido → 404 |
| `POST invitations/<token>/accept/` | Exige CSRF (como el login) y usa el throttle `login`. Usuario nuevo: `{full_name, password}` (validadores de Django; errores en `fields`). Usuario existente: `{password}` con **su contraseña actual** (una invitación nunca cambia contraseñas) → 400 `invalid_credentials` si no coincide. Crea la membership con el rol y hoteles de la invitación, **inicia sesión** y responde `Me`. 409 `invitation_expired`, `invitation_used`, `already_member` (si ya es miembro activo, su rol no se toca) |

Miembro:

```json
{"id": "08037db4-…", "user": {"id": "32d62ef4-…", "email": "recepcion@casaaurora.co", "full_name": "Andrés Gómez",
 "phone": "", "last_login": "2026-09-25T22:26:58.809314-05:00"},
 "role": {"id": "bbbf65ee-…", "code": "front_desk", "name": "Recepción", "is_system": true},
 "all_properties": true, "properties": [], "is_active": true, "is_owner": false, "is_self": false,
 "editable": true, "created_at": "2026-09-25T22:18:32.411990-05:00"}
```

Rol:

```json
{"id": "aa23097d-…", "code": "recepcion_nocturna", "name": "Recepción nocturna", "description": "Turno de noche: …",
 "is_system": false, "permissions": ["bookings.checkin", "bookings.manage", "bookings.view", "…"],
 "members_count": 0, "assignable": true, "editable": true, "created_at": "2026-09-26T18:46:19-05:00"}
```

**Protecciones** (`apps/accounts/team.py`, clase `Grantor`), todas con 403 `permission_escalation` salvo la
del dueño:

1. Nadie crea, edita, copia, borra, asigna ni reenvía un rol con permisos que no tiene (`*` solo lo cubre `*`,
   porque también otorga permisos futuros); nadie edita a un miembro cuyo rol tiene más permisos.
2. **Alcance por hotel:** un miembro restringido a algunos hoteles solo da acceso a esos hoteles (nunca
   "todos los hoteles") y solo edita a miembros cuyo acceso cabe en el suyo. `editable` en `GET users/` ya lo
   refleja.
3. **Invitaciones pendientes (verificación):** misma regla que los miembros. Solo quien cubre el rol y los
   hoteles de una invitación puede reenviarla, reemplazarla (reinvitar el mismo correo) o revocarla, y solo
   esa persona recibe su `invite_url`. Antes un gerente podía copiar el enlace de una invitación de dueño,
   crear la cuenta con su propia contraseña y entrar como dueño.
4. La organización conserva siempre al menos un dueño activo: 409 `last_owner`.

---

## Contratos implementados / consumidos

Firmas intactas (las fija `apps/core/tests/test_contracts.py`, que sigue pasando):

| Contrato (`apps.guests.services`) | Comportamiento |
|---|---|
| `upsert_guest(organization, data: GuestInput, *, actor=None) -> Guest` | Normaliza (nombres en title case respetando partículas y mayúsculas mixtas deliberadas —"De la Hoz", "McDonald"—, email en minúsculas, teléfono E.164 leído en el país de residencia/nacionalidad y si no como CO, documento sin puntos ni espacios). Busca por documento (el documento de un fusionado lleva al principal), luego por email (entre huéspedes sin documento si se envió documento); rellena solo valores no vacíos y nunca reemplaza un documento existente; consentimientos solo se otorgan. Seguro ante creación concurrente del mismo documento |
| `update_guest(guest, data: dict, *, source="user", actor=None) -> Guest` | Normaliza igual; campos no editables → `invalid_field`. Auditoría `guests.guest_updated` con los **datos personales enmascarados** (`•••`), para que anonimizar no deje copias en el historial |
| `add_document(guest, *, kind, file, uploaded_via="staff") -> GuestDocument` | Tipo por contenido (no por nombre ni content-type del cliente), ≤ 10 MB, nombre aleatorio, almacenamiento privado |
| `find_duplicates(guest) -> list[Guest]` | Mismo número de documento (cualquier tipo), mismo email (sin mayúsculas) o mismo teléfono + apellido parecido (sin tildes, primer apellido o similitud ≥ 0.8). Funciona con huéspedes sin guardar. Cada resultado trae `duplicate_reasons` (`document`, `email`, `phone_name`), más razones primero. Nunca devuelve fusionados |
| `merge_guests(primary, duplicate, *, actor) -> Guest` | Reapunta **genéricamente** todas las relaciones (`Guest._meta.related_objects`, FK y M2M de cualquier app, p. ej. `Reservation.booker`, `Stay.occupants`, `Folio.guest`, `ReservationGroup.contact_guest`, documentos y fusionados previos). En M2M evita duplicar filas; si una relación única choca, esa fila queda en el duplicado. Rellena los campos vacíos del principal, combina etiquetas/preferencias/notas/banderas, el documento pasa al principal si no tenía, marca `merged_into`, audita `guests.merged` (sin valores personales) y emite `guests_merged`. Rechaza (ConflictError 409): ya fusionados → `already_merged`; anonimizados → `guest_anonymized` (rellenar un registro borrado devolvería datos personales), también si lo llama otra app |

Servicios adicionales de la app (no son contratos entre apps, pero se pueden usar): `anonymize_guest(guest, *,
actor)`, `export_guest(guest) -> dict`, `create_guest`, `delete_guest`, `delete_document`,
`check_document_file(file) -> extensión`, `document_owner(org, type, number)`, `guest_relations(guest)`,
`surviving_guest(guest)`; y en `apps.guests.selectors`: `guest_stats(guest, *, today)`, `reservations_of(guest)`,
`annotate_stays(qs)`, `has_stayed()`.

Anonimizar: borra nombre (queda "Huésped anonimizado"), contacto, documento, fecha de nacimiento, género,
dirección, ciudad, notas, preferencias, etiquetas, campos personalizados, banderas y consentimiento de
marketing, y **elimina los documentos y sus archivos**; conserva nacionalidad, país de residencia e idioma
(estadísticas e historia del IVA) y todas las relaciones (reservas, folios). También anonimiza los registros
fusionados en él. Audita `guests.anonymized` solo con nombres de campos. Un registro ya fusionado en otro no
se anonimiza por separado (ConflictError 409 `guest_merged` con el `guest_id` del principal): sus datos
también viven en el principal, así que la supresión se hace desde ahí.

Consumidos: `inventory.services.validate_custom_values` (campos personalizados de huésped); lectura por ORM de
`bookings.Reservation/Stay` y `finance.Charge` para estadísticas e historial; `accounts.services.add_member` y
`ensure_system_roles` (A1).

## Señales emitidas / escuchadas

Nuevas, en `apps/guests/signals.py` (enviadas con `apps.core.signals.send_on_commit`: solo tras el commit;
un receiver que falla se registra y no rompe a los demás). Suscribirse desde `apps/<app>/receivers.py`:

```python
from django.dispatch import receiver
from apps.guests.signals import guest_anonymized, guests_merged

@receiver(guest_anonymized)
def erase_copies(sender, guest, merged_ids, **kwargs): ...   # guest ya anonimizado; merged_ids: list[UUID]

@receiver(guests_merged)
def follow_merge(sender, primary, duplicate, **kwargs): ...   # FK/M2M ya se movieron; solo referencias no-FK
```

Registros que la ley obliga a conservar (facturas, reportes SIRE/TRA) siguen su propia regla de retención.
Escuchadas: ninguna. Señales de `core` emitidas: ninguna.

## Automatizaciones registradas

Ninguna.

## Proveedores de integración registrados

Ninguno.

## Seguridad: documentos de identidad privados

- Se guardan **fuera de `MEDIA_ROOT`** (lo que está bajo `MEDIA_ROOT` se sirve sin autenticación en
  `/media/`): en `settings.PRIVATE_MEDIA_ROOT` si existe; si no, en `<MEDIA_ROOT>-private`
  (`backend/media-private/` en desarrollo; `/tmp/housetel-test-media-private` en tests). Ruta
  `guest-documents/<organization_id>/<uuid>.<ext>` (el nombre original, que suele traer el nombre de la
  persona, no se conserva).
- `PrivateDocumentStorage` no tiene URL (`file.url` lanza error a propósito) y escribe un `.gitignore` con `*`
  en su raíz para que los documentos nunca terminen en git.
- La API expone solo `file_url = /api/v1/guests/documents/<id>/file/` (sesión + `X-Property-Id` +
  `guests.view`, acotado a la organización). En el frontend, `<img src>` no puede enviar cabeceras: la UI
  descarga el archivo con el cliente `api` y muestra un object URL (`usePrivateFileUrl`).
- El admin de Django muestra el nombre almacenado y un enlace a su propia vista de descarga, protegida por la
  sesión del admin (`admin:guests_guestdocument_file`); subir desde el admin aplica las mismas validaciones.
- Verificado en vivo: con sesión y header 200 (bytes idénticos), sin header 400, anónimo 401, misma ruta bajo
  `/media/` 404.

## Extensiones de frontend exportadas

### `GuestPicker` (`@/features/guests/components/GuestPicker`) — para C1 y cualquier flujo de reserva

```tsx
import { GuestPicker } from '@/features/guests/components/GuestPicker'
import { isExistingGuest, type GuestPickerValue } from '@/features/guests/api'

const [booker, setBooker] = useState<GuestPickerValue | null>(null)
<Label htmlFor="booker">Huésped</Label>
<GuestPicker id="booker" value={booker} onChange={setBooker} aria-invalid={!!error} aria-describedby="booker-error" />

// al enviar la reserva (B2b acepta booker_id o booker como GuestInput):
const guestPart = isExistingGuest(booker) ? { booker_id: booker.id } : { booker }
```

| Prop | Tipo | Notas |
|---|---|---|
| `value` | `GuestSummary \| GuestInput \| null` | Controlado |
| `onChange` | `(value) => void` | Recibe un huésped existente (`GuestSummary`, tiene `id`), uno nuevo (`GuestInput`, **sin guardar**; el backend hace upsert al reservar) o `null` al pulsar "Cambiar" |
| `id` | `string?` | Id del input de búsqueda, para un `<Label htmlFor>` externo |
| `placeholder`, `disabled`, `autoFocus`, `className` | | |
| `allowCreate` | `boolean` (true) | Ofrece "Crear huésped nuevo" en línea |
| `aria-invalid`, `aria-describedby` | | Se pasan al input |

Comportamiento: búsqueda con debounce de 300 ms (8 resultados, combobox accesible con flechas/Enter/Escape);
"Crear «texto» como huésped nuevo" precarga el formulario según lo escrito (email, teléfono, documento o
nombres); el formulario en línea (nombres, apellidos, tipo y número de documento, correo, teléfono,
nacionalidad y residencia; al elegir una nacionalidad extranjera propone pasaporte) consulta
`guests/lookup/` y muestra **"Posible duplicado"** con las razones y "Usar este perfil". **No renderiza un
`<form>` y nunca envía el formulario que lo contiene** (Enter en sus campos no hace submit): se puede poner
dentro del formulario del asistente.

### Otros exports reutilizables

- `features/guests/api.ts`: tipos (`GuestSummary`, `Guest`, `GuestInput`, `DuplicateGuest`, `GuestDocument`,
  `GuestStay`, `GuestPickerValue`), `isExistingGuest`, hooks `useGuest(id)`, `useGuests(params)`,
  `useGuestSearch(q)`, `useGuestLookup(input)`, `useGuestStays`, `useGuestDocuments`, mutaciones y
  `fetchPrivateFile`/`usePrivateFileUrl` (`hooks.ts`) para archivos privados.
- `GuestFormDialog` (crear/editar con consentimiento Habeas Data y aviso de duplicados), `GuestAvatar`
  (iniciales en llavero, VIP y anonimizado), `CountrySelect` (ISO-3166 con nombres del navegador),
  `formatDocument`/`formatPhone` (`format.ts`).
- `commands.ts`: "Nuevo huésped" en la paleta ⌘K (abre `/app/guests?new=1`, permiso `guests.manage`).
- Consumo de `guest-tabs.tsx`: el perfil `/app/guests/:id` pinta las pestañas de otras features después de
  Resumen · Estancias · Documentos · Notas y preferencias (`GuestTab.Component` recibe `{ guestId }`).
- `features/team`: `PermissionMatrix` (matriz por módulo con "seleccionar todo", patrones `app.*`/`*` se ven
  marcados y se expanden a códigos al editar, bloquea lo que el usuario no puede otorgar) y `PermissionRack`.

Rutas: `/app/guests`, `/app/guests/:id` (guests); `/app/settings/users`, `/app/settings/roles` y la pública
`/invite/:token` (team), todas con `lazy`. Los ítems de nav de A2 no cambiaron.

## Seed

`apps/guests/seed.py` (en `SEED_ORDER` va antes de `bookings`): 180 huéspedes por organización con un RNG
local determinístico (65 % colombianos con CC y ciudades reales, 35 % extranjeros con pasaporte y residencia
en su país: US, ES, FR, DE, BR, AR, MX, CA, GB), ~5 % VIP, etiquetas "frecuente", "corporativo" y "luna de
miel", consentimientos, algunas preferencias, emails solo en dominios reservados (`example.com/.org/.net`) y
**3 duplicados intencionales** para la demo de fusión (mismo documento sin tipo, mismo teléfono + apellido
parecido, mismo email). Idempotente. Comparte `ctx.data["guests"] = {"aurora": [ids], "andino": [ids]}` para
el seed de reservas. Como `SEED_ORDER` no incluye `accounts`, al final llama a `apps/accounts/seed.py`: rol
propio "Recepción nocturna" en cada organización e invitaciones pendientes (`nocturno@casaaurora.co`, y
`reservas.bogota@grupoandino.co` restringida al hostel de Bogotá). No envía correos. Probado en tests y sobre
la BD de desarrollo (dos corridas, mismos conteos: 183 huéspedes por organización). **La BD de desarrollo ya
tiene estos datos** (corrí solo este seeder sobre el seed base); `seed_demo` los detecta y no los duplica.

## Dependencias nuevas (pip/npm) y por qué

Ninguna. La migración `guests/0003_unaccent` crea la extensión `unaccent` de PostgreSQL (contrib, incluida en
`postgres:17-alpine`, *trusted*) para buscar sin tildes.

## Cambios requeridos en archivos compartidos u otras apps (para B-INT)

1. `.gitignore`: agregar `backend/media-private/` (defensa adicional; el storage ya escribe su propio
   `.gitignore`).
2. `config/settings.py` → `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]`:
   `"GuestDocumentKindEnum": "apps.guests.models.GuestDocument.Kind"`. Hoy `spectacular --validate` avisa una
   colisión de nombres de enum en campos `kind` (la de documentos es `Kind279Enum`); hay colisiones análogas
   de otras apps (`status`, `source`, otros `kind`) que conviene resolver en la misma línea.
3. Opcional para producción: definir `PRIVATE_MEDIA_ROOT` (fuera de lo servido públicamente).
4. `frontend/src/components/DataTable.tsx` (fase A, compartido): el `<input type="search">` del buscador no
   tiene `name` ni `id`, y Chrome lo reporta como issue ("A form field element should have an id or name
   attribute") en toda página con búsqueda (huéspedes, usuarios y las de otras features). Basta con
   `name="search"`.

## Verificación B3 — lo corregido

Cada punto: test visto en rojo con el código anterior y en verde con el arreglo.

Backend:

1. **Seguridad — escalamiento con el enlace de invitación.** `GET invitations/` entregaba el `invite_url` de
   todas las invitaciones pendientes. Aceptar una invitación para un correo sin cuenta solo exige el token,
   así que un gerente podía abrir el enlace de una invitación de dueño, crear la cuenta con su contraseña y
   entrar como dueño. Ahora el enlace solo sale si quien consulta cubre el rol y los hoteles de la invitación.
2. **Seguridad — invitaciones de más alcance.** Un gerente, o un administrador restringido a un hotel, podía
   revocar o reemplazar (reinvitando el mismo correo) una invitación con más permisos u hoteles que los suyos.
   Ahora responde 403 `permission_escalation`, como ya pasaba al reenviar. Nuevo campo `editable`.
3. **Organización suspendida.** Los endpoints de equipo devolvían 402; el spec §3 exceptúa `accounts`.
4. **Habeas Data — anonimizar un registro fusionado** solo borraba esa copia y dejaba los datos en el
   principal. Ahora 409 `guest_merged` con el `guest_id` del principal.
5. **Habeas Data — `merge_guests` con anonimizados.** El contrato los aceptaba (solo la vista lo impedía) y
   la fusión rellenaba el registro borrado con datos personales. Ahora el servicio lo rechaza con 409
   `guest_anonymized`; la vista solo propaga el error.
6. **Paginación estable.** Al ordenar la lista (por ejemplo por estancias, casi todos en 0) no había
   desempate: las páginas podían repetir u omitir huéspedes. Ahora el orden siempre termina en `id`
   (`StableOrderingFilter`). En vivo: 183 de 183 huéspedes únicos recorriendo las 8 páginas.

Frontend:

1. La lista de huéspedes y la pestaña Estancias mostraban "no hay huéspedes/reservas" cuando la API fallaba.
   Ahora muestran el error con "Reintentar".
2. Los checkboxes de la matriz de permisos y el selector "todos/algunos hoteles" no tenían `name`. Radix
   agrega inputs nativos ocultos dentro de un `<form>` y Chrome los marca como issue. En vivo: 77 de 77
   controles del editor de roles con nombre.
3. Invitaciones fuera de tu alcance: sin copiar, reenviar ni revocar, con un candado que explica por qué.
4. **375 px:** el perfil del huésped y la página de usuarios desbordaban. Un `grid` sin columnas explícitas
   crecía al ancho de las pestañas o de la tabla; la página de usuarios medía 685 px. Se corrigió con
   `grid-cols-1` (`minmax(0, 1fr)`) y la ficha de registro ya no corta el número de documento.
5. La descripción del rol se veía en una sola línea recortada; ahora ocupa su propio renglón de 3 líneas.
6. Los filtros de la lista de huéspedes recortaban sus textos ("Todas las nacionalid…"): se ensancharon.
7. Nombres accesibles: la ruta de navegación del perfil ("Ruta de navegación"/"Breadcrumb") y el encabezado
   de la columna de acciones ("Acciones", antes "Acciones de").
8. Los candados de miembro e invitación tienen foco visible.
9. Textos del candado de miembros e invitaciones: mencionan permisos **u hoteles**.

Evidencia final:

- Backend: `docker compose run --rm -e TEST_DB_NAME=test_b3v backend pytest apps/guests apps/accounts -q` →
  **270 passed** (guests 161, accounts 109). `pytest apps/core -q` → 621 passed (incluye `test_contracts`,
  `test_domain_contract`, `test_migrations`, `test_admin`, `test_schema`). `pytest apps/core/tests/test_contracts.py`
  → 142 passed. `ruff check` y `ruff format --check` limpios; `manage.py check` sin problemas;
  `makemigrations guests accounts --check` sin cambios. `spectacular --validate`: 0 errores y los mismos 5
  avisos de nombres de enum entre apps (ver "Cambios requeridos").
- Frontend: `npx vitest run src/features/guests src/features/team src/app src/lib` → 23 archivos, **181 tests**
  (45 de B3) en el host, y los 45 de B3 también en el contenedor Node 24 sin stderr. `tsc -p tsconfig.app.json
  --noEmit` sin errores y `eslint` limpio en ambas features.
- Navegador (Chrome DevTools, contexto aislado, dueño de Casa Aurora): `/app/guests`, perfil (4 pestañas y
  diálogo de edición), `/app/settings/users` y `/app/settings/roles` a 1440 y 375 px, tema oscuro y claro.
  Sin desbordamiento horizontal a 375 px. El único issue de consola que queda es el del buscador del
  `DataTable` compartido (cambio 4 de B-INT).
- La BD de desarrollo quedó como estaba: 183 huéspedes por organización, 1 rol propio y 1 invitación
  pendiente por organización, 0 documentos.

## Verificación del implementador (antes de la verificación)

- Backend: `docker compose run --rm -e TEST_DB_NAME=test_b3 backend pytest apps/guests apps/accounts -q` →
  **255 passed** (guests 153, accounts 102). `pytest apps/core -q` → 621 passed (incluye `test_contracts`,
  `test_migrations`, `test_admin`, `test_schema`). `ruff check` y `ruff format --check` limpios en ambas apps;
  `manage.py check` sin problemas; `makemigrations guests accounts --check` sin cambios pendientes.
- Frontend: `npx vitest run src/features/guests src/features/team` → 7 archivos, **40 tests** verdes en el host
  y en el contenedor (Node 24), sin salida en stderr; `src/app` + `src/lib` (rutas, nav, paridad i18n ES/EN) →
  16 archivos, 136 tests. `tsc -p tsconfig.app.json --noEmit` termina sin errores y `eslint` limpio en ambas
  features.
- En vivo por el proxy de Vite (curl): búsqueda sin tildes, subida y descarga privada de documentos (ver
  Seguridad), endpoints de equipo, invitación → correo en Mailpit con el enlace → página pública → aceptar con
  CSRF → sesión iniciada → reutilizar el enlace da 409. En Chrome: `/invite/:token` en claro/oscuro, ES/EN y
  375 px; validación, aceptación y llegada a `/app` con el rol y hoteles de la invitación. Datos de prueba
  borrados después.

## Limitaciones conocidas / pendientes

- `anonymize` usa el permiso `guests.export` (el catálogo §D no tiene uno específico de Habeas Data; gerente y
  dueño lo tienen, recepción no).
- El correo de invitación es texto plano (ES + EN). C6 puede migrarlo a sus plantillas.
- No hay exportación masiva de huéspedes (CSV); `guests.export` cubre la exportación Habeas Data por huésped.
- Decisión de diseño: el historial `guests/<id>/stays/` y las `stats` cubren todos los hoteles de la
  organización (el CRM es de la cadena), también para un miembro restringido a un hotel. Ve códigos, fechas y
  totales de reservas de otros hoteles, pero no puede abrirlas: la API de reservas es por propiedad.
- Los teléfonos que no son colombianos se muestran en E.164 (`+5491139201885`): formatearlos por país
  requeriría `libphonenumber-js`, que no está instalada.
- No hay UI para los campos personalizados de huésped (`applies_to="guest"`); la API los valida y guarda.
- Caso borde no cubierto: si un principal toma el documento que conserva uno de sus registros fusionados, la
  API responde 409 `conflict` genérico (restricción única) en lugar de mover el documento.
