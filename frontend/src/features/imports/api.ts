/**
 * Importer API client (backend `apps/imports`, docs/integration-notes/P5-imports.md). Staff endpoints under
 * `/api/v1/imports/` with `X-Property-Id`; every one needs the `imports.run` permission.
 *
 * A job is one uploaded file of one kind. Its life: `uploaded` (mapping) → `validated` (rows reviewed; the
 * dry-run keeps it there) → `queued`/`running` (dry-run, run or rollback in the worker, with progress) →
 * `completed` | `failed` (resumable) | `reverted`. Messages of rows come in both languages (`es`, `en`).
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, isApiError } from '@/lib/api'

export type ImportKind = 'guests' | 'reservations' | 'room_types' | 'rooms'
export type ImportPreset = 'generic' | 'cloudbeds'
export type JobStatus = 'uploaded' | 'validated' | 'queued' | 'running' | 'completed' | 'failed' | 'reverted'
export type JobPhase = '' | 'dry_run' | 'run' | 'revert'
export type RowStatus = 'pending' | 'valid' | 'warning' | 'error' | 'skip'
export type DryOutcome = '' | 'create' | 'update' | 'skip' | 'fail'
export type RowOutcome = '' | 'created' | 'updated' | 'skipped' | 'failed' | 'reverted'
export type FieldGroup = 'main' | 'guest' | 'stay' | 'money' | 'extra'
export type DateFormat = 'auto' | 'dmy' | 'mdy' | 'ymd'
export type OnExisting = 'update' | 'skip'
export type StartMode = 'dry_run' | 'run' | 'revert'

export const KINDS: ImportKind[] = ['reservations', 'guests', 'room_types', 'rooms']
export const PRESETS: ImportPreset[] = ['cloudbeds', 'generic']
export const DATE_FORMATS: DateFormat[] = ['auto', 'dmy', 'mdy', 'ymd']
export const ACCEPTED_EXTENSIONS = ['.csv', '.xlsx', '.xlsm', '.txt']
export const MAX_FILE_BYTES = 15 * 1024 * 1024

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

/** A message stored in both languages (`code` is stable). */
export interface Bilingual {
  code?: string
  es: string
  en: string
}

export interface RowIssue extends Bilingual {
  level: 'error' | 'warning' | 'skip' | 'info'
  code: string
  field: string
}

export interface UserRef {
  id: string
  email: string
  name: string
}

export interface ValidationCounts {
  valid?: number
  warning?: number
  error?: number
  skip?: number
}

export interface DryRunSummary {
  create?: number
  update?: number
  skip?: number
  fail?: number
}

export interface RunSummary {
  created?: number
  updated?: number
  skipped?: number
  failed?: number
  total?: number
  start?: string | null
  end?: string | null
  room_type_ids?: string[]
}

export interface RevertSummary {
  reverted?: number
  not_reverted?: number
  reasons?: Record<string, number>
}

export interface JobSummary {
  id: string
  kind: ImportKind
  preset: ImportPreset
  source_label: string
  status: JobStatus
  phase: JobPhase
  /** Queued and nobody took it, or running and the worker stopped reporting: it can be launched again. */
  stale: boolean
  filename: string
  file_format: 'csv' | 'xlsx'
  total_rows: number
  counts: ValidationCounts
  summary: RunSummary
  progress: { done: number; total: number }
  created_by: UserRef | null
  created_at: string
  finished_at: string | null
  reverted_at: string | null
  /** Habeas Data: the file's cells were erased (the results stay). */
  data_purged: boolean
}

export interface FieldSpec {
  code: string
  type: string
  required: boolean
  group: FieldGroup
  value_mapping: '' | 'room_type' | 'rate_plan'
}

export interface ValueCandidate {
  value: string
  count: number
  suggested: string
  selected: string
}

export interface I18nName {
  es: string
  en: string
}

export interface RoomTypeOption {
  id: string
  code: string
  name: I18nName
  kind: 'private' | 'dorm'
  is_active: boolean
  max_adults: number
  max_children: number
  max_occupancy: number
}

export interface RatePlanOption {
  id: string
  code: string
  name: I18nName
  kind: string
  room_type_ids: string[]
}

export interface JobOptions {
  date_format: DateFormat
  amounts_include_tax: boolean
  on_existing: OnExisting
  /** uuid of the plan for rows without one ("" = the first active base plan). */
  default_rate_plan: string
  date_format_detected?: 'dmy' | 'mdy'
  date_format_ambiguous?: boolean
}

export type ValueMap = Partial<Record<'room_type' | 'rate_plan', Record<string, string>>>

export interface JobDetail extends JobSummary {
  source_system: string
  sheet_name: string
  file_size: number
  headers: string[]
  samples: Record<string, string[]>
  preview: { number: number; raw: Record<string, string> }[]
  /** {field code: column title} */
  mapping: Record<string, string>
  suggested_mapping: Record<string, string>
  /** Required field codes (or "a|b" groups) the mapping does not cover. */
  missing_required: string[]
  fields: FieldSpec[]
  one_of: string[][]
  value_map: ValueMap
  /** Distinct values of the category / plan columns (only while the mapping can change). */
  values: Partial<Record<'room_type' | 'rate_plan', ValueCandidate[]>>
  room_types: RoomTypeOption[]
  rate_plans: RatePlanOption[]
  options: JobOptions
  business_date: string
  dry_run_at: string | null
  dry_run_summary: DryRunSummary
  revert_summary: RevertSummary
  /** Rows by final outcome, live (after a rollback the reverted ones are apart); empty until it ran. */
  outcome_counts: Partial<Record<Exclude<RowOutcome, ''>, number>>
  error: string
  run_by: UserRef | null
  queued_at: string | null
  started_at: string | null
  heartbeat_at: string | null
  reverted_by: UserRef | null
  can_edit: boolean
  can_delete: boolean
  can_revert: boolean
  ready_rows: number
}

export interface StayData {
  room_type_id: string
  room_type_code: string
  kind: string
  rate_plan_id: string | null
  adults: number
  children: number
  room_id: string | null
  bed_id: string | null
  room_label: string
  total: string | null
}

export interface GuestData {
  first_name?: string
  last_name?: string
  email?: string
  phone?: string
  document_type?: string
  document_number?: string
  nationality?: string
  country_of_residence?: string
}

/** Normalized values of a row (shape depends on the kind; empty until validated or after the purge). */
export interface RowData {
  guest?: GuestData
  stage?: '' | 'future' | 'in_house'
  status?: string
  checkin?: string | null
  checkout?: string | null
  stays?: StayData[]
  total?: string | null
  paid?: string | null
  code?: string
  name?: string
  kind?: string
  room_numbers?: string[]
  number?: string
  room_type_code?: string
  floor?: string
}

export interface ImportRow {
  id: string
  number: number
  raw: Record<string, string>
  data: RowData
  external_id: string
  group_key: string
  status: RowStatus
  issues: RowIssue[]
  dry_outcome: DryOutcome
  dry_message: Bilingual | Record<string, never>
  outcome: RowOutcome
  outcome_message: Bilingual | Record<string, never>
  target_type: string
  target_id: string | null
  target_label: string
  revert: Bilingual | null
  processed_at: string | null
}

export interface RowFilters {
  status?: RowStatus[]
  dry_outcome?: DryOutcome[]
  outcome?: RowOutcome[]
  q?: string
  page?: number
}

export interface RevertPreview {
  revertible: number
  in_house: number
  not_active: number
  activity: number
  missing: number
  total: number
}

export interface ConfigureInput {
  mapping?: Record<string, string>
  value_map?: ValueMap
  options?: Partial<JobOptions>
  source_label?: string
}

export interface UploadInput {
  kind: ImportKind
  preset: ImportPreset
  file: File
  source_label?: string
}

const BASE = '/imports'
export const ACTIVE_STATUSES: JobStatus[] = ['queued', 'running']
export const EDITABLE_STATUSES: JobStatus[] = ['uploaded', 'validated']

export const importKeys = {
  all: ['imports'] as const,
  jobs: (page: number) => ['imports', 'jobs', page] as const,
  job: (id: string) => ['imports', 'job', id] as const,
  rows: (id: string, filters: RowFilters) => ['imports', 'rows', id, filters] as const,
  rowsOf: (id: string) => ['imports', 'rows', id] as const,
  revertPreview: (id: string) => ['imports', 'revert-preview', id] as const,
}

export function isActive(job: Pick<JobSummary, 'status'> | undefined | null): boolean {
  return Boolean(job && ACTIVE_STATUSES.includes(job.status))
}

// ---- Queries ------------------------------------------------------------------------------------------

export function useImportJobs(page = 1) {
  return useQuery({
    queryKey: importKeys.jobs(page),
    queryFn: () => api.get<Page<JobSummary>>(`${BASE}/jobs/`, { params: { page, page_size: 10 } }),
    placeholderData: keepPreviousData,
    // a job of the list may be running: refresh while that lasts
    refetchInterval: (query) => (query.state.data?.results.some((job) => isActive(job)) ? 3000 : false),
  })
}

export function useImportJob(id: string | undefined) {
  return useQuery({
    queryKey: importKeys.job(id ?? 'none'),
    queryFn: () => api.get<JobDetail>(`${BASE}/jobs/${id}/`),
    enabled: Boolean(id),
    staleTime: 0,
    // while the worker is on it: the progress every second
    refetchInterval: (query) => (isActive(query.state.data) ? 1000 : false),
  })
}

/** `version` (status, dry-run and finish times of the job) refetches the rows when a phase ends. */
export function useImportRows(id: string, filters: RowFilters, { enabled = true, version = '' }: { enabled?: boolean; version?: string } = {}) {
  return useQuery({
    queryKey: [...importKeys.rows(id, filters), version],
    queryFn: () =>
      api.get<Page<ImportRow>>(`${BASE}/jobs/${id}/rows/`, {
        params: {
          status: filters.status,
          dry_outcome: filters.dry_outcome,
          outcome: filters.outcome,
          q: filters.q,
          page: filters.page ?? 1,
          page_size: 25,
        },
      }),
    enabled,
    placeholderData: keepPreviousData,
  })
}

export function useRevertPreview(id: string, enabled: boolean) {
  return useQuery({
    queryKey: importKeys.revertPreview(id),
    queryFn: () => api.get<RevertPreview>(`${BASE}/jobs/${id}/revert-preview/`),
    enabled,
    staleTime: 0,
  })
}

// ---- Mutations ----------------------------------------------------------------------------------------

export function uploadImport(input: UploadInput): Promise<JobDetail> {
  const form = new FormData()
  form.append('kind', input.kind)
  form.append('preset', input.preset)
  form.append('file', input.file)
  if (input.source_label?.trim()) form.append('source_label', input.source_label.trim())
  return api.post<JobDetail>(`${BASE}/jobs/`, undefined, { formData: form })
}

export function useUploadImport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: uploadImport,
    onSuccess: (job) => {
      queryClient.setQueryData(importKeys.job(job.id), job)
      void queryClient.invalidateQueries({ queryKey: ['imports', 'jobs'] })
    },
  })
}

/** The backend answers 400 `mapping_incomplete` with the saved job inside (`job`): keep it in the cache. */
export function jobFromError(error: unknown): JobDetail | null {
  if (!isApiError(error) || error.code !== 'mapping_incomplete') return null
  const job = error.data?.job
  return job && typeof job === 'object' ? (job as JobDetail) : null
}

export function missingFromError(error: unknown): string[] {
  if (!isApiError(error) || error.code !== 'mapping_incomplete') return []
  const missing = error.data?.missing
  return Array.isArray(missing) ? missing.map(String) : []
}

export function useConfigureImport(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: ConfigureInput) => api.patch<JobDetail>(`${BASE}/jobs/${id}/`, input),
    onSuccess: (job) => {
      queryClient.setQueryData(importKeys.job(id), job)
      void queryClient.invalidateQueries({ queryKey: importKeys.rowsOf(id) })
      void queryClient.invalidateQueries({ queryKey: ['imports', 'jobs'] })
    },
    onError: (error) => {
      const job = jobFromError(error)
      if (job) queryClient.setQueryData(importKeys.job(id), job)
    },
  })
}

export function useStartImport(id: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ mode, confirm = false }: { mode: StartMode; confirm?: boolean }) => {
      const path = mode === 'dry_run' ? 'dry-run' : mode
      return api.post<JobDetail>(`${BASE}/jobs/${id}/${path}/`, { confirm })
    },
    onSuccess: (job) => {
      queryClient.setQueryData(importKeys.job(id), job)
      void queryClient.invalidateQueries({ queryKey: ['imports', 'jobs'] })
    },
  })
}

export function useDeleteImport() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`${BASE}/jobs/${id}/`),
    onSuccess: (_result, id) => {
      queryClient.removeQueries({ queryKey: importKeys.job(id) })
      void queryClient.invalidateQueries({ queryKey: ['imports', 'jobs'] })
    },
  })
}

// ---- Files --------------------------------------------------------------------------------------------

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

const TEMPLATE_STEMS: Record<ImportKind, { es: string; en: string }> = {
  guests: { es: 'huespedes', en: 'guests' },
  reservations: { es: 'reservas', en: 'reservations' },
  room_types: { es: 'categorias', en: 'room-types' },
  rooms: { es: 'habitaciones', en: 'rooms' },
}

/** Template (empty, Housetel's titles) or example file (rows built from this property's data). */
export async function downloadTemplate(
  kind: ImportKind,
  { lang, format, example = false, preset = 'generic' }: { lang: 'es' | 'en'; format: 'csv' | 'xlsx'; example?: boolean; preset?: ImportPreset },
) {
  const blob = await api.get<Blob>(`${BASE}/templates/${kind}/`, {
    params: { lang, format, example: example ? 1 : undefined, preset },
    responseType: 'blob',
  })
  const prefix = example ? (lang === 'en' ? 'example' : 'ejemplo') : lang === 'en' ? 'template' : 'plantilla'
  const cloud = preset === 'cloudbeds' && (kind === 'reservations' || kind === 'guests') ? '-cloudbeds' : ''
  saveBlob(blob, `housetel-${prefix}-${TEMPLATE_STEMS[kind][lang]}${cloud}.${format}`)
}

/** CSV report of the job (every row, or only the ones with errors/warnings), in the chosen language. */
export async function downloadReport(job: Pick<JobSummary, 'id' | 'filename'>, { lang, onlyIssues }: { lang: 'es' | 'en'; onlyIssues: boolean }) {
  const blob = await api.get<Blob>(`${BASE}/jobs/${job.id}/report/`, {
    params: { lang, only: onlyIssues ? 'issues' : undefined },
    responseType: 'blob',
  })
  const stem = job.filename.replace(/\.[^.]+$/, '').slice(0, 60) || 'importacion'
  const suffix = onlyIssues ? (lang === 'en' ? 'issues' : 'errores') : lang === 'en' ? 'report' : 'reporte'
  saveBlob(blob, `${stem}-${suffix}.csv`)
}
