import type { TFunction } from 'i18next'
import { formatDate, type Lang } from '@/lib/format'

/** "45 min", "2 h", "1 h 25 min" (namespace `housekeeping`). */
export function formatDuration(minutes: number, t: TFunction): string {
  const total = Math.max(0, Math.round(minutes))
  const hours = Math.floor(total / 60)
  const rest = total % 60
  if (hours === 0) return t('housekeeping:duration.minutes', { count: rest })
  if (rest === 0) return t('housekeeping:duration.hours', { hours })
  return t('housekeeping:duration.hoursMinutes', { hours, minutes: rest })
}

/** Wall-clock time of an ISO datetime ("09:40"); empty when there is none. */
export function formatClock(value: string | null | undefined, lang: Lang): string {
  return value ? formatDate(value, 'HH:mm', lang) : ''
}
