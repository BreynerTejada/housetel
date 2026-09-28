import { useTranslation } from 'react-i18next'
import { MoneyText } from '@/components/Money'
import { Tooltip } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import { moneyLabel, toCents } from '@/features/finance/money'
import { AGING_KEYS, type Aging } from '../api'
import { AGING_FILL } from '../lib/aging'

/**
 * The receivables' age as one ribbon: segments proportional to what is owed in each band (0–30, 31–60, 61–90,
 * 90+ days since the document), 2px surface gaps between them. `variant="mini"` is the thin bar for list rows
 * (no legend: the row shows the figures).
 */
export function AgingRibbon({
  aging,
  currency = 'COP',
  variant = 'full',
  className,
}: {
  aging: Aging
  currency?: string
  variant?: 'full' | 'mini'
  className?: string
}) {
  const { t } = useTranslation('corporate')
  const cents = AGING_KEYS.map((key) => Math.max(0, toCents(aging[key])))
  const total = cents.reduce((sum, value) => sum + value, 0)
  const summary = AGING_KEYS.map((key) => `${t(`aging.${key}`)}: ${moneyLabel(aging[key], currency)}`).join(' · ')
  const mini = variant === 'mini'

  return (
    <div className={cn('grid min-w-0 grid-cols-1 gap-3', className)}>
      <div
        role="img"
        aria-label={t('aging.ribbonLabel', { summary })}
        className={cn('flex w-full gap-[2px] overflow-hidden rounded-[4px] bg-surface-2', mini ? 'h-1.5' : 'h-3')}
      >
        {total > 0 &&
          AGING_KEYS.map((key, index) => {
            const share = cents[index]! / total
            if (share <= 0) return null
            return (
              <Tooltip key={key} content={`${t(`aging.${key}`)} · ${moneyLabel(aging[key], currency)}`}>
                <span
                  className={cn('h-full min-w-[3px] transition-[flex-grow] duration-500 first:rounded-l-[4px] last:rounded-r-[4px]', AGING_FILL[key])}
                  style={{ flexGrow: share, flexBasis: 0 }}
                />
              </Tooltip>
            )
          })}
      </div>
      {!mini && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
          {AGING_KEYS.map((key) => (
            <div key={key} className="grid min-w-0 gap-0.5">
              <dt className="flex items-center gap-1.5 text-xs text-muted">
                <span aria-hidden className={cn('size-2 shrink-0 rounded-[2px]', AGING_FILL[key])} />
                <span className="truncate">{t(`aging.${key}`)}</span>
              </dt>
              <dd className={cn('text-sm font-semibold', toCents(aging[key]) === 0 && 'text-subtle')}>
                <MoneyText value={aging[key]} currency={currency} />
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
