import { useMutation, useQueryClient } from '@tanstack/react-query'
import { CircleAlert, SquareArrowOutUpRight } from 'lucide-react'
import { RadioGroup as RadioGroupPrimitive } from 'radix-ui'
import { useCallback, useId, useMemo, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router'
import { DateRangePicker } from '@/components/DatePicker'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { isExistingGuest, type GuestPickerValue } from '@/features/guests/api'
import { GuestPicker } from '@/features/guests/components/GuestPicker'
import { errorMessage } from '@/lib/errors'
import { formatDateRange, formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { calendarKeys, createReservation, useOffers, type CalRoomType, type CreateReservationBody, type Offer } from '../api'
import { SCROLL_DIALOG } from '../lib/constants'
import { diffDays } from '../lib/dates'
import { checkCreate, type MoveTarget, type PlanContext } from '../lib/dnd'
import { invalidText, pick, targetLabel, type RoomIndex } from '../lib/labels'
import { calendarToast } from '../lib/toast'
import { Stepper } from './Stepper'

/** Guests a quick booking can take in one go (bigger groups go through the wizard). */
const MAX_GUESTS = 12

export interface CreateDialogProps {
  /** The days drawn on the grid and the row's place (room, bed, dorm room or a category's unassigned row). */
  draft: MoveTarget | null
  ctx: PlanContext
  index: RoomIndex
  roomTypes: readonly CalRoomType[]
  businessDate: string
  onClose: () => void
}

/**
 * Quick booking from the grid: the place and nights that were drawn, the guest (search or create), how
 * many people, and the sellable rates of that category for those nights. Anything more (extras, payment,
 * several rooms) goes through the reservation wizard, opened with the same data.
 */
export function CreateDialog({ draft, ...props }: CreateDialogProps) {
  return (
    <Dialog open={draft !== null} onOpenChange={(open) => !open && props.onClose()}>
      <DialogContent className={cn(SCROLL_DIALOG.content, 'sm:max-w-xl')}>
        {draft && <CreateBody key={`${draft.roomTypeId}:${draft.roomId}:${draft.bedId}:${draft.checkin}:${draft.checkout}`} draft={draft} {...props} />}
      </DialogContent>
    </Dialog>
  )
}

function CreateBody({ draft, ctx, index, roomTypes, businessDate, onClose }: Omit<CreateDialogProps, 'draft'> & { draft: MoveTarget }) {
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const id = useId()

  const roomType = roomTypes.find((candidate) => candidate.id === draft.roomTypeId)
  const isDorm = roomType?.kind === 'dorm'
  const oneBed = draft.bedId !== null
  const [range, setRange] = useState({ from: draft.checkin, to: draft.checkout })
  const [adults, setAdults] = useState(isDorm ? 1 : 2)
  const [children, setChildren] = useState(0)
  const [planId, setPlanId] = useState<string | null>(null)
  const [guest, setGuest] = useState<GuestPickerValue | null>(null)
  const [notes, setNotes] = useState('')
  const [tried, setTried] = useState(false)

  const nights = Math.max(0, diffDays(range.from, range.to))
  // A bed takes one guest; a dorm room or a dorm category takes one bed per guest.
  const units = isDorm && !oneBed ? adults + children : 1
  const target: MoveTarget = { ...draft, checkin: range.from, checkout: range.to }
  const check = checkCreate(target, ctx, units)
  const offersQuery = useOffers({ checkin: range.from, checkout: range.to, adults, children })
  const offers = useMemo(() => (offersQuery.data ?? []).filter((offer) => offer.room_type_id === draft.roomTypeId), [offersQuery.data, draft.roomTypeId])
  // Until someone picks one: the cheapest rate that can still be cancelled (a desk booking made in a hurry
  // should not land on a non-refundable rate by default), else the cheapest.
  const offer =
    offers.find((candidate) => candidate.rate_plan_id === planId) ??
    offers.find((candidate) => !candidate.rate_plan.cancellation_policy?.non_refundable) ??
    offers[0] ??
    null
  const category = pick(roomType?.name, lang)
  const place = targetLabel(t, lang, index, draft)

  const mutation = useMutation({
    mutationFn: (body: CreateReservationBody) => createReservation(body),
    onSuccess: (detail) => {
      void queryClient.invalidateQueries({ queryKey: calendarKeys.all })
      calendarToast.success(t('toast.created', { code: detail.code }), {
        action: { label: t('toast.view'), onClick: () => navigate(`/app/reservations/${detail.id}`) },
      })
      onClose()
    },
  })

  const wizardParams = new URLSearchParams({ checkin: range.from, checkout: range.to, adults: String(adults), room_type_id: draft.roomTypeId })
  if (draft.roomId && !isDorm) wizardParams.set('room_id', draft.roomId)
  const wizardPath = `/app/reservations/new?${wizardParams.toString()}`

  function submit(event: FormEvent) {
    event.preventDefault()
    setTried(true)
    if (!guest) {
      // The field may have scrolled away (a phone): bring it back, label included, with the focus.
      document.querySelector(`label[for="${id}-guest"]`)?.scrollIntoView({ block: 'nearest' })
      document.getElementById(`${id}-guest`)?.focus({ preventScroll: true })
      return
    }
    if (!offer || check.kind === 'invalid' || mutation.isPending) return
    mutation.mutate({
      ...(isExistingGuest(guest) ? { booker_id: guest.id } : { booker: guest }),
      stays: [
        {
          room_type_id: draft.roomTypeId,
          rate_plan_id: offer.rate_plan_id,
          checkin: range.from,
          checkout: range.to,
          adults,
          children,
          room_id: draft.roomId,
          bed_id: draft.bedId,
        },
      ],
      source: 'front_desk',
      status: 'confirmed',
      ...(notes.trim() ? { notes: notes.trim() } : {}),
    })
  }

  const guestError = tried && !guest
  // The server's refusal shows at the end of the form: scroll it into view when it appears.
  const revealAlert = useCallback((element: HTMLElement | null) => element?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }), [])
  const rateError = tried && !offer && !offersQuery.isPending

  return (
    <form onSubmit={submit} noValidate className="contents">
      <DialogHeader className={SCROLL_DIALOG.header}>
        <p className="flex items-center gap-2 text-xs font-bold text-muted">
          <span aria-hidden className="h-3.5 w-1 rounded-full" style={{ background: roomType?.color ?? 'var(--accent)' }} />
          <span className="truncate">
            {place}
            {draft.roomId ? ` · ${category}` : ''}
          </span>
        </p>
        <DialogTitle>{t('create.title')}</DialogTitle>
        <DialogDescription className="num">
          {formatDateRange(range.from, range.to, lang)} · {t('date.nights', { ns: 'common', count: nights })}
        </DialogDescription>
      </DialogHeader>

      {/* The form scrolls between a fixed header and footer: the buttons stay in reach on a phone. */}
      <div className={SCROLL_DIALOG.body}>
        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-guest`}>{t('create.guest')}</Label>
          <GuestPicker
            id={`${id}-guest`}
            value={guest}
            onChange={setGuest}
            autoFocus
            aria-invalid={guestError || undefined}
            aria-describedby={guestError ? `${id}-guest-error` : undefined}
          />
          {guestError && (
            <p id={`${id}-guest-error`} className="text-xs font-semibold text-danger-ink">
              {t('create.guestRequired')}
            </p>
          )}
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-[minmax(0,1fr)_7.5rem_7.5rem]">
          <div className="col-span-2 grid gap-1.5 sm:col-span-1">
            <Label htmlFor={`${id}-dates`}>{t('create.dates')}</Label>
            <DateRangePicker
              id={`${id}-dates`}
              value={range}
              onChange={(value) => value && setRange(value)}
              today={businessDate}
              min={businessDate}
              minNights={1}
              showNights
            />
          </div>
          <Stepper id={`${id}-adults`} label={t('create.adults')} value={adults} min={1} max={oneBed ? 1 : MAX_GUESTS} disabled={oneBed} onChange={setAdults} />
          <Stepper
            id={`${id}-children`}
            label={t('create.children')}
            value={children}
            min={0}
            max={oneBed ? 0 : MAX_GUESTS - adults}
            disabled={oneBed}
            onChange={setChildren}
          />
          {oneBed && <p className="col-span-2 text-xs text-muted sm:col-span-3">{t('create.oneGuestPerBed')}</p>}
        </div>

        {check.kind === 'invalid' && (
          <p role="alert" className="flex items-start gap-2 rounded-lg bg-danger-soft/70 px-3.5 py-2.5 text-[13px] text-danger-ink">
            <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            {check.reason === 'occupied' || check.reason === 'blocked' ? `${place}: ${invalidText(t, check, lang)}` : invalidText(t, check, lang)}
          </p>
        )}

        <div className="grid gap-1.5">
          <p id={`${id}-rate`} className="text-[13px] leading-5 font-semibold text-fg">
            {t('create.rate')}
          </p>
          {offersQuery.isPending ? (
            <div role="status" className="grid gap-2">
              <span className="sr-only">{t('create.loadingRates')}</span>
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : offersQuery.isError ? (
            <p role="alert" className="text-[13px] text-danger-ink">
              {errorMessage(offersQuery.error, t)}
            </p>
          ) : offers.length === 0 ? (
            <p className={cn('rounded-lg border border-dashed border-border-strong px-3.5 py-3 text-[13px] text-muted', rateError && 'border-danger/50 text-danger-ink')}>
              {t('create.noRates', { category })}
            </p>
          ) : (
            <RadioGroupPrimitive.Root
              value={offer?.rate_plan_id ?? ''}
              onValueChange={setPlanId}
              aria-labelledby={`${id}-rate`}
              className={cn('grid gap-2', offersQuery.isFetching && 'opacity-60')}
            >
              {offers.map((candidate) => (
                <RateOption key={candidate.rate_plan_id} offer={candidate} nights={nights} selected={candidate.rate_plan_id === offer?.rate_plan_id} />
              ))}
            </RadioGroupPrimitive.Root>
          )}
        </div>

        <div className="grid gap-1.5">
          <Label htmlFor={`${id}-notes`}>{t('create.notes')}</Label>
          <Textarea id={`${id}-notes`} value={notes} onChange={(event) => setNotes(event.target.value)} rows={2} />
        </div>

        {mutation.isError && (
          <p ref={revealAlert} role="alert" className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-soft/60 px-3.5 py-2.5 text-[13px] text-danger-ink">
            <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            {errorMessage(mutation.error, t)}
          </p>
        )}

        {/* On a phone the link lives here, at the end of the form (the footer keeps its buttons in one row). */}
        <Button asChild variant="link" size="sm" className="justify-self-start sm:hidden">
          <Link to={wizardPath} onClick={onClose}>
            {t('create.wizard')}
            <SquareArrowOutUpRight aria-hidden className="size-3.5" />
          </Link>
        </Button>
      </div>

      <DialogFooter className={SCROLL_DIALOG.footer}>
        <Button asChild variant="link" size="sm" className="mr-auto hidden sm:inline-flex">
          <Link to={wizardPath} onClick={onClose}>
            {t('create.wizard')}
            <SquareArrowOutUpRight aria-hidden className="size-3.5" />
          </Link>
        </Button>
        <Button onClick={onClose}>{t('actions.cancel', { ns: 'common' })}</Button>
        <Button type="submit" variant="primary" loading={mutation.isPending} disabled={check.kind === 'invalid'}>
          {t('create.submit')}
        </Button>
      </DialogFooter>
    </form>
  )
}

/** A sellable rate of the category for those nights: plan, meal plan, total and the average per night. */
function RateOption({ offer, nights, selected }: { offer: Offer; nights: number; selected: boolean }) {
  const { t, i18n } = useTranslation('calendar')
  const lang = normalizeLang(i18n.language)
  const total = Number(offer.total)
  const perNight = nights > 0 ? total / nights : total
  const deposit = Number(offer.rate_plan.deposit_percent)
  const name = pick(offer.rate_plan.name, lang)
  // Facts the plan's own name already says ("No reembolsable", "Con desayuno") are not repeated.
  const repeats = (fact: string) => name.toLocaleLowerCase(lang).includes(fact.toLocaleLowerCase(lang))
  const facts = [
    t(`create.meals.${offer.rate_plan.meal_plan}`, { defaultValue: offer.rate_plan.meal_plan }),
    offer.rate_plan.cancellation_policy?.non_refundable ? t('create.nonRefundable') : null,
    offer.units_needed > 1 ? t('create.beds', { count: offer.units_needed }) : null,
    deposit > 0 ? t('create.deposit', { percent: deposit }) : null,
  ].filter((fact): fact is string => Boolean(fact) && !repeats(fact as string))
  return (
    <RadioGroupPrimitive.Item
      value={offer.rate_plan_id}
      className={cn(
        'flex items-center gap-3 rounded-lg border px-3.5 py-2.5 text-left transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55',
        selected ? 'border-accent/60 bg-accent-soft/50' : 'border-border hover:border-border-strong',
      )}
    >
      <span
        aria-hidden
        className={cn('grid size-4 shrink-0 place-items-center rounded-full border', selected ? 'border-accent' : 'border-border-strong')}
      >
        {selected && <span className="size-2 rounded-full bg-accent" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-semibold text-fg">{name}</span>
        {facts.length > 0 && <span className="block truncate text-xs text-muted">{facts.join(' · ')}</span>}
      </span>
      <span className="shrink-0 text-right">
        <span className="num block text-[14px] font-bold text-fg">{formatMoney(offer.total, offer.quote.currency)}</span>
        <span className="num block text-2xs text-muted">{t('create.perNight', { amount: formatMoney(perNight, offer.quote.currency) })}</span>
      </span>
    </RadioGroupPrimitive.Item>
  )
}
