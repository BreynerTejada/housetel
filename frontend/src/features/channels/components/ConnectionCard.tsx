import { Copy, Download, Ellipsis, FlaskConical, Pause, Pencil, Play, PlugZap, RefreshCw, Trash2 } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge, type BadgeTone } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { errorMessage } from '@/lib/errors'
import { formatNumber, formatRelative, normalizeLang, type Lang } from '@/lib/format'
import {
  deleteConnection,
  fullSync,
  pauseConnection,
  pullConnection,
  resumeConnection,
  testConnection,
  useChannelsMutation,
  type Connection,
  type PullSummary,
} from '../api'
import { tr } from '../lib/text'
import { SyncLanes } from './SyncLanes'

const STATUS_TONE: Record<Connection['status'], BadgeTone> = { active: 'success', paused: 'stone', error: 'danger' }

function markupSummary(connection: Connection, lang: Lang): string | null {
  const values = [...new Set(connection.rate_mappings.map((rate) => Number(rate.markup_percent)))].sort((a, b) => a - b)
  if (!values.length) return null
  const format = (value: number) => `${value > 0 ? '+' : ''}${formatNumber(value, lang)} %`
  return values.length === 1 ? format(values[0]) : `${format(values[0])} … ${format(values[values.length - 1])}`
}

/** One connected channel: its state, the two sync wires and what the staff can do with it. */
export function ConnectionCard({
  connection,
  canManage,
  onEdit,
}: {
  connection: Connection
  canManage: boolean
  onEdit: (connection: Connection) => void
}) {
  const { t, i18n } = useTranslation('channels')
  const titleId = useId()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const ical = connection.channel_code === 'ical'
  const imports = connection.room_mappings.filter((mapping) => mapping.ical_import_url).length
  const markup = markupSummary(connection, normalizeLang(i18n.language))
  const paused = connection.status === 'paused'

  const onError = (error: unknown) => toast.error(errorMessage(error, t))
  const sync = useChannelsMutation(() => fullSync(connection.id), {
    onSuccess: (summary) =>
      summary.failed || summary.retrying
        ? toast.error(t('card.syncFailed', { channel: connection.name }))
        : toast.success(t('card.synced', { channel: connection.name })),
  })
  const check = useChannelsMutation(() => testConnection(connection.id), {
    onSuccess: (result) => (result.ok ? toast.success(result.message) : toast.error(result.message)),
  })
  const pause = useChannelsMutation(() => pauseConnection(connection.id), {
    onSuccess: () => toast.success(t('card.pausedToast', { channel: connection.name })),
  })
  const resume = useChannelsMutation(() => resumeConnection(connection.id), {
    onSuccess: () => toast.success(t('card.resumedToast', { channel: connection.name })),
  })
  const pull = useChannelsMutation(() => pullConnection(connection.id), {
    onSuccess: (summary: PullSummary) => toast.success(pullText(summary)),
  })
  const remove = useChannelsMutation(() => deleteConnection(connection.id), {
    onSuccess: () => toast.success(t('card.deleted', { channel: connection.name })),
  })

  function pullText(summary: PullSummary) {
    const changed = (summary.created ?? 0) + (summary.modified ?? 0) + (summary.cancelled ?? 0)
    if (summary.failed) return t('card.pulledWithErrors', { count: summary.failed })
    return changed
      ? t('card.pulled', { created: summary.created ?? 0, modified: summary.modified ?? 0, cancelled: summary.cancelled ?? 0 })
      : t('card.pulledNothing')
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url)
      toast.success(t('card.copied'))
    } catch {
      toast.error(t('card.copyFailed'))
    }
  }

  const summary = [
    t('card.rooms', { count: connection.room_mappings.length }),
    ical ? null : t('card.rates', { count: connection.rate_mappings.length }),
    markup ? t('card.markup', { markup }) : null,
  ].filter(Boolean)

  const canPush = !ical
  const canPull = connection.delivery === 'pull' || (ical && imports > 0)

  return (
    <article aria-labelledby={titleId} className="grid content-start gap-4 rounded-xl border border-border bg-surface p-5 shadow-xs">
      <header className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 id={titleId} className="flex flex-wrap items-center gap-2 text-[15px] leading-6 font-bold tracking-[-0.01em]">
            <span className="truncate">{connection.name}</span>
            <Badge tone={STATUS_TONE[connection.status]}>{t(`status.${connection.status}`)}</Badge>
            {!ical || connection.mode === 'real' ? (
              <Badge tone={connection.mode === 'real' ? 'info' : 'outline'}>{t(`mode.${connection.mode}`)}</Badge>
            ) : null}
          </h3>
          <p className="mt-0.5 text-[13px] text-muted">
            {t(`channels.${connection.channel_code}.short`)} · {summary.join(' · ')}
          </p>
        </div>
        {canManage && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label={t('card.more', { channel: connection.name })}>
                <Ellipsis aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => onEdit(connection)}>
                <Pencil aria-hidden /> {t('card.editMapping')}
              </DropdownMenuItem>
              {connection.simulated && (
                <DropdownMenuItem asChild>
                  <Link to={`/app/simulators/ota?connection=${connection.id}`}>
                    <FlaskConical aria-hidden /> {t('card.openSimulator')}
                  </Link>
                </DropdownMenuItem>
              )}
              {paused ? (
                <DropdownMenuItem onSelect={() => resume.mutate(undefined, { onError })}>
                  <Play aria-hidden /> {t('card.resume')}
                </DropdownMenuItem>
              ) : (
                <DropdownMenuItem onSelect={() => pause.mutate(undefined, { onError })}>
                  <Pause aria-hidden /> {t('card.pause')}
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem className="text-danger-ink" onSelect={() => setConfirmDelete(true)}>
                <Trash2 aria-hidden /> {t('card.delete')}
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </header>

      <SyncLanes connection={connection} busy={sync.isPending} />

      {connection.last_error && connection.status !== 'paused' && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-[13px] text-danger-ink">
          {connection.last_error}
        </p>
      )}

      {ical && connection.room_mappings.length > 0 && (
        <ul className="grid gap-1.5" aria-label={t('card.calendarsTitle')}>
          {connection.room_mappings.map((mapping) => (
            <li key={mapping.id} className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-[13px]">
              <span className="num text-[11px] font-bold tracking-wide text-muted">{mapping.room_type_code}</span>
              <span className="min-w-0 flex-1 truncate">
                {mapping.room_number ? t('card.room', { number: mapping.room_number }) : tr(mapping.room_type_name, i18n.language)}
                {mapping.ical_last_error && <span className="block truncate text-xs text-danger-ink">{mapping.ical_last_error}</span>}
                {!mapping.ical_last_error && mapping.ical_last_sync_at && (
                  <span className="block text-xs text-muted">
                    {t('card.importedAt', { when: formatRelative(mapping.ical_last_sync_at, normalizeLang(i18n.language)) })}
                  </span>
                )}
              </span>
              {mapping.ical_export_url && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => copy(mapping.ical_export_url as string)}
                  aria-label={t('card.copyUrlFor', { room: mapping.room_number ?? mapping.room_type_code })}
                >
                  <Copy aria-hidden /> {t('card.copyUrl')}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <footer className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
        <span className="mr-auto text-xs text-muted">
          {t('card.reservations', { count: connection.stats.reservations })}
          {connection.stats.errors_24h > 0 && ` · ${t('card.errors24h', { count: connection.stats.errors_24h })}`}
        </span>
        {canManage && (
          <>
            <Button size="sm" variant="ghost" onClick={() => check.mutate(undefined, { onError })} loading={check.isPending}>
              <PlugZap aria-hidden /> {t('card.test')}
            </Button>
            {connection.simulated && (
              <Button size="sm" variant="ghost" asChild>
                <Link to={`/app/simulators/ota?connection=${connection.id}`}>
                  <FlaskConical aria-hidden /> {t('card.simulator')}
                </Link>
              </Button>
            )}
            {canPull && (
              <Button size="sm" onClick={() => pull.mutate(undefined, { onError })} loading={pull.isPending} disabled={paused}>
                <Download aria-hidden /> {ical ? t('card.importNow') : t('card.pullNow')}
              </Button>
            )}
            {canPush && (
              <Button size="sm" onClick={() => sync.mutate(undefined, { onError })} loading={sync.isPending} disabled={paused}>
                <RefreshCw aria-hidden /> {t('card.fullSync')}
              </Button>
            )}
          </>
        )}
      </footer>

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={t('card.deleteTitle', { channel: connection.name })}
        description={t('card.deleteDescription')}
        confirmLabel={t('card.delete')}
        onConfirm={() => remove.mutateAsync(undefined)}
      />
    </article>
  )
}
