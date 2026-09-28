import type { TFunction } from 'i18next'
import { BedDouble, CircleAlert, Minus, Plus, RotateCcw, Users } from 'lucide-react'
import { useId } from 'react'
import { useTranslation } from 'react-i18next'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { PolicySnapshot, RoomOffer, StayQuoteLine } from '../../api'
import { guestsLabel, tr } from '../../lib/labels'
import {
  capacityOf,
  expandSelection,
  matchingLine,
  offerKey,
  roomSplit,
  selectedByRoomType,
  type RoomSplit,
  type RoomUnit,
  type StepErrors,
  type WizardState,
} from '../../lib/wizard'
import { FieldError } from './FieldError'

/** Offers of one room type, in the order the API ranks them. */
function groupByRoomType(offers: RoomOffer[], first: string | null) {
  const groups = new Map<string, { roomType: RoomOffer['room_type']; available: number; offers: RoomOffer[] }>()
  for (const offer of offers) {
    const group = groups.get(offer.room_type_id) ?? { roomType: offer.room_type, available: offer.available_units, offers: [] }
    group.offers.push(offer)
    groups.set(offer.room_type_id, group)
  }
  const list = [...groups.values()]
  return first ? [...list.filter((g) => g.roomType.id === first), ...list.filter((g) => g.roomType.id !== first)] : list
}

/**
 * Step 2 — rooms and rates (pilot P3): how many rooms of each offer, mixing categories (a dorm counts beds,
 * one guest each), and how the party sleeps in them. Prices are per room at its standard occupancy; the
 * summary re-prices every room with its real guests.
 */
export function StepOffers({
  state,
  update,
  errors,
  offers,
  lines,
}: {
  state: WizardState
  update: (patch: Partial<WizardState>) => void
  errors: StepErrors
  offers: { data?: RoomOffer[]; isError: boolean; error: unknown; refetch: () => unknown }
  /** Exact price of each room (quote), in the order of the rooms. */
  lines?: StayQuoteLine[]
}) {
  const { t, i18n } = useTranslation('frontdesk')

  if (offers.isError) return <ErrorState error={offers.error} onRetry={() => offers.refetch()} />
  if (!offers.data) return <LoadingState variant="rows" rows={3} />
  if (offers.data.length === 0) {
    return <EmptyState icon={BedDouble} title={t('wizard.noOffers')} description={t('wizard.noOffersHint')} />
  }
  const data = offers.data
  const promoRejected = state.promoCode.trim() !== '' && data.every((offer) => offer.quote.violations.includes('promo_invalid'))
  const groups = groupByRoomType(data, state.roomTypeId)
  const byType = selectedByRoomType(state.selection)
  const units = expandSelection(state.selection, data)

  function setQuantity(offer: RoomOffer, quantity: number) {
    const key = offerKey(offer.room_type_id, offer.rate_plan_id)
    const selection = { ...state.selection, [key]: quantity }
    if (quantity <= 0) delete selection[key]
    update({ selection, split: null })
  }

  return (
    <div className="grid gap-6">
      <PartyMeter state={state} units={units} />
      {promoRejected && (
        <p className="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">
          <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          {t('wizard.promoRejected', { code: state.promoCode.trim().toUpperCase() })}
        </p>
      )}
      {groups.map(({ roomType, available, offers: plans }) => {
        const picked = byType.get(roomType.id) ?? 0
        const dorm = roomType.kind === 'dorm'
        return (
          <section key={roomType.id} className="grid gap-2" aria-label={tr(roomType.name, i18n.language)}>
            <header className="flex flex-wrap items-center justify-between gap-2">
              <p className="flex items-center gap-2 font-semibold text-fg">
                <span aria-hidden className="size-3 rounded-[4px] ring-1 ring-black/5" style={{ backgroundColor: roomType.color }} />
                {tr(roomType.name, i18n.language)}
                {state.roomTypeId === roomType.id && state.roomId && <Badge tone="accent">{t('wizard.pickedRoom')}</Badge>}
              </p>
              <p className="flex items-center gap-3 text-[13px] text-muted">
                {!dorm && (
                  <span className="inline-flex items-center gap-1">
                    <Users aria-hidden className="size-3.5" />
                    {t('wizard.upTo', { count: roomType.max_occupancy })}
                  </span>
                )}
                <span className={cn(picked >= available && 'font-semibold text-warning-ink')}>
                  {t(dorm ? 'wizard.bedsLeft' : 'wizard.roomsLeft', { count: Math.max(0, available - picked) })}
                </span>
              </p>
            </header>
            <ul className="grid gap-2">
              {plans.map((offer) => {
                const key = offerKey(offer.room_type_id, offer.rate_plan_id)
                const quantity = state.selection[key] ?? 0
                const nights = offer.quote.nights.length || 1
                return (
                  <li
                    key={key}
                    className={cn(
                      'flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border bg-surface px-4 py-3 transition-colors',
                      quantity > 0 && 'border-accent bg-accent-soft/40',
                    )}
                  >
                    <div className="min-w-0 flex-1 basis-48">
                      <p className="font-semibold text-fg">{tr(offer.rate_plan.name, i18n.language)}</p>
                      <p className="mt-0.5 flex flex-wrap gap-x-2 text-[13px] text-muted">
                        <span>{t(`mealPlans.${offer.rate_plan.meal_plan}`, { defaultValue: offer.rate_plan.meal_plan })}</span>
                        <span aria-hidden>·</span>
                        <span>{policySummary(offer.rate_plan.cancellation_policy, t)}</span>
                      </p>
                    </div>
                    <div className="text-right">
                      <MoneyText value={offer.total} currency={offer.quote.currency} className="block text-[15px] font-bold text-fg" />
                      <span className="num block text-xs text-muted">
                        {dorm
                          ? t('wizard.perBed')
                          : t('wizard.perRoomFor', { guests: guestsLabel(t, offer.quote.adults, 0) })}
                        {' · '}
                        <MoneyText value={Math.round(Number(offer.total) / nights)} currency={offer.quote.currency} /> {t('wizard.perNight')}
                      </span>
                      {offer.quote.taxes.some((tax) => tax.exempt) && <span className="block text-xs text-success-ink">{t('wizard.taxExempt')}</span>}
                    </div>
                    <QuantityStepper
                      value={quantity}
                      max={quantity + Math.max(0, available - picked)}
                      onChange={(value) => setQuantity(offer, value)}
                      label={t(dorm ? 'wizard.bedsOf' : 'wizard.roomsOf', {
                        plan: tr(offer.rate_plan.name, i18n.language),
                        type: tr(roomType.name, i18n.language),
                      })}
                    />
                  </li>
                )
              })}
            </ul>
          </section>
        )
      })}
      <FieldError error={errors.offer} />
      {units.length > 0 && <SplitEditor state={state} update={update} units={units} offers={data} lines={lines} error={errors.split} />}
    </div>
  )
}

/** Whole-number stepper for the rooms of one offer. */
function QuantityStepper({ value, max, onChange, label }: { value: number; max: number; onChange: (value: number) => void; label: string }) {
  const { t } = useTranslation('frontdesk')
  return (
    <div role="group" aria-label={label} className="ml-auto flex items-center gap-1.5">
      <Button variant="secondary" size="icon-sm" aria-label={t('wizard.removeRoom')} disabled={value <= 0} onClick={() => onChange(value - 1)}>
        <Minus aria-hidden />
      </Button>
      <output aria-live="polite" className={cn('num w-7 text-center text-[15px] font-bold', value > 0 ? 'text-accent-ink' : 'text-muted')}>
        {value}
      </output>
      <Button
        variant={value > 0 || value >= max ? 'secondary' : 'primary'}
        size="icon-sm"
        aria-label={t('wizard.addRoom')}
        disabled={value >= max}
        onClick={() => onChange(value + 1)}
      >
        <Plus aria-hidden />
      </Button>
    </div>
  )
}

/** Who is being booked vs what the picked rooms hold: a slim bar that fills as rooms are added. */
function PartyMeter({ state, units }: { state: WizardState; units: RoomUnit[] }) {
  const { t } = useTranslation('frontdesk')
  const persons = state.adults + state.children
  const capacity = capacityOf(units)
  const fits = units.length > 0 && capacity >= persons
  const ratio = persons > 0 ? Math.min(1, capacity / persons) : 0
  return (
    <div className="grid gap-2 rounded-lg border border-border bg-surface-2/60 px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-[13px]">
        <p className="font-semibold text-fg">
          {guestsLabel(t, state.adults, state.children)}
          <span className="font-normal text-muted">
            {' · '}
            {t(units.length > 0 && units.every((unit) => unit.kind === 'dorm') ? 'wizard.bedsPicked' : 'wizard.roomsPicked', { count: units.length })}
          </span>
        </p>
        <p className={cn('font-semibold', units.length === 0 ? 'text-muted' : fits ? 'text-success-ink' : 'text-warning-ink')}>
          {units.length === 0
            ? t('wizard.pickRooms')
            : fits
              ? t('wizard.capacityOk', { count: capacity })
              : t('wizard.capacityShort', { count: persons - capacity })}
        </p>
      </div>
      <div
        role="meter"
        aria-label={t('wizard.capacityMeter')}
        aria-valuemin={0}
        aria-valuemax={persons}
        aria-valuenow={Math.min(capacity, persons)}
        className="h-1.5 overflow-hidden rounded-full bg-surface-3"
      >
        <div className={cn('h-full rounded-full transition-[width] motion-reduce:transition-none', fits ? 'bg-success' : 'bg-accent')} style={{ width: `${ratio * 100}%` }} />
      </div>
    </div>
  )
}

/** How the party sleeps: guests per room (bed), automatic until the desk changes a room. */
function SplitEditor({
  state,
  update,
  units,
  offers,
  lines,
  error,
}: {
  state: WizardState
  update: (patch: Partial<WizardState>) => void
  units: RoomUnit[]
  offers: RoomOffer[]
  lines?: StayQuoteLine[]
  error?: string
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const titleId = useId()
  const { split, auto } = roomSplit(state, units)
  const placedAdults = split.reduce((sum, room) => sum + room.adults, 0)
  const placedChildren = split.reduce((sum, room) => sum + room.children, 0)

  function change(index: number, patch: Partial<RoomSplit>) {
    const next = split.map((room, position) => (position === index ? { ...room, ...patch } : { ...room }))
    update({ split: next })
  }

  return (
    <section aria-labelledby={titleId} className="grid gap-3 border-t border-border pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 id={titleId} className="font-semibold text-fg">
            {t('wizard.split.title')}
          </h3>
          <p className="text-[13px] text-muted">{auto ? t('wizard.split.auto') : t('wizard.split.manual')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[13px]">
          <Badge tone={placedAdults === state.adults ? 'success' : 'warning'}>
            {t('wizard.split.adultsPlaced', { done: placedAdults, total: state.adults })}
          </Badge>
          {state.children > 0 && (
            <Badge tone={placedChildren === state.children ? 'success' : 'warning'}>
              {t('wizard.split.childrenPlaced', { done: placedChildren, total: state.children })}
            </Badge>
          )}
          {!auto && (
            <Button size="sm" variant="ghost" onClick={() => update({ split: null })}>
              <RotateCcw aria-hidden />
              {t('wizard.split.reset')}
            </Button>
          )}
        </div>
      </div>
      <ol className="grid gap-2">
        {units.map((unit, index) => {
          const offer = offers.find((item) => offerKey(item.room_type_id, item.rate_plan_id) === unit.offerKey)
          const room = split[index]!
          const line = matchingLine(lines, index, unit, room)
          const name = offer ? tr(offer.room_type.name, i18n.language) : ''
          const plan = offer ? tr(offer.rate_plan.name, i18n.language) : ''
          return (
            <li key={unit.key} className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border border-border px-3 py-2.5">
              <span aria-hidden className="num grid size-7 shrink-0 place-items-center rounded-md border border-border-strong bg-surface-2 text-xs font-bold text-muted">
                {index + 1}
              </span>
              <div className="min-w-0 flex-1 basis-40">
                <p className="truncate text-[13px] font-semibold text-fg">
                  {unit.kind === 'dorm' ? t('wizard.split.bed', { number: index + 1, type: name }) : t('wizard.split.room', { number: index + 1, type: name })}
                </p>
                <p className="truncate text-xs text-muted">{plan}</p>
              </div>
              {unit.kind === 'dorm' ? (
                unit.maxChildren > 0 ? (
                  <div role="radiogroup" aria-label={t('wizard.split.bedGuest', { number: index + 1 })} className="flex gap-1">
                    {(['adult', 'child'] as const).map((kind) => {
                      const checked = kind === 'adult' ? room.adults === 1 : room.children === 1
                      return (
                        <button
                          key={kind}
                          type="button"
                          role="radio"
                          aria-checked={checked}
                          onClick={() => change(index, kind === 'adult' ? { adults: 1, children: 0 } : { adults: 0, children: 1 })}
                          className={cn(
                            'rounded-md border px-2.5 py-1 text-xs font-semibold transition-colors',
                            checked ? 'border-accent bg-accent-soft/60 text-accent-ink' : 'border-border text-muted hover:border-border-strong',
                          )}
                        >
                          {t(`wizard.split.${kind}`)}
                        </button>
                      )
                    })}
                  </div>
                ) : (
                  <span className="text-xs text-muted">{t('wizard.split.oneAdult')}</span>
                )
              ) : (
                <div className="flex flex-wrap items-center gap-3">
                  <MiniCounter
                    label={t('wizard.adults')}
                    value={room.adults}
                    min={1}
                    max={unit.maxAdults}
                    onChange={(adults) => change(index, { adults })}
                    groupLabel={t('wizard.split.adultsIn', { number: index + 1 })}
                  />
                  {unit.maxChildren > 0 && (
                    <MiniCounter
                      label={t('wizard.children')}
                      value={room.children}
                      min={0}
                      max={unit.maxChildren}
                      onChange={(children) => change(index, { children })}
                      groupLabel={t('wizard.split.childrenIn', { number: index + 1 })}
                    />
                  )}
                </div>
              )}
              <span className="ml-auto min-w-24 text-right text-[13px]">
                {line ? <MoneyText value={line.total} currency={offer?.quote.currency} className="font-semibold text-fg" /> : <span className="text-muted">—</span>}
              </span>
            </li>
          )
        })}
      </ol>
      <FieldError error={error} />
    </section>
  )
}

function MiniCounter({
  label,
  value,
  min,
  max,
  onChange,
  groupLabel,
}: {
  label: string
  value: number
  min: number
  max: number
  onChange: (value: number) => void
  groupLabel: string
}) {
  const { t } = useTranslation('frontdesk')
  return (
    <div role="group" aria-label={groupLabel} className="flex items-center gap-1.5">
      <span className="text-xs text-muted">{label}</span>
      <Button variant="ghost" size="icon-sm" aria-label={t('wizard.split.less', { what: label })} disabled={value <= min} onClick={() => onChange(value - 1)}>
        <Minus aria-hidden />
      </Button>
      <output aria-live="polite" className="num w-5 text-center text-[13px] font-bold text-fg">
        {value}
      </output>
      <Button variant="ghost" size="icon-sm" aria-label={t('wizard.split.more', { what: label })} disabled={value >= max} onClick={() => onChange(value + 1)}>
        <Plus aria-hidden />
      </Button>
    </div>
  )
}

function policySummary(policy: PolicySnapshot | null, t: TFunction): string {
  if (!policy || Object.keys(policy).length === 0) return t('wizard.policy.none')
  if (policy.non_refundable) return t('wizard.policy.nonRefundable')
  if (policy.free_until_hours_before) return t('wizard.policy.freeUntil', { count: policy.free_until_hours_before })
  return t('wizard.policy.withPenalty')
}
