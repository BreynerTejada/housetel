import { Check, CircleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { CheckinStep } from '../../api'

/**
 * Progress of the check-in: a real sequence, so the steps are numbered. Steps already done (before the
 * check-in is completed) can be reopened to fix something.
 */
export function StepProgress({
  steps,
  current,
  reachable,
  onSelect,
}: {
  steps: CheckinStep[]
  current: CheckinStep
  reachable: (step: CheckinStep) => boolean
  onSelect: (step: CheckinStep) => void
}) {
  const { t } = useTranslation('guestportal')
  const position = steps.indexOf(current)

  return (
    <nav aria-label={t('checkin.progress')}>
      <ol className="flex gap-1.5">
        {steps.map((step, index) => {
          const done = index < position
          const active = index === position
          const label = `${index + 1}. ${t(`checkin.steps.${step}`)}`
          const bar = (
            <span
              aria-hidden
              className={cn(
                'block h-1.5 rounded-full transition-colors',
                done ? 'bg-accent' : active ? 'bg-accent/45' : 'bg-surface-3',
              )}
            />
          )
          return (
            <li key={step} className="min-w-0 flex-1">
              {done && reachable(step) ? (
                <button
                  type="button"
                  onClick={() => onSelect(step)}
                  className="block w-full rounded-full py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
                >
                  {bar}
                  <span className="sr-only">
                    {label} · {t('checkin.stepDone')}
                  </span>
                </button>
              ) : (
                <span className="block py-2" aria-current={active ? 'step' : undefined}>
                  {bar}
                  <span className="sr-only">
                    {label}
                    {done ? ` · ${t('checkin.stepDone')}` : ''}
                  </span>
                </span>
              )}
            </li>
          )
        })}
      </ol>
      <p className="eyebrow mt-1">
        {t('checkin.stepOf', { current: position + 1, total: steps.length })} · {t(`checkin.steps.${current}`)}
      </p>
    </nav>
  )
}

export function StepTitle({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <h2 className="flex items-center gap-2.5 text-[26px] leading-8 font-extrabold tracking-[-0.03em]">
      {icon}
      {children}
    </h2>
  )
}

export function StepActions({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn('flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:items-center sm:justify-end', className)}>{children}</div>
}

export function StepError({ message }: { message: string }) {
  return (
    <p role="alert" className="flex items-start gap-2 rounded-xl bg-danger-soft px-4 py-3 text-sm font-medium text-danger-ink">
      <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
      {message}
    </p>
  )
}

/** A green check "stamp" (the completed check-in). */
export function DoneStamp() {
  return (
    <span className="grid size-16 place-items-center rounded-full bg-success-soft text-success-ink motion-safe:animate-pop-in">
      <Check aria-hidden className="size-8" strokeWidth={2.5} />
    </span>
  )
}
