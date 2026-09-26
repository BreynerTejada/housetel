import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Badge, type BadgeTone } from './ui/badge'

export type StatusKind = 'reservation' | 'room' | 'payment' | 'task'

/** Colors follow the design tokens (spec §7.3): rooms and reservation states have fixed meanings. */
const TONES: Record<StatusKind, Record<string, BadgeTone>> = {
  reservation: {
    tentative: 'warning',
    confirmed: 'info',
    checked_in: 'accent',
    checked_out: 'success',
    cancelled: 'stone',
    no_show: 'danger',
  },
  room: { clean: 'success', dirty: 'warning', inspected: 'info', out_of_service: 'stone', occupied: 'accent' },
  payment: {
    created: 'neutral',
    pending: 'warning',
    approved: 'success',
    declined: 'danger',
    voided: 'stone',
    expired: 'stone',
    error: 'danger',
    failed: 'danger',
  },
  task: { pending: 'neutral', in_progress: 'info', done: 'success', inspected: 'success', cancelled: 'stone' },
}

const DOT: Record<BadgeTone, string> = {
  neutral: 'bg-subtle',
  accent: 'bg-accent',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
  stone: 'bg-stone',
  outline: 'bg-fg',
}

export function StatusBadge({ kind, status, className }: { kind: StatusKind; status: string; className?: string }) {
  const { t, i18n } = useTranslation()
  const tone = TONES[kind][status] ?? 'neutral'
  const key = `status.${kind}.${status}`
  return (
    <Badge tone={tone} data-status={status} data-tone={tone} className={className}>
      <span aria-hidden className={cn('size-1.5 rounded-full', DOT[tone])} />
      {i18n.exists(key) ? t(key) : status}
    </Badge>
  )
}
