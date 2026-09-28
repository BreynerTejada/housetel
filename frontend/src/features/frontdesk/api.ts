/**
 * Front desk data layer: the Today board and night audit (backend `apps/frontdesk`,
 * docs/integration-notes/C1-frontdesk.md) and the reservations API it drives (backend `apps/bookings`,
 * docs/integration-notes/B2b-bookings.md). Money is always a decimal string ("350000.00").
 */
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { api, type Query } from '@/lib/api'
import type { GuestInput } from '@/features/guests/api'

export type Money = string
export type I18nText = Record<string, string>

export type ReservationStatus = 'tentative' | 'confirmed' | 'checked_in' | 'checked_out' | 'cancelled' | 'no_show'
export type ReservationSource =
  | 'walk_in'
  | 'phone'
  | 'email'
  | 'front_desk'
  | 'booking_engine'
  | 'marketplace'
  | 'ota'
  | 'api'
  | 'import'
export type Guarantee = 'none' | 'card' | 'deposit' | 'ota'
export type HousekeepingStatus = 'clean' | 'dirty' | 'inspected' | 'out_of_service'
export type RoomKind = 'private' | 'dorm'

export const RESERVATION_STATUSES: ReservationStatus[] = [
  'tentative',
  'confirmed',
  'checked_in',
  'checked_out',
  'cancelled',
  'no_show',
]
export const RESERVATION_SOURCES: ReservationSource[] = [
  'front_desk',
  'phone',
  'email',
  'walk_in',
  'booking_engine',
  'marketplace',
  'ota',
  'api',
  'import',
]

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface RoomTypeRef {
  id: string
  code: string
  name: I18nText
  kind: RoomKind
  color: string
}

// ---- Today (GET /frontdesk/today/) --------------------------------------------------------------

export type TodayIssue =
  | 'late_arrival'
  | 'tentative'
  | 'unassigned'
  | 'room_occupied'
  | 'room_not_ready'
  | 'overdue'
  | 'balance_due'

/** The guest still in house in the unit an arrival is assigned to (usually one leaving today). */
export interface UnitOccupant {
  stay_id: string
  reservation_id: string
  code: string
  guest_name: string
  checkout: string
  departing: boolean
}

export interface TodayRow {
  stay_id: string
  reservation_id: string
  code: string
  status: ReservationStatus
  reservation_status: ReservationStatus
  source: ReservationSource
  channel_code: string
  guest_id: string
  guest_name: string
  is_vip: boolean
  room_id: string | null
  room: string | null
  bed_id: string | null
  bed: string | null
  room_status: HousekeepingStatus | null
  room_type: RoomTypeRef
  checkin: string
  checkout: string
  nights: number
  adults: number
  children: number
  eta: string | null
  balance: Money
  balance_due: Money
  online_checkin_done: boolean
  checked_in_at: string | null
  checked_out_at: string | null
  departs_today: boolean
  /** Arrivals only: the guest still in house in its room or bed (issue `room_occupied`). */
  occupied_by: UnitOccupant | null
  done: boolean
  ready: boolean
  issues: TodayIssue[]
}

export interface TodayKpis {
  occupancy_pct: number
  rooms_occupied: number
  rooms_available: number
  rooms_blocked: number
  rooms_free: number
  arrivals_total: number
  arrivals_done: number
  arrivals_late: number
  departures_total: number
  departures_done: number
  departures_overdue: number
  in_house: number
  guests_in_house: number
  room_revenue_today: Money
  other_revenue_today: Money
  revenue_today: Money
  adr_today: Money
  collected_today: Money
}

export interface RackOccupant {
  stay_id: string
  reservation_id: string
  guest_name: string
  checkout: string
  departing: boolean
}

export interface RackArrival {
  stay_id: string
  reservation_id: string
  guest_name: string
  checkin: string
  late: boolean
}

export interface RackBeds {
  total: number
  occupied: number
  departing: number
  arriving: number
  blocked: number
}

/** One key of the rack: an active room tonight. */
export interface RackRoom {
  id: string
  number: string
  floor: string
  room_type: Omit<RoomTypeRef, 'name'>
  housekeeping_status: HousekeepingStatus
  blocked: boolean
  occupant: RackOccupant | null
  arrival: RackArrival | null
  /** Dorms only (the unit is the bed). */
  beds: RackBeds | null
}

export interface NightAuditReportRef {
  id: string
  business_date: string
  status: NightAuditStatus
  finished_at: string | null
}

export interface TodayBoard {
  business_date: string
  calendar_date: string
  currency: string
  kpis: TodayKpis
  arrivals: TodayRow[]
  departures: TodayRow[]
  in_house: TodayRow[]
  rooms: RackRoom[]
  /** Figures of the day before, as its night audit closed them (null without that report). */
  previous: {
    business_date: string
    occupancy_pct: number | null
    rooms_occupied: number | null
    adr: Money | null
    revenue: Money | null
  } | null
  night_audit: { due: boolean; last_report: NightAuditReportRef | null }
}

// ---- Reservations (GET/POST /bookings/reservations/) --------------------------------------------

export interface GuestBrief {
  id: string
  full_name: string
  email: string
  phone: string
  is_vip: boolean
  nationality: string
}

export interface GuestSummaryRef extends Omit<GuestBrief, 'nationality'> {
  first_name: string
  last_name: string
  document_type: string
  document_number: string
  nationality: string
  country_of_residence: string
  language: string
  is_foreign_non_resident: boolean
}

export interface StayBrief {
  id: string
  status: ReservationStatus
  room_type: RoomTypeRef
  room: { id: string; number: string } | null
  bed: { id: string; label: string } | null
}

export interface ReservationListItem {
  id: string
  code: string
  status: ReservationStatus
  source: ReservationSource
  channel_code: string
  external_id: string
  checkin_date: string
  checkout_date: string
  nights: number
  adults: number
  children: number
  currency: string
  total_amount: Money
  balance: Money
  guarantee: Guarantee
  hold_expires_at: string | null
  created_at: string
  booker: GuestBrief
  group: { id: string; name: string } | null
  stays: StayBrief[]
}

export interface NightEntry {
  date: string
  amount: Money
  net?: Money
  tax?: Money
}

export interface StayDetail {
  id: string
  status: ReservationStatus
  checkin_date: string
  checkout_date: string
  nights: number
  adults: number
  children: number
  children_ages: number[]
  room_type: RoomTypeRef
  rate_plan: { id: string; code: string; name: I18nText; meal_plan: string }
  room: { id: string; number: string; floor: string; housekeeping_status: HousekeepingStatus } | null
  bed: { id: string; label: string } | null
  locked_room: boolean
  nightly_rates: NightEntry[]
  total_amount: Money
  checked_in_at: string | null
  checked_out_at: string | null
  occupants: GuestSummaryRef[]
  /** Picked up from this group allotment (pilot P3). */
  group_block_id?: string | null
}

export interface PolicySnapshot {
  id?: string
  name?: I18nText
  description?: I18nText
  non_refundable?: boolean
  free_until_hours_before?: number | null
  penalty_type?: 'first_night' | 'percent' | 'full'
  penalty_value?: string
}

export interface ReservationFlags {
  ready_for_checkin: boolean
  arrives_today: boolean
  departs_today: boolean
  in_house: boolean
  unassigned: boolean
  balance_due: boolean
}

export interface ReservationDetail extends Omit<ReservationListItem, 'booker' | 'stays'> {
  booker: GuestSummaryRef
  stays: StayDetail[]
  language: string
  eta: string | null
  special_requests: string
  notes: string
  promo_code: string
  cancellation_policy_snapshot: PolicySnapshot
  cancelled_at: string | null
  cancellation_reason: string
  cancellation_fee: Money
  custom_values: Record<string, unknown>
  tags: string[]
  external_payload: Record<string, unknown>
  created_by: { id: string; full_name: string; email: string } | null
  updated_at: string
  folio_id: string | null
  portal_url: string
  flags: ReservationFlags
}

export interface RoomOption {
  room_id: string
  room_number: string
  floor: string
  room_type_id: string
  room_type_code: string
  bed_id: string | null
  bed_label: string | null
  housekeeping_status: HousekeepingStatus
  ready: boolean
  same_category: boolean
}

export interface CancelPreview {
  fee: Money
  currency: string
  reason: 'tentative' | 'no_policy' | 'non_refundable' | 'free_window' | 'first_night' | 'percent' | 'full' | string
  free_until: string | null
  non_refundable: boolean
  policy: PolicySnapshot
}

export interface ModifyInput {
  checkin?: string
  checkout?: string
  room_type_id?: string
  rate_plan_id?: string
  adults?: number
  children?: number
  reprice?: boolean
}

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
    adults: number
    children: number
    nightly_rates: NightEntry[]
    total_amount: Money
  }
  /** true keeps the room, false loses it (unassigned), null when the stay had none. */
  room_kept: boolean | null
  current_total: Money
  difference: Money
  reservation_total: Money
  balance: Money
}

export interface OnlineCheckinState {
  reservation_id: string
  status: 'not_started' | 'in_progress' | 'completed' | string | null
  completed_at: string | null
}

// ---- Offers (GET /bookings/offers/) --------------------------------------------------------------

export interface NightPrice {
  date: string
  base: Money
  extra_adults: Money
  extra_children: Money
  discount: Money
  total: Money
}

export interface TaxLine {
  code: string
  name: string
  rate: string
  amount: Money
  included: boolean
  exempt: boolean
}

export interface Quote {
  room_type_id: string
  rate_plan_id: string
  checkin: string
  checkout: string
  adults: number
  children: number
  nights: NightPrice[]
  subtotal: Money
  discount_total: Money
  taxes: TaxLine[]
  tax_total: Money
  total: Money
  currency: string
  restrictions_ok: boolean
  violations: string[]
  promo_applied: string | null
}

export interface Offer {
  room_type_id: string
  rate_plan_id: string
  room_type: RoomTypeRef & { max_adults: number; max_children: number; max_occupancy: number }
  rate_plan: {
    id: string
    code: string
    name: I18nText
    meal_plan: string
    is_public: boolean
    deposit_percent: string
    cancellation_policy: PolicySnapshot | null
  }
  available_units: number
  units_needed: number
  /** Per unit (room or bed). */
  quote: Quote
  /** quote.total × units_needed. */
  total: Money
}

export interface OfferQuery {
  checkin: string
  checkout: string
  adults: number
  children: number
  childrenAges: number[]
  promoCode: string
  foreign: boolean
}

export interface StayRequestInput {
  room_type_id: string
  rate_plan_id: string
  checkin: string
  checkout: string
  adults: number
  children: number
  children_ages: number[]
  room_id?: string | null
  bed_id?: string | null
  locked_room?: boolean
  /** Picked up from a group allotment: takes the block's held units first. */
  group_block_id?: string | null
}

export interface ReservationCreateInput {
  booker?: GuestInput
  booker_id?: string
  stays: StayRequestInput[]
  source: ReservationSource
  notes: string
  special_requests: string
  promo_code: string
  language: string
  eta: string | null
  status: 'confirmed' | 'tentative'
  guarantee: Guarantee
  /** Tentative only: minutes the rooms are held (the backend default is 20). */
  hold_minutes?: number
  /** An existing group of the property… */
  group_id?: string | null
  /** …or a new one created with the reservation (the booker becomes its contact). */
  group_name?: string
  /** Staff pickups from a group allotment skip the rate restrictions. */
  enforce_restrictions?: boolean
}

// ---- Multi-room (pilot P3): offers per room and the quote of several stays ------------------------------

/** An offer per ROOM (`GET /bookings/room-offers/`): one unit quoted at the category's standard occupancy. */
export interface RoomOffer extends Offer {
  room_type: Offer['room_type'] & { base_occupancy: number }
}

export interface RoomOffersQuery {
  checkin: string
  checkout: string
  promoCode: string
  foreign: boolean
  /** A pickup from this allotment: only its category, availability + what it still holds. */
  block?: string | null
}

export interface StayQuoteLine {
  index: number
  room_type_id: string
  rate_plan_id: string
  checkin: string
  checkout: string
  nights: number
  adults: number
  children: number
  /** Units priced: dorm beds count one per guest. */
  units: number
  total: Money
  per_night: Money
  restrictions_ok: boolean
  violations: string[]
}

export interface StaysQuote {
  currency: string
  total: Money
  stays: StayQuoteLine[]
}

export interface StaysQuoteInput {
  stays: StayRequestInput[]
  promo_code: string
  foreign: boolean
}

export interface StayCancelPreview extends CancelPreview {
  stay_total: Money
  /** The last active room of a reservation not in house yet: the whole reservation is cancelled. */
  cancels_reservation: boolean
  /** The other rooms already checked out: the reservation ends as checked out. */
  ends_reservation: boolean
}

// ---- Groups and allotments (pilot P3) --------------------------------------------------------------------

export type GroupState = 'upcoming' | 'in_house' | 'past' | 'empty'
export type GroupWhen = 'upcoming' | 'past' | 'all'

export interface GroupFigures {
  start: string | null
  end: string | null
  reservations: number
  rooms: number
  blocks: number
  blocked_units: number
  picked_rooms: number
  room_nights: number
  picked_room_nights: number
  /** null without allotments. */
  pickup_pct: number | null
  balance: Money
  state: GroupState
}

export interface GroupListItem {
  id: string
  name: string
  notes: string
  contact_guest: GuestBrief | null
  reservations_count: number
  figures: GroupFigures | null
  created_at: string
}

export interface BlockNight {
  date: string
  units: number
  picked: number
  remaining: number
}

export interface BlockPickup {
  nights: BlockNight[]
  room_nights: number
  picked_room_nights: number
  pickup_pct: number
  picked_rooms: number
  remaining_min: number
  released: boolean
}

export interface GroupBlock {
  id: string
  group_id: string
  room_type: RoomTypeRef
  start: string
  end: string
  units: number
  release_date: string
  released_at: string | null
  pickup: BlockPickup
  created_at: string
}

export interface RoomingRow {
  stay_id: string
  reservation_id: string
  code: string
  status: ReservationStatus
  booker_name: string
  room_type: RoomTypeRef
  rate_plan: { id: string; code: string; name: I18nText }
  room: { id: string; number: string; housekeeping_status: HousekeepingStatus } | null
  bed: { id: string; label: string } | null
  checkin: string
  checkout: string
  nights: number
  adults: number
  children: number
  /** The guest sleeping in the room (the stay's first occupant). */
  guest: { id: string; first_name: string; last_name: string; full_name: string } | null
  occupants: number
  group_block_id: string | null
  total_amount: Money
}

export interface GroupDetail extends GroupListItem {
  currency: string
  business_date: string
  blocks: GroupBlock[]
  reservations: ReservationListItem[]
  rooming: RoomingRow[]
}

export interface GroupInput {
  name: string
  notes: string
  contact_guest_id: string | null
}

export interface BlockInput {
  room_type_id: string
  start: string
  end: string
  units: number
  release_date: string
  /** Hold the units even when a night doesn't have them (needs `bookings.overbook`). */
  allow_overbooking?: boolean
}

export interface RoomTypeOption {
  id: string
  code: string
  name: I18nText
  kind: RoomKind
  color: string
  is_active: boolean
  sort_order: number
  base_occupancy: number
  max_adults: number
  max_children: number
  max_occupancy: number
  /** Active rooms (private) or beds (dorm): the most an allotment can hold. */
  units_count: number
}

export interface Extra {
  id: string
  code: string
  name: I18nText
  price: Money
  charge_type: 'per_stay' | 'per_night' | 'per_person' | 'per_person_night'
  tax: string | null
  sellable_online: boolean
  is_active: boolean
}

// ---- Night audit ---------------------------------------------------------------------------------

export type NightAuditStatus = 'running' | 'completed' | 'partial'

export interface AuditNoShow {
  reservation_id: string
  code: string
  guest_name: string
  checkin: string
  fee: Money
}

export interface AuditOverdue {
  stay_id: string
  reservation_id: string
  code: string
  guest_name: string
  room: string | null
  bed: string | null
  checkout: string
}

export interface AuditTentative {
  reservation_id: string
  code: string
  guest_name: string
  checkin: string
  hold_expires_at: string | null
}

export interface AuditError {
  step: 'room_charges' | 'no_show' | string
  reservation_id: string
  code: string
  error_code: string
  error: string
  stay_id?: string
}

export interface DayFigures {
  rooms_occupied: number
  rooms_available: number
  rooms_blocked: number
  rooms_free: number
  occupancy_pct: number
  room_revenue: Money
  other_revenue: Money
  revenue: Money
  adr: Money
  revpar: Money
  collected: Money
  payments: { count: number; total: Money; refunds: Money; by_method: { method: string; count: number; total: Money }[] }
}

export interface NightAuditSummary {
  business_date: string
  next_business_date: string
  auto_no_show: boolean
  room_charges: { stays: number; nights: number; net: Money; tax: Money; total: Money }
  no_shows: AuditNoShow[]
  no_show_fees: Money
  overdue_departures: AuditOverdue[]
  pending_tentative: AuditTentative[]
  errors: AuditError[]
  activity: { arrivals: number; departures: number; in_house: number; cancellations: number; no_shows: number }
  figures: DayFigures
}

export interface NightAuditPreview {
  business_date: string
  next_business_date: string
  calendar_date: string
  due: boolean
  can_run: boolean
  reason: 'audit_ahead' | null
  /** What closing the day would do (null when it cannot run). */
  summary: NightAuditSummary | null
  last_report: NightAuditReportRef | null
}

export interface NightAuditReport {
  id: string
  business_date: string
  status: NightAuditStatus
  started_at: string
  finished_at: string | null
  triggered_by: { id: string; full_name: string; email: string } | null
  run_id: string | null
  summary: NightAuditSummary
  created_at: string
}

// ---- Query keys ----------------------------------------------------------------------------------

export const frontdeskKeys = {
  all: ['frontdesk'] as const,
  today: () => ['frontdesk', 'today'] as const,
  onlineCheckin: (reservationId: string) => ['frontdesk', 'online-checkin', reservationId] as const,
  auditPreview: () => ['frontdesk', 'night-audit', 'preview'] as const,
  auditReports: (page: number) => ['frontdesk', 'night-audit', 'reports', page] as const,
  auditReport: (id: string) => ['frontdesk', 'night-audit', 'report', id] as const,
}

export const bookingKeys = {
  all: ['bookings'] as const,
  reservations: (params: Query) => ['bookings', 'reservations', params] as const,
  reservation: (id: string) => ['bookings', 'reservation', id] as const,
  roomOptions: (stayId: string) => ['bookings', 'room-options', stayId] as const,
  cancelPreview: (id: string) => ['bookings', 'cancel-preview', id] as const,
  modifyPreview: (stayId: string, input: ModifyInput) => ['bookings', 'modify-preview', stayId, input] as const,
  offers: (query: OfferQuery) => ['bookings', 'offers', query] as const,
  roomOffers: (query: RoomOffersQuery) => ['bookings', 'room-offers', query] as const,
  quote: (input: StaysQuoteInput) => ['bookings', 'quote', input] as const,
  stayCancelPreview: (stayId: string) => ['bookings', 'stay-cancel-preview', stayId] as const,
  extras: () => ['bookings', 'extras'] as const,
  groups: (params: Query) => ['bookings', 'groups', params] as const,
  group: (id: string) => ['bookings', 'group', id] as const,
  roomTypes: () => ['bookings', 'room-types'] as const,
}

// ---- Fetchers ------------------------------------------------------------------------------------

export const getToday = () => api.get<TodayBoard>('/frontdesk/today/')

export const getReservations = (params: Query) =>
  api.get<Page<ReservationListItem>>('/bookings/reservations/', { params })

export const getReservation = (id: string) => api.get<ReservationDetail>(`/bookings/reservations/${id}/`)

export const createReservation = (input: ReservationCreateInput) =>
  api.post<ReservationDetail>('/bookings/reservations/', input)

export const updateReservation = (
  id: string,
  patch: Partial<Pick<ReservationDetail, 'notes' | 'special_requests' | 'eta' | 'guarantee' | 'language'>> & { group_id?: string | null },
) => api.patch<ReservationDetail>(`/bookings/reservations/${id}/`, patch)

export const getCancelPreview = (id: string) => api.get<CancelPreview>(`/bookings/reservations/${id}/cancel-preview/`)

export const cancelReservation = (id: string, reason: string, waiveFee: boolean) =>
  api.post<ReservationDetail>(`/bookings/reservations/${id}/cancel/`, { reason, waive_fee: waiveFee, confirm: true })

export const confirmReservation = (id: string) => api.post<ReservationDetail>(`/bookings/reservations/${id}/confirm/`)

export const markNoShow = (id: string) => api.post<ReservationDetail>(`/bookings/reservations/${id}/no-show/`)

export const getRoomOptions = (stayId: string) => api.get<RoomOption[]>(`/bookings/stays/${stayId}/room-options/`)

export const assignRoom = (stayId: string, input: { room_id: string; bed_id?: string | null; force?: boolean }) =>
  api.post<ReservationDetail>(`/bookings/stays/${stayId}/assign/`, input)

export const unassignRoom = (stayId: string) => api.post<ReservationDetail>(`/bookings/stays/${stayId}/unassign/`)

export const checkIn = (stayId: string, force = false) =>
  api.post<ReservationDetail>(`/bookings/stays/${stayId}/check-in/`, { force })

export const checkOut = (stayId: string, force = false) =>
  api.post<ReservationDetail>(`/bookings/stays/${stayId}/check-out/`, { force })

export const previewModify = (stayId: string, input: ModifyInput) =>
  api.post<ModifyPreview>(`/bookings/stays/${stayId}/modify-preview/`, input)

export const modifyStay = (stayId: string, input: ModifyInput) =>
  api.post<ReservationDetail>(`/bookings/stays/${stayId}/modify/`, input)

export const addOccupant = (stayId: string, guest: { guest_id: string } | { guest: GuestInput }) =>
  api.post<ReservationDetail>(`/bookings/stays/${stayId}/occupants/`, guest)

export const removeOccupant = (stayId: string, guestId: string) =>
  api.delete<ReservationDetail>(`/bookings/stays/${stayId}/occupants/`, { params: { guest_id: guestId } })

export const getOffers = (query: OfferQuery) =>
  api.get<Offer[]>('/bookings/offers/', {
    params: {
      checkin: query.checkin,
      checkout: query.checkout,
      adults: query.adults,
      children: query.children,
      children_ages: query.childrenAges.length ? query.childrenAges.join(',') : undefined,
      promo_code: query.promoCode.trim() || undefined,
      foreign: query.foreign ? 1 : undefined,
      channel: 'direct',
    },
  })

export const getExtras = () =>
  api.get<Page<Extra>>('/rates/extras/', { params: { is_active: true, page_size: 200 } })

export const getRoomOffers = (query: RoomOffersQuery) =>
  api.get<RoomOffer[]>('/bookings/room-offers/', {
    params: {
      checkin: query.checkin,
      checkout: query.checkout,
      promo_code: query.promoCode.trim() || undefined,
      foreign: query.foreign ? 1 : undefined,
      block: query.block || undefined,
    },
  })

export const quoteStays = (input: StaysQuoteInput) => api.post<StaysQuote>('/bookings/reservations/quote/', input)

export const addStay = (reservationId: string, input: Partial<StayRequestInput> & Pick<StayRequestInput, 'room_type_id' | 'rate_plan_id' | 'adults'>) =>
  api.post<ReservationDetail>(`/bookings/reservations/${reservationId}/stays/`, input)

export const getStayCancelPreview = (stayId: string) => api.get<StayCancelPreview>(`/bookings/stays/${stayId}/cancel-preview/`)

export const cancelStay = (stayId: string, reason: string, waiveFee: boolean) =>
  api.post<ReservationDetail>(`/bookings/stays/${stayId}/cancel/`, { reason, waive_fee: waiveFee, confirm: true })

export const getGroups = (params: Query) => api.get<Page<GroupListItem>>('/bookings/groups/', { params })

export const getGroup = (id: string) => api.get<GroupDetail>(`/bookings/groups/${id}/`)

export const createGroup = (input: GroupInput) => api.post<GroupListItem>('/bookings/groups/', input)

export const updateGroup = (id: string, input: Partial<GroupInput>) => api.patch<GroupListItem>(`/bookings/groups/${id}/`, input)

export const deleteGroup = (id: string) => api.delete<void>(`/bookings/groups/${id}/`)

export const createBlock = (groupId: string, input: BlockInput) => api.post<GroupBlock>(`/bookings/groups/${groupId}/blocks/`, input)

export const updateBlock = (id: string, input: Partial<Omit<BlockInput, 'room_type_id'>>) =>
  api.patch<GroupBlock>(`/bookings/blocks/${id}/`, input)

export const releaseBlock = (id: string) => api.post<GroupBlock>(`/bookings/blocks/${id}/release/`)

export const deleteBlock = (id: string) => api.delete<void>(`/bookings/blocks/${id}/`)

export const setRoomingName = (stayId: string, name: { first_name: string; last_name: string }) =>
  api.post<RoomingRow>(`/bookings/stays/${stayId}/rooming/`, name)

export const exportRooming = (groupId: string, lang: string) =>
  api.get<Blob>(`/frontdesk/groups/${groupId}/rooming-list/`, { params: { lang }, responseType: 'blob' })

export const getRoomTypes = () => api.get<RoomTypeOption[]>('/inventory/room-types/')

export const getOnlineCheckin = (reservationId: string) =>
  api.get<OnlineCheckinState>(`/frontdesk/reservations/${reservationId}/online-checkin/`)

export const exportReservations = (params: Query, lang: string) =>
  api.get<Blob>('/frontdesk/reservations/export/', { params: { ...params, lang }, responseType: 'blob' })

export const getNightAuditPreview = () => api.get<NightAuditPreview>('/frontdesk/night-audit/preview/')

export const runNightAudit = (businessDate: string) =>
  api.post<NightAuditReport>('/frontdesk/night-audit/run/', { business_date: businessDate })

export const getNightAuditReports = (page: number) =>
  api.get<Page<NightAuditReport>>('/frontdesk/night-audit/reports/', { params: { page, page_size: 30 } })

// ---- Hooks ---------------------------------------------------------------------------------------

/** The Today board; refreshes every minute so the desk sees arrivals checked in from other screens. */
export function useToday(enabled = true) {
  return useQuery({ queryKey: frontdeskKeys.today(), queryFn: getToday, enabled, refetchInterval: 60_000 })
}

export function useReservations(params: Query) {
  return useQuery({
    queryKey: bookingKeys.reservations(params),
    queryFn: () => getReservations(params),
    placeholderData: keepPreviousData,
  })
}

export function useReservation(id: string | undefined) {
  return useQuery({
    queryKey: bookingKeys.reservation(id ?? ''),
    queryFn: () => getReservation(id!),
    enabled: Boolean(id),
  })
}

export function useRoomOptions(stayId: string | null, enabled = true) {
  return useQuery({
    queryKey: bookingKeys.roomOptions(stayId ?? ''),
    queryFn: () => getRoomOptions(stayId!),
    enabled: Boolean(stayId) && enabled,
    staleTime: 0,
  })
}

export function useCancelPreview(reservationId: string, enabled = true) {
  return useQuery({
    queryKey: bookingKeys.cancelPreview(reservationId),
    queryFn: () => getCancelPreview(reservationId),
    enabled,
    staleTime: 0,
  })
}

/** What a date / plan change would do to a stay (nothing is saved). */
export function useModifyPreview(stayId: string, input: ModifyInput, enabled = true) {
  return useQuery({
    queryKey: bookingKeys.modifyPreview(stayId, input),
    queryFn: () => previewModify(stayId, input),
    enabled,
    staleTime: 0,
    retry: false,
  })
}

/** Sellable offers for the wizard's dates and guests (cheapest first). */
export function useOffers(query: OfferQuery, enabled = true) {
  return useQuery({
    queryKey: bookingKeys.offers(query),
    queryFn: () => getOffers(query),
    enabled,
    placeholderData: keepPreviousData,
  })
}

/** Active extras of the property (breakfast, parking, transfers…). */
export function useExtras(enabled = true) {
  return useQuery({ queryKey: bookingKeys.extras(), queryFn: getExtras, enabled, staleTime: 5 * 60_000 })
}

/** Offers per room for the multi-room wizard, the "add room" dialog and allotment pickups. */
export function useRoomOffers(query: RoomOffersQuery, enabled = true) {
  return useQuery({
    queryKey: bookingKeys.roomOffers(query),
    queryFn: () => getRoomOffers(query),
    enabled: enabled && Boolean(query.checkin && query.checkout && query.checkout > query.checkin),
    placeholderData: keepPreviousData,
  })
}

/** Exact prices of the rooms being booked (nothing is held). */
export function useStaysQuote(input: StaysQuoteInput | null, enabled = true) {
  return useQuery({
    queryKey: bookingKeys.quote(input ?? { stays: [], promo_code: '', foreign: false }),
    queryFn: () => quoteStays(input!),
    enabled: enabled && Boolean(input && input.stays.length > 0),
    placeholderData: keepPreviousData,
    retry: false,
  })
}

export function useStayCancelPreview(stayId: string, enabled = true) {
  return useQuery({
    queryKey: bookingKeys.stayCancelPreview(stayId),
    queryFn: () => getStayCancelPreview(stayId),
    enabled,
    staleTime: 0,
  })
}

export function useGroups(params: Query) {
  return useQuery({ queryKey: bookingKeys.groups(params), queryFn: () => getGroups(params), placeholderData: keepPreviousData })
}

export function useGroup(id: string | null | undefined) {
  return useQuery({ queryKey: bookingKeys.group(id ?? ''), queryFn: () => getGroup(id!), enabled: Boolean(id) })
}

/** Categories of the property (for new allotments). */
export function useRoomTypeOptions(enabled = true) {
  return useQuery({ queryKey: bookingKeys.roomTypes(), queryFn: getRoomTypes, enabled, staleTime: 5 * 60_000 })
}

export function useOnlineCheckin(reservationId: string | null, enabled = true) {
  return useQuery({
    queryKey: frontdeskKeys.onlineCheckin(reservationId ?? ''),
    queryFn: () => getOnlineCheckin(reservationId!),
    enabled: Boolean(reservationId) && enabled,
  })
}

/**
 * After any change to a reservation: refresh the board, reservation lists and details, folios and the
 * calendar (C13 keeps its keys under `['bookings', …]` too).
 */
export function useRefreshFrontDesk() {
  const queryClient = useQueryClient()
  return useCallback(async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: frontdeskKeys.all }),
      queryClient.invalidateQueries({ queryKey: bookingKeys.all }),
      queryClient.invalidateQueries({ queryKey: ['finance'] }),
    ])
  }, [queryClient])
}
