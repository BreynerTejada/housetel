import type { TFunction } from 'i18next'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import i18n from '@/lib/i18n'

/**
 * One sentence for the guest, in the portal's language: known backend codes have their own translation
 * (the API's `detail` is Spanish); anything else falls back to the app-wide message.
 */
export function portalError(error: unknown, t: TFunction): string {
  if (isApiError(error)) {
    const key = `guestportal:errors.${error.code}`
    if (i18n.exists(key)) return t(key)
    if (error.status === 429) return t('guestportal:errors.throttled')
  }
  return errorMessage(error, t)
}

/** Field errors of a validation response (`{"guests.0.first_name": ["…"]}`), first message per field. */
export function fieldErrors(error: unknown): Record<string, string> {
  if (!isApiError(error) || !error.fields) return {}
  return Object.fromEntries(Object.entries(error.fields).map(([field, messages]) => [field, messages[0] ?? '']))
}
