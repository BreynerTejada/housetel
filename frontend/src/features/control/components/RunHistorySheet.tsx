import { Bot, ChevronRight, UserRound } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { formatDate, normalizeLang } from '@/lib/format'
import { useAutomationRuns, type Automation, type RunSummary } from '../api'
import { formatDuration, localized } from '../lib/labels'
import { RunStatusBadge } from './badges'

/** Every run of one automation in this hotel (newest first), with who asked for it and its technical details. */
export function RunHistorySheet({ automation, open, onOpenChange }: { automation: Automation | null; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t, i18n } = useTranslation('control')
  const name = automation ? localized(automation.name, i18n.language) : ''
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[min(32rem,100vw)]">
        <SheetHeader>
          <SheetTitle>{t('automations.historySheet.title', { name })}</SheetTitle>
          <SheetDescription>{t('automations.historySheet.description')}</SheetDescription>
        </SheetHeader>
        <SheetBody className="p-0">{automation && <RunList code={automation.code} />}</SheetBody>
      </SheetContent>
    </Sheet>
  )
}

function RunList({ code }: { code: string }) {
  const { t } = useTranslation('control')
  const runs = useAutomationRuns(code)
  if (runs.isPending) return <LoadingState variant="rows" rows={6} />
  if (runs.isError) return <ErrorState error={runs.error} onRetry={() => void runs.refetch()} />
  const items = runs.data.pages.flatMap((page) => page.results)
  if (!items.length) return <EmptyState icon={Bot} title={t('automations.historySheet.empty')} />
  return (
    <div className="grid">
      <ol className="divide-y divide-border">
        {items.map((run) => (
          <RunItem key={run.id} run={run} />
        ))}
      </ol>
      {runs.hasNextPage && (
        <div className="flex justify-center p-4">
          <Button size="sm" onClick={() => void runs.fetchNextPage()} loading={runs.isFetchingNextPage}>
            {runs.isFetchingNextPage ? t('common.loadingMore') : t('common.loadMore')}
          </Button>
        </div>
      )}
    </div>
  )
}

function RunItem({ run }: { run: RunSummary }) {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const hasDetails = run.details && Object.keys(run.details).length > 0
  return (
    <li className="grid gap-1.5 px-5 py-3.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <RunStatusBadge status={run.status} />
        <time dateTime={run.started_at} className="num text-[13px] font-semibold text-fg">
          {formatDate(run.started_at, lang === 'en' ? 'MMM d, yyyy · HH:mm' : "d MMM yyyy '·' HH:mm", lang)}
        </time>
        <span className="num text-xs text-muted">{t('automations.historySheet.duration', { value: formatDuration(run.duration_ms, t, lang) })}</span>
      </div>
      {run.summary && <p className="text-[13px] break-words text-fg/85">{run.summary}</p>}
      <p className="flex items-center gap-1.5 text-xs text-muted">
        {run.triggered_by ? <UserRound aria-hidden className="size-3.5" /> : <Bot aria-hidden className="size-3.5" />}
        {run.triggered_by ? t('automations.historySheet.triggeredBy', { name: run.triggered_by.name }) : t('automations.historySheet.byBeat')}
      </p>
      {hasDetails && (
        <details className="group">
          <summary className="flex w-fit cursor-pointer list-none items-center gap-1 rounded-sm text-xs font-semibold text-muted hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 [&::-webkit-details-marker]:hidden">
            <ChevronRight aria-hidden className="size-3.5 transition-transform group-open:rotate-90" />
            {t('automations.historySheet.details')}
          </summary>
          <pre className="num mt-2 max-h-64 overflow-auto rounded-md border border-border bg-surface-2 p-2.5 text-[11px] leading-4 whitespace-pre-wrap text-fg/85">
            {JSON.stringify(run.details, null, 2)}
          </pre>
        </details>
      )}
    </li>
  )
}
