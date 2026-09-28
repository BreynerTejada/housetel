import type { ColumnDef, PaginationState } from '@tanstack/react-table'
import { ReceiptText } from 'lucide-react'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router'
import { DataTable } from '@/components/DataTable'
import { DateRangePicker } from '@/components/DatePicker'
import { EmptyState } from '@/components/EmptyState'
import { ErrorState } from '@/components/ErrorState'
import { KpiTile } from '@/components/KpiTile'
import { MoneyText } from '@/components/Money'
import { Badge } from '@/components/ui/badge'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { DateRangeValue } from '@/lib/date-ranges'
import { rangePreset } from '@/lib/date-ranges'
import { formatDate, formatMoney, formatNumber, normalizeLang } from '@/lib/format'
import { useInvoices, useInvoiceTotals, type InvoiceKind, type InvoiceStatus, type InvoiceSummary } from '../api'
import { useDebounced } from '../hooks'
import { compactMoney } from '../lib/labels'
import { InvoiceStatusBadge, SimulatedBadge } from './common'

const STATUSES: InvoiceStatus[] = ['accepted', 'issued', 'rejected', 'error', 'draft', 'cancelled']
const ALL = 'all'

/** Tab "Facturas": the documents sent to the DIAN, with the period's totals and filters (rows open the detail). */
export function InvoicesTab({ businessDate, onOpenInvoice }: { businessDate?: string; onOpenInvoice: (id: string) => void }) {
  const { t, i18n } = useTranslation('compliance')
  const lang = normalizeLang(i18n.language)
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState<InvoiceStatus | typeof ALL>(ALL)
  const [kind, setKind] = useState<InvoiceKind | typeof ALL>(ALL)
  const [range, setRange] = useState<DateRangeValue | null>(null)
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 25 })
  const q = useDebounced(search.trim())

  const month = rangePreset('thisMonth', businessDate ?? new Date())
  const totals = useInvoiceTotals(range?.from ?? month.from, range?.to ?? month.to)
  const query = useInvoices({
    q: q || undefined,
    status: status === ALL ? undefined : status,
    kind: kind === ALL ? undefined : kind,
    start: range?.from,
    end: range?.to,
    page: pagination.pageIndex + 1,
    page_size: pagination.pageSize,
  })

  // a new filter starts again on the first page
  const firstPage = () => setPagination((current) => ({ ...current, pageIndex: 0 }))

  const columns = useMemo<ColumnDef<InvoiceSummary>[]>(
    () => [
      {
        accessorKey: 'number',
        header: t('invoices.number'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="grid gap-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="num font-semibold text-fg">{row.original.number || t('invoice.draft')}</span>
              {row.original.kind === 'credit_note' && <Badge tone="outline">{t('invoice.kinds.short.credit_note')}</Badge>}
            </div>
            <InvoiceStatusBadge status={row.original.status} className="sm:hidden" />
          </div>
        ),
      },
      {
        accessorKey: 'total',
        header: t('invoices.total'),
        enableSorting: false,
        meta: { align: 'right' },
        cell: ({ row }) => (
          <MoneyText
            value={row.original.kind === 'credit_note' ? `-${row.original.total}` : row.original.total}
            currency={row.original.currency}
            highlightNegative
          />
        ),
      },
      {
        accessorKey: 'issue_date',
        header: t('invoices.date'),
        enableSorting: false,
        cell: ({ row }) => <span className="num whitespace-nowrap">{formatDate(row.original.issue_date, undefined, lang)}</span>,
      },
      {
        accessorKey: 'customer_name',
        header: t('invoices.customer'),
        enableSorting: false,
        cell: ({ row }) => (
          <div className="min-w-40">
            <p className="text-fg">{row.original.customer_name}</p>
            <p className="num text-xs text-muted">{row.original.customer_document}</p>
          </div>
        ),
      },
      {
        accessorKey: 'reservation_code',
        header: t('invoices.reservation'),
        enableSorting: false,
        cell: ({ row }) =>
          row.original.reservation_id ? (
            <Link
              to={`/app/reservations/${row.original.reservation_id}`}
              onClick={(event) => event.stopPropagation()}
              className="num font-semibold text-accent-ink hover:underline"
            >
              {row.original.reservation_code}
            </Link>
          ) : (
            '—'
          ),
      },
      {
        accessorKey: 'status',
        header: t('invoices.status'),
        enableSorting: false,
        meta: { className: 'hidden sm:table-cell' },
        cell: ({ row }) => (
          <div className="flex flex-wrap items-center gap-1.5">
            <InvoiceStatusBadge status={row.original.status} />
            {row.original.is_exempt && <Badge tone="accent">{t('invoice.exempt')}</Badge>}
            <SimulatedBadge mode={row.original.mode} className="hidden xl:inline-flex" />
          </div>
        ),
      },
    ],
    [t, lang],
  )

  const toolbar = (
    <>
      <Select
        value={status}
        onValueChange={(value) => {
          setStatus(value as InvoiceStatus | typeof ALL)
          firstPage()
        }}
        name="status"
      >
        <SelectTrigger className="h-8 w-full sm:w-44" aria-label={t('invoices.status')}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>{t('invoices.allStatuses')}</SelectItem>
          {STATUSES.map((value) => (
            <SelectItem key={value} value={value}>
              {t(`invoiceStatus.${value}`)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={kind}
        onValueChange={(value) => {
          setKind(value as InvoiceKind | typeof ALL)
          firstPage()
        }}
        name="kind"
      >
        <SelectTrigger className="h-8 w-full sm:w-44" aria-label={t('invoices.kind')}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>{t('invoices.allKinds')}</SelectItem>
          <SelectItem value="invoice">{t('invoice.kinds.invoice')}</SelectItem>
          <SelectItem value="credit_note">{t('invoice.kinds.credit_note')}</SelectItem>
        </SelectContent>
      </Select>
      <DateRangePicker
        value={range}
        onChange={(value) => {
          setRange(value)
          firstPage()
        }}
        today={businessDate}
        presets={['thisMonth', 'lastMonth', 'last30']}
        placeholder={t('invoices.anyDate')}
        aria-label={t('invoices.dates')}
        className="h-8 w-full sm:w-60"
      />
    </>
  )

  const summary = totals.data
  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTile
          label={range ? t('invoices.kpi.totalRange') : t('invoices.kpi.totalMonth')}
          value={summary ? <span title={formatMoney(summary.total)}>{compactMoney(summary.total, lang)}</span> : '—'}
          intent="neutral"
        />
        <KpiTile label={t('invoices.kpi.count')} value={summary ? formatNumber(summary.invoices, lang) : '—'} intent="neutral" />
        <KpiTile
          label={t('invoices.kpi.vat')}
          value={summary ? <span title={formatMoney(summary.tax_total)}>{compactMoney(summary.tax_total, lang)}</span> : '—'}
          intent="neutral"
        />
        <KpiTile
          label={t('invoices.kpi.exempt')}
          value={summary ? formatNumber(summary.exempt.count, lang) : '—'}
          intent="neutral"
        />
      </div>
      {query.isError ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <DataTable
          aria-label={t('invoices.title')}
          columns={columns}
          data={query.data?.results ?? []}
          isLoading={query.isPending || query.isFetching}
          getRowId={(row) => row.id}
          search={search}
          onSearchChange={(value) => {
            setSearch(value)
            firstPage()
          }}
          searchPlaceholder={t('invoices.search')}
          toolbar={toolbar}
          onRowClick={(row) => onOpenInvoice(row.id)}
          server={{ rowCount: query.data?.count ?? 0, pagination, onPaginationChange: setPagination }}
          empty={<EmptyState icon={ReceiptText} title={t('invoices.empty')} description={t('invoices.emptyHint')} />}
        />
      )}
    </div>
  )
}
