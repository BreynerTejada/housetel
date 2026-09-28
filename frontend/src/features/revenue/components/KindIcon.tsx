import { CalendarDays, Gauge, Hourglass, PartyPopper, Ticket, type LucideIcon } from 'lucide-react'
import type { RuleKind } from '../api'

const KIND_ICONS: Record<RuleKind, LucideIcon> = {
  occupancy: Gauge,
  lead_time: Hourglass,
  day_of_week: CalendarDays,
  holiday: PartyPopper,
  event: Ticket,
}

export function KindIcon({ kind, className }: { kind: RuleKind; className?: string }) {
  const Icon = KIND_ICONS[kind]
  return <Icon aria-hidden className={className} />
}
