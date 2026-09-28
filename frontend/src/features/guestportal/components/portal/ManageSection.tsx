import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CalendarRange, CircleSlash } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DateRangePicker } from '@/components/DatePicker'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { nightsBetween, normalizeLang } from '@/lib/format'
import {
  cancelBooking,
  modifyBooking,
  portalKeys,
  previewModification,
  type ModificationPreview,
  type PortalSummary,
} from '../../api'
import { portalError } from '../../lib/errors'
import { moneyLabel } from '../../lib/money'
import { formatHotelDateTime } from '../../lib/text'

const CLOSED = ['cancelled', 'checked_out', 'no_show']

/** Change dates or cancel, always within the rate's policy (the backend decides what is allowed). */
export function ManageSection({ summary, token }: { summary: PortalSummary; token: string }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const [dialog, setDialog] = useState<'cancel' | 'modify' | null>(null)
  const { cancellation, modification, reservation, property } = summary
  if (CLOSED.includes(reservation.status)) return null
  const fee = Number(cancellation.fee)
  const freeUntil = formatHotelDateTime(cancellation.free_until, property.timezone, lang)

  const policy = cancellation.non_refundable
    ? t('manage.nonRefundable')
    : fee > 0
      ? t('manage.feeNow', { amount: moneyLabel(fee, cancellation.currency) })
      : freeUntil
        ? t('manage.freeUntil', { date: freeUntil })
        : t('manage.free')

  return (
    <section aria-labelledby="manage-title" className="grid gap-3 rounded-2xl border border-border bg-surface p-5">
      <div>
        <h2 id="manage-title" className="text-lg font-bold">
          {t('manage.title')}
        </h2>
        <p className="text-sm text-muted">{policy}</p>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        {modification.can_modify ? (
          <Button onClick={() => setDialog('modify')}>
            <CalendarRange aria-hidden />
            {t('manage.changeDates')}
          </Button>
        ) : (
          modification.reason && <p className="text-[13px] text-muted sm:col-span-2">{t(`manage.modifyReasons.${modification.reason}`)}</p>
        )}
        {cancellation.can_cancel ? (
          <Button variant="ghost" className="text-danger-ink hover:bg-danger-soft" onClick={() => setDialog('cancel')}>
            <CircleSlash aria-hidden />
            {t('manage.cancel')}
          </Button>
        ) : (
          cancellation.reason && <p className="text-[13px] text-muted sm:col-span-2">{t(`manage.cancelReasons.${cancellation.reason}`)}</p>
        )}
      </div>
      {dialog === 'cancel' && <CancelDialog summary={summary} token={token} onClose={() => setDialog(null)} />}
      {dialog === 'modify' && <ModifyDialog summary={summary} token={token} onClose={() => setDialog(null)} />}
    </section>
  )
}

function CancelDialog({ summary, token, onClose }: { summary: PortalSummary; token: string; onClose: () => void }) {
  const { t } = useTranslation('guestportal')
  const queryClient = useQueryClient()
  const { cancellation, reservation } = summary
  const fee = Number(cancellation.fee)
  const [reason, setReason] = useState('')
  const [acknowledged, setAcknowledged] = useState(fee <= 0)
  const cancel = useMutation({
    mutationFn: () => cancelBooking(token, reason.trim()),
    onSuccess: (updated) => {
      queryClient.setQueryData(portalKeys.portal(token), updated)
      toast.success(t('cancel.done'))
      onClose()
    },
  })

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('cancel.title', { code: reservation.code })}</DialogTitle>
          <DialogDescription>
            {fee > 0
              ? t('cancel.fee', { amount: moneyLabel(fee, cancellation.currency), reason: t(`cancel.feeReasons.${cancellation.fee_reason}`, { defaultValue: '' }) })
              : t('cancel.free')}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          {fee > 0 && (
            <div className="flex items-start gap-2.5">
              <Checkbox id="cancel-ack" name="acknowledge" checked={acknowledged} onCheckedChange={(value) => setAcknowledged(value === true)} className="mt-0.5" />
              <Label htmlFor="cancel-ack" className="font-medium">
                {t('cancel.acknowledge', { amount: moneyLabel(fee, cancellation.currency) })}
              </Label>
            </div>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="cancel-reason">{t('cancel.reason')}</Label>
            <Textarea id="cancel-reason" name="reason" value={reason} maxLength={500} onChange={(event) => setReason(event.target.value)} />
          </div>
          {cancel.isError && (
            <p role="alert" className="text-sm font-medium text-danger-ink">
              {portalError(cancel.error, t)}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t('cancel.keep')}
          </Button>
          <Button variant="danger" disabled={!acknowledged} loading={cancel.isPending} onClick={() => cancel.mutate()}>
            {t('cancel.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ModifyDialog({ summary, token, onClose }: { summary: PortalSummary; token: string; onClose: () => void }) {
  const { t } = useTranslation('guestportal')
  const queryClient = useQueryClient()
  const { reservation, modification, today } = summary
  const [range, setRange] = useState<{ from: string; to: string } | null>({ from: reservation.checkin_date, to: reservation.checkout_date })
  const [preview, setPreview] = useState<ModificationPreview | null>(null)
  const nights = range ? nightsBetween(range.from, range.to) : 0
  const tooLong = nights > modification.max_nights
  const unchanged = range?.from === reservation.checkin_date && range?.to === reservation.checkout_date
  const ask = useMutation({
    mutationFn: () => previewModification(token, range!.from, range!.to),
    onSuccess: setPreview,
  })
  const apply = useMutation({
    mutationFn: () => modifyBooking(token, range!.from, range!.to),
    onSuccess: (result) => {
      queryClient.setQueryData(portalKeys.portal(token), result.summary)
      toast.success(t('modify.done'))
      onClose()
    },
  })
  const error = ask.error ?? apply.error

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('modify.title')}</DialogTitle>
          <DialogDescription>{t('modify.description')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="modify-dates">{t('modify.dates')}</Label>
            <DateRangePicker
              id="modify-dates"
              value={range}
              onChange={(next) => {
                setRange(next)
                setPreview(null)
                ask.reset()
                apply.reset()
              }}
              today={today}
              min={today}
              minNights={1}
              numberOfMonths={1}
              showNights
              aria-invalid={tooLong}
            />
            {tooLong && <p className="text-xs font-medium text-danger-ink">{t('modify.maxNights', { count: modification.max_nights })}</p>}
          </div>
          {preview && (
            <dl className="grid gap-1.5 rounded-lg bg-surface-2 px-4 py-3 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{t('modify.currentTotal')}</dt>
                <dd>
                  <MoneyText value={preview.current_total} currency={preview.currency} />
                </dd>
              </div>
              <div className="flex justify-between gap-3 font-bold">
                <dt>{t('modify.newTotal')}</dt>
                <dd>
                  <MoneyText value={preview.total} currency={preview.currency} />
                </dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-muted">{t('modify.difference')}</dt>
                <dd>
                  {Number(preview.difference) > 0 ? '+' : ''}
                  <MoneyText value={preview.difference} currency={preview.currency} />
                </dd>
              </div>
            </dl>
          )}
          {error && (
            <p role="alert" className="text-sm font-medium text-danger-ink">
              {portalError(error, t)}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t('common:actions.cancel')}
          </Button>
          {preview ? (
            <Button variant="primary" loading={apply.isPending} onClick={() => apply.mutate()}>
              {t('modify.confirm')}
            </Button>
          ) : (
            <Button variant="primary" disabled={!range || tooLong || unchanged} loading={ask.isPending} onClick={() => ask.mutate()}>
              {t('modify.preview')}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
