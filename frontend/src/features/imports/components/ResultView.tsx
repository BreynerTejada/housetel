import { ArrowRight, CircleAlert, FilePlus2, RotateCcw, Undo2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatNumber, normalizeLang } from '@/lib/format'
import { useStartImport, type ImportKind, type JobDetail } from '../api'
import { ReportMenu } from './ReportMenu'
import { RevertButton } from './RevertButton'
import { RowLedger, type LedgerSegment } from './RowLedger'
import { RowsList } from './RowsList'

const NEXT: Record<ImportKind, { to: string; key: string }[]> = {
  reservations: [
    { to: '/app/reservations', key: 'reservations' },
    { to: '/app/calendar', key: 'calendar' },
  ],
  guests: [{ to: '/app/guests', key: 'guests' }],
  room_types: [
    { to: '/app/settings/room-types', key: 'roomTypes' },
    { to: '/app/rates', key: 'rates' },
  ],
  rooms: [{ to: '/app/settings/rooms', key: 'rooms' }],
}

/**
 * Step 6: what the import did, row by row, with links to what it created; the report to fix the rows with
 * errors (upload them again: what was imported is skipped), and the rollback of a reservations import.
 */
export function ResultView({ job }: { job: JobDetail }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const [filter, setFilter] = useState<string | null>(null)
  const start = useStartImport(job.id)
  const counts = job.outcome_counts ?? {}
  const failed = counts.failed ?? 0
  const reverted = job.status === 'reverted'
  const segments: LedgerSegment[] = [
    { key: 'created', label: t('ledgerLabels.created'), count: counts.created ?? 0, tone: 'success' },
    { key: 'updated', label: t('ledgerLabels.updated'), count: counts.updated ?? 0, tone: 'info' },
    { key: 'skipped', label: t('ledgerLabels.skipped'), count: counts.skipped ?? 0, tone: 'stone' },
    { key: 'failed', label: t('ledgerLabels.failed'), count: failed, tone: 'danger' },
  ]
  if (reverted || (counts.reverted ?? 0) > 0) {
    segments.push({ key: 'reverted', label: t('ledgerLabels.reverted'), count: counts.reverted ?? 0, tone: 'stone', hatched: true })
  }
  const revert = job.revert_summary ?? {}
  const reasons = Object.entries(revert.reasons ?? {})

  return (
    <div className="grid gap-5">
      {job.status === 'failed' && (
        <div role="alert" className="grid gap-3 rounded-xl border border-danger/30 bg-danger-soft px-4 py-3 text-danger-ink sm:flex sm:items-center sm:justify-between">
          <div className="flex gap-2 text-[13px] leading-5">
            <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            <div>
              <p className="font-semibold">{t('result.failed')}</p>
              {job.error && <p className="mt-0.5 break-words text-xs opacity-80">{job.error}</p>}
            </div>
          </div>
          <Button variant="secondary" onClick={() => start.mutate({ mode: 'run', confirm: true })} loading={start.isPending} className="self-start sm:self-auto">
            <RotateCcw aria-hidden />
            {t('result.resume')}
          </Button>
        </div>
      )}
      {start.isError && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {errorMessage(start.error, t)}
        </p>
      )}

      {reverted && (
        <div className="flex gap-2 rounded-xl border border-border bg-stone-soft px-4 py-3 text-[13px] leading-5 text-stone-ink">
          <Undo2 aria-hidden className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-semibold text-fg">
              {t('result.reverted', {
                date: formatDate(job.reverted_at, lang === 'en' ? 'MMM d, yyyy h:mm a' : "d MMM yyyy, h:mm aaaa", lang),
                name: job.reverted_by?.name ?? '—',
              })}
            </p>
            <p>
              {t('result.revertedCount', { count: revert.reverted ?? 0 })}
              {(revert.not_reverted ?? 0) > 0 && ` · ${t('result.keptCount', { count: revert.not_reverted ?? 0 })}`}
              {reasons.length > 0 && ` (${reasons.map(([code, count]) => t(`result.revertReasons.${code}`, { count, defaultValue: `${code}: ${count}` })).join(' · ')})`}
            </p>
          </div>
        </div>
      )}

      <div className="grid gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
        <RowLedger segments={segments} total={job.total_rows} caption={t('result.caption')} active={filter} onSelect={setFilter} />
        {job.status !== 'failed' && (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border pt-3">
            <span className="text-[13px] text-muted">{t('result.next')}</span>
            {NEXT[job.kind].map((item) => (
              <Link
                key={item.key}
                to={item.to}
                className="inline-flex items-center gap-1 rounded-sm text-[13px] font-semibold text-accent-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
              >
                {t(`result.links.${item.key}`)}
                <ArrowRight aria-hidden className="size-3.5" />
              </Link>
            ))}
          </div>
        )}
      </div>

      {failed > 0 && (
        <p className="flex gap-2 rounded-lg bg-warning-soft px-4 py-3 text-[13px] leading-5 text-warning-ink">
          <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('result.fixFailed', { count: failed, formatted: formatNumber(failed, lang, 0) })}
        </p>
      )}

      <RowsList key={filter ?? 'all'} job={job} mode="result" filter={filter} />

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <ReportMenu job={job} />
          {job.can_revert && <RevertButton job={job} />}
        </div>
        <Button asChild variant="primary">
          <Link to="/app/settings/import">
            <FilePlus2 aria-hidden />
            {t('result.newImport')}
          </Link>
        </Button>
      </div>
    </div>
  )
}
