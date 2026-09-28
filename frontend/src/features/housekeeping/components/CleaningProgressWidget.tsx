import { ArrowRight, Wrench } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { useHkSummary } from '../api'
import { RoomStateCounts } from './DaySummary'
import { ProgressMeter } from './ProgressMeter'

/** Today panel (C1): how much of the day's cleaning is done, rooms per state and damage that needs a hand. */
export default function CleaningProgressWidget() {
  const { t } = useTranslation('housekeeping')
  const id = useId()
  const summary = useHkSummary()

  return (
    <section aria-labelledby={id} className="grid h-full content-start gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id={id} className="text-[15px] font-bold text-fg">
          {t('widget.title')}
        </h2>
        <Link to="/app/housekeeping" className="inline-flex items-center gap-1 text-[13px] font-semibold text-accent-ink hover:underline">
          {t('widget.open')}
          <ArrowRight aria-hidden className="size-3.5" />
        </Link>
      </div>
      {summary.isPending ? (
        <LoadingState variant="rows" rows={3} className="p-0" />
      ) : summary.isError ? (
        <ErrorState error={summary.error} onRetry={() => summary.refetch()} className="py-6" />
      ) : (
        <>
          {summary.data.tasks.total === 0 ? (
            <p className="text-sm text-muted">{t('widget.noTasks')}</p>
          ) : (
            <div className="grid gap-2">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <p className="font-semibold text-fg">
                  {t('board.tasksDone', { done: summary.data.tasks.done, count: summary.data.tasks.total })}
                </p>
                {summary.data.tasks.unassigned > 0 && (
                  <p className="text-[13px] font-semibold text-warning-ink">{t('board.unassigned', { count: summary.data.tasks.unassigned })}</p>
                )}
              </div>
              <ProgressMeter value={summary.data.tasks.done} max={summary.data.tasks.total} label={t('board.tasksDoneLabel')} />
            </div>
          )}
          <RoomStateCounts rooms={summary.data.rooms} size="md" className="sm:grid-cols-4" />
          {summary.data.tickets.open > 0 && (
            <p className="flex items-center gap-2 text-[13px] text-muted">
              <Wrench aria-hidden className="size-4" />
              <span>
                {t('widget.ticketsOpen', { count: summary.data.tickets.open })}
                {summary.data.tickets.blocking > 0 && ` · ${t('widget.ticketsBlocking', { count: summary.data.tickets.blocking })}`}
              </span>
            </p>
          )}
        </>
      )}
    </section>
  )
}
