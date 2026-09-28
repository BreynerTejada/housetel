# C12 — Centro de control — integration notes

Estado (2026-09-28, modo MVP): **backend y frontend completos y verificados de punta a punta con los datos del
seed**. Hay cuatro páginas (integraciones, automatizaciones, registro de auditoría con deshacer y alertas), la
campana del topbar, el widget de Hoy y la pestaña «Historial» de la reserva.

Esta sesión retomó el trabajo parcial de intentos anteriores: la API, los servicios, `seed.py`, `api.ts`, los
componentes base y los locales. Lo evalué, lo corregí y lo completé. Siguiendo el modo MVP no escribí tests ni
corrí suites. La app `control` no tiene modelos: es una API sobre los modelos de `core`, así que tampoco hay
migraciones.

Correcciones sobre lo heredado:
- **`next_run_at` salía corrido 5 horas.** Celery evalúa el crontab en la zona del datetime que recibe; ahora recibe
  «ahora» en `CELERY_TIMEZONE`. Antes la auditoría de las 02:00 aparecía como «Próxima: 21:00».
- **Los selects obligatorios sin `default` salían como «Faltan credenciales».** Pasaba, por ejemplo, con
  `provider` del LLM o `environment` de Wompi y Channex. Ahora toman su primera opción como valor por defecto, que
  es la que usan los proveedores en tiempo de ejecución.
- **El esquema OpenAPI daba warnings.** Había colisión del componente `Confirm` con el de guests y colisiones de
  `operationId`. Los serializers se renombraron a `AuditUndoSerializer` y `AlertIdsSerializer`, y cada operación
  tiene ahora un `operation_id` explícito.
- **Datos de prueba de un intento anterior.** Borré la organización temporal «C12 Prueba (temporal)», con su
  propiedad `c12-hotel-prueba`, y los usuarios `c12@housetel.co` y `c12-recepcion@housetel.co` de la BD de
  desarrollo.

---

## API implementada

Toda la API es staff: `/api/v1/control/…`, con sesión, CSRF en las escrituras y la cabecera `X-Property-Id`. Los
errores siguen el formato `{detail, code, fields?}`.

**Secretos**: ninguna respuesta incluye un secreto. Las integraciones solo dicen qué campo secreto está guardado
(`secrets_configured`). Los `changes` de auditoría, los `data` de alertas y los `details` de corridas pasan por
`services/scrub.py`: toda clave con aspecto de credencial (`password`, `*_secret`, `api_key`, `token`…) sale como
`•••`. `status_message` se limpia de valores secretos literales. Esto se verificó con curl: un secreto de prueba no
apareció en el PATCH, en la lista ni en el detalle de auditoría.

### Integraciones (permiso `control.integrations`)

| Método y path | Respuesta |
|---|---|
| `GET integrations/` | Lista de 9 tarjetas, una por kind de `core.integrations.KINDS` salvo `saas_billing`, que es de plataforma. No crea filas. |
| `GET integrations/{kind}/` | Una tarjeta. Un kind desconocido o `saas_billing` → 404 `integration_not_found`. |
| `PATCH integrations/{kind}/` | Recibe `{mode?, enabled?, config?, secrets?}` → devuelve la tarjeta. |
| `POST integrations/{kind}/test/` | Corre `provider.test_connection()` y guarda `status`, `status_message` y `last_checked_at` → devuelve la tarjeta más `test: {ok, message}`. |

Tarjeta de ejemplo (`GET integrations/payments/`, recortada):

```json
{"kind": "payments", "label": "Pagos", "configured": true, "mode": "simulated", "default_mode": "simulated",
 "enabled": true, "status": "ok", "status_message": "OK", "last_checked_at": "2026-09-28T05:09:21Z",
 "updated_at": "…", "config": {},
 "secrets_configured": {"events_secret": false, "integrity_secret": false, "private_key": false},
 "missing_required": [], "available_modes": ["real", "simulated"],
 "providers": {
   "real": {"label": "Wompi (tarjeta, PSE, Nequi)", "label_en": "", "config_fields": [
     {"name": "environment", "label_es": "Ambiente", "label_en": "Environment", "type": "select", "secret": false,
      "required": true, "options": [{"value": "sandbox", "label_es": "Sandbox (pruebas)", "label_en": "…"}, "…"],
      "help_es": "", "help_en": "", "default": "sandbox"},
     {"name": "private_key", "type": "password", "secret": true, "required": true, "default": null, "…": "…"}]},
   "simulated": {"label": "Pasarela simulada (sin cobros reales)", "label_en": "", "config_fields": []}}}
```

Cómo se leen los campos de la tarjeta:
- **Formularios**: salen de los `CONFIG_FIELDS` de los proveedores registrados. `type` se normaliza a
  `text|password|url|select|boolean|number|textarea|email`.
- **Secretos**: `secret: true` o `type: "password"` marca un campo de solo escritura.
- **`missing_required`**: se calcula para el proveedor del modo actual.
- **`default`**: un select obligatorio sin `default` recibe su primera opción.

Ejemplo de PATCH (se usó tal cual en la verificación):

```json
{"config": {"environment": "sandbox", "public_key": "pub_test_ABC"}, "secrets": {"private_key": "prv_test_…"}}
```

Reglas del PATCH:
- **Secretos**:
  - un valor lo guarda cifrado con `set_secrets`;
  - `null` lo borra;
  - `""` lo conserva.
- **Config**: `null` borra la clave.
- **Validación**:
  - los valores se validan según el tipo del campo: número, booleano, opción del select y URL `http(s)`;
  - un campo desconocido, o un secreto enviado en `config`, → 400 `validation_error` con
    `fields: {"config.x": [...]}`;
  - un `mode` sin proveedor → 400.
- **Estado**: cualquier cambio que no sea solo `enabled` devuelve el estado a `unknown`.
- **Auditoría**: queda `control.integration_updated`, con un diff sin valores secretos: los secretos aparecen como
  `configurado`, `actualizado` o `eliminado`. La prueba de conexión audita `control.integration_tested`.

### Automatizaciones (permiso `control.automations`)

Solo aparecen las automatizaciones con `scope="property"`; las de plataforma son del super-admin.

| Método y path | Respuesta |
|---|---|
| `GET automations/` | Lista de automatizaciones (forma abajo). |
| `GET automations/{code}/` | Una automatización. Código desconocido o de plataforma → 404 `automation_not_found`. |
| `PATCH automations/{code}/` | Recibe `{enabled?, params?}` → devuelve la automatización. `params` solo acepta las claves de `default_params`, tipadas como su valor por defecto; `params: null` o `{}` restaura los valores por defecto. Audita `control.automation_updated`. |
| `POST automations/{code}/run/` | Si la mediana de las últimas 5 corridas es menor a 10 s, corre aquí → 200 `{queued: false, run, estimated_seconds}`. Si no, va a Celery (`control.run_automation_now`) → 202 `{queued: true, run: null}`. Si ya hay una corrida en curso (menos de 15 min) → 409 `automation_running`. Corre aunque la automatización esté pausada y registra `triggered_by`. |
| `GET automation-runs/?code&status&page&page_size` | Historial paginado, del más nuevo al más viejo. `status` acepta una lista separada por comas. |
| `GET automation-runs/{id}/` | Una corrida con `details` sin secretos. |

```json
{"code": "bookings.auto_assign_rooms", "app": "bookings",
 "name": {"es": "Asignación automática de habitaciones", "en": "Automatic room assignment"},
 "description": {"es": "…", "en": "…"},
 "schedule": {"cron": "0 6 * * *", "every_seconds": null,
              "text": {"es": "Todos los días a las 06:00", "en": "Daily at 06:00"}},
 "next_run_at": "2026-09-28T06:00:00-05:00", "enabled": true, "default_enabled": true, "customized": false,
 "params": {"days_ahead": 1}, "default_params": {"days_ahead": 1}, "param_types": {"days_ahead": "integer"},
 "last_run": {"id": "…", "code": "…", "name": {"es": "…", "en": "…"}, "status": "success",
              "started_at": "…", "finished_at": "…", "duration_ms": 173,
              "summary": "2 estadías asignadas, 0 sin habitación", "triggered_by": null, "manual": false},
 "recent_runs": [{"id": "…", "status": "success", "started_at": "…"}], "stats_7d": {"runs": 1, "failed": 0}}
```

El texto de `schedule` se genera desde el crontab en ES y EN (servicio `schedules.describe`). Ejemplos: «Cada 15
minutos», «Todos los días a las 05:00, 11:00, 17:00 y 23:00», «El día 1 de cada mes…».

### Auditoría (permiso `control.audit`; deshacer exige además `control.audit_undo`)

**Alcance**: los eventos de la propiedad **más los de nivel organización** de su org (`property` null: huéspedes,
equipo, roles…). Nunca se muestran eventos de plataforma.

| Método y path | Respuesta |
|---|---|
| `GET audit/` | Paginado, del más nuevo al más viejo. Acepta los filtros de la lista siguiente. |
| `GET audit/facets/` | `{actions: [{action, count}], apps: [{app, count}], sources: [{source, count}], actors: [{id, name, email}], total}`. Llena los filtros. |
| `GET audit/{id}/` | Detalle: el evento más `changes` (sin secretos), `diff: [{field, before, after}]`, `details: [{field, value}]`, `row_changes: [{label, created, changes: [...]}]`, `row_changes_total`, `request_id`, `undo_event_id`, `original_event_id` y `can_undo` (`undoable` y además el permiso). Lo usa la grilla de tarifas de B2a. |
| `POST audit/{id}/undo/` | Recibe `{confirm: true}` y llama a `core.audit.undo(event, actor)` → devuelve el detalle actualizado (`undone_at`, `undo_event_id`). |

Filtros de `GET audit/`, todos opcionales:
- `action`: exacta.
- `app`: prefijo de la acción.
- `source`: lista separada por comas.
- `actor`: id del usuario, o `none` para las acciones sin usuario.
- `target_type` y `target_id`.
- `reservation`: la reserva, sus estadías, folios, cargos, pagos y reembolsos, y todo lo que apunta a ella (check-in
  online, facturas…), más los «Deshizo» de todo eso.
- `reversible=1`.
- `undone=0|1`.
- `start` y `end`: `YYYY-MM-DD`, ambos inclusivos, en la hora del hotel.
- `q`: busca en el resumen, el actor o la acción.

Ítem de la lista:

```json
{"id": "…", "created_at": "…", "action": "bookings.room_assigned", "app": "bookings", "source": "user",
 "actor": {"id": "…", "email": "owner@casaaurora.co", "name": "Valentina Rojas"}, "actor_label": "…",
 "summary": "Asignó la habitación 205 a HT-J65SZS", "target_type": "bookings.stay", "target_id": "…",
 "target_link": "/app/reservations/<id>", "scope": "property", "property": {"id": "…", "name": "…"},
 "has_changes": true, "reversible": true, "undoable": true, "undone_at": null, "undone_by": null}
```

`target_link` sale de `services/targets.py`: reserva, huésped, categoría, habitación, factura o una página fija
según el tipo. Un evento es `undoable` si es `reversible`, no está deshecho y hay un handler registrado para su
acción. Hoy son 3: `bookings.room_assigned`, `bookings.room_unassigned` y `rates.bulk_update`; este último también
lo usan las recomendaciones de revenue.

Respuestas de error del undo:

| HTTP | `code` | Cuándo |
|---|---|---|
| 400 | `confirmation_required` | Falta `confirm: true`. |
| 404 | `not_found` | El evento no está en el alcance de la propiedad. |
| 409 | `undo_conflict` | Hay un cambio reversible más nuevo del mismo objeto: hay que deshacer ese primero. Trae `newer_event_id`. |
| 409 | `already_undone` · `not_reversible` · `undo_not_supported` · `undo_target_missing` | Vienen de `core.audit.undo` o del handler. |

Se verificó por curl: mover una estadía, deshacer, reintentar (409) y 403 para el rol contabilidad.

### Alertas (permiso `control.alerts`)

| Método y path | Respuesta |
|---|---|
| `GET alerts/?status=open\|resolved\|all&severity=critical,warning&kind&q&page` | Las abiertas se ordenan por gravedad y después por la más reciente. Las alertas de plataforma (`property` null) no se muestran. |
| `GET alerts/count/` | `{open, by_severity: {critical, warning, info}, latest: [6 más graves]}`. La campana lo consulta cada 60 s. |
| `GET alerts/{id}/` | Una alerta. |
| `POST alerts/{id}/resolve/` | Idempotente. Audita `control.alert_resolved`. |
| `POST alerts/resolve/` | Recibe `{ids: [...]}` (máximo 200) → devuelve `{resolved: n}`. |

Alerta: `{id, kind, severity, title, message, link (solo rutas internas "/…"), source, data (sin secretos),
created_at, updated_at, resolved_at, resolved_by}`.

## Contratos implementados / consumidos

- **Consumidos** (solo lectura y los contratos de core):
  - `core.integrations`: `KINDS`, `MODES`, `providers_for`, `default_mode`, `get_setting`, `get_provider`,
    `get_secrets` y `set_secrets`.
  - `core.automation`: `all`, `get`, `run(..., triggered_by=)`, `AutomationNotFound`.
  - `core.audit`: `record`, `undo`, el registro de handlers y `UndoError`.
  - `core.alerts`: los modelos `IntegrationSetting`, `AutomationSetting`, `AutomationRun`, `AuditEvent` y `Alert`.
  - ORM de solo lectura de `bookings.Reservation` y de las relaciones inversas (para `?reservation=`).
- **Implementados**: ningún contrato nuevo del spec. La app no tiene modelos.

## Señales emitidas / escuchadas

Ninguna.

## Automatizaciones registradas

Ninguna. Hay una tarea Celery nueva, `control.run_automation_now(code, property_id, user_id)`, en
`apps/control/tasks.py`. La usa «Ejecutar ahora» cuando una automatización suele tardar 10 s o más. Se probó
llamándola en `manage.py shell` y dio `success` con `triggered_by`.

## Proveedores de integración registrados

Ninguno: C12 los lista y los configura.

El centro de control depende de estas convenciones de `CONFIG_FIELDS`:
- `secret` o `type: "password"` hace el campo de solo escritura.
- `required` y `default`: un select obligatorio sin default usa su primera opción.
- `options` son `{value, label_es, label_en}`.
- `help_es` y `help_en` son opcionales.

## Seed (`apps/control/seed.py`)

Corre la última en `SEED_ORDER` y siembra estado derivado con los mecanismos reales:
1. **Integraciones**: prueba cada integración en modo simulado de cada propiedad, así quedan con estado «Conexión
   correcta» y la fecha de la última prueba. Las de modo real (email por SMTP, Gemini) quedan «Sin probar»: el seed
   nunca llama servicios externos.
2. **Automatizaciones seguras**: corre `bookings.inventory_reconcile` y `ai.anomaly_scan` con
   `core.automation.run`, lo que deja `AutomationRun` real y auditoría. El escaneo levanta las alertas reales del
   demo. Nunca corre automatizaciones con efectos: auditoría nocturna, mensajes, liberación de tentativas, pagos…

Es idempotente: salta lo ya probado o corrido.

Probado en una transacción con rollback sobre la BD de desarrollo. Primera pasada: 1,2 s, 21 integraciones probadas
y 6 corridas `success`. Segunda pasada: 0,1 s, sin cambios.

Nota: con la BD actual, que aún no tiene el seed de C7, el escaneo produce muchas alertas `missing_tra` y
`missing_invoice`. En el `seed_demo` completo C7 siembra antes las TRA y las facturas, así que deberían ser muchas
menos.

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

**Rutas** (`routes.tsx`, todas lazy):

| Ruta | Página |
|---|---|
| `/app/alerts` | `pages/AlertsPage` |
| `/app/settings/integrations` | `pages/IntegrationsPage` |
| `/app/settings/automations` | `pages/AutomationsPage` |
| `/app/settings/audit` | `pages/AuditPage` |

`nav.ts` no cambió.

**Extensiones**:
- `topbar.tsx`: `control-alerts`, order 30, permiso `control.alerts`. Es la campana `AlertBell`: el contador sale en
  terracota, o en arcilla si hay una alerta crítica, y se actualiza cada 60 s. El popover muestra las 6 más graves,
  cada una con enlace, «Resolver» con ✓ y «Ver todas las alertas».
- `widgets.tsx`: `control.alerts`, order 20, `md`, permiso `control.alerts`. Muestra conteos por gravedad y las 4
  más graves con enlace. El cuerpo es lazy.
- `reservation-tabs.tsx`: `control-history`, label `control:history.tab`, order 90, permiso `control.audit`. Es la
  línea de tiempo de `?reservation=<id>`, con detalle, deshacer y enlace «Abrir en el registro de auditoría»
  (`/app/settings/audit?reservation=<id>`). El cuerpo es lazy.

**Piezas reutilizables** (se importan directo; no son extensiones §E):
- `api.ts`: tipos exactos; hooks `useIntegrations`, `useUpdateIntegration`, `useTestIntegration`,
  `useAutomations`, `useUpdateAutomation`, `useRunAutomation`, `useAutomationRuns`, `useAuditEvents`,
  `useAuditFacets`, `useAuditEvent`, `useUndoAudit`, `useAlerts`, `useAlertCount` y `useResolveAlerts`; claves
  `controlKeys`. `['control', 'audit', id]` es la misma clave que usa la grilla de tarifas.
- `components/AuditTimeline` (`events`, `onOpen`, `canUndo`, `hideLinks`), `AuditEventSheet`, `UndoButton` (usa
  `DangerConfirmDialog`; exige escribir DESHACER / UNDO), `IntegrationSheet` y `ScheduleRail` (riel de 24 h en hora
  del hotel).

**URL de estado**:
- Auditoría: `?q&app&source&actor&start&end&reversible=1&reservation=<id>&event=<id>`. `event` abre el detalle.
- Alertas: `?status=resolved&severity=critical`.

**i18n**: ES y EN completos, 569 claves con paridad verificada. Incluye `fieldLabels.*` para los campos más comunes
de los diffs y la traducción de valores `status`, `mode`, `source` y `severity`.

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

1. **C-INT: reiniciar `worker` y `beat`.**
   - Los procesos del stack actual llevan corriendo desde antes de la Fase C. `celery inspect registered` solo
     muestra `core.run_automation` y `distribution.push_ari_queue`.
   - Faltan en el worker la tarea `control.run_automation_now` y las automatizaciones de las apps C (el registro del
     worker es viejo); beat tampoco las programa.
   - Hasta el reinicio, «Ejecutar ahora» funciona porque corre en el proceso web (todas las automatizaciones del
     demo tardan menos de 3 s). Solo la ruta encolada (10 s o más) necesita el worker nuevo.
2. **C1 (ReservationDetailPage): a 375 px la página entera mide ~590 px de ancho.**
   - Causa: el contenedor `mx-auto grid max-w-6xl gap-6` tiene una columna implícita `auto`, y el `min-content` del
     `TabsList` la ensancha. Son 8 pestañas, así que el `overflow-x-auto` no llega a actuar.
   - Arreglo sugerido: `grid-cols-1` en ese contenedor, o `min-w-0` en la raíz de `Tabs`.
   - Pasaba antes de la pestaña «Historial»; esta la agrava un poco.
3. **A2 (tests compartidos, C-INT): falta un handler MSW para la campana.** `AlertBell` hace
   `GET /api/v1/control/alerts/count/` en todo el shell de `/app`, así que `shell.test.tsx` y `router.test.tsx`
   necesitan un handler que devuelva `{"open": 0, "by_severity": {"critical": 0, "warning": 0, "info": 0},
   "latest": []}`. Hoy (`onUnhandledRequest: 'error'`) fallarían. El widget de Hoy usa el mismo endpoint.
4. **Opcional para los dueños de proveedores (C3, C9, B4): declarar `default` en los selects obligatorios.** Por
   ejemplo, `provider: "gemini"` en `RealLLMProvider`. El centro de control ya asume la primera opción.
5. **`SPECTACULAR_SETTINGS`: nada que agregar.** `manage.py spectacular --validate` no da warnings de `control`.
6. **Visto al validar (C10): el overlay de Vite muestra un error de reports.** `OccupancyWidgetSlot.tsx` importa
   `./OccupancyWidget`, que aún no existe (trabajo en curso de C10); aparece en `/app` y en cualquier página que
   cargue los widgets. No es de C12.

## Limitaciones conocidas / pendientes

- **Sin tests**: el modo MVP pospone los de control para la fase de tests. El plan pide: secretos nunca en
  respuestas, roundtrip cifrado, cambio de modo, test_connection, toggle y ejecución crean `AutomationRun`, doble
  undo → 409, permisos, aislamiento y, en el frontend, formulario desde el schema y undo con confirmación.
- **Hora de los horarios**: `schedule.text` y `next_run_at` usan `CELERY_TIMEZONE` (America/Bogota), que hoy es la
  zona de todas las propiedades. Beat también programa en esa zona. Una propiedad en otra zona vería la hora de
  Bogotá.
- **Duración de «Ejecutar ahora»**: se estima con la mediana de las últimas 5 corridas en esa propiedad. La primera
  vez siempre corre en el request.
- **Probar conexión en modo real llama al proveedor de verdad.** Con llaves falsas de Wompi o Channex la prueba
  queda «Error de conexión» con el mensaje del proveedor, sin secretos. Sin internet falla igual.
- **`saas_billing` y las automatizaciones de plataforma no aparecen aquí**: son del super-admin (C11).
- **Deshacer solo existe para las acciones con handler registrado** (hoy 3). El resto se ve en el registro con
  «Esta acción no se puede deshacer».
- **Validación visual propia**: la hice con un Chrome headless propio, con perfil y puerto separados; no usé el
  navegador compartido. Consola sin errores en las cuatro páginas, a 1440 px y 375 px, claro y oscuro, sin scroll
  horizontal. Recorrí los flujos «Ejecutar ahora», resolver desde la campana y la lista, y deshacer con
  DangerConfirm. Falta la validación del orquestador en Chrome.

## Cómo probarlo en la UI

Usa `http://localhost:5173` con `owner@casaaurora.co` / `housetel123` (Hotel Casa Aurora). En otra pestaña o
ventana privada ten a mano `recepcion@casaaurora.co` y `contabilidad@casaaurora.co`, con la misma clave.

1. **Campana del topbar** (a la izquierda del botón de idioma).
   - Qué ver: el número de alertas abiertas. En la BD actual son 3 (2 «Llegada sin garantía» y el «Resumen del
     día»); tras el seed completo habrá más.
   - Clic en la campana: se abre un popover con las más graves, con icono de gravedad y hace cuánto.
   - El título de cada alerta lleva a su objeto (p. ej. la reserva).
   - ✓ resuelve la alerta: toast «Alerta resuelta» y el contador baja.
   - «Ver todas las alertas» lleva a `/app/alerts`.
2. **Hoy (`/app`)**: en «Más de tu hotel», el primer widget es «Alertas», con los conteos Críticas / Advertencias /
   Informativas y las 4 más graves con enlace. Si no hay ninguna, muestra «Todo en orden: no hay alertas abiertas».
3. **Alertas (`/app/alerts`)**.
   - Pestañas «Abiertas (n)» y «Resueltas».
   - Filtro de gravedad con conteo por chip, y buscador.
   - Cada tarjeta muestra una barra lateral del color de la gravedad, su tipo, el mensaje, «Ver dónde» y «Resolver».
   - «Seleccionar todas» → «Resolver seleccionadas (n)» → toast «n alertas resueltas».
   - En «Resueltas»: «Resuelta por Valentina Rojas · hace …», o «Se resolvió sola» cuando la cerró una
     automatización.
4. **Integraciones (`/app/settings/integrations`)**.
   - Banner «7 de 9 integraciones en modo simulado», con una placa por integración y su leyenda Real / Simulado.
   - Tarjetas: Pagos, Channex, iCal, DIAN, TRA, SIRE, WhatsApp, Email e IA. Cada una tiene su icono, la descripción,
     la píldora de estado, el interruptor **Real | Simulado**, «Probar conexión» y «Configurar».
   - «Probar conexión» en Pagos → toast «Conexión correcta: OK» y «Probada hace unos segundos».
   - Clic en **Real** de «Pagos en línea» → se abre la hoja con el formulario de Wompi, generado desde
     `CONFIG_FIELDS`:
     - «Ambiente», con Sandbox preseleccionado;
     - «Llave pública»;
     - «Llave privada», «Secreto de integridad» y «Secreto de eventos», enmascarados con el aviso «Por seguridad, los
       secretos nunca se muestran»;
     - la caja «URL de eventos (webhook)» con botón de copiar;
     - el aviso amarillo del modo real.
   - «Guardar y activar modo real» sin llenar nada → «Completa los campos obligatorios: Llave pública, Llave
     privada, …».
   - Llena `pub_test_demo` y `prv_test_demo` → guardar → toast «Integración «Pagos en línea» guardada». La tarjeta
     queda en Real con «Proveedor: Wompi…».
   - Reabre «Configurar»: la llave privada muestra «Guardado ✓ · escribe para reemplazarlo» y el enlace «Quitar».
     El valor nunca vuelve al navegador.
   - Para volver: clic en **Simulado** de la tarjeta → toast «“Pagos en línea” funciona ahora en modo simulado».
   - Opcional: en Configurar, «Quitar» los secretos y borra la llave pública para dejarlo limpio.
   - WhatsApp → Configurar → Real: muestra los campos de Meta y la URL del webhook de WhatsApp.
5. **Automatizaciones (`/app/settings/automations`)**.
   - Arriba: «Próxima: Auditoría nocturna a las 02:00», la próxima tarea diaria.
   - Las automatizaciones están agrupadas por módulo: Recepción, Reservas, Limpieza, Finanzas, Mensajería, Canales,
     Legal, Revenue e IA.
   - Cada fila tiene:
     - el interruptor de activa;
     - la descripción;
     - el **riel de 24 h** en hora del hotel: noche sombreada, marcas de cada ejecución, banda continua si corre cada
       pocos minutos y línea punteada en la hora actual;
     - el horario legible y «Próxima: HH:MM»;
     - la última ejecución con su badge, hace cuánto y si fue Manual o Programada;
     - puntos con las últimas 10 ejecuciones;
     - los botones «Ejecutar ahora», «Historial» y «Parámetros» (este solo si la automatización tiene parámetros).
   - «Ejecutar ahora» en «Conciliación de inventario» → toast «“Conciliación de inventario”: 0 noches creadas, 0
     corregidas» y la fila muestra «Correcta · hace unos segundos · Manual».
   - «Historial» → hoja con cada corrida (estado, fecha, duración, quién la pidió) y «Detalles técnicos» en JSON.
   - «Parámetros» en «Asignación automática de habitaciones» → «Días hacia adelante» (por defecto 1) → cámbialo a 2
     → guardar → badge «Ajustada». «Restaurar valores por defecto» lo devuelve.
   - Pausar con el interruptor → toast «… pausada», la fila se atenúa y el riel queda gris.
   - Flujo 13 del spec: «Ejecutar ahora» en «Auditoría nocturna». Cierra los días de negocio ya terminados (si la
     fecha de negocio está atrasada frente al calendario del hotel), y la fecha del topbar avanza. Si está al día, el
     resultado sale «Omitida». Ojo: modifica datos del demo, porque publica noches y marca no-shows.
6. **Registro de auditoría (`/app/settings/audit`)**.
   - Arriba a la derecha, el total de eventos. Hay filtros de Módulo, Origen y Persona (con conteos), Fechas (con
     atajos), «Solo reversibles» y búsqueda. Todo queda en la URL.
   - La línea de tiempo se agrupa por día (Hoy, Ayer…). Cada evento muestra la hora, un avatar de la persona o un
     icono (automatización, IA, canal, sistema), el resumen, quién lo hizo, la acción y el módulo. Según el caso
     lleva el badge «Toda la organización», «Deshecha por … · hace …», el enlace «Ir al objeto» y «Deshacer».
   - Clic en un resumen → hoja con Cuándo / Quién / Origen / Acción / Objeto y la tabla **Antes / Después**. Para
     una edición de tarifas muestra «Cambios por fecha».
   - **Deshacer un movimiento de habitación** (flujo 13):
     1. Mueve una reserva futura de habitación, desde el calendario o desde la reserva con «Asignar habitación».
     2. En el registro, o en la pestaña Historial de la reserva, aparece «Asignó la habitación X a HT-…» con
        «Deshacer».
     3. Pulsa «Deshacer» y escribe **DESHACER** → «Deshacer» → toast «Acción deshecha». La estadía vuelve a la
        habitación anterior y aparece el evento «Deshizo: …». El original queda tachado con «Deshecha por…».
   - Deshacer una asignación vieja cuando hay una más nueva del mismo objeto → el diálogo muestra «Hay un cambio más
     reciente sobre este mismo objeto: deshaz primero ese cambio».
   - La grilla de tarifas (`/app/rates`): tras una edición, su botón «Deshacer» ahora funciona, porque usa estos
     endpoints.
7. **Pestaña «Historial» de una reserva**: en `/app/reservations/<id>?tab=control-history`, por ejemplo HT-J65SZS
   (en la BD actual tiene un movimiento y su deshacer). Muestra solo los eventos de esa reserva: estadías, folio,
   cargos, pagos, check-in online, facturas… «Abrir en el registro de auditoría» lleva al registro filtrado con el
   chip «Solo esta reserva».
8. **Permisos**.
   - `recepcion@casaaurora.co` ve la campana y `/app/alerts`, pero no Integraciones, Automatizaciones ni Registro en
     Configuración. La API le responde 403.
   - `contabilidad@casaaurora.co` ve el registro sin botones «Deshacer»; en el detalle dice «Necesitas el permiso
     “Deshacer acciones auditadas”…».
   - `owner@grupoandino.co` no ve nada de Casa Aurora: la API responde 404.
9. **Idioma, tema y móvil**: EN completo (Integrations / Automations / Audit log / Alerts), modo oscuro y vista de
   375 px sin scroll horizontal. En móvil las filas de automatizaciones se apilan y el riel queda debajo del
   nombre.
