import { useQueryClient } from '@tanstack/react-query'
import { CircleAlert, CircleCheck, CircleDashed, LogIn, Star } from 'lucide-react'
import { lazy, Suspense, useId, useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { countryName } from '@/features/guests/countries'
import { formatDocument, formatPhone } from '@/features/guests/format'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  assignRoom,
  bookingKeys,
  checkIn,
  useOnlineCheckin,
  useRefreshFrontDesk,
  useReservation,
  useRoomOptions,
  useToday,
  type ReservationDetail,
  type StayDetail,
} from '../api'
import { shortDay, stayLine, unitLabel } from '../lib/labels'
import { currentUnit, isHousekeepingReady, occupiedUnits, orderUnits, proposedUnit } from '../lib/units'
import { RoomChoice } from './RoomChoice'

const FolioPanel = lazy(() => import('@/features/finance/components/FolioPanel'))

export interface CheckInDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  stayId: string
  reservationId: string
  /** After a successful check-in (the board and the reservation are already refreshed). */
  onDone?: (reservation: ReservationDetail) => void
}

/**
 * Check-in in one confirmation (plan C1): who arrives (document, contact, online check-in), the room — the
 * clean, vacant ones of its category first, proposing one when the assigned room is not ready or still has
 * the guest who leaves today inside — and the balance (`FolioPanel` compact). Anything the backend would
 * refuse without `force` (tentative, late arrival, room not clean) or that needs a second look (room still
 * occupied) is said in words and turns the button into "Hacer check-in igual".
 */
export function CheckInDialog({ open, onOpenChange, stayId, reservationId, onDone }: CheckInDialogProps) {
  const { t } = useTranslation('frontdesk')
  const reservation = useReservation(open ? reservationId : undefined)
  const stay = reservation.data?.stays.find((item) => item.id === stayId)
  const name = reservation.data?.booker.full_name ?? ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{name ? t('checkin.title', { name }) : t('checkin.titleLoading')}</DialogTitle>
          <StayDescription reservation={reservation.data} stay={stay} />
        </DialogHeader>
        {reservation.isError ? (
          <ErrorState error={reservation.error} onRetry={() => reservation.refetch()} />
        ) : !reservation.data || !stay ? (
          <LoadingState variant="rows" rows={4} />
        ) : (
          <CheckInForm reservation={reservation.data} stay={stay} onCancel={() => onOpenChange(false)} onDone={(detail) => {
            onDone?.(detail)
            onOpenChange(false)
          }} />
        )}
      </DialogContent>
    </Dialog>
  )
}

function StayDescription({ reservation, stay }: { reservation?: ReservationDetail; stay?: StayDetail }) {
  const { t, i18n } = useTranslation('frontdesk')
  if (!reservation || !stay) return <DialogDescription className="sr-only">{t('checkin.loading')}</DialogDescription>
  const line = stayLine(t, normalizeLang(i18n.language), {
    checkin: stay.checkin_date,
    checkout: stay.checkout_date,
    nights: stay.nights,
    adults: stay.adults,
    children: stay.children,
  })
  return (
    <DialogDescription>
      <span className="num font-semibold text-fg">{reservation.code}</span> · {line}
    </DialogDescription>
  )
}

function CheckInForm({
  reservation,
  stay,
  onCancel,
  onDone,
}: {
  reservation: ReservationDetail
  stay: StayDetail
  onCancel: () => void
  onDone: (reservation: ReservationDetail) => void
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const bd = property?.business_date ?? stay.checkin_date
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const roomsLabel = useId()
  const pending = stay.status === 'tentative' || stay.status === 'confirmed'
  const options = useRoomOptions(pending ? stay.id : null)
  const online = useOnlineCheckin(reservation.id)
  // Who is still in house where (the Today board, usually already cached): a room can be clean and still
  // have the guest who leaves today inside.
  const canSeeDesk = useCan('frontdesk.view')
  const board = useToday(pending && canSeeDesk)
  const occupied = useMemo(() => occupiedUnits(board.data?.in_house, stay.id), [board.data, stay.id])
  const [picked, setPicked] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const current = currentUnit(stay.room, stay.bed, stay.room_type.code)
  const units = orderUnits(current, options.data ?? [], occupied)
  const proposal = proposedUnit(units)
  const selected = units.find((unit) => unit.key === picked) ?? proposal
  const loadingRooms = pending && (options.isPending || board.isLoading)

  // `blockers`: the backend refuses them without `force`; `warnings`: allowed, but worth a second look.
  const blockers: { key: string; text: string }[] = []
  const warnings: { key: string; text: string }[] = []
  if (stay.status === 'tentative') blockers.push({ key: 'tentative', text: t('checkin.tentative') })
  if (stay.checkin_date < bd) blockers.push({ key: 'late', text: t('checkin.late', { date: shortDay(stay.checkin_date, lang) }) })
  // While the room options load the proposal is provisional: say nothing about the room yet.
  if (!loadingRooms && selected) {
    const room = unitLabel(selected.roomNumber, selected.bedLabel)
    if (!isHousekeepingReady(selected.housekeepingStatus)) {
      blockers.push({ key: 'room', text: t(`checkin.roomNotReady_${selected.housekeepingStatus}`, { room }) })
    }
    if (selected.occupiedBy) warnings.push({ key: 'occupied', text: t('checkin.roomOccupied', { room, name: selected.occupiedBy }) })
  }
  const reasons = [...blockers, ...warnings]
  const force = blockers.length > 0

  async function confirm() {
    setSaving(true)
    setError(null)
    try {
      if (selected && !selected.current) {
        await assignRoom(stay.id, { room_id: selected.roomId, bed_id: selected.bedId, force: !selected.sameCategory })
      }
      const detail = await checkIn(stay.id, force)
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      const room = detail.stays.find((item) => item.id === stay.id)?.room?.number ?? selected?.roomNumber ?? ''
      toast.success(t('checkin.done', { name: reservation.booker.full_name, room }))
      onDone(detail)
    } catch (err) {
      setError(errorMessage(err, t))
      await queryClient.invalidateQueries({ queryKey: bookingKeys.reservation(reservation.id) })
      await queryClient.invalidateQueries({ queryKey: bookingKeys.roomOptions(stay.id) })
    } finally {
      setSaving(false)
    }
  }

  const currentNotReady = !loadingRooms && current && !current.ready
  const currentLabel = current ? unitLabel(current.roomNumber, current.bedLabel) : null
  return (
    <>
      <div className="grid gap-5">
        <GuestFacts reservation={reservation} onlineStatus={online.data?.status ?? null} onlineLoading={online.isPending} />

        <section className="grid gap-2.5">
          <h3 id={roomsLabel} className="eyebrow">
            {t('checkin.room')}
          </h3>
          {currentNotReady && !selected?.current && (
            <Notice tone="warning">
              {current.occupiedBy
                ? t('checkin.roomOccupied', { room: currentLabel, name: current.occupiedBy })
                : t(`checkin.roomNotReady_${current.housekeepingStatus}`, { room: currentLabel })}
              {proposal && !proposal.current && ` ${t('checkin.proposed', { room: unitLabel(proposal.roomNumber, proposal.bedLabel) })}`}
            </Notice>
          )}
          {!current && <p className="text-[13px] text-muted">{t('checkin.unassigned')}</p>}
          {loadingRooms ? (
            <LoadingState variant="rows" rows={2} className="p-0" />
          ) : units.length === 0 ? (
            <p className="text-[13px] text-muted">{t('checkin.noRooms')}</p>
          ) : (
            <RoomChoice units={units} value={selected?.key ?? null} onChange={setPicked} labelId={roomsLabel} />
          )}
        </section>

        <section className="grid gap-2.5">
          <h3 className="eyebrow">{t('checkin.balance')}</h3>
          <Suspense fallback={<LoadingState variant="rows" rows={2} className="p-0" />}>
            <FolioPanel reservationId={reservation.id} compact onChange={() => void refresh()} />
          </Suspense>
        </section>

        {reasons.length > 0 && (
          <Notice tone="warning">
            <ul className="grid gap-0.5">
              {reasons.map((reason) => (
                <li key={reason.key}>{reason.text}</li>
              ))}
            </ul>
          </Notice>
        )}
        {error && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {error}
          </p>
        )}
      </div>
      <DialogFooter>
        <Button variant="secondary" onClick={onCancel} disabled={saving}>
          {t('common:actions.cancel')}
        </Button>
        <Button variant="primary" onClick={() => void confirm()} loading={saving} disabled={loadingRooms || !pending}>
          <LogIn aria-hidden />
          {reasons.length > 0 ? t('checkin.force') : t('checkin.confirm')}
        </Button>
      </DialogFooter>
    </>
  )
}

function GuestFacts({
  reservation,
  onlineStatus,
  onlineLoading,
}: {
  reservation: ReservationDetail
  onlineStatus: string | null
  onlineLoading: boolean
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const guest = reservation.booker
  const document = formatDocument(guest.document_type, guest.document_number)
  const facts = [
    document,
    guest.nationality ? countryName(guest.nationality, i18n.language) : '',
    guest.email,
    formatPhone(guest.phone),
  ].filter(Boolean)
  const status = onlineStatus === 'completed' || onlineStatus === 'in_progress' ? onlineStatus : 'not_started'
  const OnlineIcon = status === 'completed' ? CircleCheck : status === 'in_progress' ? CircleDashed : CircleDashed

  return (
    <section className="grid gap-2 rounded-lg border border-border bg-surface-2/60 px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 font-semibold text-fg">
          {guest.is_vip && <Star aria-label={t('vip')} className="size-4 fill-warning text-warning" />}
          {guest.full_name}
        </p>
        <Link to={`/app/guests/${guest.id}`} className="text-[13px] font-semibold text-accent-ink underline-offset-4 hover:underline">
          {t('checkin.editGuest')}
        </Link>
      </div>
      {facts.length > 0 && (
        <ul className="flex flex-wrap gap-x-3 gap-y-1 text-[13px] text-muted">
          {facts.map((fact) => (
            <li key={fact} className="num">
              {fact}
            </li>
          ))}
        </ul>
      )}
      {!document && (
        <p className="flex items-start gap-1.5 text-[13px] text-warning-ink">
          <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          {t('checkin.missingDocument')}
        </p>
      )}
      {!onlineLoading && (
        <p className={cn('flex items-center gap-1.5 text-[13px] font-semibold', status === 'completed' ? 'text-success-ink' : 'text-muted')}>
          <OnlineIcon aria-hidden className="size-3.5" />
          {t(`checkin.online.${status}`)}
        </p>
      )}
    </section>
  )
}

function Notice({ tone, children }: { tone: 'warning' | 'info'; children: ReactNode }) {
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-lg px-3 py-2 text-[13px]',
        tone === 'warning' ? 'bg-warning-soft text-warning-ink' : 'bg-info-soft text-info-ink',
      )}
    >
      <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  )
}

