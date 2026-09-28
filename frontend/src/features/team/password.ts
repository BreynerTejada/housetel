import { isApiError } from '@/lib/api'

/** Django's MinimumLengthValidator (backend AUTH_PASSWORD_VALIDATORS). */
export const MIN_PASSWORD = 8

export interface PasswordCheck {
  length: boolean
  notOnlyNumbers: boolean
  matches: boolean
}

/**
 * What the browser can check before sending. The backend also rejects common passwords and ones too close
 * to the name or email; those messages come back under the field (already in the user's language).
 */
export function checkPassword(password: string, confirm: string): PasswordCheck {
  return {
    length: password.length >= MIN_PASSWORD,
    notOnlyNumbers: password.length > 0 && !/^\d+$/.test(password),
    matches: confirm.length > 0 && password === confirm,
  }
}

/** Server messages for one field (`fields.new_password`), joined for a single error line. */
export function fieldMessages(error: unknown, field: string): string | null {
  if (!isApiError(error)) return null
  const messages = error.fields?.[field]
  return messages?.length ? messages.join(' ') : null
}

export function isThrottled(error: unknown): boolean {
  return isApiError(error) && (error.status === 429 || error.code === 'throttled')
}
