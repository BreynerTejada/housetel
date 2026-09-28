import { useTranslation } from 'react-i18next'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { CommissionStatus, InvoiceStatus, OrganizationStatus, SettlementStatus, SubscriptionStatus } from '../api'
import { COMMISSION_TONE, INVOICE_TONE, ORGANIZATION_TONE, SETTLEMENT_TONE, SUBSCRIPTION_TONE } from '../helpers'

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

function ToneBadge({ tone, label, className }: { tone: BadgeTone; label: string; className?: string }) {
  return (
    <Badge tone={tone} className={className} data-tone={tone}>
      <span aria-hidden className={cn('size-1.5 rounded-full', DOT[tone])} />
      {label}
    </Badge>
  )
}

export function SubscriptionBadge({ status, className }: { status: SubscriptionStatus; className?: string }) {
  const { t } = useTranslation('saas')
  return <ToneBadge tone={SUBSCRIPTION_TONE[status] ?? 'neutral'} label={t(`status.subscription.${status}`)} className={className} />
}

export function OrganizationBadge({ status, className }: { status: OrganizationStatus; className?: string }) {
  const { t } = useTranslation('saas')
  return <ToneBadge tone={ORGANIZATION_TONE[status] ?? 'neutral'} label={t(`status.organization.${status}`)} className={className} />
}

export function InvoiceBadge({ status, className }: { status: InvoiceStatus; className?: string }) {
  const { t } = useTranslation('saas')
  return <ToneBadge tone={INVOICE_TONE[status] ?? 'neutral'} label={t(`status.invoice.${status}`)} className={className} />
}

export function CommissionBadge({ status, className }: { status: CommissionStatus; className?: string }) {
  const { t } = useTranslation('saas')
  return <ToneBadge tone={COMMISSION_TONE[status] ?? 'neutral'} label={t(`status.commission.${status}`)} className={className} />
}

export function SettlementBadge({ status, className }: { status: SettlementStatus; className?: string }) {
  const { t } = useTranslation('saas')
  return <ToneBadge tone={SETTLEMENT_TONE[status] ?? 'neutral'} label={t(`status.settlement.${status}`)} className={className} />
}
