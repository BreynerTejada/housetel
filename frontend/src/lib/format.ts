import { differenceInCalendarDays, format as formatWithPattern, formatDistance, isValid, parseISO } from 'date-fns'
import { enUS, es } from 'date-fns/locale'

export type Lang = 'es' | 'en'
export type Amount = string | number | null | undefined
/** API dates are `YYYY-MM-DD` (calendar days); datetimes are ISO-8601 with offset. */
export type DateInput = string | Date | null | undefined

const DASH = '—'
const DATE_LOCALES = { es, en: enUS } as const
const NUMBER_LOCALES: Record<Lang, string> = { es: 'es-CO', en: 'en-US' }
const DEFAULT_DATE_PATTERN: Record<Lang, string> = { es: 'd MMM yyyy', en: 'MMM d, yyyy' }

const numberFormats = new Map<string, Intl.NumberFormat>()
function numberFormat(locale: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = `${locale}|${JSON.stringify(options)}`
  let nf = numberFormats.get(key)
  if (!nf) {
    nf = new Intl.NumberFormat(locale, options)
    numberFormats.set(key, nf)
  }
  return nf
}

function toNumber(value: Amount): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

export function normalizeLang(lang: string | undefined | null): Lang {
  return lang?.toLowerCase().startsWith('en') ? 'en' : 'es'
}

/** Money comes from the API as a decimal string ("350000.00"). COP shows whole pesos. */
export function formatMoney(value: Amount, currency = 'COP', locale = 'es-CO'): string {
  const n = toNumber(value)
  if (n === null) return DASH
  const digits = currency === 'COP' ? 0 : 2
  return numberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(n)
}

export function formatNumber(value: number, lang: Lang = 'es', maximumFractionDigits = 2): string {
  return numberFormat(NUMBER_LOCALES[lang], { maximumFractionDigits }).format(value)
}

/** `points` are percentage points (72.5 → "72,5 %"), which is how the API reports KPIs. */
export function formatPercent(points: number, digits = 1, lang: Lang = 'es'): string {
  return numberFormat(NUMBER_LOCALES[lang], {
    style: 'percent',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(points / 100)
}

/** Parses API dates as local calendar days (never UTC midnight). */
export function parseDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === '') return null
  const date = value instanceof Date ? value : parseISO(value)
  return isValid(date) ? date : null
}

/** Serializes the local calendar day as `YYYY-MM-DD` for API payloads. */
export function toISODate(value: Date): string {
  return formatWithPattern(value, 'yyyy-MM-dd')
}

export function formatDate(value: DateInput, pattern?: string, lang: Lang = 'es'): string {
  const date = parseDate(value)
  if (!date) return DASH
  return formatWithPattern(date, pattern ?? DEFAULT_DATE_PATTERN[lang], { locale: DATE_LOCALES[lang] })
}

export function formatDateRange(start: DateInput, end: DateInput, lang: Lang = 'es'): string {
  const s = parseDate(start)
  const e = parseDate(end)
  if (!s || !e) return DASH
  const fmt = (d: Date, pattern: string) => formatWithPattern(d, pattern, { locale: DATE_LOCALES[lang] })
  if (differenceInCalendarDays(e, s) === 0) return formatDate(s, undefined, lang)
  const sameYear = s.getFullYear() === e.getFullYear()
  const sameMonth = sameYear && s.getMonth() === e.getMonth()
  if (lang === 'en') {
    if (sameMonth) return `${fmt(s, 'MMM d')}–${fmt(e, 'd, yyyy')}`
    if (sameYear) return `${fmt(s, 'MMM d')} – ${fmt(e, 'MMM d, yyyy')}`
    return `${fmt(s, 'MMM d, yyyy')} – ${fmt(e, 'MMM d, yyyy')}`
  }
  if (sameMonth) return `${fmt(s, 'd')}–${fmt(e, 'd MMM yyyy')}`
  if (sameYear) return `${fmt(s, 'd MMM')} – ${fmt(e, 'd MMM yyyy')}`
  return `${fmt(s, 'd MMM yyyy')} – ${fmt(e, 'd MMM yyyy')}`
}

/** Nights of a stay: checkin inclusive, checkout exclusive. */
export function nightsBetween(checkin: DateInput, checkout: DateInput): number {
  const s = parseDate(checkin)
  const e = parseDate(checkout)
  if (!s || !e) return 0
  return Math.max(0, differenceInCalendarDays(e, s))
}

export function formatRelative(value: DateInput, lang: Lang = 'es', now: Date = new Date()): string {
  const date = parseDate(value)
  if (!date) return DASH
  return formatDistance(date, now, { addSuffix: true, locale: DATE_LOCALES[lang] })
}
