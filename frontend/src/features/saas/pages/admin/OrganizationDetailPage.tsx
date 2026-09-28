import { Ban, CalendarPlus, FlaskConical, Package, RotateCcw, TimerOff } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router'
import { toast } from 'sonner'
import { ConfirmDialog, DangerConfirmDialog } from '@/components/ConfirmDialog'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatMoney, formatRelative, normalizeLang } from '@/lib/format'
import {
  useAdminChangePlan,
  useEndTrial,
  useExtendTrial,
  useOrganization,
  usePlans,
  useReactivateOrganization,
  useSimulateFailure,
  useSuspendOrganization,
  type BillingCycle,
  type OrganizationDetail,
} from '../../api'
import { AdminInvoiceActions } from '../../components/AdminInvoiceActions'
import { PlanLimits } from '../../components/ChangePlanDialog'
import { CommissionsTable } from '../../components/CommissionsTable'
import { SettlementList } from '../../components/CommissionsStatement'
import { InvoicesTable } from '../../components/InvoicesTable'
import { OrganizationBadge, SubscriptionBadge } from '../../components/StatusBadges'
import { UsageMeter } from '../../components/UsageMeter'
import { pickText } from '../../helpers'

/** `/admin/organizations/:id`: read-only view of a hotel organization plus the platform's account actions. */
export default function OrganizationDetailPage() {
  const { t } = useTranslation('saas')
  const { id = '' } = useParams()
  const org = useOrganization(id)
  return (
    <div className="mx-auto grid grid-cols-1 w-full max-w-7xl gap-2">
      {org.isPending ? (
        <LoadingState variant="rows" rows={8} />
      ) : org.isError ? (
        <>
          <PageHeader title={t('pages.adminOrgDetail')} breadcrumbs={[{ label: t('nav.adminOrgs'), to: '/admin/organizations' }]} />
          <ErrorState error={org.error} onRetry={() => void org.refetch()} />
        </>
      ) : (
        <Detail org={org.data} />
      )}
    </div>
  )
}

function Detail({ org }: { org: OrganizationDetail }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  return (
    <>
      <PageHeader
        breadcrumbs={[{ label: t('nav.adminOrgs'), to: '/admin/organizations' }, { label: org.name }]}
        title={
          <span className="flex flex-wrap items-center gap-2.5">
            {org.name}
            <OrganizationBadge status={org.status} />
          </span>
        }
        description={t('admin.org.subtitle', {
          legal: org.legal_name || org.name,
          nit: org.nit ? `NIT ${org.nit}` : t('admin.org.noNit'),
          date: formatDate(org.customer_since, undefined, lang),
        })}
        actions={<OrgActions org={org} />}
      />

      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Fact label={t('admin.org.plan')}>
          {org.plan ? pickText(org.plan.name, lang) : t('admin.orgs.noPlan')}
          {org.subscription && <span className="ml-1.5 text-sm font-normal text-muted">· {t(`cycle.${org.subscription.billing_cycle}`)}</span>}
        </Fact>
        <Fact label={t('admin.org.mrr')}>
          <MoneyText value={org.mrr} />
        </Fact>
        <Fact label={t('admin.org.units')}>
          <span className="num">
            {org.units}
            {org.plan?.max_units ? <span className="text-muted"> / {org.plan.max_units}</span> : null}
          </span>
        </Fact>
        <Fact label={org.status === 'trial' ? t('admin.org.trialEnds') : t('admin.org.renewal')}>
          {org.status === 'trial'
            ? formatDate(org.trial_ends_at, undefined, lang)
            : formatDate(org.subscription?.current_period_end, undefined, lang)}
        </Fact>
      </dl>

      <Tabs defaultValue="subscription" className="mt-4">
        <TabsList>
          <TabsTrigger value="subscription">{t('admin.org.tabs.subscription')}</TabsTrigger>
          <TabsTrigger value="properties">{t('admin.org.tabs.properties', { count: org.properties.length })}</TabsTrigger>
          <TabsTrigger value="team">{t('admin.org.tabs.team', { count: org.users.length })}</TabsTrigger>
          <TabsTrigger value="invoices">{t('admin.org.tabs.invoices')}</TabsTrigger>
          <TabsTrigger value="commissions">{t('admin.org.tabs.commissions')}</TabsTrigger>
        </TabsList>
        <TabsContent value="subscription">
          <SubscriptionTab org={org} />
        </TabsContent>
        <TabsContent value="properties">
          <PropertiesTab org={org} />
        </TabsContent>
        <TabsContent value="team">
          <TeamTab org={org} />
        </TabsContent>
        <TabsContent value="invoices">
          <InvoicesTable
            invoices={org.invoices}
            admin
            actions={(invoice) => <AdminInvoiceActions invoice={invoice} />}
            empty={t('invoices.empty')}
          />
        </TabsContent>
        <TabsContent value="commissions">
          <div className="grid grid-cols-1 gap-5">
            <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              {(['pending', 'settled', 'reversed'] as const).map((status) => (
                <Fact key={status} label={t(`status.commission.${status}`)}>
                  <MoneyText value={org.commissions.summary[status].total} />
                  <span className="ml-1.5 text-sm font-normal text-muted">
                    {t('commissions.bookings', { count: org.commissions.summary[status].count })}
                  </span>
                </Fact>
              ))}
            </dl>
            {org.settlements.length > 0 && <SettlementList settlements={org.settlements} />}
            <CommissionsTable commissions={org.commissions.recent} />
          </div>
        </TabsContent>
      </Tabs>
    </>
  )
}

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
      <dt className="text-[13px] font-semibold text-muted">{label}</dt>
      <dd className="mt-1.5 text-[18px] leading-6 font-semibold text-fg">{children}</dd>
    </div>
  )
}

function OrgActions({ org }: { org: OrganizationDetail }) {
  const { t } = useTranslation('saas')
  const suspend = useSuspendOrganization(org.id)
  const reactivate = useReactivateOrganization(org.id)
  const endTrial = useEndTrial(org.id)
  const [reason, setReason] = useState('')
  const [planOpen, setPlanOpen] = useState(false)
  const [trialOpen, setTrialOpen] = useState(false)
  const canReactivate = org.status === 'suspended' || org.status === 'past_due'
  const canExtend = org.status === 'trial' || org.status === 'past_due' || org.status === 'suspended'

  return (
    <>
      {canExtend && (
        <Button variant="secondary" onClick={() => setTrialOpen(true)}>
          <CalendarPlus aria-hidden />
          {t('admin.org.extendTrial')}
        </Button>
      )}
      {org.status === 'trial' && org.subscription?.status === 'trialing' && (
        <ConfirmDialog
          trigger={
            <Button variant="secondary">
              <TimerOff aria-hidden />
              {t('admin.org.endTrial')}
            </Button>
          }
          title={t('admin.org.endTrialTitle', { name: org.name })}
          description={org.subscription.has_payment_method ? t('admin.org.endTrialWithCard') : t('admin.org.endTrialNoCard')}
          confirmLabel={t('admin.org.endTrial')}
          onConfirm={async () => {
            const detail = await endTrial.mutateAsync({})
            if (detail.status === 'active') toast.success(t('admin.org.trialEndedPaid', { name: org.name }))
            else toast.warning(t('admin.org.trialEndedDue', { name: org.name }))
          }}
        />
      )}
      {org.subscription && (
        <Button variant="secondary" onClick={() => setPlanOpen(true)}>
          <Package aria-hidden />
          {t('admin.org.changePlan')}
        </Button>
      )}
      {canReactivate && (
        <ConfirmDialog
          trigger={
            <Button variant="primary">
              <RotateCcw aria-hidden />
              {t('admin.org.reactivate')}
            </Button>
          }
          title={t('admin.org.reactivateTitle', { name: org.name })}
          description={t('admin.org.reactivateText')}
          confirmLabel={t('admin.org.reactivate')}
          onConfirm={async () => {
            await reactivate.mutateAsync({})
            toast.success(t('admin.org.reactivated', { name: org.name }))
          }}
        />
      )}
      {org.status !== 'suspended' && org.status !== 'cancelled' && (
        <DangerConfirmDialog
          trigger={
            <Button variant="danger">
              <Ban aria-hidden />
              {t('admin.org.suspend')}
            </Button>
          }
          title={t('admin.org.suspendTitle', { name: org.name })}
          description={t('admin.org.suspendText')}
          confirmLabel={t('admin.org.suspend')}
          confirmText={org.slug}
          onConfirm={async () => {
            await suspend.mutateAsync({ confirm: true, reason: reason.trim() })
            setReason('')
            toast.success(t('admin.org.suspended', { name: org.name }))
          }}
        >
          <div className="grid grid-cols-1 gap-1.5">
            <Label htmlFor="suspend-reason">{t('admin.org.suspendReason')}</Label>
            <Textarea id="suspend-reason" name="reason" rows={2} value={reason} onChange={(event) => setReason(event.target.value)} />
          </div>
        </DangerConfirmDialog>
      )}
      <AdminPlanDialog
        key={`${org.plan?.code}-${org.subscription?.billing_cycle}`}
        org={org}
        open={planOpen}
        onOpenChange={setPlanOpen}
      />
      <ExtendTrialDialog org={org} open={trialOpen} onOpenChange={setTrialOpen} />
    </>
  )
}

function AdminPlanDialog({ org, open, onOpenChange }: { org: OrganizationDetail; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const plans = usePlans()
  const change = useAdminChangePlan(org.id)
  const [plan, setPlan] = useState(org.plan?.code ?? '')
  const [cycle, setCycle] = useState<BillingCycle>(org.subscription?.billing_cycle ?? 'monthly')
  const selected = plans.data?.find((item) => item.code === plan)
  const tooSmall = selected?.max_units != null && org.units > selected.max_units

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next)
        if (!next) {
          // Closing (cancel or done) starts the next opening from the organization's current plan.
          setPlan(org.plan?.code ?? '')
          setCycle(org.subscription?.billing_cycle ?? 'monthly')
        }
      }}
      title={t('admin.org.changePlanTitle', { name: org.name })}
      description={t('admin.org.changePlanText')}
      confirmLabel={t('admin.org.changePlan')}
      confirmDisabled={!plan || (plan === org.plan?.code && cycle === org.subscription?.billing_cycle)}
      onConfirm={async () => {
        await change.mutateAsync({ plan_code: plan, billing_cycle: cycle })
        toast.success(t('admin.org.planChanged', { plan: selected ? pickText(selected.name, lang) : plan }))
      }}
    >
      <div className="grid grid-cols-1 gap-3">
        <div className="grid grid-cols-1 gap-1.5">
          <Label htmlFor="admin-plan">{t('admin.org.plan')}</Label>
          <Select name="plan" value={plan} onValueChange={setPlan}>
            <SelectTrigger id="admin-plan">
              <SelectValue placeholder={t('admin.org.choosePlan')} />
            </SelectTrigger>
            <SelectContent>
              {(plans.data ?? []).map((item) => (
                <SelectItem key={item.code} value={item.code}>
                  {pickText(item.name, lang)} · {formatMoney(item.price_monthly)}
                  {item.is_active ? '' : ` (${t('admin.plans.inactive')})`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selected && <PlanLimits plan={selected} className="text-xs text-muted" />}
        </div>
        <ToggleGroup type="single" value={cycle} onValueChange={(value) => value && setCycle(value as BillingCycle)} aria-label={t('billing.changePlan.cycle')} className="w-fit">
          <ToggleGroupItem value="monthly">{t('cycle.monthly')}</ToggleGroupItem>
          <ToggleGroupItem value="yearly">{t('cycle.yearly')}</ToggleGroupItem>
        </ToggleGroup>
        {tooSmall && <p className="rounded-md bg-warning-soft px-3 py-2 text-sm text-warning-ink">{t('admin.org.planTooSmall', { units: org.units })}</p>}
      </div>
    </ConfirmDialog>
  )
}

function ExtendTrialDialog({ org, open, onOpenChange }: { org: OrganizationDetail; open: boolean; onOpenChange: (open: boolean) => void }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const extend = useExtendTrial(org.id)
  const [days, setDays] = useState('7')
  const value = Number(days)
  const valid = Number.isInteger(value) && value >= 1 && value <= 90
  return (
    <ConfirmDialog
      open={open}
      onOpenChange={onOpenChange}
      title={t('admin.org.extendTitle', { name: org.name })}
      description={
        org.trial_ends_at
          ? t('admin.org.extendText', { date: formatDate(org.trial_ends_at, undefined, lang) })
          : t('admin.org.extendTextNoDate')
      }
      confirmLabel={t('admin.org.extendTrial')}
      confirmDisabled={!valid}
      onConfirm={async () => {
        await extend.mutateAsync({ days: value })
        toast.success(t('admin.org.extended', { count: value }))
      }}
    >
      <div className="grid grid-cols-1 gap-1.5">
        <Label htmlFor="extend-days">{t('admin.org.days')}</Label>
        <Input id="extend-days" name="days" type="number" inputMode="numeric" min={1} max={90} value={days} onChange={(event) => setDays(event.target.value)} className="num w-28" />
        <p className="text-xs text-muted">{t('admin.org.daysHint')}</p>
      </div>
    </ConfirmDialog>
  )
}

function SubscriptionTab({ org }: { org: OrganizationDetail }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const sub = org.subscription_detail
  const failure = useSimulateFailure(org.id)
  if (!sub) return <p className="text-sm text-muted">{t('admin.org.noSubscription')}</p>
  const source = sub.payment_source
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <section className="grid grid-cols-1 gap-3 rounded-xl border border-border bg-surface p-5 shadow-xs">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-[15px] font-bold text-fg">{t('admin.org.subscription')}</h2>
          <SubscriptionBadge status={sub.status} />
        </div>
        <dl className="grid grid-cols-1 gap-2 text-sm">
          <Line label={t('admin.org.planPrice')}>
            {pickText(sub.plan.name, lang)} · {formatMoney(sub.billing_cycle === 'yearly' ? sub.plan.price_yearly : sub.plan.price_monthly)}{' '}
            {sub.billing_cycle === 'yearly' ? t('billing.perYear') : t('billing.perMonth')}
          </Line>
          {sub.current_period_start && (
            <Line label={t('admin.org.period')}>
              {formatDate(sub.current_period_start, undefined, lang)} → {formatDate(sub.current_period_end, undefined, lang)}
            </Line>
          )}
          {sub.trial_ends_at && sub.status === 'trialing' && <Line label={t('admin.org.trialEnds')}>{formatDate(sub.trial_ends_at, undefined, lang)}</Line>}
          {sub.status === 'past_due' && (
            <>
              <Line label={t('admin.org.pastDueSince')}>{formatDate(sub.past_due_since, undefined, lang)}</Line>
              <Line label={t('admin.org.retries')}>
                {t('admin.org.retriesValue', { count: sub.retries, next: sub.next_retry_at ? formatDate(sub.next_retry_at, undefined, lang) : '—' })}
              </Line>
            </>
          )}
          {sub.cancel_at_period_end && <Line label={t('admin.org.cancellation')}>{t('admin.org.cancelsAtEnd')}</Line>}
          <Line label={t('billing.card.title')}>
            {source ? t('billing.card.masked', { brand: source.brand ?? '', last4: source.last4 ?? '' }) : t('billing.card.none')}
          </Line>
          {org.upcoming_invoice && (
            <Line label={t('admin.org.nextInvoice')}>
              {formatDate(org.upcoming_invoice.date, undefined, lang)} · {formatMoney(org.upcoming_invoice.total)}
            </Line>
          )}
        </dl>
        <div className="mt-1 flex items-start justify-between gap-4 rounded-lg border border-dashed border-border p-3">
          <div>
            <Label htmlFor="simulate-failure" className="flex items-center gap-1.5 font-semibold text-fg">
              <FlaskConical aria-hidden className="size-4 text-warning-ink" />
              {t('admin.org.simulateFailure')}
            </Label>
            <p className="mt-0.5 text-xs text-muted">{t('admin.org.simulateFailureHint')}</p>
          </div>
          <Switch
            id="simulate-failure"
            name="simulate_payment_failure"
            checked={org.simulate_payment_failure}
            disabled={failure.isPending}
            onCheckedChange={(enabled) =>
              failure
                .mutateAsync({ enabled })
                .then(() => toast.success(enabled ? t('admin.org.failureOn') : t('admin.org.failureOff')))
                .catch((error: unknown) => toast.error(errorMessage(error, t)))
            }
          />
        </div>
      </section>
      {org.usage && (
        <section className="grid grid-cols-1 content-start gap-5 rounded-xl border border-border bg-surface p-5 shadow-xs">
          <h2 className="text-[15px] font-bold text-fg">{t('billing.usage.title')}</h2>
          <UsageMeter
            label={t('billing.usage.units')}
            value={org.usage.units}
            max={org.usage.max_units}
            valueLabel={t('billing.usage.of', { value: org.usage.units, max: org.usage.max_units ?? 0 })}
            unlimitedLabel={t('billing.usage.unlimited', { value: org.usage.units })}
          />
          <UsageMeter
            label={t('billing.usage.properties')}
            value={org.usage.properties}
            max={org.usage.max_properties}
            valueLabel={t('billing.usage.of', { value: org.usage.properties, max: org.usage.max_properties ?? 0 })}
            unlimitedLabel={t('billing.usage.unlimited', { value: org.usage.properties })}
          />
          {org.usage.over_limit && <Badge tone="warning">{t('admin.org.overLimit')}</Badge>}
        </section>
      )}
    </div>
  )
}

function Line({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_minmax(0,1fr)] gap-3">
      <dt className="text-muted">{label}</dt>
      <dd className="text-fg">{children}</dd>
    </div>
  )
}

function PropertiesTab({ org }: { org: OrganizationDetail }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-surface">
      <table className="w-full min-w-[44rem] text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted">
            <th scope="col" className="px-4 py-2.5 font-semibold">{t('admin.org.property')}</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">{t('admin.org.type')}</th>
            <th scope="col" className="px-4 py-2.5 text-right font-semibold">{t('admin.org.units')}</th>
            <th scope="col" className="px-4 py-2.5 text-right font-semibold">{t('admin.org.reservations')}</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">{t('admin.org.marketplace')}</th>
            <th scope="col" className="px-4 py-2.5 font-semibold">{t('admin.org.businessDate')}</th>
          </tr>
        </thead>
        <tbody>
          {org.properties.map((property) => (
            <tr key={property.id} className="border-b border-border last:border-0">
              <td className="px-4 py-3">
                <p className="font-semibold text-fg">{property.name}</p>
                <p className="text-xs text-muted">{[property.city, property.department].filter(Boolean).join(', ') || property.slug}</p>
              </td>
              <td className="px-4 py-3 text-muted">{t(`common:propertyTypes.${property.property_type}`, { defaultValue: property.property_type })}</td>
              <td className="num px-4 py-3 text-right text-fg">{property.units}</td>
              <td className="num px-4 py-3 text-right text-fg">{property.reservations}</td>
              <td className="px-4 py-3">
                {property.marketplace_listed ? (
                  <Badge tone="success">{t('admin.org.listed', { rate: Number(property.commission_rate) })}</Badge>
                ) : (
                  <Badge tone="neutral">{t('commissions.notListed')}</Badge>
                )}
              </td>
              <td className="num px-4 py-3 text-muted">{formatDate(property.business_date, undefined, lang)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function TeamTab({ org }: { org: OrganizationDetail }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  return (
    <div className="grid grid-cols-1 gap-3">
      <div className="overflow-x-auto rounded-xl border border-border bg-surface">
        <table className="w-full min-w-[36rem] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted">
              <th scope="col" className="px-4 py-2.5 font-semibold">{t('admin.org.user')}</th>
              <th scope="col" className="px-4 py-2.5 font-semibold">{t('admin.org.role')}</th>
              <th scope="col" className="px-4 py-2.5 font-semibold">{t('admin.org.access')}</th>
              <th scope="col" className="px-4 py-2.5 font-semibold">{t('admin.org.lastLogin')}</th>
            </tr>
          </thead>
          <tbody>
            {org.users.map((user) => (
              <tr key={user.id} className="border-b border-border last:border-0">
                <td className="px-4 py-3">
                  <p className="font-semibold text-fg">{user.full_name || user.email}</p>
                  <p className="text-xs text-muted">{user.email}</p>
                </td>
                <td className="px-4 py-3">
                  <span className="text-fg">{user.role.name}</span>
                  {!user.is_active && <Badge tone="stone" className="ml-2">{t('admin.org.inactive')}</Badge>}
                </td>
                <td className="px-4 py-3 text-muted">{user.all_properties ? t('admin.org.allProperties') : t('admin.org.someProperties')}</td>
                <td className="px-4 py-3 text-muted">{user.last_login ? formatRelative(user.last_login, lang) : t('admin.org.never')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {org.pending_invitations > 0 && <p className="text-sm text-muted">{t('admin.org.pendingInvitations', { count: org.pending_invitations })}</p>}
    </div>
  )
}
