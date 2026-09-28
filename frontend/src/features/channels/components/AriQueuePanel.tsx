import { CalendarRange, ChevronLeft, ChevronRight, ListChecks, Send } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatDateRange, formatRelative, nightsBetween, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { retryQueue, useAriQueue, useChannelsMutation, type AriStatus, type Connection } from '../api'
import { addDaysISO } from '../lib/channels'
import { ARI_STATUS_TONE } from '../lib/labels'
import { tr } from '../lib/text'
import { ChannelMark } from './ChannelMark'

const ALL = '__all'
const PAGE_SIZE = 25

/**
 * The availability/rates updates waiting for (or already sent to) the channels. Changes in the PMS land here
 * a few seconds before they travel; failed ones are retried with backoff or sent again from here.
 */
export function AriQueuePanel({ connections, canManage }: { connections: Connection[]; canManage: boolean }) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const [connection, setConnection] = useState('')
  const [status, setStatus] = useState<AriStatus | ''>('')
  const [page, setPage] = useState(1)
  const query = useAriQueue({ connection: connection || undefined, status, page }, { refetchInterval: 5_000 })
  const data = query.data
  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1
  const pushConnections = connections.filter((item) => item.channel_code !== 'ical')
  const waiting = pushConnections
    .filter((item) => !connection || item.id === connection)
    .reduce((sum, item) => sum + item.stats.pending_updates + item.stats.failed_updates, 0)

  const send = useChannelsMutation(() => retryQueue(connection || undefined), {
    onSuccess: (result) =>
      result.failed || result.retrying
        ? toast.error(t('queue.sentWithErrors', { sent: result.sent, failed: result.failed + result.retrying }))
        : toast.success(result.sent ? t('queue.sent', { count: result.sent }) : t('queue.nothingToSend')),
  })

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={connection || ALL}
          onValueChange={(value) => {
            setConnection(value === ALL ? '' : value)
            setPage(1)
          }}
        >
          <SelectTrigger className="h-8 w-full sm:w-52" aria-label={t('log.connection')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('log.allConnections')}</SelectItem>
            {pushConnections.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={status || ALL}
          onValueChange={(value) => {
            setStatus(value === ALL ? '' : (value as AriStatus))
            setPage(1)
          }}
        >
          <SelectTrigger className="h-8 w-44 sm:w-48" aria-label={t('log.statusFilter')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>{t('log.allStatuses')}</SelectItem>
            {(['pending', 'sending', 'sent', 'failed'] as const).map((value) => (
              <SelectItem key={value} value={value}>
                {t(`queue.status.${value}`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted sm:ml-auto">{waiting ? t('queue.waiting', { count: waiting }) : t('queue.upToDate')}</p>
        {canManage && (
          <Button size="sm" onClick={() => send.mutate(undefined, { onError: (error) => toast.error(errorMessage(error, t)) })} loading={send.isPending}>
            <Send aria-hidden /> {t('queue.sendNow')}
          </Button>
        )}
      </div>

      <div className={cn('overflow-hidden rounded-lg border border-border bg-surface shadow-xs', query.isFetching && data && 'opacity-80')}>
        {query.isPending ? (
          <LoadingState variant="rows" rows={6} />
        ) : query.isError && !query.data ? (
          <ErrorState error={query.error} onRetry={() => void query.refetch()} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState icon={ListChecks} title={t('queue.empty')} description={t('queue.emptyHint')} />
        ) : (
          <ul className="divide-y divide-border">
            {data.results.map((update) => {
              const nights = nightsBetween(update.start, update.end)
              return (
                <li key={update.id} className="grid gap-2 px-3 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center sm:px-4">
                  <div className="flex min-w-0 items-start gap-3">
                    <ChannelMark channel={update.connection.channel_code} size="sm" className="mt-0.5" />
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] font-semibold text-fg">
                        {update.connection.name}
                        <span className="text-muted">·</span>
                        <span>{tr(update.room_type.name, lang) || update.room_type.code}</span>
                        <span className="text-2xs font-semibold tracking-wide text-muted">{update.room_type.code}</span>
                      </p>
                      <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
                        <span className="inline-flex items-center gap-1">
                          <CalendarRange aria-hidden className="size-3.5" />
                          <span className="num">{formatDateRange(update.start, addDaysISO(update.end, -1), lang)}</span>
                        </span>
                        <span className="num">{t('queue.nights', { count: nights })}</span>
                        {update.kinds.map((kind) => (
                          <Badge key={kind} tone="neutral">
                            {t(`queue.kinds.${kind}`)}
                          </Badge>
                        ))}
                      </p>
                      {update.last_error && <p className="mt-1 text-xs text-danger-ink">{update.last_error}</p>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 pl-9 sm:flex-col sm:items-end sm:gap-1 sm:pl-0">
                    <Badge tone={ARI_STATUS_TONE[update.status]}>{t(`queue.status.${update.status}`)}</Badge>
                    <span className="num text-xs text-muted" title={formatDate(update.updated_at, 'd MMM yyyy, HH:mm:ss', lang)}>
                      {update.status === 'sent' && update.sent_at
                        ? t('queue.sentAt', { when: formatRelative(update.sent_at, lang) })
                        : update.status === 'pending' && update.next_attempt_at
                          ? t('queue.retryAt', { when: formatRelative(update.next_attempt_at, lang), attempts: update.attempts })
                          : t('queue.createdAt', { when: formatRelative(update.created_at, lang) })}
                    </span>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
        {data && data.count > 0 && (
          <div className="flex items-center justify-between gap-3 border-t border-border px-3 py-2 text-[13px] text-muted">
            <span className="num">{t('queue.total', { count: data.count })}</span>
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
    </div>
  )
}
