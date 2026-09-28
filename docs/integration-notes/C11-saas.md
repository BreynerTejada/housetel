# C11 — SaaS y super-admin — integration notes

Estado: **terminada en modo MVP** (sin tests nuevos, por decisión del usuario). Esta sesión retomó un intento
anterior que había dejado casi todo el backend y dos páginas del frontend. Lo revisé, lo completé y lo verifiqué de
punta a punta:
- Backend: API de staff, pública y de super-admin; ciclo de cobro; comisiones; seed. Agregué la configuración de
  tarjeta en modo real, la acción de admin "terminar prueba ahora", el campo "cliente desde" y corregí textos.
- Frontend: facturación del hotel, las 6 páginas `/admin`, el aviso global de mora o suspensión (`topbar.tsx`) y los
  locales ES/EN completos (554 claves en paridad).
- Validación: los flujos se probaron con curl, con escenarios en transacciones revertidas y con un Chrome headless
  propio (perfil y puerto aislados; no toqué el navegador compartido).

Owner paths: `backend/apps/saas/**`, `frontend/src/features/saas/**` y esta nota. No toqué archivos compartidos, no
agregué dependencias, no hice commits y no modifiqué `.env`.

Lectura rápida:
- **C-INT**: ver "Cambios requeridos en archivos compartidos". Lo principal es un bug del `KpiTile` compartido y
  reiniciar `beat`. No hace falta ningún `ENUM_NAME_OVERRIDES` por saas.
- **Orquestador (Chrome)**: ver "Cómo probarlo en la UI" al final.
- **Otras apps**: la organización suspendida sigue devolviendo 402 en toda la API de staff salvo `accounts`, `saas/billing`
  y `saas/getting-started`. El shell solo depende de `/me`, así que el dueño siempre puede llegar a pagar.

---

## API implementada

Convenciones del core: errores `{detail, code, fields?}`, dinero en string con 2 decimales, fechas ISO.

### Pública — `/api/v1/public/saas/`

| Método y path | Descripción |
|---|---|
| `GET plans/` | Planes activos: `[{code, name{es,en}, description{es,en}, max_units, max_properties, price_monthly, price_yearly}]` (`max_* = null` significa ilimitado). |
| `POST signup/` | Exige CSRF como el login; throttle de 30 por hora por IP. Body: `{hotel_name, property_type (hotel\|hostel\|boutique\|aparthotel\|glamping), city, department?, rooms_estimate (1–5000), owner_name, email, password, phone?, accept_terms: true, language? (es\|en)}`. Crea la organización `trial` de 14 días, la propiedad (slug único), los roles de sistema, el dueño, la suscripción `trialing` con el plan que corresponde a las unidades, y los impuestos, políticas y planes de tarifa por defecto (`provision_rates`). Luego **inicia la sesión**. Responde 201 `{redirect: "/app/getting-started", organization: {id, slug}, property: {id, slug}, me: Me}`. Errores 400 en `fields`: email ya usado, contraseña débil (validadores de Django), `accept_terms` sin aceptar, nombre corto. |
| `POST webhooks/wompi/` | Eventos de la cuenta Wompi **de la plataforma**. Valida el checksum con `WOMPI_PLATFORM_EVENTS_SECRET` (si falla, 400 `invalid_signature`) y luego verifica activamente la factura con la API: nunca confía en el cuerpo. Responde siempre 200 `{received}` o `{received, ignored: true}`. |

Plan según unidades: ≤ 15 → Starter; ≤ 60 → Pro; más → Cadena (el plan activo más pequeño que alcance).

### Staff (hotel) — `/api/v1/saas/` (sesión + `X-Property-Id`, `allow_suspended = True`)

| Método y path | Permiso | Descripción |
|---|---|---|
| `GET billing/` | `saas.billing_view` | Resumen completo (ejemplo abajo). Si la organización no tiene suscripción (orgs creadas fuera del signup), la crea en el primer acceso. |
| `GET billing/status/` | cualquier miembro | `{organization_status, subscription_status, plan{code,name}, trial_ends_at, trial_days_left, open_balance}`. Lo usa el chip de la barra superior. |
| `GET billing/invoices/` · `GET billing/invoices/{id}/` | `saas.billing_view` | Facturas de plataforma de la organización (hasta 120, más recientes primero). |
| `GET billing/invoices/{id}/pdf/?lang=es\|en` | `saas.billing_view` | PDF (reportlab) generado al vuelo; attachment `HTP-2026-00016.pdf`. |
| `POST billing/invoices/{id}/pay/` | `saas.billing_manage` | En modo simulado cobra ya: `{status: approved\|declined, checkout_url: null, message, invoice}`. En modo real responde `{status: "requires_action", checkout_url}` (Wompi Web Checkout) y vuelve a `/app/settings/billing?invoice=<id>`. Errores 409 `invoice_paid` / `invoice_void`. |
| `POST billing/invoices/{id}/verify/` | `saas.billing_view` | Consulta al proveedor el pago de esa factura (al volver del checkout). |
| `GET billing/payment-method/` | `saas.billing_manage` | Datos del formulario de tarjeta. Simulado: `{mode: "simulated"}`. Real: `{mode: "real", public_key, environment, tokenize_url, acceptance_token, acceptance_permalink, personal_auth_token, personal_auth_permalink}`, con tokens pedidos por el servidor a `GET /v1/merchants/{public_key}`. |
| `POST billing/payment-method/` | `saas.billing_manage` | Simulado: `{holder, number, exp_month, exp_year, cvc}` validado con Luhn, vencimiento y CVC; solo se guardan marca, últimos 4 y vencimiento. Real: `{token, acceptance_token, accept_personal_auth}` (el navegador tokenizó la tarjeta en Wompi) → crea la fuente de pago. Devuelve `Subscription`. Error 400 `validation_error` con `fields.number/exp_month/cvc/holder`. `DELETE` olvida la tarjeta. |
| `POST billing/change-plan/` | `saas.billing_manage` | `{plan_code, billing_cycle?: monthly\|yearly}`. Aplica desde la próxima factura, sin prorrateo. Error 400 `plan_too_small` (con `units`, `properties`) si no alcanza. |
| `POST billing/cancel/` | `saas.billing_manage` | `{confirm: true, reason?}` → `cancel_at_period_end = true` (si falta `confirm`, 400 `confirmation_required`). `POST billing/resume/` lo revierte (409 `already_cancelled` si ya terminó). |
| `GET billing/commissions/` | `saas.billing_view` | Estado de cuenta de comisiones: `{summary, this_month, rates:[{property_id,name,commission_rate,marketplace_listed}], settlements:[…24], recent:[…50 por fecha de creación de la reserva]}`. |
| `GET getting-started/` | cualquier miembro | Checklist (ver abajo) + `billing` (mismo payload que `billing/status/`). |

`GET billing/` (Casa Aurora, recortado):

```json
{"organization": {"id": "85e4…", "name": "Casa Aurora", "status": "active", "trial_ends_at": null},
 "subscription": {"id": "…", "plan": {"id": "…", "code": "pro", "name": {"es": "Pro", "en": "Pro"}, "max_units": 60,
   "max_properties": 2, "price_monthly": "349000.00", "price_yearly": "3559800.00"}, "status": "active",
   "billing_cycle": "monthly", "current_period_start": "2026-09-15", "current_period_end": "2026-10-15",
   "trial_ends_at": "2026-04-15T08:00:00Z", "cancel_at_period_end": false,
   "payment_source": {"type": "card", "brand": "VISA", "last4": "4242", "exp_month": 11, "exp_year": 2029,
                      "holder": "Valentina Rojas", "simulated": true},
   "retries": 0, "next_retry_at": null, "past_due_since": null, "cancelled_at": null, "monthly_amount": "349000.00"},
 "summary": {"organization_status": "active", "subscription_status": "active", "plan": {"code": "pro", "name": {…}},
             "trial_ends_at": "…", "trial_days_left": null, "open_balance": "0.00"},
 "usage": {"units": 24, "properties": 1, "max_units": 60, "max_properties": 2, "units_percent": 40, "over_limit": false},
 "upcoming_invoice": {"date": "2026-10-15", "period_start": "2026-10-15", "period_end": "2026-11-14",
                      "subtotal": "349000.00", "tax": "66310.00", "total": "415310.00"},
 "open_invoices": [],
 "plans": [{"code": "starter", "fits": false, "current": false, "…": "…"}, {"code": "pro", "fits": true, "current": true},
           {"code": "cadena", "fits": true, "current": false}],
 "billing_mode": "simulated", "tax_rate": "19.00", "retry_schedule_days": [1, 3, 7]}
```

Factura de plataforma (`PlatformInvoice`, en todas las listas):

```json
{"id": "3c1a…", "number": "HTP-2026-00016", "kind": "subscription|commissions|other",
 "organization": {"id": "…", "name": "Casa Aurora", "slug": "casa-aurora"},
 "period_start": "2026-09-15", "period_end": "2026-10-14",
 "lines": [{"kind": "plan", "description": {"es": "Plan Pro (mensual) · 15/09/2026 – 14/10/2026", "en": "…"},
            "quantity": 1, "unit_price": "349000.00", "amount": "349000.00", "plan_code": "pro"}],
 "currency": "COP", "subtotal": "349000.00", "tax_rate": "19.00", "tax": "66310.00", "total": "415310.00",
 "status": "open|paid|void|failed", "issued_at": "…", "due_date": "2026-09-20", "paid_at": "…",
 "payment_reference": "SIM-SAAS-…", "payment_method": "VISA •••• 4242", "attempts": 1, "last_error": ""}
```

Las líneas de comisiones traen `kind: "commission"`, `quantity` (número de reservas), `property_id` y
`settlement_id`. Los periodos de factura y de liquidación son **inclusivos**.
`Subscription.current_period_start/end` es semiabierto: `current_period_end` es la fecha de renovación.

Checklist (`GET getting-started/`): 7 pasos `{id, done, detail, link, alt_link?}`.

| Paso | Qué exige | Enlaces |
|---|---|---|
| `profile` | Perfil del hotel completo: `legal_name`, `nit`, `rnt_number`, `phone`, `email`, `address`, `city` y `description` | `detail.missing` = lo que falta |
| `rooms` | Unidades vendibles > 0, según `inventory_summary` | alt `/app/onboarding` (IA) |
| `rates` | Toda categoría activa tiene precio base > 0 | — |
| `payments` | `IntegrationSetting(payments)` en modo real y habilitado | — |
| `channels` | Listada en el marketplace, o con al menos una `distribution.ChannelConnection` | alt `/app/channels` |
| `team` | Más de un miembro, o alguna invitación pendiente | — |
| `first_booking` | Alguna reserva | — |

Totales: `completed`, `total`, `percent`.

### Super-admin — `/api/v1/saas/admin/` (sesión + `is_platform_admin`, **sin** `X-Property-Id`)

Otro usuario recibe 403 `platform_admin_required`; un anónimo recibe 401.

| Método y path | Descripción |
|---|---|
| `GET metrics/` | `{as_of, currency, mrr, arr, trial_mrr, organizations{total,active,trial,past_due,suspended,cancelled}, churn_30d, cancelled_30d, gmv_month, commissions_month, commissions_pending, unpaid_invoices{count,total}, series:[12 × {month "YYYY-MM", subscriptions, commissions, gmv, bookings, new_organizations}], plan_mix:[{plan,count}]}`. Definiciones en `services/metrics.py`: el MRR suma suscripciones `active` y `past_due`, con las anuales divididas entre 12; el churn cuenta cancelaciones de los últimos 30 días. |
| `GET organizations/?status=&plan=&q=&page=&page_size=` | Paginado. Fila: `{id, name, slug, legal_name, nit, status, created_at, customer_since, trial_ends_at, subscription{status,billing_cycle,current_period_end,cancel_at_period_end,has_payment_method}, plan{code,name,max_units}, units, properties_count, users_count, mrr, simulate_payment_failure}`. `customer_since` es la fecha más temprana entre la creación y la primera factura (las orgs del seed muestran abril de 2026). |
| `GET organizations/{id}/` | Fila más `properties[]` (unidades, reservas, marketplace, comisión, fecha de negocio), `users[]`, `pending_invitations`, `subscription_detail`, `usage`, `upcoming_invoice`, `invoices[24]`, `commissions{summary,recent[20]}` y `settlements[]`. Es solo lectura (la suplantación queda fuera de alcance, según el plan). |
| `POST organizations/{id}/suspend/` | `{confirm: true, reason?}`. Suspende la organización y su suscripción y manda un correo a los dueños. 409 `already_suspended`. |
| `POST organizations/{id}/reactivate/` | Vuelve a `trial` (si la prueba sigue vigente y nunca pagó) o a `active`. Las facturas abiertas siguen abiertas. 409 `already_active`. |
| `POST organizations/{id}/extend-trial/` | `{days: 1–90}`. Si estaba en mora por el fin de la prueba, anula esas facturas y vuelve a `trialing`. 409 `not_in_trial` si ya pagó alguna vez. |
| `POST organizations/{id}/end-trial/` | **Nuevo.** Termina la prueba ahora por el mismo camino que el ciclo diario: con tarjeta cobra la primera factura y queda `active`; sin tarjeta, o si el cobro falla, queda `past_due` con la factura abierta. 409 `not_in_trial`. |
| `POST organizations/{id}/change-plan/` | `{plan_code, billing_cycle?}` con `force` (el admin puede asignar un plan más pequeño que el uso). |
| `POST organizations/{id}/simulate-payment-failure/` | `{enabled: bool}`: el proveedor simulado rechaza los cobros de esa organización (ayuda para demos). |
| `GET/POST/PATCH/DELETE plans/` | CRUD sin paginar, con `subscriptions_count` y `active_subscriptions_count`. Borrar un plan en uso da 409 `in_use` (hay que desactivarlo). |
| `GET invoices/?status=&kind=&organization=&q=` · `GET invoices/{id}/` | Paginado, más `summary{open_total, paid_month}`. |
| `POST invoices/{id}/charge/` · `mark-paid/` `{confirm:true, reference?}` · `void/` `{confirm:true, reason?}` · `GET invoices/{id}/pdf/` | Acciones sobre una factura. Marcar pagada la última factura pendiente reactiva la organización. Anular devuelve las comisiones a una liquidación abierta. |
| `GET commissions/?status=&organization=&property=&month=YYYY-MM&q=<código>` | Paginado, más `summary{pending,settled,reversed: {total,count}}` (respeta los filtros). |
| `GET settlements/` · `POST settlements/run/` `{month: "2026-08"}` | Lista y liquidación manual de un mes cerrado. Corre `automation.run("saas.commission_settlement", params)`; es idempotente. Un mes abierto da 400 `month_not_closed`. |
| `POST billing-cycle/run/` | Corre `saas.billing_cycle` ya y devuelve `{id, status, summary, details}`. |
| `GET/PATCH billing-settings/` · `POST billing-settings/test/` | `IntegrationSetting(kind="saas_billing", property=None)`: `{mode, enabled, status, status_message, last_checked_at, wompi{environment, *_configured, webhook_url}}`. `PATCH {mode?, enabled?}`. Las credenciales vienen del entorno y nunca se devuelven. |
| `GET subscriptions/` | Lista simple de suscripciones con su organización. |

Comisión (`Commission`):

```json
{"id": "…", "organization": {"id": "…", "name": "Casa Aurora"},
 "property": {"id": "…", "name": "Hotel Casa Aurora", "slug": "casa-aurora"},
 "reservation": {"id": "…", "code": "HT-BPSMB5", "status": "confirmed", "checkin_date": "2026-12-24",
                 "checkout_date": "2026-12-27", "total_amount": "2269092.00"},
 "basis": "stay|fee", "base_amount": "1906800.00", "rate": "10.00", "amount": "190680.00", "currency": "COP",
 "status": "pending|settled|reversed", "accrual_date": "2026-12-27", "settlement_id": null, "reversed_at": null}
```

## Contratos implementados / consumidos

- Implementa el ciclo de vida de la suscripción, las facturas y las comisiones en `apps/saas/services/{billing,
  commissions,metrics,checklist,signup,plans,pdf}.py`. Otras apps pueden usar:
  - `billing.organization_summary(org)`.
  - `billing.get_subscription(org)`.
  - `billing.check_plan_limit(org)`.
  - `commissions.sync_commission(reservation)`, que es idempotente.
- Consume:
  - `accounts.services.add_member` y `ensure_system_roles`.
  - `rates.services.provision.provision_rates` (signup y org de prueba).
  - `inventory.services.inventory_summary` (checklist).
  - `core.integrations`, `core.audit`, `core.alerts` y `core.automation`.
  - `apps.finance.wompi` (`WompiClient`, `integrity_signature`, `checkout_url`, `verify_event`, `pick_transaction`,
    `STATUS_MAP`, `API_URLS`).
  - Lectura por ORM de `bookings.Reservation/Stay`, `inventory.Room/Bed`, `accounts.Membership/Invitation`,
    `distribution.ChannelConnection` y `rates.RoomTypeRateDefaults`.
- Excepción autorizada por el plan: escribe `Organization.status` y `trial_ends_at`, y en el signup crea la
  organización, la propiedad y el usuario.

Auditoría (`AuditEvent.action`), ninguna reversible:
- `saas.signup`
- `saas.invoice_issued` · `saas.invoice_paid` · `saas.invoice_voided` · `saas.charge_failed`
- `saas.payment_method_updated` · `saas.plan_changed`
- `saas.subscription_cancel_requested` · `saas.subscription_resumed` · `saas.subscription_past_due` ·
  `saas.subscription_reactivated` · `saas.subscription_cancelled`
- `saas.organization_suspended` · `saas.organization_reactivated`
- `saas.trial_extended` · `saas.trial_ended`
- `saas.commission_recorded` · `saas.commission_updated` · `saas.commission_reversed` · `saas.commissions_settled`

## Señales emitidas / escuchadas

- Emite: ninguna.
- Escucha, en `receivers.py` y todos con `if is_seeding(): return`:
  - `reservation_created`, `reservation_updated`, `reservation_cancelled` y `reservation_no_show`, solo si
    `source == "marketplace"`. Llaman a `sync_commission`:
    - `confirmed`, `checked_in` o `checked_out` → comisión `pending`. Base = Σ `nightly_rates[].net` (o `amount`)
      de las estadías facturables, es decir, el alojamiento sin impuestos. Tarifa = `property.commission_rate`.
      Se causa en la fecha de salida.
    - `cancelled` o `no_show` con penalidad → la comisión se recalcula sobre la penalidad (`basis = fee`) y se causa
      en la fecha de cancelación.
    - `cancelled` o `no_show` sin penalidad → `reversed` (conserva la base).
    - `tentative` → nada.
    - Una comisión `settled` nunca se reescribe.
  - `inventory_changed` (salvo `origin == "bookings"`) → `check_plan_limit(org)`. Levanta o resuelve la alerta
    `plan_limit` (warning, `dedupe_key = "saas:plan_limit"`, enlace a `/app/settings/billing`) en cada propiedad
    activa. Es un límite suave: no bloquea nada.

## Automatizaciones registradas

Ambas son de plataforma (`scope="platform"`):

| Código | Horario | Qué hace |
|---|---|---|
| `saas.billing_cycle` | diario 03:00 | Por cada suscripción no cancelada, cada una en su savepoint:<br>1. Prueba vencida: empieza el periodo y emite la factura (plan + IVA 19 %). Con tarjeta cobra; sin tarjeta, o si el cobro falla → `past_due`.<br>2. Renovación en `current_period_end`: factura, cobra y avanza el periodo.<br>3. Reintentos de las `past_due` 1, 3 y 7 días después del primer fallo; el tercer fallo → `suspended` (organización `suspended`) y correo a los dueños.<br>4. `cancel_at_period_end` → `cancelled` al final del periodo.<br>5. Revisa el límite del plan.<br>`details = {trials_converted, renewed, paid, failed, past_due, suspended, recovered, cancelled, errors}`. |
| `saas.commission_settlement` | día 1, 04:00 | Liquida por organización las comisiones `pending` causadas el mes anterior, o el `params {year, month}`: crea un `CommissionSettlement` y una factura `commissions` con una línea por propiedad más IVA, y la cobra. Es idempotente. |

Un pago posterior (reintento, botón "Pagar" del hotel o "marcar pagada" del admin) sin facturas pendientes vuelve a
`active`. Las dos corren sin error con `automation.run(code, None)`; ver "Verificación".

## Proveedores de integración registrados

`kind="saas_billing"`, a nivel plataforma (`IntegrationSetting(property=None)`), en `providers.py`:

- **`simulated`** (por defecto): aprueba todo salvo `organization.settings["simulate_payment_failure"]`. La tarjeta
  se valida localmente.
- **`real`** (Wompi con la cuenta de la plataforma, variables `WOMPI_PLATFORM_*` del entorno, que ya están en
  `.env.example`). Verificado contra docs.wompi.co el 2026-09-27 ("Fuentes de pago", "Métodos de pago › Tokeniza
  una tarjeta" y "Tokens de aceptación"):
  - Tokenización en el **navegador**: `POST {api}/tokens/cards` con la llave pública como Bearer y body
    `{number, cvc, exp_month "MM", exp_year "YY" (2 dígitos), card_holder}` → `data.id`. La tarjeta nunca pasa por
    Housetel.
  - Tokens de aceptación: el servidor llama `GET /v1/merchants/{public_key}` y lee
    `data.presigned_acceptance.{acceptance_token, permalink}` y `data.presigned_personal_data_auth.{…}`. La UI
    muestra los dos documentos con casillas obligatorias.
  - Fuente de pago: `POST /v1/payment_sources` (llave privada) con `{type: "CARD", token, customer_email,
    acceptance_token, accept_personal_auth}`.
  - Cobro recurrente: `POST /v1/transactions` con `payment_source_id`, `recurrent: true`, `signature` de
    integridad, `payment_method.installments: 1` y referencia `HTP-…-A<n>`. Si queda `PENDING`, se consulta de
    nuevo.
  - Pago manual: Web Checkout firmado (`wompi.checkout_url`) con referencia `HTP-…-P<xxxx>`. Se verifica con
    `GET /v1/transactions?reference=`.
  - Webhook: `/api/v1/public/saas/webhooks/wompi/`.
  - `test_connection` revisa las variables y `GET /merchants/{public_key}`.
  - Sin llaves reales en el entorno: el modo real no se probó en vivo.

## Extensiones de frontend exportadas

- `routes.tsx`, con todas las páginas en `lazy`:
  - público: `/signup`;
  - `app`: `getting-started` y `settings/billing`;
  - `admin`: index, `organizations`, `organizations/:id`, `plans`, `billing` y `commissions`.
  - Los ítems de `nav.ts` no cambian.
- **`topbar.tsx`** (orden 5, sin permiso) → `BillingStatusItem`:
  - Organización `active`: no se muestra nada y no hace petición (el estado sale de `Me`).
  - `trial`: chip "Prueba · N días" (se oculta en teléfonos).
  - `past_due`: chip "Pago pendiente" más un aviso flotante abajo, con "Pagar ahora" y "Ocultar" (por sesión y por
    organización).
  - `suspended`: chip "Cuenta suspendida" más un aviso rojo que no se puede ocultar. Si no hay saldo, explica que
    la suspendió el equipo de Housetel.
  - `cancelled`: chip.
  - Los miembros sin `saas.billing_manage` ven "Avísale al dueño de la cuenta". En teléfonos el chip de mora o
    suspensión queda solo con el ícono.
  - El aviso no aparece en `/app/settings/billing`.
- Componentes reutilizables (`features/saas/components/`):
  - `InvoicesTable`, con paginación de servidor, filtros y acciones por fila.
  - `CommissionsTable` y `CommissionsStatement` / `SettlementList`.
  - `UsageMeter` (contrato de meter de dataviz).
  - `StatusBadges`: `SubscriptionBadge`, `OrganizationBadge`, `InvoiceBadge`, `CommissionBadge` y
    `SettlementBadge`.
  - `ChangePlanDialog` / `PlanLimits`.
  - `PaymentMethodDialog`: tarjeta simulada, o tokenización de Wompi en modo real.
  - `AdminInvoiceActions`.
  - `charts.tsx`: `MonthlyColumns` (columnas apiladas con leyenda, tooltip y vista de tabla) y `SegmentStrip`. La
    paleta se validó con el validador de dataviz y pasa en claro y oscuro: `#b4583b` / `#3a6ea8` en claro,
    `#d4775c` / `#5b8fc7` en oscuro. Son variables CSS locales a la feature, porque los tokens compartidos no tienen
    colores de gráficos.
- `api.ts` exporta tipos y hooks (`useBillingStatus`, `useBillingOverview`, `useGettingStarted`, `usePublicPlans`,
  `useSignup`, hooks del admin…) y `tokenizeCard`.

## Dependencias nuevas (pip/npm) y por qué

Ninguna. Uso `recharts`, que ya estaba instalado; `saas` es la primera feature que lo usa.

## Cambios requeridos en archivos compartidos u otras apps (para C-INT)

1. **Bug en el `KpiTile` compartido** (`frontend/src/components/KpiTile.tsx`).
   - Síntoma: la tabla accesible del sparkline (`<table className="sr-only">`) ignora `width: 1px`, porque una tabla
     toma el ancho de su contenido. Mide unos 220 px desde el sparkline y, en la columna derecha de un grid,
     desborda el viewport: en `/admin` salían 57–67 px de scroll horizontal.
   - Arreglo sugerido: envolver la tabla en `<div className="sr-only">…</div>`, o poner `overflow-hidden` al
     contenedor `relative` del sparkline.
   - Mientras tanto, en mis tiles paso `className="relative overflow-hidden"`. Afecta a cualquier página que use
     sparklines en el borde derecho (C1, C10…).
2. **Reiniciar `beat`** al integrar, para que su horario estático incluya `saas.billing_cycle` (03:00) y
   `saas.commission_settlement` (día 1, 04:00). Beat estaba arriba desde antes y no lo reinicié por la regla de
   servicios compartidos.
3. No hace falta ningún `ENUM_NAME_OVERRIDES`: los serializers de saas exponen los choices como texto. Revisé
   `spectacular --validate` y los 10 avisos actuales son de otras apps.
4. Opcional (UX): al iniciar sesión, un dueño de una organización `suspended` aterriza en `/app` (Hoy), donde los
   widgets muestran el error 402. El aviso de saas lo lleva a pagar, pero C-INT podría redirigirlo directo a
   `/app/settings/billing` (en `homeFor` o en el guard).
5. Frontend compartido: ninguno. `i18n.test.ts` debería pasar (554 claves en paridad ES/EN). Los tests del shell no
   hacen peticiones nuevas, porque las fixtures usan organizaciones `active`.

## Seed (`apps/saas/seed.py`, en `SEED_ORDER` después de `ai`)

- Idempotente. Tarda 1,1 s desde cero y 0,1 s en la segunda corrida. Corre dentro de `seeding()`, así que los
  receivers no duplican nada.
- Planes: Starter (≤ 15, $149.000), Pro (≤ 60, $349.000) y Cadena (ilimitado, $899.000). El anual es 12 × −15 %.
- Casa Aurora con Pro y Grupo Andino con Cadena: activas, mensuales, con tarjeta simulada (VISA 4242 y
  MASTERCARD 5100). Cada una tiene **6 facturas pagadas** en orden cronológico (`HTP-2026-00001…`).
- Comisiones de **todas** las reservas del marketplace sembradas, con las mismas reglas que los receivers: 649 en
  total, 511 `pending`, 125 `settled` y **13 `reversed`** (canceladas sin penalidad).
- Julio y agosto liquidados y facturados (pagados); los meses siguientes quedan pendientes.
- Org **Hostal Demo Trial** (`owner@hostaldemo.co` / `housetel123`), en prueba con unos 9 días al sembrar, con una
  propiedad vacía (Santa Marta), impuestos y planes por defecto. Sirve para probar Primeros pasos y el onboarding con
  IA.
- Pruebas: dentro de una transacción revertida borré los datos de saas, corrí el seed dos veces (conteos iguales)
  y la BD quedó intacta. Después apliqué solo mi seeder sobre la BD de desarrollo para agregar las 13 comisiones
  revertidas que faltaban. No corrí `seed_demo`.

## Limitaciones conocidas / pendientes

- Sin tests nuevos (modo MVP). El plan pide cubrir: signup completo con slug único; comisión solo para marketplace
  confirmada; reversa; liquidación; ciclo de cobro con freezegun; 402 con billing accesible; reactivación; admin
  exige platform admin; plan por unidades; alerta de límite. Ya los ejercité en escenarios revertidos (ver
  "Verificación"): sirven de guion para la fase de tests.
- No hay prorrateo al cambiar de plan: el cambio aplica desde la próxima factura. Tampoco hay notas crédito: una
  factura se anula.
- Wompi real no se probó en vivo (no hay llaves de plataforma). La tokenización desde el navegador supone que Wompi
  permite CORS en `/tokens/cards`, que es lo que hace su propio widget.
- Las facturas de plataforma son documentos internos (PDF de Housetel S.A.S. con datos ficticios). No se emiten
  como factura electrónica DIAN: eso sería C7 aplicado a la plataforma.
- Los correos a dueños (mora, suspensión) son texto plano con `send_mail` (Mailpit). No usan plantillas de C6.
- La suplantación de soporte queda fuera de alcance, según el plan; el admin ve el detalle en solo lectura.
- `GET billing/invoices/` devuelve hasta 120 facturas, sin paginar.
- En `/signup` como anónimo, Chrome registra el 401 conocido de `/accounts/me/` (documentado en A3): la página
  consulta `/me` para avisar si ya hay una sesión.

---

## Cómo probarlo en la UI

Base `http://localhost:5173`. La clave de los usuarios demo es `housetel123`. Los datos del seed están cargados:
Casa Aurora y Grupo Andino activas, Hostal Demo Trial en prueba.

> Para los flujos que cambian estados (E y F), lo ideal es una organización nueva creada con el paso A, para no
> alterar las del seed. Si se usan las del seed, "Reactivar" y "Extender prueba" las devuelven a su estado.
> `seed_demo --reset` también las regenera.

**A. Registro de un hotel (anónimo) → Primeros pasos**
1. Abrir `/signup`. A la izquierda aparece el tablero de llaves en vivo: nombre, ciudad, una llave por unidad y la
   etiqueta del plan sugerido.
2. Paso 1: nombre ("Posada Prueba"), tipo, ciudad, departamento (opcional) y habitaciones (p. ej. 9). El plan
   sugerido cambia: ≤ 15 Starter, 16–60 Pro, más de 60 Cadena. Pulsar **Continuar**.
3. Paso 2: nombre, correo nuevo, celular (opcional), contraseña de 8 o más caracteres y aceptar términos. Pulsar
   **Crear mi cuenta**.
4. Esperado:
   - Toast de bienvenida y redirección a `/app/getting-started` con la sesión iniciada.
   - En la barra superior, el nombre del hotel y el chip azul "Prueba · 14 días".
   - "Llevas 0 de 7 pasos", la tarjeta "Crea tus habitaciones con ayuda de la IA" y los 7 pasos con sus botones.
   - Un correo repetido da el error en el campo; sin aceptar términos, el formulario no avanza.

**B. Primeros pasos con datos del seed**
- `owner@hostaldemo.co`, en `/app/getting-started`: 0 de 7, la caja "Te quedan N días de prueba · Plan Starter" y
  el paso 1 marcado como "Siguiente".
- `owner@casaaurora.co`: 6 de 7. Solo falta "Activa los pagos en línea", porque los pagos están en modo simulado.

**C. Plan y facturación del hotel** (`owner@casaaurora.co`, `/app/settings/billing`)
- Contenido:
  - Tarjeta del plan: Pro, Activa, $349.000 / mes + IVA 19 %, "Hasta 60 unidades · 2 propiedades".
  - Próximo cobro: 15 oct 2026, con Plan $349.000, IVA $66.310 y total $415.310.
  - Método de pago: VISA •••• 4242 y la insignia "Cobros simulados".
  - Uso: Unidades 24 de 60 y Propiedades 1 de 2.
  - Pestaña **Facturas**: 8 pagadas (suscripciones y 2 de comisiones). El ícono descarga el PDF.
  - Pestaña **Comisiones del marketplace**: cifras de este mes, por liquidar y liquidadas; "Comisión por hotel
    10 %"; liquidaciones de julio y agosto de 2026 (pagadas); últimas comisiones con código, estadía, base × 10 %,
    comisión y estado.
- **Cambiar plan**: Starter aparece deshabilitado con "No alcanza: tienes 24 unidades y este plan incluye hasta 15".
  Pasar a **Anual (−15 %)** y elegir Pro → el botón dice "Cambiar a Pro anual" → toast "Listo…" y la tarjeta muestra
  $3.559.800 / año. Se puede volver a mensual igual.
- **Cambiar tarjeta**: "Usar tarjeta de prueba" llena 4242…; al guardar sale el toast "Tarjeta terminada en 4242
  guardada". Una tarjeta inválida o vencida muestra el error en su campo.
- **Cancelar suscripción** (abajo): confirmar con motivo opcional → callout gris "Tu suscripción termina el 15 oct
  2026" con el botón **Seguir con Housetel** (reanuda).
- Permisos:
  - `recepcion@casaaurora.co` no ve "Plan y facturación" en Configuración.
  - `contabilidad@casaaurora.co` ve la página en solo lectura: sin Cambiar plan, tarjeta, Pagar ni Cancelar.

**D. Panel de plataforma** (`admin@housetel.co`; al iniciar sesión va a `/admin`)
- `/admin` (Resumen):
  - MRR de $1.248.000 en grande, ARR y "Si convierten las pruebas".
  - Tiles: organizaciones activas (+ en prueba), cancelaciones de 30 días, ventas del marketplace del mes y
    comisiones del mes, estas dos con sparkline.
  - Gráfico "Ingresos de la plataforma por mes": columnas apiladas de suscripciones (terracota) y comisiones (azul),
    con leyenda, tooltip por mes y botón "Ver tabla".
  - "Ventas del marketplace por mes" (azul).
  - Panel de organizaciones por estado (barra más lista), mezcla de planes, dinero por cobrar y "Requieren atención".
- `/admin/organizations`: 3 organizaciones con plan, estado, unidades (24/60, 82, 0/15), propiedades, usuarios, MRR
  y "Alta" (abr 2026 para las del seed). Tiene filtros de estado y plan, y búsqueda. Clic en una fila abre el detalle.
- Detalle de Casa Aurora: tiles de plan, MRR, unidades y renovación. Pestañas Suscripción (con el interruptor
  "Simular cobro fallido"), Propiedades, Equipo, Facturas (menú ⋯ en las abiertas: Cobrar ahora, Marcar como
  pagada, Anular) y Comisiones.
- `/admin/plans`: tarjetas de los 3 planes. **Editar** abre el formulario ES/EN con límites, precios y "Calcular:
  12 meses −15 %". **Nuevo plan** crea uno. Borrar un plan con suscripciones muestra el error "en uso".
- `/admin/billing`: "Por cobrar" y "Cobrado este mes", tabla de 16 facturas con filtros y búsqueda, y **Correr ciclo
  de cobro** (toast con el resumen). Abajo, la cuenta de cobro de la plataforma: modo Simulado / Real (Wompi), estado
  de las 4 variables `WOMPI_PLATFORM_*` (Falta), URL de eventos copiable y "Probar conexión".
- `/admin/commissions`: pendientes, liquidadas y revertidas (13). Tabla de 649 con filtros de estado, mes de
  causación y organización, y búsqueda por código. Liquidaciones de julio y agosto por organización. **Liquidar un
  mes** con agosto de 2026 no duplica nada (idempotente).

**E. Pago pendiente → pagar** (organización del paso A, o Hostal Demo Trial)
1. Como admin, en `/admin/organizations`, abrir la organización en prueba → **Terminar prueba ahora** → confirmar.
   Sin tarjeta, queda "Pago pendiente" con una factura abierta: $177.310 en Starter, $415.310 en Pro. Sale un toast
   de advertencia.
2. Iniciar sesión como su dueño:
   - La barra superior muestra el chip ámbar "Pago pendiente".
   - Abajo aparece el aviso "No pudimos cobrar tu suscripción · Tienes $ X por pagar…", con **Pagar ahora** y una X
     para ocultarlo.
   - En `/app/settings/billing`: callout ámbar "Tu pago está pendiente", con reintentos 1, 3 y 7 y la fecha del
     próximo; botón **Pagar HTP-… · $X**. La tarjeta "Saldo pendiente" y la factura "Por pagar" tienen su botón
     **Pagar**.
3. Pulsar Pagar → toast "Factura … pagada. ¡Gracias!". El estado pasa a Activa, el chip y el aviso desaparecen, y el
   próximo cobro queda a un mes.
4. Variante de fallo: el admin activa **Simular cobro fallido** en esa organización; el dueño agrega una tarjeta de
   prueba y paga → toast de error "Tarjeta rechazada (simulación…)" y la factura queda en "Cobro fallido".

**F. Suspensión y reactivación**
1. Como admin, en el detalle de la organización → **Suspender** → escribir su slug exacto (el diálogo lo muestra)
   y un motivo → Suspender. El estado pasa a Suspendida.
2. Como dueño:
   - Chip rojo "Cuenta suspendida" (en teléfono, solo el candado) y aviso rojo sin opción de ocultar.
   - Hoy y las demás páginas muestran "La organización está suspendida por falta de pago" (402).
   - `/app/settings/billing` sigue funcionando, con el callout rojo "Tu cuenta está suspendida" y la opción de pagar
     si hay facturas; si la suspendió el admin sin deuda, lo explica.
3. Como admin → **Reactivar** → la organización vuelve a "En prueba" (si su prueba seguía vigente) o a "Activa".
   **Extender prueba** suma de 1 a 90 días.

**G. Comisión de una reserva del marketplace** (flujo 5 del spec §10.1)
1. Reservar en el marketplace un hotel listado (p. ej. Casa Aurora) y pagar con la pasarela simulada.
2. Cuando la reserva queda confirmada, aparece una comisión `Pendiente` (10 % del alojamiento sin IVA):
   - como `owner@casaaurora.co`, en `/app/settings/billing` → Comisiones del marketplace, primera en "Últimas
     comisiones";
   - como admin, en `/admin/commissions`, buscándola por código.
3. Si se cancela desde el PMS sin penalidad, la comisión pasa a "Revertida". Si tiene penalidad, se recalcula sobre
   la penalidad ("Sobre la penalidad").

**H. Límite del plan**
- Si una organización supera las unidades de su plan (p. ej. más de 15 habitaciones en Starter), aparece la alerta
  "Superaste el límite del plan Starter" en Alertas, con enlace a Plan y facturación. En el uso, la barra de unidades
  se pone roja; nada se bloquea.

Vistas a revisar en 375 px: `/app/settings/billing`, `/app/getting-started`, `/signup` y `/admin`. Verifiqué que
no hay scroll horizontal y que las tablas desplazan dentro de su tarjeta. También revisé el modo oscuro de `/admin`
y de facturación.

---

## Verificación realizada (sin tests, modo MVP)

- **Backend**:
  - `manage.py check`: sin problemas.
  - `makemigrations saas --check --dry-run`: "No changes detected" (la migración `saas/0001` ya estaba aplicada).
  - `ruff check` y `ruff format --check` sobre `apps/saas`: limpios.
  - `spectacular --validate`: saas no agrega avisos.
- **curl por el proxy de Vite** (cookie jar + CSRF, script en el scratchpad): 38 de 38 OK en público, staff y admin.
  - Permisos: recepción recibe 403 en `billing/` y 200 en `billing/status/` y en getting-started; contabilidad ve
    billing pero recibe 403 al gestionar; un no-admin recibe 403 en `/admin/*`.
  - Suspender da 402 en `core/context` e inventario, mientras `billing/` y getting-started siguen en 200; luego
    reactivar y extender la prueba.
  - Signup completo (sesión iniciada, plan según unidades, tarjeta de prueba, email duplicado → 400).
  - `end-trial` con tarjeta queda `active` con la factura pagada; sin tarjeta queda `past_due`, el dueño paga y queda
    `active`.
  - Las organizaciones de prueba se borraron después.
- **Escenarios en transacción revertida**:
  - Prueba sin tarjeta: mora, reintentos +1, +3 y +7 días, suspensión, pago y activa.
  - Renovación de Casa Aurora con tarjeta.
  - Grupo Andino con fallo simulado: queda en mora.
  - Receivers: una tentativa de marketplace confirmada genera la comisión pendiente (base 1.372.800 → 137.280) y al
    cancelarla sin penalidad queda revertida. Una reserva directa no genera comisión.
  - La alerta `plan_limit` se levanta con 16 unidades en Starter.
- **Automatizaciones**: `automation.run("saas.billing_cycle", None)` y `automation.run("saas.commission_settlement",
  None)` terminan en `success`.
- **Seed**: probado dentro de una transacción revertida (ver "Seed").
- **Frontend**:
  - `npx tsc -p tsconfig.app.json --noEmit` sin errores en `src/features/saas`.
  - `npx eslint src/features/saas` limpio.
  - Paridad ES/EN comprobada con un script: 554 claves, sin claves usadas que falten.
  - Vite compila todos los módulos.
- **Revisión visual** con un Chrome headless propio (perfil y puerto aislados, por CDP):
  - Páginas: facturación (escritorio, 375 px, diálogos), Primeros pasos (prueba, Aurora, 375 px), las 6 páginas
    admin (escritorio y 375 px, más oscuro).
  - Flujos: registro completo desde la UI, estados de mora y suspensión, pago desde la UI, diálogos del admin
    (suspender escribiendo el slug, reactivar, terminar prueba, editar plan).
  - Consola sin errores, salvo los 402 esperados de otras funciones con la organización suspendida y el 401 conocido
    de `/me` en `/signup`. Sin desborde horizontal.
  - Correcciones hechas a partir de esa revisión:
    - grids que se ensanchaban con las tablas en móvil;
    - desborde del `KpiTile`;
    - leyenda del estado de organizaciones;
    - número centrado en las etiquetas de los pasos;
    - concordancia de textos;
    - orden de "Últimas comisiones";
    - aviso de suspensión sin deuda.
