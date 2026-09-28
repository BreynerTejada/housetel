import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api, type Query } from '@/lib/api'

// ---- Types: exact shapes of /api/v1/reports/ (see docs/integration-notes/C10-reports.md) ---------------

export type ReportCategory = 'performance' | 'operations' | 'finance' | 'taxes'
/** past = history · future = on the books · date = a day (default today) · any = both · none = snapshot. */
export type RangeKind = 'past' | 'future' | 'date' | 'any' | 'none'
export type CompareMode = 'previous_period' | 'previous_year'
export type ExportFormat = 'csv' | 'xlsx' | 'pdf'
export type ValueType =
  | 'text'
  | 'date'
  | 'month'
  | 'datetime'
  | 'number'
  | 'money'
  | 'percent'
  | 'status'
  | 'country'
  | 'code'
  | 'boolean'
export type KpiIntent = 'higher-is-better' | 'lower-is-better' | 'neutral'

export interface ReportDef {
  id: string
  category: ReportCategory
  permission: string
  /** Whether the current user may open it (its category permission). */
  allowed: boolean
  range_kind: RangeKind
  /** Backend preset ids: today, yesterday, this_week, this_month, last_month, last30, next14, next30, next90. */
  default_preset: string | null
  compare: boolean
  group_by: string[]
  default_group_by: string | null
  /** Pickup: `days` window (1–90). */
  window_param: boolean
  window_default: number | null
}

/** Money comes as a two-decimal string ("470115.00"); percent and number as numbers; text as a string. */
export type KpiValue = string | number | null

export interface Kpi {
  key: string
  label: string
  type: 'money' | 'percent' | 'number' | 'text'
  value: KpiValue
  intent: KpiIntent
  unit?: 'days' | 'nights'
  /** Only when a comparison is on. Percent KPIs change in points (`change`), the rest also in % (`change_pct`). */
  previous?: KpiValue
  change?: KpiValue
  change_pct?: number | null
}

export interface ChartSeries {
  key: string
  label: string
  role: 'primary' | 'compare' | 'stack'
}

/** Chart values are plain numbers (money too); `x` values are ISO dates or labels. */
export type ChartRow = Record<string, string | number | boolean | null>

export interface ChartSpec {
  key: string
  title: string
  type: 'line' | 'column' | 'hbar' | 'stacked_column' | 'status_bar'
  x: string
  x_type: 'date' | 'month' | 'text'
  value_type: 'money' | 'percent' | 'number'
  series: ChartSeries[]
  data: ChartRow[]
  /** The business date, when it falls inside the range. */
  marker: { x: string; label: string } | null
  /** First x (ISO date) whose values are a forecast (on the books). */
  forecast_from: string | null
}

export interface ReportColumn {
  key: string
  label: string
  type: ValueType
  status_kind?: 'reservation' | 'room' | 'payment'
  /** "reservation" → the row's `reservation_id` opens the reservation. */
  link?: 'reservation'
  /** code → label for `status` / `code` columns (already in the report language). */
  labels?: Record<string, string>
}

export type TableRow = Record<string, string | number | boolean | null>

export interface ReportTableData {
  key: string
  title: string
  columns: ReportColumn[]
  rows: TableRow[]
  totals: TableRow | null
}

export interface ReportData {
  id: string
  category: ReportCategory
  title: string
  lang: 'es' | 'en'
  currency: string
  property: { id: string; name: string; slug: string }
  business_date: string
  /** Both ends inclusive business dates; null for snapshots. */
  range: { start: string; end: string; days: number } | null
  compare: { mode: CompareMode; start: string; end: string; days: number } | null
  group_by: string | null
  params: { days?: number }
  summary: Kpi[]
  charts: ChartSpec[]
  tables: ReportTableData[]
  /** Definitions used; the first one spells out the range, the second the comparison (when on). */
  notes: string[]
  meta: Record<string, unknown>
  generated_at: string
}

/** Query of `GET /reports/<id>/`; empty values are omitted by the API client. */
export interface ReportQuery {
  start?: string
  end?: string
  compare?: CompareMode
  group_by?: string
  days?: number
  lang?: 'es' | 'en'
}

// ---- Hooks ------------------------------------------------------------------------------------------

export const reportKeys = {
  all: ['reports'] as const,
  catalog: () => ['reports', 'catalog'] as const,
  report: (id: string, query: ReportQuery) => ['reports', 'report', id, query] as const,
}

export function useReportCatalog() {
  return useQuery({
    queryKey: reportKeys.catalog(),
    queryFn: ({ signal }) => api.get<ReportDef[]>('/reports/', { signal }),
    staleTime: 5 * 60_000,
  })
}

/** Keeps the previous report on screen while a new range loads (no skeleton flash on refetch). */
export function useReport(id: string | undefined, query: ReportQuery, enabled = true) {
  return useQuery({
    queryKey: reportKeys.report(id ?? '', query),
    queryFn: ({ signal }) => api.get<ReportData>(`/reports/${id}/`, { params: toParams(query), signal }),
    enabled: Boolean(id) && enabled,
    placeholderData: keepPreviousData,
  })
}

function toParams(query: ReportQuery): Query {
  return {
    start: query.start,
    end: query.end,
    compare: query.compare,
    group_by: query.group_by,
    days: query.days,
    lang: query.lang,
  }
}

/** Downloads the report as CSV/XLSX/PDF (same filters as the screen) and saves it with a readable name. */
export async function downloadReport(id: string, query: ReportQuery, format: ExportFormat, fileStem: string) {
  const blob = await api.get<Blob>(`/reports/${id}/`, { params: { ...toParams(query), format }, responseType: 'blob' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${fileStem}.${format}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
