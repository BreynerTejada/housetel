import { CircleAlert, Clock, CreditCard, FlaskConical, Lock, Receipt, RotateCcw } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatMoney, normalizeLang } from '@/lib/format'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import {
  useBillingOverview,
  useCancelSubscription,
  useInvoices,
  usePayInvoice,
  useResumeSubscription,
  useVerifyInvoice,
  type BillingOverview,
  type PlatformInvoice,
} from '../api'
import { ChangePlanDialog, PlanLimits } from '../components/ChangePlanDialog'
import { CommissionsStatement } from '../components/CommissionsStatement'
import { InvoicesTable } from '../components/InvoicesTable'
import { PaymentMethodDialog } from '../components/PaymentMethodDialog'
import { SubscriptionBadge } from '../components/StatusBadges'
import { UsageMeter } from '../components/UsageMeter'
import { pickText, planPrice } from '../helpers'

/** `/app/settings/billing`: the hotel's Housetel plan, usage, next charge, card, invoices and commissions. */
export default function BillingPage() {
  const { t } = useTranslation('saas')
  const overview = useBillingOverview()
  useReturnFromCheckout()

  return (
    <div className="grid grid-cols-1 gap-2">
      <PageHeader title={t('billing.title')} description={t('billing.description')} />
      {overview.isPending ? (
        <LoadingState variant="rows" rows={8} />
      ) : overview.isError ? (
        <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />
      ) : (
        <BillingContent overview={overview.data} />
      )}
    </div>
  )
}

/** Back from Wompi's checkout (`?invoice=<id>`): verify that payment once and tell the result. */
function useReturnFromCheckout() {
  const { t } = useTranslation('saas')
  const [params, setParams] = useSearchParams()
  const verify = useVerifyInvoice()
  const invoiceId = params.get('invoice')
  const handled = useRef<string | null>(null)

  useEffect(() => {
    if (!invoiceId || handled.current === invoiceId) return
    handled.current = invoiceId
    verify
      .mutateAsync(invoiceId)
      .then((invoice) => {
        if (invoice.status === 'paid') toast.success(t('billing.pay.paid', { number: invoice.number }))
        else if (invoice.status === 'failed') toast.error(invoice.last_error || t('billing.pay.declined'))
        else toast.info(t('billing.pay.pending', { number: invoice.number }))
      })
      .catch((error: unknown) => toast.error(errorMessage(error, t)))
      .finally(() => {
        const next = new URLSearchParams(params)
        next.delete('invoice')
        next.delete('id')
        setParams(next, { replace: true })
      })
  }, [invoiceId, params, setParams, t, verify])
}

/** Pay one invoice: simulated charges now; real mode goes to Wompi's checkout and comes back here. */
function usePayFlow() {
  const { t } = useTranslation('saas')
  const pay = usePayInvoice()
  const [payingId, setPayingId] = useState<string | null>(null)

  async function run(invoice: PlatformInvoice) {
    setPayingId(invoice.id)
    try {
      const result = await pay.mutateAsync(invoice.id)
      if (result.status === 'approved') toast.success(t('billing.pay.paid', { number: invoice.number }))
      else if (result.status === 'requires_action' && result.checkout_url) window.location.assign(result.checkout_url)
      else if (result.status === 'pending') toast.info(t('billing.pay.pending', { number: invoice.number }))
      else toast.error(result.message || t('billing.pay.declined'))
    } catch (error) {
      toast.error(errorMessage(error, t))
    } finally {
      setPayingId(null)
    }
  }

  return { run, payingId }
}

function BillingContent({ overview }: { overview: BillingOverview }) {
  const { t } = useTranslation('saas')
  const canManage = useCan('saas.billing_manage')
  const invoices = useInvoices()
  const payFlow = usePayFlow()
  const [planOpen, setPlanOpen] = useState(false)
  const [cardOpen, setCardOpen] = useState(false)
  const openInvoices = overview.open_invoices

  return (
    <div className="grid grid-cols-1 gap-6">
      <StatusCallout
        overview={overview}
        canManage={canManage}
        onPay={(invoice) => void payFlow.run(invoice)}
        payingId={payFlow.payingId}
        onCard={() => setCardOpen(true)}
      />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <PlanCard overview={overview} canManage={canManage} onChangePlan={() => setPlanOpen(true)} />
        <NextChargeCard overview={overview} canManage={canManage} onCard={() => setCardOpen(true)} />
      </div>

      <UsageSection overview={overview} />

      <Tabs defaultValue="invoices">
        <TabsList>
          <TabsTrigger value="invoices">
            <Receipt aria-hidden />
            {t('billing.tabs.invoices')}
            {openInvoices.length > 0 && <Badge tone="warning">{openInvoices.length}</Badge>}
          </TabsTrigger>
          <TabsTrigger value="commissions">{t('billing.tabs.commissions')}</TabsTrigger>
        </TabsList>
        <TabsContent value="invoices">
          {invoices.isError ? (
            <ErrorState error={invoices.error} onRetry={() => void invoices.refetch()} />
          ) : (
            <InvoicesTable
              invoices={invoices.data ?? []}
              isLoading={invoices.isPending}
              empty={<EmptyState icon={Receipt} title={t('invoices.emptyTitle')} description={t('invoices.emptyText')} />}
              actions={(invoice) =>
                canManage && (invoice.status === 'open' || invoice.status === 'failed') ? (
                  <Button
                    size="sm"
                    variant="primary"
                    loading={payFlow.payingId === invoice.id}
                    onClick={(event) => {
                      event.stopPropagation()
                      void payFlow.run(invoice)
                    }}
                  >
                    {t('billing.pay.action')}
                  </Button>
                ) : null
              }
            />
          )}
        </TabsContent>
        <TabsContent value="commissions">
          <CommissionsStatement />
        </TabsContent>
      </Tabs>

      {canManage && <CancelSection overview={overview} />}

      {canManage && <ChangePlanDialog open={planOpen} onOpenChange={setPlanOpen} overview={overview} />}
      {canManage && <PaymentMethodDialog open={cardOpen} onOpenChange={setCardOpen} />}
    </div>
  )
}

function Callout({
  tone,
  icon: Icon,
  title,
  children,
  actions,
}: {
  tone: 'danger' | 'warning' | 'info' | 'stone'
  icon: typeof Lock
  title: string
  children: ReactNode
  actions?: ReactNode
}) {
  const styles = {
    danger: 'border-danger/35 bg-danger-soft text-danger-ink',
    warning: 'border-warning/40 bg-warning-soft text-warning-ink',
    info: 'border-info/30 bg-info-soft text-info-ink',
    stone: 'border-border bg-stone-soft text-stone-ink',
  }[tone]
  return (
    <section role={tone === 'danger' || tone === 'warning' ? 'alert' : undefined} className={cn('flex flex-col gap-3 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5', styles)}>
      <div className="flex items-start gap-3">
        <Icon aria-hidden className="mt-0.5 size-5 shrink-0" />
        <div className="min-w-0">
          <p className="font-bold">{title}</p>
          <div className="mt-0.5 text-sm opacity-90">{children}</div>
        </div>
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2 pl-8 sm:pl-0">{actions}</div>}
    </section>
  )
}

function StatusCallout({
  overview,
  canManage,
  onPay,
  payingId,
  onCard,
}: {
  overview: BillingOverview
  canManage: boolean
  onPay: (invoice: PlatformInvoice) => void
  payingId: string | null
  onCard: () => void
}) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const subscription = overview.subscription
  const oldest = overview.open_invoices[0]
  const amount = formatMoney(overview.summary.open_balance)
  const resume = useResumeSubscription()

  const payButton = oldest && canManage && (
    <Button variant={subscription.status === 'suspended' ? 'danger' : 'primary'} loading={payingId === oldest.id} onClick={() => onPay(oldest)}>
      {t('billing.pay.invoice', { number: oldest.number, amount: formatMoney(oldest.total) })}
    </Button>
  )

  if (subscription.status === 'suspended') {
    return (
      <Callout tone="danger" icon={Lock} title={t('billing.callout.suspended.title')} actions={payButton}>
        {oldest ? t('billing.callout.suspended.text', { amount }) : t('billing.callout.suspended.noInvoices')}
        {!canManage && ` ${t('billing.callout.askOwner')}`}
      </Callout>
    )
  }
  if (subscription.status === 'past_due') {
    return (
      <Callout
        tone="warning"
        icon={CircleAlert}
        title={t('billing.callout.pastDue.title')}
        actions={
          <>
            {payButton}
            {canManage && (
              <Button variant="secondary" onClick={onCard}>
                <CreditCard aria-hidden />
                {subscription.payment_source ? t('billing.card.change') : t('billing.card.add')}
              </Button>
            )}
          </>
        }
      >
        {t('billing.callout.pastDue.text', {
          amount,
          days: new Intl.ListFormat(lang, { type: 'conjunction' }).format(overview.retry_schedule_days.map(String)),
          next: subscription.next_retry_at ? formatDate(subscription.next_retry_at, undefined, lang) : '—',
        })}
        {!canManage && ` ${t('billing.callout.askOwner')}`}
      </Callout>
    )
  }
  if (subscription.status === 'cancelled') {
    return (
      <Callout tone="stone" icon={CircleAlert} title={t('billing.callout.cancelled.title')}>
        {t('billing.callout.cancelled.text')}
      </Callout>
    )
  }
  if (subscription.cancel_at_period_end) {
    return (
      <Callout
        tone="stone"
        icon={Clock}
        title={t('billing.callout.cancelling.title', {
          date: formatDate(subscription.status === 'trialing' ? subscription.trial_ends_at : subscription.current_period_end, undefined, lang),
        })}
        actions={
          canManage && (
            <Button
              variant="secondary"
              loading={resume.isPending}
              onClick={() =>
                resume
                  .mutateAsync()
                  .then(() => toast.success(t('billing.cancel.resumed')))
                  .catch((error: unknown) => toast.error(errorMessage(error, t)))
              }
            >
              <RotateCcw aria-hidden />
              {t('billing.cancel.resume')}
            </Button>
          )
        }
      >
        {t('billing.callout.cancelling.text')}
      </Callout>
    )
  }
  if (subscription.status === 'trialing') {
    const days = overview.summary.trial_days_left ?? 0
    return (
      <Callout
        tone="info"
        icon={Clock}
        title={t('billing.callout.trial.title', { count: days })}
        actions={
          canManage && !subscription.payment_source && (
            <Button variant="primary" onClick={onCard}>
              <CreditCard aria-hidden />
              {t('billing.card.add')}
            </Button>
          )
        }
      >
        {subscription.payment_source
          ? t('billing.callout.trial.withCard', { date: formatDate(subscription.trial_ends_at, undefined, lang) })
          : t('billing.callout.trial.noCard', { date: formatDate(subscription.trial_ends_at, undefined, lang) })}
      </Callout>
    )
  }
  return null
}

function PlanCard({ overview, canManage, onChangePlan }: { overview: BillingOverview; canManage: boolean; onChangePlan: () => void }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const subscription = overview.subscription
  const plan = subscription.plan
  const cycle = subscription.billing_cycle
  return (
    <section className="relative flex flex-col gap-4 rounded-xl border border-accent/25 bg-accent-soft p-5 sm:p-6">
      {/* The key-tag perforation of the Housetel motif. */}
      <span aria-hidden className="absolute top-4 right-4 size-2.5 rounded-full bg-bg shadow-[inset_0_1px_2px_rgb(0_0_0/0.3)]" />
      <div className="flex flex-wrap items-center gap-2 pr-6">
        <p className="eyebrow !text-accent-ink/80">{t('billing.plan.eyebrow')}</p>
        <SubscriptionBadge status={subscription.status} />
      </div>
      <div>
        <p className="text-[34px] leading-none font-extrabold tracking-[-0.04em] text-accent-ink">{pickText(plan.name, lang)}</p>
        <p className="mt-2 text-accent-ink">
          <span className="num text-[18px] font-bold">{formatMoney(planPrice(plan, cycle))}</span>
          <span className="text-sm"> {cycle === 'yearly' ? t('billing.perYear') : t('billing.perMonth')}</span>
          <span className="text-sm text-accent-ink/75"> · {t('billing.plusTax', { rate: Number(overview.tax_rate) })}</span>
        </p>
        {cycle === 'yearly' && (
          <p className="text-sm text-accent-ink/75">{t('billing.perYearEq', { amount: formatMoney(subscription.monthly_amount) })}</p>
        )}
        <PlanLimits plan={plan} className="mt-1 block text-sm text-accent-ink/85" />
      </div>
      <p className="text-sm text-accent-ink/85">{t('billing.plan.included')}</p>
      {canManage && subscription.status !== 'cancelled' && (
        <div className="mt-auto">
          <Button variant="secondary" onClick={onChangePlan}>
            {t('billing.plan.change')}
          </Button>
        </div>
      )}
    </section>
  )
}

function NextChargeCard({ overview, canManage, onCard }: { overview: BillingOverview; canManage: boolean; onCard: () => void }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const subscription = overview.subscription
  const upcoming = overview.upcoming_invoice
  const source = subscription.payment_source
  const overdue =
    (subscription.status === 'past_due' || subscription.status === 'suspended') && Number(overview.summary.open_balance) > 0

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-border bg-surface p-5 shadow-xs sm:p-6">
      <div>
        <p className="eyebrow">{overdue ? t('billing.next.overdue') : t('billing.next.eyebrow')}</p>
        {overdue ? (
          <>
            <p className="mt-2 text-[28px] leading-8 font-semibold tracking-[-0.02em] text-danger-ink">
              {formatMoney(overview.summary.open_balance)}
            </p>
            <p className="text-sm text-muted">{t('billing.next.overdueText', { count: overview.open_invoices.length })}</p>
          </>
        ) : upcoming ? (
          <>
            <p className="mt-2 text-[28px] leading-8 font-semibold tracking-[-0.02em] text-fg first-letter:uppercase">
              {formatDate(upcoming.date, 'd MMM yyyy', lang)}
            </p>
            <p className="text-sm text-muted">
              {subscription.status === 'trialing' ? t('billing.next.firstCharge') : t('billing.next.renewal')}
            </p>
            <dl className="mt-3 grid grid-cols-1 gap-1 text-sm">
              <Row label={t('billing.next.plan', { plan: pickText(subscription.plan.name, lang) })} value={upcoming.subtotal} />
              <Row label={t('billing.next.tax', { rate: Number(overview.tax_rate) })} value={upcoming.tax} />
              <Row label={t('billing.next.total')} value={upcoming.total} strong />
            </dl>
          </>
        ) : (
          <p className="mt-2 text-sm text-muted">{t('billing.next.none')}</p>
        )}
      </div>

      <div className="mt-auto grid grid-cols-1 gap-2 border-t border-border pt-4">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-semibold text-fg">{t('billing.card.title')}</p>
          {overview.billing_mode === 'simulated' && (
            <Badge tone="info">
              <FlaskConical aria-hidden />
              {t('billing.card.simulated')}
            </Badge>
          )}
        </div>
        {source ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span aria-hidden className="grid grid-cols-1 h-8 w-12 place-items-center rounded-md border border-border bg-surface-2 text-[10px] font-extrabold tracking-wide text-muted">
                {(source.brand ?? 'CARD').slice(0, 4)}
              </span>
              <div>
                <p className="num font-semibold text-fg">{t('billing.card.masked', { brand: source.brand ?? '', last4: source.last4 ?? '' })}</p>
                {source.exp_month && source.exp_year && (
                  <p className="num text-xs text-muted">
                    {t('billing.card.expires', { date: `${String(source.exp_month).padStart(2, '0')}/${String(source.exp_year).slice(-2)}` })}
                  </p>
                )}
              </div>
            </div>
            {canManage && (
              <Button variant="ghost" size="sm" onClick={onCard}>
                {t('billing.card.change')}
              </Button>
            )}
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted">{t('billing.card.none')}</p>
            {canManage && (
              <Button variant="secondary" size="sm" onClick={onCard}>
                <CreditCard aria-hidden />
                {t('billing.card.add')}
              </Button>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

function Row({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={cn('flex items-baseline justify-between gap-3', strong && 'border-t border-dashed border-border pt-1')}>
      <dt className={strong ? 'font-semibold text-fg' : 'text-muted'}>{label}</dt>
      <dd>
        <MoneyText value={value} className={strong ? 'font-bold text-fg' : 'text-fg'} />
      </dd>
    </div>
  )
}

function UsageSection({ overview }: { overview: BillingOverview }) {
  const { t } = useTranslation('saas')
  const usage = overview.usage
  return (
    <section className="grid grid-cols-1 gap-4 rounded-xl border border-border bg-surface p-5 shadow-xs sm:p-6">
      <div>
        <h2 className="text-[15px] font-bold text-fg">{t('billing.usage.title')}</h2>
        <p className="text-sm text-muted">{t('billing.usage.description')}</p>
      </div>
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        <UsageMeter
          label={t('billing.usage.units')}
          value={usage.units}
          max={usage.max_units}
          valueLabel={t('billing.usage.of', { value: usage.units, max: usage.max_units ?? 0 })}
          unlimitedLabel={t('billing.usage.unlimited', { value: usage.units })}
        />
        <UsageMeter
          label={t('billing.usage.properties')}
          value={usage.properties}
          max={usage.max_properties}
          valueLabel={t('billing.usage.of', { value: usage.properties, max: usage.max_properties ?? 0 })}
          unlimitedLabel={t('billing.usage.unlimited', { value: usage.properties })}
        />
      </div>
      {usage.over_limit && (
        <p className="flex items-start gap-2 rounded-md bg-warning-soft px-3 py-2 text-sm text-warning-ink">
          <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
          {t('billing.usage.overLimit')}
        </p>
      )}
    </section>
  )
}

function CancelSection({ overview }: { overview: BillingOverview }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const subscription = overview.subscription
  const cancel = useCancelSubscription()
  const [reason, setReason] = useState('')
  if (subscription.status === 'cancelled' || subscription.cancel_at_period_end) return null
  const endDate = subscription.status === 'trialing' ? subscription.trial_ends_at : subscription.current_period_end

  return (
    <section className="flex flex-col gap-3 rounded-xl border border-border p-5 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <h2 className="text-[15px] font-bold text-fg">{t('billing.cancel.title')}</h2>
        <p className="mt-0.5 max-w-xl text-sm text-muted">{t('billing.cancel.text', { date: formatDate(endDate, undefined, lang) })}</p>
      </div>
      <ConfirmDialog
        trigger={
          <Button variant="ghost" className="shrink-0 text-danger-ink hover:bg-danger-soft">
            {t('billing.cancel.action')}
          </Button>
        }
        title={t('billing.cancel.confirmTitle')}
        description={t('billing.cancel.confirmText', { date: formatDate(endDate, undefined, lang) })}
        confirmLabel={t('billing.cancel.confirm')}
        onConfirm={async () => {
          await cancel.mutateAsync(reason.trim())
          setReason('')
          toast.success(t('billing.cancel.done', { date: formatDate(endDate, undefined, lang) }))
        }}
      >
        <div className="grid grid-cols-1 gap-1.5">
          <Label htmlFor="cancel-reason">{t('billing.cancel.reason')}</Label>
          <Textarea id="cancel-reason" name="reason" rows={3} value={reason} onChange={(event) => setReason(event.target.value)} />
        </div>
      </ConfirmDialog>
    </section>
  )
}
