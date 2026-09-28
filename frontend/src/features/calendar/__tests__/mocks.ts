import { http, HttpResponse, type JsonBodyType } from 'msw'
import type { GridResponse } from '@/features/rates/api'
import type { Me } from '@/lib/auth'
import { auroraMembership, auroraProperty, makeMe } from '@/test/fixtures'
import { server } from '@/test/server'
import type { CalendarData, CalStay, ReservationDetail } from '../api'
import { addDays, dayList, isWeekendNight } from '../lib/dates'
import { BUSINESS_DATE, IDS, makeCalendar } from './fixtures'

/** Casa Aurora with the business date of the fixtures, for a user holding `permissions`. */
export function calendarMe(permissions: string[] = ['*']): Me {
  const membership = auroraMembership(permissions, permissions.includes('*') ? 'owner' : 'custom')
  return makeMe({ memberships: [{ ...membership, properties: [{ ...auroraProperty, business_date: BUSINESS_DATE }] }] })
}

const PRICES: Record<string, number> = { [IDS.dbl]: 320000, [IDS.ste]: 650000, [IDS.dorm]: 65000 }

export function makeGridResponse(data: CalendarData, start: string, end: string): GridResponse {
  const days = dayList(start, Math.max(0, Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000)))
  return {
    rate_plan: {
      id: 'plan-flex',
      code: 'FLEX',
      name: { es: 'Tarifa flexible', en: 'Flexible rate' },
      kind: 'base',
      parent: null,
      derivation_type: 'percent',
      derivation_value: '0.00',
      editable: true,
    },
    currency: 'COP',
    start,
    end,
    dates: days,
    holidays: [],
    room_types: data.room_types.map((roomType) => ({
      id: roomType.id,
      code: roomType.code,
      name: roomType.name,
      color: roomType.color,
      kind: roomType.kind,
      rows: days.map((date) => {
        const base = PRICES[roomType.id] ?? 100000
        const price = isWeekendNight(date) ? Math.round(base * 1.15) : base
        return {
          date,
          price: `${price}.00`,
          extra_adult_price: '0.00',
          extra_child_price: '0.00',
          min_los: null,
          max_los: null,
          cta: false,
          ctd: false,
          stop_sell: roomType.id === IDS.ste && date === '2026-10-18',
          source: 'default' as const,
          available: 1,
        }
      }),
    })),
  }
}

/** A `ReservationDetail` for a stay of the calendar (one stay, confirmed data). */
export function makeDetail(stay: CalStay, data: CalendarData, overrides: Partial<ReservationDetail> = {}): ReservationDetail {
  const roomType = data.room_types.find((candidate) => candidate.id === stay.room_type_id)!
  const room = data.room_types.flatMap((candidate) => candidate.rooms).find((candidate) => candidate.id === stay.room_id)
  const nights = Math.round((Date.parse(stay.checkout) - Date.parse(stay.checkin)) / 86_400_000)
  return {
    id: stay.reservation_id,
    code: stay.code,
    status: stay.status,
    source: stay.source,
    channel_code: stay.channel_code,
    checkin_date: stay.checkin,
    checkout_date: stay.checkout,
    nights,
    adults: stay.adults,
    children: stay.children,
    currency: 'COP',
    total_amount: `${nights * 380800}.00`,
    balance: stay.balance_due ? '380800.00' : '0.00',
    hold_expires_at: null,
    booker: { id: `guest-${stay.id}`, full_name: stay.guest_name, email: '', phone: '+573001234567', is_vip: stay.is_vip, nationality: 'CO' },
    stays: [
      {
        id: stay.id,
        status: stay.status,
        checkin_date: stay.checkin,
        checkout_date: stay.checkout,
        nights,
        adults: stay.adults,
        children: stay.children,
        room_type: { id: roomType.id, code: roomType.code, name: roomType.name, kind: roomType.kind, color: roomType.color },
        rate_plan: { id: 'plan-flex', code: 'FLEX', name: { es: 'Tarifa flexible', en: 'Flexible rate' }, meal_plan: 'room_only' },
        room: room ? { id: room.id, number: room.number, floor: room.floor, housekeeping_status: room.housekeeping_status } : null,
        bed: null,
        locked_room: false,
        total_amount: `${nights * 380800}.00`,
      },
    ],
    eta: null,
    special_requests: '',
    notes: '',
    flags: {
      ready_for_checkin: false,
      arrives_today: stay.checkin === BUSINESS_DATE,
      departs_today: false,
      in_house: stay.status === 'checked_in',
      unassigned: stay.room_id === null,
      balance_due: stay.balance_due,
    },
    ...overrides,
  }
}

export interface CalendarApi {
  data: CalendarData
  calendarRequests: URL[]
  gridRequests: URL[]
  posts: { path: string; body: JsonBodyType }[]
}

/** Answers every GET the calendar makes (calendar, grid, holidays, reservation detail) from one `CalendarData`. */
export function mockCalendarApi(data: CalendarData = makeCalendar()): CalendarApi {
  const state: CalendarApi = { data, calendarRequests: [], gridRequests: [], posts: [] }
  server.use(
    http.get('/api/v1/bookings/calendar/', ({ request }) => {
      state.calendarRequests.push(new URL(request.url))
      return HttpResponse.json(state.data)
    }),
    http.get('/api/v1/rates/grid/', ({ request }) => {
      const url = new URL(request.url)
      state.gridRequests.push(url)
      const start = url.searchParams.get('start') ?? BUSINESS_DATE
      const end = url.searchParams.get('end') ?? addDays(start, 14)
      return HttpResponse.json(makeGridResponse(state.data, start, end))
    }),
    http.get('/api/v1/rates/holidays/', ({ request }) => {
      const year = new URL(request.url).searchParams.get('year')
      return HttpResponse.json(year === '2026' ? [{ date: '2026-10-12', name: 'Día de la Raza' }] : [])
    }),
    http.get('/api/v1/bookings/reservations/:id/', ({ params }) => {
      const stay = state.data.stays.find((candidate) => candidate.reservation_id === params.id)
      if (!stay) return HttpResponse.json({ detail: 'No encontrado', code: 'not_found' }, { status: 404 })
      return HttpResponse.json(makeDetail(stay, state.data))
    }),
  )
  return state
}

/** Records a POST and answers it with `respond(body)` (default: the reservation detail of the stay). */
export function mockPost(
  api: CalendarApi,
  path: string,
  respond?: (body: JsonBodyType) => { status: number; json: JsonBodyType },
) {
  server.use(
    http.post(`/api/v1${path}`, async ({ request, params }) => {
      const body = request.headers.get('Content-Type')?.includes('json') ? ((await request.json()) as JsonBodyType) : null
      api.posts.push({ path: new URL(request.url).pathname, body })
      if (respond) {
        const { status, json } = respond(body)
        return HttpResponse.json(json, { status })
      }
      const stay = api.data.stays.find((candidate) => candidate.id === params.id) ?? api.data.stays[0]
      return HttpResponse.json(makeDetail(stay, api.data))
    }),
  )
}
