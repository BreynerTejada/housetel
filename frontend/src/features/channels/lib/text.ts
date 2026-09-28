import type { I18nText } from '../api'

/** The text in `lang`, then Spanish, then any language (backend `apps.core.i18n.t`). */
export function tr(value: I18nText | null | undefined, lang: string): string {
  if (!value) return ''
  if (typeof value === 'string') return value
  const key = lang.startsWith('en') ? 'en' : 'es'
  return value[key] || value.es || value.en || Object.values(value).find(Boolean) || ''
}
