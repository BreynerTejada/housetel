import { Lock, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { formatNumber, formatRelative, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useDeleteImport, useImportJob, type JobDetail } from '../api'
import { JobStatusBadge } from '../components/badges'
import { ImportStepper } from '../components/ImportStepper'
import { MapColumnsView } from '../components/MapColumnsView'
import { MapValuesView } from '../components/MapValuesView'
import { ProgressView } from '../components/ProgressView'
import { ResultView } from '../components/ResultView'
import { ReviewView } from '../components/ReviewView'
import { isJobView, resolveView, stepOf, type JobView, type WizardStep } from '../lib/steps'

/**
 * `/app/settings/import/:jobId`: one import, from the mapping to the result. The screen follows the job's status
 * (the worker's progress is polled); while the mapping can change, `?step=columns|values|review` keeps the place.
 */
export default function ImportJobPage() {
  const { t } = useTranslation('imports')
  const { jobId } = useParams()
  const canImport = useCan('imports.run')
  const job = useImportJob(canImport ? jobId : undefined)

  if (!canImport) {
    return (
      <div className="grid gap-5">
        <PageHeader title={t('page.title')} className="pb-0" />
        <EmptyState icon={Lock} title={t('page.forbidden')} description={t('page.forbiddenHint')} />
      </div>
    )
  }
  if (job.isPending) return <LoadingState className="py-20" />
  if (job.isError) {
    return (
      <div className="grid gap-4">
        <PageHeader title={t('page.title')} breadcrumbs={[{ label: t('page.title'), to: '/app/settings/import' }]} className="pb-0" />
        <ErrorState error={job.error} onRetry={() => void job.refetch()} />
        <div className="flex justify-center">
          <Button asChild variant="secondary">
            <Link to="/app/settings/import">{t('job.backToImports')}</Link>
          </Button>
        </div>
      </div>
    )
  }
  return <JobScreen job={job.data} />
}

function JobScreen({ job }: { job: JobDetail }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const [discarding, setDiscarding] = useState(false)
  const remove = useDeleteImport()
  const wanted = params.get('step')
  const view = resolveView(job, isJobView(wanted) ? wanted : null)
  const step = stepOf(view, job)
  const editable = job.can_edit

  function go(next: JobView) {
    setParams(
      (current) => {
        const copy = new URLSearchParams(current)
        copy.set('step', next)
        return copy
      },
      { replace: true },
    )
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function goStep(target: WizardStep) {
    if (target === 'kind' || target === 'file') navigate('/app/settings/import')
    else if (target === 'map') go('columns')
    else if (target === 'review') go('review')
  }

  const reachable: WizardStep[] = editable
    ? ['kind', 'file', 'map', ...(job.status === 'validated' ? (['review'] as WizardStep[]) : [])]
    : []
  const meta = [
    job.filename,
    job.source_label,
    t('history.rows', { count: job.total_rows, formatted: formatNumber(job.total_rows, lang, 0) }),
    job.created_by ? t('job.uploadedBy', { name: job.created_by.name, when: formatRelative(job.created_at, lang) }) : formatRelative(job.created_at, lang),
  ]

  return (
    <div className="grid gap-6">
      <PageHeader
        breadcrumbs={[{ label: t('page.title'), to: '/app/settings/import' }, { label: job.filename }]}
        title={t(`kinds.${job.kind}.title`)}
        description={meta.join(' · ')}
        className="pb-0"
        actions={
          <>
            <JobStatusBadge status={job.status} phase={job.phase} stale={job.stale} />
            {job.can_delete && (
              <Button size="sm" variant="ghost" onClick={() => setDiscarding(true)}>
                <Trash2 aria-hidden />
                {t('job.discard')}
              </Button>
            )}
          </>
        }
      />
      <ImportStepper current={step} onGo={goStep} reachable={reachable} />

      {job.data_purged && (
        <p className="rounded-lg bg-stone-soft px-4 py-3 text-[13px] leading-5 text-stone-ink">{t('job.purged')}</p>
      )}

      {view === 'columns' && <MapColumnsView key={`columns-${job.id}`} job={job} onNext={() => go('values')} />}
      {view === 'values' && <MapValuesView key={`values-${job.id}`} job={job} onBack={() => go('columns')} onNext={() => go('review')} />}
      {view === 'review' && <ReviewView key={`review-${job.id}-${job.dry_run_at ?? 'none'}`} job={job} onEdit={go} />}
      {view === 'progress' && <ProgressView job={job} />}
      {view === 'result' && <ResultView key={`result-${job.id}-${job.status}`} job={job} />}

      <ConfirmDialog
        open={discarding}
        onOpenChange={setDiscarding}
        title={t('job.discardTitle')}
        description={t('job.discardDescription', { name: job.filename })}
        confirmLabel={t('job.discard')}
        onConfirm={async () => {
          await remove.mutateAsync(job.id)
          navigate('/app/settings/import')
        }}
      />
    </div>
  )
}
