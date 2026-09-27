import { formatNumber, type Lang } from '@/lib/format'
import type { DerivationType, RatePlan, Season, WeekdayAdjustments, WeekdayKey } from '../api'

export const WEEKDAY_KEYS: readonly WeekdayKey[] = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

/** Sales channels a plan can be limited to (`[]` = all): direct sales, Housetel's own channels and the OTA
 * codes of the channel manager (incl. its simulators). Unknown codes are kept as they come. */
export const KNOWN_CHANNELS = ['direct', 'marketplace', 'booking_engine', 'booksim', 'airsim'] as const

// ---- Money: exact integer arithmetic in cents, rounded half up like `core.money.quantize` -------------

const toCents = (value: string | number) => Math.round(Number(value) * 100)

/** `numerator / denominator` rounded half up (both non-negative integers). */
function roundDiv(numerator: number, denominator: number): number {
  return Math.floor((2 * numerator + denominator) / (2 * denominator))
}

/** Cents → the currency amount (COP: whole pesos, others: two decimals), rounded half up. */
function fromCents(cents: number, currency: string): number {
  if (cents <= 0) return 0
  return currency === 'COP' ? roundDiv(cents, 100) : roundDiv(cents, 1) / 100
}

/** `price × (1 + percent/100)` never below zero, rounded to the currency. */
export function applyPercent(price: string | number, percent: string | number, currency = 'COP'): number {
  const basisPoints = Math.round(Number(percent) * 100) // percent with up to two decimals
  const factor = 10000 + basisPoints
  if (factor <= 0) return 0
  const cents = toCents(price)
  return currency === 'COP' ? roundDiv(cents * factor, 1_000_000) : roundDiv(cents * factor, 10_000) / 100
}

/**
 * Price of a derived plan from its base plan's price (same rule as the quote engine): a percentage or an
 * amount, never below zero, rounded to the currency.
 */
export function derivedPrice(
  price: string | number,
  plan: { derivation_type: DerivationType; derivation_value: string },
  currency = 'COP',
): number {
  if (plan.derivation_type === 'amount') return fromCents(toCents(price) + toCents(plan.derivation_value), currency)
  return applyPercent(price, plan.derivation_value, currency)
}

// ---- Plans ---------------------------------------------------------------------------------------------

export interface PlanFamily {
  base: RatePlan
  derived: RatePlan[]
}

const byOrder = (a: RatePlan, b: RatePlan) => a.sort_order - b.sort_order || a.code.localeCompare(b.code)

/** Every base plan (sort order, then code) with the derived plans that follow it. */
export function planFamilies(plans: RatePlan[]): PlanFamily[] {
  return plans
    .filter((plan) => plan.kind === 'base')
    .sort(byOrder)
    .map((base) => ({ base, derived: plans.filter((plan) => plan.parent === base.id).sort(byOrder) }))
}

// ---- Weekday adjustments (`{"fri": 15, "sat": 15}`, percentages) -----------------------------------------

/** Adjusted weekdays in week order (Monday first), without zeros. */
export function adjustmentEntries(adjustments: WeekdayAdjustments | null | undefined): [WeekdayKey, number][] {
  return WEEKDAY_KEYS.flatMap((key) => {
    const value = Number(adjustments?.[key] ?? 0)
    return value ? ([[key, value]] as [WeekdayKey, number][]) : []
  })
}

/** Price of a weekday (Monday = 0) with its adjustment, like the quote engine. */
export function weekdayPrice(price: string | number, adjustments: WeekdayAdjustments | null | undefined, weekday: number, currency = 'COP') {
  return applyPercent(price, adjustments?.[WEEKDAY_KEYS[weekday]] ?? 0, currency)
}

/** "+15 %" / "−10 %" (true minus sign), with the decimal separator of the language on screen. */
export function signedPercent(value: number, lang: Lang = 'es'): string {
  return `${value < 0 ? '−' : '+'}${formatNumber(Math.abs(value), lang)} %`
}

// ---- Seasons and the year calendar -------------------------------------------------------------------------

/** The season that prices `day` (`YYYY-MM-DD`): end dates are inclusive; highest priority, then latest start. */
export function seasonOn(seasons: Season[], day: string): Season | null {
  let best: Season | null = null
  for (const season of seasons) {
    if (day < season.start_date || day > season.end_date) continue
    if (
      !best ||
      season.priority > best.priority ||
      (season.priority === best.priority && season.start_date > best.start_date) ||
      (season.priority === best.priority && season.start_date === best.start_date && season.id < best.id)
    ) {
      best = season
    }
  }
  return best
}

const pad = (value: number) => String(value).padStart(2, '0')

/** Cells of a month (`month` 0–11) for a Monday-first grid: `null` before the 1st, then `YYYY-MM-DD` days. */
export function monthCells(year: number, month: number): (string | null)[] {
  const leading = (new Date(year, month, 1).getDay() + 6) % 7
  const days = new Date(year, month + 1, 0).getDate()
  return [
    ...Array.from({ length: leading }, () => null),
    ...Array.from({ length: days }, (_, index) => `${year}-${pad(month + 1)}-${pad(index + 1)}`),
  ]
}
