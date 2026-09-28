# C6 — Mensajería — integration notes

Estado (2026-09-27, modo MVP sin tests): **funcional de punta a punta en backend (verificado con curl por el proxy de
Vite contra el seed) y frontend completo (typecheck y ESLint limpios)**. Reanudé el trabajo parcial de intentos
anteriores: el backend y la bandeja/simulador ya existían y funcionaban; completé lo que faltaba (página
`/app/settings/messaging`, pestañas "Mensajes" de reserva y huésped, botón de bandeja en la topbar, diálogo "Escribir al
huésped", comando ⌘K, endpoint `recipient/`) y corregí detalles (ver "Cambios de esta pasada"). **No se escribieron ni
corrieron tests** (decisión del usuario); los archivos de test que dejó el intento anterior siguen ahí sin verificar.
La validación visual en Chrome queda para el orquestador: pasos en **"Cómo probarlo en la UI"** (al final).

Owner paths: `backend/apps/messaging/**`, `frontend/src/features/messaging/**`, esta nota. No toqué nada fuera de ahí.

---

## API implementada

Staff: prefijo `/api/v1/messaging/`, sesión + CSRF + `X-Property-Id`. Permisos (plan §D): `messaging.view` lee;
`messaging.send` responde, notas, asigna, cierra, escribe al huésped y usa el simulador; `messaging.templates` edita
plantillas y reglas. Todo filtrado por la propiedad del header (plantillas: organización + propiedad); objetos de otro
hotel → 404. Errores `{detail, code, fields?}` en español.

| Método | Path | Permiso | Respuesta |
|---|---|---|---|
| GET | `conversations/?unread=1\|0&channel=email\|whatsapp\|web_chat\|ota&status=open\|closed&assigned=me\|none\|<user_id>&reservation=<uuid>&guest=<uuid>&q=&page=&page_size=` | view | `Page<Conversation>` (orden: última actividad) |
| GET | `conversations/{id}/` | view | `ConversationDetail` (= Conversation + `context`) |
| GET | `conversations/{id}/messages/?limit=50&before=<iso>` | view | `{results: Message[] (más antiguo primero), has_more}` |
| POST | `conversations/{id}/messages/` `{body, subject?, internal?, template_code?, ai_generated?}` | send | `Message` 201. 409 `channel_not_supported` (web_chat/ota), 409 `conversation_anonymized`, 400 `message_too_long` (WhatsApp > 4096) |
| POST | `conversations/{id}/read/` | view | `Conversation` (unread → 0) |
| POST | `conversations/{id}/assign/` `{user_id \| null}` | send | `Conversation` (400 `invalid_user` si no es del equipo del hotel) |
| POST | `conversations/{id}/close/` · `reopen/` | send | `Conversation` (un mensaje nuevo del huésped la reabre sola) |
| GET | `conversations/unread-count/` | view | `{conversations, messages}` (hilos abiertos con no leídos; badge de la topbar) |
| GET | `templates/` | view | `EffectiveTemplate[]` (sin paginar; todas las combinaciones código×canal×idioma con el texto efectivo) |
| POST | `templates/` `{code, name?, channel, language, scope: property\|organization, subject, body, is_active, wa_template_name, wa_template_params}` | templates | `TemplateRow` 201. 409 `template_exists` (+`id`), 403 `organization_scope_forbidden` (scope org sin acceso a todos los hoteles), 400 variables desconocidas |
| GET/PUT/PATCH/DELETE | `templates/{id}/` | view / templates | fila override; DELETE = "volver al texto heredado" (204) |
| POST | `templates/preview/` `{channel, language?, template_code? \| subject?+body?, reservation_id?, conversation_id?, guest_id?}` | view | `Preview` (sin reserva/huésped → datos de ejemplo `sample: true`) |
| GET | `variables/` | view | `Variable[]` (31 variables con etiqueta y ejemplo ES/EN) |
| GET | `lifecycle-rules/` | view | `LifecycleRule[]` (las 6; se crean con los defaults en la primera lectura) |
| PATCH | `lifecycle-rules/{id}/` `{enabled?, days_offset? (0–60), channels?, template_code?, send_after? "HH:MM"}` | templates | `LifecycleRule` (auditado) |
| POST | `send/` `{channel: email\|whatsapp, reservation_id?, guest_id?, to?, template_code? \| subject?+body?}` | send | `{message, conversation_id}` 201. 400 `no_address` / `not_sent` / `template_not_found` |
| GET | `recipient/?reservation=<uuid>&guest=<uuid>` | send | `Recipient` (**nuevo**: a quién va "Escribir al huésped") |
| POST | `simulator/whatsapp/inbound/` `{phone, body, name?}` | send | `{message, conversation_id}` 201. 409 `simulator_disabled` (WhatsApp en modo real), 400 `invalid_phone` |
| GET | `simulator/whatsapp/thread/?phone=` | send | `{phone, simulator_enabled, conversation_id, guest, messages}` (sin notas internas) |
| GET | `simulator/whatsapp/contacts/?q=` | send | `{simulator_enabled, results: [{guest_id, full_name, phone, reservation}]}` (primero en casa y llegadas ≤ 7 días) |

Público (sin auth):

| Método | Path | Respuesta |
|---|---|---|
| GET | `/api/v1/public/messaging/webhooks/whatsapp/?hub.mode=subscribe&hub.verify_token=…&hub.challenge=…` | 200 `text/plain` con el challenge si el token coincide con el de algún hotel en modo real; si no 403 |
| POST | `/api/v1/public/messaging/webhooks/whatsapp/` (firma `X-Hub-Signature-256`) | `{received: true, messages, statuses}`; 403 `invalid_signature`; 400 `invalid_body`. Idempotente por `wamid` |

Ejemplos reales (Casa Aurora, recortados):

```jsonc
// GET conversations/  → results[0]
{"id": "ce209c9f-…", "channel": "whatsapp", "status": "open", "contact_name": "Carlos Rojas",
 "address": "+573121783643", "display_name": "Carlos Rojas",
 "guest": {"id": "156d…", "full_name": "Carlos Rojas", "email": "otro.carlos.rojas2@example.org",
           "phone": "+573121783643", "language": "es", "is_vip": false},
 "reservation": {"id": "67f9…", "code": "HT-FXD58H", "status": "checked_in", "checkin_date": "2026-09-23",
                 "checkout_date": "2026-09-27", "room": "110"},
 "assigned_to": null, "last_message_at": "2026-09-27T10:16:19-05:00",
 "last_message_preview": "¡Hola! ¿Tienen toallas para la playa? …", "last_message_direction": "in",
 "last_inbound_at": "2026-09-27T10:16:19-05:00", "unread_count": 1, "whatsapp_window_open": true,
 "created_at": "2026-09-27T10:54:19-05:00"}

// GET conversations/{id}/  → context
{"guest": {"id": "156d…", "full_name": "Carlos Rojas", "first_name": "Carlos", "email": "…", "phone": "…",
           "language": "es", "is_vip": false, "nationality": "CO", "country_of_residence": "CO"},
 "reservation": {"id": "67f9…", "code": "HT-FXD58H", "status": "checked_in", "source": "front_desk",
                 "checkin_date": "2026-09-23", "checkout_date": "2026-09-27", "nights": 4, "adults": 2,
                 "children": 0, "currency": "COP", "total_amount": "1637440.00", "balance": "1637440.00",
                 "room_types": ["Estándar"], "rooms": ["110"]}}

// Message
{"id": "1fa4…", "direction": "out", "channel": "internal_note", "sender_label": "Andrés Gómez", "recipient": "",
 "subject": "", "body": "Pedí a housekeeping dos toallas de playa…", "status": "sent", "error": "",
 "template_code": "", "ai_generated": false,
 "sent_by": {"id": "cbe3…", "full_name": "Andrés Gómez", "email": "recepcion@casaaurora.co"},
 "created_at": "…", "status_updated_at": "…"}
// status: queued | sent | delivered | read | failed | received ; channel: email | whatsapp | web_chat | ota | internal_note

// GET templates/ → item
{"key": "payment_link:whatsapp:es", "code": "payment_link", "label": {"es": "Link de pago", "en": "Payment link"},
 "is_system_code": true, "channel": "whatsapp", "language": "es", "source": "system", "id": null,
 "subject": "", "body": "Hola {{guest.first_name}}, este es tu link para pagar **{{amount}}** …\n[Pagar en línea]({{payment_url}})…",
 "is_active": true, "wa_template_name": "", "wa_template_params": [], "updated_at": null,
 "organization_template_id": null, "property_template_id": null}
// source: system | organization | property (la fila que aplica); los *_template_id dicen qué overrides existen

// GET lifecycle-rules/ → item
{"id": "8f6b…", "event": "pre_arrival", "label": {"es": "Antes de la llegada (check-in en línea)", "en": "…"},
 "enabled": true, "days_offset": 3, "uses_offset": true, "channels": ["email", "whatsapp"],
 "template_code": "pre_arrival", "send_after": "09:00", "scheduled": true}

// POST templates/preview/ {"channel": "whatsapp", "template_code": "confirmation", "reservation_id": "67f9…"}
{"channel": "whatsapp", "language": "es", "source": "system", "sample": false, "subject": "",
 "text": "¡Hola Carlos! …\nCódigo: HT-FXD58H …\nTu portal de huésped: http://localhost:5173/g/…",
 "whatsapp": "¡Hola Carlos! …\n*Código:* HT-FXD58H …", "markup": "… **Código:** HT-FXD58H … [Tu portal de huésped](http://…)",
 "html": "<!DOCTYPE html>… (solo email)", "missing": [], "unknown": []}

// GET recipient/?reservation=67f9…
{"guest": {"id": "156d…", "full_name": "Carlos Rojas", "email": "otro.carlos.rojas2@example.org",
           "phone": "+573121783643", "language": "es"},
 "reservation": {"id": "67f9…", "code": "HT-FXD58H", "status": "checked_in", "checkin_date": "2026-09-23",
                 "checkout_date": "2026-09-27"},
 "language": "es", "addresses": {"email": "otro.carlos.rojas2@example.org", "whatsapp": "+573121783643"}}
```

Markup de plantillas y respuestas (renderer propio y seguro, `renderer.py`): `{{variable}}` (sin evaluar nada;
desconocida o vacía → vacío), `**negrita**` (→ `*negrita*` en WhatsApp, `<strong>` en email), `[texto](url)` (→
`texto: url` en texto plano/WhatsApp; enlace en email; **solo en su párrafo = botón** en el email), línea en blanco =
párrafo. El markup se interpreta sobre la plantilla antes de insertar valores: un valor nunca agrega enlaces ni HTML; en
el HTML todo valor se escapa.

## Contratos implementados / consumidos

Implementados (otras apps los usan):

- `apps.messaging.services.send_message(*, property, template_code, guest=None, reservation=None, to=None,
  channels=("email",), context=None, language=None) -> list[OutboundMessage]` (spec §4.2). Plantilla propiedad →
  organización → sistema en el idioma (explícito → huésped → reserva → hotel → es, con fallback de idioma); `guest`
  por defecto = booker; `to` str o `{canal: dirección}`; `context` agrega/reemplaza variables (datetime/date/Decimal
  se formatean en el idioma). Un `OutboundMessage` por canal: `sent`/`delivered`/`failed` (queda un `Message`, con
  `message_id`) o `skipped` (sin dirección, plantilla desactivada o integración apagada; no se registra nada). **Nunca
  lanza por problemas de entrega**; lanza `TemplateNotFound` (400) si ningún canal conoce el código.
- Códigos garantizados (ES/EN × email/WhatsApp, en `defaults.SYSTEM_TEMPLATES`, sin depender del seed): los 6 del
  ciclo + `checkin_invitation` (C5; context `portal_url`, `checkin_url`) + `payment_link` (B4; context `payment_url`,
  `amount`, `reference`, `expires_at`) + `custom_message` (texto libre del llamador: context `message`, `subject?`).
- `apps.messaging.inbox.send_to_guest(prop, *, channel, author, guest=None, reservation=None, to=None,
  template_code="", subject="", body="") -> Message` — lo usa el copiloto de C9 para texto libre. Lanza `DomainError`
  `no_address` / `not_sent` / `message_too_long`.
- `apps.messaging.services.record_inbound_message(property, *, channel, body, address="", guest=None,
  reservation=None, contact_name="", provider_message_id="", subject="") -> Message` — lo usa el chatbot de C9 al
  escalar a humano (`web_chat`); sirve también para mensajes de OTA (C3). Idempotente por `provider_message_id`.
- `receive_whatsapp(property, *, phone, body, profile_name="", provider_message_id="")`,
  `apply_status_update(...)`, `process_whatsapp_webhook(payload, properties)`, `erase_guest_conversations(guest_ids)`.

Consumidos: `core.integrations` (register/get_provider/get_setting/get_secrets), `core.audit.record/diff`,
`core.tokens.portal_url`, `core.automation` (register/RunResult), `core.signals` (`is_seeding`, reservas),
`core.tenancy`, `guests.services.upsert_guest/surviving_guest`, `guests.normalization.normalize_phone`,
`guests.api.filters.search_q`, `guests.signals.guest_anonymized`, `finance.services.reservation_balance`,
`bookings.services.queries.with_balance`; frontend de C9 `POST /api/v1/ai/draft-reply/` (404 → se oculta el botón).

## Señales emitidas / escuchadas

Escuchadas (`receivers.py`; todas con `if is_seeding(): return` salvo la de anonimización):

- `reservation_created` con `status == "confirmed"` → mensaje `confirmation`.
- `reservation_updated` con `changes["status"]` terminando en `"confirmed"` (p. ej. tentativa pagada) → `confirmation`.
- `reservation_cancelled` → `cancellation` (una retención tentativa que venció sin haberse confirmado se cancela en
  silencio).
- `guests.guest_anonymized` → borra los datos personales de los hilos del huésped (Habeas Data). Corre también en el
  seed (no es efecto secundario).

Todo idempotente por `LifecycleDispatch(reservation, event)` único. Emitidas: ninguna.

## Automatizaciones registradas

- `messaging.lifecycle_dispatch` — cada 10 min (`*/10`). Por propiedad, desde la hora local `send_after` de cada regla
  (09:00 por defecto): `pre_arrival` (confirmadas con llegada en ≤ N días, N=3), `arrival_day` (llegan hoy),
  `post_stay` (salieron hace N días, N=1, con 2 días de gracia), `payment_reminder` (confirmadas con saldo > 0 y llegada
  en ≤ N días, N=3). Reintenta los despachos cuyos canales fallaron todos (3 intentos, 2 días). Máx. 500 por evento y
  corrida. Resumen: "Mensajes: 4 antes de la llegada…" / "Sin mensajes pendientes".
  Verificado: `automation.run('messaging.lifecycle_dispatch', p)` para las 3 propiedades → `success`.

## Proveedores de integración registrados

| kind | mode | Clase | Notas |
|---|---|---|---|
| `email` | `real` (**por defecto**) | `SmtpEmailProvider` | `EmailMultiAlternatives` (texto + HTML con el layout Housetel: nombre y color del hotel, botón). Sin `smtp_host` usa el SMTP del entorno (Mailpit, http://localhost:8025). Config opcional: `from_email`, `reply_to` (por defecto el email del hotel), `smtp_host/port/username/use_tls`, secreto `smtp_password`. Remitente: "Hotel Casa Aurora <no-reply@housetel.co>". `test_connection` abre la conexión SMTP |
| `email` | `simulated` | `SimulatedEmailProvider` | solo registra (`sent`) |
| `whatsapp` | `real` | `WhatsAppCloudProvider` | Meta Cloud API `POST https://graph.facebook.com/{v26.0}/{phone_number_id}/messages`, Bearer token. Texto libre dentro de la ventana de 24 h (desde el último mensaje del huésped); fuera de ella usa la **plantilla aprobada** configurada en cada variante (`wa_template_name` + `wa_template_params` → parámetros `{{1}}…` del body); sin plantilla Meta responde 131047 y el mensaje queda `failed` con el motivo en español. Config: `phone_number_id`, `api_version`, `template_language_es/en`; secretos `access_token`, `app_secret` (firma del webhook), `verify_token`. `test_connection`: `GET /{phone_number_id}?fields=display_phone_number,verified_name` |
| `whatsapp` | `simulated` (por defecto) | `SimulatedWhatsAppProvider` | registra como `delivered`; el simulador `/app/simulators/whatsapp` hace de huésped |

Webhook real (Meta › WhatsApp › Configuración): URL `https://<host>/api/v1/public/messaging/webhooks/whatsapp/`,
token de verificación = `verify_token` del hotel, campos `messages`. Entran mensajes (texto, botones, interactivos;
media como "[image] pie de foto"), recibos `sent → delivered → read | failed` (nunca retroceden) y el nombre del perfil
(crea "Contacto WhatsApp"/nombre del perfil en el CRM si el teléfono no existe).

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

- `routes.tsx`: `/app/inbox`, `/app/simulators/whatsapp`, `/app/settings/messaging` (lazy).
- `nav.ts`: `inbox` (operations, `messaging.view`), `waSim` (tools, `messaging.send`), `settingsMessaging` (settings,
  `messaging.templates`).
- `reservation-tabs.tsx`: `{id: 'messages', labelKey: 'messaging:tab.label', order: 35, permission: 'messaging.view'}`
  → hilos del huésped ligados a la reserva (últimos 4 mensajes, "Abrir en la bandeja", "Escribir al huésped").
- `guest-tabs.tsx`: `{id: 'messages', order: 20, permission: 'messaging.view'}` → mismo panel filtrado por huésped.
- `topbar.tsx`: `messaging-inbox` (order 20, `messaging.view`): ícono de bandeja con el número de hilos sin leer
  (polling 60 s) → `/app/inbox?view=unread`.
- `commands.ts`: `messaging.unread` "Ver mensajes sin leer".
- Reutilizables: `components/SendDialog.tsx` (`<SendDialog open onOpenChange reservationId? guestId? onSent?>`, escribir
  al huésped con plantilla o texto libre y vista previa), `components/GuestMessagesPanel.tsx` (default export), hooks
  y tipos de `api.ts` (`useConversations({reservation|guest})`, `useUnreadCount`, `useRecipient`…).

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

1. **Tests del shell (A2), para C-INT**: el botón de bandeja de la topbar pide
   `GET /api/v1/messaging/conversations/unread-count/` a todo usuario con `messaging.view` (el `makeMe()` por defecto
   tiene `*`). `src/app/__tests__/shell.test.tsx` y `router.test.tsx` (MSW con `onUnhandledRequest: 'error'`) van a
   imprimir `[MSW] Error: intercepted a request without a matching request handler`. Agregar un handler por defecto,
   p. ej. en esos tests o en `src/test/server.ts`:
   `http.get('/api/v1/messaging/conversations/unread-count/', () => HttpResponse.json({ conversations: 0, messages: 0 }))`.
2. `ENUM_NAME_OVERRIDES`: nada (los campos de opciones de mensajería se documentan como string; renombré mis
   serializers `*Ref` para no chocar con los de finanzas: el esquema no tiene warnings de mensajería).
3. C9 (informativo): los hilos `web_chat` del chatbot ya no se "responden" en el hilo (el widget no lee respuestas
   del staff; antes quedaban como enviadas sin llegar a nadie). El compositor muestra "Escribir al huésped" (correo o
   WhatsApp). Si C9 quiere mostrar respuestas en el widget, que lea `Message(channel="web_chat", direction="out")` y se
   vuelve a habilitar `web_chat` en `apps.messaging.inbox.REPLY_CHANNELS`.

## Cambios de esta pasada (sobre el trabajo parcial)

- Nuevo: página de configuración (plantillas con editor, variables, vista previa real del email en iframe y burbuja de
  WhatsApp, override hotel/organización, restaurar heredado, plantillas propias; mensajes automáticos como línea de
  tiempo del viaje del huésped), pestañas de reserva y huésped, topbar, comando, `SendDialog`, endpoint `recipient/`.
- Backend: `conversations/?reservation=` ahora también encuentra hilos con mensajes de esa reserva (el hilo apunta a
  la reserva de su último mensaje; antes una reserva anterior de un huésped recurrente no mostraba sus mensajes);
  límite de 4096 caracteres en respuestas de WhatsApp; `web_chat` fuera de `REPLY_CHANNELS`; serializers renombrados
  (`MessagingUserRefSerializer`, `MessagingGuestRefSerializer`, `MessagingReservationRefSerializer`).
- Frontend: dos errores de ESLint (`react-refresh/only-export-components`) resueltos moviendo `CHANNEL_META` a
  `lib/channels.ts` y `useThreadMessages` a `lib/useThreadMessages.ts`; tipado de un test para el typecheck; las
  burbujas de WhatsApp (bandeja y teléfono del simulador) muestran `*negrita*` como WhatsApp (`WhatsAppText`).

## Limitaciones conocidas / pendientes

- **Sin tests en esta fase** (modo MVP). Los 23 archivos de test backend y 6 de frontend del intento anterior no se
  corrieron; algunos pueden fallar por los cambios de arriba (p. ej. responder un hilo `web_chat` ahora da 409).
- **BD de desarrollo**: antes de que el seed marcara el histórico, beat corrió `messaging.lifecycle_dispatch` (hoy
  15:20 UTC) y "envió" ~250 mensajes programados (recordatorios de pago, pre-llegada, post-estancia): están en la
  bandeja y en Mailpit. Un `seed_demo --reset` no lo repite (`mark_due_as_history`). También hay confirmaciones
  reales de las reservas de prueba de otros agentes (Smoke Canales, Smoke Marketplace, Mariana PortalC5…), que
  demuestran los receivers.
- Correo entrante: no hay ingestión de respuestas por email (IMAP/webhook de entrada); llegan al `reply_to` del hotel.
  El seed incluye respuestas de ejemplo por email.
- WhatsApp real: no descarga media ni marca como leído en Meta; las plantillas aprobadas se configuran por variante.
- Hilos de OTA: solo notas (se responde en la extranet del canal).
- La asignación de conversaciones a otros colegas requiere `accounts.users_manage` para listar el equipo (sin ese
  permiso solo "Asignármela").

## Seed (`apps/messaging/seed.py`)

Probado dentro de una transacción revertida, borrando antes los datos de mensajería (camino completo) y corriéndolo dos
veces: **2,3 s** la primera, 0,2 s la segunda (idempotente). Por hotel: las 6 reglas activas; personalizaciones de
plantillas (Casa Aurora: confirmación por email firmada por el hotel + "Cóctel de bienvenida" de la organización;
Andino: "Oferta de late check-out" de la organización; hostel: WhatsApp propio del día de llegada); 5 conversaciones de
ejemplo con reservas reales (WhatsApp de un huésped en casa con pregunta sin leer y nota interna; WhatsApp de una
llegada de hoy asignada a recepción; respuesta por email de un próximo huésped; un contacto de WhatsApp sin reserva que
pregunta disponibilidad; un hilo cerrado con un huésped que ya se fue) → 15 hilos, 12 sin leer; y los mensajes
programados ya vencidos marcados como histórico (196) para que la automatización no escriba a todo el demo de golpe.
Nada se envía durante el seed.

## Cómo probarlo en la UI

Todo en **http://localhost:5173**. Usuarios (clave `housetel123`): `owner@casaaurora.co` (todo),
`recepcion@casaaurora.co` (ve y responde; configuración de solo lectura), `limpieza@casaaurora.co` (sin mensajería).
Correos en **Mailpit http://localhost:8025**. WhatsApp está en modo simulado en los 3 hoteles.

1. **Bandeja** — Entrar como dueño de Casa Aurora. En la topbar aparece el ícono de bandeja con un número (hilos sin
   leer). Clic → `/app/inbox?view=unread`. Esperado: lista con los hilos sin leer en negrita y contador terracota;
   vistas Abiertas / Sin leer / Mías / Sin asignar / Cerradas; selector de canal; buscador (probar "Carlos" o 4 dígitos
   de un teléfono).
2. **Hilo** — Abrir el WhatsApp del huésped en casa que pregunta por **toallas de playa** (hoy: Carlos Rojas,
   HT-FXD58H, hab. 110). Esperado: mensajes del hotel a la derecha en verde salvia con chip "Plantilla: Confirmación de
   reserva / Antes de la llegada / Día de llegada" y ✓✓; la pregunta del huésped a la izquierda; una **nota interna**
   amarilla con borde perforado ("Solo la ve el equipo"); banner verde "Ventana de WhatsApp abierta · cierra en N
   horas". Al abrirlo se marca leído (baja el número de la topbar). Panel derecho (≥1280 px) o botón "Reserva y
   huésped": código, estadía, habitación (llave), total y saldo, enlaces a la reserva y al perfil.
3. **Responder** — Escribir `Hola {{guest.first_name}}, ya te las llevamos **en 10 minutos** 🙌` → "Enviar por
   WhatsApp" (o Ctrl+Enter). Esperado: burbuja nueva "Hola Carlos, ya te las llevamos **en 10 minutos** 🙌" (la parte
   entre asteriscos en negrita, como en WhatsApp), estado entregado ✓✓, toast "Mensaje enviado".
4. **Plantilla e IA** — "Plantilla" → "Invitación al check-in en línea": el cuadro se llena con los datos del huésped
   (editable). "Borrador IA": aparece un borrador (Gemini o simulado) con el aviso "revísalo antes de enviarlo".
5. **Nota, asignar, cerrar** — "Nota interna" → guardar (no cambia la vista previa ni los no leídos). "Asignar" →
   "Asignármela" → aparece en "Mías". "Cerrar" → banner gris; aparece en "Cerradas"; "Reabrir".
6. **Email** — Abrir el hilo de email de un próximo huésped que pregunta algo (hoy: Jessica Brown, cama extra, en
   inglés). Responder con asunto vacío → en Mailpit llega "Re: …" con el layout Housetel (franja terracota, nombre del
   hotel, dirección) y el texto; remitente "Hotel Casa Aurora".
7. **Simulador de WhatsApp** — `/app/simulators/whatsapp` (menú Herramientas). Elegir un huésped de la lista (primero
   los que están en el hotel o llegan pronto) o "Otro número": `+57 300 555 0101`, nombre `Paula Díaz` → "Usar este
   número". Escribir "Hola, ¿tienen parqueadero?" y Enter. Esperado: burbuja verde a la derecha del teléfono y aviso
   "Número nuevo: al escribir se crea como contacto". "Ver en la bandeja" → el hilo nuevo (Paula Díaz, sin reserva).
   Responder desde la bandeja → en ≤ 3 s la respuesta aparece en el teléfono (burbuja blanca a la izquierda).
8. **Configuración › Mensajería · Plantillas** — `/app/settings/messaging`. Lista: 8 plantillas del ciclo + "Cóctel de
   bienvenida" en "Personalizadas". "Confirmación de reserva" (Correo · Español) muestra el badge "De este hotel" (texto
   firmado por Valentina) y "Editada para este hotel" en la lista. Cambiar a WhatsApp / Inglés → "Texto de Housetel".
   Editar el mensaje, poner el cursor y "Insertar variable" → "Nombre del huésped": se inserta `{{guest.first_name}}`;
   la vista previa se actualiza sola (email = iframe con el correo real; WhatsApp = burbuja). Escribir
   `{{guest.nombre}}` → aviso rojo "Variables que no existen". "Guardar plantilla" → toast y badge "De este hotel".
   "Volver al texto heredado" → Confirmar → vuelve "Texto de Housetel". "Nueva plantilla" → nombre "Oferta de spa" →
   código `oferta_de_spa` automático → Crear → aparece en "Personalizadas" y se abre en el editor.
9. **Configuración › Mensajería · Mensajes automáticos** — pestaña "Mensajes automáticos" (`?tab=rules`). Esperado: una
   línea de tiempo del viaje del huésped: "Al reservar" (Confirmación) → "Desde 3 días antes" (Recordatorio de pago) →
   "3 días antes" (Antes de la llegada) → "Día de llegada" → tramo terracota grueso = la estadía → "1 día después"
   (Después de la estadía); aparte "Si la reserva se cancela" con línea punteada. Apagar un switch → el punto queda
   hueco y el marcador tachado, toast "Mensaje automático actualizado". Cambiar los días de "Después de la estadía" a 2
   y salir del campo → el marcador pasa a "2 días después". Marcar/desmarcar canales; sin canales → aviso. "Editar el
   texto" salta a la plantilla.
10. **Pestaña "Mensajes" de la reserva** — Abrir la reserva del paso 2 (`/app/reservations/<id>`, desde el enlace del
    panel de contexto) → pestaña "Mensajes": tarjeta por canal con los últimos 4 mensajes y "Abrir en la bandeja".
    "Escribir al huésped" → diálogo: canal WhatsApp/Correo, destinatario ya resuelto, "Plantilla" → "Recordatorio de
    pago" → a la derecha "Así lo recibe" con los datos reales (saldo, fechas) → Enviar → toast "Mensaje enviado por …"
    y la tarjeta se actualiza. Con "Correo" el mensaje llega a Mailpit.
11. **Pestaña "Mensajes" del huésped** — `/app/guests/<id>` del mismo huésped → pestaña "Mensajes" (mismo panel). Un
    huésped sin mensajes muestra el estado vacío con "Escribir al huésped"; sin email/teléfono el diálogo pide el
    destinatario.
12. **Confirmación automática** — Crear una reserva confirmada nueva (asistente de reserva) con un huésped con email y
    teléfono → llega a Mailpit "Reserva confirmada · HT-… · Hotel Casa Aurora" y en la bandeja aparece la confirmación
    por WhatsApp (entregada). Cancelarla → email "Reserva cancelada · HT-…".
13. **Permisos** — `recepcion@casaaurora.co`: responde y usa el simulador; "Mensajería" no aparece en su menú de
    Configuración (le falta `messaging.templates`) y, abriendo `/app/settings/messaging` a mano, ve el aviso de solo
    lectura y los controles deshabilitados. `limpieza@casaaurora.co`: sin "Bandeja" en el menú ni ícono en la
    topbar; `/app/inbox` muestra el error de permiso.
14. **Móvil (375 px)** — Bandeja: lista a pantalla completa → tocar un hilo → hilo a pantalla completa con flecha
    "Volver" y botón de contexto (hoja lateral). Configuración: la lista de plantillas es una fila de chips desplazable;
    en la línea de tiempo el marcador va dentro de cada tarjeta. Simulador: el teléfono debajo de la lista.
15. **Inglés y modo oscuro** — Todo traducido (vistas, compositor, simulador, configuración, línea de tiempo). La
    vista previa del correo se mantiene clara (como un correo real).

Chequeos por consola (opcionales): `docker compose exec -T backend python manage.py shell -c "from apps.core import
automation; from apps.core.models import Property; [print(automation.run('messaging.lifecycle_dispatch', p).summary)
for p in Property.objects.all()]"`; Mailpit API `curl -s 'http://localhost:8025/api/v1/messages?limit=3'`.

## Verificación hecha (sin tests)

- `manage.py check` sin problemas; `makemigrations messaging --check --dry-run` → "No changes detected"; `ruff check` y
  `ruff format` de la app limpios; `spectacular --validate` sin warnings de mensajería.
- curl por el proxy de Vite con cookie jar + CSRF (≈60 requests): bandeja (listado, filtros por canal/no leídos/mías/
  reserva/huésped, búsqueda, detalle, mensajes), simulador (contactos, entrante, hilo), respuesta WhatsApp (render de
  variables y negrita), nota interna (no visible en el teléfono), leído, asignar, cerrar y reapertura por mensaje nuevo,
  plantillas (listado efectivo, variables, vista previa con ejemplo/reserva/borrador con escape HTML, crear override,
  409 duplicado, 400 variable desconocida, editar, borrar → vuelve al sistema), reglas (orden, editar, 400 plantilla
  inexistente), `send/` (email a Mailpit verificado y WhatsApp), `recipient/`, borrador IA de C9, webhook público
  (403 sin token/firma), permisos (limpieza 403; recepción no crea plantillas 403) y multi-tenant (Andino → 404 en hilos
  y recipient de Casa Aurora; header de otra organización → 403).
- `automation.run('messaging.lifecycle_dispatch', …)` en las 3 propiedades → success.
- Seed en transacción revertida (arriba). Frontend: `tsc -p tsconfig.app.json` sin errores en `src/features/messaging` y
  `eslint src/features/messaging` → 0 problemas.
