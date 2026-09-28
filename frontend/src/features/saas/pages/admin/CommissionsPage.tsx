import type { PaginationState } from '@tanstack/react-table'
import { CalendarCheck, HandCoins } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { LoadingState } from '@/components/LoadingState'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { formatMoney, normalizeLang } from '@/lib/format'
import { useAdminCommissions, useOrganizations, useRunSettlement, useSettlements, type CommissionSummary } from '../../api'
import { CommissionsTable } from '../../components/CommissionsTable'
import { SettlementList } from '../../components/CommissionsStatement'
import { monthLabel } from '../../helpers'

const ALL = 'all'
const STATUSES = ['pending', 'settled', 'reversed'] as const

function recentMonths(count: number, includeCurrent: boolean): string[] {
  const now = new Date()
  const months: string[] = []
  for (let i = includeCurrent ? 0 : 1; months.length < count; i++) {
    const date = new Date(now.getFullYear(), now.getMonth() - i, 1)
    months.push(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`)
  }
  return months
}

/** `/admin/commissions`: marketplace commissions of every hotel, monthly settlements and the settle action. */
export default function CommissionsPage() {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const orgs = useOrganizations({ page_size: 200 })
  const [status, setStatus] = useState<string>(ALL)
  const [month, setMonth] = useState<string>(ALL)
  const [organization, setOrganization] = useState<string>(ALL)
  const [q, setQ] = useState('')
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 })
  const months = useMemo(() => recentMonths(15, true), [])
  const commissions = useAdminCommissions({
    status: status === ALL ? undefined : status,
    month: month === ALL ? undefined : month,
    organization: organization === ALL ? undefined : organization,
    q: q.trim() || undefined,
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  })

  function resetPage() {
    setPagination((current) => ({ ...current, pageIndex: 0 }))
  }

  return (
    <div className="mx-auto grid grid-cols-1 w-full max-w-7xl gap-6">
      <PageHeader title={t('admin.commissions.title')} description={t('admin.commissions.description')} className="pb-0" actions={<SettleMonthButton />} />

      <Summary summary={commissions.data?.summary} />

      {commissions.isError ? (
        <ErrorState error={commissions.error} onRetry={() => void commissions.refetch()} />
      ) : (
        <CommissionsTable
          commissions={commissions.data?.results ?? []}
          isLoading={commissions.isPending}
          showOrganization
          server={{ rowCount: commissions.data?.count ?? 0, pagination, onPaginationChange: setPagination }}
          search={q}
          onSearchChange={(value) => {
            setQ(value)
            resetPage()
          }}
          empty={<EmptyState icon={HandCoins} title={t('admin.commissions.empty')} description={t('admin.commissions.emptyText')} />}
          toolbar={
            <div className="flex flex-wrap gap-2">
              <Select
                name="status"
                value={status}
                onValueChange={(value) => {
                  setStatus(value)
                  resetPage()
                }}
              >
                <SelectTrigger className="w-48" aria-label={t('commissions.status')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>{t('admin.commissions.allStatuses')}</SelectItem>
                  {STATUSES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {t(`status.commission.${value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                name="month"
                value={month}
                onValueChange={(value) => {
                  setMonth(value)
                  resetPage()
                }}
              >
                <SelectTrigger className="w-48" aria-label={t('admin.commissions.month')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  <SelectItem value={ALL}>{t('admin.commissions.allMonths')}</SelectItem>
                  {months.map((value) => (
                    <SelectItem key={value} value={value}>
                      <span className="first-letter:uppercase">{monthLabel(value, lang, 'long')}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                name="organization"
                value={organization}
                onValueChange={(value) => {
                  setOrganization(value)
                  resetPage()
                }}
              >
                <SelectTrigger className="w-60" aria-label={t('admin.commissions.organization')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-72">
                  <SelectItem value={ALL}>{t('admin.commissions.allOrganizations')}</SelectItem>
                  {(orgs.data?.results ?? []).map((org) => (
                    <SelectItem key={org.id} value={org.id}>
                      {org.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          }
        />
      )}

      <Settlements />
    </div>
  )
}

function Summary({ summary }: { summary?: CommissionSummary }) {
  const { t } = useTranslation('saas')
  return (
    <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {STATUSES.map((status) => (
        <div key={status} className="rounded-lg border border-border bg-surface p-4 shadow-xs">
          <dt className="text-[13px] font-semibold text-muted">{t(`admin.commissions.summary.${status}`)}</dt>
          <dd className="mt-1.5 text-[24px] leading-7 font-semibold tracking-[-0.02em] text-fg">{summary ? formatMoney(summary[status].total) : '—'}</dd>
          <dd className="mt-1 text-xs text-muted">{summary ? t('commissions.bookings', { count: summary[status].count }) : ''}</dd>
        </div>
      ))}
    </dl>
  )
}

function Settlements() {
  const { t } = useTranslation('saas')
  const settlements = useSettlements()
  return (
    <section className="grid grid-cols-1 gap-3">
      <div>
        <h2 className="text-[15px] font-bold text-fg">{t('admin.commissions.settlementsTitle')}</h2>
        <p className="text-sm text-muted">{t('admin.commissions.settlementsText')}</p>
      </div>
      {settlements.isPending ? (
        <LoadingState variant="rows" rows={3} />
      ) : settlements.isError ? (
        <ErrorState error={settlements.error} onRetry={() => void settlements.refetch()} />
      ) : settlements.data.results.length ? (
        <SettlementList settlements={settlements.data.results} showOrganization />
      ) : (
        <p className="rounded-lg border border-dashed border-border px-4 py-5 text-sm text-muted">{t('commissions.noSettlements')}</p>
      )}
    </section>
  )
}

function SettleMonthButton() {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const run = useRunSettlement()
  const closed = useMemo(() => recentMonths(12, false), [])
  const [month, setMonth] = useState(closed[0] ?? '')
  return (
    <ConfirmDialog
      trigger={
        <Button variant="secondary">
          <CalendarCheck aria-hidden />
          {t('admin.commissions.settle')}
        </Button>
      }
      title={t('admin.commissions.settleTitle')}
      description={t('admin.commissions.settleText')}
      confirmLabel={t('admin.commissions.settleConfirm', { month: monthLabel(month, lang, 'long') })}
      confirmDisabled={!month}
      onConfirm={async () => {
        const result = await run.mutateAsync(month)
        const count = result.settlements.filter((settlement) => settlement.period_start.startsWith(month)).length
        toast.success(t('admin.commissions.settled', { month: monthLabel(month, lang, 'long') }), { description: result.run.summary || t('admin.commissions.settledCount', { count }) })
      }}
    >
      <div className="grid grid-cols-1 gap-1.5">
        <Label htmlFor="settle-month">{t('admin.commissions.month')}</Label>
        <Select name="month" value={month} onValueChange={setMonth}>
          <SelectTrigger id="settle-month">
            <SelectValue />
          </SelectTrigger>
          <SelectContent className="max-h-72">
            {closed.map((value) => (
              <SelectItem key={value} value={value}>
                <span className="first-letter:uppercase">{monthLabel(value, lang, 'long')}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </ConfirmDialog>
  )
}
