# P5 — Importador (migración desde otro PMS) — integration notes

Estado (2026-09-28, modo MVP): **backend y frontend completos y verificados de punta a punta** por API (proxy de
Vite con cookie + CSRF) y en un Chrome headless propio (perfil y puerto propios, nunca el navegador compartido), a
1440 px y a 375 px, en español y en inglés. Sin tests nuevos ni suites (modo MVP), sin dependencias nuevas, sin
commits y sin tocar `.env`.

Esta sesión retomó el backend de un intento anterior de P5, que había quedado sin frontend y sin notas. Lo revisé,
corrí sus flujos dentro de transacciones revertidas y lo completé. Cambios sobre lo heredado:
- `GET templates/{kind}/?format=xlsx|csv` respondía **404**. DRF interpreta `?format=` como sufijo de renderer. La
  vista ahora fija la negociación en JSON, igual que `reports`.
- El detalle del job leía todas las filas en cada consulta (hasta 10.000) para calcular los valores distintos de
  categoría y plan. Ahora solo lo hace mientras el mapeo se puede editar, porque la UI consulta el detalle cada
  segundo durante una ejecución.
- Nuevo `outcome_counts` en el detalle: las filas por resultado final, en vivo, con las revertidas aparte. Alimenta
  la barra de resultado.
- Los serializers pasaron a `ImportUploadSerializer`, `ImportConfigureSerializer` e `ImportConfirmSerializer`. El
  componente `Confirm` chocaba con el de guests en OpenAPI; `spectacular --validate` vuelve a 0 warnings.
- Los scripts de verificación sueltos (`tests/_flow_check*.py`, `_seed_check.py`) salieron del repo. `ruff check` y
  `ruff format --check` quedan limpios en `apps/imports`.

---

## Qué hace

Un **job** es un archivo subido (CSV o XLSX) de un tipo: `reservations`, `guests` y, opcionalmente, `room_types` o
`rooms`. El flujo:

1. **Subir.** Se lee el archivo, se detectan los títulos y se sugiere el mapeo. El job queda `uploaded`.
2. **Mapear.** Se guarda el mapeo de columnas, luego los valores (categorías y planes del archivo → objetos de
   Housetel) y las opciones. Cada `PATCH` vuelve a validar todas las filas y deja el job `validated`.
3. **Simular (dry-run).** Pasa cada reserva por los mismos servicios que la importación real dentro de una
   transacción que se revierte. Así se ve la disponibilidad real sin guardar nada.
4. **Importar.** Corre en Celery con progreso: una transacción por reserva (todas sus habitaciones) o por fila. El
   job pasa a `completed`, o a `failed` si se detiene; en ese caso se puede reanudar y no repite lo ya hecho.
5. **Revertir** (solo reservas). Cancela sin penalidad las reservas del job que nadie tocó después y anula su pago
   importado. El job queda `reverted`.

Estados del job: `uploaded → validated → queued/running → completed | failed | reverted`. La fase en curso está en
`phase` (`dry_run` | `run` | `revert`).

Estados de fila:
- `status` (revisión): `valid`, `warning`, `error` o `skip`.
- `dry_outcome`: `create`, `update`, `skip` o `fail`.
- `outcome`: `created`, `updated`, `skipped`, `failed` o `reverted`.

Cada mensaje se guarda en los dos idiomas (`{code, es, en}`), así que la UI y el reporte CSV salen en el idioma que
se pida.

**Idempotencia.** `ImportedRecord` guarda la clave `(propiedad, tipo, sistema de origen, id externo)` y el objeto
que se creó. El sistema de origen es el slug del nombre que da el usuario ("Cloudbeds", "Excel de recepción"…).
Reimportar el mismo archivo del mismo sistema actualiza (`on_existing=update`, por defecto) o salta
(`on_existing=skip`); nunca duplica. Sin número de reserva, la clave es una huella de huésped + fechas + categoría
(`fp-…`). Para huéspedes sin id, la clave es documento → email → teléfono + nombre.

### Reservas (el caso principal)

Se importan las **futuras** y las **en casa**:
- **Se omiten** (`skip`) las canceladas, los no-shows, las finalizadas y las que ya terminaron.
- Una llegada que ya pasó **sin estado** se importa como en casa (con advertencia). **Con estado** "confirmada", se
  omite.
- «No confirmada» se importa como **tentativa sin vencimiento** (`hold_minutes=0`).

Si una reserva ya importada llega cancelada en un archivo nuevo, se **cancela en Housetel** sin penalidad y se anulan
sus pagos importados.

Servicios de contrato que usa, en este orden:
1. `guests.services.upsert_guest` para el titular.
2. `bookings.services.reservations.create_reservation` con `ReservationRequest(source="import",
   enforce_restrictions=False, allow_overbooking=False, hold_minutes=0, status=confirmed|tentative)`:
   - trae N `StayRequest`: varias filas con el mismo número, o varias categorías en una fila de Cloudbeds;
   - asigna `room_id`/`bed_id` si viene el número de habitación (y la cama);
   - `nightly_rates` reproduce el total del archivo; si «los montos incluyen impuestos», quita el IVA de
     alojamiento del total, salvo a extranjeros no residentes.
3. `check_in(stay, force=True)` para las en casa: la habitación del archivo, o una libre de la categoría.
4. `finance.services.record_payment(folio, method="other", reference="Saldo importado", actor=None)` por lo pagado.
   Lo pagado se toma de la columna, o se calcula como total − saldo pendiente.

**Nada se sobrevende.** Un `AvailabilityError` es un error de fila. En el dry-run, un libro mayor de lo que tomaron
las filas anteriores del mismo archivo detecta también los choques internos («las filas anteriores del archivo
ocupan la última unidad»), que una transacción revertida no ve.

**Importación silenciosa.** Guests y reservas corren dentro de `core.signals.seeding()`: los receivers con
`is_seeding()` no hacen nada por fila. No hay correos de confirmación, ni TRA, ni facturas, ni tareas, ni un push
ARI por reserva. Al final se emite **un solo** `inventory_changed` que cubre las categorías y fechas afectadas, y los
canales reciben la disponibilidad nueva. Todo queda en la auditoría (`imports.job_completed` y los eventos de cada
servicio).

### Categorías y habitaciones (opcionales)

- **Categorías.** `inventory.services.provision_room_type` crea la categoría con sus números de habitación y, en
  dormitorios, las camas por habitación; `save_room_type` y `bulk_create_rooms` actualizan una existente. Con
  «precio base», `rates.services.provision.provision_rates` la agrega a los planes activos.
- **Habitaciones.** `save_room` (vía `RoomSerializer`) y `create_beds` para dormitorios.

### Preset «Export de Cloudbeds»

Investigado en el centro de ayuda de Cloudbeds:
- El export de reservas (Reservas → Exportar) sale en **.xlsx**. Un asistente deja elegir las columnas.
- Trae columnas separadas de adultos y niños.
- Incluye número de reserva, número de terceros (OTA), nombre, email, teléfono, fechas de llegada y salida, noches,
  tipo y número de habitación, plan, fuente, estado, total, depósito y saldo pendiente.

Qué reconoce el preset:
- **Títulos en inglés y español** de esas columnas y del export de huéspedes: First Name, Last Name, Email, Phone,
  Gender, Date of Birth, Country, City, Document Type, Document Number…
- **Estados**: Confirmed, Not Confirmed, Canceled, Checked In, Checked Out y No Show.
- **Fechas** mes/día o día/mes, con autodetección.
- **Varias habitaciones en una fila** (`Standard, Superior`): se reparten huéspedes y total.

Además, el preset genérico reconoce los títulos habituales en ES/EN y las plantillas de Housetel. Los títulos
exactos del preset no se probaron contra un export real de un hotel: probarlos con el archivo del hotel piloto
(ver Limitaciones).

Fuentes:
- [Reservations Management: Filtering and Flexible Exports](https://myfrontdesk.cloudbeds.com/hc/en-us/articles/43663431474715-Reservations-Management-Filtering-and-Flexible-Exports)
- [Export the exact number of guests per booking](https://myfrontdesk.cloudbeds.com/hc/en-us/articles/115000831634-Export-the-exact-number-of-guests-per-booking)
- [(New) Reservations Page — Everything you need to know](https://myfrontdesk.cloudbeds.com/hc/en-us/articles/28409627448091--New-Reservations-Page-Pilot-Everything-you-need-to-know)

---

## API implementada

Toda la API es staff: `/api/v1/imports/…`, con sesión, CSRF en las escrituras y `X-Property-Id`. **Todos los
endpoints piden `imports.run`**: dueño y gerente lo tienen; recepción y contabilidad no. Los errores siguen el
formato `{detail, code, fields?}`.

| Método y path | Qué |
|---|---|
| `GET catalog/` | Tipos, campos de cada tipo (`code`, `type`, `required`, `group`, `value_mapping`), `one_of`, presets, opciones y límites |
| `GET jobs/?page=&page_size=&kind=&status=` | Historial, lo más nuevo primero (paginado `{count, next, previous, results}`) |
| `POST jobs/` (multipart) | `kind`, `preset` (`generic` o `cloudbeds`), `file`, `source_label?`, `sheet?` → **201** con el detalle y el mapeo sugerido |
| `GET jobs/{id}/` | Detalle (abajo) |
| `PATCH jobs/{id}/` | `{mapping?, value_map?, options?, source_label?}` → guarda y **valida todas las filas** → detalle. Con columnas obligatorias sin asignar: **400** `mapping_incomplete` + `missing` + `job` (el mapeo sí se guardó) |
| `DELETE jobs/{id}/` | Descarta un job que nunca se ejecutó (`uploaded` o `validated`) → 204. Otros estados → 409 `invalid_job_state` |
| `GET jobs/{id}/rows/` | Filas paginadas. Filtros repetibles `status`, `dry_outcome` y `outcome`; `issues=1`; `q` (número de fila, id o lo creado) |
| `POST jobs/{id}/dry-run/` | Encola la simulación → **202** con el detalle (`queued`) |
| `POST jobs/{id}/run/` `{confirm: true}` | Encola la importación → 202. Sin `confirm` → 400 `confirmation_required`. Desde `failed` o un `running` detenido, **reanuda** |
| `POST jobs/{id}/revert/` `{confirm: true}` | Encola la reversión (solo reservas `completed` o `failed`) → 202 |
| `GET jobs/{id}/revert-preview/` | `{revertible, in_house, activity, not_active, missing, total}` |
| `GET jobs/{id}/report/?lang=es|en&only=issues` | CSV `;` UTF-8 con BOM (Excel). Una línea por fila con su revisión, simulación, resultado y reversión, seguida de las columnas originales |
| `GET templates/{kind}/?lang=es|en&format=csv|xlsx&example=1&preset=generic|cloudbeds` | Plantilla vacía con los títulos de Housetel, o **ejemplo** construido con las categorías, habitaciones, planes y fecha de negocio de la propiedad, con filas que muestran advertencias, omisiones y errores |

Estados en conflicto → 409 `invalid_job_state`, por ejemplo simular sin revisar, importar dos veces o revertir
huéspedes. Sin filas listas → 409 `nothing_to_import`. Sin reservas creadas → 409 `nothing_to_revert`. Archivo
ilegible → 400 con `code`: `invalid_file`, `invalid_xlsx`, `unsupported_format` (`.xls` 97-2003), `empty_file`,
`no_rows`, `too_many_rows` (> 10.000), `too_many_columns` (> 120), `file_too_large` (> 15 MB) o `invalid_encoding`.

### Ejemplos

`POST jobs/` con `kind=reservations`, `preset=generic`, `source_label=Excel de recepción` y un CSV
`Reserva;Nombre;Llegada;Noches` → 201:

```json
{"id": "b43aeb1d-…", "status": "uploaded", "source_system": "excel-de-recepcion", "source_label": "Excel de recepción",
 "total_rows": 1, "mapping": {"external_id": "Reserva", "checkin": "Llegada", "nights": "Noches", "full_name": "Nombre"},
 "missing_required": ["room_type"], "…": "…"}
```

`PATCH` con ese mapeo (falta la categoría) → 400:

```json
{"detail": "Faltan columnas obligatorias por asignar", "code": "mapping_incomplete", "missing": ["room_type"],
 "fields": {"mapping": ["room_type"]}, "job": {"…detalle…": "…"}}
```

Detalle del job (campos principales):

```json
{
  "id": "…", "kind": "reservations", "preset": "cloudbeds", "source_label": "Cloudbeds", "source_system": "cloudbeds",
  "status": "validated", "phase": "", "stale": false, "filename": "reservas.xlsx", "file_format": "xlsx",
  "sheet_name": "Datos", "total_rows": 8,
  "counts": {"valid": 5, "warning": 1, "error": 1, "skip": 2},
  "progress": {"done": 0, "total": 5},
  "headers": ["Reservation Number", "Name", "Check in Date", "…"],
  "samples": {"Reservation Number": ["R-5001", "R-5002"]},
  "preview": [{"number": 2, "raw": {"…": "…"}}],
  "mapping": {"external_id": "Reservation Number", "checkin": "Check in Date", "room_type": "Room Type"},
  "suggested_mapping": {"…": "…"}, "missing_required": [], "fields": [{"code": "checkin", "type": "date", "required": true, "group": "stay", "value_mapping": ""}],
  "one_of": [["full_name", "first_name"], ["checkout", "nights"]],
  "value_map": {"room_type": {"Suite Presidencial": "<uuid>"}},
  "values": {"room_type": [{"value": "Standard", "count": 6, "suggested": "<uuid>", "selected": "<uuid>"}], "rate_plan": []},
  "room_types": [{"id": "…", "code": "DBL", "name": {"es": "Estándar", "en": "Standard"}, "kind": "private", "is_active": true, "max_adults": 2, "max_children": 1, "max_occupancy": 3}],
  "rate_plans": [{"id": "…", "code": "FLEX", "name": {"es": "Tarifa flexible", "en": "Flexible rate"}, "kind": "base", "room_type_ids": ["…"]}],
  "options": {"date_format": "auto", "amounts_include_tax": true, "on_existing": "update", "default_rate_plan": "", "date_format_detected": "mdy", "date_format_ambiguous": false},
  "dry_run_at": "2026-09-28T12:34:02Z", "dry_run_summary": {"create": 5, "update": 0, "skip": 2, "fail": 1},
  "summary": {"created": 5, "updated": 0, "skipped": 2, "failed": 1, "total": 8, "start": "2026-09-26", "end": "2027-01-23", "room_type_ids": ["…"]},
  "outcome_counts": {"created": 5, "skipped": 2, "failed": 1},
  "revert_summary": {"reverted": 4, "not_reverted": 1, "reasons": {"revert_in_house": 1}},
  "can_edit": true, "can_delete": true, "can_revert": false, "ready_rows": 6,
  "created_by": {"id": "…", "email": "owner@casaaurora.co", "name": "Valentina Rojas"}, "data_purged": false
}
```

Fila:

```json
{"id": "…", "number": 10, "raw": {"Categoría": "Suite Presidencial", "…": "…"}, "external_id": "R-5008", "group_key": "R-5008",
 "status": "error",
 "issues": [{"level": "error", "code": "unmapped_room_type", "field": "room_type",
             "es": "Categoría sin asignar: «Suite Presidencial»", "en": "Unassigned category: “Suite Presidencial”"}],
 "data": {"stage": "future", "checkin": "2027-01-31", "checkout": "2027-02-03", "stays": [], "guest": {"first_name": "Valeria", "…": "…"}},
 "dry_outcome": "fail", "dry_message": {"code": "unmapped_room_type", "es": "…", "en": "…"},
 "outcome": "failed", "outcome_message": {"…": "…"},
 "target_type": "bookings.reservation", "target_id": null, "target_label": "", "revert": null, "processed_at": "…"}
```

Opciones:
- `date_format`: `auto` | `dmy` | `mdy` | `ymd`.
- `amounts_include_tax`: bool (por defecto `true`, como el «Grand Total» de Cloudbeds).
- `on_existing`: `update` | `skip`.
- `default_rate_plan`: uuid, o `""` para usar el primer plan base activo.

---

## Contratos implementados / consumidos

**Implementados:** ninguno nuevo para otras apps. El paquete `apps.imports` es autónomo:
- `services`: `create_job`, `configure`, `start`, `revert_preview` y `delete_job`;
- `engine.process(job_id, mode)`, que usan la tarea, el hilo de desarrollo y el comando;
- comando `manage.py imports_process <job_id> [--mode dry_run|run|revert]`, para soporte o sin worker.

**Consumidos:**
- **guests:** `upsert_guest`, `update_guest`, `document_owner`, `surviving_guest`.
- **bookings:** `create_reservation` (con `source="import"`, que ya existe en `Reservation.Source`),
  `check_in(force=True)`, `modify_stay(reprice=False)`, `assign_room`, `update_reservation`,
  `cancel_reservation(waive_fee=True)`, `pricing.split_amount/lodging_tax/tax_exempt` y `availability`.
- **finance:** `get_or_create_folio`, `record_payment`, `void_payment` (anula el «Saldo importado» al revertir o
  al cancelar desde el origen).
- **inventory:** `provision_room_type`, `save_room_type`, `bulk_create_rooms`, `save_room`, `create_beds`,
  `RoomTypeSerializer`/`RoomSerializer`/`validated`, `numbering.parse_room_numbers/duplicates_in/infer_floor` y
  `sanitize_code`.
- **rates:** `provision.provision_rates`.
- **core:** `audit.record`, `signals.seeding/send_on_commit/inventory_changed`, `automation.register`,
  `PropertyScopedAPIView`.

## Señales emitidas / escuchadas

- **Emite:** `inventory_changed` una vez al final de cada importación o reversión de reservas, desde
  `max(inicio, fecha de negocio)` hasta el fin, para las categorías afectadas (`origin` de bookings).
- **Escucha** (`receivers.py`, con `if is_seeding(): return`):
  - `guests.guest_anonymized` → borra las celdas (`raw`, `data`, `issues`) de las filas que trajeron a ese huésped
    (Habeas Data);
  - `guests.guests_merged` → los `ImportedRecord` del duplicado pasan al principal.

## Automatizaciones registradas

| Código | Alcance | Horario | Qué hace |
|---|---|---|---|
| `imports.purge_data` | plataforma | 04:45 diario | Borra las celdas de los jobs terminados hace más de `retention_days` (30) y conserva el resultado. Elimina los jobs subidos y nunca ejecutados tras `abandoned_days` (14) |

**Tarea Celery:** `imports.process_job(job_id, mode)`.
- En producción, siempre por Celery.
- En desarrollo (`DEBUG`), si ningún worker registró la tarea (el worker actual arrancó antes que esta app) o el
  broker falla, el job corre en un hilo del proceso web. Así la UI funciona sin reiniciar nada.
- Un job en cola que nadie tomó en 2 min, o en proceso sin latido en 5 min, queda `stale` y se puede relanzar: la
  importación continúa donde quedó.

## Proveedores de integración registrados

Ninguno.

## Seed (`apps/imports/seed.py`)

Casa Aurora queda con una importación terminada en su historial: `huespedes-cloudbeds.csv`, el export de huéspedes
de Cloudbeds de hace 3 días. Pasa por el importador real:
- 7 huéspedes nuevos, uno de ellos con email inválido (se importa sin email);
- 2 filas que coinciden por email con huéspedes existentes («se completaron sus datos»);
- 1 sin nombre (error).

Es idempotente (se salta si el job ya existe) y tarda 0,7 s. Lo probé dentro de `seeding()` y una transacción
revertida: la segunda corrida no crea nada y la BD queda en 0 jobs. **Requiere `"imports"` en `SEED_ORDER`** (ver
Cambios requeridos).

## Extensiones de frontend exportadas

- `features/imports/nav.ts`: «Importar datos», sección `settings`, orden 145, permiso `imports.run`, con descripción
  para el índice de Configuración.
- `features/imports/routes.tsx`: `settings/import` (inicio, pasos 1 y 2, e historial) y `settings/import/:jobId`
  (pasos 3 a 6; la pantalla sigue el estado del job; `?step=columns|values|review` guarda el lugar mientras el mapeo
  se puede editar).
- `features/imports/commands.ts`: ⌘K «Importar datos desde otro sistema».
- `features/imports/locales/{es,en}.json`: namespace `imports`, completo en los dos idiomas.

Diseño:
- La pieza propia es **el libro de filas** (`RowLedger`): una tira que muestra cómo se reparte el archivo en
  revisión (listas, advertencias, errores, omitidas), en simulación (se crearían, actualizarían, omitirían,
  fallarían) y en el resultado (creadas, actualizadas, omitidas, con error, revertidas). Sus totales filtran la
  lista de filas.
- El resto usa los componentes del sistema: `Select`, `ConfirmDialog`, `DangerConfirmDialog` (revertir pide
  escribir REVERTIR o ROLLBACK), `Badge`, los tokens de estado y `.num`/`.eyebrow`.
- En el mapeo, cada campo muestra muestras de la columna elegida con aspecto de celda. Los datos sin asignar se
  ocultan tras «Ver N datos más sin asignar».
- En celular, las acciones de cada paso quedan en una barra fija abajo.

## Dependencias nuevas (pip/npm) y por qué

Ninguna. `openpyxl` y `phonenumbers` (la lista de países ES/EN/PT/FR/DE/IT) ya estaban.

## Cambios requeridos en archivos compartidos u otras apps (para P-INT)

1. **`backend/apps/core/seed.py`** (P1): agregar `"imports"` al final de `SEED_ORDER`, después de `"control"`.
   Necesita los huéspedes de Casa Aurora.
2. **Reiniciar worker y beat** tras el seed. El worker actual no conoce la tarea `imports.process_job`; mientras
   tanto, desarrollo usa el hilo del proceso web. Beat tampoco programa `imports.purge_data`, y su «Ejecutar ahora»
   en Automatizaciones corre en el worker.
3. **`frontend/src/features/control/locales/{es,en}.json`** (P6):
   - `apps.imports`: «Importación de datos» / «Data import». Hoy el filtro del registro de auditoría y la tarjeta
     de automatizaciones muestran «Imports».
   - `actionLabels["imports.job_completed"]`: «Importó datos» / «Imported data».
   - `actionLabels["imports.job_reverted"]`: «Revirtió una importación» / «Rolled back an import».
4. **Opcionales:**
   - `make smoke` (`backend/scripts/smoke_proxy.py`): un paso con plantilla de ejemplo → `POST jobs/` → `PATCH`
     del mapeo → `dry-run` → `run` → `revert`. Mi script equivalente es la sección «Cómo repetir».
   - `endpoints_sweep.py`: agregar `imports/catalog/` y `imports/jobs/`.
   - `route-smoke.mjs`: agregar `/app/settings/import`.
   - `saas` (getting-started): un ítem «Importa tus datos» → `/app/settings/import`.

## Limitaciones conocidas / pendientes

**Alcance de lo que se importa:**
- No se importan historia (estadías finalizadas), no-shows ni cancelaciones antiguas. Solo reservas futuras y en
  casa, como pide el plan.
- No se importan cargos ni folios detallados: solo lo pagado, como un pago «Saldo importado».
- No se importa la facturación a empresa (P4) ni los grupos o cupos (P3). Varias filas con el mismo número forman
  una reserva de varias habitaciones, sin `ReservationGroup`.

**Al reimportar una reserva ya importada:**
- Una sola estadía: se aplican los cambios de fechas, categoría, plan y ocupación con `modify_stay(reprice=False)`.
  Las noches nuevas se cotizan con las tarifas de Housetel, así que el total puede diferir del archivo; queda un
  aviso «El total quedó en … (el archivo dice …)».
- Varias estadías: los cambios de habitaciones no se aplican (aviso). Se aplican los datos libres (notas, ETA,
  solicitudes) y los pagos nuevos.
- Si el archivo dice que se pagó menos que lo ya importado, no se anula nada; queda un aviso.

**Reversión:**
- Es solo para reservas. No se revierten huéspedes, categorías ni habitaciones.
- No revierte:
  - las reservas en casa;
  - las que tienen actividad posterior: otros pagos, cargos o cambios auditados de personas, huéspedes, IA, API o
    canales;
  - las que ya no están activas.

**Huéspedes:** `upsert_guest` busca por documento y luego por email. Sin ninguno de los dos, siempre crea uno nuevo:
no hay deduplicación por nombre.

**Cloudbeds:** los títulos del preset salen de la documentación pública, no de un archivo real. Probar con el export
del hotel piloto y, si algún título no se reconoce, se asigna a mano en el paso Mapear. Los alias están en
`apps/imports/catalog.py`.

**Técnicas:**
- **Hilo de desarrollo:** si otro cambio recarga runserver, el hilo muere. El job queda `stale` a los 5 min y se
  relanza desde la UI. En producción corre en Celery.
- **Límites:** 15 MB, 10.000 filas y 120 columnas. La validación corre dentro del `PATCH` (síncrona): con 10.000
  filas tarda unos segundos. Un XLSX de 15 MB puede acercarse al timeout de gunicorn.
- **Hojas y formatos:** en un XLSX con varias hojas se toma la primera con datos. La API acepta `sheet=`, pero la UI
  no ofrece elegir hoja. Los `.xls` (97-2003) no se leen: hay que guardarlos como .xlsx o .csv.
- **Habeas Data:** las celdas del archivo viven en la BD (JSON) hasta 30 días después de terminar, o hasta que se
  anonimiza al huésped. El archivo original no se guarda.

**Tests:** no se escribieron (modo MVP). Candidatos para la fase de tests:
- parsers de `normalize.py` (fechas, montos, países, estados);
- `suggest_mapping` por preset;
- validación de reservas (capacidad, en casa, grupos);
- idempotencia `update`/`skip`;
- dry-run con choques dentro del archivo;
- reversión con actividad posterior;
- reanudar un `failed`.

## Datos de prueba que dejé en la BD de desarrollo

Todo en **Andino Medellín** (`owner@grupoandino.co`). Casa Aurora quedó sin jobs.
- Dos jobs **revertidos**: `ejemplo-reservations.csv` («Prueba P5») y `reservas-pms-anterior.csv` (Cloudbeds).
  Dejaron 8 reservas **canceladas** («Importación revertida (…)», pagos importados anulados), entre ellas las de
  «Camila Restrepo Uribe», «Daniel Walker», «Grupo Andes Tours» y «Lukas Becker» para ene-2027.
- **1 reserva en casa**: «Andrea Gómez Salazar», hab. 310, 26–30 sep, pagado $761.600 como «Saldo importado». La
  reversión no toca las reservas en casa.
- Los huéspedes de esas filas (emails `@example.com`).

`seed_demo --reset` (P-INT) lo limpia todo.

---

## Cómo probarlo en la UI

Entra a `http://localhost:5173` con `owner@casaaurora.co` / `housetel123`. Para una importación **real con
reversión**, mejor usa `owner@grupoandino.co` → **Andino Medellín** en el selector: el archivo de ejemplo trae una
reserva «en casa» que la reversión no deshace.

1. **Llegar**
   - Configuración → **Importar datos**, o ⌘K «Importar datos desde otro sistema».
   - Recepción no ve el ítem: si entra a la URL, ve «No tienes permiso para importar datos».
   - Arriba aparece el asistente de 6 pasos: Tipo · Archivo · Mapear · Revisar · Importar · Resultado.
2. **Tipo y archivo** (`/app/settings/import`)
   - Elige **Reservas** (Categorías y Habitaciones dicen «Opcional») y el origen: **Export de Cloudbeds** muestra
     cómo exportar desde Cloudbeds; **Excel o CSV** pide el nombre del sistema anterior.
   - **Plantillas y ejemplo** → «Archivo de ejemplo con tus categorías» descarga
     `housetel-ejemplo-reservas.xlsx`, con reservas de la propiedad alrededor de la fecha de negocio. Con Cloudbeds
     aparece también «Ejemplo con el formato de Cloudbeds», que trae una reserva de 2 habitaciones en una fila.
   - Arrastra el archivo o usa **Elegir archivo**.
   - Un `.xls` o un archivo de más de 15 MB da un error claro sin subir nada.
3. **Mapear · columnas**
   - «Reconocimos las 23 columnas del archivo…» (o «Reconocimos 20 de 23…»). Cada dato muestra la columna elegida, el chip **Detectada** y muestras de la
     columna con aspecto de celda.
   - «Ver N datos más sin asignar» muestra los demás.
   - Asignar una columna ya usada la mueve («ya en «Nombre»»).
   - Quitar **Llegada** y pulsar **Continuar** → «Falta asignar: Llegada». Restáurala con «Volver a la detección
     automática».
4. **Mapear · valores y opciones**
   - «Categorías del archivo»: Estándar y Superior (o Ejecutiva en Andino) dicen «Asignada automáticamente».
     **Suite Presidencial** queda «Sin asignar», en ámbar, con el aviso «1 valor sin asignar: sus filas quedarán con
     error».
   - «Planes tarifarios del archivo»: Tarifa flexible → FLEX.
   - «Cómo leer el archivo»: plan por defecto, formato de fechas («Automático · detectamos día/mes/año»), «Los
     montos incluyen impuestos», «Si ya se importó antes» (Actualizar/Omitir) y sistema de origen.
   - **Revisar filas**.
5. **Revisar**
   - El **libro de filas** «Revisión, fila por fila» tiene la barra y los totales Listas / Con advertencias / Con
     errores / Se omiten.
   - Tocar un total filtra la lista; tocarlo otra vez la muestra completa.
   - Filas que vale la pena mirar:
     - R-5004: 2 filas, «Reserva de 2 habitaciones (filas …)»;
     - R-5005: «No confirmada: se importa como tentativa sin vencimiento»;
     - R-5006 (cancelada) y R-5007 (finalizada): se omiten;
     - R-5008: «Categoría sin asignar: «Suite Presidencial»».
   - El aviso rojo tiene el botón «Revisar asignación». Hay buscador por fila, número o código.
   - **Reporte** → «Solo filas con errores o advertencias» descarga un CSV (`;`) que se abre en Excel con las
     columnas originales. «Errores y advertencias, en inglés» lo baja en inglés.
6. **Simular**
   - **Simular importación**: progreso en vivo («Simulando la importación de reservas…», n / total). Vuelve a
     Revisar con la lente **Simulación** («Simulación del 28 sep, …»): Se crearían / Se actualizarían / Se
     omitirían / Fallarían, y en cada fila «Reserva HT-… creada» (códigos de prueba: no se guardó nada).
   - La lente «Revisión» vuelve a los resultados de la revisión.
7. **Importar**
   - **Importar N filas** → diálogo «¿Importar N filas?», que explica la fuente «Importación», el «Saldo importado»,
     que no hay correos y que se puede revertir → **Importar**.
   - Barra de progreso, y luego **Resultado**: Creadas / Actualizadas / Omitidas / Con error.
   - Cada fila creada enlaza a su reserva (`HT-…`). R-5003 dice «creada y en casa (hab.)».
   - «Siguiente paso: Ver reservas · Ver calendario».
   - El aviso «1 fila no se importó. Descarga el reporte de errores, corrígela en tu archivo y súbelo de nuevo: lo
     que ya se importó se omite».
8. **Verificar en el PMS**
   - En Reservas y Calendario aparecen las reservas con fuente «Importación» y notas «Importada desde … (reserva
     R-5001) · origen: Booking.com».
   - El folio tiene el pago «Otro · Saldo importado»; la en casa figura en Hoy → En casa.
   - Sin correos nuevos en Mailpit.
9. **Reimportar el mismo archivo**
   - Sube el mismo archivo con el mismo origen. La revisión dice «Ya se importó antes: se actualizará», y la
     simulación da «Se actualizaría», u «Omitida · Sin cambios» si nada cambió. No se duplica nada.
   - Si en el archivo cambias una fecha de salida, la importación la actualiza.
10. **Revertir**
    - En Resultado, **Revertir importación**. El diálogo dice «Se cancelarán N reservas» y lista las que no: «1 está
      en casa: no se revierte».
    - Escribe **REVERTIR** → **Revertir**. Aparece el banner «Revertida el … por …: 4 reservas canceladas · 1 no se
      revirtió (1 en casa)».
    - La barra muestra **Revertidas** rayado y las filas dicen «Reserva cancelada por la reversión».
    - Registro de auditoría: «Revirtió la importación …».
11. **Historial**
    - En `/app/settings/import`, «Importaciones anteriores»: cada job con su estado, su tira de resultados y
      «5 creadas · 0 actualizadas · 1 con error».
    - Casa Aurora trae del seed «huespedes-cloudbeds.csv», completada hace 3 días: 7 creadas, 2 actualizadas y 1
      con error. Ábrela para ver el resultado de huéspedes.
12. **Otros tipos**
    - **Huéspedes** con «Ejemplo con el formato de Cloudbeds» (Casa Aurora): un email inválido se importa sin email,
      «Sin tipo de documento: se asume CC», y una fila sin nombre queda con error.
    - **Categorías** con el ejemplo: SFAM (privada, 2 habitaciones 9xx) y DMIX (dormitorio de 6 camas). La
      simulación dice «Se crearía»; al importar se agregan a los planes con su precio base.
13. **Idioma y celular**
    - En inglés, todo sale traducido, también los mensajes de cada fila y el reporte.
    - A 375 px no hay scroll horizontal y las acciones quedan en la barra fija de abajo.

## Cómo repetir (verificación de esta sesión)

```bash
cd /home/breyner/Documents/new_project
docker compose exec -T backend python manage.py check                       # sin problemas
docker compose exec -T backend python manage.py makemigrations imports --check --dry-run   # No changes
docker compose exec -T backend sh -c "ruff check apps/imports && ruff format --check apps/imports"
docker compose exec -T backend python manage.py spectacular --validate --file /tmp/schema.yml   # 0 warnings
cd frontend && npx tsc -p tsconfig.app.json --noEmit && npx eslint --max-warnings 0 src/features/imports
```

Flujo por API: login con cookie + CSRF como `backend/scripts/smoke_proxy.py`.
1. `GET catalog/`, las plantillas (es/en × csv/xlsx) y el ejemplo.
2. `POST jobs/` (multipart) → `PATCH` mapeo → `PATCH` valores y opciones.
3. `GET rows/` y `report/`.
4. `run/` sin `confirm` → 400.
5. `dry-run/` → sondeo hasta `validated`.
6. `run/` → sondeo hasta `completed`.
7. `revert-preview/` → `revert/` → `reverted`.

Casi todos respondieron en menos de 200 ms. Las excepciones: la primera plantilla xlsx (~400 ms) y el primer
`dry-run/` (~1,2 s, porque en desarrollo consulta si hay worker).

Archivos: `backend/apps/imports/**` y `frontend/src/features/imports/**` (nuevos: `api.ts`, `nav.ts`,
`routes.tsx`, `commands.ts`, `lib/{fields,steps}.ts`, `pages/{ImportPage,ImportJobPage}.tsx`,
`components/{ImportStepper,KindPicker,TemplatesMenu,FileDrop,JobHistory,MapColumnsView,MapValuesView,ReviewView,RowsList,RowLedger,ProgressView,ResultView,RevertButton,ReportMenu,badges}.tsx`
y `locales/{es,en}.json`), más esta nota.
