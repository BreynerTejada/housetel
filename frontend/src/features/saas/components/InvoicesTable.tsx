import type { ColumnDef } from '@tanstack/react-table'
import { Download } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { DataTable, type DataTableServerOptions } from '@/components/DataTable'
import { MoneyText } from '@/components/Money'
import { Button } from '@/components/ui/button'
import { errorMessage } from '@/lib/errors'
import { formatDate, formatDateRange, normalizeLang } from '@/lib/format'
import { downloadInvoicePdf, type PlatformInvoice } from '../api'
import { InvoiceBadge } from './StatusBadges'

/** Platform invoices: number, period, concept, total, status and actions (PDF + optional extra actions). */
export function InvoicesTable({
  invoices,
  isLoading,
  admin = false,
  showOrganization = false,
  actions,
  empty,
  pageSize = 10,
  server,
  toolbar,
  search,
  onSearchChange,
  onRowClick,
}: {
  invoices: PlatformInvoice[]
  isLoading?: boolean
  admin?: boolean
  showOrganization?: boolean
  actions?: (invoice: PlatformInvoice) => ReactNode
  empty?: ReactNode
  pageSize?: number
  server?: DataTableServerOptions
  toolbar?: ReactNode
  search?: string
  onSearchChange?: (value: string) => void
  onRowClick?: (invoice: PlatformInvoice) => void
}) {
  const { t, i18n } = useTranslation('saas')
  const lang = normalizeLang(i18n.language)
  const [downloading, setDownloading] = useState<string | null>(null)

  const columns = useMemo<ColumnDef<PlatformInvoice>[]>(() => {
    const cols: ColumnDef<PlatformInvoice>[] = [
      {
        id: 'number',
        accessorKey: 'number',
        header: t('invoices.number'),
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="num font-semibold whitespace-nowrap text-fg">{row.original.number}</p>
            <p className="text-xs text-muted">{formatDate(row.original.issued_at, undefined, lang)}</p>
          </div>
        ),
      },
    ]
    if (showOrganization) {
      cols.push({
        id: 'organization',
        accessorFn: (invoice) => invoice.organization.name,
        header: t('invoices.organization'),
        cell: ({ row }) => <span className="font-medium text-fg">{row.original.organization.name}</span>,
      })
    }
    cols.push(
      {
        id: 'concept',
        accessorKey: 'kind',
        header: t('invoices.concept'),
        cell: ({ row }) => (
          <div className="min-w-0">
            <p className="text-fg">{t(`invoices.kind.${row.original.kind}`)}</p>
            <p className="num text-xs text-muted">{formatDateRange(row.original.period_start, row.original.period_end, lang)}</p>
          </div>
        ),
      },
      {
        id: 'total',
        accessorFn: (invoice) => Number(invoice.total),
        header: t('invoices.total'),
        meta: { align: 'right' },
        cell: ({ row }) => (
          <div className="text-right">
            <MoneyText value={row.original.total} className="font-semibold text-fg" />
            <p className="num text-xs text-muted">
              {t('invoices.taxIncluded', { rate: Number(row.original.tax_rate) })}
            </p>
          </div>
        ),
      },
      {
        id: 'status',
        accessorKey: 'status',
        header: t('invoices.status'),
        cell: ({ row }) => (
          <div className="grid grid-cols-1 gap-0.5">
            <InvoiceBadge status={row.original.status} />
            {row.original.status === 'paid' && row.original.paid_at && (
              <span className="text-xs text-muted">{formatDate(row.original.paid_at, undefined, lang)}</span>
            )}
            {row.original.status === 'failed' && row.original.last_error && (
              <span className="max-w-56 truncate text-xs text-danger-ink" title={row.original.last_error}>
                {row.original.last_error}
              </span>
            )}
          </div>
        ),
      },
      {
        id: 'actions',
        header: () => <span className="sr-only">{t('invoices.actions')}</span>,
        enableSorting: false,
        meta: { align: 'right' },
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-1.5">
            {actions?.(row.original)}
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t('invoices.downloadPdf', { number: row.original.number })}
              title={t('invoices.downloadPdf', { number: row.original.number })}
              loading={downloading === row.original.id}
              onClick={async (event) => {
                event.stopPropagation()
                setDownloading(row.original.id)
                try {
                  await downloadInvoicePdf(row.original, lang, admin)
                } catch (error) {
                  toast.error(errorMessage(error, t))
                } finally {
                  setDownloading(null)
                }
              }}
            >
              <Download aria-hidden />
            </Button>
          </div>
        ),
      },
    )
    return cols
  }, [t, lang, showOrganization, actions, downloading, admin])

  return (
    <DataTable
      columns={columns}
      data={invoices}
      getRowId={(invoice) => invoice.id}
      isLoading={isLoading}
      pageSize={pageSize}
      server={server}
      toolbar={toolbar}
      search={search}
      onSearchChange={onSearchChange}
      searchPlaceholder={t('invoices.searchPlaceholder')}
      onRowClick={onRowClick}
      empty={empty ?? t('invoices.empty')}
      aria-label={t('invoices.title')}
    />
  )
}
