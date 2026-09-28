import { differenceInCalendarDays, format, isValid, parseISO } from 'date-fns'
import { enUS, es } from 'date-fns/locale'
import type { Lang } from '@/lib/format'

const LOCALES = { es, en: enUS } as const
const WINDOW_HOURS = 24
const HOUR = 3_600_000

function toDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const date = parseISO(value)
  return isValid(date) ? date : null
}

/**
 * Whole hours left in WhatsApp's 24 h customer-service window, counted from the guest's last message
 * (free text is only accepted inside it). 0 = less than an hour left; null = closed or never opened.
 */
export function windowHoursLeft(lastInboundAt: string | null | undefined, now: Date = new Date()): number | null {
  const last = toDate(lastInboundAt)
  if (!last) return null
  const left = WINDOW_HOURS * HOUR - (now.getTime() - last.getTime())
  return left > 0 ? Math.floor(left / HOUR) : null
}

/** Time of the last activity in the conversation list: clock today, "yesterday", weekday, then the date. */
export function listTime(value: string | null | undefined, lang: Lang, now: Date = new Date()): string {
  const date = toDate(value)
  if (!date) return ''
  const days = differenceInCalendarDays(now, date)
  const locale = LOCALES[lang]
  if (days <= 0) return format(date, 'HH:mm')
  if (days === 1) return lang === 'en' ? 'yesterday' : 'ayer'
  if (days < 7) return format(date, 'EEE', { locale }).replace('.', '')
  return format(date, lang === 'en' ? 'MMM d' : 'd MMM', { locale }).replace('.', '')
}

/** Local calendar day (`YYYY-MM-DD`) of an ISO datetime. */
export function dayKey(value: string): string {
  const date = toDate(value)
  return date ? format(date, 'yyyy-MM-dd') : ''
}

export interface DayGroup<T> {
  day: string
  items: T[]
}

/** Consecutive messages of the same local day, in the order given (oldest first). */
export function groupByDay<T extends { created_at: string }>(messages: T[]): DayGroup<T>[] {
  const groups: DayGroup<T>[] = []
  for (const message of messages) {
    const day = dayKey(message.created_at)
    const last = groups.at(-1)
    if (last && last.day === day) last.items.push(message)
    else groups.push({ day, items: [message] })
  }
  return groups
}

/** Replace the textarea selection with `insertion` (or append when the caret is unknown). */
export function insertAtCursor(
  text: string,
  insertion: string,
  selectionStart: number | null,
  selectionEnd: number | null,
): { text: string; caret: number } {
  const start = selectionStart ?? text.length
  const end = selectionEnd ?? start
  const next = text.slice(0, start) + insertion + text.slice(end)
  return { text: next, caret: start + insertion.length }
}
