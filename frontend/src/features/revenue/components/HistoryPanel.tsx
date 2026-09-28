import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatDate, formatDateRange, formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useRuns, type RevenueRun } from '../api'
import { signedPercent } from '../lib/format'
import { addDays } from '../lib/dates'
import { STEP_CLASS, stepOf } from '../lib/scale'
import { RunSummaryText } from './LastRunCard'

const PAGE_SIZE = 25

/** Every revenue run (scheduled, manual, demo), newest first, with its figures and its (AI) summary. */
export function HistoryPanel() {
  const { t } = useTranslation('revenue')
  const [page, setPage] = useState(1)
  const runs = useRuns(page)

  if (runs.isPending) return <LoadingState variant="rows" rows={4} />
  if (runs.isError) return <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
  if (runs.data.count === 0) {
    return <p className="rounded-lg border border-border bg-surface px-4 py-10 text-center text-sm text-muted">{t('history.empty')}</p>
  }
  const pages = Math.max(1, Math.ceil(runs.data.count / PAGE_SIZE))
  return (
    <div className={cn('grid gap-3 transition-opacity', runs.isPlaceholderData && 'opacity-60')}>
      <ol aria-label={t('history.list')} className="grid gap-3">
        {runs.data.results.map((run) => (
          <RunItem key={run.id} run={run} />
        ))}
      </ol>
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 text-sm text-muted">
          <span className="num">{t('history.page', { page, pages })}</span>
          <Button size="sm" onClick={() => setPage(page - 1)} disabled={page <= 1}>
            <ChevronLeft aria-hidden />
            {t('history.previous')}
          </Button>
          <Button size="sm" onClick={() => setPage(page + 1)} disabled={page >= pages}>
            {t('history.next')}
            <ChevronRight aria-hidden />
          </Button>
        </div>
      )}
    </div>
  )
}

function RunItem({ run }: { run: RevenueRun }) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const who = run.triggered_by?.full_name || run.triggered_by?.email
  const top = run.details.top ?? []
  return (
    <li className="grid gap-3 rounded-lg border border-border bg-surface p-4 shadow-xs sm:p-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        <p className="num text-[13px] font-bold text-fg">{formatDate(run.started_at, 'EEE d MMM yyyy, HH:mm', lang)}</p>
        <Badge tone={run.trigger === 'manual' ? 'accent' : 'neutral'}>
          {who ? t('lastRun.by', { trigger: t(`triggers.${run.trigger}`), who }) : t(`triggers.${run.trigger}`)}
        </Badge>
        {run.status !== 'success' && <Badge tone={run.status === 'failed' ? 'danger' : 'warning'}>{t(run.status === 'failed' ? 'history.failed' : 'history.running')}</Badge>}
        {run.start_date && run.end_date && (
          <span className="text-xs text-muted">{t('history.range', { range: formatDateRange(run.start_date, addDays(run.end_date, -1), lang) })}</span>
        )}
      </div>
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs font-semibold text-fg">
        <li>{t('history.count', { count: run.recommendations_count })}</li>
        {run.auto_applied_count > 0 && <li>{t('history.autoApplied', { count: run.auto_applied_count })}</li>}
        {run.expired_count > 0 && <li className="text-muted">{t('history.expired', { count: run.expired_count })}</li>}
      </ul>
      <RunSummaryText run={run} />
      {top.length > 0 && (
        <details className="group text-xs">
          <summary className="cursor-pointer font-semibold text-accent-ink select-none">{t('history.top')}</summary>
          <ul className="mt-2 grid gap-1.5">
            {top.map((item) => (
              <li key={`${item.date}-${item.room_type}`} className="flex flex-wrap items-center gap-2">
                <span className={cn('num rounded px-1.5 py-px font-bold', STEP_CLASS[stepOf(item.change_percent)])}>
                  {signedPercent(item.change_percent, lang)}
                </span>
                <span className="num font-semibold text-fg">
                  {formatDate(item.date, 'EEE d MMM', lang)} · {item.room_type}
                </span>
                <span className="num text-muted">
                  {formatMoney(item.current_price)} → {formatMoney(item.recommended_price)}
                </span>
                {item.reasons.length > 0 && <span className="text-muted">({item.reasons.join(', ')})</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  )
}
