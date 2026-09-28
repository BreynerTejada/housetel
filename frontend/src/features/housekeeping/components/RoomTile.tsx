import { DoorOpen, LogOut, Star, UserRound, Users, Wrench } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { BoardRoom } from '../api'
import { leadTask } from '../lib/tasks'

/** Room states as tints of the key-tag rack (spec §7.3): sage, sand, slate and hatched stone. */
const TINT: Record<string, string> = {
  clean: 'bg-room-clean-soft text-success-ink',
  dirty: 'bg-room-dirty-soft text-warning-ink',
  inspected: 'bg-room-inspected-soft text-info-ink',
  out_of_service: 'bg-room-ooo-soft text-stone-ink hatch',
}

/**
 * A room on the supervision board, drawn like its key on the front-desk rack: punched hole, number, tint of its
 * housekeeping state, who is in it, who arrives today and the task with its assignee.
 */
export function RoomTile({ room, onOpen }: { room: BoardRoom; onOpen: (room: BoardRoom) => void }) {
  const { t, i18n } = useTranslation('housekeeping')
  const lang = normalizeLang(i18n.language)
  const detailsId = useId()
  const task = leadTask(room.tasks)
  const others = room.tasks.filter((item) => item !== task && item.status !== 'cancelled').length
  const vip = Boolean(room.arrival_today?.is_vip || room.in_house?.is_vip)

  return (
    <button
      type="button"
      aria-haspopup="dialog"
      aria-label={t('card.room', { number: room.number })}
      aria-describedby={detailsId}
      onClick={() => onOpen(room)}
      data-status={room.housekeeping_status}
      className={cn(
        'group relative flex min-h-36 w-full flex-col rounded-xl border border-transparent p-3 pt-2.5 text-left transition-[border-color,box-shadow] duration-150',
        'hover:border-border-strong hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55 focus-visible:ring-offset-2 focus-visible:ring-offset-bg',
        TINT[room.housekeeping_status] ?? TINT.clean,
      )}
    >
      <span aria-hidden className="absolute top-2.5 right-2.5 size-2 rounded-full bg-surface shadow-[inset_0_1px_1.5px_rgb(0_0_0/0.25)]" />
      <span className="flex items-baseline gap-2 pr-4">
        <span className="text-[22px] leading-7 font-extrabold tracking-[-0.03em] text-fg">{room.number}</span>
        <span className="text-[11px] font-bold tracking-[0.06em] uppercase opacity-80">{room.room_type.code}</span>
        {vip && <Star aria-hidden className="ml-auto size-3.5 shrink-0 fill-current" />}
      </span>
      <span id={detailsId} className="contents">
        <span className="text-[13px] font-bold">{t(`common:status.room.${room.housekeeping_status}`)}</span>
        {vip && <span className="sr-only">{t('tile.vip')}</span>}

      <span className="mt-2 grid gap-1 text-[12px] leading-4 text-fg">
        {room.in_house ? (
          <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 font-semibold text-accent-ink">
            <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
              <Users aria-hidden className="size-3.5 shrink-0" />
              {t('tile.guests', { count: room.in_house.guests })}
            </span>
            {room.in_house.departs_today && (
              <span className="inline-flex items-center gap-1 whitespace-nowrap text-fg">
                <LogOut aria-hidden className="size-3 shrink-0" />
                {t('tile.departsToday')}
              </span>
            )}
          </span>
        ) : (
          <span className="text-muted">{room.active_block ? t('tile.blocked', { date: formatDate(room.active_block.end_date, 'd MMM', lang) }) : t('tile.vacant')}</span>
        )}
        {room.arrival_today && (
          <span className="flex items-center gap-1.5 font-semibold">
            <DoorOpen aria-hidden className="size-3.5 shrink-0" />
            {room.arrival_today.eta ? t('tile.arrives', { eta: room.arrival_today.eta }) : t('tile.arrivesNoEta')}
          </span>
        )}
        {room.open_tickets > 0 && (
          <span className="flex items-center gap-1.5 text-muted">
            <Wrench aria-hidden className="size-3.5 shrink-0" />
            {t('tile.tickets', { count: room.open_tickets })}
          </span>
        )}
      </span>

      {task && (
        <span className="mt-auto grid gap-0.5 border-t border-current/15 pt-2 text-[12px] leading-4">
          <span className="font-semibold text-fg">
            {t('tile.task', {
              kind: t(`kindsShort.${task.kind}`),
              status: t(`common:status.task.${task.status}`),
            })}
            {others > 0 && <span className="ml-1 font-normal text-muted">{t('tile.more', { count: others })}</span>}
          </span>
          <span className={cn('flex items-center gap-1.5 truncate', task.assigned_to ? 'text-fg' : 'text-muted italic')}>
            <UserRound aria-hidden className="size-3.5 shrink-0" />
            <span className="truncate">{task.assigned_to?.full_name ?? t('tile.unassigned')}</span>
          </span>
        </span>
      )}
      </span>
    </button>
  )
}
