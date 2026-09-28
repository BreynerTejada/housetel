import { ArrowRight, CircleCheck, IdCard, PlaneLanding, ReceiptText } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { cn } from '@/lib/utils'
import { usePendingCounts } from '../api'

/** Today panel (C1): what the law still expects today — invoices, TRA registrations and SIRE files. */
export default function LegalWidget() {
  const { t } = useTranslation('compliance')
  const id = useId()
  const query = usePendingCounts()
  const rows = query.data
    ? [
        { key: 'invoices', icon: ReceiptText, count: query.data.counts.invoices, tab: 'pending' },
        { key: 'tra', icon: IdCard, count: query.data.counts.tra, tab: 'pending' },
        { key: 'sire', icon: PlaneLanding, count: query.data.counts.sire, tab: 'sire' },
      ]
    : []
  const resolutionTrouble = query.data && query.data.resolution_status !== 'ok'

  return (
    <section aria-labelledby={id} className="grid h-full content-start gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={id} className="text-[15px] font-bold text-fg">
          {t('widget.title')}
        </h2>
        <Link to="/app/compliance?tab=pending" className="inline-flex items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline">
          {t('widget.open')}
          <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      </div>
      {query.isPending ? (
        <LoadingState variant="rows" rows={3} className="p-0" />
      ) : query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} className="py-6" />
      ) : query.data.counts.total === 0 && !resolutionTrouble ? (
        <p className="flex items-center gap-2 text-sm text-success-ink">
          <CircleCheck aria-hidden className="size-4" />
          {t('widget.clear')}
        </p>
      ) : (
        <ul className="grid gap-1">
          {rows.map(({ key, icon: Icon, count, tab }) => (
            <li key={key}>
              <Link
                to={`/app/compliance?tab=${tab}`}
                className="flex items-center gap-3 rounded-md px-2 py-1.5 transition-colors hover:bg-surface-2"
              >
                <Icon aria-hidden className="size-4 text-muted" />
                <span className="flex-1 text-sm text-fg">{t(`widget.${key}`)}</span>
                <span className={cn('num text-sm font-bold', count ? 'text-warning-ink' : 'text-subtle')}>{count}</span>
              </Link>
            </li>
          ))}
          {resolutionTrouble && (
            <li className="mt-1 rounded-md bg-danger-soft px-2 py-1.5 text-[13px] text-danger-ink">
              {t(`resolution.health.${query.data.resolution_status}`)}
            </li>
          )}
        </ul>
      )}
    </section>
  )
}
