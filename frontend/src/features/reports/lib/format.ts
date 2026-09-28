import { formatDate, formatMoney, formatNumber, formatPercent, type Lang } from '@/lib/format'
import type { ReportColumn } from '../api'

const DASH = '—'
const LOCALE: Record<Lang, string> = { es: 'es-CO', en: 'en-US' }

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

/**
 * Money as the whole app shows it: "$ 470.115" — the peso's own format (es-CO) in both UI languages, like
 * folios, invoices and the PDF exports. `lang` is accepted for symmetry with the other formatters.
 */
export function money(value: unknown, currency: string, _lang?: Lang): string {
  const n = toNumber(value)
  if (n === null) return DASH
  return formatMoney(n, currency)
}

/**
 * Compact money for stat tiles and axis ticks, in the same peso format: "$ 196,5 M", "$ 470 mil". Below `from`
 * the full amount is kept, so ADR and RevPAR stay exact in the tiles. Thousands of millions keep the "M"
 * ("$ 4.200 M"), never the ambiguous billion.
 */
export function compactMoney(value: unknown, currency: string, lang: Lang, from = 1_000_000): string {
  const n = toNumber(value)
  if (n === null) return DASH
  const abs = Math.abs(n)
  if (abs < from) return money(n, currency, lang)
  const sign = n < 0 ? '-' : ''
  const symbol = currency === 'COP' || currency === 'USD' ? '$' : currency
  const format = (amount: number, digits: number) => formatNumber(amount, 'es', digits)
  if (abs >= 1e6) return `${sign}${symbol} ${format(abs / 1e6, abs >= 1e9 ? 0 : 1)} M`
  return `${sign}${symbol} ${format(abs / 1e3, 0)} ${lang === 'en' ? 'k' : 'mil'}`
}

/** Axis tick for a value type (short: "$ 5 M", "72 %", "1.200"). */
export function tickValue(value: number, type: 'money' | 'percent' | 'number', currency: string, lang: Lang): string {
  if (type === 'percent') return formatPercent(value, 0, lang)
  if (type === 'money') return compactMoney(value, currency, lang, 1_000)
  return formatNumber(value, lang, 1)
}

/** Full value for tooltips, tables and KPI tiles (money compacted from 10 M in tiles only). */
export function chartValue(value: unknown, type: 'money' | 'percent' | 'number', currency: string, lang: Lang): string {
  const n = toNumber(value)
  if (n === null) return DASH
  if (type === 'percent') return formatPercent(n, 1, lang)
  if (type === 'money') return money(n, currency, lang)
  return formatNumber(n, lang, 1)
}

/** "1 sep" / "Sep 1" (chart axes), "sep 26" / "Sep 26" for months. */
export function shortDate(value: string, kind: 'date' | 'month', lang: Lang): string {
  if (kind === 'month') return formatDate(value, lang === 'en' ? 'MMM yy' : 'MMM yy', lang)
  return formatDate(value, lang === 'en' ? 'MMM d' : 'd MMM', lang)
}

/** "lun 1 sep 2026" / "Mon, Sep 1, 2026" (tooltips). */
export function longDate(value: string, kind: 'date' | 'month', lang: Lang): string {
  if (kind === 'month') return formatDate(value, 'MMMM yyyy', lang)
  return formatDate(value, lang === 'en' ? 'EEE, MMM d, yyyy' : 'EEE d MMM yyyy', lang)
}

const regionNames = new Map<Lang, Intl.DisplayNames | null>()
/** Country name in the UI language (ISO-2 → "Estados Unidos"); the code when the browser can't name it. */
export function countryName(code: unknown, lang: Lang, unknown: string): string {
  if (typeof code !== 'string' || !code) return unknown
  if (!regionNames.has(lang)) {
    try {
      regionNames.set(lang, new Intl.DisplayNames([LOCALE[lang]], { type: 'region' }))
    } catch {
      regionNames.set(lang, null)
    }
  }
  try {
    return regionNames.get(lang)?.of(code.toUpperCase()) ?? code.toUpperCase()
  } catch {
    return code.toUpperCase()
  }
}

/** Plain text of a table cell (used for search, sorting of labels and the chart table view). */
export function cellText(
  value: unknown,
  column: ReportColumn,
  ctx: { currency: string; lang: Lang; yes: string; no: string; unknown: string },
): string {
  if (value === null || value === undefined || value === '') return ''
  switch (column.type) {
    case 'money':
      return money(value, ctx.currency, ctx.lang)
    case 'percent': {
      const n = toNumber(value)
      return n === null ? '' : formatPercent(n, 1, ctx.lang)
    }
    case 'number': {
      const n = toNumber(value)
      return n === null ? '' : formatNumber(n, ctx.lang, 1)
    }
    case 'date':
      return formatDate(String(value), undefined, ctx.lang)
    case 'month':
      return formatDate(String(value), 'MMMM yyyy', ctx.lang)
    case 'datetime':
      return formatDate(String(value), ctx.lang === 'en' ? 'MMM d, yyyy HH:mm' : 'd MMM yyyy HH:mm', ctx.lang)
    case 'boolean':
      return value ? ctx.yes : ctx.no
    case 'country':
      return countryName(value, ctx.lang, ctx.unknown)
    case 'status':
    case 'code':
      return column.labels?.[String(value)] ?? String(value)
    default:
      return String(value)
  }
}

/** Sortable value of a cell: numbers for amounts, ISO strings for dates, labels for codes. */
export function sortValue(value: unknown, column: ReportColumn, lang: Lang): string | number {
  if (value === null || value === undefined || value === '') return column.type === 'money' || column.type === 'number' || column.type === 'percent' ? Number.NEGATIVE_INFINITY : ''
  if (column.type === 'money' || column.type === 'number' || column.type === 'percent') return toNumber(value) ?? Number.NEGATIVE_INFINITY
  if (column.type === 'status' || column.type === 'code') return column.labels?.[String(value)] ?? String(value)
  if (column.type === 'country') return countryName(value, lang, '')
  if (column.type === 'boolean') return value ? 1 : 0
  return String(value)
}

export const isNumericColumn = (column: ReportColumn) =>
  column.type === 'money' || column.type === 'number' || column.type === 'percent'
