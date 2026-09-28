import type { TFunction } from 'i18next'
import { formatDate, formatDateRange, type Lang } from '@/lib/format'
import type { I18nText } from '../api'

/** Text of an i18n JSON field (`{es, en}`) in the UI language, falling back to Spanish. */
export function tr(value: I18nText | string | null | undefined, lang: string): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  return value[lang.startsWith('en') ? 'en' : 'es'] || value.es || Object.values(value).find(Boolean) || ''
}

/** "101", or "D1 · A" for a dorm bed; null without a room. */
export function unitLabel(room: string | null | undefined, bed?: string | null): string | null {
  if (!room) return null
  return bed ? `${room} · ${bed}` : room
}

/** "2 adultos", "2 adultos, 1 niño". */
export function guestsLabel(t: TFunction, adults: number, children: number): string {
  const parts = [t('frontdesk:guests.adults', { count: adults })]
  if (children > 0) parts.push(t('frontdesk:guests.children', { count: children }))
  return parts.join(', ')
}

/** "1–3 oct 2026 · 2 noches · 2 adultos". */
export function stayLine(
  t: TFunction,
  lang: Lang,
  stay: { checkin: string; checkout: string; nights: number; adults: number; children: number },
): string {
  return [
    formatDateRange(stay.checkin, stay.checkout, lang),
    t('date.nights', { count: stay.nights }),
    guestsLabel(t, stay.adults, stay.children),
  ].join(' · ')
}

/** "30 sep" (a day of this stay, short). */
export function shortDay(value: string, lang: Lang): string {
  return formatDate(value, lang === 'en' ? 'MMM d' : 'd MMM', lang)
}
