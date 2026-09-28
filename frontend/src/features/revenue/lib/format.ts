import { formatNumber, type Lang } from '@/lib/format'

/** A translatable API field (`{"es": …, "en": …}`). */
export interface I18nText {
  es: string
  en: string
}

export const MINUS = '−'

/** Text of a translated field in `lang`, falling back to Spanish and then to any non-empty value. */
export function pick(text: I18nText | null | undefined, lang: Lang): string {
  if (!text) return ''
  return text[lang] || text.es || text.en || ''
}

/**
 * "+12 %", "−4,25 %" (true minus, decimals as `lang` writes them); `{ unit: false }` → "+12" for heatmap cells.
 * Same shape as the percentages of the rates screens.
 */
export function signedPercent(value: string | number, lang: Lang, { unit = true }: { unit?: boolean } = {}): string {
  const amount = Number(value)
  const sign = amount > 0 ? '+' : amount < 0 ? MINUS : ''
  const body = formatNumber(Math.abs(amount), lang, 2)
  return unit ? `${sign}${body} %` : `${sign}${body}`
}

const SCALES = {
  es: [
    { min: 1e6, suffix: ' M' },
    { min: 1e3, suffix: ' mil' },
  ],
  en: [
    { min: 1e9, suffix: 'B' },
    { min: 1e6, suffix: 'M' },
    { min: 1e3, suffix: 'K' },
  ],
} as const

/**
 * Money for stat tiles: "$ 2,4 M" / "$2.4M", "−$ 4,8 M", "$ 950 mil" / "$950K". Spanish counts in millions
 * (never "mil millones"), English goes up to billions. Deterministic (no ICU compact notation).
 */
export function compactMoney(value: string | number, lang: Lang): string {
  const amount = Number(value)
  const sign = amount < 0 ? MINUS : ''
  const absolute = Math.abs(amount)
  const scale = SCALES[lang].find((item) => absolute >= item.min)
  const body = scale
    ? `${formatNumber(absolute / scale.min, lang, absolute / scale.min >= 100 ? 0 : 1)}${scale.suffix}`
    : formatNumber(absolute, lang, 0)
  return lang === 'es' ? `${sign}$ ${body}` : `${sign}$${body}`
}
