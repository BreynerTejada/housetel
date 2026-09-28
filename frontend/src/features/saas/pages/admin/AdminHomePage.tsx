import { Ban, CircleAlert, CircleCheck, Clock, HandCoins, Receipt, Store, TrendingDown, XCircle } from 'lucide-react'
import { useMemo, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { ErrorState } from '@/components/ErrorState'
import { KpiTile } from '@/components/KpiTile'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { formatDate, formatMoney, formatNumber, normalizeLang } from '@/lib/format'
import { useMetrics, useOrganizations, usePlans, type OrganizationRow, type PlatformMetrics } from '../../api'
import { MonthlyColumns, SegmentStrip } from '../../components/charts'
import { OrganizationBadge } from '../../components/StatusBadges'
import { compactMoney, monthLabel, pickText } from '../../helpers'

const DAY = 86_400_000

/** `/admin`: how the platform is doing — recurring revenue, hotels and the marketplace. */
export default function AdminHomePage() {
  const { t } = useTranslation('saas')
  const metrics = useMetrics()
  return (
    <div className="mx-auto grid grid-cols-1 w-full max-w-7xl gap-6">
      <PageHeader title={t('admin.home.title')} description={t('admin.home.description')} className="pb-0" />
      {metrics.isPending ? (
        <LoadingState variant="rows" rows={8} />
      ) : metrics.isError ? (
        <ErrorState error={metrics.error} onRetry={() => void metrics.refetch()} />
      ) : (
        <Dashboard metrics={metrics.data} />
      )}
    </div>
  )
}

function Dashboard({ metrics }: { metrics: PlatformMetrics }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const rows = useMemo(
    () =>
      metrics.series.map((point) => ({
        month: point.month,
        subscriptions: Number(point.subscriptions),
        commissions: Number(point.commissions),
        gmv: Number(point.gmv),
        bookings: point.bookings,
      })),
    [metrics.series],
  )
  const trend = (key: 'gmv' | 'commissions') => rows.map((row) => ({ label: monthLabel(row.month, lang), value: row[key] }))
  const orgs = metrics.organizations

  return (
    <div className="grid grid-cols-1 gap-6">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)]">
        {/* The one number this view leads with. */}
        <section className="flex flex-col justify-between gap-5 rounded-xl border border-accent/25 bg-accent-soft p-5 sm:p-6">
          <div>
            <p className="eyebrow !text-accent-ink/80">{t('admin.home.mrr')}</p>
            <p className="mt-2 text-[48px] leading-none font-extrabold tracking-[-0.045em] text-accent-ink sm:text-[56px]">
              {formatMoney(metrics.mrr)}
            </p>
            <p className="mt-2 text-sm text-accent-ink/85">{t('admin.home.mrrHint')}</p>
          </div>
          <dl className="grid grid-cols-2 gap-3 border-t border-accent/20 pt-4 text-accent-ink">
            <div>
              <dt className="text-xs font-semibold text-accent-ink/75">{t('admin.home.arr')}</dt>
              <dd className="num mt-0.5 font-bold">{compactMoney(metrics.arr, lang)}</dd>
            </div>
            <div>
              <dt className="text-xs font-semibold text-accent-ink/75">{t('admin.home.trialMrr')}</dt>
              <dd className="num mt-0.5 font-bold">+{compactMoney(metrics.trial_mrr, lang)}</dd>
            </div>
          </dl>
        </section>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <KpiTile
            label={t('admin.home.activeOrgs')}
            value={
              <>
                {formatNumber(orgs.active, lang)}
                <span className="ml-2 text-sm font-medium tracking-normal text-muted">{t('admin.home.inTrial', { count: orgs.trial })}</span>
              </>
            }
            icon={CircleCheck}
          />
          <KpiTile
            label={t('admin.home.churn')}
            value={`${formatNumber(metrics.churn_30d, lang, 1)} %`}
            icon={TrendingDown}
            intent="lower-is-better"
          />
          <KpiTile
            label={t('admin.home.gmv')}
            value={compactMoney(metrics.gmv_month, lang)}
            icon={Store}
            trend={trend('gmv')}
            formatTrendValue={(value) => compactMoney(value, lang)}
          />
          <KpiTile
            label={t('admin.home.commissions')}
            value={compactMoney(metrics.commissions_month, lang)}
            icon={HandCoins}
            trend={trend('commissions')}
            formatTrendValue={(value) => compactMoney(value, lang)}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
        <div className="grid grid-cols-1 gap-4">
          <MonthlyColumns
            title={t('admin.home.revenueTitle')}
            description={t('admin.home.revenueText')}
            rows={rows}
            series={[
              { key: 'subscriptions', label: t('admin.home.subscriptions'), color: 'var(--chart-1)' },
              { key: 'commissions', label: t('admin.home.commissionsSeries'), color: 'var(--chart-2)' },
            ]}
          />
          <MonthlyColumns
            title={t('admin.home.gmvTitle')}
            description={t('admin.home.gmvText')}
            rows={rows}
            series={[{ key: 'gmv', label: t('admin.home.gmvSeries'), color: 'var(--chart-2)' }]}
            tooltipFooter={(row) => (
              <p className="mt-1.5 text-xs text-muted">{t('admin.home.bookings', { count: Number(row.bookings) })}</p>
            )}
            tableExtra={{ label: t('admin.home.bookingsColumn'), value: (row) => formatNumber(Number(row.bookings), lang) }}
          />
        </div>
        <div className="grid grid-cols-1 content-start gap-4">
          <OrganizationsPanel metrics={metrics} />
          <MoneyOwedPanel metrics={metrics} />
          <AttentionPanel />
        </div>
      </div>
    </div>
  )
}

function Panel({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="grid grid-cols-1 gap-4 rounded-xl border border-border bg-surface p-4 shadow-xs sm:p-5">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-[15px] font-bold text-fg">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function OrganizationsPanel({ metrics }: { metrics: PlatformMetrics }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const plans = usePlans()
  const orgs = metrics.organizations
  const planTotal = metrics.plan_mix.reduce((sum, row) => sum + row.count, 0)
  return (
    <Panel
      title={t('admin.home.orgsTitle', { count: orgs.total })}
      action={
        <Link to="/admin/organizations" className="text-sm font-semibold text-accent-ink underline-offset-4 hover:underline">
          {t('admin.home.seeAll')}
        </Link>
      }
    >
      <SegmentStrip
        title={t('admin.home.byStatus')}
        total={orgs.total}
        segments={[
          { key: 'active', label: t('status.organization.active'), value: orgs.active, className: 'bg-success', icon: <CircleCheck aria-hidden className="size-3.5 text-success-ink" /> },
          { key: 'trial', label: t('status.organization.trial'), value: orgs.trial, className: 'bg-info', icon: <Clock aria-hidden className="size-3.5 text-info-ink" /> },
          { key: 'past_due', label: t('status.organization.past_due'), value: orgs.past_due, className: 'bg-warning', icon: <CircleAlert aria-hidden className="size-3.5 text-warning-ink" /> },
          { key: 'suspended', label: t('status.organization.suspended'), value: orgs.suspended, className: 'bg-danger', icon: <Ban aria-hidden className="size-3.5 text-danger-ink" /> },
          { key: 'cancelled', label: t('status.organization.cancelled'), value: orgs.cancelled, className: 'bg-stone', icon: <XCircle aria-hidden className="size-3.5 text-stone-ink" /> },
        ]}
      />
      {metrics.plan_mix.length > 0 && (
        <div className="grid grid-cols-1 gap-2 border-t border-border pt-3">
          <p className="text-xs font-semibold text-muted">{t('admin.home.planMix')}</p>
          <ul className="grid grid-cols-1 gap-2">
            {metrics.plan_mix.map((row) => {
              const plan = plans.data?.find((item) => item.code === row.plan)
              return (
                <li key={row.plan} className="grid grid-cols-[6rem_minmax(0,1fr)_2rem] items-center gap-3 text-sm">
                  <span className="truncate font-medium text-fg">{plan ? pickText(plan.name, lang) : row.plan}</span>
                  <span aria-hidden className="h-1.5 overflow-hidden rounded-full bg-accent-soft">
                    <span className="block h-full rounded-full bg-accent" style={{ width: `${planTotal ? (row.count * 100) / planTotal : 0}%` }} />
                  </span>
                  <span className="num text-right font-semibold text-fg">{row.count}</span>
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </Panel>
  )
}

function MoneyOwedPanel({ metrics }: { metrics: PlatformMetrics }) {
  const { t } = useTranslation('saas')
  return (
    <Panel title={t('admin.home.owedTitle')}>
      <dl className="grid grid-cols-2 gap-3">
        <Link to="/admin/billing" className="rounded-lg border border-border p-3 transition-colors hover:border-border-strong">
          <dt className="flex items-center gap-1.5 text-xs font-semibold text-muted">
            <Receipt aria-hidden className="size-3.5" />
            {t('admin.home.unpaid', { count: metrics.unpaid_invoices.count })}
          </dt>
          <dd className="num mt-1 font-bold text-fg">{formatMoney(metrics.unpaid_invoices.total)}</dd>
        </Link>
        <Link to="/admin/commissions" className="rounded-lg border border-border p-3 transition-colors hover:border-border-strong">
          <dt className="flex items-center gap-1.5 text-xs font-semibold text-muted">
            <HandCoins aria-hidden className="size-3.5" />
            {t('admin.home.pendingCommissions')}
          </dt>
          <dd className="num mt-1 font-bold text-fg">{formatMoney(metrics.commissions_pending)}</dd>
        </Link>
      </dl>
    </Panel>
  )
}

function attentionReason(org: OrganizationRow, now: number): { order: number; key: string; days?: number } | null {
  if (org.status === 'suspended') return { order: 0, key: 'suspended' }
  if (org.status === 'past_due') return { order: 1, key: 'pastDue' }
  if (org.status === 'trial' && org.trial_ends_at) {
    const days = Math.ceil((new Date(org.trial_ends_at).getTime() - now) / DAY)
    if (days <= 7) return { order: 2, key: days < 0 ? 'trialOver' : days === 0 ? 'trialToday' : 'trialEnding', days: Math.max(days, 0) }
  }
  if (org.simulate_payment_failure) return { order: 3, key: 'simulatedFailure' }
  return null
}

function AttentionPanel() {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const orgs = useOrganizations({ page_size: 200 })
  const items = useMemo(() => {
    // eslint-disable-next-line react-hooks/purity -- "now" only buckets trials by days left
    const now = Date.now()
    return (orgs.data?.results ?? [])
      .map((org) => ({ org, reason: attentionReason(org, now) }))
      .filter((item): item is { org: OrganizationRow; reason: NonNullable<ReturnType<typeof attentionReason>> } => item.reason !== null)
      .sort((a, b) => a.reason.order - b.reason.order)
      .slice(0, 6)
  }, [orgs.data])

  return (
    <Panel title={t('admin.home.attentionTitle')}>
      {orgs.isPending ? (
        <LoadingState variant="rows" rows={3} className="p-0" />
      ) : items.length === 0 ? (
        <p className="text-sm text-muted">{t('admin.home.attentionEmpty')}</p>
      ) : (
        <ul className="-mx-2 grid grid-cols-1 gap-0.5">
          {items.map(({ org, reason }) => (
            <li key={org.id}>
              <Link
                to={`/admin/organizations/${org.id}`}
                className="flex items-center justify-between gap-3 rounded-md px-2 py-2 transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/55"
              >
                <span className="min-w-0">
                  <span className="block truncate font-semibold text-fg">{org.name}</span>
                  <span className="block text-xs text-muted">
                    {t(`admin.home.reason.${reason.key}`, {
                      count: reason.days ?? 0,
                      date: formatDate(org.trial_ends_at, undefined, lang),
                    })}
                  </span>
                </span>
                <OrganizationBadge status={org.status} />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
