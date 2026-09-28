import { BedDouble, CalendarRange, ChevronLeft, ChevronRight, DoorOpen, History, Users, type LucideIcon } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { formatNumber, formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useImportJobs, type ImportKind, type JobSummary } from '../api'
import { JobStatusBadge } from './badges'

const ICONS: Record<ImportKind, LucideIcon> = {
  reservations: CalendarRange,
  guests: Users,
  room_types: BedDouble,
  rooms: DoorOpen,
}

const PAGE_SIZE = 10

/** Previous imports of the property, newest first (each opens its job page). */
export function JobHistory() {
  const { t } = useTranslation('imports')
  const [page, setPage] = useState(1)
  const jobs = useImportJobs(page)
  const count = jobs.data?.count ?? 0
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE))

  return (
    <section aria-labelledby="imports-history" className="grid gap-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="imports-history" className="text-[15px] font-bold tracking-[-0.01em]">
          {t('history.title')}
        </h2>
        {count > 0 && <span className="num text-[13px] text-muted">{t('history.count', { count })}</span>}
      </div>
      <div className="overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
        {jobs.isPending ? (
          <LoadingState variant="rows" rows={3} />
        ) : jobs.isError ? (
          <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} />
        ) : count === 0 ? (
          <EmptyState icon={History} title={t('history.empty')} description={t('history.emptyHint')} className="py-10" />
        ) : (
          <ul className="divide-y divide-border">
            {jobs.data.results.map((job) => (
              <li key={job.id}>
                <HistoryItem job={job} />
              </li>
            ))}
          </ul>
        )}
      </div>
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2">
          <span className="num text-[13px] text-muted">{t('history.page', { page, pages })}</span>
          <Button size="icon-sm" variant="secondary" aria-label={t('history.previous')} disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <ChevronLeft aria-hidden />
          </Button>
          <Button size="icon-sm" variant="secondary" aria-label={t('history.next')} disabled={page >= pages} onClick={() => setPage(page + 1)}>
            <ChevronRight aria-hidden />
          </Button>
        </div>
      )}
    </section>
  )
}

function HistoryItem({ job }: { job: JobSummary }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const Icon = ICONS[job.kind]
  const summary = job.summary ?? {}
  const done = job.status === 'completed' || job.status === 'failed' || job.status === 'reverted'
  const strip = done
    ? [
        { key: 'created', count: summary.created ?? 0, className: 'bg-success' },
        { key: 'updated', count: summary.updated ?? 0, className: 'bg-info' },
        { key: 'skipped', count: summary.skipped ?? 0, className: 'bg-stone' },
        { key: 'failed', count: summary.failed ?? 0, className: 'bg-danger' },
      ]
    : [
        { key: 'valid', count: job.counts?.valid ?? 0, className: 'bg-success' },
        { key: 'warning', count: job.counts?.warning ?? 0, className: 'bg-warning' },
        { key: 'error', count: job.counts?.error ?? 0, className: 'bg-danger' },
        { key: 'skip', count: job.counts?.skip ?? 0, className: 'bg-stone' },
      ]
  const total = strip.reduce((acc, item) => acc + item.count, 0)
  const meta = [
    t(`kinds.${job.kind}.label`),
    job.source_label,
    t('history.rows', { count: job.total_rows, formatted: formatNumber(job.total_rows, lang, 0) }),
    job.created_by?.name,
    formatRelative(job.created_at, lang),
  ].filter(Boolean)

  return (
    <Link
      to={`/app/settings/import/${job.id}`}
      className="grid gap-2 px-4 py-3 transition-colors hover:bg-surface-2/60 focus-visible:bg-surface-2 focus-visible:outline-none sm:grid-cols-[minmax(0,1fr)_15rem] sm:items-center sm:gap-4"
    >
      <span className="flex min-w-0 items-start gap-3">
        <span aria-hidden className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-lg border border-border bg-surface-2 text-muted">
          <Icon className="size-4" />
        </span>
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="truncate font-semibold text-fg">{job.filename}</span>
            <JobStatusBadge status={job.status} phase={job.phase} stale={job.stale} />
          </span>
          <span className="mt-0.5 block text-[13px] text-muted">{meta.join(' · ')}</span>
        </span>
      </span>
      {total > 0 ? (
        <span className="grid gap-1 pl-11 sm:pl-0">
          <span aria-hidden className="flex h-1.5 w-full gap-px overflow-hidden rounded-full bg-surface-3">
            {strip
              .filter((item) => item.count > 0)
              .map((item) => (
                <span key={item.key} className={cn('h-full', item.className)} style={{ width: `${(item.count / total) * 100}%` }} />
              ))}
          </span>
          <span className="num text-xs text-muted">
            {done
              ? t('history.doneSummary', { created: summary.created ?? 0, updated: summary.updated ?? 0, failed: summary.failed ?? 0 })
              : t('history.reviewSummary', { valid: (job.counts?.valid ?? 0) + (job.counts?.warning ?? 0), error: job.counts?.error ?? 0 })}
          </span>
        </span>
      ) : (
        <span className="hidden sm:block" />
      )}
    </Link>
  )
}
