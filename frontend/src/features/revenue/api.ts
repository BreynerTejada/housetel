import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { Lang } from '@/lib/format'
import type { I18nText } from './lib/format'

// ---- Types: exact shapes of /api/v1/revenue/ (see docs/integration-notes/C8-revenue.md) -------------

export type RuleKind = 'occupancy' | 'lead_time' | 'day_of_week' | 'holiday' | 'event'
export type Combine = 'stack' | 'max'
export type RecommendationStatus = 'pending' | 'approved' | 'rejected' | 'applied' | 'auto_applied' | 'expired'
export type RunTrigger = 'automation' | 'manual' | 'seed'
export type Weekday = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun'

export interface RoomTypeRef {
  id: string
  code: string
  name: I18nText
  color: string
}

export interface RatePlanRef {
  id: string
  code: string
  name: I18nText
}

export interface UserRef {
  id: string
  full_name: string
  email: string
}

export interface RevenueSettings {
  enabled: boolean
  auto_apply: boolean
  horizon_days: number
  /** Percentages and money are two-decimal strings ("20.00"). */
  max_daily_change_percent: string
  min_change_percent: string
  price_rounding: string
  updated_at: string
}

export type RevenueSettingsInput = Partial<Omit<RevenueSettings, 'updated_at'>>

export interface OccupancyParams {
  tiers: { min: number; max: number; adjust: number }[]
}
export interface LeadTimeParams {
  last_minute: { max_days: number; adjust: number }[]
  early_bird: { min_days: number; adjust: number }[]
}
export type DayOfWeekParams = Partial<Record<Weekday, number>>
export interface HolidayParams {
  adjust: number
  include_bridges: boolean
}
export interface EventParams {
  name: string
  /** Inclusive range of nights. */
  start: string
  end: string
  adjust: number
}

export interface RuleParamsByKind {
  occupancy: OccupancyParams
  lead_time: LeadTimeParams
  day_of_week: DayOfWeekParams
  holiday: HolidayParams
  event: EventParams
}

export interface PricingRule<K extends RuleKind = RuleKind> {
  id: string
  name: string
  kind: K
  /** Empty = every category. */
  room_types: string[]
  params: RuleParamsByKind[K]
  priority: number
  combine: Combine
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface RuleInput {
  name: string
  kind: RuleKind
  room_types: string[]
  params: RuleParamsByKind[RuleKind]
  priority: number
  combine: Combine
  is_active: boolean
}

export interface PriceBounds {
  id: string
  room_type: string
  rate_plan: string
  min_price: string | null
  max_price: string | null
  updated_at: string
}

export interface RuleReason {
  type: 'rule'
  rule_id: string | null
  name: string
  kind: RuleKind
  combine: Combine
  /** Signed percentage ("15.00"). */
  adjust: string
  /** False for a `max` rule that matched but lost to a bigger one. */
  applied: boolean
  detail: {
    occupancy?: string
    lead_days?: number
    window?: 'last_minute' | 'early_bird'
    days?: number
    weekday?: Weekday
    name_es?: string
    name_en?: string
    bridge?: boolean
    name?: string
  }
}

export interface LimitReason {
  type: 'limit'
  /** `rounding`: the commercial rounding to a multiple of `step` (from the price in `from`). */
  kind: 'max_daily_change' | 'min_price' | 'max_price' | 'rounding'
  /** The resulting price; for the daily cap it is the final, rounded price (`rounded: true`). */
  price: string
  percent?: string
  rounded?: boolean
  step?: string
  from?: string
}

export type Reason = RuleReason | LimitReason

export interface Recommendation {
  /** `null` for simulated recommendations (never saved). */
  id: string | null
  room_type: RoomTypeRef
  rate_plan: RatePlanRef
  date: string
  current_price: string
  current_source: string
  anchor_price: string
  anchor_source: string
  recommended_price: string
  change_percent: string
  adjustment_percent: string
  occupancy: string | null
  available_units: number | null
  reasons: Reason[]
  explanation: I18nText
  status: RecommendationStatus
  decided_by: UserRef | null
  decided_at: string | null
  applied_at: string | null
  apply_error: string
  run: string | null
  created_at: string
}

export interface CalendarCell {
  id: string
  status: RecommendationStatus
  change_percent: string
  current_price: string
  recommended_price: string
  occupancy: string | null
}

export interface CalendarRow {
  room_type: RoomTypeRef
  rate_plan: RatePlanRef
  /** Only nights with a recommendation (pending, else the latest decided one). */
  cells: Record<string, CalendarCell>
}

export interface Holiday {
  date: string
  name: string
}

export interface CalendarResponse {
  start: string
  /** Exclusive. */
  end: string
  business_date: string
  currency: string
  dates: string[]
  holidays: Holiday[]
  rows: CalendarRow[]
}

/** The AI summary of a run: written in the background after the run ("pending"), then "done" or "unavailable". */
export type AiStatus = 'pending' | 'done' | 'unavailable' | 'skipped'

export interface RunDetails {
  ai_status?: AiStatus
  count?: number
  up?: number
  down?: number
  avg_change_percent?: string
  estimated_impact?: string
  impact_up?: string
  impact_down?: string
  auto_applied?: number
  expired?: number
  rules?: { name: string; count: number }[]
  top?: { date: string; room_type: string; change_percent: string; current_price: string; recommended_price: string; reasons: string[] }[]
}

export interface RevenueRun {
  id: string
  started_at: string
  finished_at: string | null
  status: 'running' | 'success' | 'failed'
  trigger: RunTrigger
  triggered_by: UserRef | null
  start_date: string | null
  end_date: string | null
  recommendations_count: number
  auto_applied_count: number
  expired_count: number
  summary: I18nText
  /** Written by the LLM when `ai_provider` is set; otherwise the deterministic summary. */
  ai_summary: I18nText
  ai_provider: string
  details: RunDetails
}

export interface RevenueSummary {
  pending: number
  up: number
  down: number
  avg_change_percent: string
  estimated_impact: string
  impact_up: string
  impact_down: string
  first_date: string | null
  currency: string
  enabled: boolean
  auto_apply: boolean
  last_run: RevenueRun | null
}

export interface RevenueOptions {
  currency: string
  business_date: string
  room_types: (RoomTypeRef & { kind: 'private' | 'dorm' })[]
  rate_plans: (RatePlanRef & { room_types: string[]; default_prices: Record<string, string | null> })[]
}

export type Decision = 'approve' | 'reject' | 'apply'

export interface DecisionResult {
  updated: number
  skipped: { id: string; reason: 'not_found' | 'not_pending' | 'expired' }[]
  errors: { id: string; code: string; detail: string }[]
  recommendations: Recommendation[]
}

/** `POST recommendations/{id}/explain/`: the LLM's words, or the deterministic explanation when it is not available. */
export interface AiExplanation {
  id: string
  text: I18nText
  /** "gemini" | "claude" | "" (empty when the AI did not answer). */
  provider: string
  simulated: boolean
}

export interface SimulateResult {
  start: string
  end: string
  summary: {
    count: number
    up: number
    down: number
    avg_change_percent: string
    estimated_impact: string
    impact_up: string
    impact_down: string
  }
  recommendations: Recommendation[]
}

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// ---- Queries ------------------------------------------------------------------------------------------

export const revenueKeys = {
  all: ['revenue'] as const,
  settings: () => ['revenue', 'settings'] as const,
  summary: () => ['revenue', 'summary'] as const,
  calendar: (params: { start: string; end: string; lang: Lang }) => ['revenue', 'calendar', params] as const,
  recommendation: (id: string) => ['revenue', 'recommendation', id] as const,
  upcoming: (start: string) => ['revenue', 'upcoming', start] as const,
  rules: () => ['revenue', 'rules'] as const,
  bounds: () => ['revenue', 'bounds'] as const,
  options: () => ['revenue', 'options'] as const,
  runs: (page: number) => ['revenue', 'runs', page] as const,
}

export function useRevenueSettings() {
  return useQuery({ queryKey: revenueKeys.settings(), queryFn: () => api.get<RevenueSettings>('/revenue/settings/') })
}

/** How long the page keeps asking for an AI summary that is being written (the LLM answers in seconds). */
const AI_WAIT_MS = 90_000
const AI_POLL_MS = 2_500

/** The run's AI summary is still being written (and the run is recent enough to keep waiting for it). */
export function aiPending(run: RevenueRun | null | undefined): boolean {
  if (!run || run.details?.ai_status !== 'pending') return false
  const finished = Date.parse(run.finished_at ?? run.started_at)
  return Number.isFinite(finished) && Date.now() - finished < AI_WAIT_MS
}

export function useRevenueSummary() {
  return useQuery({
    queryKey: revenueKeys.summary(),
    queryFn: () => api.get<RevenueSummary>('/revenue/recommendations/summary/'),
    refetchInterval: (query) => (aiPending(query.state.data?.last_run) ? AI_POLL_MS : false),
  })
}

export function useRevenueCalendar(params: { start: string; end: string; lang: Lang }) {
  return useQuery({
    queryKey: revenueKeys.calendar(params),
    queryFn: () => api.get<CalendarResponse>('/revenue/recommendations/calendar/', { params }),
    placeholderData: (previous) => previous,
  })
}

export function useRecommendation(id: string | null) {
  return useQuery({
    queryKey: revenueKeys.recommendation(id ?? ''),
    queryFn: () => api.get<Recommendation>(`/revenue/recommendations/${id}/`),
    enabled: Boolean(id),
  })
}

/** The next pending recommendations from `start` (the business date), soonest first. */
export function useUpcomingRecommendations(start: string, pageSize = 4) {
  return useQuery({
    queryKey: revenueKeys.upcoming(start),
    queryFn: () =>
      api.get<Page<Recommendation>>('/revenue/recommendations/', {
        params: { status: 'pending', start, page_size: pageSize, ordering: 'date' },
      }),
    // without the business date the list would bring pending nights already in the past
    enabled: Boolean(start),
  })
}

export function useRules() {
  return useQuery({ queryKey: revenueKeys.rules(), queryFn: () => api.get<PricingRule[]>('/revenue/rules/') })
}

export function useBounds() {
  return useQuery({ queryKey: revenueKeys.bounds(), queryFn: () => api.get<PriceBounds[]>('/revenue/bounds/') })
}

export function useRevenueOptions() {
  return useQuery({ queryKey: revenueKeys.options(), queryFn: () => api.get<RevenueOptions>('/revenue/options/') })
}

export function useRuns(page: number) {
  return useQuery({
    queryKey: revenueKeys.runs(page),
    queryFn: () => api.get<Page<RevenueRun>>('/revenue/runs/', { params: { page } }),
    placeholderData: (previous) => previous,
    refetchInterval: (query) => (query.state.data?.results.some(aiPending) ? AI_POLL_MS : false),
  })
}

// ---- Mutations ----------------------------------------------------------------------------------------

/**
 * Everything revenue shows, plus the rate grids: approving or auto-applying writes nightly prices
 * (`source="revenue"`), so the grid of `/app/rates` must not keep the old ones.
 */
export function invalidateRevenue(queryClient: QueryClient) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: revenueKeys.all }),
    queryClient.invalidateQueries({ queryKey: ['rates', 'grid'] }),
  ])
}

export function useDecision() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ decision, ids }: { decision: Decision; ids: string[] }) =>
      api.post<DecisionResult>(`/revenue/recommendations/${decision}/`, { ids }),
    onSettled: () => invalidateRevenue(queryClient),
  })
}

export function useRunNow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<RevenueRun>('/revenue/run-now/', {}),
    onSettled: () => invalidateRevenue(queryClient),
  })
}

/** Plain-language explanation of one recommendation, written by the AI on demand (cached by the server). */
export function useExplain() {
  return useMutation({
    mutationFn: (id: string) => api.post<AiExplanation>(`/revenue/recommendations/${id}/explain/`, {}),
  })
}

export function useSimulate() {
  return useMutation({
    mutationFn: (body: { rule?: RuleInput & { id?: string } }) => api.post<SimulateResult>('/revenue/simulate/', body),
  })
}

export function useSaveSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: RevenueSettingsInput) => api.patch<RevenueSettings>('/revenue/settings/', body),
    onSuccess: (settings) => {
      queryClient.setQueryData(revenueKeys.settings(), settings)
      void queryClient.invalidateQueries({ queryKey: revenueKeys.summary() })
    },
  })
}

export function useSaveRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id?: string; body: Partial<RuleInput> }) =>
      id ? api.patch<PricingRule>(`/revenue/rules/${id}/`, body) : api.post<PricingRule>('/revenue/rules/', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: revenueKeys.rules() }),
  })
}

export function useDeleteRule() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/revenue/rules/${id}/`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: revenueKeys.rules() }),
  })
}

export function useSaveBounds() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: { room_type: string; rate_plan: string; min_price: string | null; max_price: string | null }) =>
      api.post<PriceBounds>('/revenue/bounds/', body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: revenueKeys.bounds() }),
  })
}

export function useDeleteBounds() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete(`/revenue/bounds/${id}/`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: revenueKeys.bounds() }),
  })
}
