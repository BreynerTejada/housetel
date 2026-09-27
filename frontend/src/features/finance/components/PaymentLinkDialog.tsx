import { Check, Copy, ExternalLink, Link2, Mail, MessageCircle, TriangleAlert } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { MoneyInput } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { errorMessage } from '@/lib/errors'
import { formatDate, normalizeLang } from '@/lib/format'
import { createPaymentLink, useFinanceMutation, type GuestRef, type LinkChannel, type Money, type PaymentLinkResult } from '../api'
import { moneyLabel, toNumber } from '../money'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  folioId: string
  suggestedAmount: Money
  currency: string
  guest: GuestRef | null
  onDone?: () => void
}

/** "Link de pago": an online checkout (Wompi or the simulated gateway) to copy, show as QR or send. */
export function PaymentLinkDialog({ open, onOpenChange, folioId, suggestedAmount, currency, guest, onDone }: Props) {
  const { t } = useTranslation('finance')
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{t('link.title')}</DialogTitle>
          <DialogDescription>{t('link.description')}</DialogDescription>
        </DialogHeader>
        <LinkFlow
          folioId={folioId}
          suggestedAmount={suggestedAmount}
          currency={currency}
          guest={guest}
          onClose={() => onOpenChange(false)}
          onDone={onDone}
        />
      </DialogContent>
    </Dialog>
  )
}

function LinkFlow({
  folioId,
  suggestedAmount,
  currency,
  guest,
  onClose,
  onDone,
}: Omit<Props, 'open' | 'onOpenChange'> & { onClose: () => void }) {
  const { t } = useTranslation('finance')
  const ids = useId()
  const [amount, setAmount] = useState(toNumber(suggestedAmount) > 0 ? suggestedAmount : '')
  const [channels, setChannels] = useState<LinkChannel[]>([])
  const create = useFinanceMutation(() => createPaymentLink(folioId, amount, channels), { onSuccess: () => onDone?.() })

  if (create.data) return <LinkReady result={create.data} currency={currency} requested={channels} onClose={onClose} />

  function toggle(channel: LinkChannel, on: boolean) {
    setChannels((current) => (on ? [...current, channel] : current.filter((item) => item !== channel)))
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (toNumber(amount) > 0) create.mutate(undefined)
  }

  const destinations: { channel: LinkChannel; to: string; icon: typeof Mail }[] = [
    { channel: 'email', to: guest?.email ?? '', icon: Mail },
    { channel: 'whatsapp', to: guest?.phone ?? '', icon: MessageCircle },
  ]

  return (
    <form onSubmit={submit} className="grid gap-5" noValidate>
      <div className="grid gap-1.5">
        <Label htmlFor={`${ids}-amount`}>{t('link.amount')}</Label>
        <MoneyInput
          id={`${ids}-amount`}
          name="amount"
          value={amount}
          onChange={setAmount}
          currency={currency}
          className="[&_input]:h-11 [&_input]:text-lg [&_input]:font-semibold"
        />
      </div>
      <fieldset className="grid gap-2">
        <legend className="mb-1 text-[13px] font-semibold text-fg">{t('link.sendTitle')}</legend>
        {destinations.map(({ channel, to, icon: Icon }) => (
          <label
            key={channel}
            htmlFor={`${ids}-${channel}`}
            className="flex items-center gap-3 rounded-lg border border-border px-3 py-2.5 text-sm has-[button:disabled]:opacity-60"
          >
            <Checkbox
              id={`${ids}-${channel}`}
              name={`send_${channel}`}
              checked={channels.includes(channel)}
              disabled={!to}
              onCheckedChange={(value) => toggle(channel, value === true)}
            />
            <Icon aria-hidden className="size-4 text-muted" />
            <span className="min-w-0 truncate">
              {to ? t(`link.sendVia.${channel}`, { to }) : t(`link.missing.${channel}`)}
            </span>
          </label>
        ))}
      </fieldset>
      {create.isError && (
        <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
          {errorMessage(create.error, t)}
        </p>
      )}
      <DialogFooter>
        <Button variant="secondary" onClick={onClose} disabled={create.isPending}>
          {t('common:actions.cancel')}
        </Button>
        <Button type="submit" variant="primary" loading={create.isPending} disabled={toNumber(amount) <= 0}>
          <Link2 aria-hidden />
          {t('link.create')}
        </Button>
      </DialogFooter>
    </form>
  )
}

function LinkReady({
  result,
  currency,
  requested,
  onClose,
}: {
  result: PaymentLinkResult
  currency: string
  requested: LinkChannel[]
  onClose: () => void
}) {
  const { t, i18n } = useTranslation('finance')
  const ids = useId()
  const [copied, setCopied] = useState(false)
  const { intent } = result
  const lang = normalizeLang(i18n.language)

  async function copy() {
    try {
      await navigator.clipboard.writeText(result.checkout_url)
      setCopied(true)
    } catch {
      document.getElementById(`${ids}-url`)?.focus()
    }
  }

  return (
    <div className="grid gap-5">
      <div className="flex items-center gap-4 rounded-lg border border-border bg-surface-2 p-4">
        <div className="rounded-md bg-white p-2 shadow-xs">
          <QRCodeSVG value={result.checkout_url} size={112} marginSize={0} title={t('link.qrTitle')} />
        </div>
        <div className="min-w-0 text-sm">
          <p className="eyebrow">{t('link.ready')}</p>
          <p className="num mt-1 text-xl font-semibold">{moneyLabel(intent.amount, currency)}</p>
          <p className="mt-1 text-muted">{t('link.qrHint')}</p>
          {intent.expires_at && (
            <p className="mt-1 text-xs text-muted">
              {t('link.expires', { date: formatDate(intent.expires_at, lang === 'es' ? "d MMM, HH:mm" : 'MMM d, h:mm a', lang) })}
            </p>
          )}
        </div>
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor={`${ids}-url`}>{t('link.url')}</Label>
        <div className="flex gap-2">
          <Input id={`${ids}-url`} readOnly value={result.checkout_url} onFocus={(event) => event.target.select()} className="text-xs" />
          <Button variant="secondary" onClick={copy} aria-label={t('link.copy')}>
            {copied ? <Check aria-hidden /> : <Copy aria-hidden />}
            <span className="hidden sm:inline">{copied ? t('link.copied') : t('link.copyShort')}</span>
          </Button>
        </div>
      </div>
      {requested.length > 0 && (
        <ul className="grid gap-1.5 text-sm">
          {result.messages.map((message) => (
            <li key={`${message.channel}-${message.to}`} className="flex items-center gap-2">
              {message.status === 'failed' ? (
                <TriangleAlert aria-hidden className="size-4 text-danger" />
              ) : (
                <Check aria-hidden className="size-4 text-success" />
              )}
              {t(message.status === 'failed' ? 'link.sendFailed' : 'link.sent', { channel: t(`link.channel.${message.channel}`), to: message.to })}
            </li>
          ))}
          {result.messages.length === 0 && (
            <li className="flex items-start gap-2 text-muted">
              <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0 text-warning" />
              {result.send_error ? t('link.sendError') : t('link.notSent')}
            </li>
          )}
        </ul>
      )}
      <DialogFooter>
        <Button asChild variant="secondary">
          <a href={result.checkout_url} target="_blank" rel="noreferrer">
            <ExternalLink aria-hidden />
            {t('link.open')}
          </a>
        </Button>
        <Button variant="primary" onClick={onClose}>
          {t('link.done')}
        </Button>
      </DialogFooter>
    </div>
  )
}
