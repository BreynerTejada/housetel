import { ChevronLeft, ChevronRight, CircleAlert, CircleSlash, Info, Search, SquareArrowOutUpRight, TriangleAlert, Undo2, X } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatDateRange, formatNumber, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useImportRows, type DryOutcome, type ImportRow, type JobDetail, type RowFilters, type RowIssue, type RowOutcome, type RowStatus } from '../api'
import { describeRow, targetPath, text } from '../lib/fields'
import { DryOutcomeBadge, OutcomeBadge, RowStatusBadge } from './badges'

export type RowsMode = 'review' | 'dry' | 'result'

const PAGE_SIZE = 25
const LEVELS: RowIssue['level'][] = ['error', 'skip', 'warning', 'info']
/** Keys the importer builds when the file has no id (fingerprint, document, email): not worth showing. */
const INTERNAL_ID = /^(fp-|doc:|email:)/

const ISSUE_ICON = {
  error: CircleAlert,
  warning: TriangleAlert,
  skip: CircleSlash,
  info: Info,
} as const

const ISSUE_TONE = {
  error: 'text-danger-ink',
  warning: 'text-warning-ink',
  skip: 'text-stone-ink',
  info: 'text-muted',
} as const

function filtersFor(mode: RowsMode, filter: string | null): RowFilters {
  if (!filter) return {}
  if (mode === 'review') return { status: [filter as RowStatus] }
  if (mode === 'dry') return { dry_outcome: [filter as DryOutcome] }
  return { outcome: [filter as RowOutcome] }
}

/**
 * The rows of the file with what happens to each: its review issues, its dry-run result or what the import
 * created (with a link to it). Mount it with `key={filter}` so a new filter starts on the first page.
 */
export function RowsList({ job, mode, filter }: { job: JobDetail; mode: RowsMode; filter: string | null }) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const [page, setPage] = useState(1)
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const version = [job.status, job.dry_run_at, job.finished_at, job.reverted_at].join('|')
  const rows = useImportRows(job.id, { ...filtersFor(mode, filter), q: query || undefined, page }, { version })
  const count = rows.data?.count ?? 0
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE))
  const range = (start: string, end: string) => formatDateRange(start, end, lang)

  function search(event: FormEvent) {
    event.preventDefault()
    setPage(1)
    setQuery(draft.trim())
  }

  return (
    <section aria-label={t('rows.label')} className="overflow-hidden rounded-xl border border-border bg-surface shadow-xs">
      <div className="flex flex-col gap-2 border-b border-border px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <p className="num text-[13px] font-semibold text-muted">
          {filter ? t('rows.filtered', { count, formatted: formatNumber(count, lang, 0) }) : t('rows.all', { count, formatted: formatNumber(count, lang, 0) })}
        </p>
        <form role="search" onSubmit={search} className="relative w-full sm:w-64">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-subtle" />
          <Input
            type="search"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder={t('rows.search')}
            aria-label={t('rows.search')}
            className="h-8 pr-8 pl-8 text-[13px]"
          />
          {query && (
            <button
              type="button"
              onClick={() => {
                setDraft('')
                setQuery('')
                setPage(1)
              }}
              aria-label={t('rows.clearSearch')}
              className="absolute top-1/2 right-1.5 grid size-6 -translate-y-1/2 place-items-center rounded-sm text-muted hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
            >
              <X aria-hidden className="size-3.5" />
            </button>
          )}
        </form>
      </div>

      {rows.isPending ? (
        <LoadingState variant="rows" rows={5} />
      ) : rows.isError ? (
        <ErrorState error={rows.error} onRetry={() => void rows.refetch()} />
      ) : rows.data.results.length === 0 ? (
        <EmptyState title={query ? t('rows.noMatch') : t('rows.none')} className="py-10" />
      ) : (
        <ul className={cn('divide-y divide-border transition-opacity', rows.isPlaceholderData && 'opacity-60')}>
          {rows.data.results.map((row) => (
            <li key={row.id}>
              <RowItem row={row} job={job} mode={mode} range={range} />
            </li>
          ))}
        </ul>
      )}

      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 border-t border-border px-4 py-2.5 sm:px-5">
          <span className="num text-[13px] text-muted">{t('rows.page', { page, pages })}</span>
          <Button size="icon-sm" variant="secondary" aria-label={t('rows.previous')} disabled={page <= 1} onClick={() => setPage(page - 1)}>
            <ChevronLeft aria-hidden />
          </Button>
          <Button size="icon-sm" variant="secondary" aria-label={t('rows.next')} disabled={page >= pages} onClick={() => setPage(page + 1)}>
            <ChevronRight aria-hidden />
          </Button>
        </div>
      )}
    </section>
  )
}

function IssueLine({ issue, lang }: { issue: RowIssue; lang: 'es' | 'en' }) {
  const Icon = ISSUE_ICON[issue.level] ?? Info
  return (
    <li className={cn('flex gap-1.5 text-[13px] leading-5', ISSUE_TONE[issue.level] ?? 'text-muted')}>
      <Icon aria-hidden className="mt-[3px] size-3.5 shrink-0" />
      <span className="min-w-0">{text(issue, lang)}</span>
    </li>
  )
}

function RowItem({
  row,
  job,
  mode,
  range,
}: {
  row: ImportRow
  job: JobDetail
  mode: RowsMode
  range: (start: string, end: string) => string
}) {
  const { t, i18n } = useTranslation('imports')
  const lang = normalizeLang(i18n.language)
  const { title, detail } = describeRow(job.kind, row, job.headers, range)
  const link = mode === 'result' ? targetPath(row) : null
  const message =
    mode === 'dry' ? text(row.dry_message, lang) : mode === 'result' ? text(row.outcome_message, lang) : ''
  // the result message often repeats the issue that decided it (skipped, failed): shown once
  const issues = (row.issues ?? []).filter(
    (issue) => (mode === 'review' || issue.level !== 'info') && text(issue, lang) !== message,
  )
  const ordered = [...issues].sort((a, b) => LEVELS.indexOf(a.level) - LEVELS.indexOf(b.level))
  const revertNote = mode === 'result' && row.revert ? text(row.revert, lang) : ''

  return (
    <div className="grid gap-2 px-4 py-3 sm:grid-cols-[5.5rem_minmax(0,1fr)_auto] sm:gap-4 sm:px-5">
      <div className="flex items-baseline gap-2 sm:block">
        <span className="num text-xs font-semibold text-muted">{t('rows.row', { number: row.number })}</span>
        {row.external_id && !INTERNAL_ID.test(row.external_id) && (
          <span className="num block truncate text-xs text-subtle" title={row.external_id}>
            {row.external_id}
          </span>
        )}
      </div>
      <div className="min-w-0">
        <p className="truncate font-semibold text-fg">{title || t('rows.noData')}</p>
        {detail && <p className="num truncate text-[13px] text-muted">{detail}</p>}
        {message && <p className="mt-1 text-[13px] leading-5 text-fg">{message}</p>}
        {revertNote && (
          <p className="mt-1 flex gap-1.5 text-[13px] leading-5 text-stone-ink">
            <Undo2 aria-hidden className="mt-[3px] size-3.5 shrink-0" />
            {revertNote}
          </p>
        )}
        {ordered.length > 0 && (
          <ul className="mt-1.5 grid gap-0.5">
            {ordered.map((issue, index) => (
              <IssueLine key={`${issue.code}-${index}`} issue={issue} lang={lang} />
            ))}
          </ul>
        )}
      </div>
      <div className="flex flex-wrap items-start gap-2 sm:flex-col sm:items-end">
        {mode === 'review' && <RowStatusBadge status={row.status} />}
        {mode === 'dry' && (row.dry_outcome ? <DryOutcomeBadge outcome={row.dry_outcome} /> : <RowStatusBadge status={row.status} />)}
        {mode === 'result' && (row.outcome ? <OutcomeBadge outcome={row.outcome} /> : <RowStatusBadge status={row.status} />)}
        {link && (
          <Link
            to={link}
            className="inline-flex items-center gap-1 rounded-sm text-[13px] font-semibold text-accent-ink hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
          >
            {row.target_label || t('rows.open')}
            <SquareArrowOutUpRight aria-hidden className="size-3.5" />
          </Link>
        )}
      </div>
    </div>
  )
}

