/**
 * Housekeeping API client (backend `apps/housekeeping`, docs/integration-notes/C2-housekeeping.md).
 *
 * Other features may import the types, `hkKeys` and the read hooks (`useHkSummary` for the Today panel…).
 * Every write invalidates `hkKeys.all`: tasks, board, summary and tickets move together.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export type I18nText = Record<string, string>
export type HousekeepingStatus = 'clean' | 'dirty' | 'inspected' | 'out_of_service'
export type TaskKind = 'departure_clean' | 'stayover' | 'deep_clean' | 'inspection' | 'turndown' | 'custom'
export type TaskStatus = 'pending' | 'in_progress' | 'done' | 'inspected' | 'cancelled'
export type Priority = 'low' | 'normal' | 'high' | 'urgent'
export type TicketStatus = 'open' | 'in_progress' | 'resolved' | 'cancelled'

export const TASK_KINDS: TaskKind[] = ['departure_clean', 'stayover', 'deep_clean', 'inspection', 'turndown', 'custom']
export const PRIORITIES: Priority[] = ['low', 'normal', 'high', 'urgent']
export const ROOM_STATUSES: HousekeepingStatus[] = ['clean', 'dirty', 'inspected', 'out_of_service']
/** Finishing one of these leaves the room clean. */
export const CLEANING_KINDS: TaskKind[] = ['departure_clean', 'stayover', 'deep_clean']

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface UserRef {
  id: string
  full_name: string
  email: string
}

export interface RoomTypeRef {
  id: string
  code: string
  name: I18nText
  color: string
  kind: string
}

export interface RoomRef {
  id: string
  number: string
  name: string
  floor: string
  housekeeping_status: HousekeepingStatus | string
  room_type: RoomTypeRef
}

export interface Arrival {
  code: string
  /** `HH:MM` or null. */
  eta: string | null
  is_vip: boolean
}

export interface InHouse {
  code: string
  checkout_date: string
  departs_today: boolean
  guests: number
  is_vip: boolean
}

export interface HkTask {
  id: string
  room: RoomRef
  bed: { id: string; label: string } | null
  kind: TaskKind
  status: TaskStatus
  priority: Priority
  business_date: string
  assigned_to: UserRef | null
  estimated_minutes: number
  started_at: string | null
  finished_at: string | null
  finished_by: UserRef | null
  notes: string
  reservation: { id: string; code: string } | null
  created_source: string
  /** A departure clean whose guest is still in the room: it cannot start yet. */
  waiting_for_checkout: boolean
  arrival_today: Arrival | null
  /** Still open from an earlier business date. */
  overdue: boolean
  created_at: string
  updated_at: string
}

export interface BlockRef {
  id: string
  kind: string
  reason: string
  start_date: string
  /** Exclusive. */
  end_date: string
}

export interface BoardRoom extends RoomRef {
  occupied: boolean
  in_house: InHouse | null
  arrival_today: Arrival | null
  tasks: HkTask[]
  active_block: BlockRef | null
  open_tickets: number
}

export interface HkSettings {
  /** 1 = daily, 2 = every other day…, 0 = no stayover service. */
  stayover_frequency_days: number
  require_inspection: boolean
  auto_assign: boolean
  minutes_per_shift: number
}

export interface HkSummary {
  business_date: string
  rooms: { total: number; clean: number; dirty: number; inspected: number; out_of_service: number; occupied: number }
  tasks: { total: number; pending: number; in_progress: number; done: number; inspections_pending: number; unassigned: number }
  minutes: { total: number; done: number }
  tickets: { open: number; blocking: number }
}

export interface Housekeeper extends UserRef {
  minutes: number
  minutes_done: number
  tasks: number
  tasks_done: number
}

export interface Technician extends UserRef {
  open_tickets: number
}

export interface StaffResponse {
  housekeepers: Housekeeper[]
  maintenance: Technician[]
}

export interface HousekeepingBoard {
  business_date: string
  settings: HkSettings
  summary: HkSummary
  staff: Housekeeper[]
  floors: { floor: string; rooms: BoardRoom[] }[]
}

export interface TicketPhoto {
  id: string
  content_type: string
  size: number
  /** Private: read it with `fetchPhoto` (session + X-Property-Id), never as a plain `<img src>`. */
  file_url: string
  uploaded_by: UserRef | null
  created_at: string
}

export interface MaintenanceTicket {
  id: string
  room: RoomRef | null
  location: string
  title: string
  description: string
  priority: Priority
  status: TicketStatus
  blocks_room: boolean
  /** Exclusive end of the block. */
  blocked_until: string | null
  block: { id: string; start_date: string; end_date: string; released_at: string | null } | null
  reported_by: UserRef | null
  assigned_to: UserRef | null
  started_at: string | null
  resolved_at: string | null
  resolved_by: UserRef | null
  resolution_notes: string
  photos: TicketPhoto[]
  created_at: string
  updated_at: string
}

export interface AutoAssignReport {
  business_date: string
  assigned: number
  unassigned: number
  staff: { user_id: string; full_name: string; minutes: number; tasks: number }[]
  overloaded: string[]
  minutes_per_shift: number
}

export interface GenerateReport {
  created: number
  stayovers: number
  departures: number
  dirty_rooms: number
  rooms_marked_dirty: number
}

export interface TicketInput {
  room_id?: string | null
  location?: string
  title: string
  description?: string
  priority?: Priority
  blocks_room?: boolean
  blocked_until?: string | null
  assigned_to_id?: string | null
  force?: boolean
  photos?: File[]
}

export interface TicketFilters {
  status?: TicketStatus[]
  blocking?: boolean
  mine?: boolean
  q?: string
  room?: string
}

const BASE = '/housekeeping'

export const hkKeys = {
  all: ['housekeeping'] as const,
  myTasks: () => [...hkKeys.all, 'tasks', 'mine'] as const,
  board: () => [...hkKeys.all, 'board'] as const,
  summary: () => [...hkKeys.all, 'summary'] as const,
  staff: () => [...hkKeys.all, 'staff'] as const,
  settings: () => [...hkKeys.all, 'settings'] as const,
  tickets: (filters: TicketFilters = {}) => [...hkKeys.all, 'tickets', filters] as const,
}

// ---- Reads ------------------------------------------------------------------------------------------------

export function getMyTasks(signal?: AbortSignal) {
  return api.get<Page<HkTask>>(`${BASE}/tasks/`, { params: { mine: 1, page_size: 200 }, signal })
}

/** Tasks assigned to whoever is signed in, for the business date (plus what is still open). */
export function useMyTasks() {
  return useQuery({
    queryKey: hkKeys.myTasks(),
    queryFn: ({ signal }) => getMyTasks(signal),
    select: (data) => data.results,
    refetchInterval: 60_000,
  })
}

export function useBoard() {
  return useQuery({
    queryKey: hkKeys.board(),
    queryFn: ({ signal }) => api.get<HousekeepingBoard>(`${BASE}/board/`, { signal }),
    refetchInterval: 60_000,
  })
}

export function useHkSummary() {
  return useQuery({
    queryKey: hkKeys.summary(),
    queryFn: ({ signal }) => api.get<HkSummary>(`${BASE}/summary/`, { signal }),
  })
}

export function useStaff(enabled = true) {
  return useQuery({
    queryKey: hkKeys.staff(),
    queryFn: ({ signal }) => api.get<StaffResponse>(`${BASE}/staff/`, { signal }),
    enabled,
  })
}

export function useHkSettings() {
  return useQuery({
    queryKey: hkKeys.settings(),
    queryFn: ({ signal }) => api.get<HkSettings>(`${BASE}/settings/`, { signal }),
  })
}

export function useTickets(filters: TicketFilters) {
  return useQuery({
    queryKey: hkKeys.tickets(filters),
    queryFn: ({ signal }) =>
      api.get<Page<MaintenanceTicket>>(`${BASE}/tickets/`, {
        params: {
          status: filters.status,
          blocking: filters.blocking ? 'true' : undefined,
          mine: filters.mine ? 1 : undefined,
          q: filters.q?.trim() || undefined,
          room: filters.room,
          page_size: 200,
        },
        signal,
      }),
    select: (data) => data.results,
  })
}

/** A private ticket photo as a Blob (the API path comes with its `/api/v1` prefix). */
export function fetchPhoto(fileUrl: string, signal?: AbortSignal) {
  return api.get<Blob>(fileUrl.replace(/^\/api\/v1/, ''), { responseType: 'blob', signal })
}

// ---- Writes -----------------------------------------------------------------------------------------------

export const startTask = (id: string) => api.post<HkTask>(`${BASE}/tasks/${id}/start/`)
export const finishTask = (id: string, notes = '') => api.post<HkTask>(`${BASE}/tasks/${id}/finish/`, { notes })
export const inspectTask = (id: string, passed: boolean, notes = '') =>
  api.post<HkTask>(`${BASE}/tasks/${id}/inspect/`, { passed, notes })
export const assignTask = (id: string, userId: string | null) =>
  api.post<HkTask>(`${BASE}/tasks/${id}/assign/`, { user_id: userId })
export const cancelTask = (id: string, reason = '') => api.post<HkTask>(`${BASE}/tasks/${id}/cancel/`, { reason })
export const updateTask = (id: string, data: Partial<Pick<HkTask, 'priority' | 'notes' | 'estimated_minutes'>>) =>
  api.patch<HkTask>(`${BASE}/tasks/${id}/`, data)
export const createTask = (data: {
  room_id: string
  kind: TaskKind
  priority: Priority
  notes: string
  assigned_to_id: string | null
}) => api.post<HkTask>(`${BASE}/tasks/`, data)
export const autoAssign = (userIds?: string[]) =>
  api.post<AutoAssignReport>(`${BASE}/tasks/auto-assign/`, userIds ? { user_ids: userIds } : {})
export const generateTasks = () => api.post<GenerateReport>(`${BASE}/tasks/generate/`)
export const setRoomStatus = (roomId: string, status: HousekeepingStatus) =>
  api.post<{ id: string; number: string; housekeeping_status: HousekeepingStatus }>(`${BASE}/rooms/${roomId}/status/`, {
    housekeeping_status: status,
  })
export const updateSettings = (data: Partial<HkSettings>) => api.patch<HkSettings>(`${BASE}/settings/`, data)

/** Always multipart, so photos travel with the report (a ticket and its photos are created together). */
export function createTicket(input: TicketInput) {
  const form = new FormData()
  for (const [key, value] of Object.entries(input)) {
    if (key === 'photos' || value === undefined || value === null || value === '') continue
    form.append(key, typeof value === 'boolean' ? String(value) : String(value))
  }
  for (const photo of input.photos ?? []) form.append('photos', photo)
  return api.post<MaintenanceTicket>(`${BASE}/tickets/`, undefined, { formData: form })
}

export const updateTicket = (id: string, data: Partial<Omit<TicketInput, 'photos'>>) =>
  api.patch<MaintenanceTicket>(`${BASE}/tickets/${id}/`, data)
export const startTicket = (id: string) => api.post<MaintenanceTicket>(`${BASE}/tickets/${id}/start/`)
export const resolveTicket = (id: string, notes = '') =>
  api.post<MaintenanceTicket>(`${BASE}/tickets/${id}/resolve/`, { notes })
export const cancelTicket = (id: string, reason = '') =>
  api.post<MaintenanceTicket>(`${BASE}/tickets/${id}/cancel/`, { reason })
export const deleteTicket = (id: string) => api.delete<void>(`${BASE}/tickets/${id}/`)

export function addTicketPhoto(id: string, file: File) {
  const form = new FormData()
  form.append('image', file)
  return api.post<TicketPhoto>(`${BASE}/tickets/${id}/photos/`, undefined, { formData: form })
}

/** A mutation whose success refreshes everything housekeeping shows (tasks, board, summary, tickets). */
export function useHkMutation<TVariables = void, TData = unknown>(
  fn: (variables: TVariables) => Promise<TData>,
  { onSuccess, onError }: { onSuccess?: (data: TData, variables: TVariables) => void; onError?: (error: Error) => void } = {},
) {
  const queryClient = useQueryClient()
  return useMutation<TData, Error, TVariables>({
    mutationFn: fn,
    onSuccess: async (data, variables) => {
      await queryClient.invalidateQueries({ queryKey: hkKeys.all })
      onSuccess?.(data, variables)
    },
    onError: (error) => onError?.(error),
  })
}
