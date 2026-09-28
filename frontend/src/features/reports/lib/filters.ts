import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import type { Lang } from '@/lib/format'
import type { CompareMode, ReportDef, ReportQuery } from '../api'
import { defaultPreset, PRESETS_BY_KIND, type PresetId } from './catalog'
import { matchPreset, presetRange, type ReportRange } from './presets'

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/
const COMPARE_MODES: CompareMode[] = ['previous_period', 'previous_year']
const MAX_WINDOW = 90

export interface ReportFilters {
  presets: PresetId[]
  /** `null` for snapshot reports (no date filter). */
  range: ReportRange | null
  preset: PresetId | 'custom' | null
  compare: CompareMode | null
  groupBy: string | null
  days: number | null
  /** Selected chart when a report has several (performance: occupancy, ADR, RevPAR, revenue). */
  chart: string | null
  query: ReportQuery
  setPreset: (id: PresetId) => void
  setCustomRange: (range: ReportRange) => void
  setCompare: (mode: CompareMode | null) => void
  setGroupBy: (value: string) => void
  setDays: (days: number) => void
  setChart: (key: string) => void
}

/**
 * Filters of a report live in the URL, so a link reproduces the same view. Presets are stored by name
 * (`?preset=thisMonth`) and resolved against the business date, so "Este mes" keeps meaning this month; a
 * custom range is stored as `?start=&end=` (both days included).
 */
export function useReportFilters(report: ReportDef | undefined, businessDate: string, lang: Lang): ReportFilters {
  const [params, setParams] = useSearchParams()

  const state = useMemo(() => {
    const kind = report?.range_kind ?? 'none'
    const presets = kind === 'none' ? [] : PRESETS_BY_KIND[kind]
    let range: ReportRange | null = null
    let preset: PresetId | 'custom' | null = null
    if (report && kind !== 'none' && businessDate) {
      const presetParam = params.get('preset')
      const start = params.get('start')
      const end = params.get('end')
      if (presetParam && presets.includes(presetParam as PresetId)) {
        preset = presetParam as PresetId
        range = presetRange(preset, businessDate)
      } else if (start && end && ISO_DATE.test(start) && ISO_DATE.test(end) && start <= end) {
        range = { start, end }
        preset = matchPreset(range, presets, businessDate) ?? 'custom'
      } else {
        preset = defaultPreset(report)
        range = presetRange(preset, businessDate)
      }
    }

    const compareParam = params.get('compare') as CompareMode | null
    const compare = report?.compare && compareParam && COMPARE_MODES.includes(compareParam) ? compareParam : null

    const groupParam = params.get('group_by')
    const groupBy = report && report.group_by.length > 0
      ? groupParam && report.group_by.includes(groupParam) ? groupParam : report.default_group_by
      : null

    let days: number | null = null
    if (report?.window_param) {
      const parsed = Number(params.get('days'))
      days = Number.isInteger(parsed) && parsed >= 1 && parsed <= MAX_WINDOW ? parsed : (report.window_default ?? 7)
    }

    const query: ReportQuery = {
      start: range?.start,
      end: range?.end,
      compare: compare ?? undefined,
      group_by: groupBy ?? undefined,
      days: days ?? undefined,
      lang,
    }
    return { presets, range, preset, compare, groupBy, days, chart: params.get('chart'), query }
  }, [report, businessDate, params, lang])

  const update = useCallback(
    (changes: Record<string, string | null>) => {
      setParams(
        (previous) => {
          const next = new URLSearchParams(previous)
          for (const [key, value] of Object.entries(changes)) {
            if (value === null || value === '') next.delete(key)
            else next.set(key, value)
          }
          return next
        },
        { replace: true },
      )
    },
    [setParams],
  )

  return {
    ...state,
    setPreset: (id) => update({ preset: id, start: null, end: null }),
    setCustomRange: (range) => update({ preset: null, start: range.start, end: range.end }),
    setCompare: (mode) => update({ compare: mode }),
    setGroupBy: (value) => update({ group_by: value }),
    setDays: (days) => update({ days: String(days) }),
    setChart: (key) => update({ chart: key }),
  }
}
