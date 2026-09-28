import { http, HttpResponse } from 'msw'
import { server } from '@/test/server'
import type {
  CalendarCell,
  CalendarResponse,
  DecisionResult,
  PriceBounds,
  PricingRule,
  Recommendation,
  RevenueOptions,
  RevenueRun,
  RevenueSettings,
  RevenueSummary,
} from '../api'

export const DBL = { id: 'rt-dbl', code: 'DBL', name: { es: 'Estándar', en: 'Standard' }, color: '#4e6c88' }
export const STE = { id: 'rt-ste', code: 'STE', name: { es: 'Suite Vista al Mar', en: 'Sea View Suite' }, color: '#b4583b' }
export const FLEX = { id: 'plan-flex', code: 'FLEX', name: { es: 'Tarifa flexible', en: 'Flexible rate' } }

/** The business date of the Aurora fixture property (a Friday). */
export const TODAY = '2026-09-25'

export function calendarCell(id: string, overrides: Partial<CalendarCell> = {}): CalendarCell {
  return {
    id,
    status: 'pending',
    change_percent: '12.00',
    current_price: '320000.00',
    recommended_price: '358000.00',
    occupancy: '88.00',
    ...overrides,
  }
}

function datesFrom(start: string, end: string): string[] {
  const dates: string[] = []
  const [y, m, d] = start.split('-').map(Number)
  for (let day = new Date(y, m - 1, d); ; day.setDate(day.getDate() + 1)) {
    const iso = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, '0')}-${String(day.getDate()).padStart(2, '0')}`
    if (iso >= end) break
    dates.push(iso)
  }
  return dates
}

/**
 * Estándar: +12 % on Saturday 26 Sep (pending), −8 % on Monday 28 (pending), applied on Sunday 27.
 * Suite: +15 % on Saturday 26 (pending) and a rejected one on Tuesday 29.
 */
export function makeCalendar(start = TODAY, end = '2026-10-25'): CalendarResponse {
  return {
    start,
    end,
    business_date: TODAY,
    currency: 'COP',
    dates: datesFrom(start, end),
    holidays: [{ date: '2026-10-12', name: 'Día de la Raza' }],
    rows: [
      {
        room_type: DBL,
        rate_plan: FLEX,
        cells: {
          '2026-09-26': calendarCell('rec-dbl-26'),
          '2026-09-27': calendarCell('rec-dbl-27', { status: 'applied', change_percent: '5.00', recommended_price: '336000.00' }),
          '2026-09-28': calendarCell('rec-dbl-28', { change_percent: '-8.00', recommended_price: '294000.00', occupancy: '10.00' }),
        },
      },
      {
        room_type: STE,
        rate_plan: FLEX,
        cells: {
          '2026-09-26': calendarCell('rec-ste-26', { change_percent: '15.00', current_price: '650000.00', recommended_price: '748000.00' }),
          '2026-09-29': calendarCell('rec-ste-29', { status: 'rejected', change_percent: '-5.00' }),
        },
      },
    ],
  }
}

export function makeRun(overrides: Partial<RevenueRun> = {}): RevenueRun {
  return {
    id: 'run-1',
    started_at: '2026-09-25T05:00:02-05:00',
    finished_at: '2026-09-25T05:00:04-05:00',
    status: 'success',
    trigger: 'automation',
    triggered_by: null,
    start_date: TODAY,
    end_date: '2027-01-23',
    recommendations_count: 3,
    auto_applied_count: 0,
    expired_count: 0,
    summary: {
      es: 'Se revisaron las noches del 25/09/2026 al 22/01/2027: 3 recomendaciones.',
      en: 'Nights from Sep 25, 2026 to Jan 22, 2027 reviewed: 3 recommendations.',
    },
    ai_summary: {
      es: 'Suben los sábados con alta ocupación; baja el lunes 28 porque casi no hay reservas.',
      en: 'Saturdays with high occupancy go up; Monday 28 drops because it is almost empty.',
    },
    ai_provider: 'gemini',
    details: { count: 3, up: 2, down: 1, estimated_impact: '1250000.00', impact_up: '1500000.00', impact_down: '-250000.00' },
    ...overrides,
  }
}

export function makeSummary(overrides: Partial<RevenueSummary> = {}): RevenueSummary {
  return {
    pending: 3,
    up: 2,
    down: 1,
    avg_change_percent: '6.33',
    estimated_impact: '1250000.00',
    impact_up: '1500000.00',
    impact_down: '-250000.00',
    first_date: '2026-09-26',
    currency: 'COP',
    enabled: true,
    auto_apply: false,
    last_run: makeRun(),
    ...overrides,
  }
}

export function makeRecommendation(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    id: 'rec-dbl-26',
    room_type: DBL,
    rate_plan: FLEX,
    date: '2026-09-26',
    current_price: '320000.00',
    current_source: 'default',
    anchor_price: '320000.00',
    anchor_source: 'default',
    recommended_price: '358000.00',
    change_percent: '12.00',
    adjustment_percent: '23.00',
    occupancy: '88.00',
    available_units: 1,
    reasons: [
      {
        type: 'rule',
        rule_id: 'rule-occ',
        name: 'Ocupación',
        kind: 'occupancy',
        combine: 'stack',
        adjust: '15.00',
        applied: true,
        detail: { occupancy: '88.00' },
      },
      {
        type: 'rule',
        rule_id: 'rule-sat',
        name: 'Sábados',
        kind: 'day_of_week',
        combine: 'stack',
        adjust: '8.00',
        applied: true,
        detail: { weekday: 'sat' },
      },
      { type: 'limit', kind: 'max_daily_change', percent: '20.00', price: '384000.00' },
    ],
    explanation: {
      es: 'Sube 12 % (de $ 320.000 a $ 358.000): ocupación del 88 % (+15 %); sábado (+8 %).',
      en: 'Up 12% (from $320,000 to $358,000): 88% occupancy (+15%); Saturday (+8%).',
    },
    status: 'pending',
    decided_by: null,
    decided_at: null,
    applied_at: null,
    apply_error: '',
    run: 'run-1',
    created_at: '2026-09-25T05:00:03-05:00',
    ...overrides,
  }
}

export const SETTINGS: RevenueSettings = {
  enabled: true,
  auto_apply: false,
  horizon_days: 120,
  max_daily_change_percent: '20.00',
  min_change_percent: '2.00',
  price_rounding: '1000.00',
  updated_at: '2026-09-25T05:00:00-05:00',
}

export const OPTIONS: RevenueOptions = {
  currency: 'COP',
  business_date: TODAY,
  room_types: [
    { ...DBL, kind: 'private' },
    { ...STE, kind: 'private' },
  ],
  rate_plans: [{ ...FLEX, room_types: [DBL.id, STE.id], default_prices: { [DBL.id]: '320000.00', [STE.id]: '650000.00' } }],
}

export const RULES: PricingRule[] = [
  {
    id: 'rule-occ',
    name: 'Ocupación',
    kind: 'occupancy',
    room_types: [],
    params: {
      tiers: [
        { min: 0, max: 40, adjust: -8 },
        { min: 70, max: 85, adjust: 8 },
        { min: 85, max: 100, adjust: 15 },
      ],
    },
    priority: 40,
    combine: 'stack',
    is_active: true,
    created_at: '',
    updated_at: '',
  },
  {
    id: 'rule-sat',
    name: 'Sábados',
    kind: 'day_of_week',
    room_types: [STE.id],
    params: { sat: 8 },
    priority: 10,
    combine: 'stack',
    is_active: false,
    created_at: '',
    updated_at: '',
  },
]

export const BOUNDS: PriceBounds[] = [
  { id: 'bounds-dbl', room_type: DBL.id, rate_plan: FLEX.id, min_price: '240000.00', max_price: '512000.00', updated_at: '' },
]

export interface RevenueApiLog {
  calendarRequests: URL[]
  decisions: { decision: string; ids: string[] }[]
  detailRequests: string[]
}

/** Handlers for the whole revenue API; each decision marks its ids with the resulting status. */
export function mockRevenueApi({
  calendar = makeCalendar(),
  summary = makeSummary(),
  recommendations = {} as Record<string, Recommendation>,
  decisionResult,
}: {
  calendar?: CalendarResponse
  summary?: RevenueSummary
  recommendations?: Record<string, Recommendation>
  decisionResult?: (decision: string, ids: string[]) => DecisionResult
} = {}): RevenueApiLog {
  const log: RevenueApiLog = { calendarRequests: [], decisions: [], detailRequests: [] }
  let current = structuredClone(calendar)
  server.use(
    http.get('/api/v1/revenue/recommendations/summary/', () => HttpResponse.json(summary)),
    http.get('/api/v1/revenue/recommendations/calendar/', ({ request }) => {
      const url = new URL(request.url)
      log.calendarRequests.push(url)
      const start = url.searchParams.get('start') ?? TODAY
      const end = url.searchParams.get('end') ?? '2026-10-25'
      return HttpResponse.json({ ...current, start, end, dates: datesFrom(start, end) })
    }),
    http.get('/api/v1/revenue/recommendations/:id/', ({ params }) => {
      const id = String(params.id)
      log.detailRequests.push(id)
      return HttpResponse.json(recommendations[id] ?? makeRecommendation({ id }))
    }),
    http.post('/api/v1/revenue/recommendations/:decision/', async ({ params, request }) => {
      const decision = String(params.decision)
      const { ids } = (await request.json()) as { ids: string[] }
      log.decisions.push({ decision, ids })
      const status = decision === 'reject' ? 'rejected' : 'applied'
      current = {
        ...current,
        rows: current.rows.map((row) => ({
          ...row,
          cells: Object.fromEntries(
            Object.entries(row.cells).map(([date, item]) => [date, ids.includes(item.id) ? { ...item, status } : item]),
          ),
        })),
      }
      const result: DecisionResult = decisionResult?.(decision, ids) ?? {
        updated: ids.length,
        skipped: [],
        errors: [],
        recommendations: ids.map((id) => makeRecommendation({ id, status })),
      }
      return HttpResponse.json(result)
    }),
  )
  return log
}
