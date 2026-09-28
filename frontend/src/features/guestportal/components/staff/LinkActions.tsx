import { useMutation, useQuery } from '@tanstack/react-query'
import { Check, Copy, ExternalLink, Send } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { DialogFooter } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { errorMessage } from '@/lib/errors'
import { getPortalLink, getReservationCheckin, portalKeys, sendCheckinLink, type SendLinkResult } from '../../api'

type Channel = 'email' | 'whatsapp'

/** A read-only URL with a copy button (the staff shares the link by hand when nothing was sent). */
function CopyField({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation('guestportal')
  const id = useId()
  const [copied, setCopied] = useState(false)
  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex gap-2">
        <Input id={id} readOnly value={value} onFocus={(event) => event.currentTarget.select()} className="num min-w-0 flex-1 text-[13px]" />
        <Button
          aria-label={t('common:actions.copy')}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value)
              setCopied(true)
              window.setTimeout(() => setCopied(false), 2000)
            } catch {
              /* clipboard blocked: the field is selectable */
            }
          }}
        >
          {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
          <span className="hidden sm:inline">{copied ? t('common:actions.copied') : t('common:actions.copy')}</span>
        </Button>
      </div>
    </div>
  )
}

/** Reservation action "Enviar link de check-in": the `checkin_invitation` message (email and/or WhatsApp). */
export function SendLinkAction({ reservationId, close }: { reservationId: string; close: () => void }) {
  const { t } = useTranslation('guestportal')
  const checkin = useQuery({ queryKey: portalKeys.reservationCheckin(reservationId), queryFn: () => getReservationCheckin(reservationId) })
  const booker = checkin.data?.guests.find((slot) => slot.role === 'booker')
  const data = booker && 'full_name' in booker.data ? booker.data : null
  const [channels, setChannels] = useState<Channel[]>(['email'])
  const [result, setResult] = useState<SendLinkResult | null>(null)
  const send = useMutation({ mutationFn: () => sendCheckinLink(reservationId, channels), onSuccess: setResult })
  const toggle = (channel: Channel, on: boolean) =>
    setChannels((current) => (on ? [...new Set([...current, channel])] : current.filter((item) => item !== channel)))
  const sentBy = result?.messages.filter((message) => message.status !== 'failed').map((message) => t(`send.${message.channel}`, { defaultValue: message.channel }))
  const reason = checkin.data?.window.reason
  const inactive = reason === 'cancelled' || reason === 'no_show'
  const notice = inactive
    ? t('send.inactive')
    : checkin.data?.status === 'completed'
      ? t('send.alreadyDone')
      : reason === 'checked_in' || reason === 'checked_out' || reason === 'past'
        ? t('send.closed')
        : null

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted">
        {data ? t('send.description', { name: [data.full_name, data.email].filter(Boolean).join(' · ') }) : t('link.description')}
      </p>
      {notice && !result && <p className="rounded-lg bg-warning-soft px-3 py-2 text-sm text-warning-ink">{notice}</p>}
      {checkin.isError ? (
        <ErrorState error={checkin.error} onRetry={() => checkin.refetch()} />
      ) : result ? (
        <div className="grid gap-4">
          <p role="status" className={sentBy?.length ? 'text-sm font-semibold text-success-ink' : 'text-sm font-semibold text-warning-ink'}>
            {sentBy?.length ? t('send.sent', { channels: sentBy.join(', ') }) : result.send_error ? t('send.failed') : t('send.none')}
          </p>
          <CopyField label={t('link.checkin')} value={result.checkin_url} />
        </div>
      ) : (
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-[13px] font-semibold">{t('send.channels')}</legend>
          {(['email', 'whatsapp'] as Channel[]).map((channel) => (
            <div key={channel} className="flex items-center gap-2.5">
              <Checkbox
                id={`send-${channel}`}
                name="send_via"
                value={channel}
                checked={channels.includes(channel)}
                onCheckedChange={(value) => toggle(channel, value === true)}
              />
              <Label htmlFor={`send-${channel}`} className="font-medium">
                {t(`send.${channel}`)}
                {channel === 'email' && data?.email ? <span className="ml-1.5 text-muted">{data.email}</span> : null}
                {channel === 'whatsapp' && data?.phone ? <span className="ml-1.5 text-muted">{data.phone}</span> : null}
              </Label>
            </div>
          ))}
          {!channels.length && <p className="text-xs font-medium text-danger-ink">{t('send.pickOne')}</p>}
          {send.isError && (
            <p role="alert" className="text-sm font-medium text-danger-ink">
              {errorMessage(send.error, t)}
            </p>
          )}
        </fieldset>
      )}
      <DialogFooter>
        <Button variant="ghost" onClick={close}>
          {t('common:actions.close')}
        </Button>
        {!result && (
          <Button variant="primary" disabled={!channels.length || checkin.isPending || inactive} loading={send.isPending} onClick={() => send.mutate()}>
            <Send aria-hidden />
            {t('send.submit')}
          </Button>
        )}
      </DialogFooter>
    </div>
  )
}

/** Reservation action "Copiar link / QR": the magic link and a QR code to scan at the front desk. */
export function LinkQrAction({ reservationId, close }: { reservationId: string; close: () => void }) {
  const { t } = useTranslation('guestportal')
  const link = useQuery({ queryKey: portalKeys.link(reservationId), queryFn: () => getPortalLink(reservationId) })

  return (
    <div className="grid gap-4">
      <p className="text-sm text-muted">{t('link.description')}</p>
      {link.isPending ? (
        <LoadingState />
      ) : link.isError ? (
        <ErrorState error={link.error} onRetry={() => link.refetch()} />
      ) : (
        <div className="grid gap-4">
          <figure className="grid justify-items-center gap-2">
            <img src={link.data.qr_png} alt={t('link.qr')} className="size-44 rounded-lg border border-border bg-white p-2" />
            <figcaption className="text-[12px] text-muted">{t('link.qrHint')}</figcaption>
          </figure>
          <CopyField label={t('link.portal')} value={link.data.url} />
          <CopyField label={t('link.checkin')} value={link.data.checkin_url} />
        </div>
      )}
      <DialogFooter>
        <Button variant="ghost" onClick={close}>
          {t('common:actions.close')}
        </Button>
        {link.data && (
          <Button asChild variant="primary">
            <a href={link.data.url} target="_blank" rel="noreferrer">
              <ExternalLink aria-hidden />
              {t('link.open')}
            </a>
          </Button>
        )}
      </DialogFooter>
    </div>
  )
}
