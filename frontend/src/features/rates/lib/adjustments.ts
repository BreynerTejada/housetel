import type { FieldError, FieldErrorsImpl, Merge } from 'react-hook-form'
import { z } from 'zod'
import type { WeekdayAdjustments, WeekdayKey } from '../api'
import { WEEKDAY_KEYS } from './plans'

/** Form values of the seven weekday percentage inputs (strings as typed; empty = no adjustment). */
export type AdjustmentValues = Record<WeekdayKey, string>

export const WEEKEND_PRESET: Partial<AdjustmentValues> = { fri: '15', sat: '15' }

function normalize(text: string): string {
  return text.trim().replace(',', '.')
}

/** Empty, or a percentage from -100 to 1000 with up to two decimals (comma or dot). */
export const adjustment = z.string().refine((value) => {
  const text = normalize(value)
  if (!text) return true
  if (!/^-?\d+(\.\d{1,2})?$/.test(text)) return false
  const number = Number(text)
  return number >= -100 && number <= 1000
}, 'rates:plans.adjustmentInvalid')

export const adjustmentsSchema = z.object({
  mon: adjustment,
  tue: adjustment,
  wed: adjustment,
  thu: adjustment,
  fri: adjustment,
  sat: adjustment,
  sun: adjustment,
})

export function toAdjustmentValues(adjustments?: WeekdayAdjustments | null): AdjustmentValues {
  return Object.fromEntries(
    WEEKDAY_KEYS.map((key) => {
      const value = adjustments?.[key]
      return [key, value ? String(value) : '']
    }),
  ) as AdjustmentValues
}

/** Form values → API mapping: only the adjusted days, as numbers (`{"fri": 15, "sat": 15}`). */
export function fromAdjustmentValues(values: AdjustmentValues): WeekdayAdjustments {
  const result: WeekdayAdjustments = {}
  for (const key of WEEKDAY_KEYS) {
    const text = normalize(values[key] ?? '')
    const number = Number(text)
    if (text && number) result[key] = number
  }
  return result
}

type AdjustmentErrors = Merge<FieldError, FieldErrorsImpl<AdjustmentValues>> | undefined

/** First validation message of the seven inputs. */
export function adjustmentError(errors: AdjustmentErrors): string | undefined {
  if (!errors) return undefined
  const messages = WEEKDAY_KEYS.map((key) => (errors as Record<string, { message?: string } | undefined>)[key]?.message)
  return messages.find(Boolean) ?? errors.message
}
