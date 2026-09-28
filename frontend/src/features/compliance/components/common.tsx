import { Check, Copy, FlaskConical } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { IntegrationMode, InvoiceStatus, SireStatus, TraStatus } from '../api'
import { INVOICE_TONES, SIRE_TONES, TRA_TONES } from '../lib/labels'

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

function StateBadge({ tone, label, className }: { tone: BadgeTone; label: string; className?: string }) {
  return (
    <Badge tone={tone} data-tone={tone} className={className}>
      <span aria-hidden className={cn('size-1.5 rounded-full', DOT[tone])} />
      {label}
    </Badge>
  )
}

export function InvoiceStatusBadge({ status, className }: { status: InvoiceStatus | 'not_issued'; className?: string }) {
  const { t } = useTranslation('compliance')
  return <StateBadge tone={INVOICE_TONES[status]} label={t(`invoiceStatus.${status}`)} className={className} />
}

export function SireStatusBadge({ status, className }: { status: SireStatus; className?: string }) {
  const { t } = useTranslation('compliance')
  return <StateBadge tone={SIRE_TONES[status]} label={t(`sireStatus.${status}`)} className={className} />
}

export function TraStatusBadge({ status, className }: { status: TraStatus | 'not_registered'; className?: string }) {
  const { t } = useTranslation('compliance')
  return <StateBadge tone={TRA_TONES[status]} label={t(`traStatus.${status}`)} className={className} />
}

/** Marks documents produced by a simulated integration (no legal validity). */
export function SimulatedBadge({ mode, className }: { mode: IntegrationMode; className?: string }) {
  const { t } = useTranslation('compliance')
  if (mode !== 'simulated') return null
  return (
    <Badge tone="outline" className={cn('text-muted', className)} title={t('mode.simulatedHint')}>
      <FlaskConical aria-hidden />
      {t('mode.simulated')}
    </Badge>
  )
}

export function CopyButton({ value, label, className }: { value: string; label: string; className?: string }) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  return (
    <Button
      size="sm"
      variant="ghost"
      className={className}
      aria-label={label}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(value)
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1800)
        } catch {
          /* clipboard blocked: the value stays selectable */
        }
      }}
    >
      {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
      {copied ? t('actions.copied') : t('actions.copy')}
    </Button>
  )
}

/** Names of the fields a legal report still needs (SIRE / TRA keys → words). */
export function MissingFields({ fields, scope }: { fields: string[]; scope: 'sire' | 'tra' }) {
  const { t, i18n } = useTranslation('compliance')
  if (fields.length === 0) return null
  return (
    <ul className="flex flex-wrap gap-1" aria-label={t('missing.label')}>
      {fields.map((field) => {
        const key = `fields.${scope}.${field}`
        return (
          <li key={field}>
            <Badge tone="warning" className="font-medium">
              {i18n.exists(`compliance:${key}`) ? t(key) : field}
            </Badge>
          </li>
        )
      })}
    </ul>
  )
}

/** Section of a panel: small uppercase title, optional count and actions. */
export function SectionTitle({ title, count, actions, id }: { title: string; count?: number; actions?: ReactNode; id?: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 id={id} className="eyebrow flex items-center gap-2">
        {title}
        {count !== undefined && (
          <span className="num rounded-full bg-surface-3 px-1.5 py-px text-2xs font-bold tracking-normal text-fg">{count}</span>
        )}
      </h3>
      {actions}
    </div>
  )
}
