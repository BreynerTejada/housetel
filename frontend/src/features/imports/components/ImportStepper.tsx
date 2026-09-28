import { Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { WIZARD_STEPS, type WizardStep } from '../lib/steps'

/**
 * Type → file → map → review → import → result. Done steps are checked; `onGo` makes the reachable ones
 * clickable (going back to the mapping, for instance).
 */
export function ImportStepper({
  current,
  onGo,
  reachable = [],
  className,
}: {
  current: WizardStep
  onGo?: (step: WizardStep) => void
  reachable?: WizardStep[]
  className?: string
}) {
  const { t } = useTranslation('imports')
  const index = WIZARD_STEPS.indexOf(current)
  return (
    <ol aria-label={t('steps.label')} className={cn('flex flex-wrap items-center gap-x-1 gap-y-2', className)}>
      {WIZARD_STEPS.map((step, position) => {
        const done = position < index
        const active = position === index
        const clickable = Boolean(onGo) && reachable.includes(step) && !active
        return (
          <li key={step} className="flex items-center gap-1">
            {position > 0 && (
              <span aria-hidden className={cn('hidden h-px w-5 sm:block', done || active ? 'bg-accent' : 'bg-border-strong')} />
            )}
            <button
              type="button"
              disabled={!clickable}
              onClick={() => onGo?.(step)}
              aria-current={active ? 'step' : undefined}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-xs font-semibold transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 disabled:cursor-default',
                active && 'bg-accent-soft text-accent-ink',
                done && 'text-fg',
                clickable && 'hover:bg-surface-2',
                !done && !active && 'text-subtle',
              )}
            >
              <span
                aria-hidden
                className={cn(
                  'grid size-4 place-items-center rounded-full text-[10px] leading-none',
                  active ? 'bg-accent text-on-accent' : done ? 'bg-success text-on-accent' : 'border border-border-strong',
                )}
              >
                {done ? <Check className="size-2.5" strokeWidth={3} /> : position + 1}
              </span>
              {t(`steps.${step}`)}
              {done && <span className="sr-only">{t('steps.done')}</span>}
            </button>
          </li>
        )
      })}
    </ol>
  )
}
