import { differenceInCalendarDays } from 'date-fns'
import { parseDate, type Lang } from '@/lib/format'
import type { I18nText } from '../api'

/** A translatable API value (`{es, en}`) in `lang`, then Spanish, then the first non-empty. */
export function tr(value: I18nText | string | null | undefined, lang: Lang): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  return value[lang] || value.es || Object.values(value).find(Boolean) || ''
}

export function hotelInitials(name: string): string {
  const words = name
    .replace(/^(hotel|hostal|hostel)\s+/i, '')
    .split(/\s+/)
    .filter(Boolean)
  return words
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? '')
    .join('')
}

/** Calendar days from `today` (the hotel's business date) to `date`. */
export function daysUntil(date: string, today: string): number {
  const target = parseDate(date)
  const base = parseDate(today)
  if (!target || !base) return 0
  return differenceInCalendarDays(target, base)
}

/**
 * A datetime in the hotel's time zone, whatever the guest's device says: "3 de octubre a las 15:00" /
 * "October 3 at 15:00" (hotels in Colombia state times on the 24-hour clock).
 */
export function formatHotelDateTime(iso: string | null | undefined, timeZone: string, lang: Lang): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  let parts: Intl.DateTimeFormatPart[]
  try {
    parts = new Intl.DateTimeFormat(lang === 'en' ? 'en-US' : 'es-CO', {
      timeZone,
      day: 'numeric',
      month: 'long',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date)
  } catch {
    return date.toLocaleString()
  }
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? ''
  const time = `${part('hour')}:${part('minute')}`
  return lang === 'en' ? `${part('month')} ${part('day')} at ${time}` : `${part('day')} de ${part('month')} a las ${time}`
}

/** First word of a name, for greetings. */
export function firstWord(name: string): string {
  return name.trim().split(/\s+/)[0] ?? ''
}
