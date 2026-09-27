import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { MoneyText } from '@/components/Money'
import { Input } from '@/components/ui/input'
import { moneyLabel } from '../money'

/** Colombian peso bills and coins in circulation, largest first. */
const BILLS = [100000, 50000, 20000, 10000, 5000, 2000]
const COINS = [1000, 500, 200, 100, 50]

/**
 * The drawer count sheet (arqueo): one row per bill and coin with how many there are and the subtotal.
 * `counts` maps the denomination (as a string, like the API) to a whole number.
 */
export function CashCount({
  counts,
  onChange,
  currency,
}: {
  counts: Record<string, number>
  onChange: (counts: Record<string, number>) => void
  currency: string
}) {
  const { t } = useTranslation('finance')
  const ids = useId()

  function set(value: number, raw: string) {
    const digits = raw.replace(/\D/g, '').slice(0, 5)
    const next = { ...counts }
    if (digits === '') delete next[String(value)]
    else next[String(value)] = Number(digits)
    onChange(next)
  }

  const group = (title: string, values: number[], labelKey: 'cashier.bills' | 'cashier.coins') => (
    <fieldset className="grid gap-1.5">
      <legend className="eyebrow mb-1">{title}</legend>
      {values.map((value) => {
        const id = `${ids}-${value}`
        const count = counts[String(value)] ?? 0
        return (
          <div key={value} className="grid grid-cols-[1fr_5rem_7rem] items-center gap-3">
            <label htmlFor={id} className="num text-sm font-semibold text-fg">
              {moneyLabel(value, currency)}
            </label>
            <Input
              id={id}
              aria-label={t(labelKey, { value: moneyLabel(value, currency) })}
              name={`count_${value}`}
              inputMode="numeric"
              autoComplete="off"
              value={counts[String(value)] === undefined ? '' : String(counts[String(value)])}
              onChange={(event) => set(value, event.target.value)}
              placeholder="0"
              className="num h-8 text-right"
            />
            <span className="text-right text-sm text-muted">
              {count > 0 ? <MoneyText value={count * value} currency={currency} /> : '—'}
            </span>
          </div>
        )
      })}
    </fieldset>
  )

  return (
    <div className="grid gap-5 sm:grid-cols-2 sm:gap-8">
      {group(t('cashier.billsTitle'), BILLS, 'cashier.bills')}
      {group(t('cashier.coinsTitle'), COINS, 'cashier.coins')}
    </div>
  )
}
