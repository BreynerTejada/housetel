import { CalendarClock, Pencil, Trash2, Undo2, UserPlus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { formatDate, formatDateRange, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { deleteBlock, releaseBlock, useRefreshFrontDesk, type GroupBlock } from '../../api'
import { pickupTone, releaseState } from '../../lib/groups'
import { tr } from '../../lib/labels'
import { PickupStrip } from './PickupStrip'

/**
 * One allotment of the group (pilot P3): what is held, night by night, how much the group took, when what is
 * left goes back on sale — and booking rooms from it (the wizard picks them up with `?block=`).
 */
export function BlockCard({
  block,
  groupId,
  bd,
  canManage,
  onEdit,
}: {
  block: GroupBlock
  groupId: string
  bd: string
  canManage: boolean
  onEdit: (block: GroupBlock) => void
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const refresh = useRefreshFrontDesk()
  const pickup = block.pickup
  const release = releaseState(block, bd)
  const released = release.kind === 'released'
  const nights = pickup.nights.length
  const name = tr(block.room_type.name, i18n.language)
  const dorm = block.room_type.kind === 'dorm'
  const heldNights = pickup.nights.reduce((sum, night) => sum + night.remaining, 0)
  // Rooms can still be taken from it while it holds something and its last night has not passed.
  const bookable = !released && pickup.remaining_min > 0 && block.end > bd
  const search = new URLSearchParams({
    group: groupId,
    block: block.id,
    checkin: block.start < bd ? bd : block.start,
    checkout: block.end,
  })

  async function releaseNow() {
    await releaseBlock(block.id)
    await refresh()
    toast.success(t('groups.blocks.releasedToast', { count: heldNights }))
  }

  async function remove() {
    await deleteBlock(block.id)
    await refresh()
    toast.success(t('groups.blocks.deletedToast'))
  }

  return (
    <article className={cn('grid gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5', released && 'bg-surface-2/40')}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="flex min-w-0 items-center gap-2 font-semibold text-fg">
            <span aria-hidden className="size-3 shrink-0 rounded-[4px] ring-1 ring-black/5" style={{ backgroundColor: block.room_type.color }} />
            <span className="truncate">{t(dorm ? 'groups.blocks.titleBeds' : 'groups.blocks.titleRooms', { count: block.units, type: name })}</span>
          </h3>
          <p className="num mt-0.5 text-[13px] text-muted">
            {formatDateRange(block.start, block.end, lang)} · {t('date.nights', { count: nights })}
          </p>
        </div>
        <Badge tone={released ? 'stone' : release.kind === 'due' ? 'warning' : 'neutral'} className="shrink-0">
          <CalendarClock aria-hidden />
          {released
            ? t('groups.blocks.releasedOn', { date: formatDate(block.released_at, lang === 'en' ? 'MMM d' : 'd MMM', lang) })
            : release.kind === 'due'
              ? t('groups.blocks.releasesToday')
              : t('groups.blocks.releasesIn', { count: release.days, date: formatDate(block.release_date, lang === 'en' ? 'MMM d' : 'd MMM', lang) })}
        </Badge>
      </header>

      <PickupStrip
        nights={pickup.nights}
        color={block.room_type.color}
        released={released}
        bd={bd}
        label={t('groups.blocks.stripLabel', { type: name })}
      />

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
        <p className="text-[13px]">
          <span className="num font-semibold text-fg">{t('groups.blocks.picked', { rooms: pickup.picked_rooms, units: block.units })}</span>
          <span className="text-muted"> · </span>
          <Badge tone={pickupTone(pickup.pickup_pct)}>{t('groups.blocks.pct', { pct: Math.round(pickup.pickup_pct) })}</Badge>
          {!released && heldNights > 0 && <span className="block text-xs text-muted sm:inline sm:pl-2">{t('groups.blocks.heldNights', { count: heldNights })}</span>}
        </p>
        {canManage && (
          <div className="flex flex-wrap items-center gap-1.5">
            {bookable && (
              <Button asChild size="sm" variant="primary">
                <Link to={`/app/reservations/new?${search.toString()}`}>
                  <UserPlus aria-hidden />
                  {t('groups.blocks.book')}
                </Link>
              </Button>
            )}
            {!released && (
              <Button size="sm" variant="secondary" onClick={() => onEdit(block)}>
                <Pencil aria-hidden />
                {t('groups.blocks.edit')}
              </Button>
            )}
            {!released && (
              <ConfirmDialog
                trigger={
                  <Button size="sm" variant="ghost">
                    <Undo2 aria-hidden />
                    {t('groups.blocks.release')}
                  </Button>
                }
                title={t('groups.blocks.releaseTitle')}
                description={t('groups.blocks.releaseHint', { count: heldNights })}
                confirmLabel={t('groups.blocks.releaseConfirm')}
                onConfirm={releaseNow}
              />
            )}
            {pickup.picked_rooms === 0 && (
              <ConfirmDialog
                trigger={
                  <Button size="sm" variant="ghost" className="text-danger-ink hover:bg-danger-soft" aria-label={t('groups.blocks.delete')}>
                    <Trash2 aria-hidden />
                  </Button>
                }
                title={t('groups.blocks.deleteTitle')}
                description={t('groups.blocks.deleteHint')}
                confirmLabel={t('groups.blocks.delete')}
                onConfirm={remove}
              />
            )}
          </div>
        )}
      </div>
    </article>
  )
}
