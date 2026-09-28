import { useQueryClient } from '@tanstack/react-query'
import { addDays } from 'date-fns'
import { CalendarMinus, CalendarPlus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DatePicker, DateRangePicker } from '@/components/DatePicker'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { useActiveProperty } from '@/lib/auth'
import { errorMessage } from '@/lib/errors'
import { formatMoney, nightsBetween, normalizeLang, parseDate, toISODate } from '@/lib/format'
import { cn } from '@/lib/utils'
import { bookingKeys, modifyStay, useModifyPreview, useRefreshFrontDesk, type ReservationDetail, type StayDetail } from '../api'
import { stayLine, unitLabel } from '../lib/labels'

function shift(day: string, days: number): string {
  return toISODate(addDays(parseDate(day) ?? new Date(), days))
}

/**
 * Change a stay's dates with the new price in view before saving (`modify-preview` → `modify`, repriced).
 * A guest in house keeps the arrival: only the departure moves (extend or leave earlier).
 */
export function ModifyStayDialog({
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
  const lang = normalizeLang(i18n.language)
  const { property } = useActiveProperty()
  const bd = property?.business_date ?? stay.checkin_date
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const inHouse = stay.status === 'checked_in'
  const [checkin, setCheckin] = useState(stay.checkin_date)
  const [checkout, setCheckout] = useState(stay.checkout_date)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const changed = checkin !== stay.checkin_date || checkout !== stay.checkout_date
  const input = { checkin, checkout, reprice: true }
  const preview = useModifyPreview(stay.id, input, open && changed && checkout > checkin)
  const nights = nightsBetween(checkin, checkout)
  const minCheckout = shift(inHouse ? (bd > checkin ? bd : checkin) : checkin, 1)

  async function save() {
    setSaving(true)
    setError(null)
    try {
      const detail = await modifyStay(stay.id, input)
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      toast.success(t('modify.done'))
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setSaving(false)
    }
  }

  const difference = preview.data ? Number(preview.data.difference) : 0
  const unit = unitLabel(stay.room?.number, stay.bed?.label)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('modify.title')}</DialogTitle>
          <DialogDescription>
            {stayLine(t, lang, { checkin: stay.checkin_date, checkout: stay.checkout_date, nights: stay.nights, adults: stay.adults, children: stay.children })}
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4">
          {inHouse ? (
            <div className="grid gap-2">
              <Label className="font-semibold">{t('modify.departure')}</Label>
              <DatePicker value={checkout} onChange={(value) => value && setCheckout(value)} min={minCheckout} aria-label={t('modify.departure')} className="max-w-xs" />
            </div>
          ) : (
            <div className="grid gap-2">
              <Label className="font-semibold">{t('modify.dates')}</Label>
              <DateRangePicker
                value={{ from: checkin, to: checkout }}
                onChange={(range) => {
                  if (!range) return
                  setCheckin(range.from)
                  setCheckout(range.to)
                }}
                today={bd}
                min={bd}
                minNights={1}
                showNights
                aria-label={t('modify.dates')}
                className="max-w-sm"
              />
            </div>
          )}
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => setCheckout(shift(checkout, -1))} disabled={checkout <= minCheckout}>
              <CalendarMinus aria-hidden />
              {t('modify.nightLess')}
            </Button>
            <Button size="sm" onClick={() => setCheckout(shift(checkout, 1))}>
              <CalendarPlus aria-hidden />
              {t('modify.nightMore')}
            </Button>
            <span className="num self-center text-[13px] text-muted">{t('common:date.nights', { count: nights })}</span>
          </div>

          {changed && (
            <div className="rounded-lg border border-border bg-surface-2/60 px-4 py-3" aria-live="polite">
              {preview.isFetching && !preview.data ? (
                <LoadingState variant="rows" rows={1} className="p-0" />
              ) : preview.isError ? (
                <p role="alert" className="text-[13px] text-danger-ink">
                  {errorMessage(preview.error, t)}
                </p>
              ) : preview.data ? (
                <dl className="grid gap-1 text-[13px]">
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted">{t('modify.newTotal')}</dt>
                    <dd>
                      <MoneyText value={preview.data.stay.total_amount} currency={reservation.currency} className="font-semibold text-fg" />
                    </dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted">{t('modify.difference')}</dt>
                    <dd className={cn('num font-semibold', difference > 0 ? 'text-warning-ink' : difference < 0 ? 'text-success-ink' : 'text-muted')}>
                      {difference === 0
                        ? t('modify.noDifference')
                        : `${difference > 0 ? '+' : '−'} ${formatMoney(Math.abs(difference), reservation.currency)}`}
                    </dd>
                  </div>
                  {unit && preview.data.room_kept !== null && (
                    <p className={cn('mt-1', preview.data.room_kept ? 'text-success-ink' : 'text-warning-ink')}>
                      {t(preview.data.room_kept ? 'modify.roomKept' : 'modify.roomLost', { room: unit })}
                    </p>
                  )}
                </dl>
              ) : null}
            </div>
          )}
          {error && (
            <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
              {error}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={saving}>
            {t('common:actions.cancel')}
          </Button>
          <Button variant="primary" onClick={() => void save()} loading={saving} disabled={!changed || !preview.data || preview.isError}>
            {t('common:actions.saveChanges')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
