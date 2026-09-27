import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatMoney } from '@/lib/format'
import {
  adjustment,
  adjustmentsSchema,
  fromAdjustmentValues,
  toAdjustmentValues,
  WEEKEND_PRESET,
  type AdjustmentValues,
} from '../../lib/adjustments'
import { WEEKDAY_KEYS, weekdayPrice } from '../../lib/plans'

/** Seven percentage inputs (Monday first), a weekend preset and a reset. Empty = no adjustment. */
export function WeekdayAdjustmentsInput({
  value,
  onChange,
  error,
  disabled = false,
}: {
  value: AdjustmentValues
  onChange: (value: AdjustmentValues) => void
  error?: string
  disabled?: boolean
}) {
  const { t, i18n } = useTranslation('rates')
  const id = useId()
  return (
    <fieldset className="grid gap-2" aria-describedby={error ? `${id}-error` : `${id}-hint`}>
      <legend className="mb-1 text-[13px] leading-5 font-semibold text-fg">{t('plans.adjustments.label')}</legend>
      <p id={`${id}-hint`} className="-mt-1 text-xs text-muted">
        {t('plans.adjustments.hint')}
      </p>
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
        {WEEKDAY_KEYS.map((key) => (
          <div key={key} className="grid gap-1">
            <span aria-hidden className="text-center text-2xs font-semibold tracking-wide text-muted uppercase">
              {t(`daysAbbr.${key}`)}
            </span>
            <div className="relative">
              <Input
                aria-label={t(`days.${key}`)}
                aria-invalid={Boolean(error) && Boolean(value[key]) && !adjustment.safeParse(value[key]).success}
                inputMode="decimal"
                autoComplete="off"
                disabled={disabled}
                placeholder="0"
                value={value[key]}
                onChange={(event) => onChange({ ...value, [key]: event.target.value })}
                className="num pr-5 text-right"
              />
              <span aria-hidden className="pointer-events-none absolute inset-y-0 right-2 flex items-center text-xs text-muted">
                %
              </span>
            </div>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5">
        <Button size="sm" variant="subtle" disabled={disabled} onClick={() => onChange({ ...value, ...WEEKEND_PRESET })}>
          {t('plans.adjustments.weekend')}
        </Button>
        <Button size="sm" variant="ghost" disabled={disabled} onClick={() => onChange(toAdjustmentValues(null))}>
          {t('plans.adjustments.clear')}
        </Button>
      </div>
      {error && (
        <p id={`${id}-error`} className="text-xs font-medium text-danger-ink" aria-live="polite">
          {i18n.exists(error) ? t(error) : error}
        </p>
      )}
    </fieldset>
  )
}

/**
 * "lun–jue $ 320.000 · vie–sáb $ 368.000 · dom $ 320.000": the price of each weekday once the adjustments
 * apply, grouping consecutive days that cost the same.
 */
export function WeekdayPreview({ price, adjustments, currency }: { price: string; adjustments: AdjustmentValues; currency: string }) {
  const { t } = useTranslation('rates')
  if (!/^\d+(\.\d{1,2})?$/.test(price)) return null
  const parsed = adjustmentsSchema.safeParse(adjustments)
  if (!parsed.success) return null
  const percentages = fromAdjustmentValues(adjustments)
  const prices = WEEKDAY_KEYS.map((_, weekday) => weekdayPrice(price, percentages, weekday, currency))
  const groups: { from: number; to: number; price: number }[] = []
  prices.forEach((value, weekday) => {
    const last = groups.at(-1)
    if (last && last.price === value) last.to = weekday
    else groups.push({ from: weekday, to: weekday, price: value })
  })
  const text = groups
    .map((group) => {
      const days =
        group.from === group.to
          ? t(`daysAbbr.${WEEKDAY_KEYS[group.from]}`)
          : `${t(`daysAbbr.${WEEKDAY_KEYS[group.from]}`)}–${t(`daysAbbr.${WEEKDAY_KEYS[group.to]}`)}`
      return `${days} ${formatMoney(group.price, currency)}`
    })
    .join(' · ')
  return (
    <p className="num rounded-md bg-surface-2 px-3 py-2 text-[13px] text-fg">
      <span className="eyebrow mr-2">{t('plans.adjustments.preview')}</span>
      <span>{text}</span>
    </p>
  )
}
