import { formatMoney, type Amount } from '@/lib/format'

const NBSP = new RegExp(String.fromCharCode(160), 'g') // Intl puts no-break spaces around the symbol

/** Money inside sentences and button labels ("Pagar $ 350.000"): plain spaces, same format as MoneyText. */
export function moneyLabel(value: Amount, currency = 'COP'): string {
  return formatMoney(value, currency).replace(NBSP, ' ')
}
