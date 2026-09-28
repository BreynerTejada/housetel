import { Camera, Lock, MapPin, UserRound } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { formatDate, formatRelative, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import type { MaintenanceTicket } from '../api'
import { PriorityBadge } from './TaskBadges'

/** A damage report in the maintenance lists: what, where (key tag of the room or the place), how urgent,
 * whether it keeps the room out of service, who reported it and who is on it. */
export function TicketCard({ ticket, onOpen }: { ticket: MaintenanceTicket; onOpen: (ticket: MaintenanceTicket) => void }) {
  const { t, i18n } = useTranslation('housekeeping')
  const lang = normalizeLang(i18n.language)
  const ids = useId()
  const closed = ticket.status === 'resolved' || ticket.status === 'cancelled'

  return (
    <button
      type="button"
      aria-haspopup="dialog"
      aria-labelledby={`${ids}-title`}
      aria-describedby={`${ids}-details`}
      onClick={() => onOpen(ticket)}
      className={cn(
        'grid w-full gap-3 rounded-xl border border-border bg-surface p-4 text-left shadow-xs transition-[border-color,box-shadow] duration-150',
        'hover:border-border-strong hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
        closed && 'bg-surface-2/60',
      )}
    >
      <div className="flex items-start gap-3">
        {ticket.room ? (
          <RoomKeyTag number={ticket.room.number} status={ticket.room.housekeeping_status} />
        ) : (
          <span className="grid size-9 shrink-0 place-items-center rounded-md bg-surface-2 text-muted">
            <MapPin aria-hidden className="size-4" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p id={`${ids}-title`} className={cn('font-semibold text-fg', closed && 'text-muted')}>
            {ticket.title}
          </p>
          {!ticket.room && <p className="truncate text-[13px] text-muted">{ticket.location || t('ticket.commonArea')}</p>}
        </div>
        <PriorityBadge priority={ticket.priority} />
      </div>
      <div id={`${ids}-details`} className="grid gap-2">
        {ticket.blocks_room && ticket.blocked_until && (
          <p className="hatch flex items-center gap-1.5 justify-self-start rounded-md bg-room-ooo-soft px-2 py-1 text-[12px] font-semibold text-stone-ink">
            <Lock aria-hidden className="size-3.5" />
            {t('maintenance.blocks', { date: formatDate(ticket.blocked_until, 'd MMM', lang) })}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted">
          <span>
            {ticket.reported_by
              ? t('maintenance.reportedBy', { name: ticket.reported_by.full_name, when: formatRelative(ticket.created_at, lang) })
              : t('maintenance.reported', { when: formatRelative(ticket.created_at, lang) })}
          </span>
          {ticket.photos.length > 0 && (
            <span className="inline-flex items-center gap-1">
              <Camera aria-hidden className="size-3.5" />
              {t('maintenance.photos', { count: ticket.photos.length })}
            </span>
          )}
        </div>
        <p className={cn('flex items-center gap-1.5 text-[12px]', ticket.assigned_to ? 'font-semibold text-fg' : 'text-muted italic')}>
          <UserRound aria-hidden className="size-3.5" />
          {ticket.assigned_to?.full_name ?? t('maintenance.unassigned')}
        </p>
      </div>
    </button>
  )
}
