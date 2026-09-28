import type { ColumnDef, PaginationState } from '@tanstack/react-table'
import { Building2, Plus, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useSearchParams } from 'react-router'
import { DataTable } from '@/components/DataTable'
import { ErrorState } from '@/components/ErrorState'
import { MoneyText } from '@/components/Money'
import { PageHeader } from '@/components/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useCan } from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { moneyLabel, toCents } from '@/features/finance/money'
import { COMPANY_KINDS, useCompanies, type Company, type CompanyFilters, type CompanyKind } from '../api'
import { CompanyFormDialog } from '../components/CompanyFormDialog'

const ALL = 'all'

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay)
    return () => window.clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export default function CompaniesPage() {
  const { t } = useTranslation('corporate')
  const navigate = useNavigate()
  const canManage = useCan('corporate.manage')
  const [params, setParams] = useSearchParams()
  const [creatingState, setCreatingState] = useState(false)
  const creating = creatingState || params.get('new') === '1'
  const search = params.get('q') ?? ''
  const kind = params.get('kind') ?? ''
  const withBalance = params.get('balance') === '1'
  const inactive = params.get('inactive') === '1'
  const debouncedSearch = useDebounced(search.trim(), 300)
  const filterKey = JSON.stringify([debouncedSearch, kind, withBalance, inactive])
  const [pageState, setPageState] = useState({ key: filterKey, pagination: { pageIndex: 0, pageSize: 25 } })
  const pagination: PaginationState =
    pageState.key === filterKey ? pageState.pagination : { pageIndex: 0, pageSize: pageState.pagination.pageSize }

  const filters: CompanyFilters = {
    q: debouncedSearch || undefined,
    kind: (kind || undefined) as CompanyKind | undefined,
    active: inactive ? undefined : true,
    with_balance: withBalance || undefined,
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  }
  const companies = useCompanies(filters)
  const filtered = Boolean(debouncedSearch || kind || withBalance || inactive)

  function setParam(name: string, value: string) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set(name, value)
        else next.delete(name)
        next.delete('new')
        return next
      },
      { replace: true },
    )
  }

  function setCreating(open: boolean) {
    setCreatingState(open)
    if (!open && params.get('new')) setParam('new', '')
  }

  const columns = useMemo<ColumnDef<Company>[]>(
    () => [
      { id: 'company', header: t('list.columns.company'), enableSorting: false, cell: ({ row }) => <CompanyCell company={row.original} /> },
      {
        id: 'nit',
        header: t('list.columns.nit'),
        enableSorting: false,
        cell: ({ row }) => <span className="num whitespace-nowrap text-[13px]">{row.original.nit_display}</span>,
      },
      {
        id: 'credit',
        header: t('list.columns.credit'),
        enableSorting: false,
        cell: ({ row }) => <CreditCell company={row.original} />,
      },
      {
        id: 'balance',
        header: t('list.columns.balance'),
        enableSorting: false,
        meta: { align: 'right' },
        cell: ({ row }) => <BalanceCell company={row.original} />,
      },
    ],
    [t],
  )

  return (
    <div className="mx-auto w-full max-w-7xl">
      <PageHeader
        title={t('list.title')}
        description={t('list.description')}
        actions={
          canManage && (
            <Button variant="primary" onClick={() => setCreating(true)}>
              <Plus aria-hidden />
              {t('list.new')}
            </Button>
          )
        }
      />

      <DataTable
        aria-label={t('list.tableLabel')}
        columns={columns}
        data={companies.data?.results ?? []}
        getRowId={(row) => row.id}
        isLoading={companies.isPending || companies.isPlaceholderData}
        search={search}
        onSearchChange={(value) => setParam('q', value)}
        searchPlaceholder={t('list.search')}
        server={{
          rowCount: companies.data?.count ?? 0,
          pagination,
          onPaginationChange: (updater) =>
            setPageState(() => ({ key: filterKey, pagination: typeof updater === 'function' ? updater(pagination) : updater })),
        }}
        onRowClick={(row) => navigate(`/app/companies/${row.id}`)}
        toolbar={
          <div className="flex flex-wrap items-center gap-2">
            <Select name="kind" value={kind || ALL} onValueChange={(value) => setParam('kind', value === ALL ? '' : value)}>
              <SelectTrigger className="h-8 w-48" aria-label={t('list.filters.kind')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>{t('list.filters.anyKind')}</SelectItem>
                {COMPANY_KINDS.map((value) => (
                  <SelectItem key={value} value={value}>
                    {t(`kinds.${value}`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ToggleFilter pressed={withBalance} onClick={() => setParam('balance', withBalance ? '' : '1')}>
              {t('list.filters.withBalance')}
            </ToggleFilter>
            <ToggleFilter pressed={inactive} onClick={() => setParam('inactive', inactive ? '' : '1')}>
              {t('list.filters.inactive')}
            </ToggleFilter>
            {filtered && (
              <Button variant="ghost" size="sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
                <X aria-hidden />
                {t('list.clearFilters')}
              </Button>
            )}
          </div>
        }
        empty={
          companies.isError ? (
            <ErrorState error={companies.error} onRetry={() => void companies.refetch()} className="py-0" />
          ) : filtered ? (
            t('list.emptyFiltered')
          ) : (
            <span className="grid justify-items-center gap-2">
              <Building2 aria-hidden className="size-5 text-muted" />
              <span className="font-semibold text-fg">{t('list.empty')}</span>
              <span>{t('list.emptyHint')}</span>
            </span>
          )
        }
      />

      <CompanyFormDialog open={creating} onOpenChange={setCreating} onSaved={(company) => navigate(`/app/companies/${company.id}`)} />
    </div>
  )
}

function ToggleFilter({ pressed, onClick, children }: { pressed: boolean; onClick: () => void; children: string }) {
  return (
    <Button
      variant="secondary"
      size="sm"
      aria-pressed={pressed}
      onClick={onClick}
      className={cn(pressed && 'border-accent/40 bg-accent-soft text-accent-ink hover:bg-accent-soft')}
    >
      {children}
    </Button>
  )
}

function CompanyCell({ company }: { company: Company }) {
  const { t } = useTranslation('corporate')
  return (
    <div className="flex min-w-0 items-center gap-3">
      <span
        aria-hidden
        className={cn(
          'grid size-9 shrink-0 place-items-center rounded-lg border text-[13px] font-bold',
          company.kind === 'travel_agency' ? 'border-info/25 bg-info-soft text-info-ink' : 'border-border bg-surface-2 text-muted',
        )}
      >
        {(company.trade_name || company.legal_name).slice(0, 2).toUpperCase()}
      </span>
      <div className="min-w-0">
        <p className="flex flex-wrap items-center gap-1.5">
          <span className="truncate font-semibold text-fg">{company.legal_name}</span>
          {!company.is_active && <Badge tone="stone">{t('badges.inactive')}</Badge>}
        </p>
        <p className="truncate text-xs text-muted">
          {[t(`kinds.${company.kind}`), company.trade_name, company.city].filter(Boolean).join(' · ')}
        </p>
      </div>
    </div>
  )
}

function CreditCell({ company }: { company: Company }) {
  const { t } = useTranslation('corporate')
  if (!company.credit_enabled) return <span className="text-[13px] text-subtle">{t('list.noCredit')}</span>
  return (
    <span className="grid text-[13px]">
      <span className="text-fg">{company.credit_limit ? moneyLabel(company.credit_limit) : t('list.noLimit')}</span>
      <span className="text-xs text-muted">{t('list.terms', { count: company.payment_terms_days })}</span>
    </span>
  )
}

function BalanceCell({ company }: { company: Company }) {
  const { t } = useTranslation('corporate')
  const receivable = company.receivable
  if (!receivable || (toCents(receivable.balance) === 0 && toCents(receivable.in_progress) === 0)) {
    return <span className="text-[13px] text-subtle">—</span>
  }
  return (
    <span className="grid justify-items-end">
      <MoneyText value={receivable.balance} className="font-semibold" />
      {toCents(receivable.overdue) > 0 ? (
        <span className="text-xs text-danger-ink">{t('list.overdue', { amount: moneyLabel(receivable.overdue) })}</span>
      ) : toCents(receivable.in_progress) > 0 ? (
        <span className="text-xs text-muted">{t('list.inProgress', { amount: moneyLabel(receivable.in_progress) })}</span>
      ) : null}
    </span>
  )
}
