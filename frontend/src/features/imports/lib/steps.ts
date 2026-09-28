import type { JobDetail } from '../api'

/** The six steps of the importer wizard (the first two live on `/app/settings/import`). */
export type WizardStep = 'kind' | 'file' | 'map' | 'review' | 'import' | 'result'
export const WIZARD_STEPS: WizardStep[] = ['kind', 'file', 'map', 'review', 'import', 'result']

/** Screens of a job page: the mapping has two panels (columns, then values and options). */
export type JobView = 'columns' | 'values' | 'review' | 'progress' | 'result'

const VIEWS: JobView[] = ['columns', 'values', 'review', 'progress', 'result']

export function isJobView(value: string | null): value is JobView {
  return value !== null && (VIEWS as string[]).includes(value)
}

/** Where a job is, from its status; `wanted` (the URL's `?step=`) only applies while the mapping can change. */
export function resolveView(job: JobDetail, wanted: JobView | null): JobView {
  if (job.status === 'queued' || job.status === 'running') return 'progress'
  if (job.status === 'completed' || job.status === 'failed' || job.status === 'reverted') return 'result'
  if (job.status === 'uploaded') return wanted === 'values' && Object.keys(job.mapping).length ? 'values' : 'columns'
  // validated
  if (wanted === 'columns' || wanted === 'values') return wanted
  return 'review'
}

/** The stepper's step for a view (a dry-run in progress belongs to "review"; a rollback to "result"). */
export function stepOf(view: JobView, job: JobDetail): WizardStep {
  if (view === 'columns' || view === 'values') return 'map'
  if (view === 'review') return 'review'
  if (view === 'progress') return job.phase === 'dry_run' ? 'review' : job.phase === 'revert' ? 'result' : 'import'
  return 'result'
}
