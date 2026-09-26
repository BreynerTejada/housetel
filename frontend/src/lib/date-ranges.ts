import { addDays, endOfMonth, endOfWeek, startOfMonth, startOfWeek, subDays, subMonths } from 'date-fns'
import { parseDate, toISODate } from './format'

export type RangePresetId = 'today' | 'yesterday' | 'tomorrow' | 'thisWeek' | 'next7' | 'thisMonth' | 'lastMonth' | 'last30'

/** `YYYY-MM-DD` range; both ends inclusive for reports, `to` = checkout (exclusive) for stays. */
export interface DateRangeValue {
  from: string
  to: string
}

const WEEK = { weekStartsOn: 1 } as const

/** Preset ranges relative to `today` (pass the property's business date). Both ends inclusive. */
export function rangePreset(id: RangePresetId, today: string | Date): DateRangeValue {
  const day = (typeof today === 'string' ? parseDate(today) : today) ?? new Date()
  const range = (from: Date, to: Date): DateRangeValue => ({ from: toISODate(from), to: toISODate(to) })
  switch (id) {
    case 'today':
      return range(day, day)
    case 'yesterday':
      return range(subDays(day, 1), subDays(day, 1))
    case 'tomorrow':
      return range(addDays(day, 1), addDays(day, 1))
    case 'thisWeek':
      return range(startOfWeek(day, WEEK), endOfWeek(day, WEEK))
    case 'next7':
      return range(day, addDays(day, 6))
    case 'thisMonth':
      return range(startOfMonth(day), endOfMonth(day))
    case 'lastMonth': {
      const previous = subMonths(day, 1)
      return range(startOfMonth(previous), endOfMonth(previous))
    }
    case 'last30':
      return range(subDays(day, 29), day)
  }
}
