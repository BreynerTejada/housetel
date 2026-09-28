import { ChevronLeft, ChevronRight, LayoutGrid, ListChecks, Rows3, Tags } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { useLocalStorageState } from '@/lib/hooks'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useDecision, useRevenueCalendar, useRevenueSummary, type Decision } from '../api'
import { addDays } from '../lib/dates'
import { buildHeatmap, pruneSelection, toggleIds } from '../lib/heatmap'
import { Heatmap } from './Heatmap'
import { HeatmapLegend } from './HeatmapLegend'
import { LastRunCard } from './LastRunCard'
import { RecommendationDetail } from './RecommendationDetail'
import { RecommendationList } from './RecommendationList'
import { SelectionBar } from './SelectionBar'
import { SummaryTiles } from './SummaryTiles'

const SPANS = [14, 30, 60] as const
type View = 'map' | 'list'

/**
 * The recommendations of the property from its business date: KPIs, the last run's summary, the heatmap (or
 * its list twin), the detail of the night in focus and the mass decision bar.
 */
export function RecommendationsPanel({ today }: { today: string }) {
  const { t, i18n } = useTranslation('revenue')
  const lang = normalizeLang(i18n.language)
  const canManage = useCan('revenue.manage')

  const [start, setStart] = useState(today)
  const [storedSpan, setSpan] = useLocalStorageState<number>('housetel.revenue.span', 30)
  const span = (SPANS as readonly number[]).includes(storedSpan) ? storedSpan : 30
  const [showDecided, setShowDecided] = useLocalStorageState('housetel.revenue.showDecided', true)
  const [storedView, setView] = useLocalStorageState<View>('housetel.revenue.view', 'map')
  const view: View = storedView === 'list' ? 'list' : 'map'
  const [activeId, setActiveId] = useState<string | null>(null)
  const [selection, setSelection] = useState<Set<string>>(() => new Set())
  const end = addDays(start, span)

  const summary = useRevenueSummary()
  const calendar = useRevenueCalendar({ start, end, lang })
  const decision = useDecision()
  const deciding = decision.isPending ? (decision.variables?.decision ?? null) : null

  const model = useMemo(() => (calendar.data ? buildHeatmap(calendar.data, { showDecided }) : null), [calendar.data, showDecided])
  const selected = useMemo(() => (model ? pruneSelection(selection, model) : new Set<string>()), [model, selection])
  const currency = calendar.data?.currency ?? summary.data?.currency ?? 'COP'

  const direction = useMemo(() => {
    let up = 0
    let down = 0
    for (const row of model?.rows ?? []) {
      for (const { cell } of row.cells) {
        if (!cell || !selected.has(cell.id)) continue
        if (Number(cell.change_percent) > 0) up += 1
        else down += 1
      }
    }
    return { up, down }
  }, [model, selected])

  function toggle(ids: string[]) {
    setSelection((current) => toggleIds(pruneSelection(current, model ?? { columns: [], rows: [], pendingIds: [], manyPlans: false }), ids))
  }

  function decide(kind: Decision, ids: string[]) {
    decision.mutate(
      { decision: kind, ids },
      {
        onSuccess: (result) => {
          setSelection(new Set())
          // An approval that could not be written stays "approved": it is reported as an error, not as applied.
          const done =
            kind === 'reject'
              ? result.updated
              : result.recommendations.filter((rec) => rec.status === 'applied' || rec.status === 'auto_applied').length
          if (done) toast.success(t(`decide.done.${kind}`, { count: done }))
          if (result.errors.length) {
            toast.error(t('decide.errors', { count: result.errors.length, detail: result.errors[0].detail }))
          }
          if (result.skipped.length) toast(t('decide.skipped', { count: result.skipped.length }))
        },
        onError: (error) => toast.error(errorMessage(error, t)),
      },
    )
  }

  return (
    <div className="grid gap-5">
      <SummaryTiles summary={summary.data} />
      <LastRunCard run={summary.data?.last_run} today={today} />

      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex items-center gap-1">
          <Button
            size="icon"
            aria-label={t('toolbar.previous', { count: span })}
            onClick={() => setStart(addDays(start, -span) < today ? today : addDays(start, -span))}
            disabled={start <= today}
          >
            <ChevronLeft aria-hidden />
          </Button>
          <p className="num min-w-40 px-1 text-center text-sm font-semibold text-fg" aria-live="polite">
            {formatDateRange(start, addDays(end, -1), lang)}
          </p>
          <Button size="icon" aria-label={t('toolbar.next', { count: span })} onClick={() => setStart(addDays(start, span))}>
            <ChevronRight aria-hidden />
          </Button>
          <Button variant="ghost" onClick={() => setStart(today)} disabled={start === today}>
            {t('toolbar.today')}
          </Button>
        </div>
        <ToggleGroup type="single" value={String(span)} onValueChange={(value) => value && setSpan(Number(value))} aria-label={t('toolbar.span')}>
          {SPANS.map((value) => (
            <ToggleGroupItem key={value} value={String(value)} className="px-2 whitespace-nowrap sm:px-2.5">
              {t('toolbar.spanNights', { count: value })}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
        <ToggleGroup type="single" value={view} onValueChange={(value) => value && setView(value as View)} aria-label={t('toolbar.view')}>
          <ToggleGroupItem value="map">
            <LayoutGrid aria-hidden />
            {t('toolbar.map')}
          </ToggleGroupItem>
          <ToggleGroupItem value="list">
            <Rows3 aria-hidden />
            {t('toolbar.list')}
          </ToggleGroupItem>
        </ToggleGroup>
        <label className="flex h-9 items-center gap-2 text-[13px] font-semibold text-fg">
          <Switch checked={showDecided} onCheckedChange={setShowDecided} />
          {t('toolbar.showDecided')}
        </label>
        {canManage && model && (
          <Button
            size="sm"
            className="sm:ml-auto"
            onClick={() => setSelection(new Set(model.pendingIds))}
            disabled={model.pendingIds.length === 0 || selected.size === model.pendingIds.length}
          >
            <ListChecks aria-hidden />
            {t('toolbar.selectAll', { count: model.pendingIds.length })}
          </Button>
        )}
      </div>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className={cn('grid min-w-0 gap-3 transition-opacity', calendar.isFetching && calendar.isPlaceholderData && 'opacity-60')}>
          {calendar.isPending ? (
            <LoadingState variant="rows" rows={5} />
          ) : calendar.isError ? (
            <ErrorState error={calendar.error} onRetry={() => void calendar.refetch()} />
          ) : !model || model.rows.length === 0 ? (
            <EmptyState
              icon={Tags}
              title={t('map.noRows')}
              description={t('map.noRowsHint')}
              action={
                <Button asChild>
                  <Link to="/app/rates/plans">{t('map.openPlans')}</Link>
                </Button>
              }
            />
          ) : (
            <>
              {view === 'map' ? (
                <Heatmap
                  model={model}
                  currency={currency}
                  selected={selected}
                  activeId={activeId}
                  canSelect={canManage}
                  onToggle={toggle}
                  onActivate={setActiveId}
                />
              ) : (
                <RecommendationList
                  model={model}
                  currency={currency}
                  selected={selected}
                  activeId={activeId}
                  canSelect={canManage}
                  onToggle={toggle}
                  onActivate={setActiveId}
                />
              )}
              {model.pendingIds.length === 0 && <p className="text-sm text-muted">{t('map.nothingPending')}</p>}
              <HeatmapLegend />
            </>
          )}
        </div>
        <RecommendationDetail
          id={activeId}
          currency={currency}
          canManage={canManage}
          pending={deciding}
          onDecide={decide}
          className="xl:sticky xl:top-4"
        />
      </div>

      {canManage && selected.size > 0 && (
        <SelectionBar
          count={selected.size}
          up={direction.up}
          down={direction.down}
          pending={deciding}
          onDecide={(kind) => decide(kind, [...selected])}
          onClear={() => setSelection(new Set())}
        />
      )}
    </div>
  )
}
