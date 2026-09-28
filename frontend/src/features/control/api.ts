/**
 * Control center data layer (backend `/api/v1/control/…`, see docs/integration-notes/C12-control.md):
 * integrations, automations, audit timeline + undo and alerts.
 */
import { useInfiniteQuery, useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface UserRef {
  id: string
  email: string
  name: string
}

export type I18nText = { es: string; en: string }

// ---- Integrations -------------------------------------------------------------------------------------

export type IntegrationKind =
  | 'payments'
  | 'channel_ical'
  | 'channel_channex'
  | 'einvoice'
  | 'sire'
  | 'tra'
  | 'email'
  | 'whatsapp'
  | 'llm'
export type IntegrationMode = 'real' | 'simulated'
export type IntegrationStatus = 'unknown' | 'ok' | 'error'
export type ConfigFieldType = 'text' | 'password' | 'url' | 'select' | 'boolean' | 'number' | 'textarea' | 'email'

export interface ConfigFieldOption {
  value: string | number | boolean
  label_es: string
  label_en: string
}

export interface ConfigField {
  name: string
  label_es: string
  label_en: string
  type: ConfigFieldType
  secret: boolean
  required: boolean
  options: ConfigFieldOption[]
  help_es: string
  help_en: string
  default: unknown
}

export interface ProviderInfo {
  label: string
  label_en: string
  config_fields: ConfigField[]
}

export type ConfigValue = string | number | boolean | null

export interface Integration {
  kind: IntegrationKind
  label: string
  configured: boolean
  mode: IntegrationMode
  default_mode: IntegrationMode
  enabled: boolean
  status: IntegrationStatus
  status_message: string
  last_checked_at: string | null
  updated_at: string | null
  /** Non-secret values only. */
  config: Record<string, ConfigValue>
  /** Secret fields → whether a value is stored (the value itself never leaves the backend). */
  secrets_configured: Record<string, boolean>
  missing_required: string[]
  /** Modes this installation allows (production: only `real`, except email and AI). */
  available_modes: IntegrationMode[]
  /** Every registered provider, allowed here or not. */
  providers: Partial<Record<IntegrationMode, ProviderInfo>>
  test?: { ok: boolean; message: string }
}

export interface IntegrationUpdate {
  mode?: IntegrationMode
  enabled?: boolean
  config?: Record<string, ConfigValue>
  /** A value sets the secret, `null` removes it, `""` keeps it. */
  secrets?: Record<string, string | null>
}

// ---- Automations --------------------------------------------------------------------------------------

export type RunStatus = 'running' | 'success' | 'partial' | 'failed' | 'skipped'
export type ParamType = 'boolean' | 'integer' | 'number' | 'text' | 'json'

export interface Schedule {
  cron: string | null
  every_seconds: number | null
  text: I18nText
}

export interface RunSummary {
  id: string
  code: string
  name: I18nText
  status: RunStatus
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  summary: string
  triggered_by: UserRef | null
  manual: boolean
  details?: Record<string, unknown>
}

export interface Automation {
  code: string
  app: string
  name: I18nText
  description: I18nText
  schedule: Schedule
  next_run_at: string | null
  enabled: boolean
  default_enabled: boolean
  customized: boolean
  params: Record<string, unknown>
  default_params: Record<string, unknown>
  param_types: Record<string, ParamType>
  last_run: RunSummary | null
  recent_runs: { id: string; status: RunStatus; started_at: string }[]
  stats_7d: { runs: number; failed: number }
}

export interface RunNowResult {
  queued: boolean
  run: RunSummary | null
  estimated_seconds: number | null
}

// ---- Audit --------------------------------------------------------------------------------------------

export type AuditSource = 'user' | 'automation' | 'ai' | 'channel' | 'guest' | 'system' | 'api'

export interface AuditEvent {
  id: string
  created_at: string
  action: string
  app: string
  source: AuditSource
  actor: UserRef | null
  actor_label: string
  summary: string
  target_type: string
  target_id: string
  target_link: string
  scope: 'property' | 'organization'
  property: { id: string; name: string } | null
  has_changes: boolean
  reversible: boolean
  undoable: boolean
  undone_at: string | null
  undone_by: UserRef | null
}

export interface AuditEventDetail extends AuditEvent {
  changes: Record<string, unknown>
  diff: { field: string; before: unknown; after: unknown }[]
  details: { field: string; value: unknown }[]
  row_changes: { label: string; created: boolean; changes: { field: string; before: unknown; after: unknown }[] }[]
  row_changes_total: number
  request_id: string
  undo_event_id: string | null
  original_event_id: string | null
  can_undo: boolean
}

export interface AuditFilters {
  q?: string
  app?: string
  action?: string
  source?: string
  actor?: string
  start?: string
  end?: string
  reversible?: boolean
  reservation?: string
}

export interface AuditFacets {
  actions: { action: string; count: number }[]
  apps: { app: string; count: number }[]
  sources: { source: AuditSource; count: number }[]
  actors: { id: string; name: string; email: string }[]
  total: number
}

// ---- Alerts -------------------------------------------------------------------------------------------

export type Severity = 'critical' | 'warning' | 'info'

export interface Alert {
  id: string
  kind: string
  severity: Severity
  title: string
  message: string
  link: string
  source: string
  data: Record<string, unknown>
  created_at: string
  updated_at: string
  resolved_at: string | null
  resolved_by: UserRef | null
}

export interface AlertCounts {
  open: number
  by_severity: Record<Severity, number>
  latest: Alert[]
}

export interface AlertFilters {
  status: 'open' | 'resolved'
  severity?: Severity | ''
  q?: string
}

// ---- Keys ---------------------------------------------------------------------------------------------

export const controlKeys = {
  all: ['control'] as const,
  integrations: () => ['control', 'integrations'] as const,
  automations: () => ['control', 'automations'] as const,
  runs: (code: string | null) => ['control', 'automation-runs', code ?? 'all'] as const,
  auditList: (filters: AuditFilters) => ['control', 'audit', 'list', filters] as const,
  auditFacets: () => ['control', 'audit', 'facets'] as const,
  /** Same key the rates grid uses to probe `GET audit/{id}/` (features/rates/api.ts `auditKey`). */
  auditEvent: (id: string) => ['control', 'audit', id] as const,
  alerts: (filters: AlertFilters) => ['control', 'alerts', 'list', filters] as const,
  alertCount: () => ['control', 'alerts', 'count'] as const,
}

// ---- Integrations hooks -------------------------------------------------------------------------------

export function useIntegrations() {
  return useQuery({
    queryKey: controlKeys.integrations(),
    queryFn: () => api.get<Integration[]>('/control/integrations/'),
  })
}

function replaceIntegration(queryClient: QueryClient, updated: Integration) {
  queryClient.setQueryData<Integration[]>(controlKeys.integrations(), (current) =>
    current?.map((item) => (item.kind === updated.kind ? updated : item)),
  )
}

export function useUpdateIntegration() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, body }: { kind: IntegrationKind; body: IntegrationUpdate }) =>
      api.patch<Integration>(`/control/integrations/${kind}/`, body),
    onSuccess: (updated) => {
      replaceIntegration(queryClient, updated)
      // pages of other features show the mode of their integration (AI settings, compliance…)
      void queryClient.invalidateQueries({ predicate: (query) => query.queryKey[0] !== 'me' && query.queryKey[0] !== 'control' })
    },
  })
}

export function useTestIntegration() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (kind: IntegrationKind) => api.post<Integration>(`/control/integrations/${kind}/test/`),
    onSuccess: (updated) => replaceIntegration(queryClient, updated),
  })
}

// ---- Automations hooks --------------------------------------------------------------------------------

export function useAutomations() {
  return useQuery({
    queryKey: controlKeys.automations(),
    queryFn: () => api.get<Automation[]>('/control/automations/'),
    refetchInterval: 60_000,
  })
}

export function useUpdateAutomation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ code, body }: { code: string; body: { enabled?: boolean; params?: Record<string, unknown> | null } }) =>
      api.patch<Automation>(`/control/automations/${code}/`, body),
    onSuccess: (updated) => {
      queryClient.setQueryData<Automation[]>(controlKeys.automations(), (current) =>
        current?.map((item) => (item.code === updated.code ? updated : item)),
      )
    },
  })
}

export function useRunAutomation() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => api.post<RunNowResult>(`/control/automations/${code}/run/`),
    // A run can change anything (the night audit moves the business date shown in the topbar): refresh all.
    onSuccess: () => void queryClient.invalidateQueries(),
  })
}

export function useAutomationRuns(code: string | null, enabled = true) {
  return useInfiniteQuery({
    queryKey: controlKeys.runs(code),
    queryFn: ({ pageParam }) =>
      api.get<Page<RunSummary>>('/control/automation-runs/', { params: { code: code ?? undefined, page: pageParam, page_size: 20 } }),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
    enabled,
  })
}

// ---- Audit hooks --------------------------------------------------------------------------------------

function auditParams(filters: AuditFilters) {
  return {
    q: filters.q || undefined,
    app: filters.app || undefined,
    action: filters.action || undefined,
    source: filters.source || undefined,
    actor: filters.actor || undefined,
    start: filters.start || undefined,
    end: filters.end || undefined,
    reversible: filters.reversible ? '1' : undefined,
    reservation: filters.reservation || undefined,
  }
}

export function useAuditEvents(filters: AuditFilters, { pageSize = 50, enabled = true } = {}) {
  return useInfiniteQuery({
    queryKey: controlKeys.auditList(filters),
    queryFn: ({ pageParam }) =>
      api.get<Page<AuditEvent>>('/control/audit/', { params: { ...auditParams(filters), page: pageParam, page_size: pageSize } }),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
    enabled,
  })
}

export function useAuditFacets() {
  return useQuery({
    queryKey: controlKeys.auditFacets(),
    queryFn: () => api.get<AuditFacets>('/control/audit/facets/'),
    staleTime: 60_000,
  })
}

export function useAuditEvent(id: string | null) {
  return useQuery({
    queryKey: controlKeys.auditEvent(id ?? 'none'),
    queryFn: () => api.get<AuditEventDetail>(`/control/audit/${id}/`),
    enabled: id !== null,
  })
}

/** Undo refreshes the timeline and the data of the features whose objects it may have restored. */
export function useUndoAudit() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.post<AuditEventDetail>(`/control/audit/${id}/undo/`, { confirm: true }),
    onSuccess: (event) => {
      queryClient.setQueryData(controlKeys.auditEvent(event.id), event)
      void queryClient.invalidateQueries({ queryKey: ['control', 'audit'] })
      for (const prefix of ['bookings', 'frontdesk', 'calendar', 'rates', 'housekeeping', 'finance', 'guests']) {
        void queryClient.invalidateQueries({ queryKey: [prefix] })
      }
    },
  })
}

// ---- Alerts hooks -------------------------------------------------------------------------------------

export function useAlerts(filters: AlertFilters) {
  return useInfiniteQuery({
    queryKey: controlKeys.alerts(filters),
    queryFn: ({ pageParam }) =>
      api.get<Page<Alert>>('/control/alerts/', {
        params: { status: filters.status, severity: filters.severity || undefined, q: filters.q || undefined, page: pageParam, page_size: 30 },
      }),
    initialPageParam: 1,
    getNextPageParam: (last, pages) => (last.next ? pages.length + 1 : undefined),
  })
}

/** Topbar bell and Today widget: open alerts by severity + the latest ones (polled every minute). */
export function useAlertCount({ enabled = true } = {}) {
  return useQuery({
    queryKey: controlKeys.alertCount(),
    queryFn: () => api.get<AlertCounts>('/control/alerts/count/'),
    refetchInterval: 60_000,
    enabled,
  })
}

export function useResolveAlerts() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (ids: string[]) => {
      if (ids.length === 1) {
        await api.post<Alert>(`/control/alerts/${ids[0]}/resolve/`)
        return { resolved: 1 }
      }
      return api.post<{ resolved: number }>('/control/alerts/resolve/', { ids })
    },
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['control', 'alerts'] }),
  })
}
