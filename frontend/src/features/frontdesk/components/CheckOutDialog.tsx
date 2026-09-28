import { useQueryClient } from '@tanstack/react-query'
import { CircleAlert, LogOut } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatMoney, nightsBetween, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { bookingKeys, checkOut, useRefreshFrontDesk, useReservation, type ReservationDetail, type StayDetail } from '../api'
import { shortDay, stayLine, unitLabel } from '../lib/labels'

const FolioPanel = lazy(() => import('@/features/finance/components/FolioPanel'))

export interface CheckOutDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  stayId: string
  reservationId: string
  onDone?: (reservation: ReservationDetail) => void
}

/**
 * Check-out (plan C1): the folio (collect what is due right there) and the confirmation. With a balance due
 * the check-out is blocked, unless the role has `bookings.checkout_with_balance` and says so explicitly.
 * Leaving before the booked date is an early departure: the backend releases the nights from today on.
 */
export function CheckOutDialog({ open, onOpenChange, stayId, reservationId, onDone }: CheckOutDialogProps) {
  const { t } = useTranslation('frontdesk')
  const reservation = useReservation(open ? reservationId : undefined)
  const stay = reservation.data?.stays.find((item) => item.id === stayId)
  const name = reservation.data?.booker.full_name ?? ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{name ? t('checkout.title', { name }) : t('checkout.titleLoading')}</DialogTitle>
          <Description reservation={reservation.data} stay={stay} />
        </DialogHeader>
        {reservation.isError ? (
          <ErrorState error={reservation.error} onRetry={() => reservation.refetch()} />
        ) : !reservation.data || !stay ? (
          <LoadingState variant="rows" rows={4} />
        ) : (
          <CheckOutForm
            reservation={reservation.data}
            stay={stay}
            onCancel={() => onOpenChange(false)}
            onDone={(detail) => {
              onDone?.(detail)
              onOpenChange(false)
            }}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}

function Description({ reservation, stay }: { reservation?: ReservationDetail; stay?: StayDetail }) {
  const { t, i18n } = useTranslation('frontdesk')
  if (!reservation || !stay) return <DialogDescription className="sr-only">{t('checkin.loading')}</DialogDescription>
  const unit = unitLabel(stay.room?.number, stay.bed?.label)
  const line = stayLine(t, normalizeLang(i18n.language), {
    checkin: stay.checkin_date,
    checkout: stay.checkout_date,
    nights: stay.nights,
    adults: stay.adults,
    children: stay.children,
  })
  return (
    <DialogDescription>
      <span className="num font-semibold text-fg">{reservation.code}</span>
      {unit && ` · ${t('checkout.room', { room: unit })}`} · {line}
    </DialogDescription>
  )
}

function CheckOutForm({
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
  const bd = property?.business_date ?? stay.checkout_date
  const canForce = useCan('bookings.checkout_with_balance')
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const [withBalance, setWithBalance] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const balance = Number(reservation.balance)
  const due = balance > 0
  const released = stay.checkout_date > bd ? nightsBetween(bd, stay.checkout_date) : 0
  const blocked = due && !(canForce && withBalance)

  async function confirm() {
    setSaving(true)
    setError(null)
    try {
      const detail = await checkOut(stay.id, due && withBalance)
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      toast.success(t('checkout.done', { name: reservation.booker.full_name, room: unitLabel(stay.room?.number, stay.bed?.label) ?? '' }))
      onDone(detail)
    } catch (err) {
      setError(errorMessage(err, t))
      await queryClient.invalidateQueries({ queryKey: bookingKeys.reservation(reservation.id) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="grid gap-4">
        {released > 0 && (
          <p className="rounded-lg bg-info-soft px-3 py-2 text-[13px] text-info-ink">
            {t('checkout.early', { count: released, from: shortDay(bd, lang), to: shortDay(stay.checkout_date, lang) })}
          </p>
        )}
        <Suspense fallback={<LoadingState variant="rows" rows={2} className="p-0" />}>
          <FolioPanel
            reservationId={reservation.id}
            compact
            onChange={() => {
              void queryClient.invalidateQueries({ queryKey: bookingKeys.reservation(reservation.id) })
              void refresh()
            }}
          />
        </Suspense>
        {due && (
          <div className="grid gap-2 rounded-lg border border-warning/30 bg-warning-soft/60 px-3 py-2.5">
            <p className="flex items-start gap-2 text-[13px] text-warning-ink">
              <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
              {t('checkout.balanceDue', { amount: formatMoney(reservation.balance, reservation.currency) })}
            </p>
            {canForce && (
              <div className="flex items-center gap-2 pl-5.5">
                <Checkbox id={`force-${stay.id}`} checked={withBalance} onCheckedChange={(value) => setWithBalance(value === true)} />
                <Label htmlFor={`force-${stay.id}`} className="text-[13px] font-semibold">
                  {t('checkout.withBalance')}
                </Label>
              </div>
            )}
          </div>
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
        <Button variant="primary" onClick={() => void confirm()} loading={saving} disabled={blocked || stay.status !== 'checked_in'}>
          <LogOut aria-hidden />
          {t('checkout.confirm')}
        </Button>
      </DialogFooter>
    </>
  )
}
