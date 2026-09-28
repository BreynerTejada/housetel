import { Check, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { LEGEND_STEPS, STEP_CLASS, STEP_LIMITS, STEP_RING, type Step } from '../lib/scale'

/** Key of the diverging scale (lower ← no change → raise) and of the decided states. */
export function HeatmapLegend() {
  const { t } = useTranslation('revenue')
  const [low, high] = STEP_LIMITS
  const stepLabel = (step: Step) => {
    const size = Math.abs(step)
    if (size === 0) return t('legend.none')
    if (size === 1) return t('legend.under', { value: low })
    if (size === 2) return t('legend.between', { from: low, to: high })
    return t('legend.over', { value: high })
  }
  return (
    <div className="flex flex-wrap items-end gap-x-6 gap-y-3 text-2xs text-muted">
      <figure className="m-0 grid gap-1" aria-label={t('legend.label')}>
        <div className="flex items-center gap-2">
          <span className="font-semibold text-fg">{t('legend.lower')}</span>
          <ul className="flex gap-[2px]">
            {LEGEND_STEPS.map((step) => (
              <li key={step} className="grid justify-items-center gap-1">
                <span aria-hidden className={cn('block h-3.5 w-9 rounded-[4px]', STEP_CLASS[step])} />
                <span className="num whitespace-nowrap">{stepLabel(step)}</span>
              </li>
            ))}
          </ul>
          <span className="font-semibold text-fg">{t('legend.raise')}</span>
        </div>
      </figure>
      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pb-4">
        <li className="flex items-center gap-1.5">
          <span aria-hidden className={cn('relative grid h-3.5 w-5 place-items-center rounded-[4px] bg-surface', STEP_RING[2])}>
            <Check className="size-2.5 text-success-ink" />
          </span>
          {t('legend.applied')}
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="h-3.5 w-5 rounded-[4px] bg-surface shadow-[inset_0_0_0_1px_var(--border)]" />
          <span>
            <span className="line-through">{t('legend.rejectedSample')}</span> {t('legend.rejected')}
          </span>
        </li>
        <li className="flex items-center gap-1.5">
          <span aria-hidden className="grid h-3.5 w-5 place-items-center rounded-[4px] bg-surface text-warning-ink shadow-[inset_0_0_0_2px_var(--warning)]">
            <TriangleAlert className="size-2.5" />
          </span>
          {t('legend.approved')}
        </li>
      </ul>
    </div>
  )
}
