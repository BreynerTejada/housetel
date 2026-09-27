import { CornerDownRight, Layers, Plus } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatMoney, normalizeLang, type Lang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useDeleteResource, type RatePlan } from '../../api'
import { soldRoomTypes, type PlansData } from '../../hooks/usePlansData'
import { derivedPrice, KNOWN_CHANNELS, type PlanFamily } from '../../lib/plans'
import { derivationLabel, pick } from '../../lib/text'
import { RowActions } from '../crud'
import { PlanDialog, type PlanDialogState } from './PlanDialog'
import { DefaultsDialog, type DefaultsTarget } from './PriceDialogs'

/**
 * Tab "Planes": every base plan with the derived plans that follow it. The table puts each category's default
 * price next to the price every derived plan computes from it, so a change in the base shows where it lands.
 */
export function PlanFamilies({ data, currency }: { data: PlansData; currency: string }) {
  const { t } = useTranslation('rates')
  const canManage = useCan('rates.manage')
  const [dialog, setDialog] = useState<PlanDialogState>({ open: false, plan: null, parentId: null, key: 0 })
  const [pricing, setPricing] = useState<{ open: boolean; target: DefaultsTarget | null; key: number }>({ open: false, target: null, key: 0 })

  const openPlan = (plan: RatePlan | null, parentId: string | null = null) =>
    setDialog((current) => ({ open: true, plan, parentId, key: current.key + 1 }))
  const openPricing = (target: DefaultsTarget) => setPricing((current) => ({ open: true, target, key: current.key + 1 }))

  if (data.isPending) return <LoadingState variant="rows" rows={6} />
  if (data.error) return <ErrorState error={data.error} onRetry={data.refetch} />

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="max-w-2xl text-[13px] text-muted">{t('plans.families.intro')}</p>
        {canManage && data.families.length > 0 && (
          <Button variant="primary" onClick={() => openPlan(null)}>
            <Plus aria-hidden />
            {t('plans.editor.new')}
          </Button>
        )}
      </div>

      {data.families.length === 0 ? (
        <EmptyState
          icon={Layers}
          title={t('grid.noPlans')}
          description={t('plans.families.emptyHint')}
          action={
            canManage && (
              <Button variant="primary" onClick={() => openPlan(null)}>
                {t('plans.families.createBase')}
              </Button>
            )
          }
        />
      ) : (
        data.families.map((family) => (
          <FamilyCard
            key={family.base.id}
            family={family}
            data={data}
            currency={currency}
            canManage={canManage}
            onEdit={(plan) => openPlan(plan)}
            onDerive={(base) => openPlan(null, base.id)}
            onPrice={openPricing}
          />
        ))
      )}

      {dialog.open || dialog.key > 0 ? (
        <PlanDialog
          key={dialog.key}
          state={dialog}
          onOpenChange={(open) => setDialog((current) => ({ ...current, open }))}
          data={data}
          currency={currency}
        />
      ) : null}
      {pricing.target && (
        <DefaultsDialog
          key={pricing.key}
          open={pricing.open}
          onOpenChange={(open) => setPricing((current) => ({ ...current, open }))}
          target={pricing.target}
          currency={currency}
        />
      )}
    </div>
  )
}

function channelsLabel(plan: RatePlan, t: (key: string) => string): string {
  if (plan.channels.length === 0) return t('plans.families.allChannels')
  return plan.channels
    .map((code) => ((KNOWN_CHANNELS as readonly string[]).includes(code) ? t(`plans.channelsShort.${code}`) : code))
    .join(', ')
}

function PlanBadges({ plan, data, lang }: { plan: RatePlan; data: PlansData; lang: Lang }) {
  const { t } = useTranslation('rates')
  const policy = plan.cancellation_policy ? data.policyById.get(plan.cancellation_policy) : null
  return (
    <div className="flex flex-wrap gap-1.5">
      <Badge tone="neutral">{t(`plans.meals.${plan.meal_plan}`)}</Badge>
      <Badge tone={policy?.non_refundable ? 'warning' : 'neutral'}>{policy ? pick(policy.name, lang) : t('plans.editor.noPolicy')}</Badge>
      <Badge tone="neutral">{channelsLabel(plan, t)}</Badge>
      {Number(plan.deposit_percent) > 0 && <Badge tone="info">{t('plans.families.deposit', { value: Number(plan.deposit_percent) })}</Badge>}
      {plan.min_los_default > 1 && <Badge tone="info">{t('plans.families.minLos', { count: plan.min_los_default })}</Badge>}
      {!plan.is_public && <Badge tone="accent">{t('plans.families.frontDeskOnly')}</Badge>}
      {!plan.is_active && <Badge tone="stone">{t('states.inactive')}</Badge>}
    </div>
  )
}

function FamilyCard({
  family,
  data,
  currency,
  canManage,
  onEdit,
  onDerive,
  onPrice,
}: {
  family: PlanFamily
  data: PlansData
  currency: string
  canManage: boolean
  onEdit: (plan: RatePlan) => void
  onDerive: (base: RatePlan) => void
  onPrice: (target: DefaultsTarget) => void
}) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const remove = useDeleteResource('rate-plans')
  const { base, derived } = family
  const baseName = pick(base.name, lang)
  const headingId = `plan-${base.id}`
  const roomTypes = soldRoomTypes(base, data.roomTypes)

  async function deletePlan(plan: RatePlan) {
    await remove.mutateAsync(plan.id)
    toast.success(t('plans.editor.deleted'))
  }

  return (
    // min-w-0: as a grid item the card would grow to the table's width instead of scrolling it on phones
    <section
      aria-labelledby={headingId}
      className={cn('min-w-0 rounded-lg border border-border bg-surface shadow-xs', !base.is_active && 'opacity-75')}
    >
      <header className="flex flex-wrap items-start gap-x-4 gap-y-3 px-4 pt-4 pb-3 sm:px-5">
        <div className="grid min-w-0 flex-1 gap-1.5">
          <p className="eyebrow">
            {t('plans.families.basePlan')} · {base.code}
          </p>
          <h2 id={headingId} className="text-[17px] leading-6 font-bold tracking-[-0.015em] text-fg">
            {baseName}
          </h2>
          <PlanBadges plan={base} data={data} lang={lang} />
        </div>
        {canManage && (
          <div className="flex items-center gap-1">
            <Button size="sm" onClick={() => onDerive(base)} aria-label={t('plans.families.derive', { plan: baseName })}>
              <CornerDownRight aria-hidden />
              {t('plans.families.deriveShort')}
            </Button>
            <RowActions name={baseName} onEdit={() => onEdit(base)} onDelete={() => deletePlan(base)} />
          </div>
        )}
      </header>

      {roomTypes.length === 0 ? (
        <p className="border-t border-border px-5 py-4 text-sm text-muted">{t('plans.families.noRoomTypes')}</p>
      ) : (
        <div className="border-t border-border">
          <Table aria-label={t('plans.families.tableLabel', { plan: baseName })} className="num text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="sticky left-0 z-10 min-w-40 bg-surface pl-4 sm:pl-5">{t('plans.families.roomType')}</TableHead>
                <TableHead className="min-w-32 text-right align-bottom">
                  <span className="eyebrow block text-accent-ink">{t('plans.families.base')}</span>
                  <span className="text-[13px] font-bold text-fg">{baseName}</span>
                </TableHead>
                {derived.map((plan) => (
                  <DerivedHeader
                    key={plan.id}
                    plan={plan}
                    data={data}
                    currency={currency}
                    canManage={canManage}
                    onEdit={() => onEdit(plan)}
                    onDelete={() => deletePlan(plan)}
                  />
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {roomTypes.map((roomType) => {
                const defaults = data.defaultsFor(roomType.id, base.id)
                const name = pick(roomType.name, lang)
                return (
                  <TableRow key={roomType.id}>
                    <TableHead scope="row" className="sticky left-0 z-10 h-auto bg-surface py-2.5 pl-4 font-normal sm:pl-5">
                      <span className="flex items-center gap-2.5">
                        <span aria-hidden className="h-6 w-1 shrink-0 rounded-full" style={{ background: roomType.color }} />
                        <span className="grid">
                          <span className="text-[13px] font-semibold text-fg">{name}</span>
                          <span className="text-2xs font-semibold tracking-wide text-muted">{roomType.code}</span>
                        </span>
                      </span>
                    </TableHead>
                    <TableCell className="text-right">
                      {defaults ? (
                        <MoneyText value={defaults.price} currency={currency} className="text-[14px] font-bold text-fg" />
                      ) : (
                        <span className="inline-flex items-center justify-end gap-2">
                          <span className="font-semibold text-warning-ink">{t('plans.families.noPrice')}</span>
                          {canManage && (
                            <Button
                              size="sm"
                              variant="link"
                              aria-label={t('plans.defaults.setFor', { roomType: name })}
                              onClick={() => onPrice({ roomType, plan: base, defaults: null })}
                            >
                              {t('plans.defaults.set')}
                            </Button>
                          )}
                        </span>
                      )}
                    </TableCell>
                    {derived.map((plan) => (
                      <TableCell key={plan.id} className="border-l border-dashed border-border text-right">
                        {!plan.room_types.includes(roomType.id) ? (
                          <span className="text-xs text-subtle">{t('plans.families.notSold')}</span>
                        ) : defaults ? (
                          <span className="font-semibold text-fg">{formatMoney(derivedPrice(defaults.price, plan, currency), currency)}</span>
                        ) : (
                          <span className="text-subtle">—</span>
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </section>
  )
}

function DerivedHeader({
  plan,
  data,
  currency,
  canManage,
  onEdit,
  onDelete,
}: {
  plan: RatePlan
  data: PlansData
  currency: string
  canManage: boolean
  onEdit: () => void
  onDelete: () => Promise<unknown>
}) {
  const { t, i18n } = useTranslation('rates')
  const lang = normalizeLang(i18n.language)
  const name = pick(plan.name, lang)
  const policy = plan.cancellation_policy ? data.policyById.get(plan.cancellation_policy) : null
  const policyName = policy ? pick(policy.name, lang) : null
  // "No reembolsable" usually names both the plan and its policy: say it once
  const details = [plan.meal_plan !== 'room_only' ? t(`plans.meals.${plan.meal_plan}`) : null, policyName !== name ? policyName : null]
    .filter(Boolean)
    .join(' · ')
  return (
    <TableHead className={cn('h-auto min-w-40 border-l border-dashed border-border py-2 text-right align-bottom', !plan.is_active && 'opacity-60')}>
      <span className="flex items-center justify-end gap-1.5">
        <CornerDownRight aria-hidden className="size-3.5 shrink-0 text-accent" />
        <span className="text-[13px] font-semibold whitespace-normal text-fg">{name}</span>
      </span>
      <span className="mt-1 flex items-center justify-end gap-1">
        <span className="rounded-full bg-accent-soft px-2 py-px text-2xs font-bold text-accent-ink">
          {derivationLabel(plan.derivation_type, plan.derivation_value, currency, lang)}
        </span>
        {canManage && <RowActions name={name} onEdit={onEdit} onDelete={onDelete} />}
      </span>
      {details && <span className="mt-0.5 block text-2xs font-medium whitespace-normal text-muted">{details}</span>}
    </TableHead>
  )
}
