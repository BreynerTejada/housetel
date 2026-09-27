# B4 — Finanzas y pagos — integration notes

Estado: tarea B4 completa (backend `apps/finance`, frontend `features/finance`, seed). Esta sesión retomó un
intento anterior interrumpido: revisé y conservé su trabajo (con tests), corregí un bug de seguridad en la
verificación de Wompi, agregué reembolsos automáticos con la API Refunds V2 de Wompi, el vencimiento de links de
reservas tentativas junto con su hold, el hook público `usePaymentStatus` para las páginas de retorno de C4/C5,
los reembolsos de datáfono/transferencia como movimientos del turno de caja y un `FolioPanel` que se adapta al
ancho de su contenedor (diálogos de C1).

- Backend: `docker compose run --rm -e TEST_DB_NAME=test_b4v backend pytest apps/finance -q` → **278 passed**
  (247 del implementador + 31 del verificador); `ruff check` / `ruff format --check` limpios;
  `makemigrations finance --check` sin cambios; `test_contracts` de core verde (firmas y tipos de retorno
  intactos); la suite de `bookings` (consumidor de estos servicios) sigue verde con los cambios.
- Frontend: `npx vitest run src/features/finance` → **5 archivos, 35 tests** (también en el contenedor Node 24,
  sin stderr); typecheck sin errores; eslint limpio.
- **Pasada del verificador (B4)**: ver la sección "Verificación B4 (verificador)" al final: 9 correcciones
  (seguridad de la pasarela simulada, reembolsos en folios cerrados, cierre con reembolsos pendientes,
  atomicidad, N+1 en la exportación, robustez del webhook, estados de error y un aviso en la UI) y el seed
  completo probado en una BD aislada.

Lectura rápida por consumidor:

| Quién | Qué usar |
|---|---|
| C1 (recepción) | `<FolioPanel reservationId compact onChange />` en check-in/check-out; pestaña "Folio" ya registrada; `financeKeys.all` para refrescar |
| C4 (marketplace) | `create_payment_intent(folio, amount=…, return_url=f"{FRONTEND_URL}/booking/{code}/confirmed")`; en el front `paymentReturnParams` + `usePaymentStatus` |
| C5 (portal) | `create_payment_intent(..., return_url=f"{portal_url(reservation)}?paid=1")` desde su API pública; `usePaymentStatus` al volver. **FolioPanel no sirve en el portal** (usa la API de staff) |
| C6 (mensajería) | plantilla `payment_link` con `{{payment_url}}`, `{{amount}}`, `{{reference}}`, `{{expires_at}}` (vienen en `context`) |
| C9 (anomalías) | `CashShift.difference`, `Payment` (pagos duplicados), alertas `refund_*`/`payment_*` |
| C10 (reportes) | `reporting.payments_summary`, `cash.cash_shift_totals`, CSV de caja; reglas de saldo abajo |
| C11 (SaaS) | funciones puras y `WompiClient` de `apps/finance/wompi.py` con credenciales de plataforma |
| C12 (control) | `WompiProvider.CONFIG_FIELDS` (5 campos, 3 secretos); URL de eventos `/api/v1/public/finance/webhooks/wompi/`; automatización `finance.sync_pending_intents` |

---

## API implementada

Staff: `/api/v1/finance/` (sesión + `X-Property-Id`; todo filtrado por `request.property`). Dinero siempre string
con 2 decimales. Errores con la forma del core `{detail, code, fields?, ...extra}`.

| Método y path | Permiso | Descripción |
|---|---|---|
| `GET folios/?reservation=<uuid>&status=open\|closed` | finance.view | Folios (paginado) con `totals` (sin `reservation_balance`) |
| `POST folios/` `{reservation_id}` | finance.collect | Get-or-create del folio huésped de la reserva → detalle (201 creado / 200 ya existía; 404 si la reserva es de otro hotel) |
| `GET folios/{id}/` | finance.view | Detalle: `charges`, `payments`, `refunds`, `intents` y `totals` con `reservation_balance` |
| `GET folios/{id}/charge-options/` | finance.view | Extras activos (con `default_quantity` para esta reserva e impuesto/exención) e impuestos para el diálogo "Agregar cargo" |
| `POST folios/{id}/charges/` | finance.collect | `{extra_id, quantity?}` o `{kind: extra\|fee\|adjustment\|other, description, amount (neto unitario), quantity?, tax_id?}`; solo `adjustment` admite monto negativo (descuento) |
| `POST charges/{id}/void/` `{reason, confirm: true}` | finance.void | Anula (el cargo queda tachado, no se borra) |
| `POST folios/{id}/payments/` | finance.collect | Pago manual `{amount, method: cash\|card_terminal\|bank_transfer\|other, reference?, notes?}`; efectivo exige turno de caja abierto (409 `cash_shift_required`) |
| `POST payments/{id}/void/` `{reason, confirm: true}` | finance.void | Anula un pago **manual** registrado por error (los pagos en línea se reembolsan) |
| `POST payments/{id}/refund/` `{amount, reason, confirm: true}` | finance.refund | → Refund `approved` \| `pending` (paso manual) \| `failed` |
| `POST refunds/{id}/complete/` `{confirm: true, outcome: approved\|failed, reference?}` | finance.refund | Cierra un reembolso `pending` después del paso manual |
| `POST folios/{id}/payment-link/` `{amount, send_via?: ["email","whatsapp"]}` | finance.collect | Link de pago (simulado o Wompi) que vuelve al portal del huésped; con `send_via` llama `messaging.send_message(template_code="payment_link")` |
| `GET intents/?status=&folio=&reservation=` · `GET intents/{id}/` | finance.view | Links de pago |
| `POST intents/{id}/sync/` | finance.collect | Verifica el link con el proveedor ahora |
| `GET cash-shifts/current/` | finance.view | `{shift: CashShiftDetail\|null}` del usuario en esta propiedad (totales en vivo y movimientos) |
| `POST cash-shifts/open/` `{opening_float, notes?}` | finance.cashier | Abre turno (409 `cash_shift_open` si ya tiene uno) |
| `POST cash-shifts/{id}/close/` `{counted_cash}` o `{denominations: {"50000": 3}}` (+ `notes`) | finance.cashier | Calcula `expected_cash` y `difference = contado − esperado` |
| `GET cash-shifts/?user=&status=open\|closed&start=&end=` · `GET cash-shifts/{id}/` | finance.cashier | Historial (fechas de apertura, inclusivas) y detalle |
| `GET cash-shifts/{id}/export/` · `GET cash-shifts/export/?start=&end=` | finance.cashier | CSV (`;`, UTF-8 con BOM para Excel) del turno / del historial |
| `GET summary/?date=` | finance.view | Pagos aprobados por medio, reembolsos y cargos de una fecha de negocio (por defecto la actual) |

Público: `/api/v1/public/finance/` (sin sesión; throttles propios por IP definidos en las clases, sin tocar settings).

| Método y path | Throttle | Descripción |
|---|---|---|
| `GET sim/intents/<reference>/` | 120/min | Lo que muestra la pasarela simulada. Solo links `simulated` de un hotel que **sigue** en modo simulado (los reales, los desconocidos y los simulados de un hotel que ya pasó a Wompi real → 404) |
| `POST sim/intents/<reference>/decide/` `{outcome: approved\|declined\|expired, method: card\|pse\|nequi}` | 30/min | Decisión del huésped; se aplica por el mismo camino que un webhook (`sync_payment_intent`). Link pagado o vencido → 409 `intent_closed` (aprobar dos veces es idempotente). Hotel en modo real → 404 (nadie puede "pagar" gratis un link simulado viejo) |
| `GET intents/<reference>/status/?id=<transaction id>` | 120/min | Verifica con el proveedor (máx. cada 2 s por link) y responde si está pagado. Lo usan las páginas de retorno |
| `POST webhooks/wompi/` | 600/min | Eventos de Wompi. Firma inválida → 400 `invalid_signature`; eventos ajenos, de otros tipos o con cuerpo malformado (sin `data.transaction` objeto, form-encoded…) → 200 `{received, ignored: true}` (nunca 500) |

### Ejemplos (respuestas reales capturadas de la API)

`GET folios/{id}/` (recortado: un extra, un cargo anulado, un pago con datáfono con reembolso parcial y un pago
en línea simulado):

```json
{
  "id": "d14012a8-…", "folio_type": "guest", "status": "open", "currency": "COP", "closed_at": null,
  "reservation": {"id": "5e2bed31-…", "code": "HT-7K2M9Q", "status": "confirmed",
                  "checkin_date": "2026-10-03", "checkout_date": "2026-10-05", "adults": 2, "children": 0},
  "guest": {"id": "84dad813-…", "full_name": "Camila Rodríguez", "email": "…", "phone": "+573000000000",
            "is_foreign_non_resident": false},
  "totals": {"charges_net": "70000.00", "tax_total": "13300.00", "charges_total": "83300.00",
             "payments_total": "500000.00", "refunds_total": "50000.00", "balance": "-366700.00",
             "reservation_balance": "333300.00"},
  "charges": [
    {"id": "ae43…", "folio": "d140…", "business_date": "2026-09-26", "kind": "extra", "description": "Desayuno",
     "quantity": 2, "unit_price": "35000.00", "amount": "70000.00", "tax_amount": "13300.00", "total": "83300.00",
     "tax": {"id": "2dc3…", "code": "IVA-EXT", "name": "IVA extras", "rate": "19.00"}, "tax_exempt": false,
     "stay_id": null, "night_date": null, "extra_id": "4caa…", "source": "user",
     "posted_by": {"id": "b2db…", "full_name": "Andrés Gómez", "email": "recepcion@casaaurora.co"},
     "voided": false, "voided_at": null, "voided_by": null, "void_reason": "", "created_at": "2026-09-26T18:44:50-05:00"},
    {"id": "64f9…", "kind": "fee", "description": "Lavandería", "amount": "20000.00", "tax_amount": "3800.00",
     "total": "23800.00", "voided": true, "void_reason": "Cargado por error", "…": "…"}
  ],
  "payments": [
    {"id": "f3bc…", "business_date": "2026-09-26", "amount": "300000.00", "method": "card_terminal",
     "status": "approved", "provider": "manual", "provider_reference": "VOUCHER-1", "notes": "",
     "received_by": {"…": "…"}, "refunded_amount": "50000.00", "refundable_amount": "250000.00",
     "intent_id": null, "intent_reference": null, "cash_shift_id": "d501…", "can_void": false,
     "voided_at": null, "void_reason": "", "created_at": "…"},
    {"id": "5c8a…", "amount": "200000.00", "method": "wompi_nequi", "status": "approved", "provider": "simulated",
     "provider_reference": "SIM-SW36PEBU6D", "intent_id": "2497…", "intent_reference": "HT-7K2M9Q-2D3J6D",
     "can_void": false, "…": "…"}
  ],
  "refunds": [
    {"id": "a02f…", "payment_id": "f3bc…", "amount": "50000.00", "status": "approved", "provider_reference": "",
     "reason": "Descuento acordado", "instructions": "", "error": "", "requested_by": {"…": "…"},
     "approved_by": {"…": "…"}, "business_date": "2026-09-26", "created_at": "…", "completed_at": "…"}
  ],
  "intents": [
    {"id": "2497…", "reference": "HT-7K2M9Q-2D3J6D", "folio_id": "d140…", "reservation_id": "5e2b…",
     "reservation_code": "HT-7K2M9Q", "amount": "200000.00", "currency": "COP", "status": "approved",
     "mode": "simulated", "provider": "simulated", "checkout_url": "http://localhost:5173/sim/pay/HT-7K2M9Q-2D3J6D",
     "return_url": "http://localhost:5173/g/<token>?paid=1", "expires_at": "2026-09-27T18:44:51-05:00",
     "created_at": "…", "method": "wompi_nequi", "status_message": "", "last_checked_at": "…", "payment_id": "5c8a…"}
  ]
}
```

- `totals.balance` = saldo **del folio** (cargos publicados − pagos + reembolsos). `totals.reservation_balance` =
  lo que **debe la reserva** (incluye noches aún no publicadas por la auditoría nocturna): es el número a mostrar
  al huésped. En el ejemplo: estadía 700.000 + desayuno 83.300 − 500.000 + 50.000 = 333.300.
- `tax_exempt` = el cargo tiene impuesto referenciado con `tax_amount = 0` (extranjero no residente).
- `can_void` = pago manual aprobado y sin reembolsos. `refundable_amount` descuenta reembolsos aprobados y pendientes.

`GET folios/{id}/charge-options/`:

```json
{"extras": [{"id": "4caa…", "code": "BRK", "name": {"es": "Desayuno", "en": "Breakfast"}, "price": "35000.00",
             "unit_price": "35000.00", "charge_type": "per_person_night", "default_quantity": 4,
             "tax": {"id": "2dc3…", "code": "IVA-EXT", "name": "IVA extras", "rate": "19.00", "applies_to": "extras",
                     "included_in_price": false, "exempt": false}}],
 "taxes": [{"id": "2dc3…", "code": "IVA-EXT", "…": "…"}],
 "manual_kinds": ["extra", "fee", "adjustment", "other"],
 "guest_is_foreign_non_resident": false}
```

`unit_price` es el neto que se publica (si el precio del extra incluye IVA se divide `precio/(1+tasa)`).
`default_quantity`: por estadía 1, por noche N, por persona P, por persona-noche P×N (P = adultos + niños).

`POST folios/{id}/payment-link/` `{"amount": "200000"}` → 201:

```json
{"intent": {"id": "2497…", "reference": "HT-7K2M9Q-2D3J6D", "status": "created", "mode": "simulated",
            "provider": "simulated", "amount": "200000.00", "checkout_url": "http://localhost:5173/sim/pay/HT-7K2M9Q-2D3J6D",
            "return_url": "http://localhost:5173/g/<token>?paid=1", "expires_at": "2026-09-27T18:44:51-05:00", "…": "…"},
 "checkout_url": "http://localhost:5173/sim/pay/HT-7K2M9Q-2D3J6D",
 "messages": []}
```

Con `send_via`, `messages` = `[{channel, to, status, error}]` (lo que devuelve C6). Si el envío lanza excepción el
link igual se crea y la respuesta trae `send_error` (el staff lo copia a mano).

`GET cash-shifts/current/` → `{"shift": null}` o:

```json
{"shift": {"id": "d501…", "user": {"id": "…", "full_name": "…", "email": "…"}, "opened_at": "…", "closed_at": null,
  "is_open": true, "opening_float": "200000.00", "expected_cash": null, "counted_cash": null, "difference": null,
  "denominations": {}, "notes": "", "closed_by": null,
  "totals": {"opening_float": "200000.00", "cash_payments": "0.00", "cash_refunds": "0.00",
             "expected_cash": "200000.00", "payments_count": 1, "refunds_count": 0,
             "by_method": [{"method": "card_terminal", "count": 1, "total": "300000.00"}]},
  "movements": [{"id": "f3bc…", "kind": "payment", "created_at": "…", "method": "card_terminal",
                 "amount": "300000.00", "status": "approved", "reference": "VOUCHER-1", "folio_id": "d140…",
                 "reservation_id": "5e2b…", "reservation_code": "HT-7K2M9Q", "guest_name": "Camila Rodríguez"}]}}
```

`POST cash-shifts/{id}/close/` `{"denominations": {"100000": 2}}` → el mismo objeto con `closed_at`,
`expected_cash: "200000.00"`, `counted_cash: "200000.00"`, `difference: "0.00"`, `denominations: {"100000": 2}`.
Si se envían `counted_cash` y `denominations` y no coinciden → 400 `denominations_mismatch` (con `counted`).

`GET summary/?date=2026-09-26`:

```json
{"date": "2026-09-26", "currency": "COP", "payments": {"count": 2, "total": "500000.00"},
 "refunds": {"count": 1, "total": "50000.00"}, "net_total": "450000.00",
 "by_method": [{"method": "card_terminal", "count": 1, "total": "300000.00"},
               {"method": "wompi_nequi", "count": 1, "total": "200000.00"}],
 "charges": {"net": "70000.00", "tax": "13300.00", "total": "83300.00"}}
```

Público — `GET sim/intents/<ref>/`:

```json
{"reference": "HT-7K2M9Q-2D3J6D", "amount": "200000.00", "currency": "COP", "status": "created",
 "mode": "simulated", "method": "", "expires_at": "2026-09-27T23:44:51+00:00", "created_at": "…",
 "return_url": "http://localhost:5173/g/<token>?paid=1&payment_ref=HT-7K2M9Q-2D3J6D",
 "property": {"name": "Hotel Casa Aurora", "slug": "casa-aurora", "city": "Cartagena", "primary_color": "", "logo": ""},
 "reservation_code": "HT-7K2M9Q", "payer_first_name": "Camila"}
```

`POST sim/intents/<ref>/decide/` `{"outcome": "approved", "method": "nequi"}` → el mismo objeto con
`status: "approved"`, `method: "wompi_nequi"`. `GET intents/<ref>/status/`:

```json
{"reference": "HT-7K2M9Q-2D3J6D", "status": "approved", "paid": true, "amount": "200000.00", "currency": "COP",
 "method": "wompi_nequi", "reservation_code": "HT-7K2M9Q", "property_slug": "casa-aurora"}
```

`status` ∈ `created | pending | approved | declined | expired | error` (un link sin pagar pasado su
`expires_at` se muestra `expired` aunque la automatización aún no lo haya marcado).

### Errores con `code` estable

| code | HTTP | Cuándo |
|---|---|---|
| `confirmation_required` | 400 | void / refund / complete sin `confirm: true` |
| `reason_required` | 400 | void / refund sin motivo |
| `invalid_amount`, `invalid_quantity`, `invalid_kind`, `invalid_method`, `invalid_status`, `invalid_outcome` | 400 | validación de servicios |
| `refund_exceeds_payment` | 400 | monto > lo que queda (`refundable` en el JSON: `"250000.00"`) |
| `folio_closed` | 409 | cargo, pago, void, **reembolso** o link sobre un folio cerrado (cerrado = saldado y de solo lectura) |
| `already_voided` | 409 | anular dos veces |
| `cash_shift_required` | 409 | efectivo (cobro o reembolso) sin turno abierto del usuario |
| `cash_shift_open` / `cash_shift_closed` | 409 | abrir con uno abierto / cerrar dos veces |
| `payment_not_refundable` / `payment_not_voidable` | 409 | pago no aprobado / pago en línea o con reembolsos |
| `refund_not_pending` | 409 | completar un reembolso que no está pendiente |
| `online_payments_disabled` | 409 | `IntegrationSetting(payments).enabled = False` |
| `intent_closed` | 409 | decidir sobre un link pagado o vencido (simulado) |
| `simulation_disabled` | 409 | `decide_simulated_intent` llamado (servicio) para un hotel que ya cobra en modo real; la API pública responde 404 antes |
| `integration_misconfigured` | 400 | modo real sin llaves de Wompi (`missing: [...]`); no se guarda nada |
| `integration_not_available` | 400 | ningún proveedor registrado (no debería pasar) |
| `counted_cash_required`, `invalid_denominations`, `denominations_mismatch` | 400 | cierre de caja |
| `invalid_signature` | 400 | webhook de Wompi con checksum inválido |
| `validation_error` | 400 | serializers (`fields`) |

---

## Contratos implementados / consumidos

Firmas exactas del spec §4.2 + plan §C (fijadas por `apps/core/tests/test_contracts.py`, no cambiaron):

```python
get_or_create_folio(reservation, *, stay=None) -> Folio
post_charge(folio, *, kind, amount, description, quantity=1, tax=None, tax_exempt=False, stay=None,
            night_date=None, extra=None, actor=None, source="user", business_date=None) -> Charge
void_charge(charge, *, reason, actor, confirm) -> Charge
record_payment(folio, *, amount, method, reference="", actor=None, status="approved", provider="manual",
               payload=None) -> Payment
refund_payment(payment, *, amount, reason, actor, confirm) -> Refund
create_payment_intent(folio, *, amount, return_url, provider_kind="payments") -> PaymentIntent
sync_payment_intent(intent) -> PaymentIntent
folio_balance(folio) -> Decimal
reservation_balance(reservation) -> Decimal
```

Reglas (normativas para quien los llame):

- **`post_charge`**: `amount` = neto **unitario**; `Charge.amount = quantize(amount × quantity)`;
  `tax_amount = quantize(neto × tax.rate/100)` o 0 si `tax_exempt` (el `tax` queda referenciado → "exento").
  Solo `adjustment` puede ser negativo. Folio cerrado → 409. Audita `finance.charge_posted` (cargo y auditoría
  en la misma transacción: o quedan los dos o ninguno).
- **`void_charge` / `refund_payment`**: exigen `confirm is True` (si no, `ConfirmationRequired`) y motivo. El permiso
  (`finance.void` / `finance.refund`) lo valida la API.
- **`record_payment`**: monto redondeado a la moneda y > 0. Efectivo exige el turno de caja abierto del **actor**
  si `property.settings.get("require_cash_shift", True)`; sin actor (sistema, pagos en línea) no se exige. Todo
  pago tomado por un usuario con turno abierto queda enlazado (`Payment.cash_shift`). Aprobado → emite
  `payment_received` al commit. Audita `finance.payment_recorded` (pago y auditoría en una sola transacción).
- **`refund_payment`**: monto ≤ `refundable_amount(payment)` (pago − reembolsos aprobados y pendientes); solo pagos
  aprobados y **solo en folios abiertos** (cerrado → 409 `folio_closed`: un reembolso dejaría el folio cerrado
  con saldo a cobrar). Pagos manuales → `approved` al instante (efectivo sale del turno del actor: exige turno; todo
  reembolso de un pago manual hecho con turno abierto queda en ese turno, solo el efectivo cambia el esperado);
  `ota_collect` → `pending` con instrucción (reembolsar en la extranet); pagos de un proveedor en línea → el
  proveedor decide (simulado → `approved`; Wompi → ver "Proveedores"). `pending` levanta alerta `refund_pending`
  (warning) y `failed` alerta `refund_failed` (critical), dedupe `refund:<id>`. Un `failed` libera el monto para
  reintentar. Audita `finance.payment_refunded`.
- **`create_payment_intent`**: referencia `<código de reserva>-<6 caracteres>` (casa: `F-<hex>-…`), única. Vence a
  las `property.settings["payment_link_hours"]` (24 h por defecto) y **nunca después del hold de una reserva
  `tentative`** (`hold_expires_at`): pagar después caería en una reserva ya liberada. Usa el proveedor del modo
  configurado en `IntegrationSetting(kind="payments")` y el link guarda ese modo (cambiar el modo después no rompe
  los links existentes). Si el proveedor no puede armar el checkout (p. ej. faltan llaves) no se persiste nada.
  `return_url` recibe `payment_ref=<reference>` al volver (Wompi además agrega `id=<transacción>`).
- **`sync_payment_intent`**: verificación activa (consulta al proveedor fuera de la transacción, aplica con el
  intent bloqueado). Idempotente: crea **un solo** `Payment` por intent (`Payment.intent` OneToOne + único
  `(provider, provider_reference)`), vía `record_payment` → `payment_received`. Un link rechazado puede pagarse en
  un reintento; dinero reportado después del vencimiento igual se registra; si el folio estaba cerrado se reabre
  (alerta `payment_on_closed_folio`); monto pagado ≠ monto del link → gana lo pagado + alerta
  `payment_amount_mismatch`; transacción anulada en Wompi → el pago pasa a `voided` (salvo que la explique un
  reembolso nuestro) + alerta `payment_voided_by_provider`. Errores del proveedor dejan el link igual y guardan el
  mensaje en `status_message`.
- **`folio_balance`** = Σ cargos no anulados (neto + IVA) − pagos aprobados + reembolsos aprobados.
- **`reservation_balance`** = Σ `Stay.total_amount` de stays facturables (`tentative|confirmed|checked_in|
  checked_out`) + cargos no-`room` no anulados (con IVA) − pagos aprobados + reembolsos aprobados, en todos los
  folios de la reserva. Los cargos `room` no se suman (consumen el total esperado). B2b replica esta regla en SQL
  (`bookings/services/queries.py::with_balance`): si cambia aquí, cambia allá.

Otros servicios públicos de la app (no son contrato, pero son estables): `post_extra_charge(folio, extra, *,
quantity=None, actor=None, source="user")` (extra con impuesto, exención y cantidad por defecto — lo puede usar C5
para extras comprados en el portal), `void_payment`, `complete_refund`, `refundable_amount`, `guest_of`,
`is_tax_exempt`, `extra_default_quantity`, `extra_unit_net`, `decide_simulated_intent` (409
`simulation_disabled` si el hotel ya está en modo real), `simulated_payments_enabled(property)`,
`sync_open_intents`, `close_settled_folios`, `intent_is_stale`; en `apps/finance/cash.py`: `current_cash_shift`,
`open_cash_shift`, `close_cash_shift`, `cash_shift_totals`; en `apps/finance/reporting.py`: `payments_summary`,
`folio_totals`, `annotate_folio_totals`, `annotate_shift_cash` (efectivo recibido/devuelto por turno en una sola
consulta; úsenlo C10 para listados de turnos), `shift_movements`, CSV.

Consumidos: `core.integrations` (proveedores, secretos), `core.audit`, `core.alerts`, `core.signals`,
`core.tokens.portal_url`, `messaging.services.send_message` (link de pago), modelos de `bookings`, `guests` y
`rates` (lectura).

Auditoría (`AuditEvent.action`): `finance.charge_posted`, `finance.charge_voided`, `finance.payment_recorded`,
`finance.payment_voided`, `finance.payment_refunded`, `finance.refund_completed`, `finance.payment_intent_created`,
`finance.payment_intent_updated`, `finance.folio_reopened`, `finance.folio_closed`, `finance.cash_shift_opened`,
`finance.cash_shift_closed`. Ninguna es reversible con "deshacer" (el dinero se corrige con anulaciones y
reembolsos, que quedan en el historial).

## Señales emitidas / escuchadas

- Emite `payment_received(payment)` (todo pago aprobado, manual o en línea; al commit) y `folio_closed(folio)`.
- Escucha `stay_checked_out(stay)` (`apps/finance/receivers.py`): si todas las stays de la reserva salieron (al
  menos una `checked_out`, el resto canceladas/no-show), `reservation_balance == 0` **y** no hay reembolsos
  `pending` (dinero aún en camino al huésped) → cierra los folios abiertos de la reserva y emite `folio_closed`
  por cada uno. Con saldo pendiente o a favor, o con un reembolso pendiente, el folio sigue abierto.
- B2b ya escucha `payment_received` (confirma tentativas; alerta si la reserva estaba cancelada).

## Automatizaciones registradas

- `finance.sync_pending_intents` (cada 5 min, por propiedad, activa por defecto): verifica con el proveedor todos
  los links `created`/`pending` (registra pagos cuyo webhook nunca llegó) y vence los que pasaron `expires_at` (o
  llevan > 24 h sin fecha). `details = {"checked", "approved", "expired"}`.

## Proveedores de integración registrados

`kind="payments"` (`apps/finance/providers.py`):

- `simulated` (`SimulatedPaymentProvider`, por defecto, sin `CONFIG_FIELDS`): `checkout_url =
  {FRONTEND_URL}/sim/pay/<reference>`; la página guarda la decisión en `intent.payload["simulation"]` y se verifica
  con `sync_payment_intent` como un webhook. Reembolsos aprobados al instante (`SIMREF-…`).
- `real` (`WompiProvider`, `code="wompi"`): `CONFIG_FIELDS` = `environment` (select sandbox|production),
  `public_key` (texto) y los secretos `private_key`, `integrity_secret`, `events_secret`. `test_connection` valida
  prefijos por ambiente (`pub_test_`/`prv_test_` vs `pub_prod_`/`prv_prod_`), la llave pública
  (`GET /merchants/{public_key}`) y la privada (búsqueda de transacciones).
  - Checkout Web firmado con `expiration-time` (el vencimiento del link) y `redirect-url` (return_url +
    `payment_ref`), `customer-data:email` y `customer-data:full-name`.
  - Verificación: `GET /transactions/{id}` si se conoce el id (y pertenece a la referencia), si no
    `GET /transactions?reference=`; siempre con `Authorization: Bearer <private_key>`. Se prefiere la transacción
    aprobada, luego la pendiente, luego la más reciente. El `id` que Wompi agrega al redirect lo puede editar
    cualquiera: un id desconocido (4xx), vacío o de otra referencia se ignora y decide la búsqueda por referencia
    (corregido en esta sesión: antes un id falso bloqueaba para siempre la verificación de ese link).
  - Webhook: valida el checksum con el `events_secret` de **esa** propiedad (encontrada por la referencia del
    evento) y luego verifica activamente con la API (nunca confía en el estado del cuerpo).
  - Reembolso: tarjeta → `POST /transactions/{id}/void` `{amount_in_cents}`; si la anulación ya no es posible, y
    para PSE/Nequi/otros → Refunds API V2 `POST /refunds`. Aprobado → `approved`. "No" definitivo → tarjeta
    `failed` (reintentable); otros medios `pending` con instrucción de transferencia manual. Sin respuesta (red/5xx)
    → `pending` pidiendo revisar el panel de Wompi antes de transferir (evita reembolsar dos veces).
- La interfaz (`create_checkout`, `fetch_status`, `parse_webhook`, `refund`) devuelve dicts planos para que C11
  (`saas_billing`) pueda imitarla.

### Wompi: verificación de la documentación actual (WebFetch, 2026-09-26)

Fuentes: <https://docs.wompi.co/docs/colombia/widget-checkout-web/>, <https://docs.wompi.co/docs/colombia/eventos/>,
<https://docs.wompi.co/docs/colombia/ambientes-y-llaves/>,
<https://docs.wompi.co/docs/colombia/seguimiento-de-transacciones/>,
<https://docs.wompi.co/en/docs/colombia/transacciones/>, <https://docs.wompi.co/en/docs/colombia/reembolsos-sandbox/>
y la especificación OpenAPI oficial enlazada desde la referencia (`https://api.swaggerhub.com/apis/waybox/wompi/1.2.0`).

1. **Checkout Web**: `https://checkout.wompi.co/p/` con obligatorios `public-key`, `currency`, `amount-in-cents`,
   `reference`, `signature:integrity`; opcionales `redirect-url`, `expiration-time` (ISO 8601), `tax-in-cents:vat`,
   `tax-in-cents:consumption`, `customer-data:*`, `shipping-address:*`. Al volver, Wompi agrega `?id=<transacción>`
   a la `redirect-url`.
2. **Firma de integridad**: SHA-256 de `"<Referencia><Monto en centavos><Moneda>[<ExpirationTime>]<SecretoIntegridad>"`
   calculada en el servidor. Vector oficial verificado en `test_wompi.py`: `sk8-438k4-xmxm392-sn2m`, `2490000`,
   `COP`, `prod_integrity_Z5mMke9x0k8gpErbDqwrJXMqsI6SFli6` →
   `37c8407747e595535433ef8f6a811d853cd943046624a0ec04662b17bbf33bf5`.
3. **Eventos**: `transaction.updated` (también `nequi_token.updated`, `bancolombia_transfer_token.updated`, que se
   ignoran). Checksum = SHA-256 de los valores de `signature.properties` (en orden, rutas dentro de `data`) +
   `timestamp` + secreto de eventos; llega en `signature.checksum` y en el header `X-Event-Checksum`. Hay que
   responder 200; si no, Wompi reintenta 3 veces en 24 h (30 min, 3 h, 24 h). **Ojo**: el checksum impreso en el
   ejemplo de la documentación (`3476DDA5…`) **no** es el SHA-256 de su propio string de ejemplo; el correcto,
   calculado con `hashlib`, es `5A18EC5E8FDB7DF463E9F94774CBA8F583BA21BD04A09CEFF2EA68A4BC0AEFBE` (es el que usan los
   tests). La comparación es sin distinguir mayúsculas y en tiempo constante.
4. **Consulta de transacciones**: `GET /v1/transactions/{id}` — la documentación actual dice que es "únicamente"
   con llave privada (la spec 1.2.0 la marca pública; enviamos siempre la privada). `GET /v1/transactions` busca por
   `reference` y **requiere llave privada**. Estados: `PENDING`, `APPROVED`, `DECLINED`, `VOIDED` (solo tarjeta),
   `ERROR`. Métodos: `CARD`, `PSE`, `NEQUI` (otros se registran como `wompi_other`).
5. **Anulación**: `POST /v1/transactions/{id}/void` (privada), body opcional `{amount_in_cents}`: "Anula una
   transacción APROBADA. Aplica únicamente para transacciones con Tarjeta (tipo CARD)".
6. **Reembolsos V2** (nuevo respecto al plan): `POST /v1/refunds` con llave privada, body `{transaction_id,
   amount_in_cents, reason?, reference…reference_5?}`, reembolso total o parcial; responde 201 con `status`
   `APPROVED` (con `v2_refund_id`) | `DECLINED` ("Tiempo límite sin encontrar fondos excedido") | `ERROR` |
   `CANCELLED`; 422 con más de 5 referencias. En sandbox el resultado se elige con `test_scenario` (Housetel envía
   `"approved"` solo en sandbox). La página se titula "Refunds V2 (Sandbox)" y no documenta qué medios cubre ni si
   hay eventos o consulta de reembolsos; por eso cualquier respuesta que no sea `APPROVED` cae al flujo manual.
7. Ambientes: `https://sandbox.wompi.co/v1` y `https://production.wompi.co/v1`; llaves `pub_test_`/`prv_test_`/
   `test_events_`/`test_integrity_` y sus equivalentes `prod`.

## Extensiones de frontend exportadas

- Rutas (`routes.tsx`): `app` → `cashier` (`/app/cashier`, página `CashierPage`); `bare` → `/sim/pay/:reference`
  (`SimPayPage`, sin shell de Housetel). Nav: `cashier` (operations, `finance.view`) sin cambios.
- `reservation-tabs.tsx`: `{ id: 'folio', labelKey: 'finance:tabs.folio', order: 20, permission: 'finance.view',
  Component: FolioTab }` (carga `FolioPanel` de forma perezosa).
- **`FolioPanel`** — `import { FolioPanel } from '@/features/finance/components/FolioPanel'` (también export
  default):

  ```tsx
  <FolioPanel
    reservationId={reservation.id}   // obligatorio
    compact                          // opcional: saldo + acciones; las líneas detrás de "Ver N movimientos"
    onChange={() => refetchReservation()}  // opcional: tras cada cargo, pago, anulación, reembolso o link
    className="…"                    // opcional
  />
  ```

  - Busca los folios de la reserva; si no hay y el usuario tiene `finance.collect`, crea el folio huésped
    (`POST folios/`); sin ese permiso muestra un estado vacío. Varios folios → selector.
  - Muestra el saldo grande (`reservation_balance`: por cobrar / saldado / a favor), barra pagado-vs-total, totales,
    cargos (neto, IVA, total; anulados tachados con motivo; "Exento"), pagos con sus reembolsos anidados y links de
    pago (copiar, abrir, verificar).
  - Acciones según permisos: `finance.collect` → Registrar pago (manual; avisa si efectivo sin turno con enlace a
    Caja), Agregar cargo (extra del catálogo o manual con vista previa neto/IVA/total, descuento como ajuste
    negativo), Link de pago (monto, envío por email/WhatsApp, QR y copiar); `finance.void` → anular cargo / pago
    manual (DangerConfirm: motivo + escribir el monto; al anular una noche `room` avisa que el saldo de la reserva
    no baja y sugiere un ajuste o modificar la estadía); `finance.refund` → reembolsar (DangerConfirm escribiendo el
    monto, explica qué pasa con el dinero según el medio) y completar reembolsos pendientes. Folio cerrado → solo
    lectura con insignia (tampoco ofrece reembolsar).
  - Todas las mutaciones invalidan `financeKeys.all`. Si C1 muestra el saldo en otro lado (p. ej. el encabezado de
    la reserva, que viene de bookings), refresque en `onChange`.
  - Es responsive por **container queries** (`@container` de Tailwind 4), no por el viewport: dentro de un diálogo
    angosto (p. ej. `max-w-lg`) la acción principal va a todo el ancho, las cifras en 2×2 y se ocultan las columnas
    neto/IVA, igual que en un teléfono. No hace falta pasarle nada.
- `PaymentStatusBadge` (`components/PaymentStatusBadge.tsx`, también default): estado de pago o reembolso con los
  colores del sistema (`StatusBadge kind="payment"`). `LinkStatusBadge`: estado de un link en palabras del
  huésped ("Sin pagar", "Pagado", "Vencido"…).
- `api.ts` (tipos y hooks reutilizables): `useReservationFolios(reservationId)`, `useFolio(folioId)`,
  `useCurrentShift()`, `useFinanceMutation`, `financeKeys`, tipos `FolioDetail`, `Charge`, `Payment`, `Refund`,
  `PaymentIntent`, `CashShiftDetail`…, y para páginas **públicas** de retorno:

  ```tsx
  import { paymentReturnParams, usePaymentStatus } from '@/features/finance/api'

  const { search } = useLocation()
  const { reference, transactionId } = paymentReturnParams(search)   // payment_ref (Housetel) + id (Wompi)
  const payment = usePaymentStatus(reference, { transactionId })     // cada 3 s hasta decidir
  // payment.data?.paid, payment.data?.status: created|pending|approved|declined|expired|error
  ```

  Deja de consultar al llegar a `approved|declined|expired|error`, ante un 4xx (referencia desconocida) o tras
  `maxPolls` (200) respuestas; sin referencia no hace ninguna petición. `getPaymentStatus(reference, id?)` es la
  función sin hook.
- `/sim/pay/:reference`: pasarela simulada con banda rayada fija "Modo simulación · Ningún cobro es real", marca y
  datos del hotel, total, referencia, vencimiento, pestañas Tarjeta / PSE / Nequi con formularios de prueba (datos
  del sandbox de Wompi), botones Pagar / Simular rechazo / Dejar vencer, selector de idioma. Aprobado → vuelve solo
  a `return_url` en 5 s (o con el botón); rechazado → reintentar o volver; vencido → volver.
- `/app/cashier`: turno actual (abrir con fondo inicial; efectivo esperado; recibido y devuelto; otros medios;
  movimientos —pagos y reembolsos de mostrador— con enlace a la reserva), cierre con arqueo por denominaciones
  (billetes y monedas COP) o solo total con veredicto en vivo (cuadra / sobran / faltan), cobros del día por medio,
  historial paginado con descarga CSV por turno y exportación de 30 días.
- i18n: namespace `finance` (ES y EN completos, paridad verificada por `src/lib/__tests__/i18n.test.ts`).

## Dependencias nuevas (pip/npm) y por qué

Ninguna. Backend usa `httpx`/`respx` (ya en requirements); frontend usa `qrcode.react` (ya en package.json).

## Cambios requeridos en archivos compartidos u otras apps

Ninguno obligatorio para B-INT (no toqué archivos compartidos; los throttles públicos definen su `rate` en la
clase). Para las fases siguientes:

- **C6**: crear la plantilla por defecto `payment_link` (ES/EN, email y WhatsApp). `send_message` recibe
  `context={"payment_url", "amount" ("$ 200.000"), "reference", "expires_at" (ISO)}` además de `guest` y
  `reservation`. Si `send_message` devuelve `[]` (stub actual) el front muestra "no se envió ningún mensaje, copia
  el link".
- **C4**: para `pay_now`/depósito: `create_payment_intent(get_or_create_folio(reservation), amount=…,
  return_url=f"{settings.FRONTEND_URL}/booking/{code}/confirmed")` y redirigir a `intent.checkout_url`. La reserva
  tentativa debe tener un `hold_expires_at` razonable (el link vence con él; con 20 min PSE puede quedar justo). La
  página de confirmación usa `usePaymentStatus` (el pago confirma la reserva vía el receiver de B2b).
- **C5**: `POST /public/guestportal/<token>/pay/` → `create_payment_intent(folio, amount=saldo o el pedido,
  return_url=f"{portal_url(reservation)}?paid=1")`; al volver `?paid=1&payment_ref=…` → `usePaymentStatus`. Extras
  comprados en el portal: `post_extra_charge(folio, extra, quantity=…, source="guest")`.
- **C12**: el formulario de integraciones debe renderizar `CONFIG_FIELDS` (tipos `select`, `text`, `password`
  secretos) y mostrar la URL de eventos `https://<dominio>/api/v1/public/finance/webhooks/wompi/` (el hotel la
  configura en su panel de Wompi). `test_connection` ya está implementado.
- **C10**: "pagos por método" = `Payment` aprobados por `business_date`; reembolsos por `Refund.business_date`
  (aprobados); IVA = `Charge.tax_amount` no anulados (exentos: `tax` presente y `tax_amount = 0`); turnos de caja =
  `CashShift` (`expected_cash`, `counted_cash`, `difference` se guardan al cerrar). Pueden reutilizar
  `reporting.payments_summary` y `cash.cash_shift_totals`.
- **C11**: reutilizar `apps.finance.wompi` (`checkout_url`, `integrity_signature`, `verify_event`, `WompiClient`)
  con las credenciales `WOMPI_PLATFORM_*`; no hace falta ningún cambio aquí.
- **C9** (anomalías): "pagos duplicados" puede leer `Payment` (mismo folio, monto y método en < 10 min);
  "diferencia de caja" = `CashShift.difference != 0` al cerrar.

## Modelo de datos (campos agregados, migración `finance/0002`)

- `Payment`: `intent` (OneToOne a `PaymentIntent`), `cash_shift`, `voided_at`, `voided_by`, `void_reason`; único
  `(provider, provider_reference)` salvo `manual` o referencia vacía.
- `Refund`: `requested_by`, `business_date`, `cash_shift`, `instructions`, `provider_payload`, `completed_at`.
- `PaymentIntent`: `provider_transaction_id`, `method`, `status_message`, `last_checked_at`, `created_by`.
- `CashShift`: `closed_by`, `denominations` (JSON `{"50000": 3}`); único turno abierto por `(property, user)`.

## Seed (`apps/finance/seed.py`, corre después de bookings)

Por propiedad, sobre las reservas que dejó B2b (idempotente: no toca reservas que ya tienen pagos o links; cada
decisión sale de un `Random` sembrado con el id de la reserva): estadías pasadas pagadas (datáfono, efectivo o
pasarela simulada tipo Wompi) con folios cerrados y ~8 % como cuentas por cobrar; en casa: pagadas, con 50 % o
debiendo; futuras confirmadas: depósitos 30–50 % (link pagado o transferencia), links pendientes y un link
rechazado de demo; tentativas: solo links pendientes; algunas penalidades cobradas. Para `recepcion@casaaurora.co`
y `recepcion@grupoandino.co` (claves `aurora_front`, `andino_front`): 5 turnos cerrados de días anteriores (con
alguna diferencia) y un turno **abierto hoy** con pagos de la mañana. Probado en `tests/test_seed.py` con datos
creados en el test y, en la pasada del verificador, con el **seed completo** de todas las apps (tal como están
hoy) en una BD de test aislada (`SEED_OFFLINE=1`): 2.335 pagos (efectivo, datáfono, transferencia y
Wompi simulado tarjeta/PSE/Nequi), 1.474 links (pagados, pendientes y uno rechazado de demo por hotel), turnos
abiertos para `aurora_front` y `andino_front` con 5 cerrados cada uno, 1.025 folios cerrados todos con saldo 0,
ninguna reserva con saldo a favor; la segunda corrida no creó nada (idempotente). El seed usa la pasarela
simulada: corre antes que `control` y requiere que `payments` siga en modo simulado.

## Limitaciones conocidas / pendientes

- Wompi real se probó con respx contra los payloads documentados; no hay llaves reales en el entorno. Refunds V2:
  producción y cobertura por medio no documentadas → siempre hay respaldo manual.
- No hay endpoint para crear folios de casa/maestros (sin reserva): existen en el modelo y en los servicios, pero la
  API solo abre folios de reservas (el plan no lo pide).
- Cerrar un folio no vence sus links abiertos: si el huésped paga un link viejo, el folio se reabre con alerta
  (queda saldo a favor para reembolsar).
- Los datetimes del payload público de la pasarela salen en UTC (`+00:00`) y los de staff en hora local
  (`-05:00`); ambos ISO-8601 con zona.
- `FolioPanel` es solo para staff. El portal del huésped (C5) debe usar su propia API pública.
- Pagos en línea no se "anulan" desde Housetel: se reembolsan (anulación de Wompi incluida).
- Un folio cerrado es de solo lectura (cargos, pagos, anulaciones, links y reembolsos → 409 `folio_closed`) y no
  hay acción "Reabrir folio" (no la pide el plan): el único reabierto automático es el de un pago en línea tardío.
  Si C1/C10 necesitan corregir cuentas ya cerradas, agreguen un "reabrir folio" con permiso y auditoría.
- El cierre automático ocurre solo al check-out: si la reserva salió con saldo (check-out forzado) y luego se paga
  o se reembolsa hasta quedar en 0, el folio queda abierto (en 0) hasta que alguien lo cierre.
- El link de pago que crea el staff vuelve al portal del huésped (su URL lleva el token del portal, igual que el
  `redirect-url` de Wompi): compártanlo solo con el huésped o con quien él autorice a pagar.
- Anular un cargo `room` no baja `reservation_balance` (las noches consumen el total de la estadía y la auditoría
  nocturna vuelve a cargar la noche); para descontar se usa un ajuste negativo o `modify_stay` con recotización.

## Verificación (esta sesión)

- `docker compose run --rm -e TEST_DB_NAME=test_b4 backend pytest apps/finance -q` → 247 passed.
- `docker compose run --rm -e TEST_DB_NAME=test_b4 backend pytest apps/core/tests/test_contracts.py
  apps/core/tests/test_domain_contract.py apps/core/tests/test_migrations.py -q` → verde.
- `ruff check apps/finance` y `ruff format --check apps/finance` limpios; `makemigrations finance --check` sin cambios.
- `cd frontend && npx vitest run src/features/finance` → 31 tests (también en el contenedor con Node 24:
  `docker compose run --rm --no-deps frontend npx vitest run src/features/finance`); `npx vitest run src/app src/lib`
  → 136 tests (extensiones, router, paridad i18n); `npx tsc -p tsconfig.app.json --noEmit` → 0 errores;
  `npx eslint src/features/finance` limpio.
- Chequeo de mutaciones sobre los tests heredados: quitar el `timestamp` del checksum, la idempotencia del pago del
  intent, la exigencia de turno para efectivo, la exclusión de cargos `room` en el saldo o el límite del reembolso →
  en los 5 casos algún test falla.
- Revisión visual en Chrome (contexto aislado, organización de vista previa propia creada y borrada al final; la BD
  de desarrollo quedó como estaba): `/sim/pay/<ref>` en claro/oscuro, ES/EN, 1440 px y 375 px, aprobación real →
  un solo `Payment` y saldo correcto; `/app/cashier` en escritorio y móvil; `FolioPanel` a ancho completo, en 375 px
  y compacto en un contenedor de 464 px (sin desborde horizontal); diálogo de reembolso con la ayuda por medio.
- Worker real: `finance.sync_pending_intents` corre cada 5 min en todas las propiedades activas (`success`, 0
  fallos).

## Verificación B4 (verificador)

Revisé la tarea contra el plan (B4, §B, §C, §D, §E), el spec §5 B4 y estas notas; leí todo `apps/finance` y
`features/finance`, corrí las suites y verifiqué contra la documentación oficial de Wompi (WebFetch 2026-09-26):
el vector de la firma de integridad (`37c84077…`), el algoritmo del checksum de eventos (y que el checksum impreso
en la página de eventos no corresponde a su propio string: el correcto es `5A18EC5E…`), Refunds V2
(`POST /v1/refunds`, llave privada, `APPROVED|DECLINED|ERROR|CANCELLED`, `test_scenario` en sandbox) y la anulación
(`POST /transactions/{id}/void`, solo tarjetas, 201 sin cuerpo en la spec 1.2.0).

Tests obligatorios del plan: todos existen, prueban lo que dicen y pasan (saldo neto+IVA/exento/anulados,
`reservation_balance` antes y después de publicar noches, confirm + permiso en void/refund, reembolso excedido,
vector de integridad, checksum válido/inválido, sync idempotente con webhooks repetidos (respx), flujo simulado,
expiración, `payment_received`, cierre al check-out con saldo 0, caja esperado vs contado, efectivo sin turno,
permisos, aislamiento; frontend: FolioPanel y página simulada).

Correcciones (cada una con su test visto en rojo antes del arreglo):

1. **Seguridad — pasarela simulada en un hotel que ya cobra de verdad**: cualquiera con un link simulado viejo
   podía "aprobarlo" después de que el hotel pasó `payments` a modo real, y quedaba un pago aprobado sin dinero.
   Ahora `GET/POST sim/intents/<ref>/…` responden 404 si el hotel está en modo real y `decide_simulated_intent`
   lanza 409 `simulation_disabled` (defensa en profundidad para otros llamadores).
2. **Reembolsos en folios cerrados**: `refund_payment` los aceptaba y el folio quedaba cerrado con saldo a cobrar
   (el panel lo mostraba sin acciones para cobrarlo). Ahora 409 `folio_closed` como el resto de operaciones de
   dinero, y el `FolioPanel` no ofrece "Reembolsar" en un folio cerrado.
3. **Cierre con un reembolso en camino**: el receiver de `stay_checked_out` cerraba el folio aunque hubiera un
   reembolso `pending` (p. ej. OTA); al completarlo, el folio cerrado quedaba con saldo. Ya no cierra en ese caso.
4. **Atomicidad**: `post_charge` y `record_payment` guardan la fila y su evento de auditoría en la misma transacción
   (las vistas no son atómicas; antes una falla de auditoría dejaba el pago/cargo sin rastro).
5. **N+1 en `GET cash-shifts/export/`**: 3 consultas por turno (15 vs 6 con 4 turnos). Ahora los totales de
   efectivo salen anotados (`reporting.annotate_shift_cash`) y el número de consultas no crece.
6. **Webhook robusto**: un cuerpo con `data` que no es objeto o form-encoded daba 500 (`AttributeError`); ahora
   200 `ignored`. `verify_event` tampoco revienta con `signature` no-objeto ni con checksums no ASCII
   (`hmac.compare_digest` sobre bytes).
7. **Estados de error en la UI**: el historial de turnos mostraba "Aún no hay turnos cerrados" cuando la API
   fallaba, y "Agregar cargo" mostraba "El hotel no tiene extras activos" ante un error; ahora ambos muestran el
   error con "Reintentar".
8. **Aviso al anular una noche `room`**: el diálogo decía que el cargo "deja de sumar al saldo", falso para
   noches (el saldo de la reserva no baja). Ahora lo explica y sugiere ajuste o modificar la estadía (ES/EN).
9. **Tests**: más casos de permisos y aislamiento (anular pago, completar reembolso, detalle/sync de links,
   detalle/cierre/exportación de turnos, historial CSV de otra organización vacío), confirmados con mutaciones
   del mapa de permisos; `SimPayPage.test.tsx` fija la cookie CSRF (en el contenedor Node 24 salía un error de
   MSW por `GET /accounts/auth/csrf/` sin handler).

Evidencia (corrida final):

- `docker compose run --rm -e TEST_DB_NAME=test_b4v backend pytest apps/finance -q` → **278 passed**.
- `pytest apps/core/tests/test_contracts.py apps/core/tests/test_domain_contract.py apps/core/tests/test_migrations.py`
  → 357 passed. `pytest apps/bookings` (TEST_DB_NAME propio) → 361 passed con estos cambios.
- `python manage.py check`, `makemigrations finance --check --dry-run` (sin cambios), `ruff check` y
  `ruff format --check apps/finance` limpios; `spectacular --validate` sin warnings de finance.
- `npx vitest run src/features/finance` → 35 passed (host y contenedor Node 24, sin stderr);
  `npx vitest run src/app src/lib` → 136 passed (paridad i18n, router, extensiones); `tsc` y `eslint` limpios.
- Seed completo en BD aislada: ver la sección "Seed" (idempotente, invariantes de saldo correctas).
- Revisión visual independiente con un Chrome headless propio (perfil y puerto aislados, por CDP; no se tocó el
  Chrome compartido): `/sim/pay/<ref>` a 375 px claro/oscuro y 1440 px; `/app/cashier` como
  `recepcion@casaaurora.co` a 375 px claro/oscuro y 1440 px con turno abierto, movimientos y reembolso, y el
  diálogo de cierre con el conteo por denominación a 375 px: 0 px de desborde horizontal en todos los casos. Los
  datos de vista previa (folio de casa, link, turno, 2 pagos, 1 reembolso) se borraron al final: la BD de
  desarrollo quedó sin filas de finanzas, como estaba.
