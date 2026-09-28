import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowUpRight, CircleAlert, DoorOpen, LogIn, LogOut, MoveRight, Star, SquareArrowOutUpRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Sheet, SheetBody, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'
import { RoomKeyTag } from '@/features/inventory/components/RoomKeyTag'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatDateRange, formatMoney, normalizeLang } from '@/lib/format'
import { useMediaQuery } from '@/lib/hooks'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { calendarKeys, checkIn, checkOut, useReservation, type CalStay, type ReservationDetail } from '../api'
import { nightsOf, pick, placeLabel, sourceLabel, type RoomIndex } from '../lib/labels'
import { calendarToast } from '../lib/toast'

type Problem =
  | { kind: 'room_not_ready'; room: string; status: string }
  | { kind: 'balance_due'; amount: string }
  | { kind: 'error'; message: string }

export interface StayPanelProps {
  stay: CalStay | null
  index: RoomIndex
  businessDate: string
  onClose: () => void
  onMove: (stay: CalStay) => void
  onUnassign: (stay: CalStay) => void
}

/**
 * The side panel of a booking (bottom sheet on phones): who, when, where and what they owe, plus the next
 * step at the front desk — check in, check out, move, take the room away or open the whole booking.
 */
export function StayPanel({ stay, onClose, ...props }: StayPanelProps) {
  const isPhone = useMediaQuery('(max-width: 639px)')
  // On a desk the grid stays usable next to the panel (click another booking to switch); on a phone the
  // bottom sheet takes the screen.
  return (
    <Sheet open={stay !== null} onOpenChange={(open) => !open && onClose()} modal={isPhone}>
      <SheetContent side={isPhone ? 'bottom' : 'right'} className={cn(!isPhone && 'w-[min(26rem,94vw)]')}>
        {stay && <PanelBody key={stay.id} stay={stay} {...props} />}
      </SheetContent>
    </Sheet>
  )
}

function PanelBody({ stay, index, businessDate, onMove, onUnassign }: Omit<StayPanelProps, 'stay' | 'onClose'> & { stay: CalStay }) {
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)
  const queryClient = useQueryClient()
  const canManage = useCan('bookings.manage')
  const canCheckIn = useCan('bookings.checkin')
  const canLeaveWithBalance = useCan('bookings.checkout_with_balance')
  const detailQuery = useReservation(stay.reservation_id)
  const detail = detailQuery.data
  const [problem, setProblem] = useState<Problem | null>(null)

  const room = stay.room_id ? index.rooms.get(stay.room_id) : undefined
  const place = placeLabel(t, index, stay.room_id, stay.bed_id)
  const bookedName = pick(index.roomTypeNames.get(stay.room_type_id), lang)
  const upgrade = Boolean(room && room.roomTypeId !== stay.room_type_id)
  const pending = stay.status === 'tentative' || stay.status === 'confirmed'

  function settled(response: ReservationDetail) {
    queryClient.setQueryData(calendarKeys.reservation(response.id), response)
    void queryClient.invalidateQueries({ queryKey: calendarKeys.all })
  }

  function failed(error: unknown) {
    if (isApiError(error) && error.code === 'room_not_ready') {
      const status = String(error.data?.housekeeping_status ?? 'dirty')
      setProblem({ kind: 'room_not_ready', room: room?.number ?? '', status })
    } else if (isApiError(error) && error.code === 'balance_due') {
      setProblem({ kind: 'balance_due', amount: String(error.data?.amount ?? '') })
    } else {
      setProblem({ kind: 'error', message: errorMessage(error, t) })
    }
  }

  const checkInMutation = useMutation({
    mutationFn: (force: boolean) => checkIn(stay.id, force),
    onMutate: () => setProblem(null),
    onSuccess: (response) => {
      const now = response.stays.find((candidate) => candidate.id === stay.id)
      const where = now?.bed
        ? t('bar.bed', { label: now.bed.label, room: now.room?.number ?? '' })
        : now?.room
          ? t('bar.room', { number: now.room.number })
          : place
      calendarToast.success(t('panel.checkedIn', { guest: stay.guest_name, place: where }))
      settled(response)
    },
    onError: failed,
  })
  const checkOutMutation = useMutation({
    mutationFn: (force: boolean) => checkOut(stay.id, force),
    onMutate: () => setProblem(null),
    onSuccess: (response) => {
      calendarToast.success(t('panel.checkedOut', { guest: stay.guest_name }))
      settled(response)
    },
    onError: failed,
  })
  const busy = checkInMutation.isPending || checkOutMutation.isPending

  const showCheckIn = canCheckIn && stay.status === 'confirmed' && stay.checkin <= businessDate && stay.checkout > businessDate
  const showCheckOut = canCheckIn && stay.status === 'checked_in'
  const showMove = canManage && stay.status !== 'checked_out'
  const showUnassign = canManage && pending && stay.room_id !== null
  const reservationPath = `/app/reservations/${stay.reservation_id}`
  const balance = detail ? Number(detail.balance) : null

  return (
    <>
      <SheetHeader>
        <div className="flex flex-wrap items-center gap-2">
          <span className="num eyebrow">{stay.code}</span>
          <StatusBadge kind="reservation" status={stay.status} />
        </div>
        <SheetTitle className="flex items-center gap-2 text-lg">
          {stay.guest_name}
          {stay.is_vip && (
            <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-1.5 py-px text-2xs font-bold text-accent-ink">
              <Star aria-hidden className="size-3 fill-current" />
              {t('bar.vip')}
            </span>
          )}
        </SheetTitle>
        <SheetDescription className="num">
          {formatDateRange(stay.checkin, stay.checkout, lang)} · {stay.room_id ? place : t('panel.noRoom')}
        </SheetDescription>
      </SheetHeader>

      <SheetBody className="grid content-start gap-5">
        <div className="grid grid-cols-[1fr_1fr_auto] gap-3 rounded-lg border border-border bg-surface-2/60 px-4 py-3">
          <DateFact label={t('panel.arrival')} value={formatDate(stay.checkin, 'EEE d MMM', lang)} />
          <DateFact label={t('panel.departure')} value={formatDate(stay.checkout, 'EEE d MMM', lang)} />
          <DateFact label={t('panel.nights')} value={String(nightsOf(stay))} />
        </div>

        <dl className="grid grid-cols-[7.5rem_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-[13px]">
          <Fact label={t('panel.room')}>
            <span className="flex items-center gap-2">
              {room && <RoomKeyTag number={room.number} status={room.status} size="sm" />}
              <span className={cn('font-semibold', !stay.room_id && 'text-warning-ink')}>{stay.room_id ? place : t('panel.noRoom')}</span>
            </span>
          </Fact>
          <Fact label={t('panel.category')}>
            <span className="font-semibold">{bookedName}</span>
            {upgrade && (
              <span className="mt-0.5 flex items-center gap-1 text-xs text-muted">
                <ArrowUpRight aria-hidden className="size-3" />
                {t('panel.upgrade', { category: bookedName })}
              </span>
            )}
          </Fact>
          <Fact label={t('panel.guests')}>
            {[t('panel.adults', { count: stay.adults }), stay.children > 0 ? t('panel.children', { count: stay.children }) : null]
              .filter(Boolean)
              .join(' · ')}
          </Fact>
          <Fact label={t('panel.channel')}>{sourceLabel(t, stay)}</Fact>
          <Fact label={t('panel.total')}>
            {detail ? <span className="num font-semibold">{formatMoney(detail.total_amount, detail.currency)}</span> : <Skeleton className="h-4 w-24" />}
          </Fact>
          <Fact label={t('panel.balance')}>
            {detail && balance !== null ? (
              balance > 0 ? (
                <span className="num font-bold text-warning-ink">{formatMoney(detail.balance, detail.currency)}</span>
              ) : (
                <span className="text-success-ink">{t('panel.settled')}</span>
              )
            ) : (
              <Skeleton className="h-4 w-20" />
            )}
          </Fact>
          {detail?.eta && <Fact label={t('panel.eta')}>{detail.eta.slice(0, 5)}</Fact>}
          {detail?.special_requests && <Fact label={t('panel.requests')}>{detail.special_requests}</Fact>}
          {detail?.notes && <Fact label={t('panel.notes')}>{detail.notes}</Fact>}
        </dl>
        {detailQuery.isPending && <p className="sr-only">{t('panel.loadingDetail')}</p>}

        {problem && (
          <div role="alert" className="grid gap-2.5 rounded-lg border border-warning/30 bg-warning-soft/60 px-3.5 py-3 text-[13px] text-fg">
            <p className="flex items-start gap-2">
              <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-warning-ink" />
              <span>
                {problem.kind === 'room_not_ready'
                  ? t('panel.roomNotReady', {
                      room: problem.room,
                      status: t(`status.room.${problem.status}`, { ns: 'common', defaultValue: problem.status }).toLocaleLowerCase(lang),
                    })
                  : problem.kind === 'balance_due'
                    ? t('panel.balanceDue', { amount: formatMoney(problem.amount, detail?.currency ?? 'COP') })
                    : problem.message}
              </span>
            </p>
            {problem.kind === 'room_not_ready' && (
              <Button size="sm" variant="secondary" className="justify-self-start" loading={checkInMutation.isPending} onClick={() => checkInMutation.mutate(true)}>
                {t('panel.forceCheckIn')}
              </Button>
            )}
            {problem.kind === 'balance_due' && (
              <div className="flex flex-wrap gap-2">
                <Button asChild size="sm" variant="primary">
                  <Link to={reservationPath}>{t('panel.collect')}</Link>
                </Button>
                {canLeaveWithBalance && (
                  <Button size="sm" variant="secondary" loading={checkOutMutation.isPending} onClick={() => checkOutMutation.mutate(true)}>
                    {t('panel.forceCheckOut')}
                  </Button>
                )}
              </div>
            )}
          </div>
        )}
      </SheetBody>

      <SheetFooter className="flex-wrap">
        <div role="group" aria-label={t('panel.actions')} className="flex flex-1 flex-wrap gap-2">
          {showCheckIn && (
            <Button variant="primary" size="sm" loading={checkInMutation.isPending} disabled={busy} onClick={() => checkInMutation.mutate(false)}>
              <LogIn aria-hidden />
              {t('panel.checkIn')}
            </Button>
          )}
          {showCheckOut && (
            <Button variant="primary" size="sm" loading={checkOutMutation.isPending} disabled={busy} onClick={() => checkOutMutation.mutate(false)}>
              <LogOut aria-hidden />
              {t('panel.checkOut')}
            </Button>
          )}
          {showMove && (
            <Button size="sm" disabled={busy} onClick={() => onMove(stay)}>
              <MoveRight aria-hidden />
              {t('panel.move')}
            </Button>
          )}
          {showUnassign && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => onUnassign(stay)}>
              <DoorOpen aria-hidden />
              {t('panel.unassign')}
            </Button>
          )}
        </div>
        <Button asChild size="sm" variant="link">
          <Link to={reservationPath}>
            {t('panel.open')}
            <SquareArrowOutUpRight aria-hidden className="size-3.5" />
          </Link>
        </Button>
      </SheetFooter>
    </>
  )
}

function DateFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="eyebrow">{label}</p>
      <p className="num truncate text-[15px] leading-6 font-bold text-fg">{value}</p>
    </div>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="pt-px text-muted">{label}</dt>
      <dd className="min-w-0 text-fg">{children}</dd>
    </>
  )
}
