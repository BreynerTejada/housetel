import { ArrowRight, Check, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useGettingStarted, type ChecklistStep, type GettingStarted } from '../api'
import { pickText } from '../helpers'

/** `/app/getting-started`: what is left before the hotel can take bookings, computed from real data. */
export default function GettingStartedPage() {
  const { t } = useTranslation('saas')
  const checklist = useGettingStarted()

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader title={t('gettingStarted.title')} description={t('gettingStarted.description')} />
      {checklist.isPending ? (
        <LoadingState variant="rows" rows={7} />
      ) : checklist.isError ? (
        <ErrorState error={checklist.error} onRetry={() => void checklist.refetch()} />
      ) : (
        <Checklist data={checklist.data} />
      )}
    </div>
  )
}

function Checklist({ data }: { data: GettingStarted }) {
  const { t } = useTranslation('saas')
  const rooms = data.steps.find((step) => step.id === 'rooms')
  const nextStep = data.steps.find((step) => !step.done)
  return (
    <div className="grid grid-cols-1 gap-6">
      <Progress data={data} />
      {rooms && !rooms.done && <AssistantCard />}
      <ol className="grid grid-cols-1 gap-2.5" aria-label={t('gettingStarted.stepsLabel')}>
        {data.steps.map((step, index) => (
          <StepRow key={step.id} step={step} index={index} isNext={step.id === nextStep?.id} />
        ))}
      </ol>
    </div>
  )
}

/** A key ring with one tag per step: each finished step hangs a filled key. */
function Progress({ data }: { data: GettingStarted }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const billing = data.billing
  const allDone = data.completed === data.total
  return (
    <section className="grid grid-cols-1 gap-5 rounded-xl border border-border bg-surface p-5 shadow-xs sm:grid-cols-[1fr_auto] sm:items-center sm:p-6">
      <div className="min-w-0">
        <p className="eyebrow">{data.property.name}</p>
        <p className="mt-1 text-[26px] leading-tight font-extrabold tracking-[-0.03em] text-fg">
          {allDone ? t('gettingStarted.allDone') : t('gettingStarted.progress', { done: data.completed, total: data.total })}
        </p>
        <div
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={data.total}
          aria-valuenow={data.completed}
          aria-label={t('gettingStarted.progressLabel')}
          className="mt-4 flex gap-1.5"
        >
          {data.steps.map((step) => (
            <span
              key={step.id}
              className={cn(
                'relative h-7 flex-1 rounded-md transition-colors duration-500',
                step.done ? 'bg-room-clean-soft' : 'border border-dashed border-border-strong',
              )}
            >
              <span
                aria-hidden
                className={cn(
                  'absolute top-1.5 left-1.5 size-1.5 rounded-full',
                  step.done ? 'bg-surface shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]' : 'bg-border',
                )}
              />
            </span>
          ))}
        </div>
      </div>
      {billing.subscription_status === 'trialing' && billing.trial_days_left !== null && (
        <div className="rounded-lg border border-info/25 bg-info-soft px-4 py-3 text-info-ink sm:max-w-60">
          <p className="text-sm font-bold">
            {t('gettingStarted.trialDays', { count: billing.trial_days_left })}
          </p>
          <p className="mt-0.5 text-xs">
            {t('gettingStarted.trialPlan', {
              plan: pickText(billing.plan?.name, lang),
              date: formatDate(billing.trial_ends_at, undefined, lang),
            })}
          </p>
          <Link to="/app/settings/billing" className="mt-2 inline-flex text-xs font-semibold underline underline-offset-4">
            {t('gettingStarted.seePlans')}
          </Link>
        </div>
      )}
    </section>
  )
}

function AssistantCard() {
  const { t } = useTranslation('saas')
  return (
    <section className="flex flex-col gap-4 rounded-xl border border-accent/30 bg-accent-soft p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
      <div className="flex items-start gap-3">
        <span aria-hidden className="grid grid-cols-1 size-10 shrink-0 place-items-center rounded-lg bg-accent text-on-accent">
          <Sparkles className="size-5" />
        </span>
        <div>
          <p className="font-bold text-accent-ink">{t('gettingStarted.assistant.title')}</p>
          <p className="mt-0.5 max-w-lg text-sm text-accent-ink/85">{t('gettingStarted.assistant.text')}</p>
        </div>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        <Button asChild variant="primary">
          <Link to="/app/onboarding">{t('gettingStarted.assistant.cta')}</Link>
        </Button>
        <Button asChild variant="ghost">
          <Link to="/app/settings/room-types">{t('gettingStarted.assistant.manual')}</Link>
        </Button>
      </div>
    </section>
  )
}

function StepRow({ step, index, isNext }: { step: ChecklistStep; index: number; isNext: boolean }) {
  const { t } = useTranslation('saas')
  return (
    <li
      className={cn(
        'grid grid-cols-[auto_minmax(0,1fr)] gap-x-3.5 gap-y-3 rounded-xl border bg-surface p-4 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center sm:p-5',
        isNext ? 'border-accent/40 shadow-sm' : 'border-border',
      )}
    >
      <span
        aria-hidden
        className={cn(
          'relative grid h-11 w-9 grid-cols-1 items-end justify-items-center rounded-md pb-1.5',
          step.done ? 'bg-room-clean-soft text-success-ink' : isNext ? 'bg-accent-soft text-accent-ink' : 'bg-surface-2 text-muted',
        )}
      >
        <span className="absolute top-1.5 left-1/2 size-1.5 -translate-x-1/2 rounded-full bg-surface shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]" />
        {step.done ? <Check className="size-4" strokeWidth={3} /> : <span className="num text-sm font-bold">{index + 1}</span>}
      </span>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-semibold text-fg">{t(`gettingStarted.steps.${step.id}.title`)}</p>
          {step.done && <Badge tone="success">{t('gettingStarted.done')}</Badge>}
          {isNext && <Badge tone="accent">{t('gettingStarted.next')}</Badge>}
        </div>
        <p className="mt-0.5 text-sm text-muted">
          <StepDetail step={step} />
        </p>
      </div>
      <div className="col-span-2 flex flex-wrap gap-2 sm:col-span-1 sm:justify-end">
        {step.alt_link && !step.done && (
          <Button asChild variant="ghost" size="sm">
            <Link to={step.alt_link}>{t(`gettingStarted.steps.${step.id}.alt`)}</Link>
          </Button>
        )}
        <Button asChild variant={isNext ? 'primary' : 'secondary'} size="sm">
          <Link to={step.link}>
            {step.done ? t('gettingStarted.review') : t(`gettingStarted.steps.${step.id}.cta`)}
            {!step.done && <ArrowRight aria-hidden />}
          </Link>
        </Button>
      </div>
    </li>
  )
}

function StepDetail({ step }: { step: ChecklistStep }): ReactNode {
  const { t } = useTranslation('saas')
  const d = step.detail as Record<string, number | boolean | string | string[]>
  switch (step.id) {
    case 'profile': {
      const missing = (d.missing as string[]) ?? []
      if (!missing.length) return t('gettingStarted.steps.profile.complete')
      return t('gettingStarted.steps.profile.missing', {
        fields: missing.map((field) => t(`gettingStarted.profileFields.${field}`)).join(', '),
      })
    }
    case 'rooms':
      return Number(d.units) > 0
        ? t('gettingStarted.steps.rooms.summary', { types: Number(d.room_types), count: Number(d.units) })
        : t('gettingStarted.steps.rooms.text')
    case 'rates':
      return Number(d.room_types) > 0
        ? t('gettingStarted.steps.rates.summary', { priced: Number(d.priced), total: Number(d.room_types) })
        : t('gettingStarted.steps.rates.text')
    case 'payments':
      return d.mode === 'real' ? t('gettingStarted.steps.payments.real') : t('gettingStarted.steps.payments.simulated')
    case 'channels': {
      const parts = []
      if (d.marketplace_listed) parts.push(t('gettingStarted.steps.channels.listed'))
      if (Number(d.connections) > 0) parts.push(t('gettingStarted.steps.channels.connections', { count: Number(d.connections) }))
      return parts.length ? parts.join(' · ') : t('gettingStarted.steps.channels.text')
    }
    case 'team':
      return Number(d.members) > 1 || Number(d.invitations) > 0
        ? t('gettingStarted.steps.team.summary', { members: Number(d.members), invitations: Number(d.invitations) })
        : t('gettingStarted.steps.team.text')
    case 'first_booking':
      return Number(d.reservations) > 0
        ? t('gettingStarted.steps.first_booking.summary', { count: Number(d.reservations) })
        : t('gettingStarted.steps.first_booking.text')
    default:
      return null
  }
}
