import { Info, OctagonAlert, TriangleAlert, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { Severity } from '../api'

// Severity marks of the alert center, kept apart from the other badges: the topbar bell (eager) only needs these.
const SEVERITY: Record<Severity, { tone: BadgeTone; icon: LucideIcon; dot: string; rail: string; ink: string }> = {
  critical: { tone: 'danger', icon: OctagonAlert, dot: 'bg-danger', rail: 'bg-danger', ink: 'text-danger-ink' },
  warning: { tone: 'warning', icon: TriangleAlert, dot: 'bg-warning', rail: 'bg-warning', ink: 'text-warning-ink' },
  info: { tone: 'info', icon: Info, dot: 'bg-info', rail: 'bg-info', ink: 'text-info-ink' },
}

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  const { t } = useTranslation('control')
  const spec = SEVERITY[severity] ?? SEVERITY.info
  const Icon = spec.icon
  return (
    <Badge tone={spec.tone} className={className}>
      <Icon aria-hidden />
      {t(`severity.${severity}`)}
    </Badge>
  )
}

export function SeverityIcon({ severity, className }: { severity: Severity; className?: string }) {
  const spec = SEVERITY[severity] ?? SEVERITY.info
  const Icon = spec.icon
  return <Icon aria-hidden className={cn('size-4 shrink-0', spec.ink, className)} />
}

export function SeverityDot({ severity, className }: { severity: Severity; className?: string }) {
  const spec = SEVERITY[severity] ?? SEVERITY.info
  return <span aria-hidden className={cn('inline-block size-2 shrink-0 rounded-full', spec.dot, className)} />
}

/** Left accent bar of an alert card. */
export function SeverityRail({ severity }: { severity: Severity }) {
  const spec = SEVERITY[severity] ?? SEVERITY.info
  return <span aria-hidden className={cn('absolute top-3 bottom-3 left-0 w-1 rounded-r-full', spec.rail)} />
}

