import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api, type Query } from '@/lib/api'
import type { Lang } from '@/lib/format'

// ---- Types: exact shapes of /api/v1/rates/ (see docs/integration-notes/B2a-rates.md) -------------

export interface I18nText {
  es: string
  en: string
}

export type RateSource = 'default' | 'season' | 'manual' | 'revenue' | 'bulk' | 'channel' | 'none'
export type RoomTypeKind = 'private' | 'dorm'
export type PlanKind = 'base' | 'derived'
export type DerivationType = 'percent' | 'amount'
export type MealPlan = 'room_only' | 'breakfast' | 'half_board' | 'full_board' | 'all_inclusive'

export interface GridRow {
  date: string
  /** Two-decimal string rounded to the currency; `null` when no price is configured (`source: "none"`). */
  price: string | null
  extra_adult_price: string
  extra_child_price: string
  min_los: number | null
  max_los: number | null
  cta: boolean
  ctd: boolean
  stop_sell: boolean
  source: RateSource
  available: number | null
}

export interface GridRoomType {
  id: string
  code: string
  name: I18nText
  color: string
  kind: RoomTypeKind
  rows: GridRow[]
}

export interface GridPlan {
  id: string
  code: string
  name: I18nText
  kind: PlanKind
  parent: string | null
  derivation_type: DerivationType
  derivation_value: string
  editable: boolean
}

export interface Holiday {
  date: string
  name: string
}

export interface GridResponse {
  rate_plan: GridPlan | null
  currency: string
  start: string
  /** Exclusive. */
  end: string
  dates: string[]
  holidays: Holiday[]
  room_types: GridRoomType[]
}

export interface BulkSet {
  price?: string
  price_delta_percent?: string
  price_delta_amount?: string
  min_los?: number | null
  max_los?: number | null
  cta?: boolean
  ctd?: boolean
  stop_sell?: boolean
}

export interface BulkPayload {
  room_type_ids: string[]
  rate_plan_id: string
  start: string
  /** Exclusive: the day after the last night that changes. */
  end: string
  /** Monday = 0 … Sunday = 6; empty = every day. */
  weekdays: number[]
  set: BulkSet
  source?: 'manual' | 'bulk'
}

export interface BulkResult {
  updated: number
  audit_event_id: string | null
}

export interface Tax {
  id: string
  code: string
  name: string
  rate: string
  applies_to: 'room' | 'extras' | 'all'
  included_in_price: boolean
  exempt_foreign_non_residents: boolean
  is_active: boolean
}

export type PenaltyType = 'first_night' | 'percent' | 'full'

export interface CancellationPolicy {
  id: string
  name: I18nText
  non_refundable: boolean
  free_until_hours_before: number
  penalty_type: PenaltyType
  penalty_value: string
  description: I18nText
  plans_count: number
}

export interface RatePlan {
  id: string
  code: string
  name: I18nText
  kind: PlanKind
  parent: string | null
  derivation_type: DerivationType
  derivation_value: string
  room_types: string[]
  meal_plan: MealPlan
  cancellation_policy: string | null
  deposit_percent: string
  is_public: boolean
  channels: string[]
  min_los_default: number
  is_active: boolean
  sort_order: number
  children: string[]
}

export type WeekdayKey = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun'
export type WeekdayAdjustments = Partial<Record<WeekdayKey, number>>

export interface RoomTypeDefaults {
  id: string
  room_type: string
  rate_plan: string
  price: string
  dow_adjustments: WeekdayAdjustments
  extra_adult_price: string
  extra_child_price: string
  child_age_limit: number
  single_occupancy_price: string | null
}

export interface SeasonRate {
  id: string
  season: string
  room_type: string
  rate_plan: string
  price: string
  dow_adjustments: WeekdayAdjustments
}

export interface Season {
  id: string
  name: string
  start_date: string
  /** Inclusive (the last night of the season). */
  end_date: string
  priority: number
  color: string
  rates: Omit<SeasonRate, 'season'>[]
}

export type ChargeType = 'per_stay' | 'per_night' | 'per_person' | 'per_person_night'

export interface Extra {
  id: string
  code: string
  name: I18nText
  price: string
  charge_type: ChargeType
  tax: string | null
  sellable_online: boolean
  is_active: boolean
}

export interface PromoCode {
  id: string
  code: string
  discount_type: 'percent' | 'amount'
  value: string
  valid_from: string | null
  valid_to: string | null
  stay_from: string | null
  stay_to: string | null
  rate_plans: string[]
  max_uses: number | null
  uses: number
  is_active: boolean
}

export interface RoomTypeOption {
  id: string
  code: string
  name: I18nText
  kind: RoomTypeKind
  color: string
  base_occupancy: number
  max_adults: number
  max_children: number
  max_occupancy: number
  is_active: boolean
  sort_order: number
}

interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// ---- Query keys -----------------------------------------------------------------------------------

/** What the grid shows: nights `[start, end)`, the plan (default: first base plan) and the language on screen. */
export interface GridParams {
  start: string
  end: string
  planId?: string | null
  /** Holiday names come in this language (the screen switches before the user's profile is saved). */
  lang: Lang
}

export const ratesKeys = {
  all: ['rates'] as const,
  grid: (params: GridParams) => ['rates', 'grid', params] as const,
  list: (resource: Resource, params?: Query) => ['rates', resource, params ?? {}] as const,
  roomTypes: ['rates', 'room-types'] as const,
}

export type Resource =
  | 'taxes'
  | 'cancellation-policies'
  | 'rate-plans'
  | 'room-type-defaults'
  | 'seasons'
  | 'season-rates'
  | 'extras'
  | 'promo-codes'

/** Refetch everything that shows prices (grid) after a configuration change. */
export function invalidatePrices(queryClient: QueryClient) {
  return queryClient.invalidateQueries({ queryKey: ['rates', 'grid'] })
}

// ---- Grid -----------------------------------------------------------------------------------------

export function useRateGrid(params: GridParams) {
  return useQuery({
    queryKey: ratesKeys.grid(params),
    queryFn: ({ signal }) =>
      api.get<GridResponse>('/rates/grid/', {
        params: { start: params.start, end: params.end, rate_plan: params.planId ?? undefined, lang: params.lang },
        signal,
      }),
    placeholderData: (previous) => previous,
  })
}

export function postBulk(payload: BulkPayload) {
  return api.post<BulkResult>('/rates/grid/bulk/', payload)
}

// ---- Staff quote tool (`POST /rates/quote/`, same engine as reservations) ---------------------------

export interface QuoteRequest {
  room_type_id: string
  rate_plan_id: string
  checkin: string
  /** Exclusive. */
  checkout: string
  adults: number
  children: number
  children_ages: number[]
  promo_code: string
  guest_is_foreign_non_resident: boolean
}

export interface QuoteNight {
  date: string
  base: string
  extra_adults: string
  extra_children: string
  discount: string
  total: string
}

export interface QuoteTaxLine {
  code: string
  name: string
  rate: string
  amount: string
  included: boolean
  exempt: boolean
}

export type QuoteViolation =
  | 'invalid_dates'
  | 'stop_sell'
  | 'cta'
  | 'ctd'
  | 'min_los'
  | 'max_los'
  | 'no_rate'
  | 'promo_invalid'

/** `Quote.to_dict()`: money as two-decimal strings rounded to the currency. */
export interface QuoteResult {
  room_type_id: string
  rate_plan_id: string
  checkin: string
  checkout: string
  adults: number
  children: number
  nights: QuoteNight[]
  subtotal: string
  discount_total: string
  taxes: QuoteTaxLine[]
  tax_total: string
  total: string
  currency: string
  restrictions_ok: boolean
  violations: QuoteViolation[]
  promo_applied: string | null
}

export function postQuote(body: QuoteRequest) {
  return api.post<QuoteResult>('/rates/quote/', body)
}

// ---- Configuration resources ----------------------------------------------------------------------

export function useRatesList<T>(resource: Resource, params?: Query) {
  return useQuery({
    queryKey: ratesKeys.list(resource, params),
    queryFn: ({ signal }) =>
      api.get<Page<T>>(`/rates/${resource}/`, { params: { page_size: 200, ...params }, signal }).then((page) => page.results),
  })
}

export function useRoomTypeOptions() {
  return useQuery({
    queryKey: ratesKeys.roomTypes,
    queryFn: ({ signal }) => api.get<RoomTypeOption[]>('/rates/room-types/', { signal }),
    staleTime: 5 * 60_000,
  })
}

/** Create (`POST`) or update (`PATCH` when `id` is given). Refetches the resource and the grid. */
export function useSaveResource<T extends { id: string }>(resource: Resource) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...body }: Partial<T> & { id?: string }) =>
      id ? api.patch<T>(`/rates/${resource}/${id}/`, body) : api.post<T>(`/rates/${resource}/`, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['rates', resource] })
      if (resource === 'seasons' || resource === 'season-rates') {
        await queryClient.invalidateQueries({ queryKey: ['rates', 'seasons'] })
      }
      void invalidatePrices(queryClient)
    },
  })
}

export function useDeleteResource(resource: Resource) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/rates/${resource}/${id}/`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['rates', resource] })
      void invalidatePrices(queryClient)
    },
  })
}

/** Colombian public holidays of a year (`GET /rates/holidays/?year=&lang=`), named in the language on screen. */
export function useHolidays(year: number, lang: Lang) {
  return useQuery({
    queryKey: ['rates', 'holidays', year, lang],
    queryFn: ({ signal }) => api.get<Holiday[]>('/rates/holidays/', { params: { year, lang }, signal }),
    staleTime: Infinity,
  })
}

export interface SeasonRateBody {
  season: string
  room_type: string
  rate_plan: string
  price: string
  dow_adjustments: WeekdayAdjustments
}

/** Upsert of one season price (`POST season-rates/` creates it or updates the existing one). */
export function postSeasonRate(body: SeasonRateBody) {
  return api.post<SeasonRate>('/rates/season-rates/', body)
}

// ---- Undo (generic endpoint of the control center, C12) --------------------------------------------

export const auditKey = (id: string) => ['control', 'audit', id] as const

export function undoAuditEvent(id: string) {
  return api.post<unknown>(`/control/audit/${id}/undo/`, { confirm: true }, { authRedirect: false })
}
