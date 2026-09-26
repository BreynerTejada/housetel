import { useLayoutEffect, useMemo, useRef, useState, type ChangeEvent, type ComponentProps } from 'react'
import { formatMoney, type Amount } from '@/lib/format'
import { cn } from '@/lib/utils'
import { fieldBase } from './ui/input'

const LOCALE = 'es-CO'
const DECIMAL_SEPARATOR = ','

function decimalsFor(currency: string): number {
  return currency === 'COP' ? 0 : 2
}

function group(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
}

function currencySymbol(currency: string): string {
  try {
    return new Intl.NumberFormat(LOCALE, { style: 'currency', currency }).formatToParts(0).find((p) => p.type === 'currency')?.value ?? '$'
  } catch {
    return '$'
  }
}

/** API string ("350000.00") → what the field shows ("350.000"). */
function toDisplay(value: string, decimals: number): string {
  if (value === '' || value === null || value === undefined) return ''
  const n = Number(value)
  if (!Number.isFinite(n)) return ''
  if (decimals === 0) return group(String(Math.round(Math.abs(n))))
  const [int = '0', dec] = String(Math.abs(n)).split('.')
  return dec ? `${group(int)}${DECIMAL_SEPARATOR}${dec.slice(0, decimals)}` : group(int)
}

/** What the user typed → `{ display, raw }`, where `raw` is the API string ("1234.5"). */
function parseTyped(text: string, decimals: number): { display: string; raw: string } {
  if (decimals === 0) {
    const digits = text.replace(/\D/g, '').replace(/^0+(?=\d)/, '')
    return { display: group(digits), raw: digits }
  }
  const [intPart = '', ...rest] = text.split(DECIMAL_SEPARATOR)
  const int = intPart.replace(/\D/g, '').replace(/^0+(?=\d)/, '')
  const hasDecimal = rest.length > 0
  const dec = rest.join('').replace(/\D/g, '').slice(0, decimals)
  const intOrZero = int || (hasDecimal ? '0' : '')
  return {
    display: hasDecimal ? `${group(intOrZero)}${DECIMAL_SEPARATOR}${dec}` : group(int),
    raw: dec ? `${intOrZero}.${dec}` : intOrZero,
  }
}

/** Counts the characters that carry meaning (digits and the decimal separator). */
function meaningfulBefore(text: string, caret: number): number {
  return text.slice(0, caret).replace(/[^\d,]/g, '').length
}

function caretFor(display: string, meaningful: number): number {
  let seen = 0
  for (let i = 0; i < display.length; i++) {
    if (seen === meaningful) return i
    if (/[\d,]/.test(display[i] ?? '')) seen++
  }
  return display.length
}

export interface MoneyInputProps extends Omit<ComponentProps<'input'>, 'value' | 'onChange' | 'type'> {
  /** API decimal string (`"350000.00"`, `"350000"`) or `''`. */
  value: string
  /** Receives the API string: `"350000"` for COP, `"1234.5"` for other currencies, `''` when empty. */
  onChange: (value: string) => void
  currency?: string
}

/** Money field: COP shows whole pesos with thousands separators ("$ 350.000"). */
export function MoneyInput({ value, onChange, currency = 'COP', className, ...props }: MoneyInputProps) {
  const decimals = decimalsFor(currency)
  const symbol = useMemo(() => currencySymbol(currency), [currency])
  const inputRef = useRef<HTMLInputElement>(null)
  const pendingCaret = useRef<number | null>(null)
  const [display, setDisplay] = useState(() => toDisplay(value, decimals))
  const [syncedValue, setSyncedValue] = useState(value)

  // Values that come from outside (form reset, server data) replace what is shown,
  // unless the field already shows that amount (e.g. "1.234," while typing decimals).
  if (value !== syncedValue) {
    setSyncedValue(value)
    if (parseTyped(display, decimals).raw !== value) setDisplay(toDisplay(value, decimals))
  }

  useLayoutEffect(() => {
    const input = inputRef.current
    if (input && pendingCaret.current !== null && document.activeElement === input) {
      input.setSelectionRange(pendingCaret.current, pendingCaret.current)
      pendingCaret.current = null
    }
  })

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    const text = event.target.value
    const meaningful = meaningfulBefore(text, event.target.selectionStart ?? text.length)
    const next = parseTyped(text, decimals)
    pendingCaret.current = caretFor(next.display, meaningful)
    setDisplay(next.display)
    setSyncedValue(next.raw)
    onChange(next.raw)
  }

  return (
    <div className={cn('relative', className)}>
      <span aria-hidden className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-sm text-muted">
        {symbol}
      </span>
      <input
        ref={inputRef}
        type="text"
        inputMode={decimals ? 'decimal' : 'numeric'}
        autoComplete="off"
        value={display}
        onChange={handleChange}
        className={cn(fieldBase, 'num h-9 pr-3 pl-7 text-right text-sm')}
        {...props}
      />
    </div>
  )
}

export interface MoneyTextProps extends ComponentProps<'span'> {
  value: Amount
  currency?: string
  /** Negative amounts in the danger color (balances, refunds). */
  highlightNegative?: boolean
}

export function MoneyText({ value, currency = 'COP', highlightNegative = false, className, ...props }: MoneyTextProps) {
  const negative = highlightNegative && Number(value) < 0
  return (
    <span className={cn('num whitespace-nowrap', negative && 'text-danger-ink', className)} {...props}>
      {formatMoney(value, currency)}
    </span>
  )
}
