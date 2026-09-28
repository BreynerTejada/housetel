import { useQuery } from '@tanstack/react-query'
import type { GuestInput } from '@/features/guests/api'
import { ratesKeys, type GridResponse, type Holiday, type I18nText } from '@/features/rates/api'
import { api } from '@/lib/api'
import type { Lang } from '@/lib/format'
import type { AssignBody, ModifyBody, Step } from './lib/dnd'

// ---- Types: exact shapes of the bookings API used by the calendar ---------------------------------
// See docs/integration-notes/B2b-bookings.md (`GET calendar/`, stay actions) and B2a-rates.md (grid).

export type { I18nText }

/** Statuses the calendar receives: cancelled and no-show stays never come back from `GET calendar/`. */
export type StayStatus = 'tentative' | 'confirmed' | 'checked_in' | 'checked_out'
export type RoomTypeKind = 'private' | 'dorm'
export type BlockKind = 'out_of_order' | 'out_of_service' | 'maintenance' | 'owner_hold'
export type ReservationSource =
  | 'walk_in'
  | 'phone'
  | 'email'
  | 'front_desk'
  | 'booking_engine'
  | 'marketplace'
  | 'ota'
  | 'api'

export interface CalBed {
  id: string
  label: string
}

export interface CalRoom {
  id: string
  number: string
  floor: string
  housekeeping_status: string
  /** Active beds (dorm rooms only; empty for private rooms). */
  beds: CalBed[]
}

export interface CalRoomType {
  id: string
  code: string
  name: I18nText
  color: string
  kind: RoomTypeKind
  rooms: CalRoom[]
}

export interface CalStay {
  id: string
  reservation_id: string
  code: string
  status: StayStatus
  source: ReservationSource | string
  channel_code: string
  guest_name: string
  /** `null` → the "Unassigned" row of `room_type_id`. In a dorm, `room_id` is the room and `bed_id` the bed. */
  room_id: string | null
  bed_id: string | null
  /** The category that was booked (an upgrade keeps it while `room_id` is in another category). */
  room_type_id: string
  checkin: string
  /** Exclusive: the guest leaves that morning. */
  checkout: string
  adults: number
  children: number
  balance_due: boolean
  is_vip: boolean
}

export interface CalBlock {
  id: string
  room_id: string
  /** `null` = the whole room. */
  bed_id: string | null
  start: string
  /** Exclusive. */
  end: string
  kind: BlockKind | string
  reason: string
}

/** `GET /bookings/calendar/?start&end` (half-open range, at most 93 days). */
export interface CalendarData {
  room_types: CalRoomType[]
  stays: CalStay[]
  blocks: CalBlock[]
  /** Sellable units per category and night (negative = overbooked). */
  availability: Record<string, Record<string, number>>
}

/** `ReservationDetail` (subset the calendar reads). Every stay action answers with it. */
export interface ReservationStay {
  id: string
  status: StayStatus | 'cancelled' | 'no_show'
  checkin_date: string
  checkout_date: string
  nights: number
  adults: number
  children: number
  room_type: { id: string; code: string; name: I18nText; kind: RoomTypeKind; color: string }
  rate_plan: { id: string; code: string; name: I18nText; meal_plan: string }
  room: { id: string; number: string; floor: string; housekeeping_status: string } | null
  bed: { id: string; label: string } | null
  locked_room: boolean
  total_amount: string
}

export interface ReservationDetail {
  id: string
  code: string
  status: StayStatus | 'cancelled' | 'no_show'
  source: string
  channel_code: string
  checkin_date: string
  checkout_date: string
  nights: number
  adults: number
  children: number
  currency: string
  total_amount: string
  balance: string
  hold_expires_at: string | null
  booker: {
    id: string
    full_name: string
    email: string
    phone: string
    is_vip: boolean
    nationality: string
  }
  stays: ReservationStay[]
  eta: string | null
  special_requests: string
  notes: string
  flags: {
    ready_for_checkin: boolean
    arrives_today: boolean
    departs_today: boolean
    in_house: boolean
    unassigned: boolean
    balance_due: boolean
  }
}

/** `POST stays/{id}/modify-preview/`: what a change would do, without saving anything. */
export interface ModifyPreview {
  stay: {
    id: string
    checkin_date: string
    checkout_date: string
    nights: number
    room_type_id: string
    rate_plan_id: string
    room_id: string | null
    bed_id: string | null
    total_amount: string
  }
  /** `true` keeps the room, `false` loses it (left unassigned), `null` had none. */
  room_kept: boolean | null
  current_total: string
  difference: string
  reservation_total: string
  balance: string
}

/** `GET offers/` item (subset). `quote.total` is per unit; `total` = per unit × units needed. */
export interface Offer {
  room_type_id: string
  rate_plan_id: string
  room_type: { id: string; code: string; name: I18nText; kind: RoomTypeKind; max_adults: number; max_children: number }
  rate_plan: {
    id: string
    code: string
    name: I18nText
    meal_plan: string
    deposit_percent: string
    cancellation_policy: { non_refundable: boolean; free_until_hours_before: number } | null
  }
  available_units: number
  units_needed: number
  quote: { nights: { date: string; total: string }[]; subtotal: string; tax_total: string; total: string; currency: string }
  total: string
}

/**
 * `POST reservations/` as the quick-create dialog sends it: an existing guest (`booker_id`) or a new one
 * (`booker`, GuestInput: the API upserts it). A dorm stay for N guests becomes N one-bed stays on the server.
 */
export interface CreateReservationBody {
  booker_id?: string
  booker?: GuestInput
  stays: {
    room_type_id: string
    rate_plan_id: string
    checkin: string
    checkout: string
    adults: number
    children: number
    room_id: string | null
    bed_id: string | null
  }[]
  source: 'front_desk'
  status: 'confirmed'
  notes?: string
}

// ---- Queries ----------------------------------------------------------------------------------------

/** Keys live under `['bookings', …]` so a generic `invalidateQueries({queryKey: ['bookings']})` refreshes the grid. */
export const calendarKeys = {
  all: ['bookings'] as const,
  calendar: ['bookings', 'calendar'] as const,
  range: (start: string, end: string) => ['bookings', 'calendar', start, end] as const,
  reservation: (id: string) => ['bookings', 'reservation', id] as const,
  offers: (params: OffersParams) => ['bookings', 'offers', params] as const,
}

/** The grid for the half-open range `[start, end)`. While another range loads the previous one stays on screen. */
export function useCalendarData(start: string, end: string) {
  return useQuery({
    queryKey: calendarKeys.range(start, end),
    queryFn: ({ signal }) => api.get<CalendarData>('/bookings/calendar/', { params: { start, end }, signal }),
    placeholderData: (previous) => previous,
  })
}

/**
 * Nightly prices of the first base plan for `[start, end)` (`GET /rates/grid/`, needs `rates.view`). Same
 * query key as the rate grid page, so both share the cache and a price edit there refreshes it here.
 */
export function useCalendarPrices(start: string, end: string, lang: Lang, enabled: boolean) {
  const params = { start, end, planId: null, lang }
  return useQuery({
    queryKey: ratesKeys.grid(params),
    queryFn: ({ signal }) => api.get<GridResponse>('/rates/grid/', { params: { start, end, lang }, signal }),
    placeholderData: (previous) => previous,
    enabled,
  })
}

/** Colombian holidays of a year, named in the language on screen (same cache as the rates feature). */
export function useHolidayList(year: number, lang: Lang, enabled: boolean) {
  return useQuery({
    queryKey: ['rates', 'holidays', year, lang],
    queryFn: ({ signal }) => api.get<Holiday[]>('/rates/holidays/', { params: { year, lang }, signal }),
    staleTime: Infinity,
    enabled,
  })
}

export function useReservation(id: string | null) {
  return useQuery({
    queryKey: calendarKeys.reservation(id ?? ''),
    queryFn: ({ signal }) => api.get<ReservationDetail>(`/bookings/reservations/${id}/`, { signal }),
    enabled: Boolean(id),
  })
}

/** What a change of dates or category would do (`POST stays/{id}/modify-preview/`: nothing is saved). */
export function useModifyPreview(stayId: string | null, body: ModifyBody | null) {
  return useQuery({
    queryKey: ['bookings', 'modify-preview', stayId, body],
    queryFn: () => previewModify(stayId as string, body as ModifyBody),
    enabled: Boolean(stayId && body),
    retry: false,
    staleTime: 0,
    gcTime: 0,
  })
}

export interface OffersParams {
  checkin: string
  checkout: string
  adults: number
  children: number
}

/** Sellable offers for the front desk (`channel=direct`: non-public plans included), cheapest first. */
export function useOffers(params: OffersParams | null) {
  return useQuery({
    queryKey: calendarKeys.offers(params ?? { checkin: '', checkout: '', adults: 0, children: 0 }),
    queryFn: ({ signal }) =>
      api.get<Offer[]>('/bookings/offers/', { params: { ...(params as OffersParams), channel: 'direct' }, signal }),
    enabled: Boolean(params && params.checkout > params.checkin && params.adults > 0),
    placeholderData: (previous) => previous,
  })
}

// ---- Commands ---------------------------------------------------------------------------------------

export function runStep(stayId: string, step: Step): Promise<ReservationDetail> {
  switch (step.op) {
    case 'modify':
      return api.post<ReservationDetail>(`/bookings/stays/${stayId}/modify/`, step.body satisfies ModifyBody)
    case 'assign':
      return api.post<ReservationDetail>(`/bookings/stays/${stayId}/assign/`, step.body satisfies AssignBody)
    case 'unassign':
      return api.post<ReservationDetail>(`/bookings/stays/${stayId}/unassign/`)
  }
}

export function previewModify(stayId: string, body: ModifyBody): Promise<ModifyPreview> {
  return api.post<ModifyPreview>(`/bookings/stays/${stayId}/modify-preview/`, body)
}

export function checkIn(stayId: string, force = false): Promise<ReservationDetail> {
  return api.post<ReservationDetail>(`/bookings/stays/${stayId}/check-in/`, { force })
}

export function checkOut(stayId: string, force = false): Promise<ReservationDetail> {
  return api.post<ReservationDetail>(`/bookings/stays/${stayId}/check-out/`, { force })
}

export function createReservation(body: CreateReservationBody): Promise<ReservationDetail> {
  return api.post<ReservationDetail>('/bookings/reservations/', body)
}
