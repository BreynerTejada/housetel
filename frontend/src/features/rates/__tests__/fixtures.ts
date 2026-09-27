import { http, HttpResponse } from 'msw'
import type {
  BulkPayload,
  CancellationPolicy,
  GridResponse,
  GridRow,
  RatePlan,
  RoomTypeDefaults,
  RoomTypeOption,
  Season,
} from '../api'
import { weekdayOf } from '../lib/grid-utils'
import { server } from '@/test/server'

export const FLEX: RatePlan = {
  id: 'plan-flex',
  code: 'FLEX',
  name: { es: 'Tarifa flexible', en: 'Flexible rate' },
  kind: 'base',
  parent: null,
  derivation_type: 'percent',
  derivation_value: '0.00',
  room_types: ['rt-dbl', 'rt-ste'],
  meal_plan: 'room_only',
  cancellation_policy: null,
  deposit_percent: '0.00',
  is_public: true,
  channels: [],
  min_los_default: 1,
  is_active: true,
  sort_order: 10,
  children: ['plan-nr'],
}

export const NR: RatePlan = {
  ...FLEX,
  id: 'plan-nr',
  code: 'NR',
  name: { es: 'No reembolsable', en: 'Non-refundable' },
  kind: 'derived',
  parent: 'plan-flex',
  derivation_value: '-12.00',
  sort_order: 20,
  children: [],
}

/** 25 Sep 2026 is a Friday, 26 a Saturday and 27 a Sunday. */
export const DATES = ['2026-09-25', '2026-09-26', '2026-09-27']

export function gridRow(date: string, overrides: Partial<GridRow> = {}): GridRow {
  return {
    date,
    price: '320000.00',
    extra_adult_price: '60000.00',
    extra_child_price: '30000.00',
    min_los: null,
    max_los: null,
    cta: false,
    ctd: false,
    stop_sell: false,
    source: 'default',
    available: 4,
    ...overrides,
  }
}

export function makeGrid(overrides: Partial<GridResponse> = {}): GridResponse {
  return {
    rate_plan: {
      id: FLEX.id,
      code: FLEX.code,
      name: FLEX.name,
      kind: 'base',
      parent: null,
      derivation_type: 'percent',
      derivation_value: '0.00',
      editable: true,
    },
    currency: 'COP',
    start: '2026-09-25',
    end: '2026-10-09',
    dates: DATES,
    holidays: [{ date: '2026-09-27', name: 'Festivo de prueba' }],
    room_types: [
      {
        id: 'rt-dbl',
        code: 'DBL',
        name: { es: 'Estándar', en: 'Standard' },
        color: '#4E6C88',
        kind: 'private',
        rows: [
          gridRow(DATES[0]),
          gridRow(DATES[1], { price: '368000.00', source: 'season', available: 1 }),
          gridRow(DATES[2], { price: '300000.00', source: 'manual', available: 0, min_los: 2 }),
        ],
      },
      {
        id: 'rt-ste',
        code: 'STE',
        name: { es: 'Suite Vista al Mar', en: 'Sea View Suite' },
        color: '#B4583B',
        kind: 'private',
        rows: DATES.map((date) => gridRow(date, { price: '650000.00', available: 2 })),
      },
    ],
    ...overrides,
  }
}

export function page<T>(results: T[]) {
  return { count: results.length, next: null, previous: null, results }
}

/** A bulk write applied like the server does (whole pesos; a new price takes the request's `source`). */
function applyBulk(grid: GridResponse, body: BulkPayload): void {
  for (const roomType of grid.room_types) {
    if (!body.room_type_ids.includes(roomType.id)) continue
    for (const row of roomType.rows) {
      if (row.date < body.start || row.date >= body.end) continue
      if (body.weekdays.length > 0 && !body.weekdays.includes(weekdayOf(row.date))) continue
      const { set } = body
      const current = Number(row.price ?? 0)
      const price =
        set.price !== undefined
          ? Number(set.price)
          : set.price_delta_percent !== undefined
            ? current * (1 + Number(set.price_delta_percent) / 100)
            : set.price_delta_amount !== undefined
              ? current + Number(set.price_delta_amount)
              : null
      if (price !== null) Object.assign(row, { price: Math.max(Math.round(price), 0).toFixed(2), source: body.source ?? 'bulk' })
      if (set.min_los !== undefined) row.min_los = set.min_los
      if (set.max_los !== undefined) row.max_los = set.max_los
      if (set.cta !== undefined) row.cta = set.cta
      if (set.ctd !== undefined) row.ctd = set.ctd
      if (set.stop_sell !== undefined) row.stop_sell = set.stop_sell
    }
  }
}

/** The grid of a derived plan (−12 % or its amount) computed from the base plan's grid, read-only. */
function derivedGrid(base: GridResponse, plan: RatePlan): GridResponse {
  const derive = (price: string | null) => {
    if (price === null) return null
    const value = Number(plan.derivation_value)
    const result = plan.derivation_type === 'amount' ? Number(price) + value : Number(price) * (1 + value / 100)
    return Math.max(Math.round(result), 0).toFixed(2)
  }
  return {
    ...base,
    rate_plan: {
      id: plan.id,
      code: plan.code,
      name: plan.name,
      kind: 'derived',
      parent: plan.parent,
      derivation_type: plan.derivation_type,
      derivation_value: plan.derivation_value,
      editable: false,
    },
    room_types: base.room_types.map((roomType) => ({
      ...roomType,
      rows: roomType.rows.map((row) => ({ ...row, price: derive(row.price) })),
    })),
  }
}

/**
 * Default handlers of the rates grid page, backed by a small in-memory server: bulk writes change the grid
 * they return afterwards, and a derived plan's grid follows its base plan. Returns the captured requests.
 */
export function mockGridApi({ grid = makeGrid(), plans = [FLEX, NR] }: { grid?: GridResponse; plans?: RatePlan[] } = {}) {
  const bulkRequests: unknown[] = []
  const gridRequests: URL[] = []
  const state: GridResponse = structuredClone(grid)
  server.use(
    http.get('/api/v1/rates/grid/', ({ request }) => {
      const url = new URL(request.url)
      gridRequests.push(url)
      const requested = plans.find((plan) => plan.id === url.searchParams.get('rate_plan'))
      const derived = requested?.kind === 'derived' && requested.parent === state.rate_plan?.id
      return HttpResponse.json(derived ? derivedGrid(state, requested) : state)
    }),
    http.get('/api/v1/rates/rate-plans/', () => HttpResponse.json(page(plans))),
    http.post('/api/v1/rates/grid/bulk/', async ({ request }) => {
      const body = (await request.json()) as BulkPayload
      bulkRequests.push(body)
      applyBulk(state, body)
      return HttpResponse.json({ updated: 1, audit_event_id: `evt-${bulkRequests.length}` })
    }),
    http.get('/api/v1/control/audit/:id/', () => new HttpResponse('<h1>Not found</h1>', { status: 404 })),
  )
  return { bulkRequests, gridRequests }
}

// ---- Plans page (/app/rates/plans) ----------------------------------------------------------------------

export const ROOM_TYPES: RoomTypeOption[] = [
  {
    id: 'rt-dbl',
    code: 'DBL',
    name: { es: 'Estándar', en: 'Standard' },
    kind: 'private',
    color: '#4E6C88',
    base_occupancy: 2,
    max_adults: 3,
    max_children: 2,
    max_occupancy: 4,
    is_active: true,
    sort_order: 1,
  },
  {
    id: 'rt-ste',
    code: 'STE',
    name: { es: 'Suite Vista al Mar', en: 'Sea View Suite' },
    kind: 'private',
    color: '#B4583B',
    base_occupancy: 2,
    max_adults: 2,
    max_children: 1,
    max_occupancy: 3,
    is_active: true,
    sort_order: 2,
  },
]

export const POLICIES: CancellationPolicy[] = [
  {
    id: 'pol-flex',
    name: { es: 'Flexible 48h', en: 'Flexible 48h' },
    non_refundable: false,
    free_until_hours_before: 48,
    penalty_type: 'first_night',
    penalty_value: '0.00',
    description: { es: '', en: '' },
    plans_count: 2,
  },
  {
    id: 'pol-nr',
    name: { es: 'No reembolsable', en: 'Non-refundable' },
    non_refundable: true,
    free_until_hours_before: 0,
    penalty_type: 'full',
    penalty_value: '0.00',
    description: { es: '', en: '' },
    plans_count: 1,
  },
]

export const PLAN_FLEX: RatePlan = { ...FLEX, cancellation_policy: 'pol-flex', children: ['plan-nr', 'plan-bb'] }
export const PLAN_NR: RatePlan = { ...NR, cancellation_policy: 'pol-nr' }
export const PLAN_BB: RatePlan = {
  ...NR,
  id: 'plan-bb',
  code: 'BB',
  name: { es: 'Con desayuno', en: 'Breakfast included' },
  derivation_type: 'amount',
  derivation_value: '35000.00',
  meal_plan: 'breakfast',
  cancellation_policy: 'pol-flex',
  room_types: ['rt-dbl'],
  sort_order: 30,
}

export const DBL_DEFAULTS: RoomTypeDefaults = {
  id: 'def-dbl',
  room_type: 'rt-dbl',
  rate_plan: 'plan-flex',
  price: '320000.00',
  dow_adjustments: { fri: 15, sat: 15 },
  extra_adult_price: '60000.00',
  extra_child_price: '30000.00',
  child_age_limit: 12,
  single_occupancy_price: null,
}

export const HIGH_SEASON: Season = {
  id: 'season-high',
  name: 'Alta fin de año',
  start_date: '2026-12-15',
  end_date: '2027-01-15',
  priority: 10,
  color: '#B98A2E',
  rates: [{ id: 'sr-dbl', room_type: 'rt-dbl', rate_plan: 'plan-flex', price: '416000.00', dow_adjustments: { fri: 15, sat: 15 } }],
}

interface Captured {
  method: string
  path: string
  body: unknown
}

/** Handlers of the plans page; every write is captured (method, path, JSON body). */
export function mockPlansApi({
  plans = [PLAN_FLEX, PLAN_NR, PLAN_BB],
  defaults = [DBL_DEFAULTS],
  seasons = [HIGH_SEASON],
}: { plans?: RatePlan[]; defaults?: RoomTypeDefaults[]; seasons?: Season[] } = {}) {
  const writes: Captured[] = []
  const capture = async (request: Request, path: string) => {
    const body = request.method === 'DELETE' ? null : await request.json()
    writes.push({ method: request.method, path, body })
    return body as Record<string, unknown>
  }
  server.use(
    http.get('/api/v1/rates/rate-plans/', () => HttpResponse.json(page(plans))),
    http.get('/api/v1/rates/room-types/', () => HttpResponse.json(ROOM_TYPES)),
    http.get('/api/v1/rates/room-type-defaults/', () => HttpResponse.json(page(defaults))),
    http.get('/api/v1/rates/cancellation-policies/', () => HttpResponse.json(page(POLICIES))),
    http.get('/api/v1/rates/seasons/', () => HttpResponse.json(page(seasons))),
    http.get('/api/v1/rates/holidays/', () => HttpResponse.json([{ date: '2026-12-08', name: 'Inmaculada Concepción' }])),
    http.post('/api/v1/rates/rate-plans/', async ({ request }) => {
      const body = await capture(request, 'rate-plans')
      return HttpResponse.json({ ...PLAN_FLEX, ...body, id: 'plan-new', children: [] }, { status: 201 })
    }),
    http.patch('/api/v1/rates/rate-plans/:id/', async ({ request, params }) => {
      const body = await capture(request, `rate-plans/${String(params.id)}`)
      return HttpResponse.json({ ...plans.find((plan) => plan.id === params.id), ...body })
    }),
    http.delete('/api/v1/rates/rate-plans/:id/', async ({ request, params }) => {
      await capture(request, `rate-plans/${String(params.id)}`)
      return new HttpResponse(null, { status: 204 })
    }),
    http.post('/api/v1/rates/room-type-defaults/', async ({ request }) => {
      const body = await capture(request, 'room-type-defaults')
      return HttpResponse.json({ ...body, id: 'def-new' }, { status: 201 })
    }),
    http.post('/api/v1/rates/seasons/', async ({ request }) => {
      const body = await capture(request, 'seasons')
      return HttpResponse.json({ ...body, id: 'season-new', rates: [] }, { status: 201 })
    }),
    http.patch('/api/v1/rates/seasons/:id/', async ({ request, params }) => {
      const body = await capture(request, `seasons/${String(params.id)}`)
      return HttpResponse.json({ ...seasons.find((item) => item.id === params.id), ...body })
    }),
    http.post('/api/v1/rates/season-rates/', async ({ request }) => {
      const body = await capture(request, 'season-rates')
      return HttpResponse.json({ ...body, id: 'sr-new' }, { status: 201 })
    }),
  )
  return writes
}
