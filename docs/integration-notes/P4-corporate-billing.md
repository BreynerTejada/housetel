# P4 — Facturación corporativa y cartera — integration notes

Estado: **completo en modo MVP** (backend + API + frontend + seed), sin tests nuevos ni suites corridas (decisión del
usuario). Todo lo del plan P4 está implementado: empresas con NIT/DV validado, facturación de la reserva con reglas de
enrutamiento, folios divididos (huésped + empresa) con transferir y dividir cargos, factura por folio al NIT de la
empresa, cartera con antigüedad y pagos a cuenta, `require_simulations` en la pasarela simulada y el seed.

Owner paths tocados: `backend/apps/corporate/**`, `backend/apps/finance/**`, `backend/apps/compliance/**` (no
`services/sire.py`), `frontend/src/features/corporate/**` (nueva), `frontend/src/features/finance/**`,
`frontend/src/features/compliance/**` y esta nota. Nada fuera de eso. Sin dependencias nuevas; `.env` intacto; sin
commits.

**Lo que P-INT debe hacer sí o sí** está en "Cambios requeridos" (3 cambios de una línea: `SEED_ORDER`,
`with_balance` y, opcional, los scripts de verificación).

---

## Cómo probarlo en la UI

**Datos.** El seed de P4 (`apps/corporate/seed.py`) corre dentro de `seed_demo` cuando P-INT agregue `"corporate"` a
`SEED_ORDER` (ver "Cambios requeridos"). Sobre un demo ya cargado (como la BD de desarrollo de hoy):

```bash
docker compose exec -T backend python manage.py seed_corporate            # ~1–3 s, idempotente
docker compose exec -T backend python manage.py seed_corporate --dry-run  # lo mismo en una transacción revertida
```

Deja en **Hotel Casa Aurora** (usuario `owner@casaaurora.co` / `housetel123`):

| Empresa | Tipo · crédito | Qué tiene |
|---|---|---|
| **Viajes Caribe Mágico S.A.S.** (NIT 900.482.731-8) | Agencia · 30 días · cupo $15 M | Estadía pasada hace ~45 días con el **alojamiento** a la agencia (la huésped pagó los desayunos): factura a su NIT **vencida** (31–60); saldo inicial `FV-2024-0891` de hace 75 días (61–90); estadía **futura** (en 10 días) con **todo** a la agencia y voucher `VCM-2210` (en curso) |
| **Inversiones Portuarias del Caribe S.A.S.** (NIT 901.345.678-2) | Corporativo, gran contribuyente (O-13, O-15, O-23) · 45 días · cupo $40 M | Estadía pasada hace ~12 días (todo, OC-4521) facturada a su NIT (0–30); **huésped en casa** con el alojamiento a la empresa y una **cena de negocios dividida 50/50** (folio dividido); saldo inicial `FE-1187` de hace 118 días (90+) abonado con una transferencia que dejó **$300.000 a favor** |
| **Tecnologías Andinas del Norte Ltda.** (NIT 830.512.946-0) | Corporativo, régimen simple · 30 días · cupo $10 M | Estadía pasada hace ~25 días **pagada** con una transferencia a cuenta (folio cerrado: queda en el historial) |

Los códigos de reserva salen al azar: se encuentran en `/app/companies/<empresa>` → pestaña **Reservas**.

| # | Dónde | Pasos | Resultado esperado |
|---|---|---|---|
| 1 | Sidebar **Operación → Empresas** (`/app/companies`) | Abrir; buscar "portuarias" o "901345"; filtros Tipo, **Con saldo**, **Incluir inactivas** | Lista con avatar, razón social, tipo · nombre comercial · ciudad, NIT con DV, crédito (cupo y plazo o "Sin crédito") y **saldo aquí** con lo vencido en rojo o lo "en curso" |
| 2 | **Nueva empresa** (o ⌘K "Nueva empresa") | Escribir NIT `900.123.456-9` | Debajo: "Para este NIT el dígito de verificación es 8"; al guardar marca el error. Con `900123456` muestra "Dígito de verificación: 900.123.456-8". Responsabilidades O-13…R-99-PN como chips, crédito con cupo (vacío = sin límite) y plazo, contactos repetibles |
| 3 | `/app/companies/<Portuarias>` | Encabezado | Eyebrow "Corporativo · Crédito a 45 días", razón social, NIT, responsable de IVA, chips O-13/O-15/O-23 y el **medidor de cupo** (terracota < 75 %, arena ≥ 75 %, rojo sobre el cupo) |
| 4 | Pestaña **Estado de cuenta** | Revisar | Saldo por cobrar grande, "descontando $300.000 a favor", cifras (facturado pendiente, **vencido**, a favor, en curso), la **cinta de antigüedad** (0–30 / 31–60 / 61–90 / +90, un solo tono que oscurece con la edad; tooltip por tramo) y la tabla de documentos: número de factura (o del saldo inicial), reserva y huésped, fecha, vence, "Vencida hace N días", total, pagado, saldo. Debajo "Estadías en curso" (en casa) y "Pagos a cuenta" con sus aplicaciones |
| 5 | **Registrar pago a cuenta** | Monto $1.000.000, Transferencia, referencia; "A los más antiguos" | Resumen "Se aplica / Queda a favor" en vivo → toast "Pago de $1.000.000 registrado…"; la factura más vieja baja o se salda, la cinta cambia. Con **Elegir documentos** se reparte a mano (también a estadías en curso) y avisa si se pasa del monto |
| 6 | **Aplicar saldo a favor** (aparece si hay saldo a favor y algo por cobrar) | Automático | Se aplican los $300.000 a los documentos más viejos |
| 7 | En un pago: menú ⋯ → **Anular pago** | Escribir el monto + motivo | Sus pagos en los folios se anulan, los folios que saldó se reabren y los documentos vuelven a quedar pendientes |
| 8 | **Agregar saldo inicial** (al pie) | Número `FV-OLD-1`, monto, fecha de hace 100 días | Aparece como documento "Saldo inicial (sistema anterior)" en el tramo +90; no se factura en Housetel |
| 9 | **Exportar** | Descargar | CSV `;` (Excel) con documentos, días, vencido y los tramos |
| 10 | Sidebar **Cartera** (`/app/receivables`, ⌘K "Ver la cartera") | Abrir | Cartera por cobrar total, vencido, a favor, en curso, la cinta de toda la cartera y la tabla por empresa (una columna por tramo). A 375 px: tarjetas con mini-cinta. **Exportar CSV** |
| 11 | Reserva del huésped en casa de Portuarias → pestaña **Facturación** (`?tab=corporate-billing`) | Revisar | "A una empresa" con Portuarias, reglas marcadas (**Alojamiento**), OC-4630; a la derecha **Quién paga qué**: huésped $X, Portuarias $Y "A crédito · pasa a cartera", "Por cobrar antes del check-out" (solo la parte del huésped) y el cupo |
| 12 | Misma pestaña | Marcar **Extras y consumos** (o **Todo**) con "Mover los cargos ya publicados" → **Guardar facturación** | Toast "Facturación guardada · N cargos movidos a su folio"; los desayunos pasan al folio de la empresa y "Por cobrar antes del check-out" baja |
| 13 | Pestaña **Folio** de esa reserva | Revisar | Pestañas **Huésped · Camila** / **Portuarias del Caribe** con el saldo de cada una; el folio de la empresa dice "Saldo de la empresa… Tiene crédito: pasa a su cartera al check-out" y no ofrece "Link de pago"; la cena aparece en ambos folios ($107.100 cada uno) y la original tachada "Dividido en dos cargos" |
| 14 | En un cargo: menú ⋯ → **Mover al folio de… Portuarias** / **Dividir cargo…** | Mover un desayuno; dividir otro cargo en "La mitad" hacia la empresa | Toast "«Desayuno» se movió al folio de Portuarias del Caribe"; en dividir, vista previa "Queda en… / Va a…" y los dos cargos nuevos suman el original. Un cargo ya facturado responde "El cargo está en la factura SETTn: anúlala con una nota crédito para moverlo" |
| 15 | Un pago del huésped: ⋯ → **Mover el pago al folio de…** | Mover un anticipo al folio de la empresa | Útil cuando el huésped pagó un anticipo y luego se facturó a la empresa |
| 16 | Hoy / detalle → **Check-out** de ese huésped | Con la empresa a crédito | El check-out **no se bloquea** por la parte de la empresa; solo pide lo del huésped. Al salir: se emite **una factura por folio** (la del huésped y la de la empresa a su NIT, a crédito con vencimiento) y el folio de la empresa queda abierto → aparece en la cartera |
| 17 | Pestaña **Legal** de una reserva con empresa | Revisar | "Una factura por folio": una fila **Al huésped · …** y otra **A la empresa · …** ("a crédito") con su botón. El diálogo **Emitir factura** tiene el selector **Facturar a** (tarjetas por cliente), el adquiriente con NIT-DV, régimen de IVA, responsabilidades y "Factura a crédito: vence 45 días después"; el PDF muestra "Forma de pago: crédito… vence el dd/mm/aaaa" |
| 18 | Empresa **sin crédito** | En una reserva, facturar a una empresa sin crédito | "Sin crédito · se cobra antes del check-out" y el aviso "…su parte también debe quedar paga antes del check-out": el check-out se bloquea hasta que se pague (en su pestaña de folio) |
| 19 | Permisos | `recepcion@casaaurora.co` | Ve Empresas, Cartera y la pestaña Facturación (solo lectura: controles deshabilitados), no crea empresas ni registra pagos a cuenta (403). `contabilidad@casaaurora.co` puede todo (corporate.*). Limpieza no ve nada |
| 20 | Cualquiera | Inglés, tema oscuro, 375 px | Todo traducido (ES/EN con paridad); la cinta usa el mismo tono con otros pasos en oscuro; sin desborde horizontal |

---

## API implementada

Staff: `/api/v1/corporate/` (sesión + `X-Property-Id`). Empresas por **organización**; estados de cuenta, cartera y
pagos a cuenta por **propiedad activa**. Errores con la forma del core `{detail, code, fields?, ...}`. Dinero siempre
string con 2 decimales.

| Método y path | Permiso | Descripción |
|---|---|---|
| `GET companies/?q=&kind=&active=true\|false&credit=1&with_balance=1&page=&page_size=` | corporate.view | Lista paginada (q: razón social, nombre comercial, email o NIT) con `receivable {balance, overdue, in_progress}` en esta propiedad |
| `POST companies/` · `PATCH companies/{id}/` | corporate.manage | Crear/editar. `nit` con o sin DV (`900.123.456-7`); `dv` se calcula; si viene y no coincide → 400 `fields.dv` "…para el NIT X es Y". NIT único por organización (400) |
| `GET companies/{id}/` | corporate.view | Detalle + `credit` (cupo usado en toda la organización) |
| `DELETE companies/{id}/` | corporate.manage | Solo sin folios, reservas ni pagos; si no → 409 `company_in_use` (desactivar con `is_active=false`) |
| `GET companies/{id}/statement/?as_of=` | corporate.view | Estado de cuenta (abajo) |
| `GET companies/{id}/statement/export/` | corporate.view | CSV `;` UTF-8 con BOM |
| `GET companies/{id}/reservations/` | corporate.view | Reservas facturadas a la empresa (o con un folio suyo) con su saldo y factura |
| `POST companies/{id}/payments/` | corporate.ar | Pago a cuenta `{amount, method: bank_transfer\|cash\|card_terminal\|other, reference?, notes?, received_on?, allocations: [{folio_id, amount}] \| auto_allocate: true}` → 201 estado de cuenta + `payment` |
| `POST companies/{id}/apply-credit/` | corporate.ar | Aplica el saldo a favor `{allocations} \| {auto: true}` → estado de cuenta + `applied` |
| `POST companies/{id}/opening-balance/` | corporate.ar | Saldo inicial (factura anterior a Housetel) `{amount, document_date, reference, description?}` → 201 |
| `POST account-payments/{id}/void/` `{reason, confirm: true}` | corporate.ar | Anula un pago a cuenta (sin `confirm` → 400 `confirmation_required`) |
| `GET/PUT reservations/{reservation_id}/billing/` | view / manage | Facturación de la reserva (abajo) |
| `GET receivables/?as_of=` · `GET receivables/export/` | corporate.view | Cartera de la propiedad por empresa · CSV |

Errores con `code` estable: `invalid_bill_to`, `company_required`, `company_inactive`, `invalid_allocation`,
`folio_not_found`, `duplicate_folio`, `allocation_exceeds_balance` (con `outstanding`),
`allocation_exceeds_payment`, `allocation_exceeds_credit`, `no_credit`, `nothing_to_apply`, `invalid_amount`,
`invalid_method`, `invalid_date`, `reference_required`, `already_voided`, `company_in_use`, `cash_shift_required`
(efectivo sin turno, regla de finanzas), `confirmation_required`, `reason_required`.

### Ejemplos (respuestas reales, recortadas)

`PUT reservations/{id}/billing/` `{"bill_to": "company", "company_id": "7ef7…", "routing": ["lodging"],
"purchase_order": "OC-4521", "notes": "", "move_existing": true}` → 200 (`GET` devuelve lo mismo sin `moved`):

```json
{"reservation": {"id": "c125…", "code": "HT-3WB22N", "status": "confirmed", "checkin_date": "2026-10-30",
                 "checkout_date": "2026-11-05", "booker": {"id": "704d…", "full_name": "Jessica Miller",
                 "document_type": "PA", "document_number": "USKY6974761", "email": "…"}},
 "billing": {"bill_to": "company", "routing": ["lodging"], "purchase_order": "OC-4521", "notes": "",
             "updated_at": "2026-09-28T12:10:50Z", "updated_by": "Valentina Rojas",
             "company": {"id": "7ef7…", "legal_name": "Inversiones Portuarias del Caribe S.A.S.",
                         "trade_name": "Portuarias del Caribe", "kind": "corporate", "nit": "901345678", "dv": "2",
                         "nit_display": "901.345.678-2", "credit_enabled": true, "payment_terms_days": 45,
                         "is_active": true}},
 "folios": [{"id": "2031…", "folio_type": "guest", "status": "open", "company": null,
             "balance": "180000.00", "expected_balance": "180000.00"},
            {"id": "945e…", "folio_type": "company", "status": "open", "company": {"…": "…"},
             "balance": "0.00", "expected_balance": "1774080.00"}],
 "balances": {"total": "1954080.00", "guest": "180000.00", "checkout_due": "180000.00",
              "companies": [{"company": {"…": "…"}, "expected": "1774080.00", "credit": true,
                             "blocks_checkout": false}]},
 "credit": {"enabled": true, "limit": "4000000.00", "used": "6085680.00", "available": "-2085680.00",
            "over_limit": true, "terms_days": 45},
 "routes": ["lodging", "lodging_taxes", "extras", "all"],
 "moved": 0}
```

- `balances.total` = toda la reserva; `guest` = la parte del huésped; `checkout_due` = lo que debe quedar pago antes
  del check-out (= `finance.reservation_balance`: la parte del huésped + la de empresas **sin** crédito);
  `companies[].expected` = folio de la empresa + noches aún no publicadas si el alojamiento va a ella.
- `routing` vacío o con `all` se guarda como `["all"]`; `bill_to: "guest"` borra empresa y reglas.

`GET companies/{id}/statement/`:

```json
{"company": {"…": "…"}, "as_of": "2026-09-28", "currency": "COP",
 "totals": {"balance": "4311600.00", "overdue": "3550000.00", "in_progress": "1774080.00", "unapplied": "0.00",
            "net_balance": "4311600.00", "open_items": 3},
 "aging": {"current": "0.00", "d31_60": "761600.00", "d61_90": "1850000.00", "d90_plus": "1700000.00"},
 "credit": {"enabled": true, "limit": "4000000.00", "used": "6085680.00", "available": "-2085680.00",
            "over_limit": true, "terms_days": 45},
 "items": [{"folio_id": "4f32…", "folio_status": "open", "kind": "opening_balance", "label": "FE-1187",
            "reservation": null, "invoice": null, "document_date": "2026-06-02", "due_date": "2026-07-17",
            "age_days": 118, "overdue_days": 73, "bucket": "d90_plus", "charges_total": "3200000.00",
            "paid": "1500000.00", "balance": "1700000.00", "expected_balance": "1700000.00"},
           {"kind": "reservation", "reservation": {"id": "…", "code": "HT-PM55C9", "status": "checked_out",
            "checkin_date": "…", "checkout_date": "2026-09-16", "guest_name": "Andrés Felipe Morales Rendón"},
            "invoice": {"id": "…", "number": "SETT138", "status": "accepted", "issue_date": "2026-09-16",
                        "total": "1142400.00"},
            "document_date": "2026-09-16", "due_date": "2026-10-31", "age_days": 12, "overdue_days": 0,
            "bucket": "current", "balance": "1142400.00", "…": "…"}],
 "in_progress": [{"kind": "reservation", "reservation": {"code": "HT-3WB22N", "status": "confirmed", "…": "…"},
                  "balance": "0.00", "expected_balance": "1774080.00", "…": "…"}],
 "payments": [{"id": "4cbd…", "amount": "1500000.00", "applied": "1500000.00", "unapplied": "0.00",
               "method": "bank_transfer", "reference": "TRF 88412033", "received_on": "2026-09-28", "notes": "",
               "status": "active", "created_by": "Valentina Rojas", "created_at": "…", "voided_at": null,
               "void_reason": "",
               "allocations": [{"id": "22e7…", "folio_id": "4f32…", "amount": "1500000.00", "label": "FE-1187",
                                "reservation_code": null}]}]}
```

- **Documentos por cobrar** (`items`): folios de empresa con saldo ≠ 0 cuya reserva terminó (salió, cancelada,
  no-show) o sin reserva (saldos iniciales). **En curso** (`in_progress`): reservas no terminadas (saldo esperado,
  con las noches por publicar si el alojamiento es de la empresa).
- **Fecha del documento**: la de la factura a la empresa (la última no anulada del folio); si no hay, el check-out (o
  la cancelación); en saldos iniciales, la fecha del documento. **Vence**: `Invoice.due_date` o fecha + plazo (0 si
  la empresa no tiene crédito). **Tramos** por días desde la fecha del documento: `current` 0–30, `d31_60`,
  `d61_90`, `d90_plus` (91+). **Vencido** = saldo de documentos pasados de su vencimiento.
- `credit.used` = folios de empresa abiertos + noches por publicar de sus estadías en curso − saldo a favor, **en
  toda la organización**; superar el cupo levanta la alerta `company_over_credit` (no bloquea nada).

`GET receivables/` → `{as_of, currency, totals: {balance, overdue, in_progress, unapplied, net_balance, companies},
aging, companies: [{company, balance, overdue, in_progress, unapplied, net_balance, aging, open_items,
oldest_days}]}` (ordenado por vencido y saldo).

`POST companies/{id}/payments/` `{"amount": "2000000", "method": "bank_transfer", "reference": "TRF-P4",
"auto_allocate": true}` → 201 estado de cuenta con `totals.unapplied: "300000.00"` y `payment` (la fila del pago).

### Finanzas (`/api/v1/finance/`, cambios P4)

| Método y path | Permiso | Descripción |
|---|---|---|
| `GET folios/?reservation=` | finance.view | Ahora trae `folio_type` (`guest\|master\|house\|company`), `label`, `company {id, legal_name, trade_name, nit_display, credit_enabled, payment_terms_days}` y `totals.expected_balance` en cada folio de la reserva |
| `GET folios/{id}/` | finance.view | `totals.expected_balance` (lo que debe este folio, noches por publicar incluidas) y `totals.reservation_balance` (lo que bloquea el check-out) |
| `POST folios/{id}/charges/` | finance.collect | El cargo queda **en ese folio** (el staff lo eligió): las reglas de facturación solo aplican a cargos automáticos. Nuevo tipo manual `tax` ("Impuesto o tasa": seguro hotelero, tasa turística) |
| `POST charges/{id}/transfer/` `{to_folio_id, reason?}` | finance.collect | Mueve el cargo a otro folio abierto de la misma reserva (auditoría `finance.charge_transferred`). 400 `same_folio` / `folio_mismatch`, 409 `folio_closed` / `already_voided` / **`charge_invoiced`** (con `invoice`) |
| `POST charges/{id}/split/` `{amount, to_folio_id?, reason?}` | finance.collect | Divide: `amount` (con IVA) va a un cargo nuevo en `to_folio_id` (o el mismo); el resto queda en otro cargo nuevo y el original se anula "Dividido en dos cargos". Neto e IVA proporcionales, suman exacto → 201 `{rest, part}`. 400 `invalid_amount` si `amount` ≤ 0 o ≥ total |
| `POST payments/{id}/transfer/` `{to_folio_id, reason?}` | finance.collect | Mueve un pago aprobado sin reembolsos (p. ej. un anticipo del huésped al folio de la empresa); no mueve aplicaciones de pagos a cuenta (409 `payment_not_movable`) |
| `GET/POST public/finance/sim/intents/<ref>/[decide/]` | pública | Ahora con `core.runtime.require_simulations` (404 cuando las simulaciones están apagadas en producción) |

### Legal (`/api/v1/compliance/`, cambios P4)

| Método y path | Cambio |
|---|---|
| `POST invoices/issue/` `{folio_id}` | Factura el grupo del folio: un folio de empresa solo (al NIT de la empresa), o los folios del lado del huésped juntos |
| `POST invoices/issue/` `{reservation_id}` | Emite **una factura por cliente** con cargos pendientes; responde la primera y `additional_invoices: [{id, number, status}]` |
| `GET reservations/{id}/` | Nuevo `folios: [{folio_id, folio_ids, folio_type: guest\|company, status, company_id, customer, uninvoiced {count, total}, can_issue, preview}]` (el selector "Facturar a"); `preview` sigue siendo el del primer grupo con cargos. El aviso `final_consumer` solo sale si el huésped tiene algo que facturar |
| `GET invoices/` · `GET invoices/{id}/` | Nuevos `due_date` e `is_company`; `customer_document` incluye el DV (`NIT 901345678-2`) |
| `GET public/compliance/portal/<token>/invoices/` (C5) | Ya **no** lista las facturas de folios de empresa: son de la empresa (p. ej. la tarifa neta de una agencia), no del huésped |

Cliente de una factura a empresa (`Invoice.customer`, lo usan el PDF, el XML y Factus): `{company_id, name (razón
social), trade_name, document_type: "NIT", dian_document_code: "31", document_number, dv, legal_organization:
"company", vat_responsible, tax_regime: "48"|"49", tax_responsibilities: ["O-13", …], address, city, country,
email (facturación), phone, payment_form: "credit"|"cash", payment_terms_days}`.

## Contratos implementados / consumidos

**Implementados (plan P4):**

```python
# apps/corporate/services.py
def target_folio(reservation, kind) -> Folio
    # el folio de empresa cuando la reserva se factura a una empresa y `kind` está en sus reglas; si no, el del huésped
```

Otros servicios públicos de `corporate.services`: `set_billing(reservation, *, bill_to, company=None, routing=None,
purchase_order="", notes="", actor=None, move_existing=True) -> (ReservationBilling, moved)`,
`reroute_existing_charges(reservation, *, actor=None) -> int`, `credit_status(company)`, `check_credit(company, *,
property)`, `statement(company, property, *, as_of=None)`, `receivables(property, *, as_of=None)`,
`company_balances(property, companies)`, `company_reservations(company, property)`,
`record_account_payment(company, property, *, amount, method, reference="", notes="", received_on=None,
allocations=None, auto_allocate=False, actor=None)`, `apply_credit(company, property, *, allocations=None,
auto=False, actor=None)`, `void_account_payment(account_payment, *, reason, actor=None, confirm=False)`,
`add_opening_balance(company, property, *, amount, document_date, reference, description="", actor=None)`.
`apps.corporate.routing`: `category_of(kind)`, `routes_kind(billing, kind)`, `billing_of(reservation)`,
`lodging_company(reservation)` (lecturas puras que finanzas importa en perezoso).

**Reglas de enrutamiento** (`ReservationBilling.routing`, solo con `bill_to=company`):

| Categoría | Tipos de cargo |
|---|---|
| `lodging` | `room` (cada noche con **su IVA**: la DIAN exige facturar el impuesto al mismo adquiriente del servicio) y `cancellation_fee` (penalidades y no-shows) |
| `lodging_taxes` | `tax` (impuestos o tasas cargados **aparte**: seguro hotelero, tasa turística municipal) |
| `extras` | `extra`, `fee`, `other` |
| `all` | todo, `adjustment` (descuentos) incluido |

**Finanzas (contratos sin cambio de firma; `test_contracts` sigue igual):**

- `post_charge(folio, …)`: si `folio` es el folio huésped principal de una reserva (sin `stay`), el cargo va a
  `corporate.services.target_folio(reservation, kind)`. `finance.services.explicit_folio()` (context manager) lo
  apaga: la API de cargos del staff lo usa. Lo aprovechan sin tocar nada: noches de la auditoría nocturna
  (`post_room_charges`), penalidades de `cancel_reservation`/no-show, extras del portal (C5), copiloto (C9).
- `reservation_balance(reservation)` = **toda la reserva − la parte de las empresas con crédito** (sus folios +
  las noches por publicar si el alojamiento va a una de ellas). Sin empresas es exactamente la regla anterior.
  Nuevos: `reservation_total_balance` (la regla anterior), `unposted_lodging`, `company_parts` (→ `CompanyPart`
  con `posted`, `unposted`, `expected`, `credit`), `guest_part`, `folio_expected_balance`,
  `get_or_create_company_folio(reservation, company)`, `folio_label`, `transfer_charge`, `split_charge`,
  `transfer_payment`, `reopen_folio`, `close_folio_if_settled`, `departed`.
  Identidad exacta: `reservation_total_balance = Σ saldos de folios + unposted_lodging`.
- `close_settled_folios(reservation)`: ahora cierra por partes — los folios del huésped cuando la parte del huésped
  es 0 y cada folio de empresa cuando la parte de esa empresa es 0 (un folio de empresa con saldo queda abierto: es
  cartera). `close_folio_if_settled(folio)` cierra un folio de empresa al saldarlo con un pago a cuenta.
- **`apps/finance/balances.py::annotate_reservation_balance(queryset)`**: la misma regla en SQL (una consulta). Ver
  "Cambios requeridos" (reemplaza el cuerpo de `bookings…with_balance`).

**Legal:** `issue_invoice(target)` (una factura: folio o primer grupo de la reserva), nuevos
`issue_reservation_invoices(reservation, …) -> list[Invoice]` (una por grupo con pendientes; lo usan el receiver del
check-out, la automatización y el seed de C7) e `issue_for_folio(folio, …)`; `invoice_groups(reservation)`;
`builder.company_customer(company)` y `builder.folio_customer(folio)`; `pending.folio_options(reservation,
settings)`. Los cargos `source="opening_balance"` nunca se facturan.

**Consumidos:** `core.runtime.require_simulations` (P1; import con respaldo no-op mientras no exista),
`core.audit`, `core.alerts`, `bookings` (lectura; `create_reservation`, `check_in`, `check_out`,
`post_room_charges` solo en el seed), `guests.upsert_guest` (seed).

Auditoría nueva: `corporate.company_created/updated/deleted`, `corporate.billing_updated` (con `moved_charges`),
`corporate.account_payment_recorded`, `corporate.account_payment_voided`, `corporate.credit_applied`,
`corporate.opening_balance_added`, `finance.folio_created` (folio de empresa), `finance.charge_transferred`,
`finance.charge_split`, `finance.payment_transferred`, `finance.folio_reopened` (manual).

## Señales emitidas / escuchadas

Ninguna nueva. Las de siempre salen por los servicios de finanzas: `payment_received` por cada aplicación de un pago
a cuenta (es un `Payment` normal) y `folio_closed` al cerrar folios. El receiver de C7 (`stay_checked_out`) ahora
emite una factura por folio; el de B4 cierra por partes. Ningún receiver nuevo.

Alerta nueva: `kind="company_over_credit"` (warning, `dedupe_key=corporate:credit:<company_id>`, `link` al
estado de cuenta, `data {company_id, used, limit}`, `source="corporate"`); se resuelve sola al bajar del cupo.

## Automatizaciones registradas

Ninguna.

## Proveedores de integración registrados

Ninguno nuevo. **Factus** (`FactusProvider`, C7) arma el cliente empresa con `tribute_code` `"01"` (IVA) o `"ZZ"`,
`responsibilities` (lista DIAN) y `trade_name`; y una factura a crédito va con `payment_details[0].payment_form =
"2"` y `due_date` (campos verificados en la documentación de Factus v2 el 28-sep-2026: `tribute_code` por defecto
"ZZ", `responsibilities` por defecto ["R-99-PN"], `due_date` obligatorio con forma de pago 2). El XML UBL lleva
`TaxLevelCode` con las responsabilidades, `TaxScheme` 01/IVA para responsables y `PaymentMeans` 2 +
`PaymentDueDate` a crédito; el PDF muestra régimen, responsabilidades y "Forma de pago: crédito a N días · vence…".

## Extensiones de frontend exportadas

- **Feature nueva `corporate`**:
  - `nav.ts`: `companies` (Operación, `/app/companies`, `corporate.view`, orden 45) y `receivables`
    (Operación, `/app/receivables`, `corporate.view`, orden 85).
  - `routes.tsx`: `companies`, `companies/:id` (`?tab=statement|reservations|details`), `receivables`.
  - `reservation-tabs.tsx`: `{ id: 'corporate-billing', labelKey: 'corporate:billing.tab', order: 25, permission:
    'corporate.view' }` (carga perezosa; `?tab=corporate-billing`).
  - `commands.ts`: "Nueva empresa" (`/app/companies?new=1`) y "Ver la cartera".
  - Reutilizables: `api.ts` (tipos y hooks `useCompanies`, `useStatement`, `useReceivables`,
    `useReservationBilling`, `corporateKeys`…), `components/AgingRibbon` (la cinta de antigüedad, `variant="mini"`),
    `components/CreditMeter`, `components/CompanyFormDialog`, `lib/nit.ts` (DV).
  - i18n: namespace `corporate` ES/EN (272 claves, paridad verificada).
  - La cinta usa una rampa **ordinal** de un solo tono (terracota) con pasos de luminosidad monótonos, validada con
    el validador de dataviz (`--ordinal`) en claro (sobre `#ffffff`) y oscuro (sobre `#1c1a18`); en oscuro el tramo
    más viejo es el más brillante. Tiene leyenda con montos (tabla de texto) y tooltip por tramo.
- **Finance**: `FolioPanel` muestra **pestañas por folio** (Huésped · nombre / empresa) con el saldo esperado de
  cada una, el saldo grande del folio elegido (`expected_balance`), la línea "Por cobrar antes del check-out" cuando
  difiere, textos propios del folio de empresa (sin "Link de pago"), y en los menús de fila **Mover al folio de…**
  (cargos y pagos) y **Dividir cargo…** (`SplitChargeDialog`). Tipos nuevos en `api.ts`: `FolioCompanyRef`,
  `FolioSummary.company/label` (opcionales), `totals.expected_balance`, `ManualChargeKind` con `tax`;
  funciones `transferCharge`, `splitCharge`, `transferPayment`. Nuevas claves `folio.*`, `move.*`, `split.*`.
- **Compliance**: `IssueInvoicePanel` acepta `folioId` y trae el selector **Facturar a**; `ReservationLegalTab`
  muestra una fila por cliente con su botón cuando hay folio de empresa. Tipos: `LegalFolio`,
  `InvoiceCustomer` (campos de empresa), `InvoiceSummary.due_date/is_company`.

## Modelo de datos (migraciones `corporate/0001`, `finance/0003_p4_company_folios`, `compliance/0003_p4_invoice_due_date`)

- `corporate.Company` (por organización; NIT único por organización), `corporate.ReservationBilling` (1-1 con la
  reserva; check: con empresa si `bill_to=company`), `corporate.AccountPayment` (empresa + propiedad, `active|voided`)
  y `corporate.AccountPaymentAllocation` (pago a cuenta → folio → `finance.Payment` 1-1).
- `finance.Folio`: `folio_type` gana `company`, `company` (FK PROTECT, obligatoria para `company`), `label`; un
  folio de empresa por (reserva, empresa); índice `(company, status)`.
- `compliance.Invoice.due_date`.
- Las migraciones dependen solo de migraciones existentes y estables (`bookings.0001`, `finance.0002`,
  `guests.0003`), no de las nuevas de P3.

## Seed (`apps/corporate/seed.py`, comando `seed_corporate`)

Ver "Cómo probarlo". Crea las reservas por los servicios de reservas en habitaciones libres (corre días si el hotel
está lleno), les pone la facturación **antes** de llegar (las noches se enrutan solas), hace check-in/check-out con
`force` como el seed de reservas y **conserva el estado de limpieza de hoy** de cada habitación. Facturas de las
estadías pasadas (una por folio, fechadas al check-out, sin PDF hasta la primera descarga) solo si ya hay una
resolución DIAN activa; si no, las emite después el seed de C7. Pagos a cuenta fechados en su día. Idempotente: una
organización que ya tiene empresas se omite. Probado **dentro de transacciones revertidas** (`--dry-run` y un
script de chequeo): 3 empresas, 5 reservas, 4 facturas (una del huésped y tres a NIT con vencimiento), 2 pagos a
cuenta, tramos 0–30 $1.142.400 / 31–60 $761.600 / 61–90 $1.850.000 / 90+ $2.000.000, $300.000 a favor, folio
dividido en casa, `reservation_balance` = SQL en las 5, estados de limpieza intactos, segunda corrida sin cambios;
**0,8 s**. La BD de desarrollo **no** quedó con el seed cargado (usar `seed_corporate`).

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps (para P-INT)

1. **`backend/apps/core/seed.py` (P1) → `SEED_ORDER`**: agregar `"corporate"` justo **después de `"bookings"`**
   (antes de `"finance"`): así el seed de finanzas cobra la parte de los huéspedes y el de C7 factura los folios de
   empresa en orden de fecha. (También funciona al final de la lista: entonces el seed de P4 emite sus facturas.)
2. **`backend/apps/bookings/services/queries.py::with_balance` (P3)**: reemplazar su cuerpo por
   ```python
   from apps.finance.balances import annotate_reservation_balance
   return annotate_reservation_balance(queryset)
   ```
   Es la misma regla nueva de `finance.reservation_balance` en SQL (verificado igual en las 5 reservas del seed y en
   las pruebas por API). Sin esto, las listas (Reservas, Hoy, reportes, copiloto) muestran la deuda de la empresa
   como saldo del huésped y `make check-data` reporta "saldos: reservation_balance = with_balance (SQL)" en las
   reservas facturadas a empresa.
3. **`core/management/commands/check_integrity.py` (P1, opcional)**: con el punto 2 queda consistente. Invariantes
   útiles para agregar: todo folio `company` tiene empresa; ninguna factura cubre cargos `source="opening_balance"`;
   Σ aplicaciones ≤ monto en cada pago a cuenta vigente.
4. **`backend/scripts/smoke_proxy.py` / `endpoints_sweep.py` y `frontend/scripts/route-smoke.mjs` (opcional)**: sumar
   `GET /api/v1/corporate/companies/`, `…/receivables/`, `…/companies/<id>/statement/`, `…/reservations/<id>/billing/`
   y las rutas `/app/companies`, `/app/companies/<id>`, `/app/receivables` y `?tab=corporate-billing`.
5. **P1 (`core.runtime.require_simulations`)**: ya aplicado como decorador de clase (`@require_simulations` sobre
   `SimIntentView` y `SimDecisionView`, la forma documentada en `apps/core/runtime.py`: envuelve `dispatch`). El import
   conserva un respaldo no-op por si el módulo cambia de lugar durante la integración. Nada que hacer salvo verificar
   en la prueba de producción de P-INT que `GET /api/v1/public/finance/sim/intents/<ref>/` da 404.
6. **P6 (alertas traducidas por `kind`)**: nuevo `company_over_credit` con `data {company_id, used, limit}` (texto
   guardado: "<empresa> superó su cupo de crédito").
7. **P6 (`guestportal`, opcional)**: el portal muestra como "lo que debes" `finance.reservation_balance`, que con una
   empresa **sin** crédito incluye la parte de la empresa (debe quedar paga antes del check-out). Si se quiere que el
   huésped vea solo lo suyo, usar `finance.services.guest_part(reservation)` en `guestportal/services/summary.py` y
   `payments.py`. Con empresas a crédito ya ve solo su parte.

## Limitaciones conocidas / pendientes

- **Sin tests nuevos** (modo MVP). Tests heredados que pueden romperse: `apps/finance/tests` (la firma del saldo de
  la reserva no cambió, pero `close_settled_folios` cierra por partes y `FolioSummarySerializer` suma campos),
  `apps/compliance/tests` (`issue_invoice(reservation)` ahora factura el primer grupo, el API con `reservation_id`
  agrega `additional_invoices`), `frontend/src/features/finance/__tests__` (el selector de folios cambió de
  ToggleGroup a pestañas propias).
- El **IVA del alojamiento siempre acompaña a la noche** (va al mismo folio): la regla "Impuestos y tasas aparte"
  enruta solo cargos `tax` publicados aparte (el nuevo tipo manual "Impuesto" en Agregar cargo). No se separa el IVA
  de una noche hacia otro adquiriente (la factura saldría con el servicio sin su impuesto).
- Cargos que el staff agrega a mano van al folio elegido (sin reglas). Las reglas aplican a lo automático y a
  "Mover los cargos ya publicados" al guardar la facturación.
- Estados de cuenta, cartera y pagos a cuenta son **por propiedad** (la activa); el cupo se mide en **toda la
  organización**. El cupo **avisa** (alerta y medidor en rojo), no bloquea reservas ni check-outs.
- Un cargo facturado no se mueve ni se divide (409 `charge_invoiced`): primero una nota crédito.
- Dividir una noche `room` deja dos cargos de esa noche (suman lo mismo; los reportes y `check_integrity` suman por
  estadía); anular solo una de las partes deja la noche "publicada" a medias (la otra parte no se vuelve a cargar).
- Un pago a cuenta en **efectivo** exige el turno de caja abierto (regla de finanzas); el pago se registra con la
  fecha de negocio del día (la fecha del pago queda en el pago a cuenta).
- Si cambias la empresa de una reserva, el folio de la empresa anterior queda (vacío o con lo facturado); la
  cartera lo sigue mostrando mientras tenga saldo.
- Facturas del seed de P4 cargado **sobre** un demo ya facturado quedan con números posteriores a facturas más
  nuevas (cosmético, modo simulado). Con el orden del punto 1 de "Cambios requeridos" salen en orden.
- La pestaña Facturación de un usuario sin `corporate.manage` es de solo lectura (controles deshabilitados).

## Verificación (esta sesión, sin tests)

- `docker compose exec -T backend python manage.py check` → sin problemas; `makemigrations corporate finance
  compliance --check --dry-run` → "No changes detected" (migraciones aplicadas en la BD de desarrollo);
  `ruff check` y `ruff format --check` limpios en `apps/corporate`, `apps/finance` y `apps/compliance` (sin
  `tests/`); `spectacular --validate` sin warnings de mis apps (los 2 que hay son de `imports`).
- Servicios en una transacción revertida (script de humo): enrutamiento de noches al folio de empresa,
  `reservation_balance` Python = SQL, transferir, dividir (suma exacta), estado de cuenta con tramos, pago a cuenta
  automático con saldo a favor, aplicar saldo a favor, anular (folios reabiertos), pestaña Legal con dos clientes y
  factura al NIT con DV y vencimiento (`SETT135 accepted`, due +30 días).
- API por el proxy de Vite (cookie jar + CSRF, `owner@casaaurora.co`): **43/43 comprobaciones OK** — CRUD y DV
  (400 con DV errado, NIT duplicado), facturación GET/PUT, dos folios con `expected_balance`, cargo explícito,
  tipo `tax`, transferir (y `same_folio`), dividir (y `already_voided`, `invalid_amount`), Legal con folio a NIT,
  estado de cuenta, saldos iniciales en 90+ y 31–60, pago a cuenta con $300.000 a favor, aplicar sin pendientes
  (400), CSV de cartera y de estado de cuenta, reservas de la empresa, anular sin/con `confirm`, borrar empresa usada
  (409), filtros de la lista; permisos: recepción lista (200) pero no crea, no cambia facturación ni registra pagos
  (403); limpieza 403; otra organización 404. La pasarela simulada pública sigue en 200/404.
- Seed: `seed_corporate --dry-run` y un chequeo detallado en transacción revertida (ver "Seed").
- Frontend: `npx tsc -p tsconfig.app.json --noEmit | grep features/(corporate|finance|compliance)` → 0 errores
  (los errores que quedan en el typecheck completo son de tests de otras features); `npx eslint
  src/features/corporate src/features/finance src/features/compliance` limpio; paridad ES/EN: corporate 272,
  finance 289, compliance 409 claves. Revisión visual con un **Chrome headless propio** (puerto 9561, perfil temporal;
  nunca el navegador compartido) en español a 1440 px (claro y oscuro) y 375 px: empresas, detalle (estado de
  cuenta, reservas, datos), cartera, pestañas Facturación / Folio (dividido, pestaña de la empresa) / Legal y los
  diálogos de empresa y de pago a cuenta (automático y "Elegir documentos"): sin excepciones, sin errores de consola,
  sin API ≥ 400, sin claves i18n crudas, sin desborde horizontal ni contenido fuera del viewport (un detector revisa
  cada elemento). Se corrigieron en el camino: el ancho mínimo de `fieldset` y de columnas `grid` implícitas a 375 px
  (Facturación y Cartera), la alineación de campos del formulario de empresa, "Total de este folio" en folios
  divididos y un doble punto en el texto del pago a cuenta. El inglés se verificó por paridad de claves, no a ojo
  (cambiarlo exigía tocar el perfil del dueño en la BD compartida).
- `require_simulations`: con `simulations_enabled()` en falso (parcheado en un shell), `GET` y `POST` de la pasarela
  simulada responden 404; con el entorno de desarrollo, 200 como antes.
- Datos de prueba: los de la API y de la revisión visual se crearon sobre la reserva futura **HT-3WB22N** de Casa
  Aurora y se **borraron** al terminar (empresa, folios de empresa, cargos y pagos de prueba, facturación): la
  reserva quedó como estaba (folio huésped sin cargos). Quedan solo eventos de auditoría de esas pruebas.
