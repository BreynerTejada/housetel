import { addDays, endOfMonth, endOfWeek, startOfMonth, startOfWeek, subDays, subMonths } from 'date-fns'
import { parseDate, toISODate } from '@/lib/format'
import type { PresetId } from './catalog'

export interface ReportRange {
  /** First business date (included). */
  start: string
  /** Last business date (included). */
  end: string
}

const WEEK = { weekStartsOn: 1 } as const

/**
 * Preset ranges relative to the property's business date (never the browser's clock). Both ends are
 * inclusive, like the API: "Este mes" in September is 1–30 Sep = 30 business days.
 */
export function presetRange(id: PresetId, businessDate: string): ReportRange {
  const today = parseDate(businessDate) ?? new Date()
  const range = (from: Date, to: Date): ReportRange => ({ start: toISODate(from), end: toISODate(to) })
  switch (id) {
    case 'today':
      return range(today, today)
    case 'yesterday':
      return range(subDays(today, 1), subDays(today, 1))
    case 'tomorrow':
      return range(addDays(today, 1), addDays(today, 1))
    case 'thisWeek':
      return range(startOfWeek(today, WEEK), endOfWeek(today, WEEK))
    case 'thisMonth':
      return range(startOfMonth(today), endOfMonth(today))
    case 'lastMonth': {
      const previous = subMonths(today, 1)
      return range(startOfMonth(previous), endOfMonth(previous))
    }
    case 'last30':
      return range(subDays(today, 29), today)
    case 'next14':
      return range(today, addDays(today, 13))
    case 'next30':
      return range(today, addDays(today, 29))
    case 'next90':
      return range(today, addDays(today, 89))
  }
}

/** Days of an inclusive range. */
export function rangeDays(range: ReportRange): number {
  const start = parseDate(range.start)
  const end = parseDate(range.end)
  if (!start || !end) return 0
  return Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1
}

/** Every ISO date of an inclusive range (for the range ruler). */
export function rangeDates(range: ReportRange): string[] {
  const start = parseDate(range.start)
  const total = rangeDays(range)
  if (!start || total <= 0) return []
  return Array.from({ length: total }, (_, index) => toISODate(addDays(start, index)))
}

/** The preset whose range is exactly `range` (so a shared link still highlights "Este mes"). */
export function matchPreset(range: ReportRange, presets: PresetId[], businessDate: string): PresetId | null {
  return presets.find((id) => {
    const candidate = presetRange(id, businessDate)
    return candidate.start === range.start && candidate.end === range.end
  }) ?? null
}
