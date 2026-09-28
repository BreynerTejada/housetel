/**
 * API payloads of the front desk tests, with the exact shapes of the backend (docs/integration-notes/
 * C1-frontdesk.md and B2b-bookings.md). Business date of every fixture: 2026-10-01.
 */
import { http, HttpResponse } from 'msw'
import { makeFolio, summaryOf } from '@/features/finance/__tests__/fixtures'
import type { FolioDetail } from '@/features/finance/api'
import type { Me, Membership, PropertySummary } from '@/lib/auth'
import { makeMe } from '@/test/fixtures'
import { server } from '@/test/server'
import type {
  NightAuditPreview,
  NightAuditReport,
  NightAuditSummary,
  Offer,
  RackRoom,
  ReservationDetail,
  ReservationListItem,
  RoomOption,
  StayDetail,
  TodayBoard,
  TodayRow,
} from '../api'

export const BD = '2026-10-01'

export const property: PropertySummary = {
  id: '6f1c2a4e-0000-4000-8000-00000000a001',
  name: 'Hotel Casa Aurora',
  slug: 'casa-aurora',
  property_type: 'boutique',
  timezone: 'America/Bogota',
  currency: 'COP',
  business_date: BD,
}

export const FRONT_DESK = [
  'frontdesk.view',
  'bookings.view',
  'bookings.manage',
  'bookings.checkin',
  'bookings.cancel',
  'guests.view',
  'guests.manage',
  'finance.view',
  'finance.collect',
  'finance.cashier',
  'housekeeping.view',
  'inventory.view',
  'rates.view',
]

export function membership(permissions: string[] = ['*'], roleCode = 'owner'): Membership {
  return {
    organization: { id: 'org-aurora', name: 'Casa Aurora', slug: 'casa-aurora', status: 'active' },
    role: { id: `role-${roleCode}`, name: roleCode, code: roleCode },
    permissions,
    properties: [property],
  }
}

/** A signed-in member of Casa Aurora whose business date is 2026-10-01. */
export function deskMe(permissions: string[] = ['*'], overrides: Partial<Me> = {}): Me {
  return makeMe({ full_name: 'Andrés Gómez', memberships: [membership(permissions)], ...overrides })
}

const DBL = { id: 'rt-dbl', code: 'DBL', name: { es: 'Estándar', en: 'Standard' }, kind: 'private' as const, color: '#4E6C88' }
const STE = { id: 'rt-ste', code: 'STE', name: { es: 'Suite Vista al Mar', en: 'Sea View Suite' }, kind: 'private' as const, color: '#B4583B' }

export const roomTypes = { DBL, STE }

export function makeRow(overrides: Partial<TodayRow> = {}): TodayRow {
  return {
    stay_id: 'stay-1',
    reservation_id: 'res-1',
    code: 'HT-7K2M9Q',
    status: 'confirmed',
    reservation_status: 'confirmed',
    source: 'phone',
    channel_code: '',
    guest_id: 'guest-1',
    guest_name: 'Valeria Mejía',
    is_vip: false,
    room_id: 'room-101',
    room: '101',
    bed_id: null,
    bed: null,
    room_status: 'clean',
    room_type: DBL,
    checkin: BD,
    checkout: '2026-10-03',
    nights: 2,
    adults: 2,
    children: 0,
    eta: '15:30',
    balance: '761600.00',
    balance_due: '761600.00',
    online_checkin_done: false,
    checked_in_at: null,
    checked_out_at: null,
    departs_today: false,
    occupied_by: null,
    done: false,
    ready: true,
    issues: [],
    ...overrides,
  }
}

export function makeRackRoom(overrides: Partial<RackRoom> = {}): RackRoom {
  return {
    id: 'room-101',
    number: '101',
    floor: '1',
    room_type: { id: DBL.id, code: DBL.code, color: DBL.color, kind: 'private' },
    housekeeping_status: 'clean',
    blocked: false,
    occupant: null,
    arrival: null,
    beds: null,
    ...overrides,
  }
}

export function makeBoard(overrides: Partial<TodayBoard> = {}): TodayBoard {
  return {
    business_date: BD,
    calendar_date: BD,
    currency: 'COP',
    kpis: {
      occupancy_pct: 62.5,
      rooms_occupied: 15,
      rooms_available: 24,
      rooms_blocked: 0,
      rooms_free: 9,
      arrivals_total: 4,
      arrivals_done: 1,
      arrivals_late: 0,
      departures_total: 6,
      departures_done: 3,
      departures_overdue: 0,
      in_house: 18,
      guests_in_house: 32,
      room_revenue_today: '1675000.00',
      other_revenue_today: '430800.00',
      revenue_today: '2105800.00',
      adr_today: '335000.00',
      collected_today: '111600.00',
    },
    arrivals: [makeRow()],
    departures: [],
    in_house: [],
    rooms: [makeRackRoom()],
    previous: null,
    night_audit: { due: false, last_report: null },
    ...overrides,
  }
}

export function makeStay(overrides: Partial<StayDetail> = {}): StayDetail {
  return {
    id: 'stay-1',
    status: 'confirmed',
    checkin_date: BD,
    checkout_date: '2026-10-03',
    nights: 2,
    adults: 2,
    children: 0,
    children_ages: [],
    room_type: DBL,
    rate_plan: { id: 'plan-flex', code: 'FLEX', name: { es: 'Tarifa flexible', en: 'Flexible rate' }, meal_plan: 'room_only' },
    room: { id: 'room-101', number: '101', floor: '1', housekeeping_status: 'clean' },
    bed: null,
    locked_room: false,
    nightly_rates: [
      { date: BD, amount: '380800.00', net: '320000.00', tax: '60800.00' },
      { date: '2026-10-02', amount: '380800.00', net: '320000.00', tax: '60800.00' },
    ],
    total_amount: '761600.00',
    checked_in_at: null,
    checked_out_at: null,
    occupants: [],
    ...overrides,
  }
}

export const booker = {
  id: 'guest-1',
  first_name: 'Valeria',
  last_name: 'Mejía',
  full_name: 'Valeria Mejía',
  email: 'valeria@example.com',
  phone: '+573001234567',
  is_vip: false,
  document_type: 'CC',
  document_number: '52123456',
  nationality: 'CO',
  country_of_residence: 'CO',
  language: 'es',
  is_foreign_non_resident: false,
}

export function makeReservation(overrides: Partial<ReservationDetail> = {}): ReservationDetail {
  return {
    id: 'res-1',
    code: 'HT-7K2M9Q',
    status: 'confirmed',
    source: 'phone',
    channel_code: '',
    external_id: '',
    checkin_date: BD,
    checkout_date: '2026-10-03',
    nights: 2,
    adults: 2,
    children: 0,
    currency: 'COP',
    total_amount: '761600.00',
    balance: '761600.00',
    guarantee: 'none',
    hold_expires_at: null,
    created_at: '2026-09-20T10:00:00-05:00',
    booker,
    group: null,
    stays: [makeStay()],
    language: 'es',
    eta: '15:30:00',
    special_requests: '',
    notes: '',
    promo_code: '',
    cancellation_policy_snapshot: {},
    cancelled_at: null,
    cancellation_reason: '',
    cancellation_fee: '0.00',
    custom_values: {},
    tags: [],
    external_payload: {},
    created_by: { id: 'user-1', full_name: 'Andrés Gómez', email: 'recepcion@casaaurora.co' },
    updated_at: '2026-09-20T10:00:00-05:00',
    folio_id: 'folio-1',
    portal_url: 'http://localhost:5173/g/token',
    flags: { ready_for_checkin: true, arrives_today: true, departs_today: false, in_house: false, unassigned: false, balance_due: true },
    ...overrides,
  }
}

export function makeListItem(overrides: Partial<ReservationListItem> = {}): ReservationListItem {
  return {
    id: 'res-1',
    code: 'HT-7K2M9Q',
    status: 'confirmed',
    source: 'phone',
    channel_code: '',
    external_id: '',
    checkin_date: BD,
    checkout_date: '2026-10-03',
    nights: 2,
    adults: 2,
    children: 0,
    currency: 'COP',
    total_amount: '761600.00',
    balance: '761600.00',
    guarantee: 'none',
    hold_expires_at: null,
    created_at: '2026-09-20T10:00:00-05:00',
    booker: { id: 'guest-1', full_name: 'Valeria Mejía', email: 'valeria@example.com', phone: '', is_vip: false, nationality: 'CO' },
    group: null,
    stays: [{ id: 'stay-1', status: 'confirmed', room_type: DBL, room: { id: 'room-101', number: '101' }, bed: null }],
    ...overrides,
  }
}

export function makeRoomOption(overrides: Partial<RoomOption> = {}): RoomOption {
  return {
    room_id: 'room-102',
    room_number: '102',
    floor: '1',
    room_type_id: DBL.id,
    room_type_code: 'DBL',
    bed_id: null,
    bed_label: null,
    housekeeping_status: 'clean',
    ready: true,
    same_category: true,
    ...overrides,
  }
}

export function makeOffer(overrides: Partial<Offer> = {}): Offer {
  const quote = {
    room_type_id: DBL.id,
    rate_plan_id: 'plan-flex',
    checkin: BD,
    checkout: '2026-10-03',
    adults: 2,
    children: 0,
    nights: [
      { date: BD, base: '320000.00', extra_adults: '0.00', extra_children: '0.00', discount: '0.00', total: '320000.00' },
      { date: '2026-10-02', base: '320000.00', extra_adults: '0.00', extra_children: '0.00', discount: '0.00', total: '320000.00' },
    ],
    subtotal: '640000.00',
    discount_total: '0.00',
    taxes: [{ code: 'IVA', name: 'IVA 19%', rate: '19.00', amount: '121600.00', included: false, exempt: false }],
    tax_total: '121600.00',
    total: '761600.00',
    currency: 'COP',
    restrictions_ok: true,
    violations: [],
    promo_applied: null,
  }
  return {
    room_type_id: DBL.id,
    rate_plan_id: 'plan-flex',
    room_type: { ...DBL, max_adults: 3, max_children: 2, max_occupancy: 4 },
    rate_plan: {
      id: 'plan-flex',
      code: 'FLEX',
      name: { es: 'Tarifa flexible', en: 'Flexible rate' },
      meal_plan: 'room_only',
      is_public: true,
      deposit_percent: '0.00',
      cancellation_policy: { name: { es: 'Flexible 48h', en: 'Flexible 48h' }, non_refundable: false, free_until_hours_before: 48, penalty_type: 'first_night' },
    },
    available_units: 3,
    units_needed: 1,
    quote,
    total: '761600.00',
    ...overrides,
  }
}

export function makeAuditSummary(overrides: Partial<NightAuditSummary> = {}): NightAuditSummary {
  return {
    business_date: BD,
    next_business_date: '2026-10-02',
    auto_no_show: true,
    room_charges: { stays: 18, nights: 18, net: '5400000.00', tax: '1026000.00', total: '6426000.00' },
    no_shows: [{ reservation_id: 'res-7', code: 'HT-NOSHOW', guest_name: 'Carlos Pérez', checkin: BD, fee: '380800.00' }],
    no_show_fees: '380800.00',
    overdue_departures: [],
    pending_tentative: [],
    errors: [],
    activity: { arrivals: 4, departures: 6, in_house: 18, cancellations: 1, no_shows: 1 },
    figures: {
      rooms_occupied: 15,
      rooms_available: 24,
      rooms_blocked: 0,
      rooms_free: 9,
      occupancy_pct: 62.5,
      room_revenue: '5400000.00',
      other_revenue: '430800.00',
      revenue: '5830800.00',
      adr: '360000.00',
      revpar: '225000.00',
      collected: '2111600.00',
      payments: { count: 5, total: '2111600.00', refunds: '0.00', by_method: [] },
    },
    ...overrides,
  }
}

export function makePreview(overrides: Partial<NightAuditPreview> = {}): NightAuditPreview {
  return {
    business_date: BD,
    next_business_date: '2026-10-02',
    calendar_date: '2026-10-02',
    due: true,
    can_run: true,
    reason: null,
    summary: makeAuditSummary(),
    last_report: null,
    ...overrides,
  }
}

export function makeReport(overrides: Partial<NightAuditReport> = {}): NightAuditReport {
  return {
    id: 'report-1',
    business_date: '2026-09-30',
    status: 'completed',
    started_at: '2026-10-01T02:00:00-05:00',
    finished_at: '2026-10-01T02:00:04-05:00',
    triggered_by: null,
    run_id: 'run-1',
    summary: makeAuditSummary({ business_date: '2026-09-30', next_business_date: BD }),
    created_at: '2026-10-01T02:00:00-05:00',
    ...overrides,
  }
}

export const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results })

/** Answers the finance requests of `<FolioPanel reservationId>` with the given folio. */
export function serveFolio(reservationId: string, folio: FolioDetail = makeFolio()) {
  server.use(
    http.get('/api/v1/finance/folios/', ({ request }) => {
      const asked = new URL(request.url).searchParams.get('reservation')
      return HttpResponse.json(page(asked === reservationId ? [summaryOf(folio)] : []))
    }),
    http.get(`/api/v1/finance/folios/${folio.id}/`, () => HttpResponse.json(folio)),
  )
}

export { makeFolio }
