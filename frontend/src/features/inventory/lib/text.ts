import type { I18nText } from '../api'

/** The text in `lang`, then Spanish, then any language (backend `apps.core.i18n.t`). */
export function tr(value: I18nText | string | null | undefined, lang: string): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  const key = lang.startsWith('en') ? 'en' : 'es'
  return value[key] || value.es || value.en || ''
}

/** Natural order for labels like "C2" < "C10" and room numbers like "99" < "101". */
export const naturalCompare = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' }).compare
