# B2a — Tarifas — integration notes

Estado: tarea completa y verificada. El implementador retomó un intento interrumpido. Después, el verificador de
B2a revisó spec §5, plan B2a y esta nota contra el código. Corrigió 9 problemas, cada uno con un test visto en rojo
primero; el detalle está en "Correcciones del verificador".

Verificación final (detalle al final de esta nota):
- `pytest apps/rates` (TEST_DB_NAME=test_b2av): **286 passed**.
- `apps/rates` + `apps/bookings` + `apps/finance` + `apps/core`, contratos incluidos: **1545 passed**.
  - Hubo 1 fallo intermitente en `finance/tests/test_seed.py`, que es código de B4, no usa rates y pasa solo.
- `ruff check`, `ruff format --check` y `makemigrations rates --check`: limpios.
- Vitest de `src/features/rates`: **14 archivos, 114 tests**, en el host y en el contenedor Node 24, sin stderr.
- Frontend completo: **62 archivos, 434 tests**.
- `tsc` sin errores en `features/rates`, `components`, `lib` y `app`. `eslint` limpio.
- Chrome: grilla, planes (3 pestañas), promos y configuración a 1440 y 375 px, en tema claro y oscuro, sin scroll
  horizontal de página y con la consola sin errores ni warnings.
- En vivo sobre la propiedad `preview-b2a`, flujo E2E #4:
  - editar el plan base cambia al instante el precio del derivado;
  - una estadía mínima bloquea la cotización (`min_los`);
  - `core.audit.undo` revierte las dos ediciones.

Leer primero: "Contratos implementados / consumidos" (qué calcula `quote`) y "Cambios requeridos en archivos compartidos u otras apps" (qué le toca a cada fase).

## Correcciones del verificador (resumen)

| # | Problema | Arreglo | Test |
|---|---|---|---|
| 1 | Una noche guardada solo por una restricción (fila `DailyRate` con `source` `default`/`season`) congelaba su precio. Luego, cambiar los defaults o la temporada no llegaba a esas noches. Le pasaba al seed, a los sábados de temporada alta con estadía mínima | `services/resolution.py`: esas filas **siguen** a la temporada/defaults vigentes. Un delta de precio sobre ellas parte del precio que siguen hoy | `test_resolve_daily.py::TestNightsThatOnlyHoldRestrictions`, `test_set_daily_rates.py`, `test_api_grid.py::test_a_new_default_price_reaches_nights_that_only_hold_restrictions` |
| 2 | `provision_rates` aceptaba categorías sin precio o con precio 0 o negativo, que se vendían gratis. Un número inválido tumbaba la llamada con `InvalidOperation` (500) | Valida antes de escribir. Si falla: `DomainError(code="invalid_price", room_type=...)` | `test_provision.py::test_prices_are_validated_before_writing_anything` |
| 3 | `GET grid/` llamaba a `availability()` una vez por noche: ~13 consultas por noche y **3,7 s** para 90 noches nunca vistas | Una llamada al contrato para todo el rango y lectura de `InventoryDay` por ORM. Las consultas son constantes: 90 noches en frío 1,05 s, en tibio 0,18 s y 14 noches 0,06 s | `test_api_grid.py::test_the_queries_do_not_grow_with_the_nights`, `…overbooking_night_by_night` |
| 4 | `POST quote/` sin tope de noches | Máximo 366 (400 en `checkout`). Las fechas invertidas siguen respondiendo `invalid_dates` | `test_api_grid.py::TestQuote` |
| 5 | Los festivos se pedían en el idioma del perfil y quedaban en caché sin idioma (`staleTime: Infinity`). Al cambiar a inglés seguían en español | `?lang=es\|en` en `grid/` y `holidays/`. El frontend pide el idioma que muestra, porque cambia antes de que se guarde el perfil, y lo incluye en la query key | `test_api_grid.py::TestHolidays`, `PlanSeasons.test.tsx`, `RatesGridPage.test.tsx` |
| 6 | Guardar una celda no invalidaba las grillas en caché: el plan derivado mostraba hasta 30 s el precio viejo | `useCellSave` invalida todas las grillas cuando termina de guardar la última celda pendiente | `RatesGridPage.test.tsx` (con el `staleTime` real de 30 s) |
| 7 | En el panel masivo, un precio o una estadía elegidos pero vacíos o inválidos se descartaban sin aviso | "Aplicar" queda deshabilitado con el motivo (`bulk.needPrice` / `bulk.needStay`) | `BulkEditSheet.test.tsx` |
| 8 | En el desglose de la cotización había un `<p>` directo dentro de `<dl>` (HTML inválido para lectores de pantalla) | Dos listas `dl` válidas con el aviso del código entre ellas | `QuoteSheet.test.tsx` |
| 9 | Porcentajes siempre con formato `es-CO` (en inglés salía "12,5 %") | `derivationLabel`, `signedPercent` y la tasa de impuestos formatean según el idioma | `plans-lib.test.ts` |

Además, sin test unitario porque jsdom no calcula layout, verificado en Chrome:
- A 375 px, `/app/rates/plans` tenía scroll horizontal de página (634 px): la tarjeta de cada plan crecía al ancho
  de su tabla. Se arregló con `min-w-0`, y la tabla ahora se desplaza dentro de la tarjeta.
- En teléfonos, las pestañas de Planes ocultan sus íconos para que entren las tres.
- El selector de noches de la grilla queda en una sola línea.

Cobertura agregada, con mutaciones que confirman que cada test detecta la regresión:
- Aislamiento multi-tenant de los **8** recursos CRUD: listado, detalle, PATCH y DELETE de otra propiedad → 404.
- Temporada ajena en `season-rates` → 400; categoría ajena en `grid/bulk/` → 400.
- Listados sin consultas por fila (N+1) para los 8 recursos.

---

## API implementada

Base: `/api/v1/rates/`, solo staff, con el encabezado `X-Property-Id`. Todas las respuestas de error siguen la forma
`{detail, code, fields?, ...extra}` de A1. El dinero va como string con 2 decimales, redondeado a la moneda (COP:
pesos enteros). Los rangos son `[start, end)`, salvo `Season.end_date`, que es **inclusivo**.

| Método y path | Permiso | Notas |
|---|---|---|
| CRUD `taxes/` | view / manage | filtros `applies_to`, `is_active`; `code` único por propiedad. DELETE → 409 `in_use` si lo usa un extra o un cargo |
| CRUD `cancellation-policies/` | view / manage | `name`/`description` i18n (`es` obligatorio en `name`); `plans_count`. DELETE → 409 `in_use` si la usa un plan |
| CRUD `rate-plans/` | view / manage | filtros `kind`, `is_active`, `is_public`, `parent`; `children` (ids, solo lectura). Validaciones abajo |
| CRUD `room-type-defaults/` | view / manage | **POST hace upsert** por (`room_type`, `rate_plan`): 201 si crea, 200 si actualiza. Solo planes base |
| CRUD `seasons/` | view / manage | incluye `rates` (anidados, solo lectura); `end_date >= start_date` |
| CRUD `season-rates/` | view / manage | **POST hace upsert** por (`season`, `room_type`, `rate_plan`). Solo planes base |
| CRUD `extras/` | view / manage | `tax` solo de `applies_to` `extras` o `all`. DELETE → 409 `in_use` si ya se cobró |
| CRUD `promo-codes/` | view / manage | `code` en mayúsculas, único sin distinguir mayúsculas; `uses` es solo lectura |
| `GET grid/?start&end&rate_plan&lang` | rates.view | grilla categorías × noches; máximo 186 noches; sin `rate_plan` usa el primer plan base activo; `lang=es\|en` para los nombres de festivos (por defecto, el del usuario; otro valor → 400 `lang`) |
| `POST grid/bulk/` | rates.manage | edición masiva o de una celda; un evento de auditoría reversible por llamada |
| `POST quote/` | **rates.view** | herramienta de prueba del staff: devuelve `Quote.to_dict()` y no escribe nada; máximo 366 noches (400 en `checkout`); fechas invertidas → 200 con `invalid_dates` |
| `GET holidays/?year=` o `?start&end`, más `&lang=` | rates.view | festivos de Colombia (librería `holidays`) en `lang` o, si no viene, en el idioma del usuario; por defecto, el año de la fecha de negocio |
| `GET room-types/` | rates.view | **(extra)** categorías de la propiedad para los editores: `id, code, name, kind, color, base_occupancy, max_*, is_active, sort_order` |

### Planes (`rate-plans/`)

Reglas de validación. Los errores van en `fields` salvo que se indique `code`:
- Un plan base no tiene `parent`; al guardarlo se fuerzan `parent = null` y `derivation_value = 0`.
- Un plan derivado exige `parent`, del mismo hotel. Si el padre no es base → `code: parent_not_base`; así no hay
  cadenas ni ciclos. No puede ser su propio padre.
- Un plan derivado exige `derivation_type` `percent` o `amount`. Con `percent`, `derivation_value` no puede bajar de
  −100. **(Nuevo en esta sesión.)**
- Las `room_types` de un derivado deben estar entre las de su padre. Un base no puede quitar categorías que vende
  algún derivado suyo.
- Un base con derivados no puede volverse derivado (`code: plan_has_children`) ni borrarse (409 `in_use`).
- `deposit_percent` va de 0 a 100 y `min_los_default` de 1 a 365.
- `channels`: `[]` significa todos los canales. Códigos conocidos: `direct`, `marketplace`, `booking_engine` y los
  de OTA (`booksim`, `airsim`).

```json
POST /api/v1/rates/rate-plans/
{"code": "NR", "name": {"es": "No reembolsable", "en": "Non-refundable"}, "kind": "derived",
 "parent": "<uuid FLEX>", "derivation_type": "percent", "derivation_value": "-12",
 "room_types": ["<uuid DBL>"], "meal_plan": "room_only", "cancellation_policy": "<uuid>",
 "deposit_percent": "0", "min_los_default": 1, "is_public": true, "channels": [], "is_active": true}
→ 201 {"id": "…", "code": "NR", …, "derivation_value": "-12.00", "children": []}
```

### Precios por defecto y temporadas

```json
POST /api/v1/rates/room-type-defaults/          (upsert)
{"room_type": "<uuid>", "rate_plan": "<uuid base>", "price": "320000", "dow_adjustments": {"fri": 15, "sat": 15},
 "extra_adult_price": "60000", "extra_child_price": "30000", "child_age_limit": 12, "single_occupancy_price": null}

POST /api/v1/rates/seasons/
{"name": "Alta fin de año", "start_date": "2026-12-15", "end_date": "2027-01-15", "priority": 10, "color": "#B98A2E"}
→ 201 {..., "rates": []}

POST /api/v1/rates/season-rates/                (upsert)
{"season": "<uuid>", "room_type": "<uuid>", "rate_plan": "<uuid base>", "price": "416000", "dow_adjustments": {"fri": 15, "sat": 15}}
```

`dow_adjustments` usa las claves `mon…sun`, en porcentaje, con valores de −100 a 1000.

### Grilla

```json
GET /api/v1/rates/grid/?start=2026-10-09&end=2026-10-11&rate_plan=<uuid>
{"rate_plan": {"id": "…", "code": "FLEX", "name": {"es": "Tarifa flexible", "en": "Flexible rate"}, "kind": "base",
               "parent": null, "derivation_type": "percent", "derivation_value": "0.00", "editable": true},
 "currency": "COP", "start": "2026-10-09", "end": "2026-10-11",
 "dates": ["2026-10-09", "2026-10-10"],
 "holidays": [{"date": "2026-10-12", "name": "Día de la Raza"}],
 "room_types": [{"id": "…", "code": "DBL", "name": {"es": "Estándar", "en": "Standard"}, "color": "#4E6C88",
                 "kind": "private",
                 "rows": [{"date": "2026-10-09", "price": "368000.00", "extra_adult_price": "60000.00",
                           "extra_child_price": "30000.00", "min_los": null, "max_los": null, "cta": false,
                           "ctd": false, "stop_sell": false, "source": "default", "available": 10}]}]}
```

- Es un superconjunto de la forma del plan: agrega `rate_plan`, `currency`, `start`, `end`, `room_types[].code` y
  `room_types[].kind`.
- Un plan derivado devuelve precios derivados con `editable: false`.
- Una noche sin ningún precio configurado trae `price: null` y `source: "none"`.
- `available` es lo que respondería `bookings.availability(checkin=d, checkout=d+1)` para cada noche. Se calcula
  con una llamada al contrato sobre todo el rango, que materializa `InventoryDay`, y la lectura de esas filas por
  ORM (`services/grid.py::daily_availability`). Así el costo en consultas no depende del número de noches. Es
  negativo si hay sobreventa. Si B2b cambiara `availability()` para dejar de mantener `InventoryDay`, fallaría
  `test_api_grid.py` (valores de disponibilidad).
- `source` puede ser `default`, `season`, `manual`, `bulk`, `revenue`, `channel` o `none`. Una noche con una fila
  que solo guarda restricciones reporta la fuente que sigue hoy (`season` o `default`).

```json
POST /api/v1/rates/grid/bulk/
{"room_type_ids": ["<uuid>"], "rate_plan_id": "<uuid base>", "start": "2026-10-01", "end": "2026-10-08",
 "weekdays": [4, 5], "set": {"price_delta_percent": "10", "min_los": 2, "stop_sell": true}, "source": "bulk"}
→ 200 {"updated": 2, "audit_event_id": "<uuid>"}          (sin noches que coincidan: {"updated": 0, "audit_event_id": null})
```

- `weekdays` va de 0 (lunes) a 6; `[]` significa todos los días.
- `set` acepta **uno** de `price`, `price_delta_percent` o `price_delta_amount`, más `min_los`, `max_los`
  (`null` los quita), `cta`, `ctd` y `stop_sell`.
- `source` es `manual` (edición de una celda) o `bulk` (por defecto).
- Errores:
  - 400 `derived_plan_not_editable`.
  - 400 `validation_error`, con `room_type_ids`, si una categoría no la vende el plan.
  - 400 **`no_rate`**, con `room_type` y `date`: una noche sin precio solo acepta un `price` exacto (ver
    "Contratos").

### Cotización de prueba

```json
POST /api/v1/rates/quote/
{"room_type_id": "…", "rate_plan_id": "…", "checkin": "2026-10-09", "checkout": "2026-10-11", "adults": 3,
 "children": 1, "children_ages": [6], "promo_code": "bienvenida10", "guest_is_foreign_non_resident": false}
→ {"nights": [{"date": "2026-10-09", "base": "368000.00", "extra_adults": "60000.00", "extra_children": "30000.00",
               "discount": "45800.00", "total": "412200.00"}, …],
   "subtotal": "824400.00", "discount_total": "91600.00",
   "taxes": [{"code": "IVA", "name": "IVA 19% alojamiento", "rate": "19.00", "amount": "156636.00",
              "included": false, "exempt": false}],
   "tax_total": "156636.00", "total": "981036.00", "currency": "COP", "restrictions_ok": true, "violations": [],
   "promo_applied": "BIENVENIDA10", "room_type_id": "…", "rate_plan_id": "…", "checkin": "…", "checkout": "…",
   "adults": 3, "children": 1}
```

---

## Contratos implementados / consumidos

No cambié firmas ni tipos de retorno; `apps/core/tests/test_contracts.py` sigue pasando.

- **`quote(*, property, room_type, rate_plan, checkin, checkout, adults, children=0, children_ages=None,
  promo_code=None, guest_is_foreign_non_resident=False) -> Quote`**. Implementa el algoritmo normativo del plan,
  con un test por regla en `tests/test_quote.py`:
  1. Noches `[checkin, checkout)`. Si no hay noches → `violations=["invalid_dates"]` y `restrictions_ok=False`.
  2. Plan base efectivo: el mismo plan, o su `parent` si es derivado.
  3. Precio por noche del plan base, en este orden:
     - `DailyRate` con precio propio (`source` `manual`, `bulk`, `revenue` o `channel`), que ya es el precio
       exacto de esa fecha y **no** lleva ajuste por día;
     - si no hay, la `SeasonRate` de la temporada activa. Gana la de mayor `priority`; si empatan, la que empieza
       más tarde. Lleva su `dow_adjustments`;
     - si no hay, `RoomTypeRateDefaults.price` con su `dow_adjustments`;
     - si no hay, precio 0 con el aviso `no_rate`.
     - **Filas que solo guardan restricciones** (`source` `default` o `season`, creadas al fijar una restricción
       en una noche sin fila): nadie fijó su precio, así que su precio **sigue** a la temporada y los defaults de
       hoy, incluida una temporada creada, editada o borrada después. Solo si ya no hay ni temporada ni defaults
       conservan el precio guardado, y la noche sigue vendible. (Corrección del verificador; antes quedaban
       congeladas.)
  4. Plan derivado: `percent` → `precio × (1 + v/100)`; `amount` → `precio + v`; nunca baja de 0.
  5. Ocupación:
     - Cada adulto por encima de `RoomType.base_occupancy` paga `extra_adult_price`. El valor sale de la fila
       `DailyRate` si lo tiene; si no, de los defaults.
     - Un niño con edad ≤ `child_age_limit` (12 si no hay defaults) paga `extra_child_price`. Un niño sin edad
       también cuenta como niño. Los mayores cuentan como adultos.
     - Dormitorio: una persona por cama, sin extras ni ocupación sencilla.
     - **Ocupación sencilla (decisión documentada)**: con un solo huésped adulto y `single_occupancy_price`, en una
       noche que sale de los defaults ese precio **reemplaza** el base, ajustado con el mismo porcentaje del día. En
       noches de temporada, manuales o de revenue mantiene la proporción `precio_noche × sencilla / precio_default`.
       El texto literal del plan ("reemplaza el base") hacía pagar lo mismo a un huésped solo en Año Nuevo que un
       martes, y podía cobrarle **más** que a una pareja en una noche en promoción.
  6. Código promocional (`services/promos.py`):
     - Se compara sin distinguir mayúsculas ni espacios.
     - Condiciones para que aplique: está activo; el día de hoy en la zona horaria de la propiedad (fecha de
       calendario, no la fecha de negocio) cae en `[valid_from, valid_to]`; el plan está permitido
       (`rate_plans` vacío significa todos); `uses < max_uses`; y al menos una noche cae en
       `[stay_from, stay_to]`. Ambas ventanas son inclusivas. La página de promos muestra el estado según la
       fecha de negocio, así que puede diferir por un día mientras no corra la auditoría nocturna.
     - Solo se descuentan las noches dentro de la ventana de estadía: un % de la noche (base + extras) o un monto
       fijo por noche, sin bajar de 0.
     - Si no aplica → `promo_invalid`, que es un aviso y no cambia `restrictions_ok`.
  7. Restricciones, tomadas de las filas del plan **base**:
     - `stop_sell` en cualquier noche → `stop_sell`;
     - `cta` en la noche de llegada → `cta`;
     - `ctd` en la fila de la fecha de salida → `ctd`;
     - `min_los` de la noche de llegada o, si no tiene, `min_los_default` **del plan cotizado** → `min_los`;
     - `max_los` de la noche de llegada → `max_los`.
     - `restrictions_ok` refleja solo estas restricciones.
  8. Impuestos: los `Tax` activos con `applies_to` `room` o `all`, ordenados por `code`.
     - Extranjero no residente con `exempt_foreign_non_residents` → línea con `amount=0` y `exempt=True`.
     - Impuesto incluido → línea informativa `subtotal − subtotal/(1+rate)`, que no suma.
     - Impuesto excluido → `subtotal × rate`, que suma a `tax_total`.
  9. Redondeo con `core.money.quantize` (COP: pesos, `ROUND_HALF_UP`) por noche y en los totales.
     `total = subtotal + tax_total`.
  - Orden estable de `violations`: primero las restricciones (`stop_sell, cta, ctd, min_los, max_los`), después
    `no_rate` y al final `promo_invalid`. B2b trata `no_rate` y `promo_invalid` como avisos (`QUOTE_WARNINGS`).
- **`resolve_daily(room_type, rate_plan, start, end) -> list[DayRate]`**: una fila por noche.
  - Para un plan derivado devuelve el precio derivado, sin redondear, con las restricciones del base.
  - Extras de adulto y niño: los de la fila; si están en null, los de los defaults.
  - `source` puede ser `manual|bulk|revenue|channel|default|season|none`.
- **`set_daily_rates(*, property, room_type, rate_plan, start, end, price=None, restrictions=None, dow=None,
  source="manual", actor=None) -> int`**: devuelve cuántas noches escribió.
  - Delega en `services.writes.bulk_update_rates`, que admite varias categorías y devuelve
    `WriteResult(updated, event)`.
  - Crea las filas faltantes con el precio resuelto y conserva su origen (`default` o `season`), así que su precio
    sigue a la configuración (ver el paso 3 de `quote`).
  - `price` fija el precio; `restrictions` puede traer `price_delta_percent` o `price_delta_amount`, que ajustan el
    precio vigente. En una fila que sigue a la configuración, el delta parte del precio que sigue hoy, no del que
    quedó guardado.
  - Claves de restricción: los nombres del modelo `min_los`, `max_los`, `closed_to_arrival`,
    `closed_to_departure` y `stop_sell`. Cualquier otra → `invalid_restriction`. `None` quita una estadía mín./máx.
  - `dow` es una lista 0–6, con lunes = 0.
  - Un cambio de precio marca la fila con `source`; un cambio que solo toca restricciones conserva el origen de la
    fila.
  - Plan derivado → `derived_plan_not_editable`.
  - **Nuevo en esta sesión**: una noche **sin ningún precio** (ni fila, ni temporada, ni defaults) solo acepta un
    `price` exacto. Una restricción o un delta sobre ella lanza `DomainError(code="no_rate", room_type=..., date=...)`
    y revierte todo. Antes creaba una fila con precio 0 que `quote` y `search_offers` vendían gratis.
  - Registra `audit.record(action="rates.bulk_update", reversible=True, undo_data={"rows": [...]})`.
    - `source` del evento: `user` si hay actor; si no, `automation` para `source="revenue"`, `channel` para
      `source="channel"` y `system` en los demás casos.
  - Emite `rates_changed` al hacer commit.
- **`provision_rates(property, *, room_type_prices, plans=None, taxes_default=True, policies_default=True,
  actor=None) -> None`**: idempotente. Empareja impuestos y planes por `code`, políticas por nombre en español y
  defaults por (categoría, plan); nunca sobrescribe lo que ya existe.
  - `plans=None` crea tres planes: **FLEX** (base, política "Flexible 48h"), **NR** (−12 %, "No reembolsable") y
    **BB** (+35.000 por noche, `breakfast`).
  - `weekend_adjust_percent` se aplica a las noches de **viernes y sábado**.
  - `taxes_default` crea **IVA** (19 %, alojamiento, exento para extranjeros no residentes) e **IVA-EXTRAS** (19 %,
    extras).
  - `policies_default` crea "Flexible 48h" (gratis hasta 48 h, luego la primera noche) y "No reembolsable".
  - Categoría inexistente → `DomainError(code="unknown_room_type", codes=[...])` antes de escribir nada.
  - Si un precio es inválido tampoco se escribe nada: `DomainError(code="invalid_price", room_type="<code>")`.
    Reglas: `price` obligatorio y mayor que 0; `extra_adult_price` y `extra_child_price` ≥ 0 (vacío = 0);
    `single_occupancy_price` > 0 si viene; `weekend_adjust_percent` entre −100 y 1000; `child_age_limit` entero
    de 0 a 17. Aplica sobre todo a C9 (onboarding con IA) y C11 (signup), que generan estos datos.
  - Audita `rates.provisioned` y emite `rates_changed` para un año desde la fecha de negocio.
  - Pensado para el onboarding con IA (C9) y el signup (C11).
- **Consumidos**:
  - `bookings.services.availability.availability`, una llamada por grilla sobre todo el rango. Luego se leen por
    ORM las filas `InventoryDay` que ese contrato materializa (lectura permitida por el plan §B).
  - `core.audit` (`record`, `register_undo`, `UndoError`), `core.signals.send_on_commit`,
    `core.money.quantize/apply_percent`, `core.dates`.
- Servicios internos que otras apps pueden llamar sin romper nada:
  - `apps.rates.services.calendar.holiday_list(start, end, lang)`.
  - `apps.rates.services.promos.find_promo/eligible_nights/register_use`.
  - `apps.rates.services.writes.bulk_update_rates(...)`, para escribir varias categorías con un solo evento de
    auditoría.

## Señales emitidas / escuchadas

`rates_changed(property, room_type_ids, rate_plan_ids, start, end)` se envía siempre con `send_on_commit` y con
el rango `[start, end)`. `rate_plan_ids` lista el plan base seguido de **sus derivados**, porque sus precios lo
siguen.

| Origen | Rango |
|---|---|
| `set_daily_rates` / `POST grid/bulk/` | las noches del rango escrito (si escribió al menos una) |
| deshacer `rates.bulk_update` | de la primera a la última noche restaurada |
| `provision_rates` | `[business_date, business_date + 365)` |
| crear o editar un plan | horizonte de 365 días; si es base, el plan y sus derivados; si es derivado, solo ese plan |
| crear, editar o borrar `room-type-defaults` | horizonte de 365 días, para esa categoría |
| editar o borrar una temporada | sus noches; si cambiaron las fechas, también el rango anterior |
| crear, editar o borrar `season-rates` | las noches de la temporada, para esa categoría |

Crear una temporada sin precios, cambiar impuestos, promociones o extras y **borrar un plan** no emiten nada.

Escuchada: `reservation_created`. Si la reserva trae `promo_code`, se suma un uso a ese `PromoCode`
(`receivers.py`); así se aplica `max_uses`.

## Deshacer (core.audit)

- `RatesConfig.ready()` registra `audit.register_undo("rates.bulk_update", undo_bulk_update)`.
- Cada fila de `undo_data["rows"]` guarda
  `{room_type_id, rate_plan_id, date, before (snapshot o null si la fila no existía), before_updated_by, after}`.
- Al deshacer se restauran las filas anteriores y se **borran** las creadas. Si alguna fila cambió después de la
  edición → `UndoError(code="undo_conflict")` (409). El deshacer emite `rates_changed`.
- Test: `test_set_daily_rates.py::TestAuditAndUndo`.

## Automatizaciones registradas

Ninguna.

## Proveedores de integración registrados

Ninguno.

## Extensiones de frontend exportadas

`features/rates/routes.tsx` tiene 6 páginas lazy. `nav.ts` no cambió respecto a A2. No exporta widgets, tabs,
topbar ni comandos.

| Ruta | Qué hace |
|---|---|
| `/app/rates` | **Grilla** categorías × noches (14/30/60/90) desde la **fecha de negocio**, con plan elegible (los derivados en solo lectura con aviso de su regla). Edición en celda con teclado: flechas, Home/End y Ctrl+Home/End; Enter/F2 o un dígito empiezan a editar; Enter guarda y baja; Tab guarda y avanza; Esc descarta; Supr quita la estadía mínima. CTA/CTD/stop-sell son toggles. Fila de disponibilidad por categoría, fines de semana (viernes y sábado) y festivos marcados, leyenda de `source`. Tiene panel de **edición masiva**, **Deshacer** (ver abajo) y **Cotizar**, una hoja que prueba `POST quote/` y explica cada violación |
| `/app/rates/plans` | Tres pestañas (`?tab=plans|defaults|seasons`). **Planes**: árbol base → derivados, con una tabla que pone el precio por defecto de cada categoría junto al que calcula cada derivado, más el editor de planes. **Precios por defecto**: precio, ajustes por día con vista previa por noche, extras por persona, edad límite y ocupación sencilla. **Temporadas**: lista, calendario anual (temporada que manda cada noche, festivos y fecha de negocio), precios por categoría y "Calcular desde los precios por defecto + N %" |
| `/app/rates/promos` | Códigos: descuento, ventanas de reserva y de estadía, planes, usos y estado (activo, programado, vencido, agotado, pausado) |
| `/app/settings/taxes`, `/policies`, `/extras` | Configuración (CRUD) |

- **Deshacer**: llama al endpoint genérico `POST /api/v1/control/audit/{id}/undo/` con `{confirm: true}`. Antes
  consulta `GET /api/v1/control/audit/{id}/`. Mientras esa consulta dé 404, o si el usuario no tiene
  `control.audit_undo`, el botón queda deshabilitado y se muestra el aviso.
- **Caché y derivados**: cuando termina de guardarse la última celda pendiente se invalidan todas las grillas
  (`['rates', 'grid']`). Así el plan derivado y el redondeo del servidor se ven al instante y no tras 30 s.
  Mientras otras celdas siguen guardándose no se recarga, para no traer valores viejos a medio camino.
- **Idioma**: `useRateGrid` y `useHolidays(year, lang)` mandan `?lang=` e incluyen el idioma en la query key.
- **Edición masiva**: si un precio o una estadía se eligieron pero su valor falta o es inválido (incluido un
  porcentaje menor a −100), "Aplicar" queda deshabilitado con el motivo. Nunca se envía un cambio a medias.
- Piezas reutilizables para otras features (se importan directo; no son extensiones §E):
  - `features/rates/api.ts`: tipos exactos de la API y los hooks `useRateGrid({start, end, planId, lang})`,
    `useHolidays(year, lang)`, `postQuote` y `useRatesList`.
  - `features/rates/lib/plans.ts`: `derivedPrice`, `seasonOn`, `applyPercent`, con redondeo idéntico al backend.
  - `features/rates/lib/text.ts`: `derivationLabel(type, value, currency?, lang?)`, por ejemplo "−12 %" o
    "+ $ 35.000".

## Dependencias nuevas (pip/npm) y por qué

Ninguna.

## Cambios requeridos en archivos compartidos u otras apps

Ningún cambio obligatorio. Para las fases siguientes:

- **C12 (control)**: implementar `GET /api/v1/control/audit/{id}/` (200 con el evento) y
  `POST /api/v1/control/audit/{id}/undo/` con `{confirm: true}`, llamando a `core.audit.undo(event, actor=...)`
  con el permiso `control.audit_undo` y devolviendo 409 con el `code` de `UndoError` (`undo_conflict`,
  `already_undone`). Con eso se habilita solo el botón Deshacer de la grilla, sin tocar `rates`.
- **B2b (ya no es necesario)**: el implementador sugería un contrato de rango para la disponibilidad. Ahora
  `rates/services/grid.py` llama una vez a `availability()` para todo el rango y lee las filas `InventoryDay` por
  ORM. **Pedido a B2b**: que `availability()` siga materializando `InventoryDay` para el rango que recibe, como
  dice su docstring. Si se expone un contrato de rango, basta con cambiar `daily_availability`.
- **B-INT (archivo compartido)**: `manage.py spectacular --validate --fail-on-warn` da 5 warnings por colisión de
  nombres de enums entre apps: `kind` (RoomType, RatePlan, Folio, Charge…), `status` y `source`. Hay que agregar
  entradas a `SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]` en `config/settings.py`. No son errores; el schema se
  genera igual.
- **B4 (observación)**: `apps/finance/tests/test_seed.py::test_seed_builds_a_believable_ledger` falló una vez en la
  corrida conjunta (`PaymentIntent` `created` de reservas tentativas) y pasó al correrlo solo. Parece depender de la
  hora o del orden de los tests. No usa rates.
- **C3 (distribución)**: suscribirse a `rates_changed` y leer precios con `resolve_daily(room_type, plan, start,
  end)`, que resuelve derivados y trae restricciones. Borrar un plan no emite la señal.
- **C8 (revenue)**: escribir con `set_daily_rates(..., source="revenue")`. Las filas quedan con `source="revenue"`,
  que en la grilla lleva tinta azul, y el evento de auditoría con `source="automation"` si no hay actor. Leer
  festivos con `holiday_list`.
- **C13 (calendario)**: usar `GET /api/v1/rates/holidays/?start&end` y `GET /api/v1/rates/grid/?start&end` para
  la fila de precio. `grid` pide `rates.view`: recepción lo tiene.
- **C1, C4, C5**: `GET extras/?is_active=true&sellable_online=true` para ofrecer extras. Los códigos
  promocionales se validan en `quote` (`promo_invalid`), B2b los rechaza si `enforce_restrictions` y `rates` cuenta
  el uso al crearse la reserva.
- **B-INT (seed)**: `apps/rates/seed.py` corre después del inventario y empareja categorías por código o por
  palabras del nombre: Aurora DBL/SUP/STE, Andino STD/EJE/FAM, Hostel D6/D8/DF6/PDB/PFM (son los códigos reales de
  `apps/inventory/seed.py`). Si no hay categorías en una propiedad, la omite.

## Seed (`apps/rates/seed.py`, idempotente)

Por propiedad:
- IVA 19 % de alojamiento, excluido y exento para extranjeros no residentes, más IVA 19 % de extras.
- Políticas "Flexible 48h" y "No reembolsable".
- Planes FLEX, NR (−12 %) y BB (+35.000, desayuno).
- Precios por defecto con fin de semana +15 % (viernes y sábado):
  - Aurora: 320.000, 420.000 y 650.000; adulto extra 60.000, niño 30.000.
  - Andino Medellín: 260.000, 340.000 y 420.000.
  - Hostel: cama de 6 → 65.000, de 8 → 55.000, femenino → 70.000, privada doble 180.000, familiar 260.000.
- Temporadas "Alta fin de año" (15 dic–15 ene, +30 %, prioridad 10) y "Semana Santa" (domingo de Ramos a domingo de
  Pascua, +25 %, prioridad 20), con `SeasonRate` por categoría.
- Extras: desayuno 35.000 por persona y noche, parqueadero 25.000 por noche, late check-out 80.000 por estadía y
  traslado 90.000 por estadía.
- Código `BIENVENIDA10` (10 %).
- Estadía mínima de 2 noches los sábados de temporada alta. Son filas `DailyRate` con `source="season"`: su precio
  sigue a la `SeasonRate` si luego se edita la temporada.

Probado con datos creados en `tests/test_seed.py`: segunda corrida sin cambios; propiedades sin categorías se
omiten.

## Limitaciones conocidas / pendientes

- `max_uses` no se bloquea bajo concurrencia: dos reservas simultáneas pueden pasarse por uno. Cancelar una reserva
  no devuelve el uso del código.
- El botón Deshacer de la grilla espera a C12. El handler `rates.bulk_update` ya funciona: se probó en vivo con
  `core.audit.undo`.
- Borrar un plan no emite `rates_changed`.
- Ocupación sencilla: el algoritmo del plan dice "reemplaza el base" y el implementador aplica una proporción. Es
  una decisión documentada en el paso 5 de `quote`. En una noche por defecto el resultado es el mismo; en
  temporada, manual o revenue, el huésped solo paga la misma proporción y nunca más que una pareja. El verificador
  la mantiene.
- Queda en la BD de desarrollo la propiedad `preview-b2a` (usuario `preview-b2a@housetel.co` / `housetel123`), con
  datos de tarifas para revisar la UI. El verificador deshizo sus ediciones de prueba. Las propiedades del seed aún
  no tienen tarifas: B-INT corre el seed completo.

## Verificación (corrida real del verificador)

```bash
docker compose run --rm -e TEST_DB_NAME=test_b2av backend pytest apps/rates -q                 # 286 passed
docker compose run --rm -e TEST_DB_NAME=test_b2av backend pytest apps/core/tests/test_contracts.py \
  apps/core/tests/test_domain_contract.py -q                                                   # 353 passed
docker compose run --rm -e TEST_DB_NAME=test_b2av backend pytest apps/rates apps/bookings apps/finance apps/core -q
#   1545 passed + 1 fallo intermitente de finance/test_seed (B4, sin rates; pasa solo)
docker compose run --rm backend sh -c "ruff check apps/rates && ruff format --check apps/rates"        # limpio
docker compose run --rm backend python manage.py makemigrations rates --check --dry-run               # No changes
cd frontend && npx vitest run src/features/rates                                               # 14 archivos, 114 tests
docker compose run --rm --no-deps frontend npx vitest run src/features/rates                   # igual en Node 24
npx vitest run                                                                                 # 62 archivos, 434 tests
npx tsc -p tsconfig.app.json --noEmit | grep -E "src/features/rates|src/components|src/lib|src/app"   # sin errores
npx eslint src/features/rates                                                                  # limpio
```

- Cada corrección del verificador tiene su test visto en rojo primero, por la razón esperada.
- El test del plan derivado usa el `staleTime` real de 30 s. Con el cliente de tests (`staleTime: 0`) no podía
  fallar.
- Los tests de cobertura que pasaban de entrada (aislamiento y N+1) se validaron con mutaciones: quitar el filtro de
  `season-rates` o el `prefetch` de `promo-codes` los hace fallar.
- En Chrome (contexto aislado, DevTools MCP):
  - `/app/rates`, `/app/rates/plans` (3 pestañas), `/app/rates/promos` y `/app/settings/{taxes,policies,extras}` a
    1440 y 375 px, en claro y oscuro: `scrollWidth` igual al viewport y consola sin errores.
  - A 375 px se revisaron el panel masivo y su validación.
  - Flujo E2E #4 en vivo: precio del base → derivado actualizado; estadía mínima → `min_los` en la cotización;
    `core.audit.undo` restauró todo.
- Rendimiento de `GET grid/` en dev: 14 noches 0,06 s; 90 noches 0,18 s en tibio y 1,05 s en frío (antes 0,64 s,
  0,93 s y 3,7 s).
