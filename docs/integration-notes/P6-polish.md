# P6 — Pulido de UX, i18n, accesibilidad, legal, Habeas Data e integraciones guiadas — integration notes

Estado (2026-09-28, modo MVP): **los 9 requisitos de P6 están implementados y verificados** (sin tests, por decisión
del usuario). La tarea retomó un intento anterior interrumpido que había dejado hechos los puntos 1–8 casi completos y
el texto de las guías (`control/lib/guides.ts`). En esta pasada se revisó todo contra el plan, se terminó lo que
faltaba, se corrigieron defectos y se verificó con los datos del demo. Lo hecho en esta pasada:

- las guías de integración conectadas a la UI;
- el banner "Activa los modos reales";
- las alertas traducidas: textos ES/EN, `data` enriquecida y uso en la campana, el widget y la lista;
- la regla de pago del portal en producción;
- el modo permitido en el asistente de Canales;
- el enlace legal en los pies del motor de reservas y del portal;
- la barra de total del checkout, que ahora sí se queda fija;
- la burbuja del chat, que flota sobre la barra "Tu selección";
- el token `text-subtle`, un paso más oscuro;
- las etiquetas de auditoría de la retención.

Sin commits, sin dependencias nuevas, `.env` intacto y sin migraciones (ninguna app de P6 cambió modelos).

Owner paths respetados:
- `frontend/src/design/**`;
- `frontend/src/features/{ai,marketplace,calendar,control,saas,channels,messaging,guestportal,revenue}/**`;
- `backend/apps/{marketplace,revenue,ai,distribution,messaging,guests,guestportal}/**`;
- `backend/apps/compliance/services/sire.py` (solo textos).

Contratos de P1 consumidos: `core.runtime` e `integrations.is_live` / `available_modes`.

**Para P-INT:** lee "Cambios requeridos en archivos compartidos u otras apps". **Para la validación en Chrome:** lee
"Cómo probarlo en la UI", al final.

---

## Requisitos → qué se hizo

| # | Requisito del plan | Implementación | Archivos |
|---|---|---|---|
| 1a | La burbuja del chatbot no tapa botones a 375 px | En `/g/*`, `/book/*` y `/h/<slug>/book`, en teléfonos, la burbuja se compacta (44 px) y se aparta hacia el borde mientras se baja; vuelve al subir, al final de la página o con foco. Respeta `safe-area-inset-bottom`. Flota **encima** de las barras fijas: la del total del checkout y la de "Tu selección" en `/hotel/:slug` y `/h/:slug`. Esas barras publican su alto en `--public-chat-offset`. El portal reserva su espacio al final (`--public-chat-inset`) | `ai/public-widget.tsx`, `ai/lib/chat-offset.ts`, `marketplace/components/SelectionSummary.tsx`, `guestportal/components/portal/PortalFrame.tsx` |
| 1b | Checkout móvil: total visible arriba o fijo antes de "Confirmar" | Las dos cosas. Arriba, un resumen plegable con el hotel, las fechas y el **total**, que se despliega en el detalle completo. Abajo, una barra fija (hija directa del formulario, así se queda fija desde el primer campo hasta el último) con el total, "pagas ahora X" y el botón | `marketplace/components/CheckoutView.tsx` |
| 2a | Plurales en `sire.py` | Helper `_count`: «1 movimiento de extranjero», «1 archivo SIRE», «Descarga el archivo… márcalo» o «los archivos… márcalos» | `compliance/services/sire.py` |
| 2b | Alertas traducidas en el frontend | `control/lib/alert-text.ts` (`alertText`, `useAlertText`) arma el título y el mensaje desde `control:alertText.<kind>.title / .message` con la `data` de la alerta. Tiene plurales, dinero en la moneda del hotel, fechas en el idioma de la UI y etiquetas de otros namespaces (medios de pago, estados de habitación, integraciones). Si el kind no tiene texto, o a su `data` le falta un valor que el texto usa, muestra el texto guardado. 36 kinds con texto; datos agregados a las alertas de `ai`, `distribution` y `guestportal` (tabla abajo). La campana, el widget de Hoy y `/app/alerts` lo usan | `control/lib/alert-text.ts`, `control/components/{AlertBell,AlertCard,AlertsWidget}.tsx`, `control/locales/*`, `ai/{anomalies,llm,chatbot}.py`, `distribution/services/{ical,importer,pull,queue}.py`, `guestportal/services/{checkin,manage,requests}.py` |
| 2c | Título de `/search` con mayúsculas | `cityTitle()`: el nombre canónico («cartagena» → «Cartagena», «bogota» → «Bogotá»), el de la lista de destinos o, si no, las palabras capitalizadas («villa de leyva» → «Villa de Leyva») | `marketplace/lib/places.ts`, `pages/SearchPage.tsx` |
| 3 | Contraste AA de `text-subtle` | Claro: `#6c655c`, con 5,18 sobre bg, 5,75 sobre surface, 5,06 sobre surface-2, 4,63 sobre surface-3 y ≥4,76 sobre los fondos suaves. Oscuro: `#9a938a`, con 6,11 / 5,71 / 5,21 / 4,68 y ≥4,56 sobre los suaves. Antes eran 3,1:1 y 3,6:1. `text-muted` bajó un paso para conservar la jerarquía | `design/tokens.css` (+ la pista del recuadro de firma) |
| 4a | Mes del calendario sin solaparse | El mes tiene su propia línea sobre el día de la semana y la cabecera pasó de 56 a 60 px | `calendar/components/CalendarGrid.tsx` |
| 4b | Revenue: precio final redondeado y explicado | El tope diario y los límites nombran el precio **final** (`rounded: true`). Una razón nueva `{"type": "limit", "kind": "rounding", "step", "from", "price"}` dice a qué múltiplo se redondeó y desde qué precio. La explicación termina en «redondeado a múltiplos de $ 1.000». El prompt de la IA lo sabe | `revenue/services/{engine,explain,summary}.py`, `revenue/{api.ts,lib/labels.ts,locales}` |
| 4c | Onboarding IA: sin extras repetidos | Cada extra se clasifica por concepto (desayuno, parqueadero, traslado…, según su nombre y código sin tildes). Los equivalentes se unen en el primero y los que el hotel ya vende se omiten, con avisos («Uní extras que eran el mismo servicio…», «No repetí extras que tu hotel ya vende…»). El desayuno de las políticas solo se agrega si no hay uno | `ai/onboarding.py` |
| 4d | "Ejecutar ahora" visible aunque sea instantáneo | "Ejecutando…" dura al menos 700 ms, el resultado queda en la fila (estado, hace cuánto, resumen, ×) y el toast dura 8 s | `control/pages/AutomationsPage.tsx` |
| 5a | `devOnly` en los simuladores | `otaSim` y `waSim` (el filtrado es de P1 en `extensions.ts`) | `channels/nav.ts`, `messaging/nav.ts` |
| 5b | `require_simulations` en los simuladores | Distribution: `SimulatorView` y sus subclases (inventario, reservas, modificar, cancelar, reentregar). Messaging: entrante, hilo y contactos del simulador de WhatsApp → **404** con las simulaciones apagadas. Además, las páginas del simulador muestran "no existe en este entorno" | `distribution/api/views.py`, `messaging/api/views.py`, `channels/pages/OtaSimulatorPage.tsx`, `messaging/pages/WhatsAppSimulatorPage.tsx` |
| 5c | BookSim/AirSim ocultos sin simulaciones | `options/` no los ofrece, salvo que ya estén conectados, y los modos salen de `available_modes`. `options/catalog/?channel=booksim` → 400 `not_supported`. Crearlos → 400 `not_supported`. El asistente de Canales no los muestra, y un modo guardado que ya no se permite pasa al primero permitido. Los botones "Simulador" de Canales y Bandeja se ocultan | `distribution/api/views.py`, `distribution/services/connections.py`, `channels/components/{ConnectionWizard,ConnectionCard}.tsx`, `channels/pages/ChannelsPage.tsx`, `messaging/pages/InboxPage.tsx` |
| 5d | Checkout: solo "Pagar en el hotel" si los pagos no están en vivo en producción | `online_payments_enabled(prop)`: con las simulaciones apagadas es `integrations.is_live(prop, "payments")`. El checkout ofrece solo "Pagar en el hotel", la marca y envía `pay_at_hotel`; los planes con depósito no se venden en línea. **Además**, el botón "Pagar" del portal usa la misma regla | `marketplace/services/engine.py`, `marketplace/components/CheckoutView.tsx`, `guestportal/services/summary.py` |
| 6 | SSRF de iCal con DNS y redirecciones | `check_public_url` resuelve el DNS y exige que **todas** las IP sean globales: bloquea privadas, loopback, link-local, CGNAT, reservadas, multicast y `::ffff:127.0.0.1`. La descarga usa un transporte propio que resuelve y **conecta a la IP que comprobó** en cada salto de redirección (sin DNS rebinding) e ignora los proxies del entorno. Al guardar, un dominio que no resuelve se acepta (se revisa al descargar); uno interno nunca | `distribution/providers.py`, `distribution/api/serializers.py` |
| 7a | Páginas legales ES/EN | `/legal/terminos`, `/legal/privacidad` (Ley 1581, Decreto 1377) y `/legal/encargo-datos` (DPA hotel ↔ Housetel), más `/legal` → términos y alias `/legal/terms\|privacy\|dpa`. Cada página trae resumen "En pocas palabras", índice, anclas por cláusula, contacto de soporte (`support_contact`), imprimir y versión/vigencia. Los textos van en `saas/legal/{es,en}.ts` (se cargan solo con la página) | `saas/pages/LegalPage.tsx`, `saas/legal/*`, `saas/routes.tsx` |
| 7b | Los consentimientos enlazan a esos documentos | Checkout (marketplace y motor): Habeas Data → política y «Al reservar aceptas los términos de Housetel…». Check-in online: firma y términos → política. Signup: términos, política y encargo. Formulario de traspaso del chatbot: política. Todos abren en otra pestaña, con `LegalLink`. Pies del motor de reservas y del portal: `LegalFooterLinks` | `marketplace/components/{CheckoutView,EngineShell}.tsx`, `guestportal/components/checkin/FinalSteps.tsx`, `guestportal/pages/PortalPage.tsx`, `saas/pages/SignupPage.tsx`, `ai/public-widget.tsx`, `saas/components/{LegalLink,LegalFooterLinks}.tsx` |
| 8 | Retención Habeas Data | Automatización `guests.purge_identity_documents` (detalle abajo). La pestaña "Check-in online" de la reserva dice cuándo se borraron | `guests/{retention,automations}.py`, `guestportal/services/staff.py`, `guestportal/components/staff/ReservationTabs.tsx` |
| 9 | Integraciones guiadas | Cada tarjeta tiene el botón **Guía**, que abre la hoja en modo real con la guía abierta y a la vista. La guía muestra la cuenta que hay que crear (enlace oficial), sandbox frente a producción (con el ambiente elegido marcado), los pasos numerados, **la URL del webhook** con `public_base_url` para copiar dentro del paso en que se usa, un aviso si es local (con el comando del túnel para copiar y qué hacer después), "Dónde está cada dato", la sección exacta de `docs/integraciones-reales.md` (o el `docs_url` de soporte si existe) y la ayuda por WhatsApp o correo. Cada campo del formulario dice **dónde está** en el panel del proveedor. El banner pasó de "7 de 9 en modo simulado" a la llamada **"Activa los modos reales"** con "Empezar por Pagos en línea". En producción el banner cambia a "Termina de configurar tus integraciones" cuando falten llaves. Las placas del tablero abren la guía de cada integración. "Simulado" queda deshabilitado donde las simulaciones están apagadas (salvo email e IA) | `control/components/{IntegrationGuide,IntegrationSheet,IntegrationCard,ConfigFieldInput}.tsx`, `control/pages/IntegrationsPage.tsx`, `control/lib/{guides,integrations}.ts`, `control/locales/*` |

---

## API implementada (cambios de comportamiento; no hay endpoints nuevos)

### Simuladores (distribution, messaging)

| Llamada | Simulaciones activas (desarrollo) | Simulaciones apagadas (producción, o `HOUSETEL_ALLOW_SIMULATIONS=0`) |
|---|---|---|
| `GET/POST /api/v1/distribution/simulator/{id}/…`, las 5 rutas | Igual que antes | **404** `{"detail": "No encontrado.", "code": "not_found"}` |
| `GET/POST /api/v1/messaging/simulator/whatsapp/{inbound,thread,contacts}/` | Igual que antes | **404** |
| `GET /api/v1/distribution/options/` | `channels` con `booksim`, `airsim`, `ical` y `channex`; cada uno trae `simulator: bool`, y `modes` sale de `integrations.available_modes` | Sin `booksim`/`airsim`, salvo que la propiedad ya los tenga conectados; `ical` y `channex` → `modes: ["real"]` |
| `GET /api/v1/distribution/options/catalog/?channel=booksim` | Catálogo sugerido | 400 `not_supported` |
| `POST /api/v1/distribution/connections/` con `channel_code: "booksim"` o `"airsim"` | Igual que antes | 400 `not_supported`, `fields.channel_code` |

### Pagos en línea (marketplace, portal)

`GET /api/v1/public/marketplace/properties/<slug>/` (`booking.online_payments`), `…/offers/` (`online_payments`),
`POST checkout/quote/` y `POST bookings/` usan `engine.online_payments_enabled(prop)`:
- **simulaciones activas**: `IntegrationSetting(payments).enabled` (lo de siempre);
- **simulaciones apagadas**: `integrations.is_live(prop, "payments")` (real, activa y sin campos obligatorios
  faltantes). Si es falso, los planes con depósito no se venden en línea, `pay_now` → 409 `online_payments_disabled`
  y el checkout solo ofrece "Pagar en el hotel".

`GET /api/v1/public/guestportal/<token>/` → `balance.can_pay` sigue la misma regla.

### iCal (distribution)

- **Al guardar una conexión**, una `ical_import_url` que resuelve a una red interna devuelve 400 con
  `fields.room_mappings`: `["Fila 1: La URL del calendario apunta a una red interna"]`. Un dominio que no resuelve se
  acepta y se revisa al descargar.
- **Al descargar**, las URL internas, el DNS interno o las redirecciones a redes internas fallan con `ChannelError`
  `invalid_url` (no reintentable) y alerta `ical_import_failed`. Un DNS que no resuelve da `dns_error` (reintentable).

### Revenue: razón `rounding`

Aparece en `recommendations/`, `recommendations/{id}/`, `simulate/` y `run-now/`. Ejemplo real de Casa Aurora,
Estándar · FLEX, 31-oct:

```json
{"date": "2026-10-31", "current_price": "368000.00", "recommended_price": "441000.00",
 "reasons": [ "…reglas…",
   {"type": "limit", "kind": "max_daily_change", "percent": "20.00", "price": "441000.00", "rounded": true},
   {"type": "limit", "kind": "rounding", "step": "1000.00", "from": "441600.00", "price": "441000.00"}],
 "explanation": {
   "es": "Sube 19,84 % (de $ 368.000 a $ 441.000): ocupación del 90 % (+15 %); puente de Día de Todos los Santos (observado) (+12 %); sábado (+8 %); limitado al cambio máximo de 20 %; redondeado a múltiplos de $ 1.000.",
   "en": "Up 19.84% (from $368,000 to $441,000): … capped at the 20% maximum change; rounded to multiples of $1,000."}}
```

Antes el tope decía «el precio se queda en $ 441.600» y el recomendado era $ 441.000. La razón `rounding` solo aparece
cuando el redondeo cambió el precio.

### Onboarding IA

`POST /api/v1/ai/onboarding/propose/` normaliza con `dedupe_extras=True`. `normalize/` (las ediciones del usuario) no
deduplica. Avisos nuevos en `warnings`:

```json
["Uní extras que eran el mismo servicio: «Desayuno buffet» con «Desayuno»; «Parqueo cubierto» con «Parqueadero».",
 "No repetí extras que tu hotel ya vende: «Desayuno», «Parqueadero»."]
```

### Datos nuevos en las alertas (para traducirlas)

La campana y la lista traducen con ellos. Las alertas creadas antes del cambio no los traen y muestran su texto
guardado hasta que el productor las vuelve a levantar; `raise_alert` actualiza `data`.

| Kind | Claves nuevas en `data` |
|---|---|
| `unguaranteed_arrival`, `missing_tra`, `missing_invoice` | `guest` |
| `duplicate_payment` | `code` (`""` = folio de la casa) |
| `rate_out_of_bounds` | `count`, `first`, `prices` (hasta 4) |
| `unposted_nights` | `guest`, `room` (`""` = sin habitación) |
| `vip_room_not_ready` | `guest`, `room_status` |
| `cash_difference` | `expected`, `counted`, `user` |
| `oversold` | `count`, `worst`, `first` |
| `llm_degraded` | `provider_label` |
| `chatbot_handoff` | `summary`, `reservation_code` |
| `ical_import_failed`, `channel_pull_failed` | `connection` |
| `channel_import_failed` | `connection`, `error` |
| `channel_sync_failed` | `connection`, `attempts` |
| `guestportal_duplicate_guest` | `variant` (`profile`\|`companion`), `owner` |
| `guestportal_cancelled`, `guestportal_modified` | `code` |
| `guestportal_request` | `code`, `guest`, `extra_name` (`{es, en}`), `time`, `notes` |

Kinds de otras apps que ya se traducen con su `data` actual:
- `sire_missing_data`, `sire_unsubmitted`, `tra_missing_data`, `tra_error`;
- `inventory_drift`, `overbooking`, `unassigned_arrivals`, `overdue_departures`;
- `night_audit_errors` (el título), `integration_fallback`, `company_over_credit` (el mensaje);
- `payment_on_closed_folio`, `payment_voided_by_provider`, `payment_amount_mismatch` (el título);
- `invoice_resolution` (la variante bloqueante);
- `payment_after_cancellation` y `automation_failed` (el título: el código sale del texto guardado y el nombre de la
  automatización no viene en `data`).

El resumen del día (`daily_brief`) conserva en español el texto que escribe la IA. En inglés se arma con sus `facts`
(llegadas, VIP, sin habitación, salidas con saldo, en casa, ocupación y alertas).

---

## Contratos implementados / consumidos

- **Consumidos (P1)**:
  - backend: `apps.core.runtime.simulations_enabled`, `require_simulations` y `apps.core.integrations.is_live` /
    `available_modes`;
  - frontend: `useRuntimeConfig()` (`simulations_enabled`, `public_base_url`, `support`), `whatsappLink`,
    `mailtoLink`, `hasSupportChannel` y `NavItem.devOnly`.
- **Otros consumidos, solo lectura**: `bookings.Reservation/Stay`, `guests.GuestDocument` (el borrado se hace desde
  `guests`, su propia app), `guestportal.OnlineCheckin` (lo modifica la retención; ver "Limitaciones") y
  `rates.Extra` (onboarding).
- **Implementados** (servicios nuevos que otras apps pueden llamar):
  - `apps.guests.retention.purge_identity_documents(prop, *, retention_days, today=None) -> PurgeResult`;
  - `apps.distribution.providers.resolve_public(host, port)`;
  - `apps.distribution.providers.check_public_url(url, *, resolve=True)`;
  - `apps.ai.onboarding.extra_concept(name, code="")`.

## Señales emitidas / escuchadas

Ninguna nueva. Las alertas de las apps de P6 llevan más claves en `data` (tabla de arriba).

## Automatizaciones registradas

| Código | Horario | Qué hace |
|---|---|---|
| `guests.purge_identity_documents` | diario 03:40 (zona de beat) | Habeas Data. Con `retention_days` (180 por defecto, **por propiedad** en Automatizaciones → Parámetros; `0` = nunca, resultado `skipped`) borra, N días después de la salida: (1) las fotos de documentos de identidad de los huéspedes cuya **última** reserva en la organización terminó en esta propiedad antes del corte y que no tienen reservas activas en ninguna parte; (2) las firmas del check-in online de las reservas de esta propiedad que terminaron antes del corte. Borra los archivos al confirmar la transacción. Audita sin datos personales (`guests.documents_purged`, `guests.signature_purged`, `guests.checkin_documents_purged`, `source="automation"`) y marca `OnlineCheckin.data.retention_purged_at`. La evidencia de aceptación (fecha, IP, navegador) se conserva. Resúmenes: «Nada que borrar: ninguna salida hasta el 01/04/2026 guarda documentos» o «Borrados 3 documentos de 2 huéspedes y 2 firmas (salidas hasta el …)» |

Se verificó con `automation.run` en una transacción revertida:
- hoy en Casa Aurora: «Nada que borrar»;
- con una salida simulada de hace 200 días: 1 documento y 1 firma borrados, con la marca y 2 eventos de auditoría. El
  documento del titular, que tiene otra reserva activa, se conservó;
- con `retention_days=0`: `skipped`.

## Proveedores de integración registrados

Sin proveedores nuevos. `channel_ical · real` (`RealIcalProvider`) ahora descarga con `_PublicOnlyTransport` (ver
SSRF).

## Extensiones de frontend exportadas

- **Rutas** (`saas/routes.tsx`, públicas y lazy): `/legal` y `/legal/:doc`, con el header y el footer de Housetel.
- **Nav**: `channels.otaSim` y `messaging.waSim` con `devOnly: true`.
- **Piezas reutilizables**:
  - `features/saas/components/LegalLink` (enlace legal dentro de un `<Trans>`, en otra pestaña) y `LegalFooterLinks`
    (`docs?: LegalDocId[]`);
  - `features/saas/legal/types` (`LEGAL_PATHS`, `LEGAL_VERSION`);
  - `features/ai/lib/chat-offset` (`useChatOffset(ref, active)`: una barra fija abajo le avisa su alto a la burbuja);
  - `features/control/lib/alert-text` (`alertText`, `useAlertText`);
  - `features/control/lib/guides` (`guideFor`, `webhookUrlFor`, `isLocalUrl`, `TUNNEL_COMMAND`, `DOCS_PATH`);
  - `features/control/lib/integrations` (`allowedModes`, `isLive`);
  - `features/control/components/IntegrationGuide` (`IntegrationGuide` y `WebhookBox`).
- **Variables CSS en `<html>`**: `--public-chat-inset` (espacio que la burbuja ocupa abajo) y `--public-chat-offset`
  (alto de una barra fija inferior).

## Dependencias nuevas (pip/npm) y por qué

Ninguna. El transporte de iCal usa `httpcore`, que ya viene con `httpx`; están instalados `httpx` 0.28.1 y `httpcore`
1.0.9.

## Cambios requeridos en archivos compartidos u otras apps (para P-INT)

1. **Reiniciar `worker` y `beat`**. Llevan horas con el código anterior:
   - beat no programa `guests.purge_identity_documents` y el worker no la tiene;
   - las corridas programadas de `ai.anomaly_scan` no guardan la `data` nueva;
   - `revenue.run_rules` no agrega la razón `rounding`.

   Mientras tanto, "Ejecutar ahora" y "Correr ahora" corren en el proceso web, que ya tiene el código nuevo. Las 241
   recomendaciones pendientes de Casa Aurora son del seed anterior y aún dicen «$ 441.600»: el `seed_demo --reset` de
   P-INT, o un "Correr ahora" de Revenue, las regenera.
2. **`backend/apps/control/services/integrations.py`** (C12; no tiene dueño en la Fase P):
   - `available_modes` debería ser `integrations.available_modes(kind)` (P1) en vez de "todos los modos
     registrados";
   - el PATCH debería rechazar `mode: "simulated"` cuando `integrations.mode_allowed(kind, "simulated")` es falso.

   Hoy el frontend ya deshabilita "Simulado" donde las simulaciones están apagadas (salvo email e IA), pero la API lo
   aceptaría.
3. **`frontend/src/app/layouts/PublicLayout.tsx`** (P1): agregar al `PublicFooter` los enlaces legales, p. ej.
   `<LegalFooterLinks docs={['terminos', 'privacidad', 'encargo-datos']} />` de
   `@/features/saas/components/LegalFooterLinks`. El motor de reservas y el portal ya los tienen en su pie.
4. **`docs/integraciones-reales.md`** (P1): las guías de la app enlazan a sus secciones por nombre (`docsSection` en
   `control/lib/guides.ts`, p. ej. «1. Pagos en línea: Wompi», «4. Canales: Channex (staging)»). Si P1 renombra un
   título, ajustar ahí. El comando del túnel se alineó con el de P1 (`--http-host-header localhost:5173`).
5. **Datos que faltan en alertas de otras apps.** Opcional: con esto también se traducirían sus textos
   completos.
   - bookings (P3): `payment_after_cancellation` → `code`, `amount`.
   - compliance (P4): `invoice_rejected` e `invoice_error` → `number` y tipo de documento; `invoice_resolution`
     (advertencia) → `prefix`.
   - corporate (P4): `company_over_credit` → `company`.
   - finance (P4): `refund_pending` y `refund_failed` → `amount`; `payment_amount_mismatch` → `expected` y `paid`.
   - core (P1): `automation_failed` → `name_es` y `name_en`.
   - saas: `plan_limit` → `plan_name`, `properties` y `max_properties`.

   Al agregarlos, sumar los textos en `control:alertText.<kind>`: el título y el mensaje con esos placeholders.
6. **`make smoke`**: pasos sugeridos para la Fase P. Todos los probó mi smoke por el proxy (ver "Verificación"):
   - `GET /api/v1/control/automations/guests.purge_identity_documents/` → `params.retention_days == 180`;
   - `POST /api/v1/revenue/simulate/ {}` → alguna recomendación con la razón `rounding`;
   - `POST /api/v1/distribution/connections/` iCal con `https://localtest.me/cal.ics` → 400 «red interna»;
   - `GET /legal/privacidad` con `Accept: text/html` → 200.
7. **Prueba de producción de P-INT**:
   - los simuladores devuelven 404, pero las páginas `/app/simulators/*` siguen existiendo y muestran "no existe en
     este entorno";
   - el menú no los muestra;
   - el checkout de un hotel sin Wompi configurado solo ofrece "Pagar en el hotel".

## Limitaciones conocidas / pendientes

- **Sin tests** (modo MVP). Tests heredados que probablemente se rompan:
  - distribution: los de `check_public_url` e iCal ahora resuelven DNS; sin red, los dominios de prueba dan
    `dns_error`, así que conviene *mockear* `socket.getaddrinfo`. Los que comparan `data` de alertas o
    `options.channels` exactos ahora ven `connection`, `error` y `simulator`;
  - ai: la `data` exacta de las anomalías; el onboarding con extras duplicados ahora los une;
  - revenue: los que comparan las `reasons` exactas (nuevo `rounding`, `rounded`, precio final);
  - control (frontend): el texto «N de M integraciones en modo simulado»; la caja del webhook se movió a la guía; la
    campana y la lista ahora traducen;
  - marketplace (frontend): el checkout (resumen móvil y barra fija).
- **Alertas en inglés**: cuando a la `data` le falta algo (alertas viejas o las de la tabla del punto 5) se ve el texto
  guardado en español. Los mensajes con el error del proveedor (canales, IA) insertan ese error tal como llega.
- **Textos legales**: son una plantilla completa, pero no son asesoría legal; conviene que un abogado los revise
  antes de vender (`LEGAL_VERSION = 1.0`, vigente desde el 28-sep-2026). Si hay diferencias, prevalece la versión en
  español (lo dice la página en inglés).
- **Retención**:
  - Borra solo las fotos de documentos y las firmas. No toca los datos del registro (TRA y SIRE los exige la ley) ni
    las facturas.
  - Corre una vez al día, con la fecha de negocio de cada propiedad.
  - Un huésped con estadías en varios hoteles de la cadena se decide por el hotel de su última salida (con su N).
  - Escribe en `guestportal.OnlineCheckin`: la firma y la marca `retention_purged_at` (ambas son apps de P6).
- **SSRF**:
  - Se ignoran los proxies del entorno (`trust_env=False`).
  - La primera validación al guardar hace una consulta DNS síncrona.
  - Un dominio que hoy no resuelve se guarda y falla al descargar, con alerta.
- **Burbuja**: en `/g/*` y en los checkouts se aparta al bajar. Si otra página agrega una barra fija inferior, debe
  llamar a `useChatOffset`.
- **Guías**: los textos están en `control/lib/guides.ts` (ES/EN), no en los locales, para no inflar el bundle global.
  Los caminos dentro de los paneles de Wompi, Meta, Channex y Factus pueden cambiar con el tiempo.
- **Conexiones de simulador existentes** (BookSim/AirSim del demo) en una instalación con las simulaciones apagadas:
  - siguen listadas en Canales para poder borrarlas;
  - el menú y el botón del simulador desaparecen y sus endpoints responden 404;
  - el ARI sigue escribiéndose en las tablas del simulador.
- **Capturas en headless**: la verificación visual la hice en un Chrome headless propio (perfil temporal y puerto 9573).
  Con la emulación móvil de Chrome de escritorio, al abrir una hoja la barra de scroll clásica corre 13 px la vista, así
  que el encabezado de la hoja sale un poco recortado en la captura. Es un artefacto de la emulación, no de la app.

## Verificación hecha (sin tests)

- `docker compose exec -T backend python manage.py check` → sin problemas.
- `makemigrations marketplace revenue ai distribution messaging guests guestportal --check --dry-run` → "No changes
  detected".
- `ruff check` y `ruff format --check` → limpios en las 7 apps y en `sire.py` (sin tests): 170 archivos.
- Frontend:
  - `npx tsc -p tsconfig.app.json --noEmit | grep` de mis paths → sin errores (solo quedan errores viejos en
    `frontdesk/__tests__`, de P3);
  - `npx eslint` en las 9 features → limpio;
  - paridad ES/EN de claves en las 9: ai 360, marketplace 494, calendar 213, control 737, saas 571, channels 377,
    messaging 305, guestportal 457 y revenue 360;
  - todas las claves literales que usa el código existen.
- **Smoke por el proxy de Vite**, con cookie jar y CSRF, como `owner@casaaurora.co`; todo OK:
  - `public/core/config`, login, 9 tarjetas de integraciones;
  - la automatización de retención: leer, parámetro 365, restaurar a 180, ejecutar ahora («Nada que borrar»);
  - ejecutar `ai.anomaly_scan`, alertas y conteo;
  - `revenue/simulate/`: 167 de 241 recomendaciones con `rounding`; el 31-oct dice «…redondeado a múltiplos de
    $ 1.000»;
  - canales: `options/`, el inventario del simulador y los contactos del simulador de WhatsApp (200 en desarrollo);
  - iCal con `https://localtest.me/cal.ics` → **400 «apunta a una red interna»**;
  - marketplace: `online_payments: true` y 9 ofertas del 20 al 22 de octubre;
  - portal de HT-DPZNNK: `can_pay: true`;
  - `/legal/{terminos,privacidad,encargo-datos}` → 200;
  - logout.
- **Simulaciones apagadas** (`override_settings(HOUSETEL_ALLOW_SIMULATIONS=False)`, en una transacción revertida):
  - los 5 endpoints de simulador → 404;
  - `catalog?channel=booksim` → 400;
  - crear AirSim → 400 `not_supported`;
  - `options/` con `ical` y `channex` → `["real"]`;
  - `booking.online_payments` y `payments_enabled` del portal → `false`;
  - `public/core/config` → `simulations_enabled: false`.
- **SSRF en el contenedor**:
  - bloqueadas: `127.0.0.1`, `localhost`, `10.0.0.5`, `[::ffff:127.0.0.1]`, `169.254.169.254`, `localtest.me` y
    `127.0.0.1.nip.io` (DNS → 127.0.0.1), `backend` y `db.internal`;
  - permitidas: `www.google.com` y `calendar.google.com`;
  - `dns_error` para un dominio inexistente;
  - **descarga real** del calendario de festivos de Google: 178.843 caracteres;
  - **redirecciones** de httpbin.org hacia `127.0.0.1:8000`, `localtest.me:8000` (bloqueada al conectar) y
    `169.254.169.254` → bloqueadas.
- **Onboarding** (shell):
  - Casa Aurora ya vende desayuno y parqueadero → solo propone «Masaje», con el aviso «No repetí…»;
  - un hotel sin extras → «Desayuno buffet» se une con «Desayuno» y «Parqueo cubierto» con «Parqueadero».
- **Alertas**: con el módulo real `alert-text.ts` cargado por el SSR de Vite, con i18next y los locales reales, rendí
  18 alertas del demo y 39 sintéticas (todas las kinds) en ES y EN. Salen los plurales correctos y las fechas y el
  dinero bien formateados. Los kinds sin texto, o sin datos suficientes, caen al texto guardado.
- **Seeds** de `guests`, `distribution`, `marketplace`, `guestportal`, `messaging`, `revenue` y `ai`, en una
  transacción revertida:
  - el de revenue y el de las solicitudes del portal se corrieron desde cero;
  - 1,6 s en total: guestportal 0,76 s y revenue 0,66 s;
  - 903 pendientes, 743 con `rounding`;
  - las alertas de solicitud ya traen `code`, `guest` y `time`;
  - la segunda pasada, 0,28 s sin cambios (idempotente).
- **`make routes` restringido a mis páginas** (`frontend/scripts/route-smoke.mjs` con `PORT=9571`, Chrome propio):
  24 rutas OK a 1440 px y a 375 px, sin errores de consola, sin API ≥ 400 y sin scroll horizontal.
  - Rutas: Hoy, calendario, revenue, canales, los dos simuladores, bandeja, alertas, integraciones, automatizaciones,
    `/search`, `/hotel/…`, `/book/…`, `/h/…`, `/h/…/book`, `/g/:token`, `/g/:token/checkin` y `/signup`; más el
    aterrizaje de 4 roles.
  - Un primer intento dio "Failed to fetch dynamically imported module": fue una recarga de Vite por ediciones de
    otros agentes y al repetirlo pasó.
- **Revisión visual** con capturas en ese Chrome propio. Se corrigieron tres defectos que las capturas mostraron:
  - la guía desbordaba la hoja por un *grid blowout*;
  - la barra del checkout no se quedaba fija;
  - la burbuja tapaba "Reservar" en el motor de reservas.

  Capturas revisadas:
  - integraciones, con el banner, las tarjetas y la guía de Wompi y de WhatsApp (1440 y 375 px);
  - `/app/alerts`, `/legal/privacidad` y `/legal/encargo-datos`;
  - el checkout a 375 px (arriba, al medio y al final);
  - el motor con la barra "Tu selección" y la burbuja encima;
  - el portal a 375 px (Pagar y el pie con los enlaces legales);
  - el calendario de 30 días con SEP y OCT sin solaparse;
  - "Ejecutar ahora" de la retención en Automatizaciones.

**Datos que dejé en la BD de desarrollo** (todo lo demás se probó en transacciones revertidas):
- 4 corridas manuales de `guests.purge_identity_documents` en Casa Aurora («Nada que borrar»);
- 3 corridas manuales de `ai.anomaly_scan`;
- 6 eventos `control.automation_updated`: el parámetro 365 y su restauración, tres veces. La automatización quedó con
  sus valores por defecto (`params: {}` = 180 días).

No quedó ninguna conexión, reserva ni mensaje nuevo.

---

## Cómo probarlo en la UI

App: **http://localhost:5173** (desarrollo, con las simulaciones activas). Usuario: **`owner@casaaurora.co` /
`housetel123`** (Hotel Casa Aurora). Para ver el modo producción sin tocar el stack compartido está la prueba de P-INT
(`make prod-up`); aquí se indica qué cambia en cada caso. Links del portal:

```bash
docker compose exec -T backend python manage.py portal_links --property casa-aurora --days 2
```

1. **Integraciones guiadas** (`/app/settings/integrations`).
   - El banner dice **«7 de 9 en modo simulado» · «Activa los modos reales»**, con la explicación, el botón
     **«Empezar por Pagos en línea →»** y el tablero de placas (terracota = real, rayada = simulado). Cada placa es un
     botón que abre su guía.
   - Clic en **Empezar por Pagos en línea** o en **Guía** de la tarjeta de Pagos: se abre la hoja en modo Real, con
     la guía **«Guía para pasar a modo real · Wompi · 5 pasos»** abierta y a la vista. Contiene:
     - «Crear cuenta de comercio en Wompi ↗»;
     - Sandbox (con «Elegido») frente a Producción;
     - los pasos 1–5 con su numeración de llavero;
     - en el paso 3, **«URL de eventos (webhook)»**: `http://localhost:5173/api/v1/public/finance/webhooks/wompi/`,
       con el botón copiar;
     - el aviso amarillo **«Esta URL es local…»** con `cloudflared tunnel --url http://localhost:5173
       --http-host-header localhost:5173` (copiar) y qué hacer después;
     - «Dónde está cada dato» (Llave pública → Desarrolladores › Llaves del API…);
     - al final, «Guía completa en el repositorio: `docs/integraciones-reales.md` › 1. Pagos en línea: Wompi» y
       «¿Te trabaste? soporte@housetel.co».
   - Debajo, cada campo del formulario tiene **«Dónde está:»**, con un pin terracota. Cancelar no cambia nada.
   - Repetir con **WhatsApp**: «Meta (WhatsApp Cloud API) · 6 pasos», con el webhook de WhatsApp en el paso 5.
     **iCal**, **TRA** y **SIRE** muestran una nota en vez de sandbox/producción. **Channex** avisa de la
     certificación.
   - Con `PUBLIC_BASE_URL` apuntando a un túnel (P1), la URL del webhook sale con esa dirección y el aviso de local
     desaparece.
   - **En producción** (o con `HOUSETEL_ALLOW_SIMULATIONS=0`):
     - el interruptor "Simulado" de las tarjetas queda deshabilitado, con el título «No disponible en este entorno»
       (salvo Email e IA);
     - el banner dice «N integraciones por configurar · Termina de configurar tus integraciones · Seguir con …», con
       las placas pendientes marcadas con anillo ámbar.
2. **Alertas traducidas** (campana del topbar, widget "Alertas" en Hoy y `/app/alerts`).
   - En español se ven igual que antes, pero con plurales correctos: «1 archivo SIRE por cargar en Migración
     Colombia», «SIRE: 1 movimiento de extranjero…», «TRA: 1 huésped con datos faltantes».
   - Cambiar a **inglés** (menú de idioma del topbar; cambia el idioma del perfil): «TRA: 1 guest with missing
     details», «1 SIRE file to upload to Migración Colombia», «A guest wants to talk to the team», «Transfer requested:
     HT-4V6EW5», «Daily summary · Monday, September 28», con el resumen del día en inglés armado con sus cifras, y
     «The AI is answering in simulated mode».
   - Tras **Automatizaciones → Detección de anomalías → Ejecutar ahora**, las alertas de TRA, factura y garantía se
     rehacen con el huésped y traducen también el mensaje («Juan Pablo … arrives on Tuesday, September 29 and booking
     HT-… has no guarantee or payments…»).
   - Volver a español al terminar.
3. **Retención Habeas Data** (`/app/settings/automations`, grupo **Huéspedes**).
   - «Retención de documentos (Habeas Data)», «Todos los días a las 03:40».
   - **Ejecutar ahora** → queda la caja verde «Ejecutada ahora: Correcta · hace menos de un minuto · Nada que borrar:
     ninguna salida hasta el 01/04/2026 guarda documentos» (se cierra con ×), además del toast. Esto es el punto 4d:
     el aviso queda visible aunque la corrida sea instantánea.
   - **Parámetros** → «Días después del check-out antes de borrar documentos y firmas (0 = nunca)» = 180 → cambiar a
     0 → Guardar → badge «Ajustada» → Ejecutar ahora → «Ejecutada ahora: Omitida · … Retención en 0 días: este hotel
     conserva los documentos y las firmas» → **Restaurar valores por defecto**.
   - Política: `/legal/privacidad#conservacion`.
   - Si una reserva perdió documentos, su pestaña **Check-in online** lo dice («Las fotos de los documentos y la firma
     se borraron el …»), con el enlace a la política.
4. **Legal**.
   - `/legal/terminos`, `/legal/privacidad` y `/legal/encargo-datos` (también `/legal`, que abre los términos, y
     `/legal/privacy`). Tienen:
     - eyebrow «Legal · Versión 1.0 · Vigente desde el 28 de septiembre de 2026», el título grande y el lead;
     - la fila de 3 documentos (el actual en terracota);
     - «En pocas palabras», el índice «En esta página» (en el celular, un desplegable «Contenido») y las cláusulas
       con ancla `#`;
     - el pie con el correo de soporte, Imprimir o guardar en PDF y Volver arriba.
   - En inglés, el texto en inglés y «If the versions differ, the Spanish version prevails».
   - Los enlaces abren en otra pestaña:
     - checkout `/book/casa-aurora?…` → «política de tratamiento de datos» y «términos de Housetel»;
     - check-in online `/g/<token>/checkin`, paso Firma → «política de tratamiento de datos»;
     - `/signup`, paso 2 → términos, política y contrato de encargo;
     - chat del motor (`/h/casa-aurora` → «Quiero hablar con una persona» → formulario) → política.
   - Pie del motor de reservas (`/h/casa-aurora`) y del portal (`/g/<token>`): «Política de datos personales ·
     Términos y condiciones».
5. **Checkout móvil y burbuja** (a **375 px**).
   - `/hotel/casa-aurora?checkin=2026-10-20&checkout=2026-10-22&adults=2` o `/h/casa-aurora?…` → **Elegir** una
     tarifa → aparece abajo la barra «1 habitación · $ … · Reservar» y la burbuja del chat **flota encima**, sin tapar
     el botón.
   - **Reservar** → `/book/…`:
     - arriba, la tarjeta plegable «Hotel Casa Aurora · 20–22 oct 2026 · 2 adultos · TOTAL $ 761.600», que se
       despliega en el detalle;
     - abajo, **fija todo el tiempo**, la barra «Total $ 761.600 · Confirmar reserva» (o «Reservar y pagar $ …» con
       «pagas ahora …»);
     - la burbuja es pequeña, flota sobre la barra y se aparta al bajar.
   - **Portal** `/g/<token>`: al bajar la burbuja se aparta; al final queda en su espacio, sin tapar «Pagar» ni el
     pie.
   - **En producción sin Wompi en vivo**: la sección Pago del checkout muestra una sola opción, «Pagar en el hotel»,
     marcada, con «Este hotel recibe el pago al llegar: no pagas nada en línea»; el portal no muestra «Pagar».
6. **Simuladores**.
   - En desarrollo siguen: Herramientas → Simulador de OTAs y Simulador de WhatsApp.
   - **En producción**: no aparecen en el menú ni en ⌘K. `/app/simulators/ota` y `/app/simulators/whatsapp` muestran
     «El simulador … no existe en este entorno». Sus API responden 404. En Canales → Conectar canal solo aparecen
     iCal y Channex (este solo en modo Real). Los botones "Simulador" de las tarjetas y de la Bandeja desaparecen.
7. **iCal seguro** (Canales → Conectar canal → iCal):
   - pegar `https://localtest.me/cal.ics` en una categoría → Conectar → «Fila 1: La URL del calendario apunta a una
     red interna»;
   - con `http://127.0.0.1/…` o `https://10.0.0.5/…`, lo mismo.
8. **Revenue** (`/app/revenue`).
   - **Correr ahora** (usa 1 llamada de IA para el resumen), o esperar la próxima corrida programada con el worker ya
     reiniciado.
   - Clic en **Estándar · sáb 31 oct** → detalle con:
     - «Tope de cambio diario de 20 % — con el redondeo, el precio se queda en $ 441.000»;
     - **«Redondeo a múltiplos de $ 1.000 — de $ 441.600 al precio final $ 441.000»**;
     - la explicación «…limitado al cambio máximo de 20 %; redondeado a múltiplos de $ 1.000.».
   - Antes decía «el precio se queda en $ 441.600».
9. **Calendario** (`/app/calendar`, **30 días**): en la cabecera «SEP» queda sobre «DOM 27» y «OCT» sobre «JUE 1», en
   su propia línea, sin montarse sobre el día.
10. **Onboarding IA** (`/app/onboarding`, mejor en un hotel creado por `/signup`): describir un hotel que mencione
    «desayuno» dos veces (p. ej. «Desayuno a 30.000… desayuno buffet 35.000») → **Proponer configuración** → en
    Extras sale un solo desayuno, con el aviso «Uní extras que eran el mismo servicio…». En Casa Aurora, que ya vende
    desayuno y parqueadero, avisa «No repetí extras que tu hotel ya vende…».
11. **Búsqueda**: `/search?city=cartagena` → el título es **«Cartagena»**; con `city=villa de leyva` →
    **«Villa de Leyva»**.
12. **Contraste**: en claro y oscuro, los textos secundarios (`text-subtle`: pistas, «Probada hace…», contadores) se
    leen mejor y miden ≥ 4,5:1 sobre las superficies.
