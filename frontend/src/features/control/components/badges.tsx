import {
  Bot,
  CalendarSync,
  CircleAlert,
  CircleCheck,
  CircleDashed,
  CircleMinus,
  Cpu,
  CreditCard,
  IdCard,
  LoaderCircle,
  Mail,
  MessageCircle,
  Network,
  OctagonAlert,
  PlaneLanding,
  Plug,
  ReceiptText,
  Sparkles,
  UserRound,
  Webhook,
  type LucideIcon,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Avatar, AvatarFallback, initials } from '@/components/ui/avatar'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { AuditSource, IntegrationKind, RunStatus, UserRef } from '../api'

const RUN: Record<RunStatus, { tone: BadgeTone; icon: LucideIcon; dot: string }> = {
  running: { tone: 'info', icon: LoaderCircle, dot: 'bg-info animate-pulse' },
  success: { tone: 'success', icon: CircleCheck, dot: 'bg-success' },
  partial: { tone: 'warning', icon: CircleAlert, dot: 'bg-warning' },
  failed: { tone: 'danger', icon: OctagonAlert, dot: 'bg-danger' },
  skipped: { tone: 'stone', icon: CircleMinus, dot: 'bg-stone' },
}

export function RunStatusBadge({ status, className }: { status: RunStatus; className?: string }) {
  const { t } = useTranslation('control')
  const spec = RUN[status] ?? RUN.skipped
  const Icon = spec.icon
  return (
    <Badge tone={spec.tone} className={className}>
      <Icon aria-hidden className={status === 'running' ? 'animate-spin' : undefined} />
      {t(`runStatus.${status}`)}
    </Badge>
  )
}

/** The last runs as a row of dots, oldest to newest (hover shows the status). */
export function RecentRuns({ runs }: { runs: { id: string; status: RunStatus; started_at: string }[] }) {
  const { t } = useTranslation('control')
  const ordered = [...runs].reverse()
  if (!ordered.length) return <span className="text-xs text-subtle">—</span>
  const list = ordered.map((run) => t(`runStatus.${run.status}`)).join(', ')
  return (
    <span role="img" aria-label={t('automations.recentLabel', { list })} className="inline-flex items-center gap-1" title={list}>
      {ordered.map((run) => (
        <span key={run.id} className={cn('size-2 rounded-full', (RUN[run.status] ?? RUN.skipped).dot)} />
      ))}
    </span>
  )
}

const SOURCE_ICON: Record<AuditSource, LucideIcon> = {
  user: UserRound,
  automation: Bot,
  ai: Sparkles,
  channel: Plug,
  guest: UserRound,
  system: Cpu,
  api: Webhook,
}

/** Who did it: the person's initials, or an icon for automations, AI, channels, guests and the system. */
export function SourceAvatar({ source, actor, className }: { source: AuditSource; actor: UserRef | null; className?: string }) {
  if (actor) {
    return (
      <Avatar className={cn('size-7 bg-surface ring-4 ring-surface', className)}>
        <AvatarFallback className="text-[10px]">{initials(actor.name, actor.email)}</AvatarFallback>
      </Avatar>
    )
  }
  const Icon = SOURCE_ICON[source] ?? Cpu
  return (
    <span
      className={cn(
        'grid size-7 shrink-0 place-items-center rounded-full border border-border ring-4 ring-surface',
        source === 'automation' ? 'bg-info-soft text-info-ink' : source === 'ai' ? 'bg-accent-soft text-accent-ink' : 'bg-surface-2 text-muted',
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5" />
    </span>
  )
}

const KIND_ICON: Record<IntegrationKind, LucideIcon> = {
  payments: CreditCard,
  channel_ical: CalendarSync,
  channel_channex: Network,
  einvoice: ReceiptText,
  sire: PlaneLanding,
  tra: IdCard,
  email: Mail,
  whatsapp: MessageCircle,
  llm: Sparkles,
}

export function IntegrationIcon({ kind, real, className }: { kind: IntegrationKind; real: boolean; className?: string }) {
  const Icon = KIND_ICON[kind] ?? CircleDashed
  return (
    <span
      className={cn(
        'grid size-10 shrink-0 place-items-center rounded-lg border',
        real ? 'border-transparent bg-accent-soft text-accent-ink' : 'border-border bg-surface-2 text-muted',
        className,
      )}
    >
      <Icon aria-hidden className="size-5" />
    </span>
  )
}
