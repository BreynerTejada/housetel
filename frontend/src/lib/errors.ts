import type { TFunction } from 'i18next'
import { ApiError } from './api'

const GENERIC_DETAIL = /^HTTP \d{3}$/

/**
 * One sentence for the user. Backend errors already carry a Spanish `detail`; network failures,
 * suspended organizations and permission errors get a clear fallback, anything else a generic one.
 */
export function errorMessage(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    if (error.code === 'network_error') return t('errors.network', { ns: 'common' })
    if (error.message && !GENERIC_DETAIL.test(error.message)) return error.message
    if (error.status === 402) return t('errors.suspended', { ns: 'common' })
    if (error.status === 403) return t('errors.forbidden', { ns: 'common' })
    if (error.status === 404) return t('errors.notFound', { ns: 'common' })
  }
  return t('errors.generic', { ns: 'common' })
}
