import { useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, Check, DoorOpen } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { createPaymentLink, postCharge, recordPayment } from '@/features/finance/api'
import { useActiveProperty } from '@/lib/auth'
import { isApiError } from '@/lib/api'
import { errorMessage } from '@/lib/errors'
import {
  assignRoom,
  checkIn,
  createReservation,
  frontdeskKeys,
  getRoomOptions,
  getToday,
  useExtras,
  useGroup,
  useRefreshFrontDesk,
  useRoomOffers,
  useStaysQuote,
  type ReservationDetail,
} from '../api'
import { occupiedUnits, orderUnits } from '../lib/units'
import { StepOffers } from '../components/wizard/StepOffers'
import { StepDates } from '../components/wizard/StepDates'
import { StepExtras } from '../components/wizard/StepExtras'
import { StepGuest } from '../components/wizard/StepGuest'
import { StepPayment } from '../components/wizard/StepPayment'
import { WizardSteps, WizardSummary } from '../components/wizard/WizardParts'
import {
  buildReservationPayload,
  depositPercent,
  expandSelection,
  firstInvalidStep,
  initialWizardState,
  quoteInput,
  roomOffersQuery,
  suggestedAmount,
  validateStep,
  WIZARD_STEPS,
  type StepErrors,
  type WizardState,
  type WizardStep,
} from '../lib/wizard'

/**
 * `/app/reservations/new?checkin&checkout&room_id&room_type_id[&walk_in=1][&group=<id>[&block=<id>]]` (plan C1,
 * multi-room since pilot P3): the five-step wizard — dates & guests (and group) → rooms & rates (how many of
 * each offer, the guests of each room) → guest (GuestPicker) → extras & notes → guarantee & payment. With
 * `block` the rooms are picked up from that group allotment. Walk-in mode arrives today and checks every room
 * in as soon as the reservation exists. After creating it, the extras and the payment go to its folio; if one
 * of those fails the reservation is kept and the desk is told what is left.
 */
export default function NewReservationPage() {
  const { property } = useActiveProperty()
  // The wizard starts from the business date: wait until the active property is known.
  if (!property) return <LoadingState />
  return <Wizard bd={property.business_date} currency={property.currency || 'COP'} />
}

function Wizard({ bd, currency }: { bd: string; currency: string }) {
  const { t } = useTranslation('frontdesk')
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const refresh = useRefreshFrontDesk()
  const [state, setState] = useState<WizardState>(() => initialWizardState(searchParams, bd))
  const [step, setStep] = useState<WizardStep>(0)
  const [reached, setReached] = useState<WizardStep>(0)
  const [errors, setErrors] = useState<StepErrors>({})
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const offers = useRoomOffers(roomOffersQuery(state), step >= 1)
  const units = useMemo(() => expandSelection(state.selection, offers.data), [state.selection, offers.data])
  const quote = useStaysQuote(quoteInput(state, offers.data), step >= 1)
  const extras = useExtras(step >= 3)
  const group = useGroup(state.groupId)
  const groupLabel = state.groupId ? group.data?.name : state.groupMode && state.groupName.trim() ? state.groupName.trim() : undefined
  const block = state.blockId ? group.data?.blocks.find((item) => item.id === state.blockId) : undefined
  const suggested = suggestedAmount(quote.data?.stays, offers.data, currency)

  function update(patch: Partial<WizardState>) {
    setState((current) => ({ ...current, ...patch }))
    setErrors({})
  }

  function go(target: WizardStep) {
    setStep(target)
    setReached((current) => (target > current ? target : current))
    setErrors({})
    setSubmitError(null)
    window.requestAnimationFrame(() => headingRef.current?.focus())
  }

  function next() {
    const stepErrors = validateStep(step, state, bd, offers.data)
    if (Object.keys(stepErrors).length > 0) {
      setErrors(stepErrors)
      return
    }
    if (step < 4) go((step + 1) as WizardStep)
    else void submit()
  }

  /**
   * Walk-in: each stay without a room (a dorm booking has one per bed) goes into a clean, vacant unit of its
   * category — the bookings auto-assignment only looks at the housekeeping status, so it could pick a room
   * whose guest leaves today and has not checked out — and then checks in. Returns the error, if any.
   */
  async function checkInWalkIn(reservation: ReservationDetail): Promise<string | null> {
    let occupied = new Map<string, string>()
    try {
      const board = await queryClient.fetchQuery({ queryKey: frontdeskKeys.today(), queryFn: getToday })
      occupied = occupiedUnits(board.in_house)
    } catch {
      // Without the board the check-in still works: the backend picks a clean room.
    }
    for (const stay of reservation.stays) {
      try {
        if (!stay.room) {
          const best = orderUnits(null, await getRoomOptions(stay.id), occupied).find((unit) => unit.sameCategory && unit.ready)
          if (best) {
            await assignRoom(stay.id, { room_id: best.roomId, bed_id: best.bedId })
            occupied.set(best.key, reservation.booker.full_name)
          }
        }
        await checkIn(stay.id, false)
      } catch (error) {
        return errorMessage(error, t)
      }
    }
    return null
  }

  async function submit() {
    const invalid = firstInvalidStep(state, bd, offers.data)
    if (invalid !== null) {
      go(invalid)
      setErrors(validateStep(invalid, state, bd, offers.data))
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    let created
    try {
      created = await createReservation(buildReservationPayload(state, offers.data))
    } catch (error) {
      setSubmitting(false)
      setSubmitError(errorMessage(error, t))
      if (isApiError(error) && error.code === 'no_availability') {
        await offers.refetch()
        go(1)
        setSubmitError(errorMessage(error, t))
      }
      return
    }
    const pending: string[] = []
    const folioId = created.folio_id
    for (const [extraId, quantity] of Object.entries(state.extras)) {
      if (quantity <= 0 || !folioId) continue
      try {
        await postCharge(folioId, { extra_id: extraId, quantity })
      } catch (error) {
        pending.push(t('wizard.pending.extra', { reason: errorMessage(error, t) }))
      }
    }
    if (folioId && state.payment.mode === 'payment' && state.payment.method) {
      try {
        await recordPayment(folioId, { amount: state.payment.amount, method: state.payment.method, reference: state.payment.reference.trim(), notes: '' })
      } catch (error) {
        pending.push(t('wizard.pending.payment', { reason: errorMessage(error, t) }))
      }
    }
    if (folioId && state.payment.mode === 'link') {
      try {
        await createPaymentLink(folioId, state.payment.amount, state.payment.sendEmail ? ['email'] : [])
      } catch (error) {
        pending.push(t('wizard.pending.link', { reason: errorMessage(error, t) }))
      }
    }
    if (state.walkIn) {
      const failure = await checkInWalkIn(created)
      if (failure) pending.push(t('wizard.pending.checkIn', { reason: failure }))
    }
    await refresh()
    setSubmitting(false)
    toast.success(
      t(state.walkIn && pending.length === 0 ? 'wizard.createdAndIn' : 'wizard.created', { code: created.code }) +
        (created.stays.length > 1 ? ` · ${t('wizard.createdRooms', { count: created.stays.length })}` : ''),
    )
    for (const message of pending) toast.warning(message, { duration: 10_000 })
    navigate(`/app/reservations/${created.id}`)
  }

  const title = state.walkIn ? t('wizard.titleWalkIn') : t('pages.newReservation')
  const stepKey = WIZARD_STEPS[step]
  const last = step === 4

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        title={title}
        breadcrumbs={[{ label: t('nav.reservations'), to: '/app/reservations' }, { label: title }]}
        actions={
          <Button asChild variant="ghost">
            <Link to="/app/reservations">{t('common:actions.cancel')}</Link>
          </Button>
        }
      />
      <WizardSteps current={step} reached={reached} onPick={go} />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <section className="min-w-0 rounded-xl border border-border bg-surface shadow-xs">
          <header className="border-b border-border px-5 py-4">
            <p className="eyebrow">{t('wizard.stepOf', { step: step + 1, total: WIZARD_STEPS.length })}</p>
            <h2 ref={headingRef} tabIndex={-1} className="mt-0.5 text-lg font-bold outline-none">
              {t(`wizard.steps.${stepKey}`)}
            </h2>
          </header>
          <div className="px-5 py-5">
            {step === 0 && <StepDates state={state} update={update} errors={errors} bd={bd} groupLabel={group.data?.name} block={block} />}
            {step === 1 && <StepOffers state={state} update={update} errors={errors} offers={offers} lines={quote.data?.stays} />}
            {step === 2 && <StepGuest state={state} update={update} errors={errors} />}
            {step === 3 && <StepExtras state={state} update={update} errors={errors} currency={currency} />}
            {step === 4 && (
              <StepPayment
                state={state}
                update={update}
                errors={errors}
                currency={currency}
                suggested={suggested}
                deposit={depositPercent(units, offers.data)}
              />
            )}
            {submitError && (
              <p role="alert" className="mt-5 rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
                {submitError}
              </p>
            )}
          </div>
          <footer className="flex items-center justify-between gap-3 border-t border-border px-5 py-3">
            <Button variant="ghost" onClick={() => go((step - 1) as WizardStep)} disabled={step === 0 || submitting}>
              <ArrowLeft aria-hidden />
              {t('common:actions.back')}
            </Button>
            <Button variant="primary" onClick={next} loading={submitting}>
              {last ? (
                state.walkIn ? (
                  <>
                    <DoorOpen aria-hidden />
                    {t('wizard.createAndCheckIn')}
                  </>
                ) : (
                  <>
                    <Check aria-hidden />
                    {t('wizard.create')}
                  </>
                )
              ) : (
                <>
                  {t('common:actions.continue')}
                  <ArrowRight aria-hidden />
                </>
              )}
            </Button>
          </footer>
        </section>
        <WizardSummary
          state={state}
          units={units}
          offers={offers.data}
          quote={quote}
          extras={extras.data?.results ?? []}
          currency={currency}
          groupLabel={groupLabel}
          fromBlock={Boolean(state.blockId)}
        />
      </div>
    </div>
  )
}
