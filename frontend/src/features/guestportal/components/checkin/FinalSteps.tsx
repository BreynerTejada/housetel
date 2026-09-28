import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, CalendarClock } from 'lucide-react'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { isApiError } from '@/lib/api'
import { formatDate, normalizeLang } from '@/lib/format'
import {
  completeCheckin,
  payBalance,
  portalKeys,
  saveArrival,
  saveSignature,
  type CheckinPayload,
  type CheckinStep,
  type MissingItem,
} from '../../api'
import { portalError } from '../../lib/errors'
import { moneyLabel } from '../../lib/money'
import { goTo } from '../../lib/navigation'
import { tr } from '../../lib/text'
import { PayDialog } from '../portal/BalanceCard'
import { SignaturePad, type SignaturePadHandle } from './SignaturePad'
import { DoneStamp, StepActions, StepError } from './StepLayout'

/** Step 3 — estimated time of arrival (the front desk sees it on the booking). */
export function ArrivalStep({ checkin, token, onSaved }: { checkin: CheckinPayload; token: string; onSaved: (payload: CheckinPayload) => void }) {
  const { t } = useTranslation('guestportal')
  const [eta, setEta] = useState(checkin.eta ?? checkin.reservation.eta?.slice(0, 5) ?? '')
  const [unknown, setUnknown] = useState(false)
  const [tried, setTried] = useState(false)
  const save = useMutation({ mutationFn: () => saveArrival(token, unknown ? null : eta), onSuccess: onSaved })
  const checkInTime = checkin.property.check_in_time
  const missing = !unknown && !eta
  const early = !unknown && eta && checkInTime && eta < checkInTime

  return (
    <form
      noValidate
      className="grid gap-5"
      onSubmit={(event) => {
        event.preventDefault()
        setTried(true)
        if (!missing) save.mutate()
      }}
    >
      <p className="text-[15px] text-muted">
        {checkInTime ? t('checkin.arrival.lead', { time: checkInTime }) : t('checkin.arrival.leadNoTime')}
      </p>
      <div className="grid gap-4 rounded-2xl border border-border bg-surface p-4 shadow-xs sm:p-5">
        <div className="grid gap-1.5 sm:max-w-56">
          <Label htmlFor="checkin-eta">{t('checkin.arrival.eta')}</Label>
          <Input
            id="checkin-eta"
            name="eta"
            type="time"
            step={900}
            value={eta}
            disabled={unknown}
            onChange={(event) => setEta(event.target.value)}
            aria-invalid={tried && missing}
            aria-describedby={tried && missing ? 'checkin-eta-error' : undefined}
            className="h-11 text-[15px]"
          />
          {tried && missing && (
            <p id="checkin-eta-error" className="text-xs font-medium text-danger-ink">
              {t('checkin.arrival.required')}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2.5">
          <Checkbox id="checkin-eta-unknown" name="eta_unknown" checked={unknown} onCheckedChange={(value) => setUnknown(value === true)} />
          <Label htmlFor="checkin-eta-unknown" className="font-medium">
            {t('checkin.arrival.unknown')}
          </Label>
        </div>
        {early && <p className="rounded-lg bg-info-soft px-3 py-2 text-sm text-info-ink">{t('checkin.arrival.early', { time: checkInTime })}</p>}
      </div>
      {save.isError && <StepError message={portalError(save.error, t)} />}
      <StepActions>
        <Button type="submit" variant="primary" size="lg" className="w-full sm:w-auto" loading={save.isPending}>
          {t('checkin.saveContinue')}
        </Button>
      </StepActions>
    </form>
  )
}

function missingStep(items: MissingItem[]): CheckinStep | null {
  if (items.some((item) => item.code === 'guest_data')) return 'guests'
  if (items.some((item) => item.code === 'document')) return 'documents'
  return null
}

/** Step 4 — the hotel's terms, the signature and the data-processing consent (Ley 1581); completes the check-in. */
export function SignatureStep({
  checkin,
  token,
  onSaved,
  onGoTo,
}: {
  checkin: CheckinPayload
  token: string
  onSaved: (payload: CheckinPayload) => void
  onGoTo: (step: CheckinStep) => void
}) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const queryClient = useQueryClient()
  const padRef = useRef<SignaturePadHandle>(null)
  const [empty, setEmpty] = useState(true)
  const [accept, setAccept] = useState(false)
  const [marketing, setMarketing] = useState(false)
  const [tried, setTried] = useState(false)
  const signed = checkin.signature.signed
  const signatureMissing = checkin.settings.require_signature && !signed && empty
  const submit = useMutation({
    mutationFn: async () => {
      await saveSignature(token, {
        signature: empty ? '' : (padRef.current?.toDataURL() ?? ''),
        accept_terms: accept,
        marketing_consent: marketing,
      })
      return completeCheckin(token)
    },
    onSuccess: onSaved,
    onError: () => void queryClient.invalidateQueries({ queryKey: portalKeys.checkin(token) }),
  })
  const incomplete = isApiError(submit.error) && submit.error.code === 'checkin_incomplete' ? submit.error : null
  const goBack = incomplete ? missingStep((incomplete.data?.missing as MissingItem[] | undefined) ?? []) : null

  return (
    <form
      noValidate
      className="grid gap-5"
      onSubmit={(event) => {
        event.preventDefault()
        setTried(true)
        if (signatureMissing || !accept) return
        submit.mutate()
      }}
    >
      <p className="text-[15px] text-muted">{t('checkin.signature.lead')}</p>
      <div
        role="region"
        aria-label={t('checkin.signature.terms')}
        tabIndex={0}
        className="max-h-56 overflow-y-auto rounded-2xl border border-border bg-surface-2 p-4 text-[14px] leading-relaxed whitespace-pre-line focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
      >
        {tr(checkin.terms, lang)}
      </div>
      <div className="grid gap-2">
        <p className="text-sm font-bold">{t('checkin.signature.yours')}</p>
        {signed && <p className="text-[13px] text-muted">{t('checkin.signature.alreadySigned')}</p>}
        <SignaturePad ref={padRef} onChange={setEmpty} invalid={tried && signatureMissing} describedBy={tried && signatureMissing ? 'signature-error' : undefined} />
        {tried && signatureMissing && (
          <p id="signature-error" className="text-sm font-medium text-danger-ink">
            {t('checkin.signature.required')}
          </p>
        )}
      </div>
      <div className="grid gap-3">
        <div className="flex items-start gap-2.5">
          <Checkbox
            id="accept-terms"
            name="accept_terms"
            checked={accept}
            onCheckedChange={(value) => setAccept(value === true)}
            aria-invalid={tried && !accept}
            aria-describedby={tried && !accept ? 'accept-error' : undefined}
            className="mt-0.5"
          />
          <Label htmlFor="accept-terms" className="leading-5 font-medium">
            {t('checkin.signature.accept')}
          </Label>
        </div>
        {tried && !accept && (
          <p id="accept-error" className="text-sm font-medium text-danger-ink">
            {t('checkin.signature.acceptRequired')}
          </p>
        )}
        <div className="flex items-start gap-2.5">
          <Checkbox id="marketing" name="marketing_consent" checked={marketing} onCheckedChange={(value) => setMarketing(value === true)} className="mt-0.5" />
          <Label htmlFor="marketing" className="leading-5 font-medium text-muted">
            {t('checkin.signature.marketing')}
          </Label>
        </div>
      </div>
      {submit.isError && (
        <div className="grid gap-2">
          <StepError message={portalError(submit.error, t)} />
          {goBack && (
            <Button variant="secondary" className="justify-self-start" onClick={() => onGoTo(goBack)}>
              {t('checkin.goTo', { step: t(`checkin.steps.${goBack}`) })}
              <ArrowRight aria-hidden />
            </Button>
          )}
        </div>
      )}
      <StepActions>
        <Button type="submit" variant="primary" size="lg" className="w-full sm:w-auto" loading={submit.isPending}>
          {t('checkin.signature.submit')}
        </Button>
      </StepActions>
    </form>
  )
}

/** Step 5 — pay the balance now (gateway) or at the hotel. */
export function PaymentStep({ checkin, token, onSkip }: { checkin: CheckinPayload; token: string; onSkip: () => void }) {
  const { t } = useTranslation('guestportal')
  const [other, setOther] = useState(false)
  const { balance } = checkin
  const pay = useMutation({ mutationFn: () => payBalance(token), onSuccess: (link) => goTo(link.checkout_url) })

  return (
    <div className="grid gap-5">
      <p className="text-[15px] text-muted">{t('checkin.payment.lead')}</p>
      <div className="rounded-2xl border border-border bg-surface p-5 shadow-xs">
        <p className="eyebrow">{t('balance.due')}</p>
        <p className="num mt-1 text-[36px] leading-10 font-bold tracking-[-0.035em]">
          <MoneyText value={balance.due} currency={balance.currency} />
        </p>
        <button type="button" onClick={() => setOther(true)} className="mt-2 text-sm font-semibold text-accent-ink underline-offset-4 hover:underline">
          {t('checkin.payment.other')}
        </button>
      </div>
      {pay.isError && <StepError message={portalError(pay.error, t)} />}
      <StepActions>
        <Button variant="ghost" size="lg" onClick={onSkip}>
          {t('checkin.payment.later')}
        </Button>
        <Button variant="primary" size="lg" className="w-full sm:w-auto" loading={pay.isPending} onClick={() => pay.mutate()}>
          {t('checkin.payment.pay', { amount: moneyLabel(balance.due, balance.currency) })}
        </Button>
      </StepActions>
      <PayDialog open={other} onOpenChange={setOther} balance={balance} token={token} />
    </div>
  )
}

/** Step 6 — done: what happens at the front desk. */
export function DoneStep({ checkin, token }: { checkin: CheckinPayload; token: string }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const { reservation } = checkin
  const eta = checkin.eta ?? reservation.eta?.slice(0, 5)

  return (
    <div className="grid justify-items-center gap-3 rounded-2xl border border-border bg-surface px-5 py-8 text-center shadow-xs">
      <DoneStamp />
      <h2 className="mt-2 text-[26px] leading-8 font-extrabold tracking-[-0.03em]">{t('checkin.done.title')}</h2>
      <p className="text-[15px]">{t('checkin.done.lead', { date: formatDate(reservation.checkin_date, lang === 'en' ? 'EEEE, MMMM d' : "EEEE d 'de' MMMM", lang) })}</p>
      <p className="max-w-sm text-sm text-muted">{t('checkin.done.frontDesk', { code: reservation.code })}</p>
      {eta && <p className="text-sm font-semibold">{t('checkin.done.eta', { eta })}</p>}
      <Button asChild variant="primary" size="lg" className="mt-3">
        <Link to={`/g/${encodeURIComponent(token)}`}>{t('checkin.done.back')}</Link>
      </Button>
    </div>
  )
}

/** The online check-in is not available (not open yet, booking not confirmed, already checked in…). */
export function ClosedPanel({ checkin, token }: { checkin: CheckinPayload; token: string }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const reason = checkin.window.reason ?? 'past'
  return (
    <div className="grid justify-items-center gap-2 rounded-2xl border border-border bg-surface px-5 py-8 text-center">
      <CalendarClock aria-hidden className="size-7 text-muted" />
      <h2 className="text-xl font-bold">{t('checkin.closed.title')}</h2>
      <p className="max-w-sm text-sm text-muted">
        {t(`checkin.closed.${reason}`, { date: formatDate(checkin.window.opens_on, lang === 'en' ? 'MMMM d' : "d 'de' MMMM", lang) })}
      </p>
      <Button asChild variant="secondary" className="mt-3">
        <Link to={`/g/${encodeURIComponent(token)}`}>{t('checkin.done.back')}</Link>
      </Button>
    </div>
  )
}
