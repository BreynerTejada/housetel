# C7 — Legal Colombia (DIAN, SIRE, TRA) — integration notes

Estado: **MVP funcional de punta a punta en modo simulado** (backend + API + frontend + automatizaciones + seed).
Esta sesión retomó un intento anterior que había dejado el backend avanzado y sin frontend: revisé y conservé el
backend (con algunos arreglos), escribí el `seed.py`, un comando `seed_compliance`, tres extensiones de la API para
la UI y todo el frontend. Modo MVP (decisión del usuario): **no se escribieron ni corrieron tests** en esta sesión;
los tests heredados de `apps/compliance/tests/` no se tocaron (pueden estar desactualizados; se reescriben después
de la validación en Chrome).

Owner paths: `backend/apps/compliance/**`, `frontend/src/features/compliance/**` y esta nota. No se tocó nada fuera.

---

## Cómo probarlo en la UI

**Datos.** El seed de C7 corre dentro de `seed_demo` (orden `SEED_ORDER`). Si el demo ya está cargado sin datos
legales (la BD de desarrollo quedó así: probé el seed dentro de una transacción revertida y limpié los datos de mis
pruebas por API), basta con:

```bash
docker compose exec -T backend python manage.py seed_compliance     # ~40 s, idempotente
```

Deja por propiedad: resolución DIAN de pruebas `SETT 1–5000`, facturas simuladas de las salidas de los últimos 30
días (Casa Aurora ≈129, Andino MDE ≈204, Hostel ≈233), 1 nota crédito con su factura reexpedida, 2 salidas recientes
**sin factura** (demo de Pendientes), SIRE `[hoy−30, hoy−8]` con acuse y `[hoy−7, hoy−1]` **por reportar**, TRA de
los huéspedes en casa y de las llegadas de los últimos 3 días (algunos con datos faltantes).

Usuario: `owner@casaaurora.co` / `housetel123` (también `recepcion@casaaurora.co` para permisos reducidos).

| # | Dónde | Pasos | Resultado esperado |
|---|---|---|---|
| 1 | `/app/compliance` (sidebar **Legal → DIAN, SIRE y TRA**) | Abrir | Tres tarjetas: **DIAN** (total facturado del mes, nº de facturas y exentas, "2 pendientes por facturar"), **SIRE** (tira de 30 barras: ~23 verdes "reportado", 7 arena "por subir"), **TRA** (huéspedes registrados, "N registros por resolver"). Cada tarjeta lleva a su pestaña |
| 2 | Pestaña **Facturas** | Filtrar por estado / tipo / fechas; buscar "SETT1" o un código de reserva | Tabla paginada en servidor; notas crédito en negativo; badges "Exenta" (extranjeros) y "Simulado". KPIs del mes (facturado, válidas, IVA, exentas) |
| 3 | Clic en una factura | Hoja lateral | El documento dibujado como papel (borde perforado, sello "ACEPTADA DIAN"), adquiriente, conceptos, IVA o "Exenta" + nota *Art. 481 lit. d) E.T.*, CUFE en grupos de 8 con "Copiar", QR, "Consultar en la DIAN", autorización de numeración |
| 4 | En la hoja | **Ver PDF** / **Descargar XML** | Se abre el PDF en otra pestaña (A4 con marca de agua "SIMULADA · SIN VALIDEZ FISCAL", QR, CUFE); baja el XML UBL 2.1 |
| 5 | En la hoja de una factura aceptada | **Anular con nota crédito** → motivo (≥ 5 letras) → escribir el número de la factura → **Emitir nota crédito** | Toast "Nota crédito NCx emitida"; la factura queda **Anulada**; sus cargos quedan libres (ver paso 9) |
| 6 | Pestaña **Pendientes** | Revisar | Facturas: 2 salidas "Sin factura" con **Emitir** (toast "SETTnnn: Aceptada"); TRA: huéspedes con datos faltantes (**Completar datos** → perfil del huésped) y, en el hostel, camas sin huéspedes asociados (**Agregar huéspedes** → pestaña Huéspedes de la reserva); SIRE: el archivo de los últimos 7 días con **Descargar TXT** y **Marcar como reportado** (en simulado genera acuse `SIRE-XXXXXXXX`); extranjeros con datos faltantes. A la derecha, la salud de la resolución |
| 7 | Pestaña **SIRE** | Elegir periodo → **Generar archivo** | Toast con movimientos/faltantes y se abre el reporte: movimientos (Entrada/Salida), faltantes con enlace al huésped; descarga TXT (TAB, 12 columnas, CRLF). La tira de 30 días se actualiza |
| 8 | Pestaña **TRA** | Filtrar por estado (`?status=pending` desde alertas) o fecha de llegada | Registros por huésped (Principal/Acompañante), número `TRA-XXXXXXXX`, faltantes, **Reintentar** |
| 9 | Reserva → pestaña **Legal** (`/app/reservations/<id>?tab=compliance-legal`) | Abrir una reserva en casa o una con factura anulada | Avisos (consumidor final, TRA pendiente, SIRE incompleto), facturas con PDF, "N cargos sin facturar" + **Emitir factura** → diálogo con vista previa (adquiriente, líneas, IVA/exento, total, "Se numerará como SETTnnn") → resultado con **Ver PDF**; TRA por huésped (o **Registrar** si la estadía no tiene); movimientos SIRE |
| 10 | Reserva → **Más acciones → Emitir factura** | Menú de acciones de C1 | El mismo panel de emisión dentro del diálogo de C1 |
| 11 | `/app` (Hoy) | Check-out de una salida del día (C1) | La reserva queda con factura emitida y validada sola (receiver de `stay_checked_out`), visible en su pestaña Legal y en Facturas. Check-in de una llegada → TRA registrada sola |
| 12 | `/app` (Hoy) | Zona de widgets | Tarjeta **Pendientes legales** (facturas por emitir, TRA por resolver, SIRE) con enlace a Pendientes |
| 13 | `/app/settings/compliance` | Revisar / editar | Tarjeta de la resolución (próximo número, números restantes, vigencia, ambiente), historial (con la de notas crédito `NC`), **Nueva resolución** (formulario con validación), emisor (razón social, NIT, RNT → enlace al perfil), modos de integración (Simulado + enlace a Integraciones), reglas DIAN (emitir al check-out, consumidor final, inicio en Housetel, nota al pie), SIRE (código, DIVIPOLA, 13 columnas, códigos de documento y países) y TRA; **Guardar cambios** solo se activa con cambios |
| 14 | Recepción (`recepcion@casaaurora.co`) | Mismas páginas | Puede emitir facturas, generar SIRE y registrar TRA; **no** ve "Anular con nota crédito" ni la configuración |
| 15 | Automatizaciones (C12 `/app/settings/automations`) | Ejecutar "Emitir facturas electrónicas pendientes" | Emite las 2 salidas pendientes (lookback 3 días) |
| 16 | Portal del huésped (C5) `/g/<token>` de una reserva que salió | Sección de facturas (si C5 la muestra) | Lista y PDF vía la API pública de abajo |
| 17 | Cualquiera | EN, tema oscuro, 375 px | Todo traducido; sin desborde horizontal en `/app/compliance` y `/app/settings/compliance` (las tablas se desplazan dentro de su tarjeta) |

---

## API implementada

Staff: `/api/v1/compliance/` (sesión + `X-Property-Id`; filtrado por `request.property`; errores `{detail, code}`).

| Método y path | Permiso | Descripción |
|---|---|---|
| `GET/POST resolutions/` · `GET/PATCH/DELETE resolutions/{id}/` | view (lectura) / settings | Resoluciones DIAN. Crear/activar una desactiva la activa del mismo `document_kind`. Con documentos numerados no cambian `document_kind`, `prefix`, `from_number` ni `to_number < current_number` (400) |
| `GET invoices/?status=&kind=&mode=&reservation=&start=&end=&q=&page=&page_size=` | view | Lista paginada (`q`: número, código de reserva, nombre o documento del cliente; fechas de emisión inclusivas) |
| `GET invoices/{id}/` | view | Detalle (cliente, líneas, CUFE, QR, notas crédito, resolución) |
| `GET invoices/summary/?start=&end=` | view | **(nuevo)** Totales del periodo (por defecto el mes de la fecha de negocio) |
| `POST invoices/issue/` `{reservation_id}` o `{folio_id}` | invoice | Emite los cargos no anulados y no facturados → 201 detalle. 409 `nothing_to_invoice`, 409 `no_active_resolution` / `resolution_expired` / `resolution_exhausted` / `resolution_not_valid_yet` (`numbering_error`), 400 `invalid_total` |
| `POST invoices/{id}/retry/` | invoice | Reenvía borrador/error/rechazada (toma los datos actuales del cliente) o consulta una `issued`; 409 `invalid_state` |
| `POST invoices/{id}/credit-note/` `{reason, confirm: true}` | void_invoice | Nota crédito total (concepto 2) → 201 detalle de la nota; sin `confirm` → 400 `confirmation_required`; sin motivo → 400 `reason_required`; 409 `invalid_state` / `credit_note_exists` |
| `GET invoices/{id}/pdf/` · `GET invoices/{id}/xml/` (`?download=1`) | view | Archivos (se generan y guardan en el primer acceso si faltan). `Cache-Control: private, no-store` |
| `GET sire/?status=` · `GET sire/{id}/` | view | Reportes SIRE (detalle con `records` y `missing`) |
| `POST sire/generate/` `{start, end}` | sire | Genera (reemplaza un reporte del mismo periodo aún no reportado) → 201; periodo inválido o > 93 días → 400 `invalid_period` |
| `GET sire/{id}/download/` | sire | TXT |
| `POST sire/{id}/mark-submitted/` `{ack_code?}` | sire | Simulado → `acknowledged` con acuse generado; real → `submitted` (acuse opcional, se puede agregar luego); 409 `invalid_state` |
| `GET tra/?status=&reservation=&date=&q=` | view | Registros TRA (paginado) |
| `POST tra/register/` `{stay_id}` | tra | Registra a los huéspedes de una estadía con check-in → 201 lista; sin check-in → 400 `invalid_state` |
| `POST tra/{id}/retry/` | tra | Reintenta (y primero al principal si el acompañante lo espera); registrado → 409 `invalid_state` |
| `GET/PATCH settings/` | view / settings | Configuración + `effective`, `defaults`, `integrations` (modo por tipo), `supplier` (datos del emisor y `missing`) |
| `GET pending/` · `GET pending/?summary=1` | view | Pendientes (máx. 50 ítems por grupo, más antiguos primero) · solo conteos (widget) |
| `GET reservations/{id}/` | view | Pestaña Legal: facturas, `uninvoiced`, `can_issue`, TRA, SIRE, avisos **+ (nuevo) `resolution`, `preview`, `tra_candidates`** |

Público (`/api/v1/public/compliance/`, sin sesión, throttle 60/min, contrato C7 → C5 del plan §C):
`GET portal/<token>/invoices/` → `[{id, number, kind, status, total, currency, issued_at, pdf_url}]` (solo documentos
`issued/accepted` y facturas `cancelled`); `GET portal/<token>/invoices/<id>/pdf/` (`?download=1`). Token inválido → 404.

### Ejemplos (respuestas reales, recortadas)

`POST invoices/issue/` `{"reservation_id": "1ca39826-…"}` → 201:

```json
{"id": "1e9a3d2c-…", "kind": "invoice", "status": "accepted", "number": "SETT1", "prefix": "SETT",
 "issue_date": "2026-09-27", "issued_at": "2026-09-27T15:57:02-05:00", "currency": "COP",
 "subtotal": "368000.00", "tax_total": "0.00", "total": "368000.00",
 "customer_name": "Sergio Navarro", "customer_document": "PA ESZL5821747",
 "reservation_id": "1ca39826-…", "reservation_code": "HT-2WQ7YZ", "related_invoice_id": null, "related_number": "",
 "mode": "simulated", "environment": "test", "attempts": 1, "error_message": "", "has_pdf": true, "is_exempt": true,
 "customer": {"guest_id": "…", "name": "Sergio Navarro", "document_type": "PA", "dian_document_code": "41",
              "document_number": "ESZL5821747", "dv": "", "legal_organization": "person", "is_final_consumer": false,
              "is_foreign_non_resident": true, "email": "…", "phone": "…", "address": "", "city": "…", "country": "ES",
              "nationality": "ES"},
 "lines": [{"code": "ALOJ-DBL", "kind": "room", "description": "Alojamiento Estándar · 1 noche", "quantity": 1,
            "unit_price": "368000.00", "net": "368000.00", "tax_code": "01", "tax_status": "exempt",
            "tax_rate": "0.00", "tax_amount": "0.00", "total": "368000.00", "charge_ids": ["…"]}],
 "exempt_note": "Exento de IVA — Art. 481 lit. d) E.T., servicios hoteleros a no residentes",
 "cufe": "e1298d30d685…(96 hex)", "qr_data": "NumFac=SETT1\nFecFac=2026-09-27\n…\nQRCode=https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey=…",
 "validation_url": "https://catalogo-vpfe-hab.dian.gov.co/document/searchqr?documentkey=…",
 "provider": "simulated", "provider_ref": "SIM-SETT1", "reason": "", "credit_notes": [],
 "resolution": {"id": "…", "prefix": "SETT", "resolution_number": "18760000001", "from_number": 1, "to_number": 5000,
                "valid_from": "2025-09-27", "valid_to": "2028-08-27"},
 "folio_id": "…", "charges_count": 1, "last_attempt_at": "…"}
```

`tax_status`: `taxed` (IVA), `exempt` (impuesto referenciado con 0: extranjero no residente) o `excluded` (sin
impuesto, p. ej. penalidades). Totales = exactamente los del folio (Σ neto + Σ IVA de los cargos cubiertos).

`GET invoices/summary/` → `{"start": "2026-09-01", "end": "2026-09-27", "invoices": 128, "total": "58214300.00",
"subtotal": "…", "tax_total": "…", "exempt": {"count": 41, "total": "…"}, "credit_notes": 1, "failed": 0,
"waiting_dian": 0}` (solo facturas `issued/accepted` en los totales).

`GET reservations/{id}/` (pestaña Legal) → `{reservation: {id, code, status, checkout_date, booker: {id, full_name,
document_type, document_number, nationality, is_foreign_non_resident}}, invoices: [InvoiceSummary], uninvoiced:
{count, total}, can_issue, has_accepted_invoice, tra: [TraRegistration], tra_candidates: [{stay_id, status, room,
checkin_date, guests: [nombres]}], sire: [{id, report_id, report_status, guest_id, guest_name, movement, movement_date,
complete, missing_fields}], warnings: ["final_consumer"|"invoice_failed"|"tra_pending"|"sire_missing"], resolution:
ResolutionHealth, preview: {customer, lines, subtotal, tax_total, total, exempt_note, charges_count} | null}`.

`ResolutionHealth` (en `pending.resolution` y en la pestaña Legal): `{status: ok|warning|critical|missing, message,
resolution_id, prefix, from_number, to_number, next_number, remaining, used_percent, valid_to, days_left,
environment}` (warning = ≥ 90 % usado o < 30 días de vigencia).

`GET pending/` → `{resolution, invoices: {count, items: [{status: not_issued|error|rejected|draft, invoice_id, number,
kind, reservation_id, reservation_code, guest_name, checkout_date, total, error}]}, tra: {count, items: [{status:
not_registered|pending|error, registration_id, reservation_id, reservation_code, stay_id, guest_id, guest_name, room,
checkin_date, missing_fields, error}]}, sire: {count, reports: [{report_id, period_start, period_end, records_count,
missing_count, generated_at}], missing: [SireMissing], unreported_days: ["YYYY-MM-DD"]}, counts: {invoices, tra, sire,
total}}`. `missing_fields: ["occupants"]` = estadía de cama sin huéspedes asociados. `?summary=1` →
`{counts, resolution_status}`.

`POST sire/generate/` → detalle `{id, period_start, period_end, status, records_count, missing_count, mode,
generated_at, generated_by_name, submitted_at, submitted_by_name, ack_code, file_name, missing: [{guest_id, guest_name,
reservation_id, reservation_code, stay_id, movement: "E"|"S", movement_date, fields: [...], record}], records: [{id,
guest_id, guest_name, reservation_id, reservation_code, movement, movement_date, complete, missing_fields, document,
nationality}]}`. Línea real del TXT (TAB): `130458  13001  3  MXRT9352008  493  HERNANDEZ  EMILIANO  E  20/09/2026
493  13001  01/03/1993`.

`TraRegistration`: `{id, status, tra_number, guest: {id, full_name, document_type, document_number, nationality},
reservation_id, reservation_code, stay_id, room, checkin_date, checkout_date, is_main, parent_id, mode,
missing_fields, error, attempts, registered_at, last_attempt_at, payload, created_at}`.

## Contratos implementados / consumidos

- **Implementa (plan §C, C7 → C5)** los endpoints públicos del portal (arriba).
- **Servicios propios** (otras apps pueden llamarlos): `apps.compliance.services.invoices.issue_invoice(reservation |
  folio, *, actor=None, source="user", issued_at=None, render=True)`, `retry_invoice`, `issue_credit_note(invoice, *,
  reason, confirm, actor=None, source="user", issued_at=None, render=True)`, `ensure_pdf`, `ensure_xml`,
  `uninvoiced_by_reservation(property, ids)`; `services.sire.generate_sire(property, start, end, *, actor=None)`,
  `mark_submitted`; `services.tra.register_stay(stay, *, actor=None)`, `retry_registration`;
  `services.pending.pending_summary(property)`, `reservation_legal(reservation)`.
- **Consume (solo lectura por ORM)**: `bookings.Reservation/Stay` (+ ocupantes), `finance.Folio/Charge/Payment`,
  `guests.Guest`, `guestportal.OnlineCheckin.data["travel"]` (import protegido: motivo, procedencia, destino por
  huésped). No escribe en modelos ajenos. Core: `integrations`, `alerts`, `audit`, `automation`, `tokens`, `signals`.

## Señales emitidas / escuchadas

- Escucha `stay_checked_out` → si todas las estadías salieron y `auto_issue_invoices` → emite la factura de la
  reserva (respeta `go_live_date`; errores de numeración levantan alerta y no rompen el check-out).
- Escucha `stay_checked_in` → registra la TRA de cada huésped de la estadía (si `tra_auto_register`; nunca rompe el
  check-in).
- Ambos receivers: `if is_seeding(): return` (el seed siembra lo derivado explícitamente).
- No emite señales. `guest_anonymized` / `guests_merged` (B3) **no** se escuchan a propósito: facturas, SIRE y TRA
  son registros legales con retención obligatoria (la fusión genérica de B3 reapunta sus FKs).
- Alertas (`source="compliance"`): `compliance:resolution:<kind>` (crítica si no se puede numerar; warning ≥ 90 % o
  < 30 días), `compliance:invoice:<id>` (error/rechazo), `compliance:sire:missing`, `compliance:sire:unsubmitted`,
  `compliance:tra:missing`, `compliance:tra:error`. Todas enlazan a `/app/compliance?tab=…` o a la configuración.
- Auditoría: `compliance.invoice_issued`, `credit_note_issued`, `invoice_failed`, `resolution_created/updated/deleted`,
  `settings_updated`, `sire_generated`, `sire_submitted`, `tra_registered`, `tra_failed`.

## Automatizaciones registradas

| Código | Horario | Qué hace |
|---|---|---|
| `compliance.issue_pending_invoices` | cada 15 min | Reintenta borradores/errores (máx. 8 intentos), consulta a la DIAN las `issued` y, con emisión automática, factura las salidas de los últimos `lookback_days` (param, 3) sin factura. Sin resolución usable se detiene al primer error (1 error + alerta, no uno por reserva) |
| `compliance.sire_daily_file` | diario 08:00 | Archivo SIRE del día anterior, salvo que un reporte ya cubra ese día; `skipped` si no hubo movimientos de extranjeros |
| `compliance.tra_retry` | cada 15 min | Reenvía registros TRA pendientes/con error de la última semana |

Verificadas con `automation.run` manual (en transacción revertida): Casa Aurora `success` (11 facturas emitidas),
Andino MDE sin resolución → `partial` con 1 error y la alerta de resolución.

## Proveedores de integración registrados

| kind | simulated | real |
|---|---|---|
| `einvoice` | `SimulatedEInvoiceProvider`: CUFE/CUDE = SHA-384 del anexo técnico v1.9 (determinístico), QR con la URL de validación DIAN de habilitación, `accepted` al instante | `FactusProvider` (`code="factus"`): OAuth2 password grant `POST /oauth/token` (token en caché), `POST /v2/bills/validate`, `POST /v2/credit-notes/validate`, `GET /v2/bills/{número}`, `GET …/download-xml`, `GET /v2/numbering-ranges` (probar conexión). `CONFIG_FIELDS`: environment (sandbox/production), client_id, client_secret\*, username, password\*, numbering_range_id, credit_note_range_id, send_email |
| `sire` | `SimulatedSireProvider`: al marcar como reportado devuelve acuse `SIRE-XXXXXXXX` | `PortalSireProvider`: Migración Colombia no tiene API; el TXT se sube a mano en el portal y se marca como reportado (acuse opcional) |
| `tra` | `SimulatedTraProvider`: `TRA-XXXXXXXX` | `MincitTraProvider`: `POST <base_url>/one/` (principal) y `/two/` (acompañantes con `padre`), header `Authorization: token <token del RNT>`; `CONFIG_FIELDS`: base_url (def. `https://pms.mincit.gov.co`), token\*, establishment_id, main_path, companion_path |

\* secreto (nunca vuelve al frontend; C12 lo gestiona).

**Verificado en la documentación (WebFetch/WebSearch, 2026-09-27):**
- **Factus** (<https://developers.factus.com.co/facturas/crear-y-validar/>): `POST /v2/bills/validate` sobre
  `https://api-sandbox.factus.com.co`, headers `Authorization: Bearer`, `Accept: application/json`; cuerpo con
  `reference_code`, `payment_details[{payment_form, payment_method_code, amount}]`, `customer{identification_document_code,
  identification, legal_organization_code, names|company, …}`, `items[{code_reference, name, quantity, price,
  unit_measure_code, standard_code, taxes[{code, rate}]}]`, opcionales `numbering_range_id`, `observation`, `document`,
  `operation_type`; respuesta `data.cufe`, `data.number`, `data.is_validated`, `data.links.qr`. Coincide con el
  mapeo del adaptador (validado → `accepted`, no validado → `issued` y se consulta después; 400/422 → `rejected`;
  409 → documento pendiente en Factus). Token OAuth de 1 h.
- **SIRE**: no hay especificación pública descargable del archivo plano. Las guías de PMS (LobbyPMS, Pxsol)
  confirman el cargue de un TXT en "Alojamiento y hospedaje → Cargar archivo" y los campos procedencia, destino y
  fecha de nacimiento. Se implementó el formato documentado más reciente conocido: TAB, CRLF, sin encabezado, ASCII
  mayúsculas, fechas `dd/mm/aaaa`, columnas `establecimiento · ciudad (DIVIPOLA) · tipo doc · número · nacionalidad ·
  apellidos [· segundo apellido] · nombres · E|S · fecha · procedencia · destino · nacimiento` (12 columnas; 13 con
  el interruptor "segundo apellido"). Códigos configurables por hotel: `SIRE_DOCUMENT_TYPES` (3 pasaporte, 5 cédula
  de extranjería, …) y `SIRE_COUNTRY_CODES` (tabla de países de la DIAN, p. ej. 169 Colombia, 249 EE. UU.).
- **TRA**: el token se pide por RNT en <https://pms.mincit.gov.co/token/> (confirmado); el manual oficial
  (`tramincit.gov.co/…/Manual-TRA-Grupo-1-Alojamientos-con-PMS-29abr2022.pdf`) no respondió (conexión rechazada), por
  eso base URL y rutas son configurables; la guía de Chekin confirma el campo `costo` numérico. Las búsquedas
  muestran también `traapi.mincit.gov.co` como host posible.

## Extensiones de frontend exportadas

- `routes.tsx`: `/app/compliance` (`CompliancePage`, `?tab=invoices|sire|tra|pending`, `?invoice=<id>` abre la hoja
  de una factura, `?report=<id>` la de un reporte SIRE, `?status=pending|error` filtra TRA — los enlaces de las
  alertas usan estos parámetros) y `/app/settings/compliance` (`ComplianceSettingsPage`). `nav.ts` sin cambios.
- `reservation-tabs.tsx`: `{ id: 'compliance-legal', labelKey: 'compliance:legal.tab', order: 50, permission:
  'compliance.view' }` (carga perezosa).
- `reservation-actions.tsx`: `{ id: 'compliance-issue-invoice', labelKey: 'compliance:issue.action', icon: ReceiptText,
  order: 60, permission: 'compliance.invoice' }`. **El componente dibuja solo el contenido** (vista previa + botones
  y llama `close()`): el detalle de reserva de C1 lo envuelve hoy en su propio `Dialog` con el título `labelKey`.
- `widgets.tsx`: `{ id: 'compliance.pending', order: 60, size: 'md', permission: 'compliance.view' }` (Hoy).
- `commands.ts`: "Generar archivo SIRE" y "Ver pendientes legales" (⌘K).
- Reutilizables: `api.ts` (tipos y hooks: `useReservationLegal`, `usePendingCounts`, `useInvoices`, `complianceKeys`,
  `fetchInvoiceFile`…), `hooks.ts` (`useInvoiceFiles`: PDF en pestaña nueva / XML), `components/InvoiceSheet`
  (`<InvoiceSheet invoiceId onOpenChange />`), `components/IssueInvoicePanel` (`<IssueInvoicePanel reservationId
  onClose />`), `components/ResolutionHealth`, `components/SireDayStrip`.
- i18n: namespace `compliance`, ES/EN con paridad de claves (395).

## Seed (`apps/compliance/seed.py`, corre después de finance)

Ver "Cómo probarlo". Por propiedad y a través de los servicios: settings (`go_live_date = hoy − 30`, código SIRE),
resolución `SETT 1–5000` (habilitación, clave técnica de pruebas de la DIAN, vigencia de 3 años desde hoy − 365),
facturas de las salidas de los últimos 30 días fechadas en el check-out y numeradas en ese orden (PDF/XML se generan
en la primera descarga), las 2 salidas más recientes sin factura, 1 nota crédito + reexpedición, 2 reportes SIRE y
TRA de huéspedes en casa y llegadas de los últimos 3 días (fechadas al check-in). Idempotente por bloque (si la
propiedad ya tiene facturas / SIRE / TRA, ese bloque se omite). **~36–49 s** para las 3 propiedades (probado dos
veces dentro de una transacción revertida; la segunda corrida no creó nada). Comando `python manage.py
seed_compliance` para correr solo este seeder sobre un demo ya cargado.

## Dependencias nuevas (pip/npm) y por qué

Ninguna (reportlab, httpx, qrcode.react ya estaban).

## Cambios requeridos en archivos compartidos u otras apps (para C-INT)

1. **`config/settings.py` → `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]`**: `spectacular --validate` avisa
   colisiones de `status`, `kind`, `mode` y "multiple names for DocumentKindEnum". Entradas de C7:
   ```python
   "InvoiceStatusEnum": "apps.compliance.models.Invoice.Status",
   "InvoiceKindEnum": "apps.compliance.models.Invoice.Kind",          # mismo set que InvoiceResolution.DocumentKind
   "SireReportStatusEnum": "apps.compliance.models.SireReport.Status",
   "TraRegistrationStatusEnum": "apps.compliance.models.TraRegistration.Status",
   "IntegrationModeEnum": "apps.compliance.models.IntegrationMode",   # real|simulated, mismo set que core/finance
   ```
2. **C1 `features/frontdesk/pages/ReservationDetailPage.tsx`**: a 375 px la página mide ~529 px de ancho: su `grid`
   raíz no tiene `grid-cols-1`/`min-w-0` y la `TabsList` (7+ pestañas de extensión) impone su ancho mínimo (mismo
   problema que corrigió B3 en sus páginas). Solución: `grid-cols-1` en el contenedor (o `min-w-0` en `<Tabs>`).
3. **Convención de `ReservationAction`**: C1 envuelve el `Component` en su `Dialog`; C5 (`guestportal`) renderiza su
   propio `Dialog` dentro → diálogos anidados. C7 sigue a C1 (solo contenido). Unificar en C-INT.
4. Los tests de A2 que renderizan `/app` (Hoy) pueden necesitar un handler MSW para
   `GET /api/v1/compliance/pending/?summary=1` (el widget legal), como anota B-INT.
5. `backend/media-private/compliance/` guarda PDF/XML/TXT legales (ya ignorado por `.gitignore`).

## Limitaciones conocidas / pendientes

- **Sin tests nuevos** (modo MVP). Los tests heredados en `apps/compliance/tests/` no se corrieron ni se
  actualizaron; hay que revisarlos/reescribirlos en la fase de tests.
- XML: UBL 2.1 con la estructura del anexo técnico pero **sin firma** (en real lo firma Factus y se guarda el suyo).
- SIRE: formato inferido (ver arriba), por eso layout y códigos son configurables. Real = carga manual en el portal.
- TRA real: adaptador según lo público (manual oficial inaccesible); probar con un token real antes de producción.
- Pendientes muestra hasta 50 ítems por grupo; sin emisión masiva desde la UI (la automatización cubre 3 días).
- Un hotel sin `go_live_date` ve como pendientes todas sus salidas históricas: se ajusta con "Inicio en Housetel".
- Emitir antes del check-out factura solo las noches ya publicadas; lo que se cobre después sale en otra factura
  al hacer el check-out.
- Estadías de cama sin ocupantes (hostel) no pueden registrarse en la TRA hasta asociar los huéspedes (C1/C5).

## Verificación (esta sesión, sin tests)

- Backend: `manage.py check` sin problemas; `makemigrations compliance --check --dry-run` → "No changes detected"
  (migraciones 0001/0002 aplicadas); `ruff check` y `ruff format --check` limpios en todo `apps/compliance` excepto
  `tests/` (no tocados).
- API por el proxy de Vite (cookie jar + CSRF, `owner@casaaurora.co`): 77 comprobaciones OK — settings (GET/PATCH,
  validación DIVIPOLA), emitir sin resolución → 409 `no_active_resolution`, crear resolución, vista previa de la
  pestaña Legal = total de la factura, emitir → `accepted` con CUFE de 96 hex, repetir → 409 `nothing_to_invoice`,
  PDF (15 KB, `%PDF`) y XML, búsqueda y filtros, `summary`, nota crédito (sin `confirm` → 400; con → `accepted`,
  original `cancelled`), reexpedición, SIRE (generar, TXT de 12 columnas con código y DIVIPOLA 13001, marcar →
  acuse, repetir → 409), TRA (registrar → `TRA-…`, antes del check-in → 400, reintentar registrado → 409),
  pendientes y resumen del widget, portal público (lista + PDF; token inválido → 404). Permisos: recepción lee y no
  anula ni configura (403), contabilidad lee, limpieza 403, otra organización 404, anónimo 401.
- Receivers verificados en transacción revertida: check-out forzado → factura `accepted` con PDF; check-in → TRA
  registrada. Automatizaciones con `automation.run` (arriba).
- Seed: dos corridas en transacción revertida (36–49 s; idempotente). Los datos y archivos de mis pruebas se
  borraron de la BD de desarrollo al final.
- Frontend: `tsc -p tsconfig.app.json --noEmit` sin errores en `src/features/compliance`; `eslint
  src/features/compliance` limpio; paridad ES/EN verificada. Revisión visual propia con un Chrome headless aislado
  (puerto propio, sin tocar el navegador compartido): `/app/compliance` (tablero, Facturas, Pendientes, SIRE) a
  1440 px claro/oscuro y 375 px, hoja de factura a 1440/375, configuración a 1440/375, pestaña Legal con el diálogo
  de emisión, widget en Hoy: sin desborde horizontal en páginas propias y sin errores de consola propios.
