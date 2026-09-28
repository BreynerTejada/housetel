import { Store } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { formatMoney, normalizeLang } from '@/lib/format'
import { useHotelCommissions, type Settlement } from '../api'
import { monthLabel } from '../helpers'
import { CommissionsTable } from './CommissionsTable'
import { SettlementBadge } from './StatusBadges'

/** The hotel's statement of marketplace commissions (Housetel charges a % of lodging on marketplace bookings). */
export function CommissionsStatement() {
  const { t } = useTranslation('saas')
  const query = useHotelCommissions()

  if (query.isPending) return <LoadingState variant="rows" rows={6} />
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  const data = query.data
  const month = data.this_month
  const monthTotal = Number(month.pending.total) + Number(month.settled.total)
  const monthCount = month.pending.count + month.settled.count

  return (
    <div className="grid grid-cols-1 gap-6">
      <p className="max-w-2xl text-sm text-muted">{t('commissions.intro')}</p>
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Figure label={t('commissions.thisMonth')} value={formatMoney(monthTotal)} hint={t('commissions.bookings', { count: monthCount })} />
        <Figure
          label={t('commissions.pendingTotal')}
          value={formatMoney(data.summary.pending.total)}
          hint={t('commissions.pendingHint', { count: data.summary.pending.count })}
        />
        <Figure
          label={t('commissions.settledTotal')}
          value={formatMoney(data.summary.settled.total)}
          hint={t('commissions.bookings', { count: data.summary.settled.count })}
        />
      </dl>

      <section className="grid grid-cols-1 gap-3">
        <h2 className="text-[15px] font-bold text-fg">{t('commissions.ratesTitle')}</h2>
        <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {data.rates.map((rate) => (
            <li key={rate.property_id} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-surface px-4 py-3">
              <div className="min-w-0">
                <p className="truncate font-semibold text-fg">{rate.name}</p>
                <Badge tone={rate.marketplace_listed ? 'success' : 'neutral'} className="mt-1">
                  {rate.marketplace_listed ? t('commissions.listed') : t('commissions.notListed')}
                </Badge>
              </div>
              <p className="num shrink-0 text-right text-[22px] leading-none font-bold text-fg">
                {Number(rate.commission_rate)}
                <span className="text-sm font-semibold text-muted"> %</span>
              </p>
            </li>
          ))}
        </ul>
      </section>

      <section className="grid grid-cols-1 gap-3">
        <h2 className="text-[15px] font-bold text-fg">{t('commissions.settlementsTitle')}</h2>
        {data.settlements.length ? (
          <SettlementList settlements={data.settlements} />
        ) : (
          <p className="rounded-lg border border-dashed border-border px-4 py-5 text-sm text-muted">{t('commissions.noSettlements')}</p>
        )}
      </section>

      <section className="grid grid-cols-1 gap-3">
        <h2 className="text-[15px] font-bold text-fg">{t('commissions.recentTitle')}</h2>
        <CommissionsTable
          commissions={data.recent}
          empty={<EmptyState icon={Store} title={t('commissions.emptyTitle')} description={t('commissions.emptyText')} />}
        />
      </section>
    </div>
  )
}

function Figure({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4 shadow-xs">
      <dt className="text-[13px] font-semibold text-muted">{label}</dt>
      <dd className="mt-2 text-[24px] leading-7 font-semibold tracking-[-0.02em] text-fg">{value}</dd>
      <dd className="mt-1 text-xs text-muted">{hint}</dd>
    </div>
  )
}

export function SettlementList({ settlements, showOrganization = false }: { settlements: Settlement[]; showOrganization?: boolean }) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  return (
    <ul className="divide-y divide-border rounded-lg border border-border bg-surface">
      {settlements.map((settlement) => (
        <li key={settlement.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3 sm:grid-cols-[minmax(0,1fr)_auto_auto]">
          <div className="min-w-0">
            <p className="font-semibold text-fg first-letter:uppercase">
              {showOrganization ? `${settlement.organization.name} · ` : ''}
              {monthLabel(settlement.period_start.slice(0, 7), lang, 'long')}
            </p>
            <p className="text-xs text-muted">
              {t('commissions.bookings', { count: settlement.commissions_count })}
              {settlement.invoice ? ` · ${t('commissions.invoice', { number: settlement.invoice.number })}` : ''}
            </p>
          </div>
          <MoneyText value={settlement.total} className="text-right font-semibold text-fg" />
          <div className="col-span-2 sm:col-span-1 sm:justify-self-end">
            <SettlementBadge status={settlement.status} />
          </div>
        </li>
      ))}
    </ul>
  )
}
