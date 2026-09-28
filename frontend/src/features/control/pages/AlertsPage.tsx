import { BellOff, Check, CircleCheck, Search, SearchX } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { formatNumber, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useAlertCount, useAlerts, useResolveAlerts, type AlertFilters, type Severity } from '../api'
import { AlertCard } from '../components/AlertCard'
import { SeverityDot } from '../components/severity'

const SEVERITIES: Severity[] = ['critical', 'warning', 'info']

/** `/app/alerts`: open alerts (most severe first) and the resolved ones, with search, severity and bulk resolve. */
export default function AlertsPage() {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const canResolve = useCan('control.alerts')
  const [params, setParams] = useSearchParams()
  const status: AlertFilters['status'] = params.get('status') === 'resolved' ? 'resolved' : 'open'
  const severityParam = params.get('severity')
  const severity = SEVERITIES.includes(severityParam as Severity) ? (severityParam as Severity) : ''
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const filters: AlertFilters = useMemo(() => ({ status, severity, q }), [status, severity, q])
  const alerts = useAlerts(filters)
  const counts = useAlertCount()
  const resolve = useResolveAlerts()
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [resolvingId, setResolvingId] = useState<string | null>(null)
  const items = useMemo(() => alerts.data?.pages.flatMap((page) => page.results) ?? [], [alerts.data])
  const total = alerts.data?.pages[0]?.count ?? 0
  const visibleSelected = items.filter((item) => selected.has(item.id)).map((item) => item.id)

  useEffect(() => {
    const id = window.setTimeout(() => setQ(search.trim()), 300)
    return () => window.clearTimeout(id)
  }, [search])

  function setParam(key: string, value: string | null) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set(key, value)
        else next.delete(key)
        return next
      },
      { replace: true },
    )
    setSelected(new Set())
  }

  async function resolveIds(ids: string[]) {
    if (!ids.length) return
    setResolvingId(ids.length === 1 ? ids[0] : null)
    try {
      const result = await resolve.mutateAsync(ids)
      toast.success(ids.length === 1 ? t('alerts.toasts.resolved') : t('alerts.toasts.resolvedMany', { count: result.resolved }))
      setSelected((current) => {
        const next = new Set(current)
        for (const id of ids) next.delete(id)
        return next
      })
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setResolvingId(null)
    }
  }

  const openCount = counts.data?.open
  const filtered = Boolean(severity || q)

  return (
    <div className="mx-auto grid w-full max-w-4xl gap-5">
      <PageHeader title={t('alerts.title')} description={t('alerts.description')} className="pb-0" />

      <Tabs value={status} onValueChange={(value) => setParam('status', value === 'resolved' ? 'resolved' : null)}>
        <TabsList>
          <TabsTrigger value="open">
            {t('alerts.tabs.open')}
            {openCount !== undefined && (
              <span className="num rounded-full bg-surface-2 px-1.5 text-xs font-bold text-fg">{formatNumber(openCount, lang, 0)}</span>
            )}
          </TabsTrigger>
          <TabsTrigger value="resolved">{t('alerts.tabs.resolved')}</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative sm:w-72">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
          <Input
            type="search"
            name="q"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t('alerts.search')}
            aria-label={t('alerts.search')}
            className="pl-9"
          />
        </div>
        <ToggleGroup
          type="single"
          value={severity || 'all'}
          onValueChange={(value) => value && setParam('severity', value === 'all' ? null : value)}
          aria-label={t('alerts.severityFilter')}
          className="self-start overflow-x-auto sm:self-auto"
        >
          <ToggleGroupItem value="all">{t('severityPlural.all')}</ToggleGroupItem>
          {SEVERITIES.map((item) => (
            <ToggleGroupItem key={item} value={item}>
              <SeverityDot severity={item} />
              {t(`severityPlural.${item}`)}
              {status === 'open' && counts.data && (
                <span className="num text-xs text-subtle">{formatNumber(counts.data.by_severity[item], lang, 0)}</span>
              )}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      {status === 'open' && canResolve && items.length > 0 && (
        <div className="flex min-h-9 flex-wrap items-center gap-3 px-1">
          <label className="flex items-center gap-2 text-[13px] font-medium text-muted">
            <Checkbox
              checked={visibleSelected.length === 0 ? false : visibleSelected.length === items.length ? true : 'indeterminate'}
              onCheckedChange={(checked) => setSelected(checked === true ? new Set(items.map((item) => item.id)) : new Set())}
              aria-label={t('alerts.selectAll')}
            />
            {t('alerts.selectAll')}
          </label>
          {visibleSelected.length > 0 && (
            <>
              <Button size="sm" variant="primary" onClick={() => void resolveIds(visibleSelected)} loading={resolve.isPending && resolvingId === null}>
                {!(resolve.isPending && resolvingId === null) && <Check aria-hidden />}
                {t('alerts.resolveSelected', { count: visibleSelected.length })}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
                {t('alerts.clearSelection')}
              </Button>
            </>
          )}
          <span className="num ml-auto text-xs text-subtle">{t('alerts.showing', { shown: items.length, total })}</span>
        </div>
      )}

      {alerts.isPending ? (
        <LoadingState variant="rows" rows={5} className="p-0" />
      ) : alerts.isError ? (
        <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />
      ) : items.length === 0 ? (
        filtered ? (
          <EmptyState icon={SearchX} title={t('alerts.emptyFiltered')} />
        ) : status === 'open' ? (
          <EmptyState icon={CircleCheck} title={t('alerts.emptyOpen')} description={t('alerts.emptyOpenHint')} />
        ) : (
          <EmptyState icon={BellOff} title={t('alerts.emptyResolved')} />
        )
      ) : (
        <div className="grid gap-2.5">
          {items.map((alert) => (
            <AlertCard
              key={alert.id}
              alert={alert}
              canResolve={canResolve}
              selected={selected.has(alert.id)}
              onSelectedChange={
                canResolve && status === 'open'
                  ? (checked) =>
                      setSelected((current) => {
                        const next = new Set(current)
                        if (checked) next.add(alert.id)
                        else next.delete(alert.id)
                        return next
                      })
                  : undefined
              }
              onResolve={() => void resolveIds([alert.id])}
              resolving={resolvingId === alert.id}
            />
          ))}
          {alerts.hasNextPage && (
            <div className="flex justify-center pt-2">
              <Button onClick={() => void alerts.fetchNextPage()} loading={alerts.isFetchingNextPage}>
                {alerts.isFetchingNextPage ? t('common.loadingMore') : t('common.loadMore')}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
