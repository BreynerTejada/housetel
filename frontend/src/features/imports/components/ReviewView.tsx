import { ArrowLeft, CircleAlert, FlaskConical, Import, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Button } from '@/components/ui/button'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatNumber, normalizeLang } from '@/lib/format'
import { useStartImport, type JobDetail } from '../api'
import { ReportMenu } from './ReportMenu'
import { RowLedger, type LedgerSegment } from './RowLedger'
import { RowsList } from './RowsList'

type Lens = 'review' | 'dry'

/**
 * Step 4: every row checked (formats, required values, categories, capacity, dates, repeated rows and records
 * imported before). The dry-run then goes through the real booking services without saving — availability
 * included — and "Import" runs it for real.
 */
export function ReviewView({ job, onEdit }: { job: JobDetail; onEdit: (view: 'columns' | 'values') => void }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const start = useStartImport(job.id)
  const hasDry = Boolean(job.dry_run_at)
  const [lens, setLens] = useState<Lens>(hasDry ? 'dry' : 'review')
  const [filter, setFilter] = useState<string | null>(null)
  const [confirming, setConfirming] = useState(false)
  const mode: Lens = hasDry ? lens : 'review'
  const counts = job.counts ?? {}
  const dry = job.dry_run_summary ?? {}
  const ready = job.ready_rows
  const errors = counts.error ?? 0

  const segments: LedgerSegment[] =
    mode === 'dry'
      ? [
          { key: 'create', label: t('ledgerLabels.create'), count: dry.create ?? 0, tone: 'success' },
          { key: 'update', label: t('ledgerLabels.update'), count: dry.update ?? 0, tone: 'info' },
          { key: 'skip', label: t('ledgerLabels.skipDry'), count: dry.skip ?? 0, tone: 'stone' },
          { key: 'fail', label: t('ledgerLabels.fail'), count: dry.fail ?? 0, tone: 'danger' },
        ]
      : [
          { key: 'valid', label: t('ledgerLabels.valid'), count: counts.valid ?? 0, tone: 'success' },
          { key: 'warning', label: t('ledgerLabels.warning'), count: counts.warning ?? 0, tone: 'warning' },
          { key: 'error', label: t('ledgerLabels.error'), count: errors, tone: 'danger' },
          { key: 'skip', label: t('ledgerLabels.skip'), count: counts.skip ?? 0, tone: 'stone' },
        ]

  function switchLens(next: string) {
    if (next !== 'review' && next !== 'dry') return
    setLens(next)
    setFilter(null)
  }

  return (
    <div className="grid gap-5">
      <div className="grid gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
        {hasDry && (
          <ToggleGroup type="single" value={mode} onValueChange={switchLens} aria-label={t('review.lens')} className="self-start">
            <ToggleGroupItem value="dry">{t('review.lensDry')}</ToggleGroupItem>
            <ToggleGroupItem value="review">{t('review.lensReview')}</ToggleGroupItem>
          </ToggleGroup>
        )}
        <RowLedger
          segments={segments}
          total={job.total_rows}
          caption={
            mode === 'dry' && job.dry_run_at
              ? t('review.dryCaption', { date: formatDate(job.dry_run_at, lang === 'en' ? 'MMM d, h:mm a' : "d MMM, h:mm aaaa", lang) })
              : t('review.caption')
          }
          active={filter}
          onSelect={setFilter}
        />
      </div>

      {errors > 0 && (
        <div role="status" className="flex flex-col gap-2 rounded-lg bg-danger-soft px-4 py-3 text-[13px] text-danger-ink sm:flex-row sm:items-center sm:justify-between">
          <p className="flex gap-2">
            <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            {t('review.errors', { count: errors, formatted: formatNumber(errors, lang, 0) })}
          </p>
          <Button size="sm" variant="secondary" onClick={() => onEdit('values')} className="self-start sm:self-auto">
            {t('review.fixMapping')}
          </Button>
        </div>
      )}
      {!hasDry && ready > 0 && (
        <p className="flex gap-2 rounded-lg bg-info-soft px-4 py-3 text-[13px] leading-5 text-info-ink">
          <ShieldCheck aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t(`review.dryHint.${job.kind}`)}
        </p>
      )}

      <RowsList key={`${mode}-${filter ?? 'all'}`} job={job} mode={mode} filter={filter} />

      {start.isError && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {errorMessage(start.error, t)}
        </p>
      )}

      <div className="sticky bottom-0 z-10 -mx-4 grid gap-2 border-t border-border bg-bg/95 px-4 py-3 backdrop-blur sm:static sm:mx-0 sm:flex sm:items-center sm:justify-between sm:border-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" onClick={() => onEdit('columns')} disabled={start.isPending}>
            <ArrowLeft aria-hidden />
            {t('review.back')}
          </Button>
          <ReportMenu job={job} />
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          <Button
            variant={hasDry ? 'secondary' : 'primary'}
            onClick={() => start.mutate({ mode: 'dry_run' })}
            loading={start.isPending && start.variables?.mode === 'dry_run'}
            disabled={ready === 0 || start.isPending}
          >
            <FlaskConical aria-hidden />
            {hasDry ? t('review.dryAgain') : t('review.dry')}
          </Button>
          <Button variant={hasDry ? 'primary' : 'secondary'} onClick={() => setConfirming(true)} disabled={ready === 0 || start.isPending}>
            <Import aria-hidden />
            {t('review.run', { count: ready, formatted: formatNumber(ready, lang, 0) })}
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t('review.confirmTitle', { count: ready, formatted: formatNumber(ready, lang, 0) })}
        description={t(`review.confirm.${job.kind}`, { source: job.source_label })}
        confirmLabel={t('review.confirmButton')}
        onConfirm={() => start.mutateAsync({ mode: 'run', confirm: true })}
      >
        {!hasDry && <p className="rounded-md bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">{t('review.noDryWarning')}</p>}
      </ConfirmDialog>
    </div>
  )
}
