import type { ColumnDef, PaginationState } from '@tanstack/react-table'
import { Building, FlaskConical } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router'
import { DataTable } from '@/components/DataTable'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tooltip } from '@/components/ui/tooltip'
import { formatDate, normalizeLang } from '@/lib/format'
import { useOrganizations, usePlans, type OrganizationRow } from '../../api'
import { OrganizationBadge } from '../../components/StatusBadges'
import { pickText } from '../../helpers'

const STATUSES = ['trial', 'active', 'past_due', 'suspended', 'cancelled'] as const
const ALL = 'all'

/** `/admin/organizations`: every hotel organization with its plan, state, size and revenue. */
export default function OrganizationsPage() {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const navigate = useNavigate()
  const plans = usePlans()
  const [status, setStatus] = useState<string>(ALL)
  const [plan, setPlan] = useState<string>(ALL)
  const [q, setQ] = useState('')
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 })
  const orgs = useOrganizations({
    status: status === ALL ? undefined : status,
    plan: plan === ALL ? undefined : plan,
    q: q.trim() || undefined,
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  })

  const columns = useMemo<ColumnDef<OrganizationRow>[]>(
    () => [
      {
        id: 'name',
        accessorKey: 'name',
        header: t('admin.orgs.organization'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 font-semibold text-fg">
              <span className="truncate">{row.original.name}</span>
              {row.original.simulate_payment_failure && (
                <Tooltip content={t('admin.orgs.simulatedFailure')}>
                  <FlaskConical aria-label={t('admin.orgs.simulatedFailure')} className="size-3.5 shrink-0 text-warning-ink" />
                </Tooltip>
              )}
            </p>
            <p className="truncate text-xs text-muted">{row.original.nit ? `NIT ${row.original.nit}` : row.original.slug}</p>
          </div>
        ),
      },
      {
        id: 'plan',
        accessorFn: (row) => row.plan?.code ?? '',
        header: t('admin.orgs.plan'),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.plan ? (
            <div>
              <p className="font-medium text-fg">{pickText(row.original.plan.name, lang)}</p>
              {row.original.subscription && (
                <p className="text-xs text-muted">{t(`cycle.${row.original.subscription.billing_cycle}`)}</p>
              )}
            </div>
          ) : (
            <span className="text-sm text-muted">{t('admin.orgs.noPlan')}</span>
          ),
      },
      {
        id: 'status',
        accessorKey: 'status',
        header: t('admin.orgs.status'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="grid grid-cols-1 gap-0.5">
            <OrganizationBadge status={row.original.status} />
            {row.original.status === 'trial' && row.original.trial_ends_at && (
              <span className="text-xs text-muted">{t('admin.orgs.trialUntil', { date: formatDate(row.original.trial_ends_at, undefined, lang) })}</span>
            )}
          </div>
        ),
      },
      {
        id: 'units',
        accessorKey: 'units',
        header: t('admin.orgs.units'),
        enableSorting: false,
        meta: { align: 'right' },
        cell: ({ row }) => {
          const max = row.original.plan?.max_units
          const over = max !== null && max !== undefined && row.original.units > max
          return (
            <span className={over ? 'num font-semibold text-danger-ink' : 'num text-fg'}>
              {row.original.units}
              <span className="text-muted">{max ? ` / ${max}` : ''}</span>
            </span>
          )
        },
      },
      {
        id: 'properties',
        accessorKey: 'properties_count',
        header: t('admin.orgs.properties'),
        enableSorting: false,
        meta: { align: 'right' },
        cell: ({ row }) => <span className="num text-fg">{row.original.properties_count ?? 0}</span>,
      },
      {
        id: 'users',
        accessorKey: 'users_count',
        header: t('admin.orgs.users'),
        enableSorting: false,
        meta: { align: 'right' },
        cell: ({ row }) => <span className="num text-fg">{row.original.users_count ?? 0}</span>,
      },
      {
        id: 'mrr',
        accessorKey: 'mrr',
        header: t('admin.orgs.mrr'),
        enableSorting: false,
        meta: { align: 'right' },
        cell: ({ row }) => <MoneyText value={row.original.mrr} className="font-semibold text-fg" />,
      },
      {
        id: 'created',
        accessorKey: 'customer_since',
        header: t('admin.orgs.created'),
        enableSorting: false,
        cell: ({ row }) => <span className="num text-sm text-muted">{formatDate(row.original.customer_since, undefined, lang)}</span>,
      },
    ],
    [t, lang],
  )

  function resetPage() {
    setPagination((current) => ({ ...current, pageIndex: 0 }))
  }

  return (
    <div className="mx-auto grid grid-cols-1 w-full max-w-7xl gap-2">
      <PageHeader title={t('admin.orgs.title')} description={t('admin.orgs.description')} />
      {orgs.isError ? (
        <ErrorState error={orgs.error} onRetry={() => void orgs.refetch()} />
      ) : (
        <DataTable
          columns={columns}
          data={orgs.data?.results ?? []}
          getRowId={(row) => row.id}
          isLoading={orgs.isPending}
          search={q}
          onSearchChange={(value) => {
            setQ(value)
            resetPage()
          }}
          searchPlaceholder={t('admin.orgs.search')}
          server={{ rowCount: orgs.data?.count ?? 0, pagination, onPaginationChange: setPagination }}
          onRowClick={(row) => navigate(`/admin/organizations/${row.id}`)}
          aria-label={t('admin.orgs.title')}
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
                <SelectTrigger className="w-44" aria-label={t('admin.orgs.status')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>{t('admin.orgs.allStatuses')}</SelectItem>
                  {STATUSES.map((value) => (
                    <SelectItem key={value} value={value}>
                      {t(`status.organization.${value}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                name="plan"
                value={plan}
                onValueChange={(value) => {
                  setPlan(value)
                  resetPage()
                }}
              >
                <SelectTrigger className="w-40" aria-label={t('admin.orgs.plan')}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>{t('admin.orgs.allPlans')}</SelectItem>
                  {(plans.data ?? []).map((item) => (
                    <SelectItem key={item.code} value={item.code}>
                      {pickText(item.name, lang)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          }
          empty={<EmptyState icon={Building} title={t('admin.orgs.empty')} description={t('admin.orgs.emptyText')} />}
        />
      )}
    </div>
  )
}
