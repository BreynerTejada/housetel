import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { isApiError } from '@/lib/api'
import { formatDateRange, normalizeLang } from '@/lib/format'
import { portalKeys, useCheckin, type CheckinPayload, type CheckinStep } from '../api'
import { DocumentsStep } from '../components/checkin/DocumentsStep'
import { ArrivalStep, ClosedPanel, DoneStep, PaymentStep, SignatureStep } from '../components/checkin/FinalSteps'
import { GuestsStep } from '../components/checkin/GuestsStep'
import { StepProgress, StepTitle } from '../components/checkin/StepLayout'
import { InvalidLink } from '../components/portal/InvalidLink'
import { PortalFrame, PortalTopBar } from '../components/portal/PortalFrame'
import { resolveStep, stepsFor } from '../lib/checkin'
import { useReservationLanguage } from '../lib/language'

const EDITABLE: CheckinStep[] = ['guests', 'documents', 'arrival', 'signature']

/**
 * `/g/:token/checkin` — the online check-in stepper: Huéspedes → Documentos → Llegada → Firma y términos
 * → Pago → Listo. Every step is saved on the server, so the guest can stop and come back later (the stepper
 * reopens where it was left). Mobile first, one hand, in the hotel's colors.
 */
export default function CheckinPage() {
  const { token = '' } = useParams()
  const checkin = useCheckin(token)
  useReservationLanguage(checkin.data?.reservation.code, checkin.data?.reservation.language)

  if (checkin.isPending) return <CheckinSkeleton />
  if (checkin.isError) {
    return isApiError(checkin.error) && checkin.error.status === 404 ? (
      <InvalidLink />
    ) : (
      <PortalFrame className="items-center justify-center px-4">
        <ErrorState error={checkin.error} onRetry={() => checkin.refetch()} />
      </PortalFrame>
    )
  }
  return <Stepper checkin={checkin.data} token={token} />
}

function Stepper({ checkin, token }: { checkin: CheckinPayload; token: string }) {
  const { t, i18n } = useTranslation('guestportal')
  const lang = normalizeLang(i18n.language)
  const queryClient = useQueryClient()
  const [chosen, setChosen] = useState<CheckinStep | null>(null)
  const steps = stepsFor(checkin)
  const completed = checkin.status === 'completed'
  const step = chosen && steps.includes(chosen) && (completed ? !EDITABLE.includes(chosen) : true) ? chosen : resolveStep(checkin)
  // a booking cancelled after its check-in was done has nothing left to show but the closed notice
  const inactive = checkin.reservation.status === 'cancelled' || checkin.reservation.status === 'no_show'
  const closed = inactive || (!checkin.window.is_open && !completed)

  function go(next: CheckinStep) {
    setChosen(next)
    document.getElementById('checkin-top')?.scrollIntoView({ block: 'start' })
  }

  function update(payload: CheckinPayload) {
    queryClient.setQueryData(portalKeys.checkin(token), payload)
    void queryClient.invalidateQueries({ queryKey: portalKeys.portal(token) })
  }

  /** A step was saved: store the new state and move to the next visible step. */
  function saved(payload: CheckinPayload) {
    update(payload)
    const list = stepsFor(payload)
    const next = payload.status === 'completed' ? resolveStep(payload) : (list[list.indexOf(step) + 1] ?? resolveStep(payload))
    go(next)
  }

  const titles: Partial<Record<CheckinStep, string>> = {
    guests: t('checkin.guests.title'),
    documents: t('checkin.documents.title'),
    arrival: t('checkin.arrival.title'),
    signature: t('checkin.signature.title'),
    payment: t('checkin.payment.title'),
  }

  return (
    <PortalFrame property={checkin.property}>
      <PortalTopBar property={checkin.property}>
        <Link
          to={`/g/${encodeURIComponent(token)}`}
          aria-label={t('checkin.back')}
          className="-ml-2 grid size-9 shrink-0 place-items-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
        >
          <ArrowLeft aria-hidden className="size-5" />
        </Link>
      </PortalTopBar>
      <main id="checkin-top" className="mx-auto grid w-full max-w-2xl scroll-mt-20 gap-6 px-4 pt-6 pb-16 sm:px-6">
        <header className="grid gap-3">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
            <h1 className="text-lg font-extrabold tracking-[-0.02em]">{t('checkin.title')}</h1>
            <p className="num text-[13px] text-muted">
              {checkin.reservation.code} · {formatDateRange(checkin.reservation.checkin_date, checkin.reservation.checkout_date, lang)}
            </p>
          </div>
          {!closed && (
            <StepProgress
              steps={steps}
              current={step}
              reachable={(candidate) => !completed && EDITABLE.includes(candidate)}
              onSelect={go}
            />
          )}
        </header>

        {closed ? (
          <ClosedPanel checkin={checkin} token={token} />
        ) : (
          <>
            {titles[step] && <StepTitle>{titles[step]}</StepTitle>}
            {step === 'guests' && <GuestsStep key={checkin.status} checkin={checkin} token={token} onSaved={saved} />}
            {step === 'documents' && <DocumentsStep checkin={checkin} token={token} onUpdated={update} onSaved={saved} />}
            {step === 'arrival' && <ArrivalStep checkin={checkin} token={token} onSaved={saved} />}
            {step === 'signature' && <SignatureStep checkin={checkin} token={token} onSaved={saved} onGoTo={go} />}
            {step === 'payment' && <PaymentStep checkin={checkin} token={token} onSkip={() => go('done')} />}
            {step === 'done' && <DoneStep checkin={checkin} token={token} />}
          </>
        )}
      </main>
    </PortalFrame>
  )
}

function CheckinSkeleton() {
  const { t } = useTranslation('guestportal')
  return (
    <PortalFrame>
      <div role="status" aria-label={t('loading')} className="mx-auto grid w-full max-w-2xl gap-5 px-4 pt-20 sm:px-6">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-2 w-full" />
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-72 rounded-2xl" />
      </div>
    </PortalFrame>
  )
}
