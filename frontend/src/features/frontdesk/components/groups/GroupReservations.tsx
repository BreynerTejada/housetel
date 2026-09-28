import { Unlink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { MoneyText } from '@/components/Money'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { updateReservation, useRefreshFrontDesk, type GroupDetail, type ReservationListItem } from '../../api'
import { tr } from '../../lib/labels'

const LIVE = new Set(['tentative', 'confirmed', 'checked_in', 'checked_out'])

/** The reservations of the group (pilot P3): who booked, when, how many rooms and what each one owes. */
export function GroupReservations({ group, canManage }: { group: GroupDetail; canManage: boolean }) {
  const { t } = useTranslation('frontdesk')
  if (group.reservations.length === 0) {
    return <p className="rounded-xl border border-dashed border-border-strong px-4 py-6 text-center text-[13px] text-muted">{t('groups.reservationsEmpty')}</p>
  }
  return (
    <ul className="grid gap-2" aria-label={t('groups.sections.reservations')}>
      {group.reservations.map((reservation) => (
        <ReservationRow key={reservation.id} reservation={reservation} currency={group.currency} canManage={canManage} />
      ))}
    </ul>
  )
}

function ReservationRow({ reservation, currency, canManage }: { reservation: ReservationListItem; currency: string; canManage: boolean }) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const refresh = useRefreshFrontDesk()
  const rooms = reservation.stays.filter((stay) => LIVE.has(stay.status))
  const types = [...new Map(rooms.map((stay) => [stay.room_type.id, stay.room_type])).values()]
  const balance = Number(reservation.balance)
  const inactive = reservation.status === 'cancelled' || reservation.status === 'no_show'

  async function detach() {
    await updateReservation(reservation.id, { group_id: null })
    await refresh()
    toast.success(t('groups.detached', { code: reservation.code }))
  }

  return (
    <li
      className={cn(
        'grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1.5 rounded-xl border border-border bg-surface px-4 py-3 shadow-xs md:grid-cols-[minmax(0,1.6fr)_minmax(0,1.2fr)_minmax(0,1.2fr)_minmax(0,0.9fr)_auto]',
        inactive && 'opacity-70',
      )}
    >
      <span className="min-w-0">
        <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <Link
            to={`/app/reservations/${reservation.id}`}
            className="num text-[13px] font-bold tracking-wide whitespace-nowrap text-fg underline-offset-4 hover:text-accent-ink hover:underline"
          >
            {reservation.code}
          </Link>
          <StatusBadge kind="reservation" status={reservation.status} />
        </span>
        <span className="block truncate text-[13px] text-muted">{reservation.booker.full_name}</span>
      </span>
      <span className="text-right md:order-last">
        {canManage && !inactive ? (
          <ConfirmDialog
            trigger={
              <Button size="icon-sm" variant="ghost" aria-label={t('groups.detach', { code: reservation.code })}>
                <Unlink aria-hidden />
              </Button>
            }
            title={t('groups.detachTitle', { code: reservation.code })}
            description={t('groups.detachHint')}
            confirmLabel={t('groups.detachConfirm')}
            onConfirm={detach}
          />
        ) : null}
      </span>
      <span className="num text-[13px] text-fg">
        {formatDateRange(reservation.checkin_date, reservation.checkout_date, lang)}
        <span className="block text-xs text-muted">{t('date.nights', { count: reservation.nights })}</span>
      </span>
      <span className="min-w-0 text-[13px]">
        <span className="block font-semibold text-fg">{t('groups.rooms', { count: rooms.length })}</span>
        <span className="flex min-w-0 flex-wrap gap-x-2 text-xs text-muted">
          {types.map((type) => (
            <span key={type.id} className="inline-flex items-center gap-1">
              <span aria-hidden className="size-2 rounded-[2px]" style={{ backgroundColor: type.color }} />
              {tr(type.name, i18n.language)}
            </span>
          ))}
        </span>
      </span>
      <span className="text-[13px] md:text-right">
        <span className="block text-xs text-muted">{t('groups.balance')}</span>
        <MoneyText value={reservation.balance} currency={currency} className={cn('num font-semibold', balance > 0 ? 'text-warning-ink' : 'text-fg')} />
      </span>
    </li>
  )
}
