import { Hourglass, LoaderCircle, RotateCcw, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/errors'
import { formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useStartImport, type JobDetail } from '../api'

/**
 * The worker is on it (dry-run, import or rollback): the page polls every second. A job nobody picked up, or
 * whose worker stopped reporting, can be launched again — the import resumes where it stopped.
 */
export function ProgressView({ job }: { job: JobDetail }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const start = useStartImport(job.id)
  const phase = job.phase || 'run'
  const queued = job.status === 'queued'
  const { done, total } = job.progress
  const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0
  const unit = t(`progress.units.${phase === 'revert' ? 'revert' : job.kind}`, { count: total })

  return (
    <section
      aria-labelledby="import-progress"
      className="grid gap-5 rounded-xl border border-border bg-surface p-5 shadow-xs sm:p-6"
    >
      <div className="flex items-start gap-3">
        <span
          aria-hidden
          className={cn(
            'grid size-10 shrink-0 place-items-center rounded-xl border',
            job.stale ? 'border-warning/40 bg-warning-soft text-warning-ink' : 'border-accent/30 bg-accent-soft text-accent-ink',
          )}
        >
          {job.stale ? <TriangleAlert className="size-5" /> : queued ? <Hourglass className="size-5" /> : <LoaderCircle className="size-5 animate-spin" />}
        </span>
        <div className="min-w-0">
          <h2 id="import-progress" className="text-[17px] font-bold tracking-[-0.02em] text-fg">
            {t(`progress.title.${phase}`, { kind: t(`kinds.${job.kind}.noun`) })}
          </h2>
          <p className="mt-0.5 text-[13px] text-muted">
            {job.stale ? t('progress.stale') : queued ? t('progress.queued') : t(`progress.hint.${phase}`)}
          </p>
        </div>
      </div>

      <div className="grid gap-2">
        <div aria-live="polite" className="flex items-baseline justify-between gap-3">
          <p className="num text-2xl font-bold tracking-[-0.02em] text-fg">
            {formatNumber(done, lang, 0)}
            <span className="text-base font-semibold text-muted"> / {formatNumber(total, lang, 0)}</span>
          </p>
          <p className="num text-[13px] font-semibold text-muted">
            {unit} · {percent} %
          </p>
        </div>
        <div
          role="progressbar"
          aria-label={t('progress.label')}
          aria-valuemin={0}
          aria-valuemax={total || 1}
          aria-valuenow={done}
          className="h-3 w-full overflow-hidden rounded-full bg-surface-3"
        >
          <div
            className={cn('h-full rounded-full transition-[width] duration-700 ease-out', job.stale ? 'bg-warning' : 'bg-accent', queued && 'animate-shimmer')}
            style={{ width: `${queued ? 4 : Math.max(percent, 2)}%` }}
          />
        </div>
      </div>

      <p className="text-xs leading-5 text-muted">{t('progress.leave')}</p>

      {job.stale && (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            onClick={() => start.mutate({ mode: phase, confirm: phase !== 'dry_run' })}
            loading={start.isPending}
          >
            <RotateCcw aria-hidden />
            {t('progress.relaunch')}
          </Button>
          {start.isError && <p role="alert" className="text-sm text-danger-ink">{errorMessage(start.error, t)}</p>}
        </div>
      )}
    </section>
  )
}
