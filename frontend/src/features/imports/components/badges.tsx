import { LoaderCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { DryOutcome, JobPhase, JobStatus, RowOutcome, RowStatus } from '../api'
import { DRY_TONE, JOB_STATUS_TONE, OUTCOME_TONE, ROW_STATUS_TONE, type Tone } from '../lib/fields'

const DOT: Record<Tone, string> = {
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  stone: 'bg-stone',
  info: 'bg-info',
  accent: 'bg-accent',
  neutral: 'bg-subtle',
}

function Dot({ tone }: { tone: Tone }) {
  return <span aria-hidden className={cn('size-1.5 rounded-full', DOT[tone])} />
}

/** Status of a job; while it runs it says what it is doing (simulating, importing, rolling back). */
export function JobStatusBadge({ status, phase, stale = false }: { status: JobStatus; phase: JobPhase; stale?: boolean }) {
  const { t } = useTranslation('imports')
  const tone = stale ? 'warning' : JOB_STATUS_TONE[status]
  const running = status === 'queued' || status === 'running'
  const label = stale ? t('jobStatus.stale') : running && phase ? t(`jobPhase.${phase}`) : t(`jobStatus.${status}`)
  return (
    <Badge tone={tone}>
      {running && !stale ? <LoaderCircle aria-hidden className="animate-spin" /> : <Dot tone={tone} />}
      {label}
    </Badge>
  )
}

export function RowStatusBadge({ status }: { status: RowStatus }) {
  const { t } = useTranslation('imports')
  const tone = ROW_STATUS_TONE[status]
  return (
    <Badge tone={tone}>
      <Dot tone={tone} />
      {t(`rowStatus.${status}`)}
    </Badge>
  )
}

export function DryOutcomeBadge({ outcome }: { outcome: DryOutcome }) {
  const { t } = useTranslation('imports')
  if (!outcome) return null
  const tone = DRY_TONE[outcome]
  return (
    <Badge tone={tone}>
      <Dot tone={tone} />
      {t(`dryOutcome.${outcome}`)}
    </Badge>
  )
}

export function OutcomeBadge({ outcome }: { outcome: RowOutcome }) {
  const { t } = useTranslation('imports')
  if (!outcome) return null
  const tone = OUTCOME_TONE[outcome]
  return (
    <Badge tone={tone}>
      <Dot tone={tone} />
      {t(`outcome.${outcome}`)}
    </Badge>
  )
}
