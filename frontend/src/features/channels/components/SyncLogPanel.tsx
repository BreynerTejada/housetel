import { ArrowDownLeft, ArrowUpRight, ChevronLeft, ChevronRight, ExternalLink, ScrollText } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { formatDate, formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useSyncLogs, type Connection, type LogDirection, type LogStatus, type SyncLogEntry } from '../api'
import { LOG_STATUS_TONE, logKindKey } from '../lib/labels'
import { ChannelMark } from './ChannelMark'

const ALL = '__all'
const PAGE_SIZE = 25

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

/** What went in (bookings, calendars) and out (prices and availability) of every connection, newest first. */
export function SyncLogPanel({ connections }: { connections: Connection[] }) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const [connection, setConnection] = useState('')
  const [direction, setDirection] = useState<LogDirection | ''>('')
  const [status, setStatus] = useState<LogStatus | ''>('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<SyncLogEntry | null>(null)
  const q = useDebounced(search.trim())

  const query = useSyncLogs({ connection: connection || undefined, direction, status, q: q || undefined, page }, { refetchInterval: 15_000 })
  const data = query.data
  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1

  function reset<T>(setter: (value: T) => void) {
    return (value: T) => {
      setter(value)
      setPage(1)
    }
  }

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={connection || ALL} onValueChange={(value) => reset(setConnection)(value === ALL ? '' : value)}>
          <SelectTrigger className="h-8 w-full sm:w-52" aria-label={t('log.connection')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('log.allConnections')}</SelectItem>
            {connections.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <ToggleGroup
          type="single"
          value={direction || ALL}
          onValueChange={(value) => value && reset(setDirection)(value === ALL ? '' : (value as LogDirection))}
          aria-label={t('log.direction')}
        >
          <ToggleGroupItem value={ALL}>{t('log.both')}</ToggleGroupItem>
          <ToggleGroupItem value="out">
            <ArrowUpRight aria-hidden /> {t('log.out')}
          </ToggleGroupItem>
          <ToggleGroupItem value="in">
            <ArrowDownLeft aria-hidden /> {t('log.in')}
          </ToggleGroupItem>
        </ToggleGroup>
        <Select value={status || ALL} onValueChange={(value) => reset(setStatus)(value === ALL ? '' : (value as LogStatus))}>
          <SelectTrigger className="h-8 w-[calc(50%-0.25rem)] sm:w-48" aria-label={t('log.statusFilter')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('log.allStatuses')}</SelectItem>
            {(['success', 'warning', 'error', 'skipped'] as const).map((value) => (
              <SelectItem key={value} value={value}>
                {t(`log.status.${value}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          type="search"
          name="search"
          value={search}
          onChange={(event) => {
            setSearch(event.target.value)
            setPage(1)
          }}
          placeholder={t('log.search')}
          aria-label={t('log.search')}
          className="h-8 w-[calc(50%-0.25rem)] sm:ml-auto sm:w-64"
        />
      </div>

      <div className={cn('overflow-hidden rounded-lg border border-border bg-surface shadow-xs', query.isFetching && data && 'opacity-80')}>
        {query.isPending ? (
          <LoadingState variant="rows" rows={6} />
        ) : query.isError && !query.data ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState icon={ScrollText} title={t('log.empty')} description={t('log.emptyHint')} />
        ) : (
          <ul className="divide-y divide-border">
            {data.results.map((entry) => (
              <li key={entry.id}>
                <button
                  type="button"
                  onClick={() => setSelected(entry)}
                  className="grid w-full grid-cols-[auto_minmax(0,1fr)] gap-3 px-3 py-3 text-left transition-colors hover:bg-surface-2/60 focus-visible:bg-surface-2 focus-visible:outline-none sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:px-4"
                >
                  <DirectionIcon direction={entry.direction} status={entry.status} />
                  <span className="min-w-0">
                    <span className="line-clamp-2 text-[13px] leading-5 font-medium text-fg">{entry.message || t(logKindKey(entry.kind))}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
                      <span className="inline-flex items-center gap-1.5 font-semibold text-fg">
                        <ChannelMark channel={entry.connection.channel_code} size="sm" className="size-4 rounded text-[8px]" />
                        {entry.connection.name}
                      </span>
                      <span aria-hidden>·</span>
                      <span>{t(logKindKey(entry.kind))}</span>
                      <span aria-hidden>·</span>
                      <time dateTime={entry.created_at} className="num" title={formatDate(entry.created_at, 'd MMM yyyy, HH:mm:ss', lang)}>
                        {formatDate(entry.created_at, 'd MMM, HH:mm', lang)}
                      </time>
                      {entry.reservation && (
                        <>
                          <span aria-hidden>·</span>
                          <span className="num font-semibold text-accent-ink">{entry.reservation.code}</span>
                        </>
                      )}
                      <Badge tone={LOG_STATUS_TONE[entry.status]} className="sm:hidden">
                        {t(`log.status.${entry.status}`)}
                      </Badge>
                    </span>
                  </span>
                  <Badge tone={LOG_STATUS_TONE[entry.status]} className="hidden self-start sm:inline-flex">
                    {t(`log.status.${entry.status}`)}
                  </Badge>
                </button>
              </li>
            ))}
          </ul>
        )}
        {data && data.count > 0 && (
          <div className="flex items-center justify-between gap-3 border-t border-border px-3 py-2 text-[13px] text-muted">
            <span className="num">{t('log.total', { count: data.count })}</span>
            <div className="flex items-center gap-2">
              <span className="num">{t('log.page', { page, pages })}</span>
              <Button size="icon-sm" aria-label={t('log.previous')} disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft aria-hidden />
              </Button>
              <Button size="icon-sm" aria-label={t('log.next')} disabled={!data.next} onClick={() => setPage(page + 1)}>
                <ChevronRight aria-hidden />
              </Button>
            </div>
          </div>
        )}
      </div>

      <LogDetail entry={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

function DirectionIcon({ direction, status }: { direction: LogDirection; status: LogStatus }) {
  const { t } = useTranslation('channels')
  const Icon = direction === 'out' ? ArrowUpRight : ArrowDownLeft
  return (
    <span
      title={t(direction === 'out' ? 'log.out' : 'log.in')}
      className={cn(
        'mt-0.5 grid size-8 place-items-center rounded-full',
        status === 'error' ? 'bg-danger-soft text-danger-ink' : status === 'warning' ? 'bg-warning-soft text-warning-ink' : direction === 'out' ? 'bg-accent-soft text-accent-ink' : 'bg-info-soft text-info-ink',
      )}
    >
      <Icon aria-hidden className="size-4" />
      <span className="sr-only">{t(direction === 'out' ? 'log.out' : 'log.in')}</span>
    </span>
  )
}

function LogDetail({ entry, onClose }: { entry: SyncLogEntry | null; onClose: () => void }) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  return (
    <Sheet open={entry !== null} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="w-[min(34rem,100vw)]">
        {entry && (
          <>
            <SheetHeader>
              <SheetTitle>{t(logKindKey(entry.kind))}</SheetTitle>
              <SheetDescription>
                {entry.connection.name} · {formatDate(entry.created_at, 'd MMM yyyy, HH:mm:ss', lang)} ({formatRelative(entry.created_at, lang)})
              </SheetDescription>
            </SheetHeader>
            <SheetBody className="grid content-start gap-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={LOG_STATUS_TONE[entry.status]}>{t(`log.status.${entry.status}`)}</Badge>
                <Badge tone="outline">
                  {entry.direction === 'out' ? <ArrowUpRight aria-hidden /> : <ArrowDownLeft aria-hidden />}
                  {t(entry.direction === 'out' ? 'log.out' : 'log.in')}
                </Badge>
                {entry.external_id && <Badge tone="neutral">{t('log.externalId', { id: entry.external_id })}</Badge>}
              </div>
              {entry.message && <p className="text-sm leading-6 text-fg">{entry.message}</p>}
              {entry.reservation && (
                <Button asChild size="sm" className="w-fit">
                  <Link to={`/app/reservations/${entry.reservation.id}`}>
                    <ExternalLink aria-hidden /> {t('log.openReservation', { code: entry.reservation.code })}
                  </Link>
                </Button>
              )}
              <div className="grid gap-1.5">
                <p className="eyebrow">{t('log.payload')}</p>
                <pre className="num max-h-[50dvh] overflow-auto rounded-lg border border-border bg-surface-2 p-3 text-xs leading-5 whitespace-pre-wrap break-all text-fg">
                  {JSON.stringify(entry.payload, null, 2)}
                </pre>
              </div>
            </SheetBody>
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
