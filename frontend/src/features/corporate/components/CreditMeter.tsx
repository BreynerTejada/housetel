import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { moneyLabel, toCents } from '@/features/finance/money'
import type { CreditStatus } from '../api'

const TONES = {
  ok: { fill: 'bg-accent', track: 'bg-accent-soft', text: 'text-muted' },
  high: { fill: 'bg-warning', track: 'bg-warning-soft', text: 'text-warning-ink' },
  over: { fill: 'bg-danger', track: 'bg-danger-soft', text: 'text-danger-ink' },
} as const

/**
 * Credit used against the limit (cupo) in the whole organization. The fill carries the severity (accent → warning
 * at 75 % → danger over the limit) on a lighter track of the same hue; the sentence under it says the numbers.
 */
export function CreditMeter({ credit, currency = 'COP', className }: { credit: CreditStatus; currency?: string; className?: string }) {
  const { t } = useTranslation('corporate')
  if (!credit.enabled) {
    return <p className={cn('text-[13px] text-muted', className)}>{t('credit.disabled')}</p>
  }
  const used = Math.max(0, toCents(credit.used))
  if (credit.limit === null) {
    return (
      <p className={cn('text-[13px] text-muted', className)}>
        {t('credit.noLimit', { used: moneyLabel(credit.used, currency), days: credit.terms_days })}
      </p>
    )
  }
  const limit = Math.max(1, toCents(credit.limit))
  const ratio = used / limit
  const tone = credit.over_limit ? TONES.over : ratio >= 0.75 ? TONES.high : TONES.ok
  return (
    <div className={cn('grid gap-1.5', className)}>
      <div
        role="meter"
        aria-label={t('credit.meterLabel')}
        aria-valuemin={0}
        aria-valuemax={limit / 100}
        aria-valuenow={Math.min(used, limit) / 100}
        aria-valuetext={t('credit.usedOf', { used: moneyLabel(credit.used, currency), limit: moneyLabel(credit.limit, currency) })}
        className={cn('h-1.5 overflow-hidden rounded-full', tone.track)}
      >
        <div className={cn('h-full rounded-full transition-[width] duration-500', tone.fill)} style={{ width: `${Math.min(1, ratio) * 100}%` }} />
      </div>
      <p className={cn('flex flex-wrap justify-between gap-x-3 text-xs', tone.text)}>
        <span>{t('credit.usedOf', { used: moneyLabel(credit.used, currency), limit: moneyLabel(credit.limit, currency) })}</span>
        <span>
          {credit.over_limit
            ? t('credit.over', { amount: moneyLabel(String(-(toCents(credit.available ?? '0') / 100)), currency) })
            : t('credit.available', { amount: moneyLabel(credit.available ?? '0', currency), days: credit.terms_days })}
        </span>
      </p>
    </div>
  )
}
