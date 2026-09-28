import { useQueryClient } from '@tanstack/react-query'
import { CircleAlert } from 'lucide-react'
import { useId, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatMoney, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { bookingKeys, cancelStay, useRefreshFrontDesk, useStayCancelPreview, type ReservationDetail, type StayDetail } from '../api'
import { stayLine, tr, unitLabel } from '../lib/labels'

/**
 * Cancel one room of a multi-room reservation (pilot P3) with its proportional penalty in view
 * (`stays/{id}/cancel-preview/`). The last active room cancels the whole reservation, and the dialog says so.
 * Waiving the penalty needs `bookings.waive_fee` and typing the reservation code (spec §3).
 */
export function CancelStayDialog({
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
  const ids = { reason: useId(), waive: useId(), code: useId() }
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const canWaive = useCan('bookings.waive_fee')
  const preview = useStayCancelPreview(stay.id, open)
  const [reason, setReason] = useState('')
  const [waive, setWaive] = useState(false)
  const [typed, setTyped] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fee = Number(preview.data?.fee ?? 0)
  const codeOk = !waive || typed.trim().toUpperCase() === reservation.code
  const ready = reason.trim().length > 0 && Boolean(preview.data) && codeOk
  const unit = unitLabel(stay.room?.number, stay.bed?.label)

  async function confirm() {
    setSaving(true)
    setError(null)
    try {
      const detail = await cancelStay(stay.id, reason.trim(), waive)
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      toast.success(detail.status === 'cancelled' ? t('cancel.done', { code: reservation.code }) : t('cancelStay.done'))
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, t))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !saving && onOpenChange(next)}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('cancelStay.title')}</DialogTitle>
          <DialogDescription>
            {tr(stay.room_type.name, i18n.language)}
            {unit ? ` · ${unit}` : ''} ·{' '}
            {stayLine(t, lang, { checkin: stay.checkin_date, checkout: stay.checkout_date, nights: stay.nights, adults: stay.adults, children: stay.children })}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="rounded-lg border border-border bg-surface-2/60 px-4 py-3 text-[13px]" aria-live="polite">
            {preview.isPending ? (
              <LoadingState variant="rows" rows={1} className="p-0" />
            ) : preview.isError ? (
              <p role="alert" className="text-danger-ink">
                {errorMessage(preview.error, t)}
              </p>
            ) : (
              <>
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-muted">{t('cancelStay.roomTotal')}</span>
                  <MoneyText value={preview.data.stay_total} currency={preview.data.currency} className="font-semibold text-fg" />
                </div>
                {fee > 0 ? (
                  <>
                    <p className="mt-1 font-semibold text-warning-ink">{t('cancel.fee', { amount: formatMoney(preview.data.fee, preview.data.currency) })}</p>
                    <p className="text-muted">{t(`cancel.reasons.${preview.data.reason}`, { defaultValue: '' })}</p>
                  </>
                ) : (
                  <>
                    <p className="mt-1 font-semibold text-success-ink">{t('cancel.noFee')}</p>
                    {preview.data.free_until && (
                      <p className="text-muted">{t('cancel.freeUntil', { date: formatDate(preview.data.free_until, lang === 'en' ? 'MMM d, HH:mm' : 'd MMM, HH:mm', lang) })}</p>
                    )}
                  </>
                )}
              </>
            )}
          </div>
          {preview.data?.cancels_reservation && (
            <p className="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">
              <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
              {t('cancelStay.lastRoom', { code: reservation.code })}
            </p>
          )}
          {preview.data?.ends_reservation && (
            <p className="flex items-start gap-2 rounded-lg bg-info-soft px-3 py-2 text-[13px] text-info-ink">
              <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
              {t('cancelStay.endsReservation')}
            </p>
          )}
          <div className="grid gap-2">
            <Label htmlFor={ids.reason} className="font-semibold">
              {t('cancel.reason')}
            </Label>
            <Textarea id={ids.reason} value={reason} onChange={(event) => setReason(event.target.value)} rows={2} placeholder={t('cancelStay.reasonPlaceholder')} />
          </div>
          {fee > 0 && canWaive && (
            <div className="grid gap-3 rounded-lg border border-danger/25 bg-danger-soft/40 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor={ids.waive} className="text-[13px] font-semibold">
                  {t('cancel.waive')}
                </Label>
                <Switch id={ids.waive} checked={waive} onCheckedChange={setWaive} />
              </div>
              {waive && (
                <div className="grid gap-1.5">
                  <Label htmlFor={ids.code} className="text-[13px] text-muted">
                    <Trans t={t} i18nKey="cancel.typeCode" values={{ code: reservation.code }} components={{ strong: <strong className="num font-bold text-fg" /> }} />
                  </Label>
                  <Input id={ids.code} value={typed} onChange={(event) => setTyped(event.target.value)} autoComplete="off" spellCheck={false} className="num bg-surface" />
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
          <Button variant="secondary" onClick={() => onOpenChange(false)} disabled={saving}>
            {t('common:actions.back')}
          </Button>
          <Button variant="danger" onClick={() => void confirm()} loading={saving} disabled={!ready}>
            {preview.data?.cancels_reservation ? t('cancel.confirm') : t('cancelStay.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
