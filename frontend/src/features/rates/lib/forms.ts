import { isApiError } from '@/lib/api'
import type { I18nText } from '../api'

/** First human message of a DRF error value (list, nested object or string). */
export function firstMessage(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map(firstMessage).find(Boolean) ?? ''
  if (value && typeof value === 'object') return Object.values(value).map(firstMessage).find(Boolean) ?? ''
  return ''
}

/**
 * Splits an API error into messages for form fields (`map`: API field → form field) and a general message
 * for everything that has no input of its own (domain errors, unknown fields). Non-API errors give `null`
 * so the caller can fall back to a generic text.
 */
export function fieldErrors(
  error: unknown,
  map: Record<string, string>,
): { fields: Record<string, string>; general: string | null } {
  if (!isApiError(error)) return { fields: {}, general: null }
  const fields: Record<string, string> = {}
  let unmatched = !error.fields
  for (const [field, value] of Object.entries(error.fields ?? {})) {
    const target = map[field]
    if (target) fields[target] = firstMessage(value)
    else unmatched = true
  }
  return { fields, general: unmatched ? error.message : null }
}

export function toI18n(es: string, en: string): I18nText {
  return { es: es.trim(), en: en.trim() }
}

export function i18nValue(value: I18nText | null | undefined): I18nText {
  return { es: value?.es ?? '', en: value?.en ?? '' }
}

/** A decimal typed with comma or dot ("1,5" → "1.5"; up to 2 decimals); `null` when invalid. */
export function parseDecimal(typed: string, { signed = true }: { signed?: boolean } = {}): string | null {
  const text = typed.trim().replace(',', '.')
  const pattern = signed ? /^-?\d+(\.\d{1,2})?$/ : /^\d+(\.\d{1,2})?$/
  return pattern.test(text) ? text : null
}
