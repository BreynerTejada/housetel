import { useTranslation } from 'react-i18next'
import { LogoMark } from '@/components/Logo'
import { formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Connection } from '../api'
import { laneHealth, type LaneHealth } from '../lib/channels'
import { ChannelMark } from './ChannelMark'
import './sync-lanes.css'

const TONE: Record<LaneHealth, string> = {
  ok: 'text-success-ink',
  queued: 'text-warning-ink',
  error: 'text-danger-ink',
  paused: 'text-stone-ink',
  idle: 'text-muted',
}

/**
 * Housetel's key tag and the channel's badge joined by two wires: prices and availability going out, bookings
 * coming in (for iCal: the exported and the imported calendars). Each wire shows its own state and time.
 */
export function SyncLanes({ connection, busy = false }: { connection: Connection; busy?: boolean }) {
  const { t, i18n } = useTranslation('channels')
  const lang = normalizeLang(i18n.language)
  const ical = connection.channel_code === 'ical'
  const imports = connection.room_mappings.filter((mapping) => mapping.ical_import_url).length
  const stats = connection.stats
  const out = busy ? 'queued' : laneHealth(connection, 'out')
  const incoming = laneHealth(connection, 'in')

  const outDetail = ical
    ? t('lanes.calendars', { count: connection.room_mappings.length })
    : {
        ok: t('lanes.outOk'),
        queued: busy ? t('lanes.sending') : t('lanes.queued', { count: stats.pending_updates }),
        error: stats.failed_updates ? t('lanes.failed', { count: stats.failed_updates }) : t('lanes.outError'),
        paused: t('lanes.paused'),
        idle: t('lanes.outIdle'),
      }[out]
  const inDetail = {
    ok: ical ? t('lanes.imported', { count: imports }) : t('lanes.inOk'),
    queued: '',
    error: t('lanes.inErrors', { count: stats.in_errors_24h }),
    paused: t('lanes.paused'),
    idle: ical ? (imports ? t('lanes.inIdle') : t('lanes.noImports')) : t('lanes.inIdle'),
  }[incoming]

  const lanes = [
    {
      key: 'out',
      direction: 'out' as const,
      health: out,
      label: ical ? t('lanes.exportedCalendars') : t('lanes.prices'),
      time: ical ? null : stats.last_out_at,
      detail: outDetail,
    },
    {
      key: 'in',
      direction: 'in' as const,
      health: incoming,
      label: ical ? t('lanes.importedCalendars') : t('lanes.bookings'),
      time: stats.last_in_at,
      detail: inDetail,
    },
  ]

  return (
    <figure
      aria-label={t('lanes.title', { channel: connection.name })}
      className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 rounded-lg bg-surface-2/60 px-3 py-3"
    >
      <LogoMark className="size-8" />
      <ul className="grid gap-3">
        {lanes.map((lane) => (
          <li key={lane.key} className="grid gap-1" aria-label={`${lane.label}: ${lane.detail}`}>
            <div className="flex items-baseline justify-between gap-3 text-[13px] leading-4">
              <span className="truncate font-semibold text-fg">{lane.label}</span>
              {lane.time && (
                <time dateTime={lane.time} className="num shrink-0 text-xs text-muted">
                  {formatRelative(lane.time, lang)}
                </time>
              )}
            </div>
            <div className="channels-lane" data-direction={lane.direction} data-health={lane.health} aria-hidden />
            <span className={cn('text-xs leading-4', TONE[lane.health])}>{lane.detail}</span>
          </li>
        ))}
      </ul>
      <ChannelMark channel={connection.channel_code} />
    </figure>
  )
}
