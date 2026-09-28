# C8 — Revenue management — integration notes

Estado: **MVP completo y verificado sin tests** (modo MVP pedido por el usuario: sin TDD ni suites). Backend, API,
frontend, automatización, seed y aceptación funcionan de punta a punta con los datos del demo. Esta tarea retomó un
intento anterior que había dejado casi todo escrito: se evaluó, se completó y se corrigió (ver "Qué cambió en esta
sesión"). Sin dependencias nuevas, sin commits, `.env` intacto. Solo se tocaron `backend/apps/revenue/**`,
`frontend/src/features/revenue/**` y esta nota.

Lectura rápida para el orquestador: **"Cómo probarlo en la UI"** (al final) y "Cambios requeridos en archivos
compartidos" (C-INT).

---

## Qué hace

- **Reglas** por propiedad: ocupación on-the-books (tramos), anticipación (última hora / early-bird), día de la
  semana, festivos de Colombia y puentes (`holidays.CO`), eventos manuales. Cada regla aplica a todas las categorías
  o a algunas, tiene prioridad y se combina `stack` (suma) o `max` (gana el mayor ajuste).
- **Motor** `compute_recommendations`: por categoría × plan base × noche, desde la fecha de negocio y durante el
  horizonte, propone un precio con razones legibles, explicación determinística ES/EN, límites (`PriceBounds`), cambio
  máximo diario y umbral mínimo.
- **Recomendaciones** `pending → approved/applied | rejected | auto_applied | expired`. Aprobar escribe la grilla con
  `rates.set_daily_rates(source="revenue")`, agrupando noches contiguas con el mismo precio (un evento de auditoría
  reversible `rates.bulk_update` por grupo).
- **Corridas** (`RevenueRun`): programadas (`revenue.run_rules`), manuales ("Correr ahora") o del seed, con resumen
  determinístico y **resumen IA** (`get_llm(property).generate(...)`, escrito en segundo plano tras el commit).
- **Explicación IA por noche** bajo demanda ("Explicar con IA" en el detalle; `POST recommendations/{id}/explain/`).
- **Auto-aplicar** por propiedad (con confirmación en la UI): cada corrida aplica sus recomendaciones como
  `auto_applied` y la auditoría queda con `source="automation"`.

### Algoritmo del motor (`services/engine.py`)

1. Pares (categoría activa × plan **base** activo que la vende). Los planes derivados siguen solos a su base.
2. Precio actual por noche: `rates.resolve_daily` (DailyRate → temporada → defaults). Noches sin precio
   (`source="none"`) o sin unidades vendibles se omiten.
3. **Ancla** (precio de referencia): el precio resuelto ignorando lo que escribió revenue. Una noche con
   `source="revenue"` vuelve a su precio de temporada/default, salvo que el precio que revenue reemplazó fuera
   manual/bulk/canal (se recuerda en la última recomendación aplicada: `anchor_source`).
4. Hechos de la noche: ocupación = `sold / (total − blocked)` de `InventoryDay` (tope 100 %), días de anticipación
   desde la fecha de negocio, día de la semana, festivo / puente (sábado y domingo antes de un lunes festivo).
5. Reglas: las `stack` se suman; de las `max` cuenta solo la de mayor ajuste (empate: mayor prioridad). Total nunca
   baja de −90 %.
6. Objetivo = ancla × (1 + total/100) → **cambio máximo diario** ±`max_daily_change_percent` alrededor del precio de
   la noche al empezar el día → **`PriceBounds`** (mínimo/máximo duros; ganan sobre el cambio diario) → redondeo
   comercial a múltiplos de `price_rounding` (1.000 COP por defecto) sin salirse de los límites.
7. **Umbral**: si `|cambio| < min_change_percent` (2 % por defecto) del precio actual no se recomienda.
8. Almacenamiento: a lo sumo **una pendiente por noche** (restricción única parcial). Una propuesta igual a la
   pendiente la refresca; una distinta la reemplaza (la vieja vence); una igual a la última **rechazada** no se
   vuelve a proponer; las pendientes que ya no se proponen vencen. Las de noches pasadas vencen en cada corrida y al
   intentar decidirlas.

---

## API implementada

Base `/api/v1/revenue/`, solo staff, encabezado `X-Property-Id`. `revenue.view` lee; `revenue.manage` configura,
decide, corre y simula (excepción: `explain` pide solo `revenue.view`). Errores con la forma de A1
(`{detail, code, fields?}`). Dinero y porcentajes como string con 2 decimales. Fechas `YYYY-MM-DD`; los rangos
`start/end` son `[start, end)` salvo `event.end` (inclusivo, como las temporadas).

| Método y path | Permiso | Notas |
|---|---|---|
| `GET settings/` · `PATCH settings/` | view · manage | se crean con defaults al primer acceso; PATCH audita `revenue.settings_updated` |
| CRUD `rules/` (sin paginar) | view · manage | filtros `kind`, `is_active`; `params` validados por tipo (400 `invalid_rule_params` con `fields.params`); categorías de otra propiedad → 400 en `room_types`; audita `revenue.rule_created/updated/deleted` |
| CRUD `bounds/` (sin paginar) | view · manage | **POST hace upsert** por (categoría, plan): 201 crea / 200 actualiza; solo planes base; `min ≤ max`; al menos uno |
| `GET recommendations/?start&end&status&room_type&rate_plan&ordering&page&page_size` | view | paginado; `status` repetible; `end` exclusivo; `ordering` = `date`, `change_percent`, `recommended_price`, `created_at` (con `-`) |
| `GET recommendations/{id}/` | view | detalle |
| `GET recommendations/calendar/?start&end&lang` | view | heatmap: filas categoría × plan base, celdas por noche (la pendiente, si no la última decidida; sin vencidas); máx. 186 noches |
| `GET recommendations/summary/` | view | KPIs de las pendientes desde la fecha de negocio + última corrida |
| `POST recommendations/approve/` `{ids}` | manage | aprueba **y aplica** pendientes |
| `POST recommendations/reject/` `{ids}` | manage | rechaza pendientes |
| `POST recommendations/apply/` `{ids}` | manage | aplica pendientes o aprobadas que no se pudieron escribir (reintento) |
| `POST recommendations/{id}/explain/` | view | explicación IA (caché 24 h); sin IA devuelve la determinística con `simulated: true` |
| `GET runs/` · `GET runs/{id}/` | view | historial paginado, más reciente primero |
| `POST run-now/` | manage | corre ahora vía `automation.run("revenue.run_rules")` (queda en AutomationRun + auditoría); 409 `revenue_disabled` si está apagado; 201 con la corrida |
| `POST simulate/` `{start?, end?, rule?}` | manage | lo que dejaría una corrida ahora, **sin guardar**; `rule` = borrador (con `id` reemplaza una guardada; `is_active: false` la quita) |
| `GET options/` | view | categorías activas y planes base activos con el precio por defecto de cada categoría (editor de reglas y tabla de límites) |

### Payloads

```json
GET settings/
{"enabled": true, "auto_apply": false, "horizon_days": 120, "max_daily_change_percent": "20.00",
 "min_change_percent": "2.00", "price_rounding": "1000.00", "updated_at": "2026-09-27T11:00:06-05:00"}
PATCH settings/ {"auto_apply": true}            → mismo objeto
   horizon_days 7–365 · max_daily_change_percent 1–100 · min_change_percent 0–50 · price_rounding 0–1.000.000
```

```json
POST rules/
{"name": "Ocupación", "kind": "occupancy", "room_types": [], "priority": 40, "combine": "stack", "is_active": true,
 "params": {"tiers": [{"min": 0, "max": 40, "adjust": -8}, {"min": 70, "max": 85, "adjust": 8},
                      {"min": 85, "max": 100, "adjust": 15}]}}
→ 201 {"id": "…", …mismos campos…, "created_at": "…", "updated_at": "…"}
```

`params` por tipo (ajustes en % sobre el ancla, de −90 a +300):

| kind | params |
|---|---|
| `occupancy` | `{"tiers": [{"min", "max", "adjust"}]}` — 0–100 %, `min` inclusivo, `max` exclusivo (un tramo que termina en 100 incluye el 100), sin solapes |
| `lead_time` | `{"last_minute": [{"max_days", "adjust"}], "early_bird": [{"min_days", "adjust"}]}` — gana la ventana de última hora más estrecha o la early-bird más amplia; las early-bird empiezan después de las de última hora; días enteros ≤ 730 |
| `day_of_week` | `{"fri": 5, "sat": 10}` — claves `mon…sun` |
| `holiday` | `{"adjust": 12, "include_bridges": true}` |
| `event` | `{"name": "Festival", "start": "2027-01-07", "end": "2027-01-12", "adjust": 20}` — `end` inclusivo, máx. 366 noches |

```json
POST bounds/  {"room_type": "<uuid>", "rate_plan": "<uuid base>", "min_price": "240000", "max_price": "512000"}
→ 201|200 {"id": "…", "room_type": "…", "rate_plan": "…", "min_price": "240000.00", "max_price": "512000.00",
           "updated_at": "…"}
```

Recomendación (lista, detalle, respuestas de decisión y de `simulate`, donde `id` es `null`):

```json
{"id": "…", "date": "2026-10-31", "status": "pending",
 "room_type": {"id": "…", "code": "STE", "name": {"es": "Suite Vista al Mar", "en": "Sea View Suite"}, "color": "#B4583B"},
 "rate_plan": {"id": "…", "code": "FLEX", "name": {"es": "Tarifa flexible", "en": "Flexible rate"}},
 "current_price": "747500.00", "current_source": "default", "anchor_price": "747500.00", "anchor_source": "default",
 "recommended_price": "897000.00", "change_percent": "20.00", "adjustment_percent": "28.00",
 "occupancy": "83.33", "available_units": 1,
 "reasons": [
   {"type": "rule", "rule_id": "…", "name": "Ocupación", "kind": "occupancy", "combine": "stack", "adjust": "8.00",
    "applied": true, "detail": {"occupancy": "83.33"}},
   {"type": "rule", "name": "Festivos y puentes", "kind": "holiday", "adjust": "12.00", "applied": true,
    "detail": {"bridge": true, "name_es": "Día de Todos los Santos (observado)", "name_en": "All Saints' Day (observed)"}, "…": "…"},
   {"type": "rule", "name": "Sábados", "kind": "day_of_week", "adjust": "8.00", "applied": true, "detail": {"weekday": "sat"}, "…": "…"},
   {"type": "limit", "kind": "max_daily_change", "percent": "20.00", "price": "897000.00"}],
 "explanation": {"es": "Sube 20 % (de $ 747.500 a $ 897.000): ocupación del 83,33 % (+8 %); puente de Día de Todos los Santos (observado) (+12 %); sábado (+8 %); limitado al cambio máximo de 20 %.",
                 "en": "Up 20% (from $747,500 to $897,000): 83.33% occupancy (+8%); long weekend: All Saints' Day (observed) (+12%); Saturday (+8%); capped at the 20% maximum change."},
 "decided_by": null, "decided_at": null, "applied_at": null, "apply_error": "", "run": "…", "created_at": "…"}
```

- `reasons[].type = "rule"`: `detail` según el tipo — `occupancy`; `lead_days`, `window` (`last_minute|early_bird`),
  `days`; `weekday`; `name_es`, `name_en`, `bridge`; `name` (evento). `applied: false` = regla `max` que perdió.
- `reasons[].type = "limit"`: `kind` = `max_daily_change` (con `percent`) | `min_price` | `max_price`, `price` resultante.
- `change_percent` es contra el precio actual; `adjustment_percent` es la suma de reglas sobre el ancla.

```json
GET recommendations/calendar/?start=2026-09-27&end=2026-09-30&lang=es
{"start": "2026-09-27", "end": "2026-09-30", "business_date": "2026-09-27", "currency": "COP",
 "dates": ["2026-09-27", "2026-09-28", "2026-09-29"], "holidays": [{"date": "2026-10-12", "name": "Día de la Raza"}],
 "rows": [{"room_type": {…}, "rate_plan": {…},
           "cells": {"2026-09-28": {"id": "…", "status": "pending", "change_percent": "-5.00",
                                    "current_price": "320000.00", "recommended_price": "304000.00", "occupancy": "66.67"}}}]}
```

```json
GET recommendations/summary/
{"pending": 247, "up": 167, "down": 80, "avg_change_percent": "4.74", "estimated_impact": "2225400.00",
 "impact_up": "25294600.00", "impact_down": "-23069200.00", "first_date": "2026-09-27", "currency": "COP",
 "enabled": true, "auto_apply": false, "last_run": {…corrida…}}
```

Impacto estimado = Σ (recomendado − actual) × unidades libres de cada noche (si se vendieran las libres al precio
recomendado). Se reporta dividido en subidas y bajadas: una bajada en una noche vacía lo hace negativo a propósito.

```json
POST recommendations/approve/ {"ids": ["…", "…"]}           (igual reject/ y apply/)
→ 200 {"updated": 2, "skipped": [{"id": "…", "reason": "not_found|not_pending|expired"}],
       "errors": [{"id": "…", "code": "no_rate", "detail": "…"}], "recommendations": [ …las que cambiaron… ]}
```

Una aprobación cuya escritura falla queda `approved` con `apply_error` y se reporta en `errors` (se reintenta con
`apply/`). Solo toca recomendaciones de la propiedad del encabezado (las demás → `not_found`). Máx. 1000 ids.

```json
POST recommendations/{id}/explain/
→ 200 {"id": "…", "text": {"es": "Sugerimos subir la tarifa del martes 8 de diciembre de $ 260.000 a $ 312.000 …",
                           "en": "We recommend increasing the rate for Tuesday, December 8 …"},
       "provider": "gemini", "simulated": false}
   (sin IA: "text" = explicación determinística, "provider": "", "simulated": true)
```

Corrida (`runs/`, `run-now/`, `summary.last_run`):

```json
{"id": "…", "started_at": "…", "finished_at": "…", "status": "success", "trigger": "manual|automation|seed",
 "triggered_by": {"id": "…", "full_name": "Valentina Rojas", "email": "owner@casaaurora.co"},
 "start_date": "2026-09-27", "end_date": "2027-01-25", "recommendations_count": 250, "auto_applied_count": 0,
 "expired_count": 0, "summary": {"es": "Se revisaron las noches del 27/09/2026 al 24/01/2027: 250 recomendaciones …", "en": "…"},
 "ai_summary": {"es": "…", "en": "…"}, "ai_provider": "gemini",
 "details": {"ai_status": "pending|done|unavailable|skipped", "count": 250, "up": 169, "down": 81,
             "avg_change_percent": "4.73", "estimated_impact": "…", "impact_up": "…", "impact_down": "…",
             "rules": [{"name": "Ocupación", "count": 219}], "room_types": […],
             "top": [{"date": "…", "room_type": "STE", "change_percent": "20.00", "current_price": "…",
                      "recommended_price": "…", "reasons": ["Ocupación", "Festivos y puentes"]}], "…": "…"}}
```

`ai_summary` = el resumen determinístico hasta que la IA responda; `ai_provider` vacío = no hubo IA (la UI muestra
"Resumen automático"). `details.ai_status`: `pending` (escribiéndose), `done`, `unavailable` (simulado, cuota, red),
`skipped` (seed).

```json
POST simulate/ {"rule": {"name": "Borrador", "kind": "day_of_week", "params": {"fri": 10}, "combine": "stack",
                         "priority": 5, "is_active": true, "room_types": []}}
→ 200 {"start": "2026-09-27", "end": "2027-01-25",
       "summary": {"count": 258, "up": 183, "down": 75, "avg_change_percent": "5.96", "estimated_impact": "…",
                   "impact_up": "…", "impact_down": "…"},
       "recommendations": [ …con "id": null… ]}
```

```json
GET options/
{"currency": "COP", "business_date": "2026-09-27",
 "room_types": [{"id": "…", "code": "DBL", "name": {…}, "color": "#4E6C88", "kind": "private"}],
 "rate_plans": [{"id": "…", "code": "FLEX", "name": {…}, "room_types": ["…"], "default_prices": {"<rt id>": "320000.00"}}]}
```

## Modelos (`apps/revenue/models.py`, migración `0001_initial`, ya aplicada)

`RevenueSettings` (1-1 propiedad: `enabled`, `auto_apply`, `horizon_days`, `max_daily_change_percent`,
`min_change_percent`, `price_rounding`), `PricingRule`, `PriceBounds` (único por categoría+plan, `min ≤ max`),
`RevenueRun` (+ `trigger`, `triggered_by`, rango, contadores, `summary`/`ai_summary` i18n, `ai_provider`,
`details`) y `RateRecommendation` (+ `current_source`, `anchor_source`, `adjustment_percent`, `occupancy`,
`available_units`, `applied_at`, `apply_error`; única pendiente por (categoría, plan, noche)). Todo en el admin de
Django (corridas y recomendaciones de solo lectura).

## Contratos implementados / consumidos

Consumidos (sin escribir en modelos ajenos):
- `rates.services.quote.resolve_daily` (precio actual) y **`set_daily_rates(..., source="revenue", actor=...)`**
  (escritura; sin actor la auditoría queda `source="automation"`).
- Lectura de helpers de rates: `rates.services.resolution.configured_price/load_defaults/season_rates_for` (precio
  de temporada/default para el ancla), `rates.services.calendar.holiday_list` (festivos del heatmap).
- `bookings.services.availability.availability_by_date` (materializa `InventoryDay` del rango) + lectura ORM de
  `InventoryDay` (ocupación on-the-books).
- `apps.ai.llm.get_llm(property).generate(messages, system=..., response_schema={es, en}, temperature=0.3)` para el
  resumen de corrida y la explicación por noche; si el resultado es `simulated` o falla, se usa la plantilla.
- `core.automation`, `core.audit`, `core.signals.is_seeding`, `core.money.quantize`.

Servicios de `revenue` que otras apps pueden llamar:
- `apps.revenue.services.engine.compute_recommendations(property, *, start, end, persist=True)` (con
  `persist=False` devuelve las propuestas sin guardar).
- `apps.revenue.services.runs.run_revenue(property, *, trigger="automation", actor=None, use_ai=True) -> RevenueRun`.
- `apps.revenue.services.decisions.approve/reject/apply(property, ids, *, actor) -> DecisionResult`.
- `apps.revenue.services.summary.ai_explanation(rec)` y `ask_llm(...)`.
- Para C9 (anomalía "tarifa fuera de límites"): `PriceBounds` por (categoría, plan base) se lee por ORM.
- Para C10 / C1: `GET recommendations/summary/` da los KPIs de pendientes.

## Señales emitidas / escuchadas

- Emitidas: ninguna propia. Aprobar/auto-aplicar llama `set_daily_rates`, que emite `rates_changed` (C3 la usa para
  el ARI).
- Escuchada: `rates_changed` → vencen las recomendaciones **pendientes** de esas categorías/planes/noches cuyo
  precio actual ya no coincide con el de la noche (p. ej. alguien lo cambió a mano en la grilla); la próxima corrida
  propone de nuevo. Ignorada con `is_seeding()`.

Auditoría: `revenue.settings_updated`, `revenue.rule_created/updated/deleted`, `revenue.bounds_saved/deleted`,
`revenue.recommendations_approved/rejected` (con `count`, `ids`, `errors`, rango), más el `rates.bulk_update`
reversible de cada grupo aplicado (se deshace con el undo genérico de C12) y `automation.revenue.run_rules`.

## Automatizaciones registradas

| Código | Horario | Qué hace |
|---|---|---|
| `revenue.run_rules` | `crontab(minute=0, hour="5,11,17,23")` (05:00 y cada 6 h) | Si revenue está activo: vence pendientes de noches pasadas, corre el motor sobre `[fecha de negocio, + horizonte)`, guarda las recomendaciones, auto-aplica si está activado y deja el resumen (la IA en segundo plano). Desactivado → `skipped`. Params: `ai_summary` (default `true`); "Correr ahora" pasa además `trigger="manual"` y `triggered_by` |

## Proveedores de integración registrados

Ninguno (usa el LLM de C9 por el contrato `get_llm`).

## Extensiones de frontend exportadas

- `routes.tsx`: `/app/revenue` (lazy `pages/RevenuePage`), con pestañas en `?tab=rules|bounds|history|settings`
  (sin parámetro = recomendaciones).
- `nav.ts`: sin cambios respecto a A2 (`revenue`, sección `revenue`, `revenue.view`).
- `widgets.tsx`: `revenue-recommendations` (order 50, size `md`, `revenue.view`) → tarjeta "Recomendaciones de
  precio" del panel Hoy: las próximas 4 pendientes con aprobar en un clic (cada una o todas) y enlace a la página.
  Carga perezosa (`RecommendationsWidgetSlot`).
- Piezas reutilizables (import directo, no son extensiones §E): `features/revenue/api.ts` (tipos exactos y hooks
  `useRevenueSummary`, `useUpcomingRecommendations`, `useDecision`, …), `lib/scale.ts` (escala divergente
  `stepOf`/`STEP_CLASS`), `lib/format.ts` (`signedPercent`, `compactMoney`).

### UI (`/app/revenue`)

- Encabezado con **Correr ahora** (solo `revenue.manage`); avisos si revenue está apagado o si auto-aplicar está
  activo.
- **Recomendaciones**: KPIs (pendientes con cuántas suben/bajan, cambio medio, impacto estimado con subidas/bajadas,
  primera noche con cambio), tarjeta de la última corrida con su resumen (insignia "Resumen IA · Gemini", "Resumen
  automático" o "Escribiendo el resumen con IA…" mientras llega; la página consulta cada 2,5 s hasta 90 s), barra
  (rango 14/30/60 noches navegable desde la fecha de negocio, vista **Mapa/Lista**, "Mostrar decididas",
  "Seleccionar las N pendientes"), **heatmap** categoría × noche con el % recomendado impreso en cada celda
  (festivos con punto y nombre, fines de semana sombreados, hoy marcado, cambio de mes), leyenda de la escala y de
  estados, **detalle** de la noche (precio actual → recomendado, ocupación, unidades libres, referencia, total de
  reglas, cada regla con su ajuste, límites que la frenaron, explicación y **Explicar con IA**), aprobar/rechazar
  una o en masa (barra de selección fija abajo). Teclado: flechas/Home/End mueven el foco y el detalle; Espacio/Enter
  selecciona; encabezados de fila y de noche seleccionan sus pendientes.
- **Reglas**: tarjetas dibujadas por tipo (barra 0–100 % de tramos, semana, ventanas, festivo, evento), encender/
  apagar, editar/borrar; editor lateral con constructor visual por tipo, categorías, combinación, prioridad y
  **Probar con los datos de hoy** (`simulate/`, sin guardar).
- **Límites**: tabla por categoría × plan base con el precio por defecto de referencia, mínimo/máximo (con % del
  default), guardar y quitar.
- **Historial**: corridas paginadas con disparador, rango, cifras, resumen (IA o automático) y "Cambios más grandes".
- **Ajustes**: activar revenue, **aplicar automáticamente** (diálogo de confirmación al activar), horizonte, cambio
  máximo diario, cambio mínimo y redondeo.
- Escala del heatmap (skill dataviz, validada con `validate_palette.js`): divergente pizarra (bajar) ↔ terracota
  (subir) con punto medio piedra del sistema, 3 pasos iguales por brazo (< 6 %, 6–12 %, ≥ 12 %), luminosidad
  monótona con saltos ≥ 0,06 (incluido neutro → primer paso) en claro y oscuro, texto ≥ 4,96:1 en todos los pasos.
  El paso más pálido se acerca a la superficie a propósito ("casi cero", como en heatmaps secuenciales); el valor
  impreso, la leyenda y la vista Lista (tabla) son el canal redundante, así que el color nunca va solo.
- i18n ES/EN completo (paridad verificada), tema claro/oscuro, responsive desde 375 px (tabs y tablas con scroll
  interno, heatmap con primera columna fija y scroll propio).

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps (para C-INT)

1. **`config/settings.py` › `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]`** (los choices `kind`/`status` chocan
   con los de otras apps). Verificado con un settings temporal fuera del repo: con estas entradas los enums de
   revenue quedan con nombre estable:
   ```python
   "PricingRuleKindEnum": "apps.revenue.models.PricingRule.Kind",
   "RateRecommendationStatusEnum": "apps.revenue.models.RateRecommendation.Status",
   "RevenueRunStatusEnum": "apps.revenue.models.RevenueRun.Status",
   ```
2. **Reiniciar `worker` y `beat`** al integrar: el worker lleva horas con la versión del código de revenue de esta
   mañana (sin el resumen IA en segundo plano ni `details.ai_status`). Beat ya programa `revenue.run_rules`.
3. **Tests compartidos del shell (A2)**: si `shell.test.tsx`/`router.test.tsx` renderizan el panel Hoy con los
   widgets reales, el de revenue pide `GET /api/v1/revenue/recommendations/summary/` y
   `GET /api/v1/revenue/recommendations/?status=pending…`: agregar handlers vacíos
   (`{pending: 0, …, last_run: null}` y `{count: 0, next: null, previous: null, results: []}`).
4. Nada que cambiar en otras apps.

## Limitaciones conocidas / pendientes

- **Tests**: los archivos de `backend/apps/revenue/tests/` y `frontend/src/features/revenue/__tests__/` vienen del
  intento anterior y **no se corrieron** en esta fase (modo MVP). Pueden necesitar ajustes (p. ej. `details` ahora
  incluye `ai_status`; `test_seed.py` ya esperaba el arreglo del seed). Se escriben/ajustan en la fase de tests.
- Resumen IA en un **hilo en segundo plano** del proceso web/worker (bajo `settings.TESTING` va en línea). Si el
  proceso se reinicia en plena llamada, la corrida queda con `ai_status="pending"`: la UI deja de esperar a los 90 s
  y muestra el resumen automático. Para producción conviene pasarlo a una tarea Celery (D1).
- **Explicar con IA** es síncrono: con Gemini tarda 5–25 s (el botón muestra "La IA está escribiendo…"); se cachea
  24 h por recomendación. En desarrollo, con varios agentes editando código, `runserver` se recarga seguido y una
  petición larga puede devolver 502: reintentar.
- El impacto estimado es una aproximación transparente (unidades libres × diferencia de precio), sin elasticidad.
- Los nombres de las reglas son datos del hotel (no se traducen): en inglés, las razones muestran "Ocupación",
  "Sábados"… tal como se crearon.
- Solo planes base reciben recomendaciones (los derivados las siguen por su regla de derivación).
- `simulate/` devuelve lo que propone el motor sin la memoria de rechazos: puede contar alguna noche más que una
  corrida real (una corrida no vuelve a proponer el mismo precio que se rechazó para esa noche).
- En pantallas angostas el detalle de la noche queda debajo del mapa (no hay hoja inferior): tras tocar una celda
  hay que bajar para verlo; la barra de selección sí queda fija abajo.
- Estado actual de la BD de desarrollo (útil para validar): corridas manuales hechas en las tres propiedades; en
  Casa Aurora se aprobaron **DBL 2 y 3 de octubre de 2026 a $ 397.000** (la grilla los muestra con fuente
  `revenue`) y se rechazó **DBL 27 de septiembre**; quedan ~247 pendientes. El LLM de **Casa Aurora está en modo
  `simulated`** (lo cambió otro agente a las 15:43 hora Bogotá), por eso allí el resumen sale "automático"; **Andino
  Medellín** tiene el resumen de Gemini. El seed completo (C-INT) recrea todo desde cero.

---

## Cómo probarlo en la UI

App en **http://localhost:5173**. Usuario demo **owner@casaaurora.co / housetel123** (Hotel Casa Aurora). Para ver la
IA real: **owner@grupoandino.co / housetel123** → propiedad Andino Medellín (selector de propiedad arriba).

1. **Entrar**: `/login` → sidebar, sección de revenue → **Revenue** (`/app/revenue`).
   Esperado: título "Revenue", botón **Correr ahora**, 4 KPIs (Pendientes ≈ 247 · "167 suben · 80 bajan", Cambio
   medio ≈ +4,7 %, Impacto estimado "$ 2,2 M" con "Subidas … · bajadas …", Primera noche con cambio), tarjeta
   "Última corrida · hace … · Manual por Valentina Rojas" con el resumen.
2. **Correr reglas**: clic en **Correr ahora**. Esperado: en ~1 s el toast "Corrida lista: N recomendaciones
   pendientes"; la tarjeta muestra la insignia "Escribiendo el resumen con IA…" y luego "Resumen IA · Gemini" (en
   Andino Medellín, ~10–20 s) o "Resumen automático" (Casa Aurora, LLM simulado). La pestaña Historial suma la
   corrida.
3. **Heatmap**: filas Estándar/Superior/Suite Vista al Mar × 30 noches desde la fecha de negocio. Celdas terracota =
   subir, pizarra = bajar, con el % impreso (p. ej. "+20", "−5"); columna del **12 oct** con punto y nombre "Día de
   la Raza" al pasar el mouse; fines de semana sombreados. Cambiar a **14 / 60 noches**, avanzar/retroceder y **Hoy**.
   Alternar **Mapa / Lista** (la lista es una tabla con los mismos datos).
4. **Detalle**: clic en una celda (p. ej. Suite, **sábado 31 oct**, "+20"). Esperado en el panel derecho (debajo del
   mapa en pantallas angostas): "$ 747.500 → $ 897.000 +20 %", ocupación 83,33 %, 1 unidad libre, "Referencia
   $ 747.500 (precio por defecto) · reglas +28 %", reglas Ocupación +8 %, Festivos y puentes +12 % ("Puente de Día de
   Todos los Santos"), Sábados +8 %, el límite "Tope de cambio diario de 20 %: el precio se queda en $ 897.000" y la explicación. **Explicar con IA** → texto de la
   IA con insignia "Explicación IA · Gemini" (Andino) o el aviso "La IA no está disponible…" con **Reintentar**
   (Casa Aurora).
5. **Aprobar una** (flujo E2E #11): en el detalle, **Aprobar y aplicar**. Esperado: toast "1 recomendación aprobada
   y aplicada a la grilla", la celda pasa a borde con ✓ (con "Mostrar decididas" activo) y el KPI de pendientes baja
   en 1. Clic en **Ver la grilla de tarifas** → `/app/rates` (plan FLEX): esa noche muestra el precio nuevo con la
   tinta azul de la fuente `revenue`. Referencia ya aplicada: Estándar 2 y 3 oct = $ 397.000.
6. **Masivo**: clic en varias celdas pendientes (o en el ícono de lista al lado del nombre de una fila, o en el
   encabezado de una noche) → barra fija abajo "N seleccionadas · X suben · Y bajan" → **Rechazar** o **Aprobar y
   aplicar**. **Seleccionar las N pendientes** toma todas las visibles. Las rechazadas quedan tachadas.
7. **Reglas** (`?tab=rules`): 5 tarjetas (Ocupación con barra de tramos, Festival de Música de Cartagena 7–12 ene
   +20 %, Festivos y puentes +12 %, Última hora ≤ 3 días −5 %, Sábados +8 %). Apagar una con su interruptor (toast).
   **Nueva regla** → tipo **Evento** → nombre, fechas, ajuste → **Probar con los datos de hoy** (muestra "Una
   corrida ahora dejaría N recomendaciones (…), cambio medio …, impacto …" sin guardar) → **Crear regla**. Editar y borrar (diálogo de
   confirmación). Validaciones: tramos solapados, ajuste fuera de −90…+300, fechas invertidas.
8. **Límites** (`?tab=bounds`): Estándar $ 240.000–$ 512.000, Superior $ 315.000–$ 672.000, Suite $ 488.000–
   $ 1.040.000 (75 %–160 % del default, con el % debajo). Cambiar uno → **Guardar** (toast); mínimo > máximo → error
   en la fila.
9. **Historial** (`?tab=history`): corridas (Manual/Programada/Datos de demo) con rango, cifras, resumen y
   "Cambios más grandes" desplegable.
10. **Ajustes** (`?tab=settings`): activar **Aplicar automáticamente** → diálogo "¿Aplicar las recomendaciones
    automáticamente?" → **Activar** → aparece el aviso azul arriba y el KPI dice "Aplicar automáticamente:
    activado" (desactivarlo después para no mover precios). Cambiar "Cambio mínimo (%)" → **Guardar cambios**.
    Apagar "Revenue management activo" → aviso amarillo y **Correr ahora** deshabilitado (volver a activarlo).
11. **Panel Hoy** (`/app`): tarjeta "Recomendaciones de precio" con las próximas pendientes, ✓ por fila y
    **Aprobar las 4** (si C1 muestra los widgets).
12. **Permisos**: `recepcion@casaaurora.co` ve Revenue en solo lectura (sin Correr ahora, sin selección ni botones
    de decisión, ajustes bloqueados con aviso); `limpieza@casaaurora.co` no ve Revenue (la API responde 403).
13. **Idioma / tema / móvil**: cambiar a inglés (todo traducido, festivos en inglés en el heatmap), modo oscuro
    (la escala tiene sus propios pasos) y 375 px (pestañas y heatmap con scroll interno, sin scroll horizontal de
    página, barra de selección abajo).

---

## Qué cambió en esta sesión (sobre el intento anterior)

- **Resumen IA en segundo plano**: antes "Correr ahora" esperaba a Gemini dentro del request (8–25 s). Ahora la
  corrida responde en < 1 s y el resumen llega después (`details.ai_status`); la UI muestra "Escribiendo el resumen
  con IA…" y consulta hasta que llega.
- **Explicación IA por noche**: nuevo `POST recommendations/{id}/explain/` + bloque "Explicar con IA" en el detalle
  (el plan pide "detalle con razones y explicación IA").
- Prompt del resumen: formato de dinero/porcentajes/fechas por idioma y aclaración del impacto negativo de las
  bajadas (Gemini escribía "-7,140,900.00 COP" y "20.00%").
- **Seed**: crea su corrida inicial si no hay una corrida *del seed* (antes, una corrida programada previa sin
  reglas dejaba el demo sin recomendaciones: es lo que pasó hoy en la BD de desarrollo).
- "Correr ahora" con auto-aplicar activo avisa "N precios aplicados automáticamente a la grilla" (antes decía
  "pendientes"). Las llamadas al LLM se etiquetan `feature="revenue"` en el registro de uso de C9 (si el cliente
  lo soporta).
- Ruff limpio (`check` + `format`) en `apps/revenue`.

## Verificación hecha (sin tests)

- `docker compose exec -T backend python manage.py check` → sin problemas; `makemigrations revenue --check
  --dry-run` → "No changes detected"; `ruff check apps/revenue` y `ruff format --check apps/revenue` → limpios.
- Curl por el proxy de Vite (cookie jar + CSRF, `owner@casaaurora.co`, `owner@grupoandino.co`,
  `recepcion@casaaurora.co`, `limpieza@casaaurora.co`): los 16 endpoints responden; `simulate` no persiste
  (pendientes iguales antes/después); `run-now` 201 en ~0,7 s con 250 recomendaciones y el resumen de Gemini en
  ~16 s (Andino Medellín); aprobar 2 noches contiguas → `applied` y la grilla de tarifas las muestra a $ 397.000 con
  `source: "revenue"`; re-aprobar → `not_pending`; rechazar; `apply` de rechazada/inexistente → `skipped`; `ids: []`
  → 400; CRUD de reglas (válidas e inválidas: solape, fechas, ajuste), upsert de límites (200) y min > max (400),
  PATCH de ajustes (y 400 con horizonte 2); recepción: lecturas 200, `run-now`/`approve`/`settings` 403;
  housekeeping 403; dueño de otra organización → 404 y categoría ajena → 400; `explain` con IA (Gemini, texto ES/EN)
  y sin IA (determinística, `simulated: true`).
- `automation.run("revenue.run_rules", <hostel>)` desde `manage.py shell` → `success`, 411 recomendaciones.
- En transacciones revertidas: auto-aplicar (234 `auto_applied`, filas `DailyRate` `source="revenue"`, 152 eventos
  `rates.bulk_update` con `source="automation"`, segunda corrida sin cambios), vencimiento al avanzar la fecha de
  negocio (3 vencidas), receptor de `rates_changed` (precio manual encima de una pendiente → `expired`).
- Seed en transacción revertida y partiendo sin datos de revenue: 0,96 s para las 3 propiedades (4/4/5 reglas,
  5/3/3 límites, 411/234/248 pendientes); segunda corrida 0,09 s sin crear nada.
- Frontend: `npx tsc -p tsconfig.app.json --noEmit | grep src/features/revenue` → sin errores; `npx eslint
  src/features/revenue` → limpio; los 30 módulos de la feature transforman sin error en el Vite del contenedor;
  paridad de claves ES/EN verificada. Validación visual en Chrome: pendiente (la hace el orquestador).
- Motor contra el demo (sin guardar): Casa Aurora 250 recomendaciones (0,28 s), Andino Medellín 234 (0,10 s), Hostel
  411 (0,15 s).
