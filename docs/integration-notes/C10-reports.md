# C10 Reportes: notas de integración

Estado: **completo en modo MVP** (sin tests nuevos, por decisión del usuario). Backend: motor único de KPIs,
18 reportes con JSON y exportes CSV/XLSX/PDF, permisos por categoría y seed de verificación. Frontend: hub
`/app/reports`, detalle `/app/reports/:reportId`, widget del panel Hoy y comandos ⌘K. La app `reports` no
tiene modelos ni migraciones: todo se calcula en vivo con los datos de bookings, finance e inventory.

Verificación hecha: `manage.py check` limpio; `makemigrations reports --check` sin cambios; smoke por el proxy
de Vite (login con cookie jar + CSRF) de los 18 reportes, las 7 comparaciones y los 54 exportes: 79/79 OK, cada
reporte en menos de 250 ms con el seed (~3.300 reservas); permisos por rol y aislamiento entre organizaciones
verificados; seed probado dentro de una transacción con rollback (18/18 reportes por propiedad, 2,5 s en total);
`ruff check` y `ruff format` de `apps/reports` limpios; `tsc` y `eslint` de `src/features/reports` sin errores;
paridad de i18n ES/EN verde. Validación visual con un
Chrome headless **aislado** (perfil y puerto propios, nunca el navegador compartido): hub, rendimiento (con
comparación y por semana), segmentos, pickup, ingresos diarios, estado de habitaciones, anticipación, llegadas,
saldos e impuestos, en claro/oscuro, ES/EN, 1440 px y 375 px, sin errores de consola.

## Definiciones del motor (`backend/apps/reports/engine.py`)

Un único motor calcula todo sobre la **fecha de negocio** de la propiedad. El panel Hoy (C1) y el reporte
coinciden: el 27 sep ambos muestran 60,9 % (14 de 23 habitaciones).

- **Rango** `[start, end]`, inclusivo en ambos extremos: "1 al 30 sep" son 30 días. La noche `d` de una estadía
  cuenta si `checkin ≤ d < checkout`, así que **el día de salida nunca es noche**.
- **Noches vendidas(d)**: estadías `confirmed | checked_in | checked_out` que cubren `d`. Las tentativas,
  canceladas y no-show no cuentan (su penalidad entra como "otros ingresos"). **En dormitorios cada cama es una
  unidad** (cada estadía de dorm es una cama).
- **Noches disponibles(d)**: Σ `InventoryDay.total_units − blocked_units`. Los bloqueos (fuera de servicio,
  mantenimiento, uso del propietario) salen del disponible. Para fechas sin `InventoryDay` se aplica la misma
  regla de `rebuild_inventory`, en solo lectura, sobre las tablas de habitaciones, camas y bloqueos.
- **Ocupación** = vendidas ÷ disponibles. **ADR** = ingresos de alojamiento ÷ noches vendidas. **RevPAR** =
  ingresos de alojamiento ÷ noches disponibles. Los totales de un rango son **cocientes de las sumas**, nunca
  promedios de cocientes diarios.
- **Ingresos de alojamiento**:
  - reales: Σ `Charge.amount` (neto) de los cargos `room` **no anulados** con `business_date` en el rango;
  - desde la fecha de negocio en adelante (noches aún sin publicar), el pronóstico: Σ `nightly_rates[].net`
    de las estadías vendidas, omitiendo cada noche que ya tenga cargo publicado (esa cuenta como real).
- **Otros ingresos** (solo lo publicado): extras, penalidades (`cancellation_fee`) y cargos/ajustes (`fee`,
  `adjustment`, `other`), en neto. Impuestos = Σ `tax_amount` más los cargos `tax` manuales.
- **Impuestos**: la base gravada es el neto de los cargos con impuesto cobrado. La **base exenta** es el neto de
  los cargos con impuesto que quedó en 0 por la exención de IVA a extranjeros no residentes (ET art. 481
  lit. d). **No gravado** son los cargos sin impuesto.
- **Comparación**: `previous_period` son los mismos N días justo antes; `previous_year` son las mismas fechas un
  año antes (29 feb → 28 feb).

### Contrastes hechos a mano con SQL (seed actual, fecha de negocio 27 sep 2026)

| Caso | SQL directo | API |
|---|---|---|
| Aurora, sep 1–30: vendidas / disponibles | 418 / 718 | 418 / 718 → 58,2 % |
| Aurora, sep: ingresos de alojamiento | 169.811.800 reales + 26.696.400 previstos | 196.508.200 · ADR 470.115 · RevPAR 273.688 |
| Aurora, cargos `room` anulados en sep | 0 | — |
| Aurora, ago: base gravada / IVA / exenta (134 cargos) / no gravado | 133.986.080 / 25.457.362 / 61.312.240 / 7.866.955 | idénticos; los 134 exentos son de huéspedes extranjeros no residentes |
| Aurora, 29 ago–27 sep: pagos aprobados | 384 pagos · 404.040.189 · reembolsos 100.000 | idénticos · en línea 44,5 % |
| Hostel Bogotá, sep (dorm = camas): vendidas / disponibles | 158 priv. + 627 camas / 238 + 1.020 (34 camas × 30) | 785 / 1.258 → 62,4 % |

## API implementada

Staff, con `X-Property-Id`. Los errores siguen el formato del core `{detail, code, fields?}`.

### `GET /api/v1/reports/`: catálogo

Lo puede llamar cualquier miembro de la propiedad; `allowed` dice si su rol puede abrir cada reporte.

```json
[{"id": "performance", "category": "performance", "permission": "reports.performance", "allowed": true,
  "range_kind": "any", "default_preset": "this_month", "compare": true, "group_by": ["day", "week", "month"],
  "default_group_by": "day", "window_param": false, "window_default": null}, …]
```

`range_kind`: `past` (historia), `future` (on the books), `date` (un día, por defecto hoy), `any` (ambos) o
`none` (foto del momento, sin rango). `default_preset`: `today | yesterday | this_week | this_month |
last_month | last30 | next14 | next30 | next90`.

### `GET /api/v1/reports/<id>/?start&end&compare&group_by&days&lang[&format]`

- `start`/`end` en `YYYY-MM-DD`, ambos incluidos. Si faltan, se usa el preset por defecto del reporte,
  relativo a la fecha de negocio. El rango máximo es de 731 días.
- `compare=previous_period|previous_year`, solo en los reportes con `compare: true`.
- `group_by` según el reporte: `day | week | month` (las semanas empiezan el lunes) o, en
  `revenue-by-segment`, `source | channel | room_type | rate_plan`.
- `days`: ventana de pickup, de 1 a 90 (por defecto 7).
- `lang=es|en`: idioma de las etiquetas del JSON y de los exportes. Por defecto, el idioma del usuario.
- `format=csv|xlsx|pdf` devuelve el archivo (`Content-Disposition: attachment;
  filename="<id>_<slug>_<start>_<end>.<ext>"`).

Respuesta JSON (recortada, datos reales del seed):

```json
{"id": "performance", "category": "performance", "title": "Rendimiento", "lang": "es", "currency": "COP",
 "property": {"id": "6b36…", "name": "Hotel Casa Aurora", "slug": "casa-aurora"},
 "business_date": "2026-09-27",
 "range": {"start": "2026-09-26", "end": "2026-09-28", "days": 3},
 "compare": {"mode": "previous_period", "start": "2026-09-23", "end": "2026-09-25", "days": 3},
 "group_by": "day", "params": {},
 "summary": [{"key": "occupancy", "label": "Ocupación", "type": "percent", "value": 68.6,
              "intent": "higher-is-better", "previous": 62.5, "change": 6.1, "change_pct": 9.8},
             {"key": "adr", "label": "ADR", "type": "money", "value": "481760.00", "previous": "491795.00",
              "change": "-10035.00", "change_pct": -2.0, "intent": "higher-is-better"}],
 "charts": [{"key": "occupancy", "title": "Ocupación por noche", "type": "line", "x": "date", "x_type": "date",
             "value_type": "percent",
             "series": [{"key": "occupancy", "label": "Ocupación", "role": "primary"},
                        {"key": "occupancy_prev", "label": "Periodo anterior", "role": "compare"}],
             "data": [{"date": "2026-09-26", "occupancy": 75.0, "forecast": false, "occupancy_prev": 62.5,
                       "date_prev": "2026-09-23", "…": "…"}],
             "marker": {"x": "2026-09-27", "label": "Hoy"}, "forecast_from": "2026-09-27"}],
 "tables": [{"key": "periods", "title": "Detalle por día",
             "columns": [{"key": "date", "label": "Fecha", "type": "date"}, "…"],
             "rows": [{"date": "2026-09-26", "available": 24, "sold": 18, "occupancy": 75.0,
                       "adr": "527959.00", "room_revenue": "9503260.00", "kind": "actual", "…": "…"}],
             "totals": {"available": 70, "sold": 48, "occupancy": 68.6, "adr": "481760.00", "…": "…"}}],
 "notes": ["Rango: del 26 sep 2026 al 28 sep 2026, ambos días incluidos (3 días de fecha de negocio)…",
           "Comparación (periodo anterior): del 23 sep 2026 al 25 sep 2026.", "…definiciones…"],
 "meta": {}, "generated_at": "2026-09-28T00:24:01-05:00"}
```

Convenciones del JSON:

- En tablas y KPIs, el dinero es string (`"481760.00"`); en gráficos es número.
- Los porcentajes son puntos (`68.6`). El `change` de un KPI porcentual se da en puntos porcentuales.
- Tipos de columna: `text | date | month | datetime | number | money | percent | status | country | code |
  boolean`. `status_kind` (`reservation | room | payment`) indica cuál `StatusBadge` usar; `labels` da el mapa
  código → texto; `link: "reservation"` enlaza la fila a su `reservation_id`.
- Tipos de gráfico: `line | column | hbar | stacked_column | status_bar`. Roles de serie:
  `primary | compare | stack`.

Errores (400, con `code` estable):

- `invalid_date`, `invalid_range` (fin antes del inicio, o falta un extremo), `range_too_long`;
- `invalid_compare`, `invalid_group_by`, `invalid_days`, `invalid_format`, `invalid_lang`.

Además: 404 `not_found` para un reporte inexistente, 403 `permission_denied` cuando el rol no tiene el permiso
de la categoría, y 404 cuando la propiedad es de otra organización.

### Catálogo de reportes

| id | Categoría (permiso) | Rango (preset) | Compara | Agrupa | Contenido |
|---|---|---|---|---|---|
| `performance` | Rendimiento (`reports.performance`) | any (este mes) | sí | día/semana/mes | ocupación, ADR, RevPAR, ingresos (reales + previstos), otros ingresos; serie y tabla por periodo |
| `revenue-by-segment` | Rendimiento | any (este mes) | sí | fuente/canal/categoría/plan | noches, ingresos, participación y ADR por segmento; suma exacta = rendimiento; KPI de ingresos directos (sin OTA) |
| `pickup` | Rendimiento | future (próx. 30) | — | ventana `days` | noches nuevas − canceladas por noche de estadía, on the books antes y ahora, ingresos del pickup |
| `forecast` | Rendimiento | future (próx. 90) | — | día/semana/mes | OTB por noche: ocupación, tentativas aparte, llegadas, salidas, ingresos, ADR, RevPAR |
| `cancellations` | Rendimiento | past (últ. 30) | sí | — | canceladas por fecha de cancelación, noches e ingresos perdidos, penalidades, tasa; por canal |
| `booking-window` | Rendimiento | any (últ. 30) | sí | — | anticipación (media, mediana, mismo día) y duración por tramos y por canal |
| `guests-by-nationality` | Rendimiento | any (este mes) | — | — | noches, ingresos, reservas y huéspedes únicos por país del titular |
| `arrivals` | Operación (`reports.operational`) | date (hoy) | — | — | estadías que llegan, estado, habitación/cama, ETA, saldo de la reserva |
| `departures` | Operación | date (hoy) | — | — | estadías que salen (incluye confirmadas por llegar si el rango es futuro), saldo |
| `in-house` | Operación | date (hoy) | — | — | estadías en casa en las noches del rango (futuro: también confirmadas esperadas) |
| `no-shows` | Operación | past (últ. 30) | — | — | no-shows por fecha de llegada, noches e ingresos perdidos, penalidad y saldo pendiente |
| `occupancy-outlook` | Operación | future (próx. 14) | — | — | ocupación, libres, tentativas, llegadas y salidas por noche (alimenta el widget) |
| `housekeeping-status` | Operación | none (foto) | — | — | cada habitación activa: estado de limpieza, ocupación esta noche, sale hoy, llega hoy |
| `daily-revenue` | Finanzas (`reports.financial`) | past (últ. 30) | sí | día/semana/mes | cargos publicados por tipo (alojamiento, extras, penalidades, cargos y ajustes, impuestos) |
| `payments-by-method` | Finanzas | past (últ. 30) | sí | — | pagos aprobados y reembolsos por medio y por día, % en línea (Wompi) |
| `cash-shifts` | Finanzas | past (últ. 30) | — | — | turnos: fondo, efectivo recibido/devuelto, esperado, contado y diferencia |
| `receivables` | Finanzas | none (foto) | — | — | reservas con saldo > 0: salidas con saldo (antigüedad), en casa, penalidades, llegadas futuras |
| `taxes` | Impuestos (`reports.financial`) | past (mes pasado) | sí | — | base gravada, IVA, base exenta y no gravado, por impuesto y por día |

### Exportes (`backend/apps/reports/exporters.py`)

Se generan desde el mismo resultado que el JSON.

- **CSV**: separador `;`, UTF-8 con BOM (Excel en español lo abre con tildes y columnas correctas), coma decimal
  en ES, pesos enteros, fechas ISO. Si hay varias tablas, cada una va precedida de su título. Incluye la fila
  de totales.
- **XLSX** (openpyxl): una hoja "Resumen" con la propiedad, el rango, los KPIs (valor, periodo anterior y
  variación) y las definiciones, y una hoja por tabla con números y fechas reales, formatos (`"$" #,##0`,
  `0.0%`, `yyyy-mm-dd`), encabezado congelado, autofiltro y totales en negrita.
- **PDF** (reportlab): encabezado "Housetel · propiedad · reporte" y pie con fecha de generación y número de
  página en cada página, KPIs, tablas con el encabezado repetido (horizontal si tienen más de 7 columnas; tope
  de 2.000 filas con aviso), y "Cómo se calcula".

## Contratos implementados / consumidos

- Consumidos (solo lectura por ORM):
  - modelos `bookings.Stay`, `Reservation` e `InventoryDay`; `finance.Charge`, `Payment`, `Refund` y
    `CashShift`; `inventory.RoomType`, `Room`, `Bed` y `RoomBlock`; `rates.RatePlan`;
  - `apps.bookings.services.queries.with_balance` (saldo por reserva, la misma regla de
    `finance.reservation_balance`) y `apps.finance.reporting.annotate_shift_cash`.
- Expuestos para otras apps (C9 copiloto, C12, D1), sin HTTP:
  - `apps.reports.params.make_params(report, prop, user=None, query={...})` y
    `apps.reports.service.run_report(report, params)`: dan cualquier reporte con las mismas validaciones del
    API. `REPORTS` y `get_report(id)` están en `apps.reports.registry`.
  - El motor: `engine.daily_figures(prop, start, end)`, `totals_of(days)`, `available_by_day`,
    `revenue_by_kind`, `segment_figures(prop, start, end, key)`, `comparison_range`.

## Señales emitidas / escuchadas

Ninguna.

## Automatizaciones registradas

Ninguna: los reportes se calculan al pedirlos.

## Proveedores de integración registrados

Ninguno.

## Extensiones de frontend exportadas (widgets, tabs, topbar, commands)

- `routes.tsx`: `app` `reports` (hub) y `reports/:reportId` (detalle), ambos lazy.
- `nav.ts`: sin cambios. Ítem `reports`, sección `insights`, permiso `reports.operational`.
- `widgets.tsx`: `reports-occupancy-14` (orden 35, `md`, permiso `reports.operational`). Muestra la ocupación
  de los próximos 14 días con el reporte `occupancy-outlook`: media, noche pico rotulada y enlace al reporte.
  Se carga perezosamente (Recharts solo se descarga si el widget se muestra).
- `commands.ts`: ⌘K "Ver reporte de rendimiento" (`reports.performance`), "Ver llegadas de hoy"
  (`reports.operational`) y "Ver ingresos diarios" (`reports.financial`).
- Componentes internos, reutilizables si otra feature los necesita:
  - `components/RangeRuler` (regla de días del rango);
  - `components/ChartCard` (gráfico + leyenda + vista de tabla);
  - `components/ReportTable` (tabla tipada con orden, búsqueda, paginación y totales);
  - `lib/format` (`compactMoney`, etc.).

Diseño y dataviz:

- **Paleta de gráficos** (`features/reports/viz.css`, validada con el validador de dataviz en todos los pares):
  - claro `#b4583b · #3b6fb6 · #179c84` (CVD ΔE ≥ 9,6; visión normal ≥ 17,3);
  - oscuro `#d4775c · #4f86cc · #1fa88f` (CVD ≥ 8,7; normal ≥ 15,7);
  - el slot 1 es el acento; gris de comparación; "previsto" es un paso más suave del acento;
  - los colores de estado no se usan como series.
- **Reglas de los gráficos**: un solo eje y; los KPIs cambian en pestañas; 2 px de separación en los apilados y
  extremo redondeado de 4 px; tooltip con todas las series; leyenda siempre que hay 2 o más series; vista
  "Tabla" en todo gráfico; los filtros van en una fila sobre el contenido; en una recarga se conserva el
  contenido anterior atenuado.
- **Elemento propio**: la **regla de rango**, un tick por día de negocio (el rango inclusivo se puede contar),
  con la muesca de "Hoy" y los días previstos en el tono suave; el periodo comparado va debajo en gris.
- **Filtros en la URL**: `?preset=thisMonth` (relativo a la fecha de negocio) o `?start=&end=`, más `compare`,
  `group_by`, `days` y `chart`. Así un enlace compartido reproduce la misma vista.

## Dependencias nuevas (pip/npm) y por qué

Ninguna. Se usan `openpyxl`, `reportlab` y `recharts`, que ya estaban instaladas.

## Cambios requeridos en archivos compartidos u otras apps

Ninguno. Todo se registra por auto-descubrimiento (rutas, nav, locales, widget, comandos, permisos, seed; `reports`
ya está en `SEED_ORDER`).

## Limitaciones conocidas / pendientes

- **Tests**: no se escribieron (modo MVP). Hay que cubrir, según el plan:
  - rangos con bordes (el día de salida no cuenta, fin inclusivo) y cruce de mes;
  - bloqueos, anulados, canceladas, no-show y exentos;
  - la comparación y el CSV exacto;
  - que XLSX y PDF se generen;
  - permisos y aislamiento.

  Las funciones del motor están pensadas para testearse sin HTTP.
- **Comisiones del marketplace**: el spec §5 las menciona entre los financieros, pero el plan C10 no las lista
  y los modelos son de C11 (`saas.Commission`). No hay reporte de comisiones; C11 las muestra en su panel. Si se
  quiere un reporte, se agrega un builder de solo lectura sobre `saas.Commission` en `builders/financial.py`.
- **Pickup**: se calcula con el estado actual (fecha de creación y de cancelación de cada reserva), no con fotos
  diarias del inventario. Un cambio de fechas de una reserva antigua no aparece como pickup. La ventana cuenta
  también lo reservado después de medianoche y antes de la auditoría nocturna.
- **Historia de inventario**: para fechas sin `InventoryDay`, el disponible se calcula con las habitaciones y
  camas **actuales**. Un cambio de inventario pasado no se reconstruye.
- **Demo**:
  - "Año anterior" sale en cero porque el seed cubre −60 a +90 días;
  - las reservas que el seed crea con fecha de hoy aparecen como un pico de pickup en la ventana de 1 día.
- **Semanas parciales**: al agrupar por semana, el primer bucket se rotula con su lunes aunque el rango empiece
  después (p. ej., "31 ago" para 1–6 sep). El encabezado dice "Semana (desde el lunes)".
- **Dinero**: se muestra en formato COP (`$ 470.115`) en ambos idiomas, como el resto de la app. Los números y
  porcentajes siguen el idioma.

## Cómo probarlo en la UI

Usuario demo `owner@casaaurora.co` / `housetel123` (Hotel Casa Aurora) en http://localhost:5173. Las cifras
esperadas son las del seed con fecha de negocio 27 sep 2026; cambian si la fecha de negocio avanza o si se crean
reservas o cargos.

1. **Hub**: menú **Análisis → Reportes** (`/app/reports`).
   - Arriba aparece "Este mes de un vistazo": Ocupación **58,2 %**, ADR **$ 470.115**, RevPAR **$ 273.688** e
     Ingresos de alojamiento **$ 196,5 M**.
   - Debajo, la regla de 30 ticks: "1–30 sep 2026 · 30 días · primer y último día incluidos · 26 reales ·
     4 previstos · Hoy 27 sep".
   - Luego las categorías Rendimiento (7), Operación (6), Finanzas (4) e Impuestos (1), cada reporte con su
     descripción.
2. **Rendimiento** (`/app/reports/performance`).
   - Los tiles y el total de la tabla cuadran con el hub: 718 disponibles, 418 vendidas, 58,2 %,
     $ 196.508.200.
   - El gráfico de ocupación es una línea continua hasta el 26 sep y punteada desde el 27 (previsto), con una
     regla "Hoy". En la tabla, del 27 al 30 sep el tipo es "Previsto".
   - Las pestañas ADR / RevPAR / Ingresos de alojamiento cambian el gráfico. **Tabla** muestra los mismos
     valores.
   - **Comparar con → Periodo anterior**: aparece la línea gris del periodo anterior, los deltas en los tiles
     (ocupación en pp) y la regla gris "Comparado con 2–31 ago 2026".
   - **Agrupar por → Semana / Mes**: columnas por semana o mes; los totales no cambian.
   - **Rango → Rango personalizado**: elige dos días; el disparador dice "Personalizado" y la regla cuenta los
     días.
3. **Exportar** (botón arriba a la derecha) → CSV para Excel / Excel (.xlsx) / PDF.
   - Se descargan `performance_casa-aurora_2026-09-01_2026-09-30.*`.
   - El CSV abre en Excel con columnas separadas y tildes. El XLSX tiene una hoja "Resumen" y otra con el
     detalle. El PDF tiene el encabezado Housetel · Hotel Casa Aurora.
4. **Ingresos por segmento**: Agrupar por Fuente, Canal, Categoría o Plan. Las barras horizontales muestran el
   valor y el %. La fila Total es siempre **$ 196.508.200** (igual a rendimiento).
5. **Pickup** (próximos 30 días): cambia "Reservado en" entre Último día, 7, 14 y 30 días. Las columnas por noche
   de estadía cambian, y también los KPIs "Pickup (noches)" y "Ocupación hace N días".
6. **Operación**:
   - **Llegadas**, Hoy: 2 llegadas (HT-D62XA4 VIP, HT-M2BDPV), con enlace a cada reserva y su saldo.
   - **Salidas** y **En casa**: el rango "Mañana" incluye confirmadas esperadas.
   - **Estado de habitaciones**: 24 habitaciones; la franja muestra limpia, sucia, inspeccionada y fuera de
     servicio (con rayado).
   - **Ocupación prevista**.
7. **Finanzas e impuestos**:
   - **Ingresos diarios**: columnas apiladas de alojamiento, extras y penalidades.
   - **Pagos por medio**: 29 ago–27 sep, **$ 404.040.189** en 384 pagos, 44,5 % en línea.
   - **Saldos por cobrar**: foto con paginación de 50 filas y antigüedad.
   - **Turnos de caja**.
   - **Impuestos**, mes pasado (ago): base gravada **$ 133.986.080**, IVA **$ 25.457.362**, base exenta
     **$ 61.312.240** (134 cargos) y no gravado **$ 7.866.955**.
8. **Panel Hoy** (`/app`): en "Más de tu hotel" aparece la tarjeta **Ocupación de los próximos 14 días**, con
   columnas por noche, la noche pico rotulada, "Media 61,4 %" y el enlace "Ver ocupación prevista".
9. **Permisos**:
   - `recepcion@casaaurora.co` solo ve la categoría Operación. Si abre `/app/reports/performance` ve "Tu rol no
     incluye este reporte".
   - `contabilidad@casaaurora.co` ve todo.
   - `limpieza@casaaurora.co` no ve el ítem Reportes.
   - `owner@grupoandino.co` ve sus hoteles. En **Andino Hostel Bogotá**, el rendimiento de sep da **62,4 %**
     (785 noches vendidas contando camas / 1.258 disponibles).
10. **Idioma, tema y móvil**:
    - En inglés, las etiquetas del reporte y de los exportes salen en inglés (el backend recibe `lang`).
    - En modo oscuro, los gráficos usan sus pasos oscuros.
    - A 375 px, los filtros se apilan, los KPIs van en 2 columnas y las tablas hacen scroll horizontal dentro de
      su tarjeta.
11. **⌘K**: escribe "rendimiento", "llegadas" o "ingresos" para abrir esos reportes.
