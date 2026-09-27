import { formatMoney, type Amount } from '@/lib/format'

/** Money strings from the API ("350000.00") as numbers; empty or invalid → 0. */
export function toNumber(value: Amount): number {
  const n = Number(value ?? 0)
  return Number.isFinite(n) ? n : 0
}

/** Integer cents, so sums of money strings never drift (0.10 + 0.20 = 30). */
export function toCents(value: Amount): number {
  return Math.round(toNumber(value) * 100)
}

/** Cents back to the API format ("350000.00"). */
export function fromCents(cents: number): string {
  return (cents / 100).toFixed(2)
}

/**
 * The amount as people type it in a confirmation box: grouped digits without the currency symbol
 * ("83.300" for COP, "1.234,50" for other currencies).
 */
export function plainAmount(value: Amount, currency = 'COP'): string {
  const digits = currency === 'COP' ? 0 : 2
  return new Intl.NumberFormat('es-CO', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(
    toNumber(value),
  )
}

/** Money inside sentences and button labels ("Pagar $ 350.000"): regular spaces, same format as MoneyText. */
export function moneyLabel(value: Amount, currency = 'COP'): string {
  return formatMoney(value, currency).replace(/\u00a0/g, ' ')
}

export type BalanceState = 'due' | 'settled' | 'credit'

/** Owed by the guest, settled, or in the guest's favor (a refund is due). */
export function balanceState(balance: Amount): BalanceState {
  const cents = toCents(balance)
  return cents > 0 ? 'due' : cents < 0 ? 'credit' : 'settled'
}

/** Total of a drawer count by denomination (`{"50000": 3}` → 150000). */
export function countDenominations(counts: Record<string, number>): number {
  return Object.entries(counts).reduce((sum, [value, count]) => sum + Number(value) * (count || 0), 0)
}

export type CashVerdict = { kind: 'exact' | 'over' | 'short'; amount: number }

/** Counted cash against the expected cash of the shift. */
export function cashVerdict(counted: number, expected: Amount): CashVerdict {
  const difference = Math.round(counted) - Math.round(toNumber(expected))
  if (difference === 0) return { kind: 'exact', amount: 0 }
  return { kind: difference > 0 ? 'over' : 'short', amount: Math.abs(difference) }
}
