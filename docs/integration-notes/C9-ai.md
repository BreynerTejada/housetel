# C9 — IA (proveedores, copiloto, chatbot, onboarding, anomalías) — integration notes

Estado: **funcional de punta a punta en modo simulado y con Gemini real** (MVP, sin tests nuevos por decisión del
usuario). Esta tarea reanudó un intento previo: el backend heredado se revisó con datos del seed, se corrigieron
defectos y se completó el frontend (las 3 páginas faltaban). Sin commits, sin dependencias nuevas, `.env` intacto.

Leer primero: "Cómo probarlo en la UI" (para la validación en Chrome) y "Cambios requeridos en archivos
compartidos" (para C-INT: **reiniciar beat y worker**).

---

## Qué se hizo en esta pasada

- Revisión completa del backend heredado contra el seed (curl por el proxy de Vite + shell). Correcciones:
  - `create_reservation` del copiloto elegía la oferta más barata (el plan **No reembolsable**); ahora usa el plan
    base del hotel (`rates.services.grid.default_plan`) salvo que se pida otro, y un plan pedido explícitamente ya
    no se pierde (antes `offer_options` solo guardaba la oferta más barata por categoría y respondía "sin
    disponibilidad").
  - La propuesta de extra mostraba el neto ($25.000) y el folio recibía $29.750: ahora muestra subtotal, IVA y total
    con las mismas reglas de `finance.post_extra_charge` (sin escribir nada al proponer). "Agrega **un**
    parqueadero" ya no fija cantidad 1: usa la regla del extra (por noche → noches de la estadía).
  - LLM: tras una respuesta real exitosa se limpia el último error y se **resuelve la alerta `llm_degraded` del
    día**; timeout interactivo 20 s → 30 s; el reintento corto solo ocurre si el fallo fue rápido (un timeout no se
    reintenta: duplicaba la espera); los chats (copiloto, chatbot, borradores) piden a Gemini `thinking_level =
    MINIMAL` (la latencia medida era casi toda razonamiento: 15,9 s para 71 tokens); onboarding y resumen diario
    usan `LOW`.
  - Chatbot simulado: una FAQ ahora gana a la línea de "Extras" que también menciona el tema (antes "¿Tienen
    parqueadero?" respondía con la lista de extras); en el portal, "¿cuándo es mi llegada?" responde con la reserva
    (estado traducido, horarios); si ya hay contacto (reserva del portal) el traspaso no vuelve a pedir datos.
  - Onboarding: las categorías heurísticas salen en el orden del texto; nuevo `POST onboarding/normalize/` (sin
    LLM) para que la pantalla de revisión obtenga números de habitación únicos en el hotel al cambiar unidades.
  - Conversaciones del chatbot: la API devuelve el contacto conocido por la reserva (portal) cuando el huésped no
    dejó datos.
  - `provider_info` expone `custom_model` y `platform_model` (el formulario distingue el modelo propio del de la
    plataforma).
- Frontend: `/app/onboarding`, `/app/settings/chatbot`, `/app/settings/ai` (antes `UnderConstruction`), IVA/total
  en la tarjeta de extra, nota "respondido por el asistente simulado" cuando el proveedor real falla, correcciones
  de lint (setState en efecto del botón, `toTurns` movido a `components/turns.ts`).

## API implementada

Staff: `/api/v1/ai/…` con sesión + `X-Property-Id` (reglas de tenancy de A1). Público: `/api/v1/public/ai/…`
sin sesión. Errores `{detail, code, fields?}`. Toda la API está en `/api/docs/`.

| Método y path | Permiso | Respuesta |
|---|---|---|
| `GET copilot/status/?language=es` | `ai.copilot` | `{enabled, effective: real\|simulated, provider_label, suggestions[4]}` (sugerencias según las herramientas que permite el rol) |
| `GET/POST copilot/sessions/` | `ai.copilot` | sesiones **del usuario** en la propiedad (página) / crea `{title?}` → 201 detalle |
| `GET/DELETE copilot/sessions/{id}/` | `ai.copilot` | `{id, title, created_at, last_message_at, messages[], actions[]}` |
| `POST copilot/sessions/{id}/messages/` | `ai.copilot` (+ throttle 30/min) | `{session, messages, proposals}` (ver abajo). 409 `feature_disabled` si el copiloto está apagado |
| `GET copilot/actions/{id}/` | `ai.copilot` | propuesta |
| `POST copilot/actions/{id}/confirm/` | `ai.copilot` + **el permiso de la acción revalidado en ese momento** | propuesta `executed` o `failed` (con `error`); 403 `permission_denied` si el rol ya no lo permite; 404 si no es del usuario; 409 `action_not_pending` si ya se decidió |
| `POST copilot/actions/{id}/reject/` | `ai.copilot` | propuesta `rejected` |
| `POST onboarding/propose/` | `ai.onboarding` (10/min) | `{proposal, warnings[], simulated, provider, website}` |
| `POST onboarding/normalize/` | `ai.onboarding` | `{proposal, warnings}` — sin LLM; filas con `room_numbers: []` reciben números nuevos únicos en el hotel |
| `POST onboarding/apply/` | `ai.onboarding` | 201 `{room_types[{id,code,name,kind,rooms[]}], rooms_created, rate_plans[], extras[], profile_updated[], links{}}`; 400 con `fields` (p. ej. `duplicate_room_numbers`); todo o nada |
| `POST draft-reply/` | `messaging.send` (30/min) | `{text, simulated, language}` — contrato §C con C6. **404** si el hotel apagó los borradores (la bandeja oculta el botón) |
| `GET/PATCH settings/` | `ai.settings` | `{copilot_enabled, chatbot_enabled, draft_replies_enabled, chatbot_greeting{es,en}, provider{…}}`; PATCH acepta además `mode: real\|simulated`, `provider: gemini\|claude`, `model` ("" = el de la plataforma). Audita `ai.settings_updated` |
| `GET usage/?days=30` | `ai.settings` | `{since, days, totals{calls, real, simulated, errors, input_tokens, output_tokens, avg_latency_ms}, by_feature[], by_provider[], by_day[], recent_errors[5]}` |
| CRUD `faqs/?language=es` | `ai.settings` | `{id, question, answer, language, sort, is_active}` (máx. 300/2000 caracteres) |
| `GET chatbot-conversations/?handoff=1&open=1` | `ai.settings` | página `{id, language, handoff_requested, handoff_reason, handoff_at, handoff_resolved_at, contact, reservation{id,code}, messages_count, last_message, last_message_at}` |
| `GET chatbot-conversations/{id}/` | `ai.settings` | + `messages[{role, content, cards[], at}]` |
| `POST chatbot-conversations/{id}/resolve/` | `ai.settings` | marca atendida y resuelve su alerta `chatbot_handoff` |
| `GET public/ai/chat/<slug>/?language=es&session_id=` | pública (120/min IP) | `{enabled, property{name,slug,city,primary_color}, greeting, suggestions[], languages, session_id, messages[], handoff}`; **404 si el chatbot del hotel está apagado** (el widget no se muestra) |
| `POST public/ai/chat/<slug>/` | pública (30/min IP; 20 mensajes/10 min por sesión → 429 `rate_limited`) | `{session_id, reply{role, content, cards[], at}, handoff{requested, contact_needed, contact_received}}` |
| `POST public/ai/chat/<slug>/contact/` | pública | `{session_id, name, email?, phone?, message?}` (email o teléfono) → `{ok, handoff}` |
| `GET/POST public/ai/portal-chat/<token>/` y `…/contact/` | pública | igual, con el token del portal (C5): el asistente conoce la reserva |

Ejemplos reales (Casa Aurora, fecha de negocio 2026-09-27):

```json
// POST copilot/sessions/{id}/messages/  {"message": "Agrega un parqueadero a HT-M2BDPV", "language": "es"}
{"session": {"id": "…", "title": "Agrega un parqueadero a HT-M2BDPV", "created_at": "…", "last_message_at": "…"},
 "messages": [
   {"id": "…", "role": "user", "content": "Agrega un parqueadero a HT-M2BDPV", "tool_calls": [], "provider": "", "simulated": false},
   {"id": "…", "role": "assistant", "content": "", "tool_calls": [{"id": "sim-1", "name": "add_extra",
     "arguments": {"reservation_code": "HT-M2BDPV", "extra": "parqueadero"}}], "provider": "simulated", "simulated": true},
   {"id": "…", "role": "tool", "name": "add_extra", "content": "{\"proposal\": {…}}"},
   {"id": "…", "role": "assistant", "content": "Preparé esta acción: Agregar 3 × Parqueadero a HT-M2BDPV · $ 89.250. Revísala y confírmala en la tarjeta para ejecutarla.", "provider": "simulated", "simulated": true}],
 "proposals": [{"id": "…", "action": "add_extra", "status": "proposed", "permission": "finance.collect",
   "summary": "Agregar 3 × Parqueadero a HT-M2BDPV · $ 89.250",
   "details": {"code": "HT-M2BDPV", "guest": "Julián Pérez Ramírez", "extra": "Parqueadero", "quantity": 3,
               "unit_price": "25000.00", "subtotal": "75000.00", "tax": "14250.00", "total": "89250.00",
               "currency": "COP", "reservation_id": "…"},
   "result": {}, "error": "", "message_id": "…"}]}

// POST copilot/actions/{id}/confirm/  (create_reservation)
{"id": "…", "action": "create_reservation", "status": "executed",
 "result": {"reservation_id": "…", "code": "HT-5UPGR6", "status": "confirmed", "total": "761600.00", "currency": "COP"}}
// check_out con saldo → {"status": "failed", "error": "La reserva tiene un saldo pendiente de 1338500.00"} (nada se escribe)

// POST public/ai/chat/casa-aurora/  {"message": "¿Tienen habitación del 12 al 14 de octubre para 2 adultos?", "language": "es"}
{"session_id": "PlVtrYlIHygW9wWvv-t79W2hMPvktx4b",
 "reply": {"role": "assistant", "content": "Para 12 de octubre → 14 de octubre (2 noches) hay disponibilidad:\n- Estándar · …",
   "cards": [{"type": "offer", "room_type": "Estándar", "rate_plan": "No reembolsable", "total": "670208.00",
     "per_night": "335104.00", "currency": "COP", "available": 5, "nights": 2, "checkin": "2026-10-12",
     "checkout": "2026-10-14", "adults": 2, "children": 0,
     "url": "/h/casa-aurora?checkin=2026-10-12&checkout=2026-10-14&adults=2&children=0"}]},
 "handoff": {"requested": false, "contact_needed": false, "contact_received": false}}

// POST onboarding/propose/  {"description": "Hotel boutique en Santa Marta con 14 habitaciones: 10 dobles a 280.000 …"}
{"proposal": {
   "property": {"name": "…", "description": {"es": "…", "en": ""}, "city": "Santa Marta", "address": "", "phone": "",
                "email": "", "star_rating": null, "check_in_time": "15:00", "check_out_time": "11:00",
                "amenities": ["wifi", "pool", "air_conditioning", "parking", "sea_view", "breakfast"]},
   "room_types": [{"code": "DBL", "name": {"es": "Doble", "en": "Double"}, "kind": "private", "units": 10,
     "room_numbers": ["101", "…"], "base_occupancy": 2, "max_adults": 2, "max_children": 1, "max_occupancy": 2,
     "beds": [{"type": "queen", "count": 1}], "beds_per_room": null, "size_m2": null, "amenities": ["wifi"],
     "base_price": "280000", "weekend_adjust_percent": 0, "extra_adult_price": "0", "extra_child_price": "0"}],
   "policies": {"non_refundable_discount_percent": 12, "breakfast_price": "30000", "pets_allowed": false,
                "smoking_allowed": false, "children_allowed": true},
   "extras": [{"code": "BRK", "name": {"es": "Desayuno", "en": "Breakfast"}, "price": "30000", "charge_type": "per_person_night"},
              {"code": "PARK", "name": {"es": "Parqueadero", "en": "Parking"}, "price": "20000", "charge_type": "per_night"}]},
 "warnings": [], "simulated": true, "provider": "simulated", "website": null}
```

`apply` crea en una transacción: perfil (`inventory.update_property_profile` con su `PropertyProfileSerializer`),
cada categoría con sus habitaciones (`inventory.provision_room_type`), tarifas (`rates.provision_rates`: plan base
FLEX + derivados NR −X % y BB +desayuno según la propuesta, con impuestos y políticas por defecto) y extras (con
el `ExtraSerializer` de rates; un código que el hotel ya vende se conserva). Audita `ai.onboarding_applied`
(`source="ai"`). Los códigos y números se hacen únicos en el hotel (DBL → DBL2, habitaciones que no chocan).

## Contratos implementados / consumidos

- **Implementa** `apps.ai.llm.get_llm(property=None) -> LLMClient` (spec §4.2; firma y `LLMResult`/`ToolCall`
  congelados por `test_contracts.py`, sin cambios). `LLMClient.generate(messages, *, system, tools,
  response_schema, temperature) -> LLMResult(text, tool_calls, data, provider, model, simulated, usage)`.
  - Selección: `IntegrationSetting(kind="llm")` de la propiedad (`get_setting` la crea en `real` si hay
    `GEMINI_API_KEY`, si no `simulated`). `real` → `config.provider` `gemini` (default) | `claude`; clave de la
    plataforma (`GEMINI_API_KEY`/`ANTHROPIC_API_KEY`) salvo un secreto propio `api_key`; modelo `config.model` o
    `GEMINI_MODEL`/`CLAUDE_MODEL`. `simulated`, integración apagada o sin clave → cliente simulado.
  - Fallas 429/5xx/timeouts/red → un reintento corto si el fallo fue rápido → respuesta del simulado + alerta
    `llm_degraded` (una por propiedad y día; se resuelve sola con la siguiente respuesta real) + pausa del proveedor
    (2 min tras cuota, 30 s tras otro error; la pausa es por clave de API: afecta a todas las propiedades que la
    comparten). Cada llamada queda en `AIUsage` (intento fallido y fallback = dos filas).
  - `apps.ai.llm.llm_for(property, feature, *, timeout)` = `get_llm` etiquetado por función (para el reporte de
    uso). **C8** puede seguir usando `get_llm(property).generate(...)` (queda como `general`) o pasar a
    `llm_for(prop, "revenue")` para que el uso aparezca como "Revenue".
  - Adaptadores: `clients/gemini.py` (google-genai 2.25, verificado con Context7 + introspección de tipos:
    `models.generate_content`, `FunctionDeclaration(parameters_json_schema=…)`, `AutomaticFunctionCallingConfig(
    disable=True)`, `Part.from_function_response` en un turno `tool`, `response_mime_type="application/json"` +
    `response_json_schema`, `thought_signature` de Gemini 3 conservada en `ToolCall.meta` entre turnos);
    `clients/claude.py` (anthropic 1.8: `messages.create` sin `temperature` —no existe en esa versión—,
    `tool_use`/`tool_result`, `output_config.format=json_schema`).
- **Implementa** el endpoint §C C9 → C6 `POST /api/v1/ai/draft-reply/`.
- **Consume**: bookings (`availability.search_offers`, `availability`, `availability_by_date`,
  `reservations.create_reservation(source_label="ai")`, `assign_room`, `check_in`, `check_out`,
  `queries.with_balance`), finance (`reservation_balance`, `get_or_create_folio`, `post_extra_charge`,
  `extra_unit_net`), inventory (`block_room`, `provision_room_type`, `update_property_profile`), rates
  (`quote.resolve_daily`, `grid.default_plan`, `provision.provision_rates`, `ExtraSerializer`), guests
  (`api.filters.search_q`), messaging (`services.send_message`, `inbox.send_to_guest`,
  `services.record_inbound_message` para el hilo `web_chat` del traspaso), core (`alerts`, `audit`,
  `integrations`, `automation`, `permissions.has_perm/codes_match`, `tokens.read_reservation_token`). Solo
  lectura: `compliance.TraRegistration/Invoice/ComplianceSettings`, `revenue.PriceBounds` (vía
  `django.apps.get_model`, las reglas se omiten si la app no existe).

### Copiloto

- Herramientas de lectura (se ofrecen solo si el rol tiene el permiso; se revalida al ejecutar):
  `get_today_summary`, `list_arrivals`, `list_departures`, `search_reservations`, `get_reservation`,
  `check_availability` (bookings.view), `find_guest` (guests.view), `get_balance` (finance.view), `list_alerts`
  (control.alerts), `get_rates` (rates.view).
- Herramientas de acción (solo **proponen** un `CopilotAction`): `create_reservation`, `move_room`
  (bookings.manage), `check_in`, `check_out` (bookings.checkin), `send_message` (messaging.send; plantilla o texto
  libre por email/WhatsApp), `block_room` (inventory.manage), `add_extra` (finance.collect).
- Bucle de agente: máximo 5 llamadas al modelo por mensaje; historial de las últimas 8 preguntas.
- Confirmar: solo el dueño de la sesión, una vez; revalida el permiso **en ese momento**; ejecuta con los
  servicios de contrato dentro de un savepoint (un error de negocio deja la propuesta `failed` con el motivo y no
  escribe nada); audita `ai.copilot_action` con `source="ai"` y el usuario que confirmó como actor.

## Señales emitidas / escuchadas

Ninguna (no hay `receivers.py`). Las acciones del copiloto y el onboarding emiten las señales de los servicios que
llaman (p. ej. `reservation_created`, `inventory_changed`, `room_assigned`).

Alertas (`core.alerts.raise_alert`, `source="ai"`):

| kind | dedupe_key | Cuándo |
|---|---|---|
| `llm_degraded` (warning) | `ai:llm_degraded:<AAAA-MM-DD>` | el proveedor real falló y respondió el simulado (1 por día; link `/app/settings/ai`) |
| `chatbot_handoff` (warning) | `ai:chatbot_handoff:<conversation_id>` | el huésped pidió una persona o el asistente no supo; link `/app/settings/chatbot?conversation=<id>`; se actualiza con el contacto; se resuelve al marcar atendida |
| `<regla>` (ver abajo) | `ai:anomaly:<regla>:<objeto>` | `ai.anomaly_scan` |
| `daily_brief` (info) | `ai:daily_brief:<fecha>` | `ai.daily_brief` (resuelve el del día anterior) |

Auditoría: `ai.copilot_action` (source ai), `ai.onboarding_applied` (source ai), `ai.settings_updated`.

## Automatizaciones registradas

| Código | Horario | Qué hace |
|---|---|---|
| `ai.anomaly_scan` | cada hora (`minute=0`) | reglas → alertas con dedupe estable; resuelve solas las que ya no aplican; una alerta resuelta a mano no vuelve (por objeto) o vuelve en un día (agregadas). Reglas (`kind`): `unguaranteed_arrival` (confirmada sin garantía ni pagos, llegada < 48 h), `duplicate_payment` (mismo folio, monto y medio en < 10 min), `rate_out_of_bounds` (fuera de `revenue.PriceBounds` o < 30 % del precio por defecto), `unposted_nights` (noches en casa sin cargo tras la auditoría), `vip_room_not_ready` (VIP que llega hoy, habitación no lista a < 2 h de su ETA/check-in; crítica), `missing_tra` (check-in sin TRA registrado a +2 h), `missing_invoice` (check-out sin factura a +1 h si `auto_issue_invoices`), `cash_difference` (turno cerrado con diferencia > 50.000), `oversold` (vendidas > unidades; crítica). `partial` si una regla falla (las demás siguen) |
| `ai.daily_brief` | diario 07:30 | resumen del día (IA; simulado si no hay proveedor) como alerta `info` |

Verificado con `automation.run` manual en las 3 propiedades: `success` en 0,2–0,3 s. **Ojo**: en la BD de
desarrollo actual (sin el seed de C7) la regla de TRA/factura marcaba todas las estadías recientes; con el seed
completo de C-INT (C7 siembra TRA y facturas históricas) solo quedan las pendientes reales. Borré esas ~115 alertas
de prueba; dejé las legítimas (llegadas sin garantía, VIP con habitación sin preparar) y el resumen del día.

## Proveedores de integración registrados

`llm` · `real` (`RealLLMProvider`: formulario `provider` gemini|claude, `model` opcional, `api_key` secreta
opcional; `test_connection` consulta los metadatos del modelo sin gastar cuota de generación) y `llm` ·
`simulated` (`SimulatedLLMProvider`). El centro de control (C12) los lista.

## Extensiones de frontend exportadas

- `topbar.tsx` → botón **Copiloto** (`ai.copilot`, atajo Ctrl/⌘+J) que abre el panel lateral (historial por
  propiedad, sugerencias según rol, respuestas Markdown, "Consultó: …", tarjetas de propuesta con
  Confirmar/Descartar y sello Ejecutada/Descartada/No se pudo ejecutar, enlace a la reserva, nota cuando la
  respuesta vino del simulado estando en modo real).
- `commands.ts` → "Preguntar al copiloto…" (grupo `ai:commands.group`): abre el panel y envía lo escrito en ⌘K.
- `public-widget.tsx` → burbuja de chat en páginas con `:slug` (hotel, booking engine) o `:token` (portal): saludo,
  sugerencias, tarjetas de oferta con "Reservar" (`/h/<slug>?checkin&checkout&adults&children`), formulario de
  traspaso, marca del hotel (`branding.primary_color`), sesión recordada en `localStorage`. Si el chatbot está
  apagado no aparece.
- Rutas (`routes.tsx`, lazy): `/app/onboarding`, `/app/settings/chatbot`, `/app/settings/ai`.
- `api.ts` exporta el cliente tipado (útil para C6/C11: `proposeOnboarding`, `applyOnboarding`, `getSettings`…).

## Dependencias nuevas (pip/npm) y por qué

Ninguna (google-genai, anthropic, httpx, react-markdown y zustand ya estaban).

## Cambios requeridos en archivos compartidos u otras apps

1. **Reiniciar `beat` y `worker`** (C-INT): arrancaron antes de que existiera `apps/ai/automations.py`, así que
   `ai.anomaly_scan` y `ai.daily_brief` no están en el horario estático de beat y el worker no tiene el código
   nuevo. `docker compose restart beat worker` (no lo hice: servicio compartido).
2. `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]`: mis serializers suman a las colisiones globales de `language`
   (es/en: FAQ, conversaciones, chat, borradores) y `mode` (real/simulated: ajustes de IA, igual que
   `IntegrationSetting.mode` y TRA). Sugerido: un `LanguageEnum` (es/en) y un `IntegrationModeEnum`
   (real/simulated) compartidos. `CopilotActionStatusEnum` y `CopilotMessageRoleEnum` ya salen con nombre propio.
3. Tests compartidos de A2 (`router.test.tsx`, `shell.test.tsx`): las páginas de IA ya no son stubs; si algún
   test las renderiza necesitará handlers MSW para `/api/v1/ai/…` (fase de tests).
4. (Opcional, B2a) un servicio `rates.services.create_extra(...)`: hoy `onboarding.apply` crea extras con el
   `ExtraSerializer` de rates (misma validación que su API) porque no hay servicio de contrato para eso.
5. C8: usar `llm_for(prop, "revenue")` para que su consumo se etiquete "Revenue" en `/app/settings/ai`.

## Limitaciones conocidas / pendientes

- **Cuota de Gemini**: el free tier de `gemini-3.5-flash` permite **20 solicitudes** (la API devuelve
  `generate_content_free_tier_requests, limit: 20`) y es compartido por todo el proyecto. Hoy se agotó durante la
  fase C: desde ahí todo responde el asistente simulado (con la nota en el panel y el estado en
  `/app/settings/ai`). Cada pregunta del copiloto cuesta 2+ llamadas (herramienta + respuesta).
- Verificación real con Gemini en esta sesión (9 llamadas en total): **function calling del copiloto OK en vivo**
  (llamada a herramienta + respuesta final con firma de pensamiento reenviada, 15,9 s + 4,7 s); después: 504
  DEADLINE_EXCEEDED por saturación del modelo y 429 por cuota → el fallback (reintento, pausa, simulado, alerta,
  `AIUsage`) funcionó en vivo cada vez. **La salida estructurada (onboarding, resumen diario, borradores) no se pudo
  probar en vivo** por la cuota; está verificada contra la documentación oficial del SDK (Context7) y sus tipos
  instalados. Claude no se probó (no hay `ANTHROPIC_API_KEY`).
- El modo simulado entiende pedidos concretos (llegadas, salidas, ocupación, disponibilidad con fechas, saldo de
  un código, mover/bloquear/check-in/out/extras/mensajes con código de reserva); no conversa libremente.
- Onboarding sobre un hotel existente agrega categorías (códigos y números únicos) — pensado para hoteles nuevos
  (signup de C11).
- El traspaso del chatbot abre un hilo `web_chat` en la bandeja de C6; responder desde la bandeja por ese canal
  depende de C6.
- `ai.anomaly_scan` en real necesita los datos de C7 (TRA/facturas) sembrados para no sobre-alertar.
- Sin tests nuevos (decisión del usuario para esta fase). Existen tests del intento previo en
  `backend/apps/ai/tests/` y `frontend/src/features/ai/__tests__/` que no se corrieron ni actualizaron.

## Cambios que dejé en la BD de desarrollo (verificación)

- Casa Aurora: reserva **HT-5UPGR6** (Ana Torres, 12–14 oct) creada y movida a la 105 por el copiloto y luego
  **cancelada** (motivo "Prueba del copiloto (C9)", sin penalidad); un WhatsApp simulado a HT-D62XA4 ("tu
  habitación está lista") enviado por el copiloto vía C6; un hilo "Chat web" de "Prueba C9" en la bandeja de C6 (no
  lo borré: es de otra app).
- Borré mis FAQ, conversaciones de chatbot, sesiones del copiloto de prueba y el hotel temporal "C9 Prueba
  Onboarding" (org + usuario). El modo LLM de las 3 propiedades quedó en `real` (el valor por defecto).
- Quedaron `AIUsage` (historial real de consumo) y `AutomationRun` de `ai.*`.
- **El seed de IA no está aplicado en esta BD** (se probó con rollback, como pide la tarea): no hay FAQ ni la
  conversación demo hasta que C-INT corra `seed_demo`. Para sembrar solo lo de IA (idempotente, < 1 s) ver abajo.

## Verificación mínima (sin tests)

- `docker compose exec -T backend python manage.py check` → sin problemas. `makemigrations ai --check --dry-run`
  → "No changes detected" (migración `ai/0001_initial` aplicada). `ruff check apps/ai` y `ruff format` limpios.
- Seed (`apps/ai/seed.py`) dos veces dentro de una transacción revertida: 0,10 s; 30 FAQ (5 ES + 5 EN × 3
  hoteles), 2 conversaciones (una con traspaso y su alerta) y ajustes; idempotente; nada quedó escrito.
- curl por el proxy de Vite (cookie jar + CSRF): ajustes GET/PATCH, estado del copiloto, 7 preguntas de lectura y
  las 7 acciones propuestas; confirmar `create_reservation`, `move_room`, `send_message` (reales),
  `check_in/check_out/add_extra/block_room` ejecutados dentro de transacciones revertidas; `check_out` con saldo →
  `failed` sin efectos; doble confirmación → 409; propuesta ajena → 404; recepción sin `inventory.manage` → el
  copiloto no ofrece bloquear; housekeeping → 403; revalidación de permiso al confirmar → 403 (rol cambiado en
  transacción revertida). FAQ CRUD + validación; chatbot público (FAQ, horarios, disponibilidad con tarjetas,
  traspaso, contacto → alerta + hilo `web_chat` en C6, reanudar sesión, 404 hotel inexistente, inglés); chat del
  portal con token; borradores (ES/EN, 400, 403); onboarding propose (simulado, sitio no público rechazado),
  normalize, apply sobre un hotel temporal (2 categorías, 12 habitaciones, FLEX/NR/BB, extras, perfil) y 400 al
  repetir números; `ai.anomaly_scan` y `ai.daily_brief` con `automation.run`.
- Frontend: `npx tsc -p tsconfig.app.json --noEmit | grep src/features/ai` → sin errores; `npx eslint
  src/features/ai` → limpio; paridad ES/EN (359 claves). Chrome headless **propio** (perfil temporal, no el
  navegador compartido): las 3 páginas, el panel del copiloto con propuesta y el widget en `/h/casa-aurora`, a 1280
  y 375 px, sin errores de consola ni desbordamiento horizontal.

---

## Cómo probarlo en la UI

Usuario demo: **owner@casaaurora.co / housetel123** en http://localhost:5173/login (Hotel Casa Aurora). Para
roles: `recepcion@casaaurora.co`, `limpieza@casaaurora.co` (misma clave).

**0. Preparación (una vez).**
- Si beat/worker no se reiniciaron tras la fase C, las automatizaciones de IA solo corren a mano (paso 8).
- Si la BD no tiene el seed de IA (sin FAQ en `/app/settings/chatbot`), sembrarlo (idempotente, < 1 s):
  ```bash
  docker compose exec -T backend python manage.py shell -c "import random; from django.utils import timezone; from apps.core.seed import SeedContext; from apps.core.models import Property; from apps.ai.seed import seed; ctx = SeedContext(today=timezone.localdate(), rng=random.Random(1)); ctx.properties = {k: Property.objects.get(slug=v) for k, v in {'aurora': 'casa-aurora', 'andino_mde': 'andino-medellin', 'andino_bog': 'andino-hostel-bogota'}.items()}; seed(ctx)"
  ```
- Real vs simulado: `/app/settings/ai` dice qué responde. Con la cuota de Gemini agotada todo funciona igual con
  el asistente simulado (las preguntas deben ser concretas, como las de abajo).

**1. Copiloto — lectura.** En cualquier página de `/app`: botón **Copiloto** (arriba a la derecha) o Ctrl+J.
- Clic en la sugerencia "¿Cuántas llegadas hay hoy?" → aparece "Consultó: llegadas" y la lista de llegadas del día
  con código, huésped, habitación (estado de limpieza) y saldo. Insignia "Modo simulado" o "Con Google Gemini".
- Probar también: "¿Quién sale hoy?", "Dame el resumen del día", "¿Cómo va la ocupación esta semana?", "¿Hay
  disponibilidad este fin de semana para 2 adultos?", "tarifas de la próxima semana", "¿Qué alertas hay
  abiertas?", "saldo de HT-XXXXXX" (un código de la lista).
- ⌘K / Ctrl+K → escribir "cuántas salidas hay hoy" → elegir **Preguntar al copiloto…** → el panel se abre y
  envía la pregunta.

**2. Copiloto — acción con confirmación.**
- Escribir: "Crea una reserva para Ana Torres del 12 al 14 de octubre para 2 adultos" → tarjeta **Acción
  propuesta · Crear reserva** (huésped, categoría Estándar, plan Tarifa flexible, fechas, noches, total) con
  **Confirmar / Descartar**. Nada se crea todavía.
- **Confirmar** → sello "Ejecutada" y enlace **Abrir la reserva** → la reserva existe (confirmada); en la
  auditoría figura `ai.copilot_action` con fuente IA.
- Otras: "mueve HT-XXXXXX a la 105" (misma categoría), "Agrega un parqueadero a HT-XXXXXX" (tarjeta con subtotal,
  IVA y total), "Envía un WhatsApp a HT-XXXXXX: tu habitación está lista", "check-in de HT-XXXXXX" (una llegada de
  hoy con habitación limpia), "Bloquea la 110 del 3 al 4 de noviembre por mantenimiento". **Descartar** → sello
  "Descartada". Un check-out con saldo → sello "No se pudo ejecutar" con el motivo.
- Permisos: con `recepcion@casaaurora.co`, "Bloquea la 110 mañana por mantenimiento" → "No puedo bloquear
  habitaciones con tu usuario…". Con `limpieza@casaaurora.co` no aparece el botón Copiloto.

**3. Chatbot público (motor de reservas).** Abrir http://localhost:5173/h/casa-aurora (sin sesión):
- Burbuja abajo a la derecha → saludo y sugerencias.
- "¿Tienen habitación del 12 al 14 de octubre para 2 adultos?" → respuesta + tarjetas por categoría (precio por
  noche, total, "Quedan N") con **Reservar** → lleva a `/h/casa-aurora?checkin=2026-10-12&checkout=2026-10-14…`.
- "¿Tienen parqueadero?" → responde con la FAQ (tras el seed). "Do you have parking?" → en inglés.
- "Quiero hablar con una persona" → formulario **Déjanos tus datos** → nombre + correo → **Enviar mis datos** →
  "Listo: recibimos tus datos…".
- Staff: aparece la alerta "Un huésped pide hablar con el equipo" (centro de alertas / campana) → su enlace abre
  `/app/settings/chatbot?conversation=<id>` con la conversación y el contacto → **Marcar como atendida** (la
  alerta se resuelve). En la bandeja (`/app/inbox`, C6) hay un hilo "Chat web".
- Portal del huésped (`/g/<token>`, C5): la burbuja también aparece; "¿Cuándo es mi llegada?" responde con la
  reserva y pedir una persona no vuelve a pedir datos (usa los de la reserva).

**4. `/app/settings/chatbot`** (Configuración › Chatbot):
- Pestaña **Preguntas frecuentes**: selector Español/Inglés; 5 FAQ por idioma tras el seed. **Agregar pregunta**
  → diálogo (pregunta, respuesta, idioma, activa) → aparece en la lista; el interruptor la desactiva (texto "El
  chatbot no usa esta respuesta…"); lápiz para editar; papelera → confirmación → eliminada.
- Pestaña **Conversaciones** (con número de pendientes): filtros Todas / Pidieron una persona / Sin atender; lista
  (contacto o "Visitante", último mensaje, insignias) y detalle con la transcripción. A 375 px el detalle se abre
  en un panel lateral.

**5. `/app/settings/ai`** (Configuración › Inteligencia artificial):
- Tarjeta **Estado**: "Respondiendo con Google Gemini" (verde) o "Respondiendo en modo simulado" (arena) y el
  último problema del proveedor (p. ej. 429 de cuota).
- **Proveedor**: Real/Simulado, proveedor, modelo (vacío = el de la plataforma) → **Guardar cambios** → toast
  "Ajustes de IA guardados"; al pasar a Simulado el estado cambia y el copiloto muestra "Modo simulado".
- **Funciones**: apagar **Chatbot de la página** → la burbuja desaparece de `/h/casa-aurora`; apagar
  **Copiloto** → el panel dice que está desactivado. (Volver a encenderlas.)
- **Saludo del chatbot** ES/EN → guardar → el widget lo muestra al abrirse.
- **Consumo de los últimos 30 días**: consultas (con tendencia), respondidas por el proveedor, en simulado, tiempo
  medio; tabla por función y últimos errores.

**6. `/app/onboarding`** (Herramientas › Configuración asistida). Crea categorías reales: mejor en un hotel nuevo
(signup de C11); en Casa Aurora agrega categorías con códigos y números que no chocan (DBL2, 111…).
- **Usar un ejemplo** → **Proponer configuración** → paso **Revisa**: tarjeta del hotel (nombre, ciudad,
  horarios, estrellas, descripción, amenidades), una ficha por categoría con sus campos y su fila de **llaves**
  (números de habitación), políticas y planes, extras y el **Resumen** con **Crear todo**.
- Subir "Habitaciones" con **+** → tras un instante la fila de llaves agrega números que no existen en el hotel.
- Dejar un nombre vacío → el resumen avisa "Ponle nombre a cada categoría" y **Crear todo** se desactiva.
- **Crear todo** → paso **Listo**: sello "Creado", las llaves "colgadas" en verde, planes (Tarifa flexible, No
  reembolsable, Con desayuno) y enlaces **Ver la grilla de tarifas / categorías / habitaciones / Completar el
  perfil**; la grilla ya tiene precios para las nuevas categorías.

**7. Borradores (con C6).** En la bandeja, el botón de borrador IA llama a `POST /api/v1/ai/draft-reply/`; si se
apaga "Borradores de respuesta" en `/app/settings/ai`, el endpoint responde 404 y la bandeja lo oculta.

**8. Anomalías y resumen del día** (manual mientras beat no se reinicie):
```bash
docker compose exec -T backend python manage.py shell -c "from apps.core import automation; from apps.core.models import Property; p = Property.objects.get(slug='casa-aurora'); print(automation.run('ai.anomaly_scan', p).summary); print(automation.run('ai.daily_brief', p).summary)"
```
→ alertas "Llegada sin garantía: HT-…", "VIP llega pronto y la … no está lista", etc., y "Resumen del día · …"
(info) en el centro de alertas. En `/app/settings/automations` (C12) aparecen con su última corrida.

**Modo oscuro / inglés / móvil:** las 3 páginas, el panel y el widget están traducidos (selector de idioma) y
probados a 375 px.
