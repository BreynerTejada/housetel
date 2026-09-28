import { ArrowRight, IdCard, PlaneLanding, ReceiptText } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Skeleton } from '@/components/ui/skeleton'
import { formatMoney, normalizeLang, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { InvoiceTotals, PendingSummary, SireReport } from '../api'
import { buildSireDays } from '../lib/sire'
import { SireDayStrip } from './SireDayStrip'

export type ComplianceTab = 'invoices' | 'sire' | 'tra' | 'pending'

function Obligation({
  icon: Icon,
  authority,
  title,
  children,
  footer,
  tone,
  onOpen,
}: {
  icon: typeof ReceiptText
  authority: string
  title: string
  children: ReactNode
  footer: string
  tone: 'ok' | 'attention'
  onOpen: () => void
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cn(
        'group grid min-w-0 content-between gap-4 rounded-xl border bg-surface p-4 text-left shadow-xs transition-colors sm:p-5',
        'hover:border-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
        tone === 'attention' ? 'border-warning/45' : 'border-border',
      )}
    >
      <div className="grid gap-3">
        <div className="flex items-center gap-2">
          <Icon aria-hidden className="size-4 text-muted" />
          <span className="eyebrow">{authority}</span>
        </div>
        <p className="text-[15px] font-bold text-fg">{title}</p>
        {children}
      </div>
      <p
        className={cn(
          'flex items-center gap-1 text-[13px] font-semibold',
          tone === 'attention' ? 'text-warning-ink' : 'text-success-ink',
        )}
      >
        {footer}
        <ArrowRight aria-hidden className="size-3.5 transition-transform group-hover:translate-x-0.5" />
      </p>
    </button>
  )
}

/**
 * The three legal obligations of a Colombian hotel side by side (the page's thesis): invoices to the DIAN, foreign
 * guests to Migración Colombia (SIRE) and every guest to MinCIT (TRA). Each card opens its tab.
 */
export function ObligationsBoard({
  businessDate,
  totals,
  pending,
  reports,
  registered,
  onOpen,
}: {
  businessDate?: string
  totals?: InvoiceTotals
  pending?: PendingSummary
  reports?: SireReport[]
  registered?: number
  onOpen: (tab: ComplianceTab) => void
}) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  if (!pending || !totals || !reports) {
    return (
      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((index) => (
          <Skeleton key={index} className="h-48 rounded-xl" />
        ))}
      </div>
    )
  }
  const days = buildSireDays(businessDate, reports, pending.sire.unreported_days)
  const toUpload = days.filter((day) => day.state === 'toUpload').length
  const missingDays = days.filter((day) => day.state === 'missing').length
  const invoicesPending = pending.counts.invoices
  const resolutionTrouble = pending.resolution.status !== 'ok'
  const traPending = pending.counts.tra

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Obligation
        icon={ReceiptText}
        authority={t('board.dian')}
        title={t('board.invoicesTitle')}
        tone={invoicesPending || resolutionTrouble ? 'attention' : 'ok'}
        footer={
          resolutionTrouble
            ? t(`resolution.health.${pending.resolution.status}`)
            : invoicesPending
              ? t('board.invoicesPending', { count: invoicesPending })
              : t('board.invoicesOk')
        }
        onOpen={() => onOpen(invoicesPending || resolutionTrouble ? 'pending' : 'invoices')}
      >
        <div>
          <p className="num text-[26px] leading-8 font-semibold tracking-[-0.02em] text-fg">{formatMoney(totals.total)}</p>
          <p className="text-[13px] text-muted">
            {t('board.invoicesMonth', { count: totals.invoices, formatted: formatNumber(totals.invoices, lang) })}
            {totals.exempt.count > 0 && ` · ${t('board.exempt', { count: totals.exempt.count })}`}
          </p>
        </div>
      </Obligation>

      <Obligation
        icon={PlaneLanding}
        authority={t('board.sire')}
        title={t('board.sireTitle')}
        tone={toUpload || missingDays || pending.sire.missing.length ? 'attention' : 'ok'}
        footer={
          missingDays
            ? t('board.sireMissingDays', { count: missingDays })
            : toUpload
              ? t('board.sireToUpload', { count: toUpload })
              : t('board.sireOk')
        }
        onOpen={() => onOpen('sire')}
      >
        <SireDayStrip days={days} size="sm" />
        <p className="text-[13px] text-muted">{t('board.sireWindow')}</p>
      </Obligation>

      <Obligation
        icon={IdCard}
        authority={t('board.tra')}
        title={t('board.traTitle')}
        tone={traPending ? 'attention' : 'ok'}
        footer={traPending ? t('board.traPending', { count: traPending }) : t('board.traOk')}
        onOpen={() => onOpen(traPending ? 'pending' : 'tra')}
      >
        <div>
          <p className="num text-[26px] leading-8 font-semibold tracking-[-0.02em] text-fg">
            {formatNumber(registered ?? 0, lang)}
          </p>
          <p className="text-[13px] text-muted">{t('board.traRegistered', { count: registered ?? 0 })}</p>
        </div>
      </Obligation>
    </div>
  )
}
