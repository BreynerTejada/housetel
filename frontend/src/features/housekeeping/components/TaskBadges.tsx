import { ArrowUp, BedSingle, ClockAlert, DoorOpen, Siren, Star, Timer } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge } from '@/components/ui/badge'
import type { Arrival, HkTask, Priority } from '../api'

/** Only what deserves attention: urgent and high. Normal work carries no badge; low is quiet stone. */
export function PriorityBadge({ priority }: { priority: Priority }) {
  const { t } = useTranslation('housekeeping')
  if (priority === 'normal') return null
  if (priority === 'urgent')
    return (
      <Badge tone="danger">
        <Siren aria-hidden />
        {t('priorities.urgent')}
      </Badge>
    )
  if (priority === 'high')
    return (
      <Badge tone="outline">
        <ArrowUp aria-hidden />
        {t('priorities.high')}
      </Badge>
    )
  return <Badge tone="stone">{t('priorities.low')}</Badge>
}

export function ArrivalBadge({ arrival }: { arrival: Arrival }) {
  const { t } = useTranslation('housekeeping')
  return (
    <Badge tone="accent">
      <DoorOpen aria-hidden />
      {arrival.eta ? t('card.arrival', { eta: arrival.eta }) : t('card.arrivalNoEta')}
    </Badge>
  )
}

export function VipBadge() {
  const { t } = useTranslation('housekeeping')
  return (
    <Badge tone="warning">
      <Star aria-hidden />
      {t('card.vip')}
    </Badge>
  )
}

/** The chips of a task, in reading order: priority, arrival (and VIP), bed, left over from another day. */
export function TaskBadges({ task, extra }: { task: HkTask; extra?: ReactNode }) {
  const { t } = useTranslation('housekeeping')
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <PriorityBadge priority={task.priority} />
      {task.arrival_today && <ArrivalBadge arrival={task.arrival_today} />}
      {task.arrival_today?.is_vip && <VipBadge />}
      {task.bed && (
        <Badge tone="neutral">
          <BedSingle aria-hidden />
          {t('card.bed', { label: task.bed.label })}
        </Badge>
      )}
      {task.overdue && (
        <Badge tone="neutral">
          <ClockAlert aria-hidden />
          {t('card.overdue')}
        </Badge>
      )}
      {extra}
    </div>
  )
}

export function MinutesTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 text-[13px] font-semibold text-muted">
      <Timer aria-hidden className="size-3.5" />
      {children}
    </span>
  )
}
