import { useTranslation } from 'react-i18next'
import { StatusBadge } from '@/components/StatusBadge'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import type { IntentStatus } from '../api'

/**
 * Payment or refund state with the system colors (approved → sage, pending → sand, declined/error →
 * clay, voided/expired → stone). Exported for other features: `import { PaymentStatusBadge } from
 * '@/features/finance/components/PaymentStatusBadge'`.
 */
export function PaymentStatusBadge({ status, className }: { status: string; className?: string }) {
  return <StatusBadge kind="payment" status={status} className={className} />
}

const LINK_TONES: Record<IntentStatus, BadgeTone> = {
  created: 'neutral',
  pending: 'warning',
  approved: 'success',
  declined: 'danger',
  expired: 'stone',
  error: 'danger',
}

/** Payment link state in words a guest-facing person uses ("Sin pagar", "Pagado", "Vencido"). */
export function LinkStatusBadge({ status }: { status: IntentStatus }) {
  const { t } = useTranslation('finance')
  return (
    <Badge tone={LINK_TONES[status] ?? 'neutral'} data-status={status}>
      {t(`links.status.${status}`)}
    </Badge>
  )
}

export default PaymentStatusBadge
