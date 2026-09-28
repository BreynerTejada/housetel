import { Check, CheckCheck, CircleAlert, Clock, type LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import type { MessageChannel, MessageStatus } from '../api'
import { CHANNEL_META } from '../lib/channels'

/** Channel chip: icon only (with an accessible name) or icon + label. */
export function ChannelMark({
  channel,
  withLabel = false,
  className,
}: {
  channel: MessageChannel
  withLabel?: boolean
  className?: string
}) {
  const { t } = useTranslation('messaging')
  const meta = CHANNEL_META[channel] ?? CHANNEL_META.ota
  const Icon = meta.icon
  const label = t(`channels.${channel}`)
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full font-semibold',
        withLabel ? 'h-5 px-2 text-[11px]' : 'size-5 justify-center',
        meta.chip,
        className,
      )}
      title={withLabel ? undefined : label}
    >
      <Icon aria-hidden className="size-3" />
      {withLabel ? label : <span className="sr-only">{label}</span>}
    </span>
  )
}

const STATUS_ICON: Partial<Record<MessageStatus, LucideIcon>> = {
  queued: Clock,
  sent: Check,
  delivered: CheckCheck,
  read: CheckCheck,
  failed: CircleAlert,
}

/** Delivery state of an outgoing message: ✓ sent, ✓✓ delivered, slate ✓✓ read, alert when it failed. */
export function DeliveryStatus({ status, className }: { status: MessageStatus; className?: string }) {
  const { t } = useTranslation('messaging')
  const Icon = STATUS_ICON[status]
  if (!Icon) return null
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1',
        status === 'read' && 'text-info-ink',
        status === 'failed' && 'font-semibold text-danger-ink',
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      <span className={status === 'failed' ? undefined : 'sr-only'}>{t(`status.${status}`)}</span>
    </span>
  )
}
