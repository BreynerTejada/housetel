import { useQueryClient } from '@tanstack/react-query'
import { useId, useState } from 'react'
import { Trans, useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatMoney, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { bookingKeys, cancelReservation, useCancelPreview, useRefreshFrontDesk, type ReservationDetail } from '../api'

/**
 * Cancel a reservation with its penalty in view (`cancel-preview`) and a reason. Waiving the penalty is a risky
 * money action (spec §3): it needs `bookings.waive_fee` and typing the reservation code.
 */
export function CancelReservationDialog({
  open,
  onOpenChange,
  reservation,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  reservation: ReservationDetail
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const lang = normalizeLang(i18n.language)
  const ids = { reason: useId(), waive: useId(), code: useId() }
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const canWaive = useCan('bookings.waive_fee')
  const preview = useCancelPreview(reservation.id, open)
  const [reason, setReason] = useState('')
  const [waive, setWaive] = useState(false)
  const [typed, setTyped] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fee = Number(preview.data?.fee ?? 0)
  const codeOk = !waive || typed.trim().toUpperCase() === reservation.code
  const ready = reason.trim().length > 0 && Boolean(preview.data) && codeOk

  async function confirm() {
    setSaving(true)
    setError(null)
    try {
      const detail = await cancelReservation(reservation.id, reason.trim(), waive)
      queryClient.setQueryData(bookingKeys.reservation(reservation.id), detail)
      await refresh()
      toast.success(t('cancel.done', { code: reservation.code }))
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
          <DialogTitle>{t('cancel.title', { code: reservation.code })}</DialogTitle>
          <DialogDescription>{t('cancel.description')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="rounded-lg border border-border bg-surface-2/60 px-4 py-3 text-[13px]" aria-live="polite">
            {preview.isPending ? (
              <LoadingState variant="rows" rows={1} className="p-0" />
            ) : preview.isError ? (
              <p role="alert" className="text-danger-ink">
                {errorMessage(preview.error, t)}
              </p>
            ) : fee > 0 ? (
              <>
                <p className="font-semibold text-warning-ink">{t('cancel.fee', { amount: formatMoney(preview.data.fee, preview.data.currency) })}</p>
                <p className="text-muted">{t(`cancel.reasons.${preview.data.reason}`, { defaultValue: '' })}</p>
              </>
            ) : (
              <>
                <p className="font-semibold text-success-ink">{t('cancel.noFee')}</p>
                {preview.data.free_until && (
                  <p className="text-muted">{t('cancel.freeUntil', { date: formatDate(preview.data.free_until, lang === 'en' ? 'MMM d, HH:mm' : "d MMM, HH:mm", lang) })}</p>
                )}
              </>
            )}
          </div>

          <div className="grid gap-2">
            <Label htmlFor={ids.reason} className="font-semibold">
              {t('cancel.reason')}
            </Label>
            <Textarea id={ids.reason} value={reason} onChange={(event) => setReason(event.target.value)} rows={2} placeholder={t('cancel.reasonPlaceholder')} />
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
            {t('cancel.confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
