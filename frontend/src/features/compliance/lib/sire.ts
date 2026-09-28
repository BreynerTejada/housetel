import { subDays } from 'date-fns'
import { parseDate, toISODate } from '@/lib/format'
import type { SireReport } from '../api'

export type SireDayState = 'reported' | 'toUpload' | 'missing' | 'clear'

export interface SireDay {
  date: string
  state: SireDayState
}

export const SIRE_WINDOW_DAYS = 30

/**
 * The last 30 days (business date − 30 … − 1) and where each stands with Migración Colombia: inside a file already
 * uploaded, inside a file still waiting to be uploaded, with foreign check-ins/outs that no file covers yet, or
 * with nothing to report.
 */
export function buildSireDays(businessDate: string | undefined, reports: SireReport[], unreportedDays: string[]): SireDay[] {
  const today = parseDate(businessDate) ?? new Date()
  const missing = new Set(unreportedDays)
  const days: SireDay[] = []
  for (let offset = SIRE_WINDOW_DAYS; offset >= 1; offset -= 1) {
    const date = toISODate(subDays(today, offset))
    const covering = reports.filter((report) => report.period_start <= date && date <= report.period_end)
    let state: SireDayState = 'clear'
    if (covering.some((report) => report.status !== 'generated')) state = 'reported'
    else if (covering.length > 0) state = 'toUpload'
    else if (missing.has(date)) state = 'missing'
    days.push({ date, state })
  }
  return days
}
