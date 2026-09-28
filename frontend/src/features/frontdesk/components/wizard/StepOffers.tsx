import type { TFunction } from 'i18next'
import { BedDouble, CircleAlert, Users } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { useOffers, type Offer, type PolicySnapshot } from '../../api'
import { tr } from '../../lib/labels'
import { offerQuery, type StepErrors, type WizardState } from '../../lib/wizard'
import { FieldError } from './FieldError'

/** Offers of one room type, in the order the API ranks them (cheapest first). */
function groupByRoomType(offers: Offer[], first: string | null): { roomType: Offer['room_type']; offers: Offer[] }[] {
  const groups = new Map<string, { roomType: Offer['room_type']; offers: Offer[] }>()
  for (const offer of offers) {
    const group = groups.get(offer.room_type_id) ?? { roomType: offer.room_type, offers: [] }
    group.offers.push(offer)
    groups.set(offer.room_type_id, group)
  }
  const list = [...groups.values()]
  return first ? [...list.filter((g) => g.roomType.id === first), ...list.filter((g) => g.roomType.id !== first)] : list
}

/** Step 2 — the rate: every sellable room type × plan for those dates, with its total and conditions. */
export function StepOffers({
  state,
  update,
  errors,
}: {
  state: WizardState
  update: (patch: Partial<WizardState>) => void
  errors: StepErrors
}) {
  const { t, i18n } = useTranslation('frontdesk')
  const offers = useOffers(offerQuery(state))
  const chosen = state.offer ? `${state.offer.roomTypeId}:${state.offer.ratePlanId}` : null

  if (offers.isError) return <ErrorState error={offers.error} onRetry={() => offers.refetch()} />
  if (!offers.data) return <LoadingState variant="rows" rows={3} />
  if (offers.data.length === 0) {
    return <EmptyState icon={BedDouble} title={t('wizard.noOffers')} description={t('wizard.noOffersHint')} />
  }
  const promoRejected = state.promoCode.trim() !== '' && offers.data.every((offer) => offer.quote.violations.includes('promo_invalid'))
  const groups = groupByRoomType(offers.data, state.roomTypeId)

  return (
    <div className="grid gap-5" role="radiogroup" aria-label={t('wizard.steps.offer')}>
      {promoRejected && (
        <p className="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-[13px] text-warning-ink">
          <CircleAlert aria-hidden className="mt-0.5 size-3.5 shrink-0" />
          {t('wizard.promoRejected', { code: state.promoCode.trim().toUpperCase() })}
        </p>
      )}
      {groups.map(({ roomType, offers: plans }) => (
        <section key={roomType.id} className="grid gap-2">
          <header className="flex flex-wrap items-center justify-between gap-2">
            <p className="flex items-center gap-2 font-semibold text-fg">
              <span aria-hidden className="size-3 rounded-[4px] ring-1 ring-black/5" style={{ backgroundColor: roomType.color }} />
              {tr(roomType.name, i18n.language)}
              {state.roomTypeId === roomType.id && state.roomId && <Badge tone="accent">{t('wizard.pickedRoom')}</Badge>}
            </p>
            <p className="flex items-center gap-3 text-[13px] text-muted">
              <span className="inline-flex items-center gap-1">
                <Users aria-hidden className="size-3.5" />
                {t('wizard.upTo', { count: roomType.max_occupancy })}
              </span>
              <span>{t(roomType.kind === 'dorm' ? 'wizard.bedsLeft' : 'wizard.roomsLeft', { count: plans[0]!.available_units })}</span>
            </p>
          </header>
          <div className="grid gap-2">
            {plans.map((offer) => {
              const value = `${offer.room_type_id}:${offer.rate_plan_id}`
              const selected = value === chosen
              const nights = offer.quote.nights.length || 1
              return (
                <label
                  key={value}
                  className={cn(
                    'flex cursor-pointer items-start gap-3 rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:border-border-strong',
                    'focus-within:ring-2 focus-within:ring-accent/55',
                    selected && 'border-accent bg-accent-soft/40 hover:border-accent',
                  )}
                >
                  <input
                    type="radio"
                    name="offer"
                    value={value}
                    checked={selected}
                    onChange={() =>
                      update({
                        offer: {
                          roomTypeId: offer.room_type_id,
                          ratePlanId: offer.rate_plan_id,
                          total: offer.total,
                          depositPercent: offer.rate_plan.deposit_percent,
                        },
                      })
                    }
                    className="mt-1 size-4 shrink-0 accent-accent"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block font-semibold text-fg">
                      {tr(offer.rate_plan.name, i18n.language)}
                      <span className="sr-only"> · {tr(roomType.name, i18n.language)}</span>
                    </span>
                    <span className="mt-0.5 flex flex-wrap gap-x-2 text-[13px] text-muted">
                      <span>{t(`mealPlans.${offer.rate_plan.meal_plan}`, { defaultValue: offer.rate_plan.meal_plan })}</span>
                      <span aria-hidden>·</span>
                      <span>{policySummary(offer.rate_plan.cancellation_policy, t)}</span>
                      {offer.units_needed > 1 && (
                        <>
                          <span aria-hidden>·</span>
                          <span>{t('wizard.units', { count: offer.units_needed })}</span>
                        </>
                      )}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <MoneyText value={offer.total} currency={offer.quote.currency} className="block text-[15px] font-bold text-fg" />
                    <span className="num block text-xs text-muted">
                      <MoneyText value={Math.round(Number(offer.total) / nights)} currency={offer.quote.currency} /> {t('wizard.perNight')}
                    </span>
                    {offer.quote.taxes.some((tax) => tax.exempt) && <span className="block text-xs text-success-ink">{t('wizard.taxExempt')}</span>}
                  </span>
                </label>
              )
            })}
          </div>
        </section>
      ))}
      <FieldError error={errors.offer} />
    </div>
  )
}

function policySummary(policy: PolicySnapshot | null, t: TFunction): string {
  if (!policy || Object.keys(policy).length === 0) return t('wizard.policy.none')
  if (policy.non_refundable) return t('wizard.policy.nonRefundable')
  if (policy.free_until_hours_before) return t('wizard.policy.freeUntil', { count: policy.free_until_hours_before })
  return t('wizard.policy.withPenalty')
}
