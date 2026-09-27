import { formatMoney, formatNumber, type Lang } from '@/lib/format'
import type { I18nText, RateSource } from '../api'

/** Text of a translatable field in `lang`, falling back to Spanish and then to any non-empty value. */
export function pick(text: I18nText | null | undefined, lang: Lang): string {
  if (!text) return ''
  return text[lang] || text.es || text.en || ''
}

/** "−12 %" or "+ $ 35.000": how a derived plan is computed from its base plan (numbers as `lang` writes them). */
export function derivationLabel(type: 'percent' | 'amount', value: string, currency = 'COP', lang: Lang = 'es'): string {
  const amount = Number(value)
  const sign = amount < 0 ? '−' : '+'
  if (type === 'percent') return `${sign}${formatNumber(Math.abs(amount), lang)} %`
  return `${sign} ${formatMoney(Math.abs(amount), currency)}`
}

/** Color of the "ink" stroke that tells where a nightly price comes from (defaults carry none). */
export const SOURCE_INK: Record<RateSource, string | null> = {
  default: null,
  none: null,
  season: 'var(--warning)',
  manual: 'var(--accent)',
  revenue: 'var(--info)',
  bulk: 'var(--success)',
  channel: 'var(--stone)',
}

export const LEGEND_SOURCES: RateSource[] = ['default', 'season', 'manual', 'bulk', 'revenue', 'channel']
