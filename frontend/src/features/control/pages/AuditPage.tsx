import { FileClock, Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { DateRangePicker } from '@/components/DatePicker'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { formatNumber, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { useAuditEvents, useAuditFacets, type AuditFilters } from '../api'
import { AuditEventSheet } from '../components/AuditEventSheet'
import { AuditTimeline } from '../components/AuditTimeline'
import { appLabel } from '../lib/labels'

const ALL = 'all'
const FILTER_KEYS = ['q', 'app', 'source', 'actor', 'start', 'end', 'reversible', 'reservation'] as const

/** `/app/settings/audit`: the hotel's logbook with filters (kept in the URL), detail before → after and undo. */
export default function AuditPage() {
  const { t, i18n } = useTranslation('control')
  const lang = normalizeLang(i18n.language)
  const canUndo = useCan('control.audit_undo')
  const [params, setParams] = useSearchParams()
  const filters: AuditFilters = useMemo(
    () => ({
      q: params.get('q') ?? undefined,
      app: params.get('app') ?? undefined,
      source: params.get('source') ?? undefined,
      actor: params.get('actor') ?? undefined,
      start: params.get('start') ?? undefined,
      end: params.get('end') ?? undefined,
      reversible: params.get('reversible') === '1',
      reservation: params.get('reservation') ?? undefined,
    }),
    [params],
  )
  const openId = params.get('event')
  const events = useAuditEvents(filters)
  const facets = useAuditFacets()
  const items = useMemo(() => events.data?.pages.flatMap((page) => page.results) ?? [], [events.data])
  const total = events.data?.pages[0]?.count ?? 0
  const filtered = FILTER_KEYS.some((key) => params.get(key))

  function update(changes: Record<string, string | null>) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value)
          else next.delete(key)
        }
        return next
      },
      { replace: true },
    )
  }

  function clearFilters() {
    setParams((current) => {
      const next = new URLSearchParams()
      const event = current.get('event')
      if (event) next.set('event', event)
      return next
    })
  }

  return (
    <div className="grid gap-5">
      <PageHeader
        title={t('audit.title')}
        description={t('audit.description')}
        className="pb-0"
        actions={
          events.data && (
            <span className="num text-[13px] font-semibold text-muted">{t('audit.total', { count: total, formatted: formatNumber(total, lang, 0) })}</span>
          )
        }
      />

      <section aria-label={t('audit.filters.label')} className="grid gap-3 rounded-xl border border-border bg-surface p-3 shadow-xs sm:p-4">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-[minmax(0,1.4fr)_repeat(3,minmax(0,1fr))]">
          <SearchBox value={filters.q ?? ''} onChange={(value) => update({ q: value || null })} />
          <Select name="app" value={filters.app ?? ALL} onValueChange={(value) => update({ app: value === ALL ? null : value })}>
            <SelectTrigger aria-label={t('audit.filters.app')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t('audit.filters.allApps')}</SelectItem>
              {facets.data?.apps.map((row) => (
                <SelectItem key={row.app} value={row.app}>
                  {appLabel(t, i18n, row.app)} <span className="num text-subtle">· {formatNumber(row.count, lang, 0)}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select name="source" value={filters.source ?? ALL} onValueChange={(value) => update({ source: value === ALL ? null : value })}>
            <SelectTrigger aria-label={t('audit.filters.source')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t('audit.filters.allSources')}</SelectItem>
              {facets.data?.sources.map((row) => (
                <SelectItem key={row.source} value={row.source}>
                  {t(`sources.${row.source}`)} <span className="num text-subtle">· {formatNumber(row.count, lang, 0)}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select name="actor" value={filters.actor ?? ALL} onValueChange={(value) => update({ actor: value === ALL ? null : value })}>
            <SelectTrigger aria-label={t('audit.filters.actor')}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>{t('audit.filters.allActors')}</SelectItem>
              <SelectItem value="none">{t('audit.filters.noActor')}</SelectItem>
              {facets.data?.actors.map((row) => (
                <SelectItem key={row.id} value={row.id}>
                  {row.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <DateRangePicker
            value={filters.start && filters.end ? { from: filters.start, to: filters.end } : null}
            onChange={(range) => update({ start: range?.from ?? null, end: range?.to ?? null })}
            presets={['today', 'yesterday', 'thisWeek', 'last30', 'thisMonth', 'lastMonth']}
            placeholder={t('audit.filters.dates')}
            aria-label={t('audit.filters.dates')}
            className="w-full sm:w-64"
          />
          <div className="flex items-center gap-2">
            <Switch
              id="audit-reversible"
              name="reversible"
              checked={filters.reversible ?? false}
              onCheckedChange={(checked) => update({ reversible: checked ? '1' : null })}
            />
            <Label htmlFor="audit-reversible" className="font-medium">
              {t('audit.filters.reversible')}
            </Label>
          </div>
          {filters.reservation && (
            <Badge tone="accent" className="h-7 gap-1 pr-1 pl-2.5 text-[13px]">
              {t('audit.filters.reservation')}
              <button
                type="button"
                onClick={() => update({ reservation: null })}
                aria-label={t('audit.filters.removeReservation')}
                className="grid size-5 place-items-center rounded-full hover:bg-accent/15 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
              >
                <X aria-hidden className="size-3.5" />
              </button>
            </Badge>
          )}
          {filtered && (
            <Button size="sm" variant="ghost" onClick={clearFilters} className="sm:ml-auto">
              <X aria-hidden />
              {t('audit.filters.clear')}
            </Button>
          )}
        </div>
      </section>

      {events.isPending ? (
        <LoadingState variant="rows" rows={8} className="p-0" />
      ) : events.isError ? (
        <ErrorState error={events.error} onRetry={() => void events.refetch()} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={FileClock}
          title={filtered ? t('audit.empty') : t('audit.emptyAll')}
          action={
            filtered ? (
              <Button size="sm" onClick={clearFilters}>
                {t('audit.filters.clear')}
              </Button>
            ) : undefined
          }
        />
      ) : (
        <div className="grid gap-4">
          <AuditTimeline events={items} onOpen={(id) => update({ event: id })} canUndo={canUndo} selectedId={openId} />
          {events.hasNextPage && (
            <div className="flex justify-center">
              <Button onClick={() => void events.fetchNextPage()} loading={events.isFetchingNextPage}>
                {events.isFetchingNextPage ? t('common.loadingMore') : t('common.loadMore')}
              </Button>
            </div>
          )}
        </div>
      )}

      <AuditEventSheet eventId={openId} onOpenChange={(open) => !open && update({ event: null })} onNavigate={(id) => update({ event: id })} />
    </div>
  )
}

/** Search box that updates the URL 300 ms after the last keystroke. */
function SearchBox({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation('control')
  const [draft, setDraft] = useState(value)
  const [synced, setSynced] = useState(value)
  // The URL changed from outside (e.g. "Clear filters"): show it (render-time sync, no effect needed).
  if (value !== synced) {
    setSynced(value)
    setDraft(value)
  }

  useEffect(() => {
    if (draft.trim() === value) return
    const id = window.setTimeout(() => onChange(draft.trim()), 300)
    return () => window.clearTimeout(id)
  }, [draft, value, onChange])

  return (
    <div className="relative">
      <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-subtle" />
      <Input
        type="search"
        name="q"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder={t('audit.filters.search')}
        aria-label={t('audit.filters.search')}
        className="pl-9"
      />
    </div>
  )
}
