# C5 — Portal del huésped — integration notes

Estado: **funcional de punta a punta (modo MVP)**. Esta sesión retomó el trabajo parcial de intentos anteriores
(backend, frontend y seed ya existían sin commitear), lo evaluó contra el plan, lo completó y lo verificó contra el
stack real con los datos del seed. Por decisión del usuario **no se escribieron ni corrieron tests** en esta fase
(los tests del intento anterior siguen en `backend/apps/guestportal/tests/` y `frontend/src/features/guestportal/
__tests__/`; ver "Tests del intento anterior" abajo: algunos quedaron desactualizados a propósito).

Owner paths: `backend/apps/guestportal/**`, `frontend/src/features/guestportal/**` y esta nota. No se tocó nada
fuera de ellos. Migración única `guestportal/0001_initial` (ya aplicada; `makemigrations guestportal --check` sin
cambios).

Lectura rápida por consumidor:

| Quién | Qué usar |
|---|---|
| C1 (recepción) | `guestportal.OnlineCheckin` (`reservation` 1-1, `status` `not_started\|in_progress\|completed`, `completed_at`, `eta`). Pestañas "Check-in online" y "Solicitudes", acciones "Enviar link de check-in" y "Copiar link / QR" (renderizan **solo el cuerpo** dentro del diálogo que abre C1), widget "Check-in online de hoy" |
| C6 (mensajería) | `send_message(template_code="checkin_invitation", context={"portal_url", "checkin_url"})`. El portal **lee** (solo lectura, ORM) `messaging.Message` de la reserva y los muestra en "Mensajes" |
| C7 (legal) | Datos de viaje TRA/SIRE en `OnlineCheckin.data["travel"][<guest_id>] = {travel_reason, origin, destination}` (motivos: `leisure, business, family, education, health, religion, shopping, transit, other`). El portal consume `GET /public/compliance/portal/<token>/invoices/` y lo oculta si falla/404 |
| C9 (IA) | `PublicLayout` monta `PublicChatSlot` con `portalToken` en `/g/:token` y `/g/:token/checkin` (no hubo que hacer nada) |
| C12 (control) | Alertas `guestportal_*` (tabla abajo) con `link` a la reserva; auditoría `guestportal.*` |
| C-INT | Nada obligatorio en archivos compartidos. Ver "Cambios requeridos" (nota para C1 sobre el ancho a 375 px del detalle de reserva) |

---

## Cómo probarlo en la UI

App: http://localhost:5173 · Staff: `owner@casaaurora.co` o `recepcion@casaaurora.co` / `housetel123` · Mailpit:
http://localhost:8025. Todo en modo simulado (pagos con la pasarela simulada de B4).

### 0. Conseguir un link del portal

- **Desde la UI (staff)**: `/app` → widget **"Check-in online de hoy"** (llegadas de hoy con su estado *Sin
  empezar / En progreso / Completado*) → clic en una llegada → detalle de la reserva → **Más acciones** →
  **Copiar link / QR** (QR + link del portal + link directo al check-in, botón **Abrir portal**). También
  **Enviar link de check-in** → elige Correo y/o WhatsApp → "Link enviado por Correo." y el correo aparece en
  Mailpit con el botón "Hacer check-in en línea".
- **Desde la terminal** (lista llegadas de hoy a +N días con su estado y su link):
  `docker compose exec -T backend python manage.py portal_links --property casa-aurora --days 3 --status not_started`
  (también `andino-medellin`, `andino-hostel-bogota`; `--status completed` para ver las que ya hicieron el check-in).
- El check-in online abre **7 días antes** de la llegada (configurable) y solo para reservas **confirmadas**; usa
  una llegada de los próximos días con estado *Sin empezar*.
- Tras el seed de C-INT, ~40 % de las llegadas confirmadas de hoy y los 2 días siguientes ya traen el check-in
  online **completado** (datos, documento de muestra, firma, ETA) y cada hotel tiene 3 solicitudes pendientes
  (late check-out, early check-in, traslado). Con la BD actual (sin ese seed) todas las llegadas están *Sin empezar*
  (p. ej. Casa Aurora hoy: HT-D62XA4, HT-M2BDPV; mañana: HT-BDBZHV, HT-CXN9G4).

### 1. Portal `/g/:token` (probar a 375 px y en escritorio, claro/oscuro, ES/EN)

Esperado, de arriba abajo, con el color del hotel (terracota en Casa Aurora, pizarra en Andino MDE, salvia en el
hostel) y sin el header de Housetel:
1. Foto del hotel, nombre, selector **ES | EN**, saludo "Hola, <nombre>" y "Te esperamos mañana en Cartagena" (o
   "en N días", "Hoy…", "Estás hospedado…", "Reserva cancelada").
2. **Tarjeta de la reserva** (código, llegada/salida grandes con horas del hotel, noches, huéspedes, categoría y
   plan) con el talón: **"Haz tu check-in online" + botón Hacer check-in** (o "Tu check-in va por la mitad" /
   "Check-in listo · Llegada estimada 16:00 · Ver registro" / "El check-in online abre el 21 de septiembre").
3. **Tu cuenta**: saldo pendiente, barra pagado/total, botón **Pagar $ …** (diálogo para pagar todo o parte →
   pasarela simulada) y "N pagos realizados" (el recibo, desplegable).
4. **Agrega a tu estadía**: extras vendibles en línea (Desayuno, Parqueadero, Late check-out, Traslado) con
   precio para esta reserva (IVA o "Exento de IVA" para extranjeros no residentes) → diálogo con cantidad y total →
   "Agregar a mi cuenta" → toast "… quedó en tu cuenta" y el saldo sube (con auto-aprobación; si el hotel la apaga el
   botón dice "Pedir al hotel" y queda como solicitud).
5. **¿Necesitas algo?**: Salir más tarde / Llegar más temprano / Traslado / Otra solicitud → diálogo (hora y
   detalles; traslado y "otra" exigen detalles) → "Enviar solicitud" → toast "Solicitud enviada…" y aparece en
   "Tus solicitudes" como *Pendiente*.
6. **Mensajes**: lo que el hotel le escribió sobre la reserva (confirmación por correo y WhatsApp, invitación al
   check-in, respuestas de la bandeja…), en burbujas, con enlaces clicables; "Leer más" en los largos.
7. **Facturas** (solo si C7 tiene facturas emitidas para la reserva; si no, la sección no aparece).
8. **Cambios y cancelación**: política en palabras ("Cancelación gratuita hasta el 26 de septiembre a las 15:00",
   "Si cancelas ahora se cobra $ 416.500"…). **Cambiar fechas** (solo reservas confirmadas de una habitación dentro
   de la ventana gratuita: calendario → "Ver nuevo precio" → actual/nuevo/diferencia → "Confirmar cambio") y
   **Cancelar reserva** (si hay penalidad hay que marcar "Entiendo que se cobrarán $ …"). Para reservas de OTA dice
   que se cancela en el canal.
9. **El hotel**: dirección con "Ver en el mapa", horarios, teléfono, correo, web y reglas de la casa.
10. Burbuja del chatbot (C9) abajo a la derecha.

Link alterado (cambiar un carácter del token) → página "Este enlace no es válido" (API 404 `invalid_link`).

### 2. Check-in online `/g/:token/checkin` (el flujo E2E #7)

Barra de progreso numerada (Huéspedes → Documentos → Llegada → Firma y términos → Pago → Listo); el progreso se
guarda en el servidor (se puede cerrar y volver: reabre donde quedó; los pasos hechos se pueden reabrir).
1. **Huéspedes**: una tarjeta por huésped esperado. El titular viene prellenado (nombre, documento, nacionalidad,
   residencia, correo, celular): completar **fecha de nacimiento** y "Tu viaje" (motivo — "Vacaciones y ocio" por
   defecto —, procedencia, destino). Acompañantes: nombres, apellidos, tipo y número de documento, nacionalidad y
   residencia (prellenadas con las del titular), fecha de nacimiento. Los cupos de niños se titulan **"Niño o niña
   N"** (tarjeta de identidad por defecto si es colombiano). Campo vacío → error en el campo; **Guardar y
   continuar**.
2. **Documentos**: una tarjeta por huésped registrado; los adultos suben foto o PDF ("Tomar foto o subir archivo",
   abre la cámara en el celular); los menores dicen "Menor de edad: no necesita foto". "Continuar" sin la foto de
   algún adulto → "Falta la foto del documento de: …" y su tarjeta en rojo. Para subir desde Chrome sirve cualquier
   JPG/PNG/PDF ≤ 10 MB, p. ej. `/home/breyner/Documents/new_project/backend/media/photos/seed/casa-aurora-1.jpg`.
3. **Llegada**: hora estimada (o marcar "Aún no lo sé", más fácil de automatizar que el `input type=time`); si es
   antes del check-in avisa que depende de disponibilidad.
4. **Firma y términos**: términos del hotel (editables en configuración), recuadro blanco para **firmar con el dedo
   o el mouse**, "Acepto los términos del hotel y autorizo el tratamiento de mis datos…" (obligatorio) y el
   consentimiento de marketing (opcional) → **Firmar y terminar**. Sin firma → "Firma dentro del recuadro para continuar"; sin aceptar → aviso
   bajo la casilla.
5. **Pago** (solo si hay saldo y pagos en línea activos): "Pagar $ …" → `/sim/pay/<ref>` → Pagar (tarjeta/PSE/Nequi
   simulados) → vuelve a `/g/<token>?paid=1&payment_ref=…` con el aviso verde "Recibimos tu pago" y el saldo
   actualizado; o **Pagar en el hotel**.
6. **Listo**: sello verde, "Check-in listo", "Te esperamos el lunes 28 de septiembre", "Al llegar, di tu nombre o el
   código HT-… en recepción", ETA y "Ver mi reserva" (la tarjeta del portal queda en "Check-in listo · Ver
   registro").

Reserva tentativa, en casa, finalizada o cancelada → el stepper muestra "El check-in online no está disponible" con
el motivo (y el portal, en el talón de la tarjeta).

### 3. Lo que ve recepción

- Detalle de la reserva (`/app/reservations/:id`) → pestaña **Check-in online**: insignia *Completado* con fecha y
  hora del hotel, ETA; por huésped: documento, nacionalidad, residencia, nacimiento, contacto, viaje y **miniaturas
  privadas del documento** (se descargan con la sesión; nunca `/media`); **firma** con la evidencia (fecha, IP,
  dispositivo). Si falta algo, recuadro "Falta para completarlo". Sin empezar → "El huésped aún no hace el check-in
  online".
- Pestaña **Solicitudes**: cada pedido con estado; *Aprobar* (opcionalmente cobrando un extra del catálogo, p. ej.
  "Late check-out", con cantidad y nota), *Rechazar* (motivo), *Marcar como realizada*. El huésped ve el estado y la
  nota del hotel en su portal.
- `/app` (Hoy): widget **"Check-in online de hoy"** (N de M llegadas listas, lista con estado y ETA, aviso "N
  solicitudes por atender") y, en la lista de llegadas de C1, el chip **"Check-in online listo"**.
- `/app/alerts` (C12): "Late check-out solicitado: HT-…" (se resuelve sola al decidir), "HT-… cancelada por el
  huésped", "HT-…: el huésped cambió sus fechas", "Posible huésped duplicado en HT-…".
- `/app/settings/guest-portal` (**Portal del huésped**, permiso `guestportal.manage`): días de apertura del check-in
  (0–60), pedir foto del documento, pedir firma, auto-aprobar extras, permitir cancelar, permitir cambiar fechas y
  términos ES/EN → "Guardar cambios" (toast "Configuración guardada"). Apagar "Pedir foto del documento" quita el
  paso Documentos del stepper.

---

## API implementada

### Pública — `/api/v1/public/guestportal/<token>/…` (sin sesión; el token firmado es la llave)

Token de `core.tokens.make_reservation_token` (sin vencimiento; cada firma es distinta pero todas abren la misma
reserva). Token alterado, de otro *salt* o de una reserva inexistente → **404 `invalid_link`**. Todas responden
`Cache-Control: no-store, private`, `X-Robots-Tag: noindex, nofollow`, `Referrer-Policy: no-referrer`. Throttles
propios por IP: lectura 120/min, escritura 40/min (429 `throttled`). Sin CSRF (no hay autenticación de sesión).

| Método y path | Descripción |
|---|---|
| `GET <token>/` | Resumen del portal (abajo) |
| `GET <token>/checkin/` | Estado completo del check-in (cupos de huéspedes, datos, documentos, faltantes, términos) |
| `POST <token>/checkin/` `{step: "guests", guests: [...]}` | Datos TRA/SIRE de cada huésped → `guests.update_guest` / `upsert_guest` + `bookings.add_occupant` |
| `POST <token>/checkin/` multipart `{step: "documents", guest_id, kind: id_front\|id_back\|passport\|other, file}` | 201 `{document: {id, kind, guest_id}, checkin}` → `guests.add_document(uploaded_via="portal")` (almacenamiento privado; JPG/PNG/WebP/HEIC/PDF ≤ 10 MB por contenido) |
| `POST <token>/checkin/` `{step: "documents"}` | Confirma el paso (400 `documents_missing` + `guest_ids` si falta la foto de algún adulto y el hotel la exige) |
| `POST <token>/checkin/` `{step: "arrival", eta: "HH:MM"\|null}` | ETA en el check-in y en `Reservation.eta` (`bookings.update_reservation`, `source="guest"`) |
| `POST <token>/checkin/` `{step: "signature", signature: "data:image/png;base64,…", accept_terms: true, marketing_consent?: bool}` | PNG con trazo visible (≤ 1,5 MB, lado ≤ 4000 px) en almacenamiento privado + aceptación (hora, IP, user agent) + consentimiento Habeas Data en el titular |
| `POST <token>/checkin/complete/` | Valida todo → `completed` + `guest_checked_in_online` (una vez; idempotente). 400 `checkin_incomplete` + `missing` |
| `POST <token>/pay/` `{amount?}` | Link de pago del saldo (o parte) → 201 `{reference, checkout_url, amount, currency, status, mode, expires_at}`; vuelve a `/g/<token>?paid=1&payment_ref=<ref>`; reutiliza un link abierto del mismo monto |
| `GET <token>/extras/` | Extras vendibles en línea con precio para esta reserva |
| `POST <token>/requests/` `{kind: extra\|late_checkout\|early_checkin\|transfer\|other, extra_id?, quantity?, requested_time?: "HH:MM", notes?}` | 201 `{request, ...resumen}`. Extra + auto-aprobación → cargo en el folio (`finance.post_extra_charge`, `source="guest"`) y `approved`; lo demás → `requested` + alerta |
| `POST <token>/cancel/` `{confirm: true, reason?}` | Cancela dentro de la política (`bookings.cancel_reservation`, `source="guest"`) → resumen actualizado |
| `POST <token>/modify-preview/` `{checkin, checkout}` | Nuevo total y saldo sin guardar → `{checkin, checkout, nights, current_total, total, difference, balance, currency}` |
| `POST <token>/modify/` `{checkin, checkout}` | Cambia la estadía (`bookings.modify_stay(reprice=True)`) → `{total, balance, currency, summary}` |

`GET <token>/` (real, recortado):

```json
{"today": "2026-09-27",
 "property": {"name": "Hotel Casa Aurora", "slug": "casa-aurora", "city": "Cartagena", "address": "Calle del Cuartel #36-77…",
   "phone": "+57 605 660 1234", "email": "reservas@casaaurora.co", "website": "https://casaaurora.co",
   "check_in_time": "15:00", "check_out_time": "12:00", "timezone": "America/Bogota", "currency": "COP",
   "default_language": "es", "primary_color": "#B4583B", "logo": "", "photo": "/media/photos/seed/casa-aurora-1.jpg",
   "house_rules": {"es": "…", "en": "…"}},
 "reservation": {"code": "HT-EXFBG9", "status": "confirmed", "source": "phone", "channel_code": "",
   "checkin_date": "2026-09-28", "checkout_date": "2026-10-01", "nights": 3, "adults": 2, "children": 1,
   "currency": "COP", "total_amount": "1249500.00", "eta": null, "language": "es", "cancelled_at": null,
   "cancellation_fee": "0.00"},
 "stays": [{"id": "…", "status": "confirmed", "checkin_date": "2026-09-28", "checkout_date": "2026-10-01", "nights": 3,
   "adults": 2, "children": 1,
   "room_type": {"id": "…", "code": "DBL", "name": {"es": "Estándar", "en": "Standard"}, "kind": "private", "photo": "/media/…"},
   "rate_plan": {"id": "…", "code": "FLEX", "name": {"es": "Tarifa flexible", "en": "Flexible rate"}, "meal_plan": "room_only"},
   "room": null, "total_amount": "1249500.00"}],
 "guests": [{"id": "…", "first_name": "Mariana", "full_name": "Mariana …", "role": "booker", "stay_id": null}],
 "balance": {"total": "1249500.00", "paid": "0.00", "due": "1249500.00", "currency": "COP", "can_pay": true},
 "payments": [{"date": "2026-09-27", "method": "wompi_nequi", "amount": "50000.00"}],
 "checkin": {"status": "not_started", "current_step": "guests", "completed_at": null, "opens_on": "2026-09-21",
   "is_open": true, "reason": null},
 "extras": [{"id": "…", "code": "AIRPORT_TRANSFER", "name": {"es": "Traslado aeropuerto", "en": "Airport transfer"},
   "charge_type": "per_stay", "unit_price": "107100.00", "default_quantity": 1, "default_total": "107100.00",
   "tax_exempt": false, "currency": "COP"}],
 "requests": [{"id": "…", "kind": "late_checkout", "status": "requested", "extra": null, "quantity": 1,
   "requested_time": "14:00", "notes": "Vuelo a las 6 pm", "price": null, "decision_note": "", "created_at": "…",
   "decided_at": null}],
 "messages": [{"id": "…", "direction": "out", "channel": "email", "subject": "¡Tu reserva en Casa Aurora está confirmada! · HT-EXFBG9",
   "body": "Hola Mariana,\n\n…", "created_at": "2026-09-27T20:52:12.128593+00:00"}],
 "cancellation": {"can_cancel": true, "reason": null, "fee": "416500.00", "fee_reason": "first_night",
   "free_until": "2026-09-26T15:00:00-05:00", "non_refundable": false,
   "policy": {"name": {"es": "Flexible 48h", "en": "…"}, "description": {"es": "…", "en": "…"}}, "currency": "COP"},
 "modification": {"can_modify": false, "reason": "outside_free_window", "free_until": "2026-09-26T15:00:00-05:00",
   "max_nights": 30},
 "settings": {"auto_approve_extras": true}}
```

- `balance.due` = `finance.reservation_balance` (incluye noches aún no publicadas); `paid` = pagos aprobados −
  reembolsos aprobados; `total` = due + paid. `can_pay` = due > 0 y `IntegrationSetting(payments).enabled`.
- `checkin.reason` (cerrado): `not_open_yet | tentative | checked_in | checked_out | cancelled | no_show | past`.
- `room` solo se muestra con el huésped en casa. Nunca salen notas internas, auditoría ni documentos.
- `cancellation.reason` (no permitido): `disabled | channel | status | past`. `modification.reason`: `disabled |
  channel | status | multiple_rooms | past | non_refundable | outside_free_window`. Cambiar fechas solo mientras
  la cancelación es gratis (así el cambio nunca esquiva una penalidad), máximo 30 noches; valida restricciones de
  tarifa con `rates.quote` (400 `restriction_violation` + `violations`) y disponibilidad con
  `bookings.preview_modify_stay` (409 `no_availability`).
- `messages`: los últimos 20 de `messaging.Message` con `reservation` = esta, sin `internal_note` ni fallidos, sin el
  nombre del staff (`direction` `in` = lo escribió el huésped).

`GET <token>/checkin/` (recortado):

```json
{"status": "in_progress", "current_step": "documents", "completed_at": null,
 "window": {"opens_on": "2026-09-21", "is_open": true, "reason": null},
 "settings": {"require_document_photo": true, "require_signature": true},
 "terms": {"es": "Confirmo que los datos registrados son verdaderos…", "en": "I confirm…"},
 "travel_reasons": ["leisure", "business", "family", "education", "health", "religion", "shopping", "transit", "other"],
 "property": {"…": "igual que el resumen"}, "reservation": {"…": "…"}, "stays": ["…"],
 "guests": [
   {"slot": 0, "stay_id": "…", "role": "booker", "guest_id": "…", "complete": true, "is_adult": true, "expected": "adult",
    "data": {"first_name": "Mariana", "last_name": "…", "document_type": "CC", "document_number": "930542331",
             "nationality": "CO", "country_of_residence": "CO", "city_of_residence": "Bogotá", "birth_date": "1987-03-14",
             "email": "…", "phone": "+573004445566"},
    "travel": {"travel_reason": "leisure", "origin": "Bogotá", "destination": "Cartagena"},
    "documents": [{"id": "…", "kind": "id_front", "uploaded_via": "portal", "created_at": "…"}]},
   {"slot": 1, "stay_id": "…", "role": "companion", "guest_id": "…", "complete": true, "is_adult": true, "expected": "adult",
    "data": {"first_name": "Andrés", "last_name": "Pérez Gómez", "nationality": "CO", "document_type": "CC", "document_hint": "••••7561"},
    "travel": {"…": "…"}, "documents": []},
   {"slot": 2, "stay_id": "…", "role": "companion", "guest_id": null, "complete": false, "is_adult": false, "expected": "child",
    "data": {}, "travel": {}, "documents": []}],
 "eta": "16:00", "signature": {"signed": false, "accepted_terms_at": null},
 "missing": [{"code": "guest_data", "slot": 2, "stay_id": "…", "guest_id": null}, {"code": "document", "guest_id": "…"},
             {"code": "signature"}],
 "balance": {"…": "…"}}
```

- Cupos: uno por huésped esperado de cada estadía activa (adultos + niños, mínimo 1); el titular es el primero de la
  primera estadía; los acompañantes son `Stay.occupants`. Cupos vacíos más allá de los adultos → `expected: "child"`.
- Del titular se devuelven sus datos (los revisa él mismo); de los acompañantes solo nombre, nacionalidad, tipo de
  documento y los 4 últimos dígitos (`document_hint`).
- Entrada del paso `guests`: `{stay_id, role: booker|companion, guest_id?, keep?, first_name, last_name,
  document_type (CC|CE|TI|PA|PEP|PPT|DNI|NIT|OTHER), document_number, nationality, country_of_residence (ISO-2),
  city_of_residence?, birth_date (AAAA-MM-DD), email?, phone?, travel_reason, origin, destination}` (viaje
  obligatorio solo del titular; los acompañantes lo heredan). `keep: true` + `guest_id` conserva a un acompañante ya
  registrado sin tocarlo. Errores por campo: `fields: {"guests.1.birth_date": ["…"]}`.
- Protecciones del paso `guests`: exactamente un titular; no más acompañantes nuevos que los cupos libres de la
  habitación (400 `too_many_guests`); la misma persona dos veces → 400 `duplicate_guest`; un documento que ya es de
  otro perfil nunca se toma desde un link público → 409 `document_in_use` + alerta `guestportal_duplicate_guest`
  (si es un acompañante nuevo con el mismo nombre se vincula al perfil existente y solo se completan sus vacíos).

Errores (`{detail, code, …}`, detalle en español; el frontend traduce por `code`):
`invalid_link` 404 · `checkin_closed` 409 (+`reason`, `opens_on`) · `validation_error` 400 (+`fields`) ·
`too_many_guests` 400 · `duplicate_guest` 400 · `document_in_use` 409 · `invalid_guest` 400 · `invalid_file_type` /
`file_too_large` 400 · `documents_missing` 400 · `terms_required` · `signature_required` · `signature_empty` ·
`invalid_signature` 400 · `checkin_incomplete` 400 (+`missing`) · `nothing_to_pay` 409 · `invalid_amount` 400 (+`due`)
· `online_payments_disabled` 409 (B4) · `invalid_extra` 400 · `invalid_state` 409 · `confirmation_required` 400 ·
`cancellation_not_allowed` / `cancellation_disabled` / `managed_by_channel` 409 · `modification_not_allowed` 409
(+`reason`) · `invalid_dates` / `no_rate` / `restriction_violation` 400 · `no_availability` 409 · `throttled` 429.

### Staff — `/api/v1/guestportal/…` (sesión + `X-Property-Id`)

`guestportal.view` lee; `guestportal.manage` envía links, decide solicitudes y edita la configuración (recepción,
gerente y dueño tienen ambos; §D).

| Método y path | Permiso | Descripción |
|---|---|---|
| `GET checkins/?date=AAAA-MM-DD` | view | Llegadas del día (por defecto la fecha de negocio; tentativas, confirmadas o en casa) con su check-in: `[{reservation_id, code, status, guest_name, is_vip, adults, children, checkin_status, completed_at, eta}]` (completadas primero, luego por ETA) |
| `GET reservations/{id}/checkin/` | view | Todo lo recogido (abajo). Tras la salida o una cancelación sigue mostrando a los huéspedes |
| `GET reservations/{id}/checkin/signature/` | view | PNG de la firma (`Cache-Control: private, no-store`, `nosniff`); anónimo → 401 |
| `GET reservations/{id}/link/` | view | `{url, checkin_url, qr_png: "data:image/png;base64,…"}` |
| `POST reservations/{id}/send-link/` `{send_via?: ["email","whatsapp"]}` | manage | `send_message(template_code="checkin_invitation")` al titular → `{url, checkin_url, messages: [{channel, to, status, error}], send_error?}` (si el envío falla, el link igual se devuelve para copiarlo). Reserva cancelada o no-show → 409 `invalid_state` (el diálogo lo avisa y deshabilita el envío) |
| `GET service-requests/?status=&kind=&reservation=` | view | Paginado; cada fila = solicitud + `reservation: {id, code, guest_name, checkin_date, checkout_date, status}` |
| `POST service-requests/{id}/approve/` `{extra_id?, quantity?, note?}` | manage | Aprueba; con `extra_id` (o el extra pedido) publica el cargo en el folio (`post_extra_charge`) |
| `POST service-requests/{id}/reject/` `{reason?}` · `POST …/complete/` | manage | Rechaza / marca realizada (solo aprobadas). Decidir dos veces → 409 `invalid_state` |
| `GET/PATCH settings/` | view / manage | `{checkin_opens_days_before (0–60), require_document_photo, require_signature, auto_approve_extras, allow_guest_cancellation, allow_guest_modification, terms: {es, en}, updated_at}` (`terms` vacío → texto por defecto de Housetel) |

`GET reservations/{id}/checkin/` (recortado):

```json
{"reservation_id": "…", "code": "HT-TD79TK", "status": "completed", "current_step": "payment",
 "completed_at": "2026-09-27T20:46:11.056687+00:00", "accepted_terms_at": "2026-09-27T20:46:10.832212+00:00",
 "eta": "16:30", "ip": "181.52.10.4", "user_agent": "Mozilla/5.0 (iPhone…)",
 "signature_url": "/api/v1/guestportal/reservations/<id>/checkin/signature/",
 "window": {"opens_on": "2026-09-21", "is_open": false, "reason": "checked_in"},
 "guests": [{"slot": 0, "stay_id": "…", "role": "booker", "guest_id": "…", "complete": true, "is_adult": true,
   "data": {"first_name": "…", "last_name": "…", "full_name": "…", "document_type": "CC", "document_number": "…",
            "nationality": "CO", "country_of_residence": "CO", "city_of_residence": "Bogotá", "birth_date": "1988-04-12",
            "email": "…", "phone": "…", "is_foreign_non_resident": false},
   "travel": {"travel_reason": "leisure", "origin": "Bogotá", "destination": "Cartagena"},
   "documents": [{"id": "…", "kind": "id_front", "uploaded_via": "portal", "created_at": "…",
                  "file_url": "/api/v1/guests/documents/<id>/file/"}]}],
 "missing": [], "requests": ["…"], "portal_url": "http://localhost:5173/g/<token>", "checkin_url": "…/checkin"}
```

Los documentos se leen **solo** por el endpoint autenticado de B3 (`file_url`); la firma por el nuestro.

---

## Contratos implementados / consumidos

No hay contratos nuevos entre apps (C5 no expone servicios a otras). Consumidos (todos por sus firmas del spec §4.2 /
plan §C, sin escribir en modelos ajenos):

- `core.tokens` (`read_reservation_token`, `portal_url`), `core.audit`, `core.alerts`, `core.integrations.get_setting`,
  `core.signals.send_on_commit`.
- `guests.services`: `update_guest(source="guest")`, `upsert_guest`, `add_document(uploaded_via="portal")`,
  `document_owner`, `phone_region`; normalización de B3 (`fold`, `similar_last_names`, `is_usable_phone`,
  `normalize_document`). Almacenamiento privado `apps.guests.storage.PrivateDocumentStorage` (también para la firma).
- `bookings.services.reservations`: `add_occupant`, `update_reservation` (ETA), `cancel_reservation(source="guest")`,
  `modify_stay(reprice=True)`, `preview_modify_stay`; `bookings.services.policies.cancellation_fee`.
- `rates.services.quote.quote` (restricciones al cambiar fechas).
- `finance.services`: `reservation_balance`, `get_or_create_folio`, `create_payment_intent` (+`intent_is_stale` para
  reutilizar links), `post_extra_charge`, `extra_default_quantity`, `extra_unit_net`, `is_tax_exempt`.
- `messaging.services.send_message` (plantilla `checkin_invitation` de C6, `context={portal_url, checkin_url}`).
- Lecturas por ORM: `bookings.Reservation/Stay`, `finance.Payment/Refund` (recibo), `inventory.Photo` (fotos),
  `rates.Extra`, `guests.GuestDocument`, `messaging.Message` (import protegido con `apps.get_model`; si falla, lista
  vacía).

## Modelos (`guestportal/0001_initial`)

- `GuestPortalSettings(property 1-1, checkin_opens_days_before=7, require_document_photo=True, require_signature=True,
  auto_approve_extras=True, allow_guest_cancellation=True, allow_guest_modification=True, terms i18n)` — los dos
  `allow_*` son extra respecto al plan (el hotel decide si el huésped puede cancelar/cambiar solo).
- `OnlineCheckin(reservation 1-1 related_name="online_checkin", status[not_started|in_progress|completed],
  current_step[guests|documents|arrival|signature|payment|done], data JSON, signature FileField (privado), accepted_terms_at,
  eta, completed_at, ip, user_agent)`. `data = {"travel": {<guest_id>: {travel_reason, origin, destination}},
  "documents": [{guest_id, document_id, kind, uploaded_at}], "steps": [...]}`.
- `ServiceRequest(reservation, kind[late_checkout|early_checkin|transfer|extra|other], extra null, quantity,
  requested_time null, notes, status[requested|approved|rejected|done], price null (neto+IVA), charge null,
  decided_by, decided_at, decision_note)`.

## Señales emitidas / escuchadas

- **Emite** `core.signals.guest_checked_in_online(reservation)` al completar el check-in (tras el commit, una sola vez;
  el seed no la emite). Hoy nadie la escucha (C1 y C7 leen el modelo).
- **Escucha** (B3): `guest_anonymized` → borra sus datos de viaje y documentos listados en los check-ins; si era
  titular, también la firma (archivo al commit), IP y user agent. `guests_merged` → mueve los datos de viaje del
  duplicado al principal. Ambos con `if is_seeding(): return`.

## Automatizaciones registradas

Ninguna (el plan no pide ninguna para C5: la invitación de pre-llegada con `{{checkin_url}}` la manda la
automatización `messaging.lifecycle_dispatch` de C6).

## Proveedores de integración registrados

Ninguno (usa el de pagos de B4 y la mensajería de C6).

## Alertas y auditoría

| Alerta (`kind`) | `dedupe_key` | Cuándo |
|---|---|---|
| `guestportal_request` (info) | `guestportal:request:<id>` | Solicitud del huésped que espera al staff (late/early/traslado/otra, o extra sin auto-aprobación). Se resuelve al aprobar/rechazar |
| `guestportal_cancelled` (info; warning si queda saldo a favor) | `guestportal:cancelled:<reserva>` | El huésped canceló desde el portal (`data.credit` = saldo a reembolsar) |
| `guestportal_modified` (info; warning si queda saldo a favor) | `guestportal:modified:<reserva>` | El huésped cambió sus fechas (revisar asignación) |
| `guestportal_duplicate_guest` (warning) | `guestportal:duplicate:<reserva>:<huésped>` | Se escribió un documento que ya es de otro perfil |

Auditoría (`source="guest"` salvo decisiones del staff): `guestportal.checkin_completed`, `guestportal.request_created`,
`guestportal.request_approved`, `guestportal.request_rejected`, `guestportal.request_done`,
`guestportal.reservation_modified`, `guestportal.link_sent`, `guestportal.settings_updated`, `guestportal.demo_seeded`
(marca del seed). Además, los servicios de otras apps auditan lo suyo (`guests.guest_updated`, `bookings.occupant_added`,
`bookings.reservation_cancelled`, `finance.charge_posted`, …).

## Extensiones de frontend exportadas

- `routes.tsx`: públicas `/g/:token` (`PortalPage`) y `/g/:token/checkin` (`CheckinPage`) con `handle: {chrome:
  'none'}` (sin header de Housetel; el chat de C9 sigue montado), app `settings/guest-portal` (`SettingsPage`).
  Todas `lazy`. `nav.ts` sin cambios (ítem de configuración, `guestportal.manage`).
- `reservation-tabs.tsx`: `guestportal-checkin` ("Check-in online", order 30) y `guestportal-requests`
  ("Solicitudes", order 31), permiso `guestportal.view`.
- `reservation-actions.tsx`: `guestportal-send-link` ("Enviar link de check-in", `guestportal.manage`) y
  `guestportal-link` ("Copiar link / QR", `guestportal.view`). **Convención de C1**: el detalle abre un `Dialog` con
  el título (`labelKey`) y renderiza el `Component` como cuerpo; nuestros componentes pintan descripción, contenido y
  `DialogFooter` (cerrar llama `close()`), **no** su propio `Dialog`.
- `widgets.tsx`: `guestportal-checkins` (size `md`, `guestportal.view`) — llegadas de hoy con su check-in y aviso de
  solicitudes pendientes.
- Todos los componentes de extensión se cargan perezosos (`components/staff/lazy.tsx`).
- Piezas reutilizables: `lib/brand.ts` (`brandStyle(hex, theme)`: sobreescribe las variables `--accent*` con el color
  del hotel ajustado a contraste AA en claro/oscuro), `SignaturePad` (`components/checkin/SignaturePad.tsx`,
  `signature_pad` 5), `api.ts` (tipos y hooks del portal).
- Diseño: mobile-first, tarjeta de reserva tipo "tarjeta de registro" con talón perforado, color del hotel,
  claro/oscuro, ES/EN completos (paridad de claves verificada), sin desborde horizontal a 375 px.

## Seed (`apps/guestportal/seed.py`, corre después de `marketplace`)

- `GuestPortalSettings` por propiedad con términos que nombran al hotel (si ya existen, se respetan).
- ~40 % de las llegadas **confirmadas** de hoy y los 2 días siguientes (sin check-in previo y con el titular
  identificable) quedan con el check-in online **completado** exactamente como lo deja el flujo real: datos de todos
  los huéspedes (acompañantes creados con `upsert_guest` + `add_occupant`, niños con TI/pasaporte), un documento de
  **muestra** por adulto (imagen generada "DOCUMENTO DE MUESTRA · DEMO", privada, `uploaded_via="portal"`), ETA en la
  reserva, firma en almacenamiento privado, aceptación con IP/UA. No emite `guest_checked_in_online` (es historia).
- 3 solicitudes pendientes por hotel (late check-out, early check-in de mañana, traslado) creadas con el servicio real
  (con sus alertas).
- Idempotente con la marca de auditoría `guestportal.demo_seeded` por propiedad (check-ins que un usuario o una prueba
  hicieron por su cuenta no bloquean ni se pisan). Aleatoriedad sembrada por slug.
- **Probado dentro de una transacción revertida** sobre la BD de desarrollo (con los archivos privados borrados al
  final): 2,1 s; Aurora 5, Andino MDE 8, Hostel 8 check-ins completados (todos firmados, sin cupos vacíos), 3
  solicitudes por hotel, 38 documentos privados, 3 marcas; segunda corrida 0,0 s sin crear nada.

## Dependencias nuevas (pip/npm) y por qué

Ninguna (`signature_pad`, `qrcode`/`Pillow` y `reportlab` ya estaban instalados).

## Cambios requeridos en archivos compartidos u otras apps

- **Ninguno obligatorio.** El esquema OpenAPI no suma avisos por C5 (los enums de sus serializers quedan con nombres
  propios: `CheckinStepKindEnum`, `ServiceRequestCreateKindEnum`, `CheckinGuestEntryRoleEnum`, `TravelReasonEnum`,
  `StepEnum`, `SendViaEnum`). Los avisos de colisión que muestra hoy `spectacular --validate` vienen de otras apps.
- **C1 (sugerencia, no es de C5)**: a 375 px `/app/reservations/:id` mide ~550 px de ancho (el grid de la página crece
  con la fila de pestañas —Resumen, Huéspedes + 6 de extensiones— y con el encabezado). Poner `min-w-0` en el
  contenedor de `Tabs`/secciones o `grid-cols-1` en el grid de la página. Afecta también a los diálogos de acciones
  (se centran en el viewport ensanchado).
- **C6**: la plantilla `checkin_invitation` ya existe y funciona (correo verificado en Mailpit). El portal lee
  `messaging.Message(reservation, direction, channel, subject, body, status)`: si C6 renombra esos campos, la sección
  "Mensajes" queda vacía (no rompe; se registra en el log).

## Limitaciones conocidas / pendientes

- **Tests**: modo MVP, no se escribieron ni corrieron. Del intento anterior quedaron desactualizados a propósito:
  `__tests__/staff.test.tsx` (3 casos de `SendLinkAction`/`LinkQrAction` buscan un `role="dialog"` propio; ahora el
  diálogo lo pone C1), y posiblemente casos de backend que asumían solicitudes/extras en reservas **tentativas** (ahora
  solo confirmadas o en casa) o más acompañantes que cupos (ahora 400 `too_many_guests`). `__tests__/fixtures.ts` no
  trae `messages` (por eso es opcional en el tipo).
- "Descargar recibo": el portal muestra los pagos como recibo (fecha, medio, monto); no genera un PDF propio. La
  factura electrónica viene de C7.
- Cambiar fechas solo para reservas de **una** habitación y dentro de la ventana de cancelación gratuita; cambiar
  categoría o número de huéspedes se pide al hotel ("Otra solicitud").
- Los links del portal no vencen (el token no lleva `max_age`); quien tenga el link ve los datos del titular. Se
  envía solo al titular y el correo advierte que es personal.
- Un acompañante que el hotel ya registró se muestra enmascarado; si el huésped lo "edita" reescribe ese perfil del
  CRM con lo que escriba (pensado para completar datos del mismo acompañante).
- Los documentos de muestra del seed son imágenes generadas, no documentos reales.
- **Datos de prueba de esta verificación** en la BD de desarrollo (Casa Aurora): 5 reservas **canceladas** con saldo 0
  y huéspedes "Prueba PortalC5 A/B" y "Mariana PortalC5 Prueba" (+ acompañantes Julia Walker, Andrés Pérez Gómez,
  Sofía Pérez): HT-TD79TK, HT-3HV3TW, HT-EXFBG9, HT-A2U5D8, HT-JPKHH8 (tres con check-in online completado y
  documentos de prueba). Sus alertas quedaron resueltas. Un `seed_demo --reset` las borra.

## Verificación hecha (sin tests)

- `docker compose exec -T backend python manage.py check` → sin problemas; `makemigrations guestportal --check
  --dry-run` → "No changes detected"; `ruff check` y `ruff format --check` limpios en `apps/guestportal` (sin tests).
- `cd frontend && npx tsc -p tsconfig.app.json --noEmit | grep src/features/guestportal` → vacío;
  `npx eslint src/features/guestportal` → limpio.
- **API de punta a punta por el proxy de Vite** (cookie jar + CSRF, `owner@casaaurora.co`, datos del seed): script de
  71 comprobaciones, todas OK — token alterado 404; resumen (ventana abierta/cerrada, política, cambio permitido);
  check-in completo (validación por campo, límite de cupos, re-guardado con `keep`, documentos privados y tipo de
  archivo rechazado, confirmación sin fotos → `documents_missing`, ETA, términos obligatorios, firma en blanco
  rechazada, completar idempotente); C1 ve el check-in completado (`frontdesk/reservations/{id}/online-checkin/`);
  staff: llegadas, detalle con documentos (bytes PNG por el endpoint de B3), firma PNG (401 anónimo), link + QR, envío
  real por correo (Mailpit); pago parcial por la pasarela simulada (link reutilizado, retorno con `paid=1`, saldo −
  50.000, recibo); extra auto-aprobado con cargo; late check-out y traslado pendientes → aprobar con cargo del extra
  "Late check-out", realizar, rechazar, decidir dos veces 409; settings PATCH; cambiar fechas (preview + modify) y
  cancelar gratis desde el portal; limpieza (anulación de cargos, reembolso, cancelación sin cargo).
- **UI en un Chrome headless propio** (perfil y puerto aislados; no se usó el navegador compartido): `/g/:token` y
  `/g/:token/checkin` a 375 px en oscuro y claro y a 1280 px (sin desborde, consola sin errores propios); **stepper
  completo manejado en la UI** (llenar huéspedes con un niño, subir documentos, ETA, dibujar la firma en el canvas,
  aceptar términos → completado; luego paso Pago); staff: `/app/settings/guest-portal`, pestaña Check-in online con
  miniaturas privadas y firma, acciones "Copiar link / QR" (un solo diálogo, QR) y "Enviar link", widget en `/app`.
- Seed probado con rollback (arriba).
