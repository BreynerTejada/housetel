import { useQueryClient } from '@tanstack/react-query'
import { useId, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { useCan } from '@/lib/permissions'
import { assignRoom, bookingKeys, unassignRoom, useRefreshFrontDesk, useRoomOptions, useToday, type ReservationDetail, type StayDetail } from '../api'
import { tr } from '../lib/labels'
import { currentUnit, occupiedUnits, orderUnits, proposedUnit } from '../lib/units'
import { RoomChoice } from './RoomChoice'

/**
 * Assign or move a stay's room (`room-options` → `assign`): its category's free rooms first, clean ones on top,
 * then other categories (an upgrade keeps the booked price). Moving a guest in house leaves the old room dirty.
 */
export function AssignRoomDialog({
  open,
  onOpenChange,
  reservation,
  stay,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  reservation: ReservationDetail
  stay: StayDetail
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const labelId = useId()
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const options = useRoomOptions(open ? stay.id : null)
  const { property } = useActiveProperty()
  const bd = property?.business_date ?? ''
  // Tonight's occupancy only matters for a stay that covers tonight (arriving today or in house).
  const tonight = stay.checkin_date <= bd && bd < stay.checkout_date
  const canSeeDesk = useCan('frontdesk.view')
  const board = useToday(open && tonight && canSeeDesk)
  const occupied = useMemo(
    () => (tonight ? occupiedUnits(board.data?.in_house, stay.id) : new Map<string, string>()),
    [tonight, board.data, stay.id],
  )
  const [picked, setPicked] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const current = currentUnit(stay.room, stay.bed, stay.room_type.code)
  const units = orderUnits(current, options.data ?? [], occupied)
  const selected = units.find((unit) => unit.key === picked) ?? (current ?? proposedUnit(units))
  const pending = stay.status === 'tentative' || stay.status === 'confirmed'

  async function run(action: () => Promise<ReservationDetail>, message: string) {
    setSaving(true)
    setError(null)
    try {
      const detail = await action()
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      toast.success(message)
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{stay.room ? t('assign.titleMove') : t('assign.title')}</DialogTitle>
          <DialogDescription>
            {tr(stay.room_type.name, i18n.language)} · {reservation.booker.full_name}
          </DialogDescription>
        </DialogHeader>
        <p id={labelId} className="sr-only">
          {t('checkin.room')}
        </p>
        {options.isError ? (
          <ErrorState error={options.error} onRetry={() => options.refetch()} />
        ) : options.isPending || board.isLoading ? (
          <LoadingState variant="rows" rows={3} className="p-0" />
        ) : units.length === 0 ? (
          <p className="text-[13px] text-muted">{t('checkin.noRooms')}</p>
        ) : (
          <RoomChoice units={units} value={selected?.key ?? null} onChange={setPicked} labelId={labelId} />
        )}
        {stay.status === 'checked_in' && <p className="text-[13px] text-muted">{t('assign.inHouseHint')}</p>}
        {error && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {error}
          </p>
        )}
        <DialogFooter className="sm:justify-between">
          {pending && stay.room ? (
            <Button variant="ghost" onClick={() => void run(() => unassignRoom(stay.id), t('assign.unassigned'))} disabled={saving}>
              {t('assign.unassign')}
            </Button>
          ) : (
            <span />
          )}
          <div className="flex flex-col-reverse gap-2 sm:flex-row">
            <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={saving}>
              {t('common:actions.cancel')}
            </Button>
            <Button
              variant="primary"
              loading={saving}
              disabled={!selected || selected.current}
              onClick={() =>
                selected &&
                void run(
                  () => assignRoom(stay.id, { room_id: selected.roomId, bed_id: selected.bedId, force: !selected.sameCategory }),
                  t('assign.done', { room: selected.roomNumber }),
                )
              }
            >
              {t('assign.confirm')}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
