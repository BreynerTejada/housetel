import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatMoney, normalizeLang } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useChangePlan, type BillingCycle, type BillingOverview, type BillingPlanOption } from '../api'
import { pickText, planPrice } from '../helpers'

/** Size line of a plan: "Hasta 60 unidades · 2 propiedades" / "Unidades y propiedades ilimitadas". */
export function PlanLimits({ plan, className }: { plan: Pick<BillingPlanOption, 'max_units' | 'max_properties'>; className?: string }) {
  const { t } = useTranslation('saas')
  const units = plan.max_units === null ? t('plans.unlimitedUnits') : t('plans.units', { count: plan.max_units })
  const properties =
    plan.max_properties === null ? t('plans.unlimitedProperties') : t('plans.properties', { count: plan.max_properties })
  return <span className={className}>{`${units} · ${properties}`}</span>
}

/** Switch plan and billing cycle. Plans too small for the current usage are shown but cannot be chosen. */
export function ChangePlanDialog({
  open,
  onOpenChange,
  overview,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  overview: BillingOverview
}) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const subscription = overview.subscription
  const [cycle, setCycle] = useState<BillingCycle>(subscription.billing_cycle)
  const [selected, setSelected] = useState(subscription.plan.code)
  const [error, setError] = useState<string | null>(null)
  const change = useChangePlan()

  const plan = overview.plans.find((option) => option.code === selected)
  const unchanged = selected === subscription.plan.code && cycle === subscription.billing_cycle
  const startDate = overview.upcoming_invoice?.date ?? subscription.current_period_end

  function reset(next: boolean) {
    if (!next) {
      setCycle(subscription.billing_cycle)
      setSelected(subscription.plan.code)
      setError(null)
    }
    onOpenChange(next)
  }

  async function submit() {
    if (!plan || unchanged) return
    setError(null)
    try {
      await change.mutateAsync({ plan_code: plan.code, billing_cycle: cycle })
      toast.success(t('billing.changePlan.done', { plan: pickText(plan.name, lang), cycle: t(`cycle.${cycle}`) }))
      onOpenChange(false)
    } catch (err) {
      setError(errorMessage(err, t))
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !change.isPending && reset(next)}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t('billing.changePlan.title')}</DialogTitle>
          <DialogDescription>{t('billing.changePlan.description')}</DialogDescription>
        </DialogHeader>

        <ToggleGroup
          type="single"
          value={cycle}
          onValueChange={(value) => value && setCycle(value as BillingCycle)}
          aria-label={t('billing.changePlan.cycle')}
          className="w-fit"
        >
          <ToggleGroupItem value="monthly">{t('cycle.monthly')}</ToggleGroupItem>
          <ToggleGroupItem value="yearly">
            {t('cycle.yearly')}
            <span className="rounded-full bg-success-soft px-1.5 text-[11px] font-bold text-success-ink">−15 %</span>
          </ToggleGroupItem>
        </ToggleGroup>

        <RadioGroup value={selected} onValueChange={setSelected} aria-label={t('billing.changePlan.plans')} className="gap-2.5">
          {overview.plans.map((option) => {
            const id = `plan-option-${option.code}`
            const price = planPrice(option, cycle)
            return (
              <label
                key={option.code}
                htmlFor={id}
                className={cn(
                  'grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 rounded-lg border p-3.5 transition-colors',
                  selected === option.code ? 'border-accent bg-accent-soft/40' : 'border-border hover:border-border-strong',
                  !option.fits && 'cursor-not-allowed opacity-60',
                )}
              >
                <RadioGroupItem id={id} value={option.code} disabled={!option.fits} className="mt-1" />
                <span className="min-w-0">
                  <span className="flex flex-wrap items-center gap-2">
                    <span className="font-bold text-fg">{pickText(option.name, lang)}</span>
                    {option.current && (
                      <span className="rounded-full bg-surface-2 px-2 text-[11px] font-semibold text-muted">
                        {t('billing.changePlan.current')}
                      </span>
                    )}
                  </span>
                  <PlanLimits plan={option} className="mt-0.5 block text-sm text-muted" />
                  {!option.fits && (
                    <span className="mt-1 block text-xs font-medium text-danger-ink">
                      {option.max_units !== null && overview.usage.units > option.max_units
                        ? t('billing.changePlan.tooSmallUnits', { count: overview.usage.units, max: option.max_units })
                        : t('billing.changePlan.tooSmallProperties', {
                            count: overview.usage.properties,
                            max: option.max_properties ?? 0,
                          })}
                    </span>
                  )}
                </span>
                <span className="text-right">
                  <span className="num block font-bold text-fg">{formatMoney(price)}</span>
                  <span className="block text-xs text-muted">
                    {cycle === 'yearly'
                      ? t('billing.perYearEq', { amount: formatMoney(Math.round(Number(option.price_yearly) / 12)) })
                      : t('billing.perMonth')}
                  </span>
                </span>
              </label>
            )
          })}
        </RadioGroup>

        {plan && !unchanged && (
          <p className="rounded-md bg-surface-2 px-3 py-2 text-sm text-muted">
            {subscription.status === 'trialing'
              ? t('billing.changePlan.whenTrial', { plan: pickText(plan.name, lang) })
              : t('billing.changePlan.when', {
                  date: formatDate(startDate, undefined, lang),
                  amount: formatMoney(planPrice(plan, cycle)),
                  rate: Number(overview.tax_rate),
                })}
          </p>
        )}

        {error && (
          <p role="alert" className="rounded-md bg-danger-soft px-3 py-2 text-sm text-danger-ink">
            {error}
          </p>
        )}

        <DialogFooter>
          <Button variant="secondary" onClick={() => reset(false)} disabled={change.isPending}>
            {t('common:actions.cancel')}
          </Button>
          <Button variant="primary" onClick={() => void submit()} disabled={unchanged || !plan?.fits} loading={change.isPending}>
            {plan && !unchanged
              ? t('billing.changePlan.submitTo', { plan: pickText(plan.name, lang), cycle: t(`cycle.${cycle}`).toLowerCase() })
              : t('billing.changePlan.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
