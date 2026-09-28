/**
 * Channel manager API client (backend `apps/distribution`, docs/integration-notes/C3-distribution.md).
 * Staff endpoints under `/api/v1/distribution/`: `distribution.view` to read, `distribution.manage` to change.
 * Money is a decimal string ("352000.00"); dates are `YYYY-MM-DD`; ranges are `[start, end)`.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export type I18nText = Record<string, string> | string
export type ChannelCode = 'booksim' | 'airsim' | 'ical' | 'channex'
export type ConnectionStatus = 'active' | 'paused' | 'error'
export type Delivery = 'push' | 'pull' | 'ical'
export type IntegrationMode = 'real' | 'simulated'
export type LogDirection = 'in' | 'out'
export type LogStatus = 'success' | 'warning' | 'error' | 'skipped'
export type AriStatus = 'pending' | 'sending' | 'sent' | 'failed'
export type AriKind = 'availability' | 'rates' | 'restrictions'
export type SimBookingStatus = 'new' | 'modified' | 'cancelled'
export type SimPmsStatus = 'pending' | 'imported' | 'failed'

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface RoomMapping {
  id: string
  room_type: string
  room_type_code: string
  room_type_name: I18nText
  room: string | null
  room_number: string | null
  external_room_id: string
  ical_import_url: string
  /** Secret public URL listing sites import (iCal connections only). */
  ical_export_url: string | null
  ical_last_sync_at: string | null
  ical_last_error: string
}

export interface RateMapping {
  id: string
  /** null when the plan was deleted: the channel receives the rate closed. */
  rate_plan: string | null
  rate_plan_code: string | null
  rate_plan_name: I18nText | null
  /** Set when the channel rate belongs to one room (Channex). */
  room_type: string | null
  room_type_code: string | null
  external_rate_id: string
  markup_percent: string
}

export interface ConnectionStats {
  pending_updates: number
  failed_updates: number
  reservations: number
  errors_24h: number
  in_errors_24h: number
  last_out_at: string | null
  last_in_at: string | null
}

export interface IntegrationInfo {
  kind: 'channel_ical' | 'channel_channex'
  mode: IntegrationMode
  enabled: boolean
  config: Record<string, string>
  /** Names of the secrets already stored (never their values). */
  secrets: string[]
}

export interface Connection {
  id: string
  channel_code: ChannelCode
  channel_label: string
  name: string
  status: ConnectionStatus
  mode: IntegrationMode
  delivery: Delivery
  /** Served by the OTA simulator (BookSim, AirSim, Channex in simulated mode). */
  simulated: boolean
  settings: { import_all_events?: boolean }
  last_sync_at: string | null
  last_error: string
  created_at: string
  updated_at: string
  room_mappings: RoomMapping[]
  rate_mappings: RateMapping[]
  stats: ConnectionStats
  integration: IntegrationInfo | null
}

export interface ConfigField {
  name: string
  label_es: string
  label_en: string
  type: 'text' | 'password' | 'url' | 'select' | 'boolean' | 'number'
  secret: boolean
  required: boolean
  options?: { value: string; label_es: string; label_en: string }[]
  help_es?: string
  help_en?: string
}

export interface ChannelOption {
  code: ChannelCode
  label: string
  delivery: Delivery
  pushes_ari: boolean
  modes: IntegrationMode[]
  /** iCal: one connection per listing site. */
  multiple: boolean
  connected: boolean
  integration: 'channel_ical' | 'channel_channex' | null
}

export interface RoomTypeOption {
  id: string
  code: string
  name: I18nText
  kind: 'private' | 'dorm'
  color: string
  is_active: boolean
  rooms: { id: string; number: string }[]
}

export interface RatePlanOption {
  id: string
  code: string
  name: I18nText
  kind: 'base' | 'derived'
  room_types: string[]
  is_public: boolean
  is_active: boolean
  channels: string[]
  /** The plan's price tonight in its first category (to preview the channel price); null without a price. */
  sample?: { room_type: string; date: string; price: string } | null
  /** The plan's price tonight in every active category that has one. */
  samples?: { room_type: string; room_type_code: string; date: string; price: string }[]
}

export interface ChannelOptions {
  channels: ChannelOption[]
  room_types: RoomTypeOption[]
  rate_plans: RatePlanOption[]
  integrations: Record<'channel_ical' | 'channel_channex', IntegrationInfo & { fields: ConfigField[] }>
  currency: string
  business_date: string
}

export interface ChannelCatalog {
  rooms: { id: string; title: string }[]
  rates: { id: string; title: string; room_id: string | null; currency: string }[]
}

export interface RoomMappingInput {
  id?: string
  room_type: string
  room?: string | null
  external_room_id?: string
  ical_import_url?: string
}

export interface RateMappingInput {
  id?: string
  rate_plan: string
  room_type?: string | null
  external_rate_id: string
  markup_percent: string
}

export interface ConnectionInput {
  channel_code?: ChannelCode
  name?: string
  settings?: { import_all_events?: boolean }
  room_mappings?: RoomMappingInput[]
  rate_mappings?: RateMappingInput[]
  mode?: IntegrationMode
  integration?: { config?: Record<string, string>; secrets?: Record<string, string> }
  full_sync?: boolean
}

export interface SyncSummary {
  sent: number
  retrying: number
  failed: number
  connections: number
}

/** Create/update response: the connection plus the full sync it ran (null when the changes were only queued). */
export type ConnectionWriteResult = Connection & { sync: SyncSummary | null }

export interface PullSummary {
  created?: number
  modified?: number
  cancelled?: number
  unchanged?: number
  failed?: number
  skipped?: number
  acknowledged?: number
  errors?: number
  calendars?: number
}

export interface ConnectionRef {
  id: string
  name: string
  channel_code: ChannelCode
}

export interface SyncLogEntry {
  id: string
  connection: ConnectionRef
  direction: LogDirection
  kind: string
  status: LogStatus
  message: string
  payload: Record<string, unknown>
  external_id: string
  reservation: { id: string; code: string; status: string } | null
  created_at: string
}

export interface AriUpdate {
  id: string
  connection: ConnectionRef
  room_type: { id: string; code: string; name: I18nText }
  start: string
  end: string
  kinds: AriKind[]
  status: AriStatus
  attempts: number
  next_attempt_at: string | null
  last_error: string
  sent_at: string | null
  created_at: string
  updated_at: string
}

export interface OtaCell {
  date: string
  available: number
  price: string | null
  min_los: number | null
  max_los: number | null
  closed_to_arrival: boolean
  closed_to_departure: boolean
  stop_sell: boolean
}

export interface OtaRate {
  external_rate_id: string
  rate_plan: { id: string; code: string; name: I18nText } | null
  markup_percent: string
  /** One per date of the grid; null = the OTA never received that night. */
  cells: (OtaCell | null)[]
}

export interface OtaRoom {
  external_room_id: string
  room_type: { id: string; code: string; name: I18nText; kind: 'private' | 'dorm'; color: string }
  rates: OtaRate[]
}

export interface OtaInventory {
  connection: { id: string; name: string; channel_code: ChannelCode; ota: string; delivery: 'push' | 'pull' }
  start: string
  end: string
  currency: string
  dates: string[]
  rooms: OtaRoom[]
  last_update: string | null
}

export interface OtaGuest {
  first_name?: string
  last_name?: string
  email?: string
  phone?: string
  country?: string
  language?: string
}

export interface OtaBookingRoom {
  external_room_id: string
  external_rate_id: string
  checkin: string
  checkout: string
  adults: number
  children: number
  nightly_rates: { date: string; amount: string }[] | null
}

export interface OtaBooking {
  id: string
  external_id: string
  status: SimBookingStatus
  revision: number
  pms_status: SimPmsStatus
  pms_message: string
  payload: {
    ota: string
    guest: OtaGuest
    rooms: OtaBookingRoom[]
    currency: string
    total: string | null
    notes: string
    forced: boolean
  }
  reservation: { id: string; code: string; status: string } | null
  created_at: string
  updated_at: string
}

export interface OtaBookingInput {
  external_room_id: string
  external_rate_id: string
  checkin: string
  checkout: string
  adults: number
  children: number
  guest?: OtaGuest
  notes?: string
  force?: boolean
}

export type OtaBookingChange = Partial<Omit<OtaBookingInput, 'guest' | 'notes'>>

// ---- Query keys -------------------------------------------------------------------------------------------

export interface LogFilters {
  connection?: string
  direction?: LogDirection | ''
  status?: LogStatus | ''
  q?: string
  page?: number
}

export const channelKeys = {
  all: ['channels'] as const,
  connections: () => ['channels', 'connections'] as const,
  options: () => ['channels', 'options'] as const,
  catalog: (channel: ChannelCode) => ['channels', 'catalog', channel] as const,
  logs: (filters: LogFilters) => ['channels', 'logs', filters] as const,
  queue: (filters: { connection?: string; status?: AriStatus | ''; page?: number }) =>
    ['channels', 'queue', filters] as const,
  simInventory: (connectionId: string, start: string, end: string) =>
    ['channels', 'sim', connectionId, 'inventory', start, end] as const,
  simBookings: (connectionId: string, page: number) => ['channels', 'sim', connectionId, 'bookings', page] as const,
}

// ---- Fetchers ---------------------------------------------------------------------------------------------

const BASE = '/distribution'

export const getConnections = () => api.get<Connection[]>(`${BASE}/connections/`)
export const getOptions = () => api.get<ChannelOptions>(`${BASE}/options/`)
export const getCatalog = (channel: ChannelCode) =>
  api.get<ChannelCatalog>(`${BASE}/options/catalog/`, { params: { channel } })

export const createConnection = (input: ConnectionInput) => api.post<ConnectionWriteResult>(`${BASE}/connections/`, input)
export const updateConnection = (id: string, input: ConnectionInput) =>
  api.patch<ConnectionWriteResult>(`${BASE}/connections/${id}/`, input)
export const deleteConnection = (id: string) => api.delete(`${BASE}/connections/${id}/`)
export const testConnection = (id: string) =>
  api.post<{ ok: boolean; message: string }>(`${BASE}/connections/${id}/test/`)
export const fullSync = (id: string) => api.post<SyncSummary>(`${BASE}/connections/${id}/full-sync/`)
export const pauseConnection = (id: string) => api.post<Connection>(`${BASE}/connections/${id}/pause/`)
export const resumeConnection = (id: string) =>
  api.post<{ connection: Connection; sync: SyncSummary | null }>(`${BASE}/connections/${id}/resume/`)
export const pullConnection = (id: string) => api.post<PullSummary>(`${BASE}/connections/${id}/pull/`)

export const getLogs = ({ page = 1, ...filters }: LogFilters) =>
  api.get<Page<SyncLogEntry>>(`${BASE}/logs/`, { params: { ...filters, page, page_size: 25 } })

export const getQueue = ({ page = 1, ...filters }: { connection?: string; status?: AriStatus | ''; page?: number }) =>
  api.get<Page<AriUpdate>>(`${BASE}/queue/`, { params: { ...filters, page, page_size: 25 } })
export const retryQueue = (connection?: string) =>
  api.post<SyncSummary & { retried: number }>(`${BASE}/queue/retry/`, connection ? { connection } : {})

export const getSimInventory = (connectionId: string, start: string, end: string) =>
  api.get<OtaInventory>(`${BASE}/simulator/${connectionId}/inventory/`, { params: { start, end } })
export const getSimBookings = (connectionId: string, page: number) =>
  api.get<Page<OtaBooking>>(`${BASE}/simulator/${connectionId}/bookings/`, { params: { page, page_size: 20 } })
export const createSimBooking = (connectionId: string, input: OtaBookingInput) =>
  api.post<OtaBooking>(`${BASE}/simulator/${connectionId}/bookings/`, input)
export const modifySimBooking = (connectionId: string, externalId: string, change: OtaBookingChange) =>
  api.post<OtaBooking>(`${BASE}/simulator/${connectionId}/bookings/${encodeURIComponent(externalId)}/modify/`, change)
export const cancelSimBooking = (connectionId: string, externalId: string) =>
  api.post<OtaBooking>(`${BASE}/simulator/${connectionId}/bookings/${encodeURIComponent(externalId)}/cancel/`)
export const deliverSimBooking = (connectionId: string, externalId: string) =>
  api.post<OtaBooking>(`${BASE}/simulator/${connectionId}/bookings/${encodeURIComponent(externalId)}/deliver/`)

// ---- Hooks ------------------------------------------------------------------------------------------------

/** Connections of the active property; `refetchInterval` keeps queue and sync states live on screen. */
export function useConnections({ refetchInterval }: { refetchInterval?: number } = {}) {
  return useQuery({ queryKey: channelKeys.connections(), queryFn: getConnections, refetchInterval })
}

export function useChannelOptions() {
  return useQuery({ queryKey: channelKeys.options(), queryFn: getOptions })
}

export function useSyncLogs(filters: LogFilters, { refetchInterval }: { refetchInterval?: number } = {}) {
  return useQuery({
    queryKey: channelKeys.logs(filters),
    queryFn: () => getLogs(filters),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useAriQueue(
  filters: { connection?: string; status?: AriStatus | ''; page?: number },
  { refetchInterval }: { refetchInterval?: number } = {},
) {
  return useQuery({
    queryKey: channelKeys.queue(filters),
    queryFn: () => getQueue(filters),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useSimInventory(
  connectionId: string | undefined,
  start: string,
  end: string,
  { refetchInterval, enabled = true }: { refetchInterval?: number; enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: channelKeys.simInventory(connectionId ?? '', start, end),
    queryFn: () => getSimInventory(connectionId as string, start, end),
    enabled: Boolean(connectionId) && enabled && start < end,
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

export function useChannelCatalog(channel: ChannelCode, enabled: boolean) {
  return useQuery({ queryKey: channelKeys.catalog(channel), queryFn: () => getCatalog(channel), enabled, retry: false })
}

export function useSimBookings(connectionId: string | undefined, page: number, { refetchInterval }: { refetchInterval?: number } = {}) {
  return useQuery({
    queryKey: channelKeys.simBookings(connectionId ?? '', page),
    queryFn: () => getSimBookings(connectionId as string, page),
    enabled: Boolean(connectionId),
    placeholderData: keepPreviousData,
    refetchInterval,
  })
}

/** A mutation that refreshes everything of the feature afterwards (cards, log, queue, simulator). */
export function useChannelsMutation<TVariables, TResult>(
  mutationFn: (variables: TVariables) => Promise<TResult>,
  { onSuccess }: { onSuccess?: (result: TResult, variables: TVariables) => void } = {},
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: async (result, variables) => {
      await queryClient.invalidateQueries({ queryKey: channelKeys.all })
      onSuccess?.(result, variables)
    },
  })
}
